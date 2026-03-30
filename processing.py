import ee
import streamlit as st
import os

# =========================================================
# CONSTANTES
# =========================================================
# On garde les constantes liées au projet et à la collection Sentinel-2.
PROJECT_ID = "rising-method-478510-v9"
ASSET_REGION = "projects/rising-method-478510-v9/assets/GEE_OT_Region"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Seuils simples pour classer la vigueur végétale (NDVI)
NDVI_LOW_THRESHOLD = 0.30
NDVI_HIGH_THRESHOLD = 0.50

# Seuils simples pour classer l'état hydrique (NDMI)
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
    Retourne la région d'étude par défaut depuis les assets GEE.
    """
    return ee.FeatureCollection(ASSET_REGION)


# =========================================================
# CONSTRUCTION D'UNE PARCELLE À PARTIR DE COORDONNÉES
# =========================================================
def build_parcel_from_text(coord_text: str):
    """
    Construit une parcelle (polygone) à partir d'un texte saisi par l'utilisateur.

    Format attendu :
    une ligne par point avec :
    latitude,longitude

    Exemple :
    32.5021,-6.4132
    32.5028,-6.4011
    32.4950,-6.3998
    32.4942,-6.4110

    Attention :
    - l'utilisateur saisit latitude,longitude
    - Earth Engine attend longitude,latitude
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
            raise ValueError("Chaque ligne doit contenir exactement : latitude,longitude")

        lat = float(parts[0])
        lon = float(parts[1])

        # Earth Engine attend [longitude, latitude]
        points.append([lon, lat])

    if len(points) < 3:
        raise ValueError("Il faut au moins 3 points pour construire un polygone.")

    # Fermer automatiquement le polygone si besoin
    if points[0] != points[-1]:
        points.append(points[0])

    polygon = ee.Geometry.Polygon([points])
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
        scl.neq(3)    # ombre de nuage
        .And(scl.neq(8))   # nuage moyen
        .And(scl.neq(9))   # nuage fort
        .And(scl.neq(10))  # cirrus
        .And(scl.neq(11))  # neige / glace
    )
    return image.updateMask(mask)


# =========================================================
# DÉBUT ET FIN D'UN MOIS
# =========================================================
def get_month_start_end(year: int, month: int):
    """
    Retourne la date de début et de fin d'un mois.
    """
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")
    return start, end


# =========================================================
# COLLECTION SENTINEL-2 SUR UNE PARCELLE
# =========================================================
def get_monthly_collection(year: int, month: int, cloud_threshold: int = 15, region=None):
    """
    Retourne la collection Sentinel-2 filtrée :
    - sur une zone donnée
    - sur un mois donné
    - selon un seuil de nuages
    """
    if region is None:
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
# NOMBRE D'IMAGES UTILISÉES
# =========================================================
def get_month_image_count(year: int, month: int, cloud_threshold: int = 15, region=None):
    """
    Retourne le nombre d'images Sentinel-2 retenues.
    """
    collection = get_monthly_collection(year, month, cloud_threshold, region)
    return collection.size().getInfo()


# =========================================================
# IMAGE MÉDIANE D'UN MOIS
# =========================================================
def get_monthly_composite(year: int, month: int, cloud_threshold: int = 15, region=None):
    """
    Construit l'image médiane d'un mois sur la parcelle étudiée.
    """
    if region is None:
        region = get_region()

    collection = get_monthly_collection(year, month, cloud_threshold, region)
    image = collection.median().clip(region)

    start, _ = get_month_start_end(year, month)

    return image.set({
        "year": year,
        "month": month,
        "system:time_start": start.millis(),
        "image_count": collection.size()
    })


# =========================================================
# CALCUL NDVI
# =========================================================
def get_monthly_ndvi(year: int, month: int, cloud_threshold: int = 15, region=None):
    """
    Calcule le NDVI sur la parcelle étudiée.

    NDVI = (B8 - B4) / (B8 + B4)
    """
    image = get_monthly_composite(year, month, cloud_threshold, region)
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return ndvi


# =========================================================
# CALCUL NDMI (INDICE HYDRIQUE)
# =========================================================
def get_monthly_ndmi(year: int, month: int, cloud_threshold: int = 15, region=None):
    """
    Calcule le NDMI sur la parcelle étudiée.

    NDMI = (B8 - B11) / (B8 + B11)

    Cet indice donne une indication sur l'état hydrique de la végétation.
    """
    image = get_monthly_composite(year, month, cloud_threshold, region)
    ndmi = image.normalizedDifference(["B8", "B11"]).rename("NDMI")
    return ndmi


# =========================================================
# CLASSIFICATION DE LA VIGUEUR VÉGÉTALE
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
# CLASSIFICATION DE L'ÉTAT HYDRIQUE
# =========================================================
def classify_ndmi_hydric(ndmi_image):
    """
    Classe le NDMI en 3 classes :

    1 = état hydrique faible / stress potentiel
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
# CARTE DE PRIORITÉ D'INTERVENTION
# =========================================================
def build_priority_map(vigor_class, hydric_class):
    """
    Construit une carte de priorité d'intervention.

    Règles simples :
    - 1 = zone normale
    - 2 = zone à surveiller
    - 3 = zone prioritaire (faible végétation + faible état hydrique)

    Logique :
    - si vigueur faible ET état hydrique faible => priorité forte
    - si un seul des deux est faible => vigilance
    - sinon => zone normale
    """
    priority = ee.Image(1)

    vigilance = vigor_class.eq(1).Or(hydric_class.eq(1))
    critique = vigor_class.eq(1).And(hydric_class.eq(1))

    priority = priority.where(vigilance, 2)
    priority = priority.where(critique, 3)

    return priority.updateMask(vigor_class.mask().And(hydric_class.mask())).rename("Priority_Class")


# =========================================================
# STATISTIQUES D'UNE IMAGE
# =========================================================
def get_image_stats(image, band_name="NDVI", region=None):
    """
    Calcule des statistiques descriptives sur une image :
    - moyenne
    - écart-type
    - P25
    - P75
    - min
    - max
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
# SURFACES PAR CLASSE
# =========================================================
def get_class_surface_stats(classified_image, class_dict, region=None):
    """
    Calcule la surface (en hectares) de chaque classe d'une image classée.

    Paramètres :
    - classified_image : image classée
    - class_dict : dictionnaire du type {1: "faible", 2: "moyen", 3: "fort"}
    - region : parcelle à analyser
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
# PARAMÈTRES D'AFFICHAGE DES CARTES
# =========================================================
def get_ndvi_vis_params():
    """
    Paramètres d'affichage du NDVI.
    """
    return {
        "min": 0,
        "max": 1,
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }


def get_ndmi_vis_params():
    """
    Paramètres d'affichage du NDMI.
    """
    return {
        "min": -0.3,
        "max": 0.5,
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }


def get_vigor_vis_params():
    """
    Paramètres d'affichage des classes de vigueur végétale.
    """
    return {
        "min": 1,
        "max": 3,
        "palette": ["#d73027", "#fee08b", "#1a9850"]
    }


def get_hydric_vis_params():
    """
    Paramètres d'affichage des classes hydriques.
    """
    return {
        "min": 1,
        "max": 3,
        "palette": ["#d73027", "#fee08b", "#4575b4"]
    }


def get_priority_vis_params():
    """
    Paramètres d'affichage de la carte de priorité d'intervention.
    """
    return {
        "min": 1,
        "max": 3,
        "palette": ["#1a9850", "#fee08b", "#d73027"]
    }