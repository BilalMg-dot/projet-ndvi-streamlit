import ee


# =========================================================
# CONSTANTES
# =========================================================
PROJECT_ID = "rising-method-478510-v9"
ASSET_REGION = "projects/rising-method-478510-v9/assets/GEE_OT_Region"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Seuils de classification de la différence NDVI
NEGATIVE_THRESHOLD = -0.05
POSITIVE_THRESHOLD = 0.05


# =========================================================
# INITIALISATION EARTH ENGINE
# =========================================================
def init_ee():
    ee.Initialize(project=PROJECT_ID)


# =========================================================
# CHARGEMENT DE LA REGION
# =========================================================
def get_region():
    return ee.FeatureCollection(ASSET_REGION)


# =========================================================
# MASQUE SIMPLE DES NUAGES
# =========================================================
def mask_s2_clouds(image):
    scl = image.select("SCL")
    mask = (
        scl.neq(3)   # ombre de nuage
        .And(scl.neq(8))   # nuage moyen
        .And(scl.neq(9))   # nuage fort
        .And(scl.neq(10))  # cirrus
        .And(scl.neq(11))  # neige/glace
    )
    return image.updateMask(mask)


# =========================================================
# DATES D'UN MOIS
# =========================================================
def get_month_start_end(year: int, month: int):
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")
    return start, end


# =========================================================
# COLLECTION SENTINEL-2 D'UN MOIS
# =========================================================
def get_monthly_collection(year: int, month: int, cloud_threshold: int = 15):
    region = get_region()
    start, end = get_month_start_end(year, month)

    collection = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
        .map(mask_s2_clouds)
    )
    return collection


# =========================================================
# CALCUL NDVI MENSUEL
# =========================================================
def get_monthly_ndvi(year: int, month: int, cloud_threshold: int = 15):
    region = get_region()
    collection = get_monthly_collection(year, month, cloud_threshold)

    image = collection.median().clip(region)
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")

    start, _ = get_month_start_end(year, month)

    return ndvi.set({
        "year": year,
        "month": month,
        "system:time_start": start.millis(),
        "image_count": collection.size()
    })


# =========================================================
# CALCUL NDVI D'UNE PÉRIODE (PLUSIEURS MOIS)
# =========================================================
def get_period_ndvi(year: int, months: list[int], cloud_threshold: int = 15):
    images = [get_monthly_ndvi(year, month, cloud_threshold) for month in months]
    image_collection = ee.ImageCollection(images)
    ndvi_period = image_collection.mean().rename("NDVI")
    return ndvi_period


# =========================================================
# NOMBRE TOTAL D'IMAGES D'UNE PÉRIODE
# =========================================================
def get_period_image_count(year: int, months: list[int], cloud_threshold: int = 15):
    total = 0
    for month in months:
        collection = get_monthly_collection(year, month, cloud_threshold)
        total += collection.size().getInfo()
    return total


# =========================================================
# DIFFÉRENCE ENTRE DEUX PÉRIODES
# =========================================================
def get_ndvi_difference(period1_ndvi, period2_ndvi):
    common_mask = period1_ndvi.mask().And(period2_ndvi.mask())
    p1 = period1_ndvi.updateMask(common_mask)
    p2 = period2_ndvi.updateMask(common_mask)
    diff = p2.subtract(p1).rename("NDVI_diff")
    return diff


# =========================================================
# CLASSIFICATION DU CHANGEMENT
# Classes :
# 1 = diminution
# 2 = stable
# 3 = augmentation
# =========================================================
def classify_ndvi_difference(diff_image):
    classified = (
        ee.Image(2)
        .where(diff_image.lt(NEGATIVE_THRESHOLD), 1)
        .where(diff_image.gt(POSITIVE_THRESHOLD), 3)
        .updateMask(diff_image.mask())
        .rename("Change_Class")
    )
    return classified


# =========================================================
# STATISTIQUES D'UNE IMAGE
# =========================================================
def get_image_stats(image, band_name="NDVI"):
    region = get_region()

    stats = image.reduceRegion(
        reducer=(
            ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.percentile([25, 75]), sharedInputs=True)
            .combine(reducer2=ee.Reducer.min(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.max(), sharedInputs=True)
        ),
        geometry=region.geometry(),
        scale=10,
        maxPixels=1e13,
        bestEffort=True
    )

    info = stats.getInfo()

    return {
        "mean": info.get(f"{band_name}_mean"),
        "stdDev": info.get(f"{band_name}_stdDev"),
        "p25": info.get(f"{band_name}_p25"),
        "p75": info.get(f"{band_name}_p75"),
        "min": info.get(f"{band_name}_min"),
        "max": info.get(f"{band_name}_max"),
    }


# =========================================================
# SURFACES PAR CLASSE DE CHANGEMENT
# Retourne les surfaces en hectares
# =========================================================
def get_change_surface_stats(classified_image):
    region = get_region()
    pixel_area_ha = ee.Image.pixelArea().divide(10000)

    diminution = pixel_area_ha.updateMask(classified_image.eq(1)).rename("area")
    stable = pixel_area_ha.updateMask(classified_image.eq(2)).rename("area")
    augmentation = pixel_area_ha.updateMask(classified_image.eq(3)).rename("area")

    diminution_stats = diminution.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region.geometry(),
        scale=10,
        maxPixels=1e13,
        bestEffort=True
    )

    stable_stats = stable.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region.geometry(),
        scale=10,
        maxPixels=1e13,
        bestEffort=True
    )

    augmentation_stats = augmentation.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region.geometry(),
        scale=10,
        maxPixels=1e13,
        bestEffort=True
    )

    return {
        "diminution_ha": diminution_stats.get("area").getInfo() or 0.0,
        "stable_ha": stable_stats.get("area").getInfo() or 0.0,
        "augmentation_ha": augmentation_stats.get("area").getInfo() or 0.0,
    }


# =========================================================
# PARAMÈTRES D'AFFICHAGE
# =========================================================
def get_ndvi_vis_params():
    return {
        "min": 0,
        "max": 1,
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }


def get_diff_vis_params():
    return {
        "min": -0.4,
        "max": 0.4,
        "palette": ["#b2182b", "#ef8a62", "#fddbc7", "#f7f7f7", "#d9f0d3", "#7fbf7b", "#1a9850"]
    }


def get_classified_change_vis_params():
    return {
        "min": 1,
        "max": 3,
        "palette": ["#d73027", "#f0f0f0", "#1a9850"]
    }