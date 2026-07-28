"""
BetMachine / Miliardarul — aplicatie unificata
"""

from __future__ import annotations

import joblib
import pandas as pd
import streamlit as st

import data_source
import football_data_org as fdo
import scanner
from pipeline import analizeaza_meci


def construieste_tablou_decizie(piete: dict, prag_da: float = 1.30):
    cota = {nume: (1 / prob if prob > 0 else float("inf")) for nume, prob in piete.items()}

    prefera_12 = cota.get("12", float("inf")) <= prag_da
    excluse = {"1X", "X2"} if prefera_12 else set()

    randuri = []
    piete_da = []
    for nume, prob in piete.items():
        c = cota[nume]
        da = (c <= prag_da) and (nume not in excluse)
        if da:
            piete_da.append(nume)
        randuri.append({
            "Piata": nume,
            "Probabilitate": f"{prob:.1%}",
            "Cota corecta": f"{c:.2f}",
            "DA": "✅ DA" if da else ("— (exclus, acoperit de 12)" if nume in excluse else ""),
        })

    return pd.DataFrame(randuri), piete_da, cota

st.set_page_config(page_title="Miliardarul — BetMachine", layout="wide")
st.title("⚽ Miliardarul — BetMachine")
st.caption("Motor Poisson/Dixon-Coles pe date reale + semnal ML secundar, intr-un singur loc.")

tab_poisson, tab_rapid, tab_scanner, tab_despre = st.tabs([
    "🧮 Motor Poisson (Miliardarul)",
    "🎯 Model rapid (RandomForest)",
    "🎰 Scanner Bilete",
    "ℹ️ Despre",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — MOTORUL PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════
with tab_poisson:
    st.subheader("1. Alege liga")
    st.caption("Un singur apel incarca tot sezonul unei ligi (cache 6h).")

    if st.button("🌍 Incarca lista de tari si ligi", key="btn_ligi"):
        try:
            with st.spinner("Se incarca lista de ligi..."):
                st.session_state["ligi"] = data_source.leagues_cu_tari()
        except RuntimeError as e:
            st.error(str(e))

    ligi = st.session_state.get("ligi", [])
    if ligi:
        optiuni_liga = {}
        for tara in ligi:
            for liga in tara.get("leagues", []):
                eticheta = f"{tara.get('name', '?')} — {liga.get('name', '?')}"
                optiuni_liga[eticheta] = liga.get("id")

        filtru = st.text_input("🔍 Filtreaza dupa nume (tara sau liga)", "", key="filtru_liga")
        chei_filtrate = sorted(
            k for k in optiuni_liga if filtru.lower() in k.lower()
        ) if filtru else sorted(optiuni_liga.keys())

        if not chei_filtrate:
            st.warning(f"Nimic gasit pentru '{filtru}'.")
            league_id = None
        else:
            eticheta_aleasa = st.selectbox("Liga", chei_filtrate, key="select_liga")
            league_id = optiuni_liga[eticheta_aleasa]

        if league_id and st.button("📥 Incarca meciurile acestei ligi", key="btn_meciuri_liga"):
            try:
                with st.spinner("Se incarca meciurile ligii..."):
                    st.session_state["meciuri_liga"] = data_source.meciuri_liga(league_id)
                    st.session_state["liga_curenta"] = eticheta_aleasa
            except RuntimeError as e:
                st.error(str(e))

    meciuri_liga = st.session_state.get("meciuri_liga", [])
    if meciuri_liga:
        st.caption(f"Liga curenta: **{st.session_state.get('liga_curenta', '')}** — {len(meciuri_liga)} meciuri incarcate")

        echipe = {}
        for m in meciuri_liga:
            if m["echipa_gazda_id"]:
                echipe[m["echipa_gazda"]] = m["echipa_gazda_id"]
            if m["echipa_oaspete_id"]:
                echipe[m["echipa_oaspete"]] = m["echipa_oaspete_id"]

        if len(echipe) < 2:
            st.warning("Nu s-au gasit suficiente echipe in aceasta liga.")
        else:
            st.subheader("2. Alege cele doua echipe")
            nume_echipe = sorted(echipe.keys())
            col_a, col_b = st.columns(2)
            gazda_nume = col_a.selectbox("Echipa gazda", nume_echipe, key="sel_gazda")
            oaspete_nume = col_b.selectbox(
                "Echipa oaspete", nume_echipe,
                index=1 if len(nume_echipe) > 1 else 0, key="sel_oaspete",
            )

            col1, col2, col3 = st.columns(3)
            half_life = col1.slider("Half-life decay (zile)", 10, 90, 30)
            k_shrinkage = col2.slider("Shrinkage (k)", 1, 30, 10)
            n_meciuri_istoric = col3.slider("Meciuri istorice per echipa", 5, 30, 20)

            if st.button("🧮 Analizeaza meciul", type="primary"):
                if gazda_nume == oaspete_nume:
                    st.error("Alege doua echipe diferite.")
                else:
                    istoric_gazda = data_source.istoric_echipa_din_liga(
                        meciuri_liga, echipe[gazda_nume], n_meciuri_istoric
                    )
                    istoric_oaspete = data_source.istoric_echipa_din_liga(
                        meciuri_liga, echipe[oaspete_nume], n_meciuri_istoric
                    )

                    if len(istoric_gazda) < 1 or len(istoric_oaspete) < 1:
                        st.error("Nu exista destule meciuri terminate pentru aceste echipe.")
                    else:
                        rezultat = analizeaza_meci(
                            istoric_gazda, istoric_oaspete,
                            half_life_zile=half_life, k_shrinkage=k_shrinkage,
                        )
                        st.session_state["ultima_analiza"] = (
                            {"echipa_gazda": gazda_nume, "echipa_oaspete": oaspete_nume},
                            rezultat,
                        )

    if "ultima_analiza" in st.session_state:
        meci, rezultat = st.session_state["ultima_analiza"]
        st.markdown(f"### 📊 {meci['echipa_gazda']} — {meci['echipa_oaspete']}")

        rec = rezultat["reconciliere"]
        c1, c2 = st.columns(2)
        c1.metric("λ (goluri asteptate gazde)", f"{rec['lambda_gazde']:.2f}")
        c2.metric("μ (goluri asteptate oaspeti)", f"{rec['mu_oaspeti']:.2f}")

        st.markdown("#### Piete (probabilitate reala)")
        piete = rezultat["piete"]
        df_piete = pd.DataFrame([
            {"Piata": k, "Probabilitate": f"{v:.1%}", "Cota corecta": f"{(1 / v):.2f}" if v > 0 else "—"}
            for k, v in piete.items()
        ])
        st.dataframe(df_piete, use_container_width=True, hide_index=True)

        st.markdown("#### 🎯 Tablou Decizie Combo")
        prag_da = st.slider("Prag DA (cota corecta maxima)", 1.05, 2.00, 1.30, 0.01, key="prag_da")
        df_decizie, piete_da, cota_map = construieste_tablou_decizie(piete, prag_da)
        st.dataframe(df_decizie, use_container_width=True, hide_index=True)

        if piete_da:
            cota_combo = 1.0
            for p in piete_da:
                cota_combo *= cota_map[p]
            st.success(f"**Combo CREMA** ({' + '.join(piete_da)}) — cota combinata: **{cota_combo:.2f}**")

# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — MODEL RAPID
# ═══════════════════════════════════════════════════════════════════════
with tab_rapid:
    st.subheader("Model rapid — cote + RandomForest")
    
    @st.cache_resource
    def incarca_model_1x2():
        try:
            return joblib.load("model_1x2.joblib")
        except Exception as e:
            st.error(f"Nu am putut incarca model_1x2.joblib: {e}")
            return None

    model_1x2 = incarca_model_1x2()

    FEATURES_1X2 = [
        "shots_home", "shots_away",
        "shots_on_target_home", "shots_on_target_away",
        "xG_home", "xG_away",
        "corners_home", "corners_away",
        "form_home", "form_away",
        "league_strength",
    ]

    cols = st.columns(3)
    valori = {}
    for i, feat in enumerate(FEATURES_1X2):
        valori[feat] = cols[i % 3].number_input(feat, value=None, step=0.1, format="%.2f")

    odd_1 = st.number_input("Cota 1", min_value=1.01, value=2.00, step=0.01)
    odd_X = st.number_input("Cota X", min_value=1.01, value=3.30, step=0.01)
    odd_2 = st.number_input("Cota 2", min_value=1.01, value=3.60, step=0.01)

    if st.button("🎯 Ruleaza modelul"):
        lipsesc = [f for f, v in valori.items() if v is None]
        if lipsesc:
            st.error(f"Lipsesc valori pentru: {', '.join(lipsesc)}.")
        elif model_1x2 is not None:
            X = [[valori[f] for f in FEATURES_1X2]]
            pred = model_1x2.predict(X)[0]
            proba = model_1x2.predict_proba(X)[0]

            st.markdown(f"**Predictie model:** {['1', 'X', '2'][pred]}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — SCANNER AUTOMAT DE BILETE (ACTUALIZAT)
# ═══════════════════════════════════════════════════════════════════════
with tab_scanner:
    st.subheader("Scanner automat de bilete")
    st.caption(
        "Scaneaza meciurile pe intervale de date si construieste automat categoriile de bilet."
    )

    st.markdown("#### Sursa 1 — RapidAPI (Scanare automata pe intervale de date)")
    foloseste_rapidapi = st.checkbox("Include RapidAPI (toate ligile, scanat pe date)", value=True, key="cb_rapidapi")
    zile_istoric_rapidapi = st.slider("Zile de istoric in urma (RapidAPI)", 10, 60, 30, key="zile_istoric_rapidapi")

    st.markdown("#### Sursa 2 — football-data.org (ligi mari)")
    competitii_alese = st.multiselect(
        "Competiții football-data.org",
        list(fdo.COMPETITII_GRATUITE.keys()),
        default=["PL", "PD", "SA", "BL1", "FL1"],
        format_func=lambda cod: fdo.COMPETITII_GRATUITE.get(cod, cod),
        key="competitii_scanare",
    )

    zile = st.slider("Cate zile inainte?", 1, 14, 7, key="zile_scanare")

    surse = []
    if foloseste_rapidapi:
        surse.append(("rapidapi", "all"))
    for cod in competitii_alese:
        surse.append(("football_data", cod))

    col_min, col_max = st.columns(2)
    cota_min = col_min.number_input("Cota minima (categoria Sigur)", 1.01, 3.00, 1.30, 0.01)
    cota_max = col_max.number_input("Cota maxima (categoria Sigur)", 1.05, 5.00, 1.80, 0.01)

    if st.button("🎰 Scaneaza și construiește biletele", type="primary"):
        if not surse:
            st.error("Alege cel putin o sursa.")
        else:
            bara = st.progress(0.0, text="Scanez...")

            def _progres(i, total, ident):
                bara.progress((i + 1) / total, text=f"Scanez {i + 1}/{total}: {ident}...")

            candidati = scanner.scaneaza(
                surse,
                zile_inainte=zile,
                zile_istoric=zile_istoric_rapidapi,
                progres_callback=_progres,
            )
            bara.empty()
            st.session_state["bilete"] = scanner.construieste_bilete(
                candidati, cota_min_sigur=cota_min, cota_max_sigur=cota_max
            )
            st.success(f"Am gasit {len(candidati)} meciuri viitoare analizabile.")

    bilete = st.session_state.get("bilete")
    if bilete:
        def _afiseaza_categorie(titlu: str, selectii: list, culoare: str = "🟢"):
            st.markdown(f"#### {culoare} {titlu}")
            if not selectii:
                st.caption("Niciun meci gasit pentru aceasta categorie.")
                return
            cota_totala = 1.0
            for s in selectii:
                nume_piata = scanner.NUME_PIATA.get(s.piata, s.piata)
                st.markdown(
                    f"✔️ `{s.cota:.2f}` ({s.data.strftime('%d.%m')}) "
                    f"**{s.echipa_gazda}** vs **{s.echipa_oaspete}** ➜ {nume_piata} "
                    f"_(prob. {s.probabilitate:.0%})_"
                )
                cota_totala *= s.cota
            st.caption(f"Cotă totală categorie: **{cota_totala:.2f}**")

        _afiseaza_categorie("Sigur (1/X/2/1X/X2)", bilete["sigur"], "🟢")
        _afiseaza_categorie("Goluri (Peste 1.5 / Peste 2.5 / Sub 3.5)", bilete["goluri"], "🔵")
        _afiseaza_categorie("Gazdele sau oaspeții marchează", bilete["scor_echipe"], "🟡")
        _afiseaza_categorie("GG (ambele echipe marchează)", bilete["gg"], "🟣")

# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — DESPRE
# ═══════════════════════════════════════════════════════════════════════
with tab_despre:
    st.markdown("""
    ### Despre Miliardarul
    Aplicatie personala de analiza a meciurilor de fotbal.
    """)
# --- COD DE ADĂUGAT ÎN app.py ---
if not chei_filtrate:
    st.warning(f"Nimic gasit pentru '{filtru}'.")
    league_id = None
else:
    eticheta_aleasa = st.selectbox("Liga", chei_filtrate, key="select_liga")
    league_id = optiuni_liga[eticheta_aleasa]
    
    # Adăugăm un selector de sezon pentru flexibilitate totală în pauzele competiționale
    sezon_ales = st.selectbox(
        "📅 Sezon (utilizat pentru fallback / istorice)", 
        ["2025-2026", "2024-2025", "2023-2024", "2022-2023"], 
        index=1 # Pune automat pe 2024-2025 ca să ai date complete de analizat în pauze
    )
    # Convertim formatul (ex: din '2024-2025' în '24-25' scurt, cerut de soccerdata)
    format_sezon = f"{sezon_ales[2:4]}-{sezon_ales[7:9]}"

if league_id and st.button("📥 Incarca meciurile acestei ligi", key="btn_meciuri_liga"):
    try:
        with st.spinner("Se incarca meciurile..."):
            # Trimitem și sezonul ales către data_source
            if isinstance(league_id, str) and "-" in league_id:
                st.session_state["meciuri_liga"] = data_source._incarca_meciuri_din_soccerdata(league_id, season=format_sezon)
            else:
                st.session_state["meciuri_liga"] = data_source.meciuri_liga(league_id)
                
            st.session_state["liga_curenta"] = f"{eticheta_aleasa} ({sezon_ales})"
    except RuntimeError as e:
        st.error(str(e))
