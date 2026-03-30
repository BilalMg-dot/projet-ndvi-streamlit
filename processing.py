import ee
import streamlit as st
import os

# =========================================================
# CONSTANTES ET CONFIGURATION
# =========================================================
PROJECT_ID = "rising-method-478510-v9"
ASSET_REGION = "projects/rising-method-478510-v9/assets/GEE_OT_Region"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

NEGATIVE_THRESHOLD = -0.05
POSITIVE_THRESHOLD = 0.05

# =========================================================
# INITIALISATION EARTH ENGINE
# =========================================================
def init_ee():
    try:
        # 1. Tentative avec les Secrets Streamlit (Mode Cloud)
        if "gee_service_account_json" in st.secrets:
            creds_dict = st.secrets["gee_service_account_json"]
            credentials = ee.ServiceAccountCredentials(
                email=creds_dict['client_email'],
                key_data=creds_dict['private_key']
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
            return True

        # 2. Tentative avec fichier local (Mode Dev)
        elif os.path.exists("private-key.json"):
            credentials = ee.ServiceAccountCredentials(
                email="streamlit-ndvi-app@rising-method-478510-v9.iam.gserviceaccount.com",
                key_file="private-key.json"
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
            return True
            
        return False
    except Exception as e:
        st.error(f"Erreur d'initialisation GEE : {e}")
        return False

# =========================================================
# FONCTIONS DE TRAITEMENT
# =========================================================

def get_region():
    return ee.FeatureCollection(ASSET_REGION)

def mask_s2_clouds(image):
    scl = image.select("SCL")
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return image.updateMask(mask)

def get_month_start_end(year, month):
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")
    return start, end

def get_monthly_collection(year, month, cloud_threshold=15):
    region = get_region()
    start, end = get_month_start_end(year, month)
    return (ee.ImageCollection(S2_COLLECTION)
            .filterBounds(region)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
            .map(mask_s2_clouds))

def get_monthly_ndvi(year, month, cloud_threshold=15):
    region = get_region()
    collection = get_monthly_collection(year, month, cloud_threshold)
    image = collection.median().clip(region)
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    start, _ = get_month_start_end(year, month)
    return ndvi.set({
        "year": year, "month": month,
        "system:time_start": start.millis(),
        "image_count": collection.size()
    })

def get_period_ndvi(year, months, cloud_threshold=15):
    images = [get_monthly_ndvi(year, month, cloud_threshold) for month in months]
    return ee.ImageCollection(images).mean().rename("NDVI")

def get_period_image_count(year, months, cloud_threshold=15):
    total = 0
    for month in months:
        total += get_monthly_collection(year, month, cloud_threshold).size().getInfo()
    return total

def get_ndvi_difference(p1, p2):
    mask = p1.mask().And(p2.mask())
    return p2.subtract(p1).updateMask(mask).rename("NDVI_diff")

def classify_ndvi_difference(diff):
    return (ee.Image(2)
            .where(diff.lt(NEGATIVE_THRESHOLD), 1)
            .where(diff.gt(POSITIVE_THRESHOLD), 3)
            .updateMask(diff.mask()).rename("Change_Class"))

def get_image_stats(image, band_name):
    region = get_region()
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True)
               .combine(ee.Reducer.percentile([25, 75]), sharedInputs=True),
        geometry=region.geometry(), scale=30, maxPixels=1e9, bestEffort=True
    ).getInfo()
    return {
        "mean": stats.get(f"{band_name}_mean"),
        "stdDev": stats.get(f"{band_name}_stdDev"),
        "p25": stats.get(f"{band_name}_p25"),
        "p75": stats.get(f"{band_name}_p75")
    }

def get_change_surface_stats(classified):
    region = get_region()
    area_img = ee.Image.pixelArea().divide(10000)
    
    def get_area(val):
        return area_img.updateMask(classified.eq(val)).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=region.geometry(), 
            scale=30, maxPixels=1e9, bestEffort=True).get("area").getInfo() or 0

    return {
        "diminution_ha": get_area(1),
        "stable_ha": get_area(2),
        "augmentation_ha": get_area(3)
    }

# Paramètres de visualisation
def get_ndvi_vis_params(): return {"min": 0, "max": 0.8, "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]}
def get_diff_vis_params(): return {"min": -0.2, "max": 0.2, "palette": ["red", "white", "green"]}
def get_classified_change_vis_params(): return {"min": 1, "max": 3, "palette": ["#d73027", "#f0f0f0", "#1a9850"]}
