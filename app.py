import pandas as pd
import plotly.express as px
import streamlit as st
import geemap.foliumap as geemap
import folium
from folium.plugins import Draw, Fullscreen
from streamlit_folium import st_folium

from processing import (
    init_ee,
    get_region,
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
# CONFIGURATION PAGE
# =========================================================
st.set_page_config(
    page_title="Suivi agricole de parcelle",
    page_icon="🌿",
    layout="wide",
)

# =========================================================
# STYLE CSS
# =========================================================
st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(to bottom, #f4f8f2, #edf6ee);
        }

        .main-title {
            font-size: 2.2rem;
            font-weight: 800;
            color: #1f5c3f;
            margin-bottom: 0.2rem;
        }

        .sub-title {
            font-size: 1rem;
            color: #4b6355;
            margin-bottom: 0.7rem;
        }

        .zone-box {
            background: #f8fcf8;
            border-left: 6px solid #4f8a5b;
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 1rem;
            color: #35523f;
            font-size: 0.96rem;
        }

        .section-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #234b34;
            margin-top: 1rem;
            margin-bottom: 0.6rem;
        }

        .custom-card {
            background-color: white;
            padding: 18px 20px;
            border-radius: 16px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
            border: 1px solid #e3eee4;
            margin-bottom: 12px;
        }

        section[data-testid="stSidebar"] {
            background: #eef5ef;
        }

        .sidebar-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #214c34;
            margin-bottom: 0.7rem;
        }

        .highlight-box {
            background: #f8fcf8;
            border-left: 6px solid #4f8a5b;
            padding: 14px 16px;
            border-radius: 12px;
            margin-bottom: 12px;
            color: #35523f;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# TITRE
# =========================================================
st.markdown('<div class="main-title">🌿 Application de suivi agricole de parcelle</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Dessiner une parcelle, choisir un mois, sélectionner une date disponible, puis analyser la vigueur végétale, l’état hydrique et les zones prioritaires.</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="zone-box">
    <b>Objectif :</b> aider l’agriculteur à localiser sa parcelle sur une carte,
    dessiner ou saisir sa zone d’intérêt, puis analyser l’image Sentinel-2 disponible
    sur la date réellement accessible.
    </div>
    """,
    unsafe_allow_html=True
)

# =========================================================
# INITIALISATION GEE
# =========================================================
try:
    ee_ok = init_ee()
    if not ee_ok:
        st.stop()
except Exception as e:
    st.error("Erreur lors de l'initialisation de Google Earth Engine.")
    st.exception(e)
    st.stop()

# =========================================================
# ÉTAT DE SESSION
# =========================================================
if "parcel_geojson" not in st.session_state:
    st.session_state["parcel_geojson"] = None

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown('<div class="sidebar-title">Paramètres de l’analyse</div>', unsafe_allow_html=True)

zone_mode = st.sidebar.radio(
    "Mode de sélection de la parcelle",
    ["Dessiner sur la carte", "Saisir les coordonnées"]
)

cloud_threshold = st.sidebar.slider("Seuil maximal de nuages (%)", 0, 80, 20)

year_selected = st.sidebar.selectbox("Année", [2022, 2023, 2024, 2025, 2026], index=4)
month_dict = {
    "Janvier": 1,
    "Février": 2,
    "Mars": 3,
    "Avril": 4,
    "Mai": 5,
    "Juin": 6,
    "Juillet": 7,
    "Août": 8,
    "Septembre": 9,
    "Octobre": 10,
    "Novembre": 11,
    "Décembre": 12
}
month_label = st.sidebar.selectbox("Mois", list(month_dict.keys()), index=2)
month_selected = month_dict[month_label]

parcel_text = ""
if zone_mode == "Saisir les coordonnées":
    parcel_text = st.sidebar.text_area(
        "Coordonnées de la parcelle (latitude,longitude sur chaque ligne)",
        height=180,
        placeholder="32.5021,-6.4132\n32.5028,-6.4011\n32.4950,-6.3998\n32.4942,-6.4110"
    )
    st.sidebar.caption("Format attendu : une ligne par point, sous la forme latitude,longitude")

analyze_clicked = st.sidebar.button("🚀 Analyser la parcelle", use_container_width=True)

# =========================================================
# PARTIE 1 : CARTE DE LOCALISATION / DESSIN
# =========================================================
st.markdown('<div class="section-title">1. Localisation de la parcelle</div>', unsafe_allow_html=True)

left_col, right_col = st.columns([2.2, 1])

with left_col:
    # Centre initial sur le Maroc
    m = folium.Map(location=[31.8, -7.1], zoom_start=6, tiles=None)

    # Fonds de carte
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)

    # Si une parcelle existe déjà, on la réaffiche
    if st.session_state["parcel_geojson"] is not None:
        folium.GeoJson(
            st.session_state["parcel_geojson"],
            name="Parcelle enregistrée",
            style_function=lambda x: {
                "color": "blue",
                "weight": 3,
                "fillOpacity": 0.1
            }
        ).add_to(m)

    # Outil de dessin : uniquement polygones
    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "rectangle": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "polygon": True
        },
        edit_options={
            "edit": True,
            "remove": True
        }
    ).add_to(m)

    Fullscreen().add_to(m)
    folium.LayerControl().add_to(m)

    map_data = st_folium(
        m,
        width=None,
        height=600,
        returned_objects=["all_drawings", "last_active_drawing"]
    )

with right_col:
    st.markdown(
        """
        <div class="custom-card">
        <b>Utilisation de la carte</b><br><br>
        • Choisis un fond OSM ou Satellite<br>
        • Zoome sur ta zone au Maroc<br>
        • Dessine un polygone sur ta parcelle<br>
        • Ou utilise la saisie des coordonnées dans la barre latérale
        </div>
        """,
        unsafe_allow_html=True
    )

    if zone_mode == "Dessiner sur la carte":
        if map_data and map_data.get("all_drawings"):
            last_polygon = None
            for feature in map_data["all_drawings"]:
                geom = feature.get("geometry", {})
                if geom.get("type") == "Polygon":
                    last_polygon = feature

            if last_polygon is not None:
                st.session_state["parcel_geojson"] = last_polygon
                st.success("Parcelle dessinée détectée.")
            else:
                st.info("Dessine un polygone pour définir la parcelle.")
        else:
            st.info("Dessine un polygone sur la carte.")

# =========================================================
# CONSTRUCTION DE LA PARCELLE
# =========================================================
parcel_region = None

try:
    if zone_mode == "Dessiner sur la carte":
        if st.session_state["parcel_geojson"] is not None:
            parcel_region = build_parcel_from_geojson(st.session_state["parcel_geojson"])
    else:
        if parcel_text.strip():
            parcel_region = build_parcel_from_text(parcel_text)
except Exception as e:
    st.warning(f"Problème dans la définition de la parcelle : {e}")

# =========================================================
# ARRÊT SI PARCELLE NON DISPONIBLE
# =========================================================
if parcel_region is None:
    st.warning("Veuillez dessiner votre parcelle sur la carte ou saisir ses coordonnées.")
    st.stop()

# =========================================================
# PARTIE 2 : DATES DISPONIBLES
# =========================================================
st.markdown('<div class="section-title">2. Dates d’images disponibles</div>', unsafe_allow_html=True)

try:
    available_dates = get_available_dates_for_month(
        region=parcel_region,
        year=year_selected,
        month=month_selected,
        cloud_threshold=cloud_threshold
    )
except Exception as e:
    st.error("Erreur lors de la récupération des dates disponibles.")
    st.exception(e)
    st.stop()

if not available_dates:
    st.warning("Aucune image disponible pour cette parcelle sur le mois choisi.")
    st.stop()

st.markdown(
    f"""
    <div class="highlight-box">
    <b>Mois choisi :</b> {month_label} {year_selected}<br>
    <b>Nombre de dates disponibles :</b> {len(available_dates)}<br>
    Pour rester en Python/Streamlit, l’application propose directement les dates réellement disponibles au lieu d’un calendrier coloré.
    </div>
    """,
    unsafe_allow_html=True
)

formatted_dates = {
    d: pd.to_datetime(d).strftime("%d/%m/%Y") for d in available_dates
}

selected_date = st.selectbox(
    "Choisis une date disponible",
    available_dates,
    format_func=lambda x: formatted_dates[x]
)

# =========================================================
# ANALYSE
# =========================================================
if not analyze_clicked:
    st.stop()

try:
    # -----------------------------------------------------
    # 1. Chargement de l'image
    # -----------------------------------------------------
    image = get_image_for_date(
        region=parcel_region,
        selected_date=selected_date,
        cloud_threshold=cloud_threshold
    )

    # -----------------------------------------------------
    # 2. Calcul des indices
    # -----------------------------------------------------
    ndvi_image = get_ndvi(image)
    ndmi_image = get_ndmi(image)

    # -----------------------------------------------------
    # 3. Classes
    # -----------------------------------------------------
    vigor_class = classify_ndvi_vigor(ndvi_image)
    hydric_class = classify_ndmi_hydric(ndmi_image)
    priority_map = build_priority_map(vigor_class, hydric_class)

    # -----------------------------------------------------
    # 4. Statistiques
    # -----------------------------------------------------
    ndvi_stats = get_image_stats(ndvi_image, band_name="NDVI", region=parcel_region)
    ndmi_stats = get_image_stats(ndmi_image, band_name="NDMI", region=parcel_region)

    vigor_surfaces = get_class_surface_stats(
        vigor_class,
        {
            1: "vegetation_faible_ha",
            2: "vegetation_moyenne_ha",
            3: "vegetation_forte_ha"
        },
        region=parcel_region
    )

    hydric_surfaces = get_class_surface_stats(
        hydric_class,
        {
            1: "hydrique_faible_ha",
            2: "hydrique_moyen_ha",
            3: "hydrique_bon_ha"
        },
        region=parcel_region
    )

    priority_surfaces = get_class_surface_stats(
        priority_map,
        {
            1: "zone_normale_ha",
            2: "zone_vigilance_ha",
            3: "zone_prioritaire_ha"
        },
        region=parcel_region
    )

    st.success("Analyse réalisée avec succès.")

    # =====================================================
    # RÉSUMÉ RAPIDE
    # =====================================================
    st.markdown('<div class="section-title">3. Résumé rapide</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Date image utilisée", pd.to_datetime(selected_date).strftime("%d/%m/%Y"))

    with c2:
        st.metric("NDVI moyen", f"{ndvi_stats['mean']:.3f}" if ndvi_stats["mean"] is not None else "NA")

    with c3:
        st.metric("NDMI moyen", f"{ndmi_stats['mean']:.3f}" if ndmi_stats["mean"] is not None else "NA")

    with c4:
        st.metric("Zone prioritaire (ha)", f"{priority_surfaces['zone_prioritaire_ha']:.2f}")

    # =====================================================
    # ONGLETS
    # =====================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "🗺️ Cartes",
        "📊 Statistiques",
        "📈 Graphiques",
        "🧠 Diagnostic"
    ])

    # =====================================================
    # ONGLET 1 - CARTES
    # =====================================================
    with tab1:
        st.markdown('<div class="section-title">Cartes principales</div>', unsafe_allow_html=True)

        gm = geemap.Map()
        gm.centerObject(parcel_region, 15)

        gm.addLayer(
            parcel_region.style(**{"color": "blue", "fillColor": "00000000", "width": 2}),
            {},
            "Parcelle"
        )

        gm.addLayer(ndvi_image, get_ndvi_vis_params(), "NDVI")
        gm.addLayer(ndmi_image, get_ndmi_vis_params(), "NDMI")
        gm.addLayer(vigor_class, get_vigor_vis_params(), "Classes de vigueur")
        gm.addLayer(hydric_class, get_hydric_vis_params(), "Classes hydriques")
        gm.addLayer(priority_map, get_priority_vis_params(), "Carte de priorité")

        gm.add_colorbar(
            vis_params=get_ndvi_vis_params(),
            label="NDVI",
            layer_name="NDVI",
            position="bottomleft"
        )

        gm.add_colorbar(
            vis_params=get_ndmi_vis_params(),
            label="NDMI",
            layer_name="NDMI",
            position="bottomright"
        )

        gm.addLayerControl()
        gm.to_streamlit(height=700)

    # =====================================================
    # ONGLET 2 - STATISTIQUES
    # =====================================================
    with tab2:
        st.markdown('<div class="section-title">Statistiques globales</div>', unsafe_allow_html=True)

        df_stats = pd.DataFrame([
            {
                "Indicateur": "NDVI",
                "Moyenne": ndvi_stats["mean"],
                "P25": ndvi_stats["p25"],
                "P75": ndvi_stats["p75"],
                "Écart-type": ndvi_stats["stdDev"],
                "Min": ndvi_stats["min"],
                "Max": ndvi_stats["max"],
            },
            {
                "Indicateur": "NDMI",
                "Moyenne": ndmi_stats["mean"],
                "P25": ndmi_stats["p25"],
                "P75": ndmi_stats["p75"],
                "Écart-type": ndmi_stats["stdDev"],
                "Min": ndmi_stats["min"],
                "Max": ndmi_stats["max"],
            },
        ])

        st.dataframe(df_stats.round(3), use_container_width=True)

        st.markdown('<div class="section-title">Surfaces par classe (ha)</div>', unsafe_allow_html=True)

        df_surfaces = pd.DataFrame([
            {"Type": "Végétation faible", "Surface (ha)": vigor_surfaces["vegetation_faible_ha"]},
            {"Type": "Végétation moyenne", "Surface (ha)": vigor_surfaces["vegetation_moyenne_ha"]},
            {"Type": "Végétation forte", "Surface (ha)": vigor_surfaces["vegetation_forte_ha"]},
            {"Type": "Hydrique faible", "Surface (ha)": hydric_surfaces["hydrique_faible_ha"]},
            {"Type": "Hydrique moyen", "Surface (ha)": hydric_surfaces["hydrique_moyen_ha"]},
            {"Type": "Hydrique bon", "Surface (ha)": hydric_surfaces["hydrique_bon_ha"]},
            {"Type": "Zone normale", "Surface (ha)": priority_surfaces["zone_normale_ha"]},
            {"Type": "Zone vigilance", "Surface (ha)": priority_surfaces["zone_vigilance_ha"]},
            {"Type": "Zone prioritaire", "Surface (ha)": priority_surfaces["zone_prioritaire_ha"]},
        ])

        st.dataframe(df_surfaces.round(2), use_container_width=True)

    # =====================================================
    # ONGLET 3 - GRAPHIQUES
    # =====================================================
    with tab3:
        df_vigor = pd.DataFrame({
            "Classe": ["Faible", "Moyenne", "Forte"],
            "Surface (ha)": [
                vigor_surfaces["vegetation_faible_ha"],
                vigor_surfaces["vegetation_moyenne_ha"],
                vigor_surfaces["vegetation_forte_ha"]
            ]
        })
        st.plotly_chart(
            px.bar(df_vigor, x="Classe", y="Surface (ha)", title="Répartition des classes de vigueur végétale"),
            use_container_width=True
        )

        df_hydric = pd.DataFrame({
            "Classe": ["Faible", "Moyen", "Bon"],
            "Surface (ha)": [
                hydric_surfaces["hydrique_faible_ha"],
                hydric_surfaces["hydrique_moyen_ha"],
                hydric_surfaces["hydrique_bon_ha"]
            ]
        })
        st.plotly_chart(
            px.bar(df_hydric, x="Classe", y="Surface (ha)", title="Répartition des classes hydriques"),
            use_container_width=True
        )

        df_priority = pd.DataFrame({
            "Classe": ["Normale", "Vigilance", "Prioritaire"],
            "Surface (ha)": [
                priority_surfaces["zone_normale_ha"],
                priority_surfaces["zone_vigilance_ha"],
                priority_surfaces["zone_prioritaire_ha"]
            ]
        })
        st.plotly_chart(
            px.bar(df_priority, x="Classe", y="Surface (ha)", title="Répartition des zones prioritaires"),
            use_container_width=True
        )

    # =====================================================
    # ONGLET 4 - DIAGNOSTIC
    # =====================================================
    with tab4:
        priority_area = priority_surfaces["zone_prioritaire_ha"]

        if priority_area > 0:
            diagnostic_text = (
                f"La parcelle présente {priority_area:.2f} ha classés comme zones prioritaires. "
                f"Ces secteurs combinent une faible vigueur végétale et un état hydrique défavorable. "
                f"Une vérification terrain est recommandée, notamment pour contrôler l’irrigation."
            )
        elif ndvi_stats["mean"] is not None and ndvi_stats["mean"] < 0.35:
            diagnostic_text = (
                "La vigueur végétale moyenne de la parcelle reste relativement faible. "
                "Une surveillance est recommandée pour identifier les secteurs les moins performants."
            )
        else:
            diagnostic_text = (
                "La parcelle présente globalement un état satisfaisant. "
                "Aucune zone critique majeure n’a été détectée avec les seuils retenus."
            )

        st.markdown(
            f"""
            <div class="highlight-box">
            {diagnostic_text}
            </div>
            """,
            unsafe_allow_html=True
        )

except Exception as e:
    st.error("Erreur lors de l’analyse de la parcelle.")
    st.exception(e)
