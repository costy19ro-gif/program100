"""
BetMachine / Miliardarul — aplicatie unificata
=================================================
Doua motoare, un singur loc:

  1. "Motor Poisson (Miliardarul)" — pipeline.py: Decay + Shrinkage Bayesian +
     reconciliere lambda/mu + Dixon-Coles + scanner de piete, pe date reale
     din API-Football (via data_source.py). Asta e sursa principala.

  2. "Model rapid (RandomForest)" — semnal ML secundar, antrenat pe
     model_1x2.joblib. Foloseste-l doar ca a doua parere, nu ca sursa
     principala: are nevoie de statistici per meci (xG, sut-uri, cornere)
     pe care API-ul gratuit nu le da mereu.

Ruleaza cu: streamlit run app.py
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
    """
    Tablou Decizie Combo — regulile lui Julien:
    - cota corecta = 1 / probabilitate
    - o piata e "DA" daca cota corecta <= prag_da
    - verifica INTAI piata '12' (fara egal): daca trece pragul, o prefera
      fata de 1X/X2 (care sunt excluse din combo, ca sa nu fie redundante
      cu '12' — 1X si X2 se suprapun partial cu ea)

    Intoarce: (dataframe pt. afisare, lista piete DA, dict cota per piata)
    """
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
# TAB 1 — MOTORUL PRINCIPAL: Poisson + Dixon-Coles, date reale
# ═══════════════════════════════════════════════════════════════════════
with tab_poisson:
    st.subheader("1. Alege liga")
    st.caption(
        "Un singur apel incarca tot sezonul unei ligi (cache 6h) — economisim "
        "cota gratuita. Istoricul fiecarei echipe se calculeaza local, din "
        "aceleasi date, fara apeluri suplimentare."
    )

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

        filtru = st.text_input(
            "🔍 Filtreaza dupa nume (tara sau liga)", "",
            key="filtru_liga",
            placeholder="ex: Europa, Argentina, Romania...",
        )
        chei_filtrate = sorted(
            k for k in optiuni_liga if filtru.lower() in k.lower()
        ) if filtru else sorted(optiuni_liga.keys())

        if not chei_filtrate:
            st.warning(f"Nimic gasit pentru '{filtru}'. Incearca alt termen — "
                       f"unele competitii (ex. cele UEFA) pot fi listate sub "
                       f"'Europe'/'International' in loc de numele lor, iar "
                       f"ligile foarte mici s-ar putea sa nu fie in acest API gratuit.")
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

                    if len(istoric_gazda) < 3 or len(istoric_oaspete) < 3:
                        st.warning(
                            "Prea putine meciuri istorice gasite pentru una din echipe "
                            "(sub 3) — rezultatul poate fi nesigur."
                        )

                    if len(istoric_gazda) < 1 or len(istoric_oaspete) < 1:
                        st.error("Nu exista destule meciuri terminate pentru aceste echipe in datele incarcate.")
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

        st.markdown("#### Piete (probabilitate reala, din matricea de scor)")
        piete = rezultat["piete"]
        df_piete = pd.DataFrame([
            {"Piata": k, "Probabilitate": f"{v:.1%}", "Cota corecta": f"{(1 / v):.2f}" if v > 0 else "—"}
            for k, v in piete.items()
        ])
        st.dataframe(df_piete, use_container_width=True, hide_index=True)

        st.markdown("#### 🎯 Tablou Decizie Combo")
        prag_da = st.slider(
            "Prag DA (cota corecta maxima)", 1.05, 2.00, 1.30, 0.01,
            key="prag_da",
            help="O piata e marcata DA daca 1/probabilitate <= acest prag. "
                 "'12' e verificata prima — daca trece pragul, inlocuieste 1X/X2 in combo.",
        )
        df_decizie, piete_da, cota_map = construieste_tablou_decizie(piete, prag_da)
        st.dataframe(df_decizie, use_container_width=True, hide_index=True)

        if piete_da:
            cota_combo = 1.0
            for p in piete_da:
                cota_combo *= cota_map[p]
            st.success(
                f"**Combo CREMA** ({' + '.join(piete_da)}) — "
                f"cota combinata: **{cota_combo:.2f}**"
            )
        else:
            st.info("Nicio piata nu trece pragul DA la acest prag ales.")

        st.markdown("#### Top 5 scoruri probabile")
        df_scoruri = pd.DataFrame(
            [{"Scor": f"{h}-{a}", "Probabilitate": f"{p:.1%}"} for h, a, p in rezultat["top_scoruri"]]
        )
        st.dataframe(df_scoruri, use_container_width=True, hide_index=True)

    st.divider()
    with st.expander("📅 Meciurile de azi (informativ, separat de motorul Poisson)"):
        st.caption(
            "Foloseste alt sistem de ID-uri decat cel de mai sus, deci nu se "
            "poate lega automat de analiza pe liga."
        )
        if st.button("Incarca meciurile de azi", key="btn_meciuri_azi"):
            try:
                with st.spinner("Se incarca..."):
                    st.session_state["meciuri_azi"] = data_source.meciuri_azi()
            except RuntimeError as e:
                st.error(str(e))
        meciuri_azi = st.session_state.get("meciuri_azi", [])
        if meciuri_azi:
            st.dataframe(
                pd.DataFrame(meciuri_azi)[["fixture_id", "echipa_gazda", "echipa_oaspete", "scor", "status"]],
                use_container_width=True,
            )

    st.caption(
        "Sursa principala de adevar: pipeline.py (Decay + Shrinkage + Dixon-Coles). "
        "Nu foloseste date inventate — doar istoricul real venit din API."
    )

# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — MODEL RAPID: RandomForest + cote de pe piata (semnal secundar)
# ═══════════════════════════════════════════════════════════════════════
with tab_rapid:
    st.subheader("Model rapid — cote + RandomForest")
    st.warning(
        "⚠️ Acest tab e un semnal SECUNDAR. Modelul a fost antrenat pe statistici "
        "reale per meci (xG, sut-uri, cornere) — daca nu ai acele date pentru "
        "meciul curent, nu inventa valori default; foloseste doar motorul Poisson din primul tab."
    )

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

    st.markdown("#### Introdu statisticile reale ale meciului")
    st.caption("Fara valori inventate — completeaza doar ce ai confirmat (ex. din /fixtures/statistics).")

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
            st.error(f"Lipsesc valori pentru: {', '.join(lipsesc)}. Nu completez automat cu date inventate.")
        elif model_1x2 is None:
            st.error("Modelul nu e incarcat.")
        else:
            X = [[valori[f] for f in FEATURES_1X2]]
            pred = model_1x2.predict(X)[0]
            proba = model_1x2.predict_proba(X)[0]

            inv = 1 / odd_1 + 1 / odd_X + 1 / odd_2
            prob_piata = {"1": (1 / odd_1) / inv, "X": (1 / odd_X) / inv, "2": (1 / odd_2) / inv}

            st.markdown(f"**Predictie model:** {['1', 'X', '2'][pred]}")
            df_comp = pd.DataFrame({
                "Rezultat": ["1", "X", "2"],
                "Probabilitate model": [f"{p:.1%}" for p in proba],
                "Probabilitate piata (din cote)": [f"{prob_piata[k]:.1%}" for k in ["1", "X", "2"]],
                "Cota": [odd_1, odd_X, odd_2],
            })
            st.dataframe(df_comp, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — SCANNER AUTOMAT DE BILETE
# ═══════════════════════════════════════════════════════════════════════
with tab_scanner:
    st.subheader("Scanner automat de bilete")
    st.caption(
        "Cauta meciuri viitoare din doua surse (RapidAPI + football-data.org), "
        "ruleaza motorul Poisson pe fiecare, si construieste automat categoriile "
        "de bilet. **Limitare reala:** forma fiecarei echipe se calculeaza doar "
        "din meciurile aceleiasi competitii/sezon. Prima repriza nu e folosita "
        "inca — categoria a fost eliminata din bilet."
    )
    st.caption(
        "⚠️ In perioada de vara, ligile mari din Europa de obicei nu au meciuri "
        "programate (pauza intre sezoane) — '0 meciuri gasite' poate fi normal."
    )

    st.markdown("#### Sursa 1 — RapidAPI (ligi mici/mijlocii + Liga I)")
    if st.button("🌍 Incarca lista de ligi RapidAPI", key="btn_ligi_scanner"):
        try:
            with st.spinner("Se incarca lista de ligi..."):
                st.session_state["ligi"] = data_source.leagues_cu_tari()
        except RuntimeError as e:
            st.error(str(e))

    ligi = st.session_state.get("ligi", [])
    optiuni_liga = {}
    ligi_alese = []
    if not ligi:
        st.info("Apasa butonul de mai sus daca vrei sa incluzi ligi RapidAPI (opțional).")
    else:
        for tara in ligi:
            for liga in tara.get("leagues", []):
                eticheta = f"{tara.get('name', '?')} — {liga.get('name', '?')}"
                optiuni_liga[eticheta] = liga.get("id")

        LIGI_IMPLICITE = [("Romania", "Liga I")]
        implicite = [
            f"{tara.get('name')} — {liga.get('name')}"
            for tara in ligi for liga in tara.get("leagues", [])
            for tara_tinta, liga_tinta in LIGI_IMPLICITE
            if tara.get("name") == tara_tinta and liga.get("name") == liga_tinta
        ]

        ligi_alese = st.multiselect(
            "Ligi RapidAPI", sorted(optiuni_liga.keys()),
            default=implicite, key="ligi_scanare",
        )

    st.markdown("#### Sursa 2 — football-data.org (ligi mari, meciuri viitoare corect marcate)")
    competitii_alese = st.multiselect(
        "Competiții football-data.org",
        list(fdo.COMPETITII_GRATUITE.keys()),
        default=["PL", "PD", "SA", "BL1", "FL1"],
        format_func=lambda cod: fdo.COMPETITII_GRATUITE.get(cod, cod),
        key="competitii_scanare",
    )

    zile = st.slider("Cate zile inainte?", 1, 14, 7, key="zile_scanare")

    surse = [("rapidapi", optiuni_liga[k]) for k in ligi_alese] + \
            [("football_data", cod) for cod in competitii_alese]

    if st.button("🔍 Verifica ce surse (din cele alese) au meciuri active", key="btn_verifica_ligi"):
        if not surse:
            st.error("Alege cel putin o liga sau o competiție.")
        else:
            with st.spinner("Verific fiecare sursa..."):
                verificare = scanner.verifica_ligi_active(surse, zile_inainte=zile)
            id_catre_eticheta = {v: k for k, v in optiuni_liga.items()}
            randuri = []
            for r in verificare:
                nume = (
                    id_catre_eticheta.get(r["id"], str(r["id"]))
                    if r["tip"] == "rapidapi"
                    else fdo.COMPETITII_GRATUITE.get(r["id"], r["id"])
                )
                randuri.append({
                    "Sursa": "RapidAPI" if r["tip"] == "rapidapi" else "football-data.org",
                    "Liga/Competiție": nume,
                    "Meciuri viitoare": r["meciuri_viitoare"] if r["eroare"] is None else "eroare",
                    "Detaliu eroare": r["eroare"] or "",
                })
            df_verificare = pd.DataFrame(randuri).sort_values(
                "Meciuri viitoare", ascending=False,
                key=lambda s: s.map(lambda v: v if isinstance(v, int) else -1),
            )
            st.dataframe(df_verificare, use_container_width=True, hide_index=True)

    col_min, col_max = st.columns(2)
    cota_min = col_min.number_input("Cota minima (categoria Sigur)", 1.01, 3.00, 1.30, 0.01)
    cota_max = col_max.number_input("Cota maxima (categoria Sigur)", 1.05, 5.00, 1.80, 0.01)

    if st.button("🎰 Scaneaza și construiește biletele", type="primary"):
        if not surse:
            st.error("Alege cel putin o liga sau o competiție.")
        else:
            bara = st.progress(0.0, text="Scanez sursele...")

            def _progres(i, total, ident):
                bara.progress((i + 1) / total, text=f"Scanez {i + 1}/{total}: {ident}...")

            candidati = scanner.scaneaza(surse, zile_inainte=zile, progres_callback=_progres)
            bara.empty()
            st.session_state["bilete"] = scanner.construieste_bilete(
                candidati, cota_min_sigur=cota_min, cota_max_sigur=cota_max
            )
            st.session_state["nr_candidati"] = len(candidati)
            st.success(
                f"Am gasit {len(candidati)} meciuri viitoare cu istoric suficient, "
                f"din {len(surse)} surse scanate."
            )

    bilete = st.session_state.get("bilete")
    if bilete:
        def _afiseaza_categorie(titlu: str, selectii: list, culoare: str = "🟢"):
            st.markdown(f"#### {culoare} {titlu}")
            if not selectii:
                st.caption("Niciun meci gasit pentru aceasta categorie, cu criteriile curente.")
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

        toate = bilete["sigur"] + bilete["goluri"] + bilete["scor_echipe"] + bilete["gg"]
        if toate:
            cota_generala = 1.0
            for s in toate:
                cota_generala *= s.cota
            st.divider()
            st.markdown(f"### 💰 Cotă totală bilet complet ({len(toate)} selecții): **{cota_generala:.2f}**")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — DESPRE
# ═══════════════════════════════════════════════════════════════════════
with tab_despre:
    st.markdown("""
    ### Despre Miliardarul

    Aplicatie personala de analiza a meciurilor de fotbal, construita pe doua motoare:

    - **Motor principal** — Poisson + Dixon-Coles, portat din sistemul Excel:
      decay exponential pe istoric, shrinkage Bayesian pentru esantioane mici,
      reconciliere λ/μ, corectie Dixon-Coles pentru scoruri mici, scanner de piete
      care calculeaza fiecare piata direct din matricea de scor (nu prin inmultire
      naiva de cote).
    - **Semnal secundar** — un model RandomForest antrenat pe statistici reale
      (xG, sut-uri, cornere), folosit doar ca a doua parere.

    Fara date inventate, niciodata — daca o statistica nu exista, campul ramane gol
    in loc sa fie completat cu o valoare default.

    ---
    *Uz personal. Nu constituie sfat financiar.*
    """)
