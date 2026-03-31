import pandas as pd
import plotly.express as px
import streamlit as st
import geemap.foliumap as geemap
from datetime import date, timedelta

from processing import (
    init_ee,
    get_region,
    build_parcel_from_text,
    get_available_dates,
    find_closest_date,
    get_image_for_exact_date,
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
    '<div class="sub-title">Analyse de la vigueur végétale, de l’état hydrique et des zones prioritaires sur une parcelle agricole à partir de l’image disponible la plus proche.</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="zone-box">
    <b>Objectif :</b> aider l’agriculteur à suivre sa parcelle à distance, à partir de l’image Sentinel-2 disponible la plus proche de la date souhaitée, afin d’évaluer l’état de la végétation, l’état hydrique et les zones à surveiller.
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
# SIDEBAR
# =========================================================
st.sidebar.markdown('<div class="sidebar-title">Paramètres de l’analyse</div>', unsafe_allow_html=True)

zone_mode = st.sidebar.radio(
    "Choix de la zone",
    ["Utiliser la région par défaut", "Définir ma parcelle par coordonnées"]
)

parcel_text = ""
if zone_mode == "Définir ma parcelle par coordonnées":
    parcel_text = st.sidebar.text_area(
        "Coordonnées de la parcelle (latitude,longitude sur chaque ligne)",
        height=180,
        placeholder="32.5021,-6.4132\n32.5028,-6.4011\n32.4950,-6.3998\n32.4942,-6.4110"
    )
    st.sidebar.caption("Format : une ligne par point, sous la forme latitude,longitude")

cloud_threshold = st.sidebar.slider("Seuil maximal de nuages (%)", 0, 80, 20)

# Date demandée par l'utilisateur
desired_date = st.sidebar.date_input(
    "Date souhaitée",
    value=date.today() - timedelta(days=10)
)

# Fenêtre de recherche des dates disponibles
days_back = st.sidebar.slider(
    "Nombre de jours récents à explorer",
    min_value=15,
    max_value=180,
    value=90,
    step=5
)

run = st.sidebar.button("🚀 Analyser la parcelle", use_container_width=True)

# =========================================================
# ÉTAT INITIAL
# =========================================================
if not run:
    st.markdown(
        """
        <div class="highlight-box">
        Cette application permet à l’utilisateur :
        <br>• de choisir sa parcelle,
        <br>• de demander une date d’analyse,
        <br>• d’utiliser automatiquement l’image disponible la plus proche,
        <br>• puis d’obtenir un diagnostic agricole simplifié.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="section-title">Mode d’utilisation</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            <div class="custom-card">
                <b>1. Définir la parcelle</b><br>
                Utilise la région par défaut ou saisis les coordonnées de ta parcelle.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            """
            <div class="custom-card">
                <b>2. Choisir une date</b><br>
                L’application recherche automatiquement l’image disponible la plus proche.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            """
            <div class="custom-card">
                <b>3. Lire le diagnostic</b><br>
                Consulte les cartes, les statistiques et les zones prioritaires d’intervention.
            </div>
            """,
            unsafe_allow_html=True
        )

    st.stop()

# =========================================================
# CONTRÔLE DE SAISIE
# =========================================================
if zone_mode == "Définir ma parcelle par coordonnées" and not parcel_text.strip():
    st.warning("Veuillez saisir les coordonnées de la parcelle.")
    st.stop()

# =========================================================
# TRAITEMENT
# =========================================================
try:
    # -----------------------------------------------------
    # 1. Définition de la zone d’analyse
    # -----------------------------------------------------
    if zone_mode == "Utiliser la région par défaut":
        region = get_region()
        zone_label = "Région par défaut"
    else:
        region = build_parcel_from_text(parcel_text)
        zone_label = "Parcelle utilisateur"

    # -----------------------------------------------------
    # 2. Recherche des dates disponibles sur les derniers jours
    # -----------------------------------------------------
    desired_date_str = desired_date.strftime("%Y-%m-%d")
    start_search_date = (desired_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end_search_date = date.today().strftime("%Y-%m-%d")

    available_dates = get_available_dates(
        region=region,
        start_date=start_search_date,
        end_date=end_search_date,
        cloud_threshold=cloud_threshold
    )

    if not available_dates:
        st.warning("Aucune image disponible pour cette parcelle sur la période récente choisie.")
        st.stop()

    closest_date = find_closest_date(desired_date_str, available_dates)

    if closest_date is None:
        st.warning("Impossible de trouver une date proche.")
        st.stop()

    # -----------------------------------------------------
    # 3. Chargement de l'image du jour retenu
    # -----------------------------------------------------
    image = get_image_for_exact_date(
        region=region,
        selected_date=closest_date,
        cloud_threshold=cloud_threshold
    )

    if image is None:
        st.warning("Impossible de charger l’image retenue.")
        st.stop()

    # -----------------------------------------------------
    # 4. Calcul des indices
    # -----------------------------------------------------
    ndvi_image = get_ndvi(image)
    ndmi_image = get_ndmi(image)

    # -----------------------------------------------------
    # 5. Classification
    # -----------------------------------------------------
    vigor_class = classify_ndvi_vigor(ndvi_image)
    hydric_class = classify_ndmi_hydric(ndmi_image)
    priority_map = build_priority_map(vigor_class, hydric_class)

    # -----------------------------------------------------
    # 6. Statistiques
    # -----------------------------------------------------
    ndvi_stats = get_image_stats(ndvi_image, band_name="NDVI", region=region)
    ndmi_stats = get_image_stats(ndmi_image, band_name="NDMI", region=region)

    vigor_surfaces = get_class_surface_stats(
        vigor_class,
        {
            1: "vegetation_faible_ha",
            2: "vegetation_moyenne_ha",
            3: "vegetation_forte_ha"
        },
        region=region
    )

    hydric_surfaces = get_class_surface_stats(
        hydric_class,
        {
            1: "hydrique_faible_ha",
            2: "hydrique_moyen_ha",
            3: "hydrique_bon_ha"
        },
        region=region
    )

    priority_surfaces = get_class_surface_stats(
        priority_map,
        {
            1: "zone_normale_ha",
            2: "zone_vigilance_ha",
            3: "zone_prioritaire_ha"
        },
        region=region
    )

    st.success("Analyse réalisée avec succès.")

    # =====================================================
    # RÉSUMÉ RAPIDE
    # =====================================================
    st.markdown('<div class="section-title">Résumé rapide</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Date demandée", desired_date.strftime("%d/%m/%Y"))

    with c2:
        st.metric("Image utilisée", datetime.strptime(closest_date, "%Y-%m-%d").strftime("%d/%m/%Y"))

    with c3:
        st.metric("NDVI moyen", f"{ndvi_stats['mean']:.3f}" if ndvi_stats["mean"] is not None else "NA")

    with c4:
        st.metric("Zone prioritaire (ha)", f"{priority_surfaces['zone_prioritaire_ha']:.2f}")

    # =====================================================
    # DATES DISPONIBLES
    # =====================================================
    st.markdown('<div class="section-title">Dates disponibles récentes</div>', unsafe_allow_html=True)

    df_dates = pd.DataFrame({"Dates disponibles": available_dates})
    df_dates["Date formatée"] = pd.to_datetime(df_dates["Dates disponibles"]).dt.strftime("%d/%m/%Y")
    df_dates["Utilisée"] = df_dates["Dates disponibles"].apply(lambda x: "Oui" if x == closest_date else "")

    st.dataframe(
        df_dates[["Date formatée", "Utilisée"]],
        use_container_width=True
    )

    # =====================================================
    # ONGLETS
    # =====================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🗺️ Cartes",
        "📊 Statistiques",
        "📈 Graphiques",
        "🧠 Diagnostic",
        "⬇️ Export"
    ])

    # =====================================================
    # ONGLET 1 - CARTES
    # =====================================================
    with tab1:
        st.markdown('<div class="section-title">Cartes principales</div>', unsafe_allow_html=True)

        st.markdown(
            """
            <div class="highlight-box">
            <b>Lecture des cartes :</b><br>
            - NDVI : vigueur végétale<br>
            - NDMI : état hydrique de la végétation<br>
            - Carte de priorité : vert = normal, jaune = vigilance, rouge = prioritaire
            </div>
            """,
            unsafe_allow_html=True
        )

        m = geemap.Map()
        m.centerObject(region, 14)

        # Fond de carte de base
        try:
            m.add_basemap("SATELLITE")
        except Exception:
            pass

        m.addLayer(
            region.style(**{"color": "blue", "fillColor": "00000000", "width": 2}),
            {},
            zone_label
        )

        m.addLayer(ndvi_image, get_ndvi_vis_params(), "NDVI")
        m.addLayer(ndmi_image, get_ndmi_vis_params(), "NDMI")
        m.addLayer(vigor_class, get_vigor_vis_params(), "Classes de vigueur")
        m.addLayer(hydric_class, get_hydric_vis_params(), "Classes hydriques")
        m.addLayer(priority_map, get_priority_vis_params(), "Carte de priorité")

        m.add_colorbar(
            vis_params=get_ndvi_vis_params(),
            label="NDVI",
            layer_name="NDVI",
            position="bottomleft"
        )

        m.add_colorbar(
            vis_params=get_ndmi_vis_params(),
            label="NDMI",
            layer_name="NDMI",
            position="bottomright"
        )

        m.addLayerControl()
        m.to_streamlit(height=700)

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
        st.markdown('<div class="section-title">Graphiques de synthèse</div>', unsafe_allow_html=True)

        df_vigor_graph = pd.DataFrame({
            "Classe": ["Faible", "Moyenne", "Forte"],
            "Surface (ha)": [
                vigor_surfaces["vegetation_faible_ha"],
                vigor_surfaces["vegetation_moyenne_ha"],
                vigor_surfaces["vegetation_forte_ha"]
            ]
        })

        fig_vigor = px.bar(
            df_vigor_graph,
            x="Classe",
            y="Surface (ha)",
            title="Répartition des classes de vigueur végétale"
        )
        st.plotly_chart(fig_vigor, use_container_width=True)

        df_hydric_graph = pd.DataFrame({
            "Classe": ["Faible", "Moyen", "Bon"],
            "Surface (ha)": [
                hydric_surfaces["hydrique_faible_ha"],
                hydric_surfaces["hydrique_moyen_ha"],
                hydric_surfaces["hydrique_bon_ha"]
            ]
        })

        fig_hydric = px.bar(
            df_hydric_graph,
            x="Classe",
            y="Surface (ha)",
            title="Répartition des classes hydriques"
        )
        st.plotly_chart(fig_hydric, use_container_width=True)

        df_priority_graph = pd.DataFrame({
            "Classe": ["Normale", "Vigilance", "Prioritaire"],
            "Surface (ha)": [
                priority_surfaces["zone_normale_ha"],
                priority_surfaces["zone_vigilance_ha"],
                priority_surfaces["zone_prioritaire_ha"]
            ]
        })

        fig_priority = px.bar(
            df_priority_graph,
            x="Classe",
            y="Surface (ha)",
            title="Répartition des zones prioritaires"
        )
        st.plotly_chart(fig_priority, use_container_width=True)

    # =====================================================
    # ONGLET 4 - DIAGNOSTIC
    # =====================================================
    with tab4:
        st.markdown('<div class="section-title">Diagnostic agronomique simplifié</div>', unsafe_allow_html=True)

        ndvi_mean = ndvi_stats["mean"]
        ndmi_mean = ndmi_stats["mean"]
        priority_area = priority_surfaces["zone_prioritaire_ha"]

        if ndvi_mean is not None and ndmi_mean is not None:
            if priority_area > 0:
                diagnostic_text = (
                    f"La parcelle présente {priority_area:.2f} ha classés comme zones prioritaires. "
                    f"Ces secteurs combinent une faible vigueur végétale et un état hydrique faible ou défavorable. "
                    f"Une vérification terrain est recommandée, notamment pour contrôler l’irrigation et l’homogénéité de la parcelle."
                )
            elif ndvi_mean < 0.35:
                diagnostic_text = (
                    "La vigueur végétale moyenne de la parcelle reste relativement faible. "
                    "Une surveillance est recommandée afin d’identifier les secteurs de développement insuffisant."
                )
            else:
                diagnostic_text = (
                    "La parcelle présente globalement un état végétatif satisfaisant. "
                    "Aucune zone critique majeure n’a été identifiée à partir des seuils retenus."
                )
        else:
            diagnostic_text = "Le diagnostic automatique n’a pas pu être généré."

        st.markdown(
            f"""
            <div class="highlight-box">
            {diagnostic_text}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown('<div class="section-title">Interprétation métier</div>', unsafe_allow_html=True)

        interpretation_text = (
            "L’application ne remplace pas la visite de terrain. "
            "Elle aide à repérer rapidement les zones où la végétation est plus faible que le reste de la parcelle "
            "et à examiner si un état hydrique défavorable peut constituer une piste d’explication."
        )

        st.markdown(
            f"""
            <div class="highlight-box">
            {interpretation_text}
            </div>
            """,
            unsafe_allow_html=True
        )

    # =====================================================
    # ONGLET 5 - EXPORT
    # =====================================================
    with tab5:
        st.markdown('<div class="section-title">Export des résultats</div>', unsafe_allow_html=True)

        df_export = pd.DataFrame([
            {"Indicateur": "Date demandée", "Valeur": desired_date.strftime("%Y-%m-%d")},
            {"Indicateur": "Date image utilisée", "Valeur": closest_date},
            {"Indicateur": "NDVI moyen", "Valeur": ndvi_stats["mean"]},
            {"Indicateur": "NDMI moyen", "Valeur": ndmi_stats["mean"]},
            {"Indicateur": "Végétation faible (ha)", "Valeur": vigor_surfaces["vegetation_faible_ha"]},
            {"Indicateur": "Végétation moyenne (ha)", "Valeur": vigor_surfaces["vegetation_moyenne_ha"]},
            {"Indicateur": "Végétation forte (ha)", "Valeur": vigor_surfaces["vegetation_forte_ha"]},
            {"Indicateur": "Hydrique faible (ha)", "Valeur": hydric_surfaces["hydrique_faible_ha"]},
            {"Indicateur": "Hydrique moyen (ha)", "Valeur": hydric_surfaces["hydrique_moyen_ha"]},
            {"Indicateur": "Hydrique bon (ha)", "Valeur": hydric_surfaces["hydrique_bon_ha"]},
            {"Indicateur": "Zone normale (ha)", "Valeur": priority_surfaces["zone_normale_ha"]},
            {"Indicateur": "Zone vigilance (ha)", "Valeur": priority_surfaces["zone_vigilance_ha"]},
            {"Indicateur": "Zone prioritaire (ha)", "Valeur": priority_surfaces["zone_prioritaire_ha"]},
        ])

        st.dataframe(df_export, use_container_width=True)

        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Télécharger les résultats en CSV",
            data=csv,
            file_name="diagnostic_parcelle_agricole.csv",
            mime="text/csv"
        )

except Exception as e:
    st.error("Erreur lors de l’analyse de la parcelle.")
    st.exception(e)
