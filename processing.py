import ee
import streamlit as st
import os
import geemap.foliumap as geemap # Plus léger pour le déploiement web

# =========================================================
# CONFIGURATION ET CONSTANTES
# =========================================================
st.set_page_config(page_title="GEE NDVI Monitor", layout="wide")

PROJECT_ID = "rising-method-478510-v9"
ASSET_REGION = "projects/rising-method-478510-v9/assets/GEE_OT_Region"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

NEGATIVE_THRESHOLD = -0.05
POSITIVE_THRESHOLD = 0.05

# =========================================================
# INITIALISATION EARTH ENGINE
# =========================================================
def init_ee():
    """
    Initialise GEE sans chercher de fichier JSON physique en mode Cloud.
    """
    try:
        # PRIORITÉ 1 : Secrets Streamlit (Mode Déployé)
        if "gee_service_account_json" in st.secrets:
            creds = st.secrets["gee_service_account_json"]
            credentials = ee.ServiceAccountCredentials(
                email=creds["client_email"],
                key_data=creds["private_key"]
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
            return True

        # PRIORITÉ 2 : Fichier local (Mode Développement)
        elif os.path.exists("private-key.json"):
            # Ici, on utilise le chemin classique pour tes tests en local
            ee.Initialize(
                credentials=ee.ServiceAccountCredentials(
                    email="streamlit-ndvi-app@rising-method-478510-v9.iam.gserviceaccount.com",
                    key_file="private-key.json"
                ),
                project=PROJECT_ID
            )
            return True

        else:
            st.error("❌ Erreur : Aucune méthode d'authentification trouvée (Secrets ou JSON).")
            return False
    except Exception as e:
        st.error(f"❌ Échec de la connexion à Google Earth Engine : {e}")
        return False

# =========================================================
# FONCTIONS DE TRAITEMENT (Optimisées)
# =========================================================

def get_region():
    return ee.FeatureCollection(ASSET_REGION)

def mask_s2_clouds(image):
    scl = image.select("SCL")
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return image.updateMask(mask)

def get_monthly_ndvi(year, month, cloud_threshold=15):
    region = get_region()
    start = ee.Date.fromYMD(year, month, 1)
    end = start.advance(1, "month")
    
    collection = (ee.ImageCollection(S2_COLLECTION)
                  .filterBounds(region)
                  .filterDate(start, end)
                  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
                  .map(mask_s2_clouds))
    
    image = collection.median().clip(region)
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    
    return ndvi.set({
        "year": year, 
        "month": month, 
        "system:time_start": start.millis(),
        "image_count": collection.size()
    })

def get_ndvi_vis_params():
    return {
        "min": 0, "max": 0.8, 
        "palette": ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#01665e"]
    }

# =========================================================
# INTERFACE UTILISATEUR (UI)
# =========================================================

def main():
    st.title("🛰️ Analyse de la Végétation (NDVI)")
    
    if not init_ee():
        st.stop() # Arrête l'application si l'auth échoue

    # --- Barre latérale ---
    st.sidebar.header("Paramètres")
    year = st.sidebar.slider("Année", 2015, 2025, 2023)
    month = st.sidebar.slider("Mois", 1, 12, 6)
    cloud_pct = st.sidebar.number_input("Seuil de nuages (%)", 0, 100, 15)

    # --- Calculs ---
    with st.spinner("Calcul du NDVI en cours..."):
        try:
            region_fc = get_region()
            ndvi_img = get_monthly_ndvi(year, month, cloud_pct)
            
            # Vérification si des images existent
            count = ndvi_img.get("image_count").getInfo()
            
            if count == 0:
                st.warning(f"Aucune image trouvée pour {month}/{year} avec ce seuil de nuages.")
            else:
                st.success(f"Analyse basée sur {count} images Sentinel-2.")
                
                # --- Affichage de la carte ---
                m = geemap.Map()
                m.centerObject(region_fc, 10)
                m.addLayer(ndvi_img, get_ndvi_vis_params(), f"NDVI {month}/{year}")
                m.addLayer(region_fc, {"color": "red"}, "Zone d'étude", False)
                m.to_streamlit(height=600)
                
        except Exception as e:
            st.error(f"Erreur lors du traitement : {e}")

if __name__ == "__main__":
    main()