import ee
import streamlit as st
import os
from datetime import datetime

# =========================================================
# CONSTANTES
# =========================================================
PROJECT_ID = "rising-method-478510-v9"
ASSET_REGION = "projects/rising-method-478510-v9/assets/GEE_OT_Region"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Seuils NDVI
NDVI_LOW_THRESHOLD = 0.30
NDVI_HIGH_THRESHOLD = 0.50

# Seuils NDMI
NDMI_LOW_THRESHOLD = 0.10
NDMI_HIGH_THRESHOLD = 0.30


# =========================================================
# INITIALISATION EARTH ENGINE
# =========================================================
def init_ee():
    """
    Initialise Earth Engine.

    Cas 1 : mode local
    - si le fichier private-key.json existe, on l'utilise

    Cas 2 : mode Streamlit Cloud
    - on utilise les secrets Streamlit :
      * gee_service_account
      * gee_private_key
    """
    try:
        key_file = "private-key.json"

        # MODE LOCAL
        if os.path.exists(key_file):
            credentials = ee.ServiceAccountCredentials(
                email="streamlit-ndvi-app@rising-method-478510-v9.iam.gserviceaccount.com",
                key_file=key_file
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
            return True

        # MODE STREAMLIT CLOUD
        elif "gee_service_account" in st.secrets and "gee_private_key" in st.secrets:
            credentials = ee.ServiceAccountCredentials(
                email=st.secrets["gee_service_account"],
                key_data=st.secrets["gee_private_key"]
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
            return True

        else:
            st.error("❌ Secrets 'gee_service_account' ou 'gee_private_key' manquants dans Streamlit Cloud.")
            st.info("Vérifiez la section 'Settings > Secrets' de votre application.")
            return False

    except Exception as e:
        st.error(f"❌ Erreur d'authentification GEE : {str(e)}")
        return False


# =========================================================
# RÉGION PAR DÉFAUT
# =========================================================
def get_region():
    """
    Retourne la région d'étude par défaut.
    """
    return ee.FeatureCollection(ASSET_REGION)


# =========================================================
# CONSTRUCTION D'UNE PARCELLE DEPUIS DU TEXTE
# =========================================================
def build_parcel_from_text(coord_text: str):
    """
    Construit une parcelle (polygone) à partir d'un texte saisi.

    Format attendu :
    une ligne par point sous la forme :
    latitude,longitude
    """
    if not coord_text or not coord_text.strip():
        raise ValueError("Aucune coordonnée saisie.")

    lines = coord_text.strip().splitlines()
    points = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            raise ValueError("Chaque ligne doit contenir : latitude,longitude")

        lat = float(parts[0])
        lon = float(parts[1])

        # Earth Engine attend [longitude, latitude]
        points.append([lon, lat])

    if len(points) < 3:
        raise ValueError("Il faut au moins 3 points pour créer un polygone.")

    if points[0] != points[-1]:
        points.append(points[0])

    polygon = ee.Geometry.Polygon([points])
    return ee.FeatureCollection([ee.Feature(polygon)])


# =========================================================
# CONSTRUCTION D'UNE PARCELLE DEPUIS GEOJSON
# =========================================================
def build_parcel_from_geojson(geojson_feature):
    """
    Construit une parcelle Earth Engine à partir d'un polygone GeoJSON
    dessiné sur la carte.
    """
    if geojson_feature is None:
        raise ValueError("Aucun polygone GeoJSON fourni.")

    geometry = geojson_feature.get("geometry", {})
    geom_type = geometry.get("type")

    if geom_type != "Polygon":
        raise ValueError("Le dessin doit être un polygone.")

    coordinates = geometry.get("coordinates")
    polygon = ee.Geometry.Polygon(coordinates)
    return ee.FeatureCollection([ee.Feature(polygon)])


# =========================================================
# MASQUE DES NUAGES
# =========================================================
def mask_s2_clouds(image):
    """
    Supprime certains pixels non souhaités à partir de la bande SCL.
    """
    scl = image.select("SCL")
    mask = (
        scl.neq(3)
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
        .And(scl.neq(11))
    )
    return image.updateMask(mask)


# =========================================================
# COLLECTION SENTINEL-2
# =========================================================
def get_image_collection(region, start_date: str, end_date: str, cloud_threshold: int = 20):
    """
    Retourne la collection Sentinel-2 filtrée :
    - sur la parcelle étudiée
    - sur l'intervalle de dates demandé
    - selon un seuil maximal de nuages
    """
    collection = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(region)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
        .map(mask_s2_clouds)
    )
    return collection


# =========================================================
# DATES DISPONIBLES DANS UN MOIS
# =========================================================
def get_available_dates_for_month(region, year: int, month: int, cloud_threshold: int = 20):
    """
    Retourne la liste des dates disponibles (YYYY-MM-DD)
    pour une parcelle, une année et un mois donnés.
    """
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")

    collection = get_image_collection(
        region=region,
        start_date=start.format("YYYY-MM-dd").getInfo(),
        end_date=end.format("YYYY-MM-dd").getInfo(),
        cloud_threshold=cloud_threshold
    )

    timestamps = collection.aggregate_array("system:time_start").getInfo() or []

    date_strings = []
    for ts in timestamps:
        date_str = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        date_strings.append(date_str)

    date_strings = sorted(list(set(date_strings)))
    return date_strings


# =========================================================
# IMAGE D'UNE DATE DONNÉE
# =========================================================
def get_image_for_date(region, selected_date: str, cloud_threshold: int = 20):
    """
    Retourne l'image Sentinel-2 de la date choisie.

    Si plusieurs images existent le même jour,
    on garde celle avec le plus faible taux de nuages.
    """
    start_dt = datetime.strptime(selected_date, "%Y-%m-%d")
    end_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = (start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
               .timestamp())

    # Plus simple : jour choisi -> jour suivant
    next_day = datetime.strptime(selected_date, "%Y-%m-%d")
    from datetime import timedelta
    next_day = next_day + timedelta(days=1)
    next_day_str = next_day.strftime("%Y-%m-%d")

    collection = (
        get_image_collection(region, start_str, next_day_str, cloud_threshold)
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    image = collection.first()

    return ee.Image(image).clip(region)


# =========================================================
# CALCUL DES INDICES
# =========================================================
def get_ndvi(image):
    """
    Calcule le NDVI :
    NDVI = (B8 - B4) / (B8 + B4)
    """
    return image.normalizedDifference(["B8", "B4"]).rename("NDVI")


def get_ndmi(image):
    """
    Calcule le NDMI :
    NDMI = (B8 - B11) / (B8 + B11)

    Cet indice renseigne sur l'état hydrique de la végétation.
    """
    return image.normalizedDifference(["B8", "B11"]).rename("NDMI")


# =========================================================
# CLASSIFICATION VIGUEUR VÉGÉTALE
# =========================================================
def classify_ndvi_vigor(ndvi_image):
    """
    Classe le NDVI en 3 classes :
    1 = végétation faible
    2 = végétation moyenne
    3 = végétation forte
    """
    classified = (
        ee.Image(2)
        .where(ndvi_image.lt(NDVI_LOW_THRESHOLD), 1)
        .where(ndvi_image.gte(NDVI_HIGH_THRESHOLD), 3)
        .updateMask(ndvi_image.mask())
        .rename("Vigor_Class")
    )
    return classified


# =========================================================
# CLASSIFICATION ÉTAT HYDRIQUE
# =========================================================
def classify_ndmi_hydric(ndmi_image):
    """
    Classe le NDMI en 3 classes :
    1 = état hydrique faible
    2 = état hydrique moyen
    3 = état hydrique satisfaisant
    """
    classified = (
        ee.Image(2)
        .where(ndmi_image.lt(NDMI_LOW_THRESHOLD), 1)
        .where(ndmi_image.gte(NDMI_HIGH_THRESHOLD), 3)
        .updateMask(ndmi_image.mask())
        .rename("Hydric_Class")
    )
    return classified


# =========================================================
# CARTE DE PRIORITÉ
# =========================================================
def build_priority_map(vigor_class, hydric_class):
    """
    Construit une carte de priorité d'intervention.

    1 = zone normale
    2 = zone à surveiller
    3 = zone prioritaire
    """
    priority = ee.Image(1)

    vigilance = vigor_class.eq(1).Or(hydric_class.eq(1))
    critique = vigor_class.eq(1).And(hydric_class.eq(1))

    priority = priority.where(vigilance, 2)
    priority = priority.where(critique, 3)

    return priority.updateMask(vigor_class.mask().And(hydric_class.mask())).rename("Priority_Class")


# =========================================================
# STATISTIQUES D'IMAGE
# =========================================================
def get_image_stats(image, band_name="NDVI", region=None):
    """
    Calcule :
    - moyenne
    - écart-type
    - percentile 25
    - percentile 75
    - minimum
    - maximum
    """
    if region is None:
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
# SURFACES PAR CLASSES
# =========================================================
def get_class_surface_stats(classified_image, class_dict, region=None):
    """
    Calcule la surface (en hectares) de chaque classe.
    """
    if region is None:
        region = get_region()

    pixel_area_ha = ee.Image.pixelArea().divide(10000)
    results = {}

    for class_value, class_name in class_dict.items():
        area_img = pixel_area_ha.updateMask(classified_image.eq(class_value)).rename("area")

        stats = area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region.geometry(),
            scale=10,
            maxPixels=1e13,
            bestEffort=True
        )

        results[class_name] = stats.get("area").getInfo() or 0.0

    return results


# =========================================================
# PARAMÈTRES D'AFFICHAGE
# =========================================================
def get_ndvi_vis_params():
    return {
        "min": 0,
        "max": 1,
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }


def get_ndmi_vis_params():
    return {
        "min": -0.3,
        "max": 0.5,
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }


def get_vigor_vis_params():
    return {
        "min": 1,
        "max": 3,
        "palette": ["#d73027", "#fee08b", "#1a9850"]
    }


def get_hydric_vis_params():
    return {
        "min": 1,
        "max": 3,
        "palette": ["#d73027", "#fee08b", "#4575b4"]
    }


def get_priority_vis_params():
    return {
        "min": 1,
        "max": 3,
        "palette": ["#1a9850", "#fee08b", "#d73027"]
    }
