"""
Scanner automat de meciuri viitoare
====================================
Gaseste meciuri din urmatoarele N zile si calculeaza cotele/probabilitatile
folosind motorul Poisson din pipeline.py.

Noua arhitectura:
- RapidAPI scaneaza pe date (meciuri_interval), acoperind automat toate ligile.
- football-data.org scaneaza pe competitii specifice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import data_source
import football_data_org as fdo
from pipeline import analizeaza_meci


@dataclass
class SelectieMeci:
    data: date
    sursa: str
    liga_id: str
    echipa_gazda: str
    echipa_oaspete: str
    piata: str
    probabilitate: float
    cota: float
    detalii: dict


NUME_PIATA = {
    "1": "Victorie gazde (1)",
    "X": "Egal (X)",
    "2": "Victorie oaspeți (2)",
    "1X": "Sansa dubla 1X",
    "X2": "Sansa dubla X2",
    "12": "Sansa dubla 12",
    "Peste_1.5": "Peste 1.5 goluri",
    "Peste_2.5": "Peste 2.5 goluri",
    "Sub_2.5": "Sub 2.5 goluri",
    "Sub_3.5": "Sub 3.5 goluri",
    "Gazde_marcheaza": "Gazdele marchează",
    "Oaspeti_marcheaza": "Oaspeții marchează",
    "GG": "Ambele marchează (GG)",
}


def scaneaza(
    surse: list[tuple[str, str | int]],
    zile_inainte: int = 7,
    zile_istoric: int = 30,
    progres_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    candidati = []
    azi = date.today()
    data_max = azi + timedelta(days=zile_inainte)

    are_rapidapi = any(tip == "rapidapi" for tip, _ in surse)

    if are_rapidapi:
        if progres_callback:
            progres_callback(0, len(surse), "RapidAPI (interval de date)")

        d_start = azi - timedelta(days=zile_istoric)
        meciuri_rapidapi = data_source.meciuri_interval(d_start, data_max)

        viitoare_rapidapi = [
            m for m in meciuri_rapidapi
            if not m["terminat"] and m["data"] and azi <= m["data"] <= data_max
        ]

        for m in viitoare_rapidapi:
            h_id, a_id = m["echipa_gazda_id"], m["echipa_oaspete_id"]
            if not h_id or not a_id:
                continue

            hist_h = data_source.istoric_echipa_din_liga(meciuri_rapidapi, h_id)
            hist_a = data_source.istoric_echipa_din_liga(meciuri_rapidapi, a_id)

            if len(hist_h) < 3 or len(hist_a) < 3:
                continue

            rez = analizeaza_meci(hist_h, hist_a, data_referinta=m["data"])
            candidati.append({
                "meci": m,
                "sursa": "rapidapi",
                "liga_id": m.get("league_id"),
                "rezultat": rez,
            })

    surse_fd = [s for s in surse if s[0] == "football_data"]
    for idx, (tip, cod) in enumerate(surse_fd):
        if progres_callback:
            progres_callback(idx, len(surse_fd), f"football-data: {cod}")

        try:
            meciuri = fdo.meciuri_competitie_toate(str(cod))
        except Exception:
            continue

        viitoare = [
            m for m in meciuri
            if not m["terminat"] and m["data"] and azi <= m["data"] <= data_max
        ]

        for m in viitoare:
            h_id, a_id = m["echipa_gazda_id"], m["echipa_oaspete_id"]
            if not h_id or not a_id:
                continue

            hist_h = fdo.af.istoric_echipa_din_liga(meciuri, h_id)
            hist_a = fdo.af.istoric_echipa_din_liga(meciuri, a_id)

            if len(hist_h) < 3 or len(hist_a) < 3:
                continue

            rez = analizeaza_meci(hist_h, hist_a, data_referinta=m["data"])
            candidati.append({
                "meci": m,
                "sursa": "football_data",
                "liga_id": cod,
                "rezultat": rez,
            })

    return candidati


def construieste_bilete(
    candidati: list[dict],
    cota_min_sigur: float = 1.30,
    cota_max_sigur: float = 1.80,
) -> dict[str, list[SelectieMeci]]:
    sigur, goluri, scor_echipe, gg = [], [], [], []

    for item in candidati:
        m = item["meci"]
        piete = item["rezultat"]["piete"]

        def _cota(p_nume: str) -> float:
            prob = piete.get(p_nume, 0)
            return (1 / prob) if prob > 0 else float("inf")

        def _creaza_selectie(p_nume: str) -> SelectieMeci:
            prob = piete[p_nume]
            return SelectieMeci(
                data=m["data"],
                sursa=item["sursa"],
                liga_id=str(item["liga_id"]),
                echipa_gazda=m["echipa_gazda"],
                echipa_oaspete=m["echipa_oaspete"],
                piata=p_nume,
                probabilitate=prob,
                cota=(1 / prob) if prob > 0 else float("inf"),
                detalii=item["rezultat"],
            )

        cota_12 = _cota("12")
        piata_sigur = "12" if cota_12 <= cota_max_sigur else None

        if not piata_sigur:
            cand_sigur = [
                (p, _cota(p)) for p in ["1", "X", "2", "1X", "X2"]
                if cota_min_sigur <= _cota(p) <= cota_max_sigur
            ]
            if cand_sigur:
                cand_sigur.sort(key=lambda x: -piete[x[0]])
                piata_sigur = cand_sigur[0][0]

        if piata_sigur and cota_min_sigur <= _cota(piata_sigur) <= cota_max_sigur:
            sigur.append(_creaza_selectie(piata_sigur))

        for p_gol in ["Peste_1.5", "Peste_2.5", "Sub_3.5"]:
            if _cota(p_gol) <= 1.50 and piete.get(p_gol, 0) >= 0.65:
                goluri.append(_creaza_selectie(p_gol))
                break

        p_h = piete.get("Gazde_marcheaza", 0)
        p_a = piete.get("Oaspeti_marcheaza", 0)
        if p_h >= 0.75 and _cota("Gazde_marcheaza") <= 1.35:
            scor_echipe.append(_creaza_selectie("Gazde_marcheaza"))
        elif p_a >= 0.75 and _cota("Oaspeti_marcheaza") <= 1.35:
            scor_echipe.append(_creaza_selectie("Oaspeti_marcheaza"))

        if piete.get("GG", 0) >= 0.58 and _cota("GG") <= 1.75:
            gg.append(_creaza_selectie("GG"))

    return {
        "sigur": sigur,
        "goluri": goluri,
        "scor_echipe": scor_echipe,
        "gg": gg,
    }


def verifica_ligi_active(
    surse: list[tuple[str, str | int]], zile_inainte: int = 7
) -> list[dict]:
    rezultate = []
    azi = date.today()
    data_max = azi + timedelta(days=zile_inainte)

    for tip, ident in surse:
        try:
            if tip == "rapidapi":
                meciuri = data_source.meciuri_liga(int(ident))
            else:
                meciuri = fdo.meciuri_competitie_toate(str(ident))

            viitoare = [
                m for m in meciuri
                if not m["terminat"] and m["data"] and azi <= m["data"] <= data_max
            ]
            rezultate.append({
                "tip": tip,
                "id": ident,
                "meciuri_viitoare": len(viitoare),
                "eroare": None,
            })
        except Exception as e:
            rezultate.append({
                "tip": tip,
                "id": ident,
                "meciuri_viitoare": 0,
                "eroare": str(e),
            })

    return rezultate
