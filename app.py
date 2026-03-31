import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import geemap.foliumap as geemap

from processing import (
    init_ee,
    get_region,
    build_parcel_from_text,
    get_monthly_ndvi,
    get_monthly_ndmi,
    classify_ndvi_vigor,
    classify_ndmi_hydric,
    build_priority_map,
    get_image_stats,
    get_month_image_count,
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
    page_title="Application agricole - Parcelle",
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
st.markdown('<div class="main-title">🌿 Application de diagnostic agricole de parcelle</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Analyse de la vigueur végétale, de l’état hydrique et des zones prioritaires sur une parcelle agricole.</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="zone-box">
    <b>Objectif :</b> aider l’agriculteur à analyser sa parcelle à distance,
    repérer les zones à faible végétation, examiner un stress hydrique potentiel
    et identifier les secteurs prioritaires à surveiller.
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
# MOIS DISPONIBLES
# =========================================================
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

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown('<div class="sidebar-title">Paramètres de l’analyse</div>', unsafe_allow_html=True)

zone_mode = st.sidebar.radio(
    "Choix de la zone",
    ["Utiliser la région par défaut", "Définir ma parcelle par coordonnées"]
)

year_selected = st.sidebar.selectbox("Année", [2022, 2023, 2024, 2025], index=3)
month_label = st.sidebar.selectbox("Mois", list(month_dict.keys()), index=3)
cloud_threshold = st.sidebar.slider("Seuil maximal de nuages (%)", 0, 50, 15)

parcel_text = ""
if zone_mode == "Définir ma parcelle par coordonnées":
    parcel_text = st.sidebar.text_area(
        "Coordonnées du polygone (latitude,longitude sur chaque ligne)",
        height=180,
        placeholder="32.5021,-6.4132\n32.5028,-6.4011\n32.4950,-6.3998\n32.4942,-6.4110"
    )
    st.sidebar.caption("Format attendu : une ligne par point, sous la forme latitude,longitude")

run = st.sidebar.button("🚀 Analyser la parcelle", use_container_width=True)

# =========================================================
# ÉTAT INITIAL
# =========================================================
if not run:
    st.markdown(
        """
        <div class="highlight-box">
        Cette application permet à l’utilisateur :
        <br>• de choisir une parcelle,
        <br>• de visualiser la vigueur végétale,
        <br>• d’examiner l’état hydrique,
        <br>• et d’identifier les zones prioritaires d’intervention.
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
                <b>1. Définir la zone</b><br>
                Utilise la région par défaut ou saisis les coordonnées de ta parcelle.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            """
            <div class="custom-card">
                <b>2. Choisir la période</b><br>
                Sélectionne l’année, le mois et le seuil de nuages.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            """
            <div class="custom-card">
                <b>3. Lire le diagnostic</b><br>
                Consulte la vigueur végétale, l’état hydrique et les zones prioritaires.
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

    month_selected = month_dict[month_label]

    # -----------------------------------------------------
    # 2. Calcul des indices
    # -----------------------------------------------------
    ndvi_image = get_monthly_ndvi(year_selected, month_selected, cloud_threshold, region)
    ndmi_image = get_monthly_ndmi(year_selected, month_selected, cloud_threshold, region)

    # -----------------------------------------------------
    # 3. Classification thématique
    # -----------------------------------------------------
    vigor_class = classify_ndvi_vigor(ndvi_image)
    hydric_class = classify_ndmi_hydric(ndmi_image)
    priority_map = build_priority_map(vigor_class, hydric_class)

    # -----------------------------------------------------
    # 4. Statistiques descriptives
    # -----------------------------------------------------
    ndvi_stats = get_image_stats(ndvi_image, band_name="NDVI", region=region)
    ndmi_stats = get_image_stats(ndmi_image, band_name="NDMI", region=region)

    image_count = get_month_image_count(year_selected, month_selected, cloud_threshold, region)

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

    st.success("Analyse de la parcelle réalisée avec succès.")

    # =====================================================
    # RÉSUMÉ
    # =====================================================
    st.markdown('<div class="section-title">Résumé du diagnostic</div>', unsafe_allow_html=True)

    r1, r2, r3, r4 = st.columns(4)

    with r1:
        st.metric("NDVI moyen", f"{ndvi_stats['mean']:.3f}" if ndvi_stats["mean"] is not None else "NA")

    with r2:
        st.metric("NDMI moyen", f"{ndmi_stats['mean']:.3f}" if ndmi_stats["mean"] is not None else "NA")

    with r3:
        st.metric("Images utilisées", image_count)

    with r4:
        st.metric("Zone prioritaire (ha)", f"{priority_surfaces['zone_prioritaire_ha']:.2f}")

    # =====================================================
    # ONGLETS
    # =====================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Statistiques",
        "📈 Graphiques",
        "🗺️ Cartes",
        "🧠 Diagnostic",
        "⬇️ Export"
    ])

    # =====================================================
    # ONGLET 1 - STATISTIQUES
    # =====================================================
    with tab1:
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

        st.markdown('<div class="section-title">Surfaces par classe (hectares)</div>', unsafe_allow_html=True)

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
    # ONGLET 2 - GRAPHIQUES
    # =====================================================
    with tab2:
        st.markdown('<div class="section-title">Graphique des surfaces de végétation</div>', unsafe_allow_html=True)

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

        st.markdown('<div class="section-title">Graphique des surfaces hydriques</div>', unsafe_allow_html=True)

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

        st.markdown('<div class="section-title">Graphique des priorités</div>', unsafe_allow_html=True)

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
    # ONGLET 3 - CARTES
    # =====================================================
    with tab3:
        st.markdown('<div class="section-title">Cartes de diagnostic</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="highlight-box">
            <b>Lecture des cartes :</b><br>
            - NDVI : mesure la vigueur végétale<br>
            - NDMI : renseigne sur l’état hydrique de la végétation<br>
            - Carte de priorité : vert = normal, jaune = vigilance, rouge = intervention prioritaire
            </div>
            """,
            unsafe_allow_html=True
        )

        m = geemap.Map()
        m.centerObject(region, 14)

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
                    f"Une vérification terrain est recommandée, notamment pour contrôler l’irrigation, l’homogénéité "
                    f"de la parcelle et d’éventuels facteurs limitants."
                )
            elif ndvi_mean < 0.35:
                diagnostic_text = (
                    "La vigueur végétale moyenne de la parcelle reste relativement faible. "
                    "Même en l’absence de zone critique marquée, une surveillance est recommandée afin "
                    "d’identifier d’éventuelles zones de développement insuffisant."
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
            "L’application ne remplace pas l’observation de terrain. "
            "Elle sert à repérer rapidement les zones où la végétation est plus faible que le reste de la parcelle "
            "et à vérifier si un état hydrique défavorable peut constituer une piste d’explication."
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
            {"Indicateur": "NDVI moyen", "Valeur": ndvi_stats["mean"]},
            {"Indicateur": "NDMI moyen", "Valeur": ndmi_stats["mean"]},
            {"Indicateur": "Images utilisées", "Valeur": image_count},
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
