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
            
            sezon_ales = st.selectbox(
                "📅 Sezon (utilizat pentru fallback / istorice)", 
                ["2025-2026", "2024-2025", "2023-2024", "2022-2023"], 
                index=1
            )
            format_sezon = f"{sezon_ales[2:4]}-{sezon_ales[7:9]}"

        if league_id and st.button("📥 Incarca meciurile acestei ligi", key="btn_meciuri_liga"):
            try:
                with st.spinner("Se incarca meciurile ligii..."):
                    if isinstance(league_id, str) and "-" in league_id:
                        st.session_state["meciuri_liga"] = data_source._incarca_meciuri_din_soccerdata(league_id, season=format_sezon)
                    else:
                        st.session_state["meciuri_liga"] = data_source.meciuri_liga(league_id)
                        
                    st.session_state["liga_curenta"] = f"{eticheta_aleasa} ({sezon_ales})"
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
        valori[feat] = cols[i % 3].number_input(feat, value=0.0, step=0.1, format="%.2f")

    odd_1 = st.number_input("Cota 1", min_value=1.01, value=2.00, step=0.01)
    odd_X = st.number_input("Cota X", min_value=1.01, value=3.30, step=0.01)
    odd_2 = st.number_input("Cota 2", min_value=1.01, value=3.60, step=0.01)

    if st.button("🎯 Ruleaza modelul rapid", key="btn_run_rf"):
        if model_1x2 is not None:
            try:
                X_nou = pd.DataFrame([valori])
                pred_proaspat = model_1x2.predict_proba(X_nou)[0]
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Probabilitate 1", f"{pred_proaspat[0]:.1%}")
                c2.metric("Probabilitate X", f"{pred_proaspat[1]:.1%}")
                c3.metric("Probabilitate 2", f"{pred_proaspat[2]:.1%}")
            except Exception as ex:
                st.error(f"Eroare la rularea predictiei: {ex}")
        else:
            st.error("Modelul RandomForest (.joblib) nu este incarcat.")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — SCANNER
# ═══════════════════════════════════════════════════════════════════════
with tab_scanner:
    st.subheader("🎰 Scanner Bilete")
    st.info("Modul dedicat pentru scanarea si verificarea automata a pietelor active.")

# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — DESPRE
# ═══════════════════════════════════════════════════════════════════════
with tab_despre:
    st.subheader("ℹ️ Despre proiect")
    st.markdown("""
