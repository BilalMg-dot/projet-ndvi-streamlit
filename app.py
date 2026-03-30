import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import geemap.foliumap as geemap

from processing import (
    init_ee,
    get_region,
    get_period_ndvi,
    get_ndvi_difference,
    classify_ndvi_difference,
    get_image_stats,
    get_ndvi_vis_params,
    get_diff_vis_params,
    get_classified_change_vis_params,
    get_period_image_count,
    get_change_surface_stats,
)

# =========================================================
# CONFIGURATION PAGE
# =========================================================
st.set_page_config(
    page_title="Application NDVI",
    page_icon="🌿",
    layout="wide",
)

# =========================================================
# STYLE CSS PERSONNALISÉ
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
st.markdown('<div class="main-title">🌿 Application interactive d’analyse du NDVI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Comparaison de deux périodes pour analyser les changements de la végétation à partir des images Sentinel-2 et de Google Earth Engine.</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="zone-box">
    <b>Zone d’étude :</b> Région Béni Mellal-Khénifra (Maroc).<br>
    Les images Sentinel-2, les calculs du NDVI et les statistiques affichées dans cette application
    sont limités à cette emprise spatiale.
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
    "Mars": 3,
    "Avril": 4,
    "Mai": 5,
    "Juillet": 7,
    "Septembre": 9,
    "Novembre": 11
}

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown('<div class="sidebar-title">Paramètres de l’analyse</div>', unsafe_allow_html=True)

year_1 = st.sidebar.selectbox("Année - période 1", [2022, 2023, 2024, 2025], index=0)
months_1_labels = st.sidebar.multiselect(
    "Mois - période 1",
    options=list(month_dict.keys()),
    default=["Mars", "Avril", "Mai"]
)

year_2 = st.sidebar.selectbox("Année - période 2", [2022, 2023, 2024, 2025], index=2)
months_2_labels = st.sidebar.multiselect(
    "Mois - période 2",
    options=list(month_dict.keys()),
    default=["Mars", "Avril", "Mai"]
)

cloud_threshold = st.sidebar.slider("Seuil maximal de nuages (%)", 0, 50, 15)

st.sidebar.info("Conseil : compare les mêmes mois entre les deux années pour une analyse plus cohérente.")

run = st.sidebar.button("🚀 Comparer les deux périodes", use_container_width=True)

# =========================================================
# ÉTAT INITIAL
# =========================================================
if not run:
    st.markdown(
        """
        <div class="highlight-box">
        Cette application permet de comparer deux périodes temporelles sur la région de Béni Mellal-Khénifra
        afin de mettre en évidence les changements de la végétation à partir du NDVI.
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
                <b>1. Choisir les périodes</b><br>
                Sélectionne une année et un ou plusieurs mois pour chaque période.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            """
            <div class="custom-card">
                <b>2. Lancer l’analyse</b><br>
                Clique sur le bouton dans la barre latérale pour exécuter la comparaison.
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            """
            <div class="custom-card">
                <b>3. Lire les résultats</b><br>
                Consulte les statistiques, le graphique et les cartes comparatives.
            </div>
            """,
            unsafe_allow_html=True
        )

    st.stop()

# =========================================================
# TRAITEMENT
# =========================================================
if not months_1_labels or not months_2_labels:
    st.warning("Sélectionne au moins un mois pour chaque période.")
    st.stop()

try:
    region = get_region()

    months_1 = [month_dict[m] for m in months_1_labels]
    months_2 = [month_dict[m] for m in months_2_labels]

    ndvi_p1 = get_period_ndvi(year_1, months_1, cloud_threshold)
    ndvi_p2 = get_period_ndvi(year_2, months_2, cloud_threshold)
    diff_ndvi = get_ndvi_difference(ndvi_p1, ndvi_p2)
    classified_change = classify_ndvi_difference(diff_ndvi)

    stats_p1 = get_image_stats(ndvi_p1, band_name="NDVI")
    stats_p2 = get_image_stats(ndvi_p2, band_name="NDVI")
    stats_diff = get_image_stats(diff_ndvi, band_name="NDVI_diff")

    count_p1 = get_period_image_count(year_1, months_1, cloud_threshold)
    count_p2 = get_period_image_count(year_2, months_2, cloud_threshold)

    surface_stats = get_change_surface_stats(classified_change)

    st.success("Comparaison réalisée avec succès.")

    # =====================================================
    # RÉSUMÉ
    # =====================================================
    st.markdown('<div class="section-title">Résumé de l’analyse</div>', unsafe_allow_html=True)

    r1, r2, r3 = st.columns(3)

    with r1:
        st.metric("NDVI moyen période 1", f"{stats_p1['mean']:.3f}" if stats_p1["mean"] is not None else "NA")

    with r2:
        st.metric("NDVI moyen période 2", f"{stats_p2['mean']:.3f}" if stats_p2["mean"] is not None else "NA")

    with r3:
        st.metric("Différence moyenne", f"{stats_diff['mean']:.3f}" if stats_diff["mean"] is not None else "NA")

    # =====================================================
    # ONGLETS
    # =====================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Statistiques",
        "📈 Graphiques",
        "🗺️ Cartes",
        "🧠 Analyse & interprétation",
        "⬇️ Export"
    ])

    # =====================================================
    # ONGLET 1 - STATISTIQUES
    # =====================================================
    with tab1:
        st.markdown('<div class="section-title">Nombre d’images utilisées</div>', unsafe_allow_html=True)

        cc1, cc2 = st.columns(2)
        with cc1:
            st.metric("Images période 1", count_p1)
        with cc2:
            st.metric("Images période 2", count_p2)

        st.markdown('<div class="section-title">Tableau comparatif des statistiques</div>', unsafe_allow_html=True)

        df_stats = pd.DataFrame([
            {
                "Période": f"Période 1 ({year_1})",
                "Mois": ", ".join(months_1_labels),
                "Moyenne": stats_p1["mean"],
                "P25": stats_p1["p25"],
                "P75": stats_p1["p75"],
                "Écart-type": stats_p1["stdDev"],
            },
            {
                "Période": f"Période 2 ({year_2})",
                "Mois": ", ".join(months_2_labels),
                "Moyenne": stats_p2["mean"],
                "P25": stats_p2["p25"],
                "P75": stats_p2["p75"],
                "Écart-type": stats_p2["stdDev"],
            },
            {
                "Période": "Différence",
                "Mois": "-",
                "Moyenne": stats_diff["mean"],
                "P25": stats_diff["p25"],
                "P75": stats_diff["p75"],
                "Écart-type": stats_diff["stdDev"],
            },
        ])

        st.dataframe(df_stats.round(3), use_container_width=True)

        st.markdown('<div class="section-title">Surfaces de changement (hectares)</div>', unsafe_allow_html=True)

        s1, s2, s3 = st.columns(3)
        with s1:
            st.metric("Surface en diminution (ha)", f"{surface_stats['diminution_ha']:.2f}")
        with s2:
            st.metric("Surface stable (ha)", f"{surface_stats['stable_ha']:.2f}")
        with s3:
            st.metric("Surface en augmentation (ha)", f"{surface_stats['augmentation_ha']:.2f}")

    # =====================================================
    # ONGLET 2 - GRAPHIQUES
    # =====================================================
    with tab2:
        st.markdown('<div class="section-title">Graphique comparatif du NDVI</div>', unsafe_allow_html=True)

        indicators = ["Moyenne", "P25", "P75", "Écart-type"]
        values_p1 = [stats_p1["mean"], stats_p1["p25"], stats_p1["p75"], stats_p1["stdDev"]]
        values_p2 = [stats_p2["mean"], stats_p2["p25"], stats_p2["p75"], stats_p2["stdDev"]]

        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                name=f"Période 1 ({year_1})",
                x=indicators,
                y=values_p1,
                text=[f"{v:.3f}" if v is not None else "NA" for v in values_p1],
                textposition="outside",
            )
        )

        fig.add_trace(
            go.Bar(
                name=f"Période 2 ({year_2})",
                x=indicators,
                y=values_p2,
                text=[f"{v:.3f}" if v is not None else "NA" for v in values_p2],
                textposition="outside",
            )
        )

        fig.update_layout(
            title="Comparaison des statistiques robustes du NDVI entre les deux périodes",
            xaxis_title="Indicateurs",
            yaxis_title="Valeur",
            barmode="group",
            legend_title="Périodes",
            height=520,
            margin=dict(l=40, r=40, t=70, b=40),
        )

        st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-title">Graphique des surfaces de changement</div>', unsafe_allow_html=True)

        df_surface = pd.DataFrame({
            "Classe": ["Diminution", "Stable", "Augmentation"],
            "Surface (ha)": [
                surface_stats["diminution_ha"],
                surface_stats["stable_ha"],
                surface_stats["augmentation_ha"],
            ]
        })

        fig_surface = px.bar(
            df_surface,
            x="Classe",
            y="Surface (ha)",
            title="Répartition des surfaces selon le type de changement"
        )

        st.plotly_chart(fig_surface, use_container_width=True)

    # =====================================================
    # ONGLET 3 - CARTES
    # =====================================================
    with tab3:
        st.markdown('<div class="section-title">Cartes comparatives</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="highlight-box">
            <b>Lecture des cartes :</b><br>
            - Carte NDVI : les valeurs plus élevées traduisent une végétation plus vigoureuse.<br>
            - Carte de différence : le vert indique une augmentation, le rouge une diminution.<br>
            - Carte classée : rouge = diminution, gris = stabilité, vert = augmentation.
            </div>
            """,
            unsafe_allow_html=True
        )

        m = geemap.Map()
        m.centerObject(region, 8)

        m.addLayer(
            region.style(**{"color": "blue", "fillColor": "00000000", "width": 2}),
            {},
            "Région"
        )

        m.addLayer(ndvi_p1, get_ndvi_vis_params(), f"NDVI période 1 ({year_1})")
        m.addLayer(ndvi_p2, get_ndvi_vis_params(), f"NDVI période 2 ({year_2})")
        m.addLayer(diff_ndvi, get_diff_vis_params(), "Différence NDVI")
        m.addLayer(classified_change, get_classified_change_vis_params(), "Changement classé")

        m.add_colorbar(
            vis_params=get_ndvi_vis_params(),
            label="NDVI",
            layer_name=f"NDVI période 1 ({year_1})",
            position="bottomleft"
        )

        m.add_colorbar(
            vis_params=get_diff_vis_params(),
            label="Différence NDVI",
            layer_name="Différence NDVI",
            position="bottomright"
        )

        m.addLayerControl()
        m.to_streamlit(height=700)

    # =====================================================
    # ONGLET 4 - ANALYSE & INTERPRÉTATION
    # =====================================================
    with tab4:
        st.markdown('<div class="section-title">Analyse des résultats</div>', unsafe_allow_html=True)

        analyse_text = (
            f"Le NDVI moyen de la période 1 ({year_1}) est de {stats_p1['mean']:.3f}, "
            f"contre {stats_p2['mean']:.3f} pour la période 2 ({year_2}). "
            f"Les percentiles P25 et P75 décrivent la distribution des valeurs de NDVI "
            f"et permettent une lecture plus robuste que les seules valeurs minimales et maximales. "
            f"L’écart-type est de {stats_p1['stdDev']:.3f} pour la période 1 et de {stats_p2['stdDev']:.3f} "
            f"pour la période 2. "
            f"Les surfaces calculées montrent {surface_stats['diminution_ha']:.2f} ha en diminution, "
            f"{surface_stats['stable_ha']:.2f} ha stables et {surface_stats['augmentation_ha']:.2f} ha en augmentation."
        )

        st.markdown(
            f"""
            <div class="highlight-box">
            {analyse_text}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown('<div class="section-title">Interprétation des résultats</div>', unsafe_allow_html=True)

        diff_mean = stats_diff["mean"]
        if diff_mean is not None:
            if diff_mean > 0.02:
                interpretation = (
                    "La comparaison suggère une amélioration globale de la vigueur de la végétation entre les deux périodes. "
                    "Cette évolution peut être liée à de meilleures conditions hydriques, à une dynamique culturale plus favorable "
                    "ou à une couverture végétale plus dense."
                )
            elif diff_mean < -0.02:
                interpretation = (
                    "La comparaison suggère une diminution globale de la vigueur de la végétation entre les deux périodes. "
                    "Cette baisse peut refléter un stress hydrique, une variabilité climatique, des changements d’occupation du sol "
                    "ou des pratiques agricoles différentes."
                )
            else:
                interpretation = (
                    "La comparaison suggère une relative stabilité globale de la végétation entre les deux périodes. "
                    "Les variations observées semblent limitées et peuvent correspondre à une dynamique saisonnière normale "
                    "ou à des changements de faible intensité."
                )
        else:
            interpretation = "Aucune interprétation automatique n’a pu être générée."

        st.markdown(
            f"""
            <div class="highlight-box">
            {interpretation}
            </div>
            """,
            unsafe_allow_html=True
        )

    # =====================================================
    # ONGLET 5 - EXPORT
    # =====================================================
    with tab5:
        st.markdown('<div class="section-title">Export des statistiques</div>', unsafe_allow_html=True)

        df_export = pd.DataFrame([
            {
                "Période": f"Période 1 ({year_1})",
                "Mois": ", ".join(months_1_labels),
                "Moyenne": stats_p1["mean"],
                "P25": stats_p1["p25"],
                "P75": stats_p1["p75"],
                "Écart-type": stats_p1["stdDev"],
                "Images": count_p1,
            },
            {
                "Période": f"Période 2 ({year_2})",
                "Mois": ", ".join(months_2_labels),
                "Moyenne": stats_p2["mean"],
                "P25": stats_p2["p25"],
                "P75": stats_p2["p75"],
                "Écart-type": stats_p2["stdDev"],
                "Images": count_p2,
            },
            {
                "Période": "Différence",
                "Mois": "-",
                "Moyenne": stats_diff["mean"],
                "P25": stats_diff["p25"],
                "P75": stats_diff["p75"],
                "Écart-type": stats_diff["stdDev"],
                "Images": "-",
            },
            {
                "Période": "Surface diminution",
                "Mois": "-",
                "Moyenne": surface_stats["diminution_ha"],
                "P25": None,
                "P75": None,
                "Écart-type": None,
                "Images": "-",
            },
            {
                "Période": "Surface stable",
                "Mois": "-",
                "Moyenne": surface_stats["stable_ha"],
                "P25": None,
                "P75": None,
                "Écart-type": None,
                "Images": "-",
            },
            {
                "Période": "Surface augmentation",
                "Mois": "-",
                "Moyenne": surface_stats["augmentation_ha"],
                "P25": None,
                "P75": None,
                "Écart-type": None,
                "Images": "-",
            },
        ])

        st.dataframe(df_export, use_container_width=True)

        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Télécharger les statistiques en CSV",
            data=csv,
            file_name="statistiques_ndvi_comparaison.csv",
            mime="text/csv"
        )

except Exception as e:
    st.error("Erreur lors de la comparaison des périodes.")
    st.exception(e)