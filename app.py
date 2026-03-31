import pandas as pd
import plotly.express as px
import streamlit as st
import geemap.foliumap as geemap
import folium
from folium.plugins import Draw, Fullscreen
from streamlit_folium import st_folium

from processing import (
    init_ee,
    build_parcel_from_text,
    build_parcel_from_geojson,
    get_available_dates_for_month,
    get_image_for_date,
    get_ndvi,
    get_ndmi,
    classify_ndvi_vigor,
    classify_ndmi_hydric,
    build_priority_map,
    get_image_stats,
    get_class_surface_stats,
    get_ndvi_vis_params,
    get_ndmi_vis_params,
    get_vigor_vis_params,
    get_hydric_vis_params,
    get_priority_vis_params,
)

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="Suivi agricole", layout="wide")

st.title("🌿 Suivi agricole de parcelle")

# =========================================================
# INIT EE
# =========================================================
if not init_ee():
    st.stop()

# =========================================================
# SESSION
# =========================================================
if "parcel_geojson" not in st.session_state:
    st.session_state["parcel_geojson"] = None

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.header("Paramètres")

zone_mode = st.sidebar.radio(
    "Mode",
    ["Dessiner", "Coordonnées"]
)

cloud_threshold = st.sidebar.slider("Nuages (%)", 0, 80, 20)

year = st.sidebar.selectbox("Année", [2023, 2024, 2025], index=2)

month = st.sidebar.selectbox(
    "Mois",
    list(range(1, 13)),
    format_func=lambda x: f"Mois {x}"
)

parcel_text = ""
if zone_mode == "Coordonnées":
    parcel_text = st.sidebar.text_area("Coordonnées")

analyze_clicked = st.sidebar.button("🚀 Analyser")

# =========================================================
# CARTE
# =========================================================
st.subheader("📍 Dessine ta parcelle")

m = folium.Map(location=[31.8, -7.1], zoom_start=6)

Draw(
    draw_options={"polygon": True, "rectangle": False},
    edit_options={"edit": True}
).add_to(m)

Fullscreen().add_to(m)

map_data = st_folium(m, height=500)

# ✅ FIX sécurisation
if map_data is not None and "all_drawings" in map_data:
    drawings = map_data["all_drawings"]
    if drawings:
        st.session_state["parcel_geojson"] = drawings[-1]

# =========================================================
# PARCELLE
# =========================================================
parcel_region = None

try:
    if zone_mode == "Dessiner":
        if st.session_state["parcel_geojson"]:
            parcel_region = build_parcel_from_geojson(
                st.session_state["parcel_geojson"]
            )
    else:
        if parcel_text.strip():
            parcel_region = build_parcel_from_text(parcel_text)

except Exception as e:
    st.error(f"Erreur parcelle : {e}")

if parcel_region is None:
    st.warning("Définis une parcelle")
else:
    st.success("Parcelle OK")

# =========================================================
# DATES
# =========================================================
if parcel_region:
    try:
        dates = get_available_dates_for_month(
            parcel_region,
            year,
            month,
            cloud_threshold
        )
    except Exception as e:
        st.error(e)
        dates = []

    if dates:
        selected_date = st.selectbox("Date", dates)
    else:
        st.warning("Aucune image disponible")
        selected_date = None
else:
    selected_date = None

# =========================================================
# ANALYSE
# =========================================================
if analyze_clicked and parcel_region and selected_date:

    with st.spinner("Analyse en cours..."):

        try:
            image = get_image_for_date(
                parcel_region,
                selected_date,
                cloud_threshold
            )

            ndvi = get_ndvi(image)
            ndmi = get_ndmi(image)

            vigor = classify_ndvi_vigor(ndvi)
            hydric = classify_ndmi_hydric(ndmi)
            priority = build_priority_map(vigor, hydric)

            ndvi_stats = get_image_stats(ndvi, "NDVI", parcel_region)
            ndmi_stats = get_image_stats(ndmi, "NDMI", parcel_region)

            priority_surface = get_class_surface_stats(
                priority,
                {3: "priority"},
                parcel_region
            )

            st.success("Analyse terminée")

        except Exception as e:
            st.error(e)
            st.stop()

    # =====================================================
    # RESULTATS
    # =====================================================
    col1, col2, col3 = st.columns(3)

    col1.metric("NDVI moyen", round(ndvi_stats["mean"], 3))
    col2.metric("NDMI moyen", round(ndmi_stats["mean"], 3))
    col3.metric("Zone prioritaire (ha)", round(priority_surface["priority"], 2))

    # =====================================================
    # CARTE RESULTAT
    # =====================================================
    st.subheader("🗺️ Carte")

    gm = geemap.Map()
    gm.centerObject(parcel_region, 14)

    gm.addLayer(ndvi, get_ndvi_vis_params(), "NDVI")
    gm.addLayer(priority, get_priority_vis_params(), "Priorité")

    gm.to_streamlit(height=600)

    # =====================================================
    # GRAPHIQUE
    # =====================================================
    df = pd.DataFrame({
        "Indice": ["NDVI", "NDMI"],
        "Valeur": [ndvi_stats["mean"], ndmi_stats["mean"]]
    })

    st.plotly_chart(px.bar(df, x="Indice", y="Valeur"))
