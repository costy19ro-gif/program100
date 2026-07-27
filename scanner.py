"""
Scanner automat de bilete.

Cauta meciuri viitoare din DOUA surse — RapidAPI ('Free API Live Football
Data', ligi mici/mijlocii + Liga I) si football-data.org (~13 ligi mari,
dar cu status=SCHEDULED corect, fara problema de sezon vechi) — ruleaza
motorul Poisson/Dixon-Coles (pipeline.py) pe fiecare, si construieste
automat categoriile de bilet, dupa regulile lui Julien.

LIMITARI reale — de stiut inainte sa te bazezi pe rezultat:

1. Forma fiecarei echipe se calculeaza DOAR din meciurile aceleiasi
   competitii/sezon (indiferent de sursa). Nu avem acces la meciuri din
   cupe/alte competitii ale aceleiasi echipe — pentru echipe care joaca
   des si in alte competitii, forma calculata aici poate fi incompleta.

2. Prima repriza NU e disponibila (desi football-data.org o are in raspuns,
   n-o folosim inca) — categoria a fost scoasa complet din bilet.

3. "Data" meciurilor viitoare vine doar ca zi (fara ora exacta afisata) —
   verifica ora reala pe surse oficiale inainte sa pariezi.

4. Cele doua surse au sisteme de ID-uri de echipa COMPLET separate — nu se
   amesteca niciodata (football-data.org e prefixat "fd:").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import data_source
import football_data_org as fdo
from pipeline import analizeaza_meci


@dataclass
class SelectieBilet:
    data: date
    echipa_gazda: str
    echipa_oaspete: str
    piata: str
    probabilitate: float
    cota: float


def _candidati_din_liga_rapidapi(league_id: int, zile_inainte: int, min_istoric: int = 5) -> list[dict]:
    """Meciurile viitoare dintr-o liga RapidAPI ('Free API Live Football Data'), cu piete calculate."""
    meciuri = data_source.meciuri_liga(league_id)

    azi = date.today()
    prag = azi + timedelta(days=zile_inainte)

    candidati = []
    for m in meciuri:
        if m["terminat"] or m["data"] is None:
            continue
        if not (azi <= m["data"] <= prag):
            continue

        istoric_gazda = data_source.istoric_echipa_din_liga(meciuri, m["echipa_gazda_id"], 20)
        istoric_oaspete = data_source.istoric_echipa_din_liga(meciuri, m["echipa_oaspete_id"], 20)
        if len(istoric_gazda) < min_istoric or len(istoric_oaspete) < min_istoric:
            continue

        rezultat = analizeaza_meci(istoric_gazda, istoric_oaspete)
        candidati.append({
            "data": m["data"],
            "echipa_gazda": m["echipa_gazda"],
            "echipa_oaspete": m["echipa_oaspete"],
            "piete": rezultat["piete"],
            "sursa": "rapidapi",
        })
    return candidati


def _candidati_din_competitie_fd(cod: str, zile_inainte: int, min_istoric: int = 5) -> list[dict]:
    """Meciurile viitoare dintr-o competitie football-data.org, cu piete calculate."""
    meciuri = fdo.meciuri_competitie_toate(cod)

    azi = date.today()
    prag = azi + timedelta(days=zile_inainte)

    candidati = []
    for m in meciuri:
        if m["terminat"] or m["data"] is None:
            continue
        if not (azi <= m["data"] <= prag):
            continue

        istoric_gazda = data_source.istoric_echipa_din_liga(meciuri, m["echipa_gazda_id"], 20)
        istoric_oaspete = data_source.istoric_echipa_din_liga(meciuri, m["echipa_oaspete_id"], 20)
        if len(istoric_gazda) < min_istoric or len(istoric_oaspete) < min_istoric:
            continue

        rezultat = analizeaza_meci(istoric_gazda, istoric_oaspete)
        candidati.append({
            "data": m["data"],
            "echipa_gazda": m["echipa_gazda"],
            "echipa_oaspete": m["echipa_oaspete"],
            "piete": rezultat["piete"],
            "sursa": "football_data",
        })
    return candidati


def verifica_ligi_active(surse: list[tuple], zile_inainte: int = 3) -> list[dict]:
    """
    Verificare rapida: pentru fiecare sursa, cate meciuri viitoare (neterminate)
    are in urmatoarele `zile_inainte` zile — FARA sa ruleze motorul Poisson
    (mult mai rapid decat scaneaza()). Acelasi format de tuplu ca la scaneaza().
    """
    azi = date.today()
    prag = azi + timedelta(days=zile_inainte)

    rezultate = []
    for tip, ident in surse:
        try:
            if tip == "rapidapi":
                meciuri = data_source.meciuri_liga(ident)
            elif tip == "football_data":
                meciuri = fdo.meciuri_competitie_toate(ident)
            else:
                continue
        except RuntimeError as e:
            rezultate.append({"tip": tip, "id": ident, "meciuri_viitoare": None, "eroare": str(e)})
            continue

        nr = sum(
            1 for m in meciuri
            if not m["terminat"] and m["data"] is not None and azi <= m["data"] <= prag
        )
        rezultate.append({"tip": tip, "id": ident, "meciuri_viitoare": nr, "eroare": None})
    return rezultate


def scaneaza(
    surse: list[tuple], zile_inainte: int = 3, min_istoric: int = 5,
    progres_callback=None,
) -> list[dict]:
    """
    Scaneaza toate sursele date, intoarce lista de candidati (meci + piete).

    `surse` e o lista de tupluri (tip_sursa, identificator):
      ("rapidapi", league_id)   -- ID numeric, din api_football/RapidAPI
      ("football_data", cod)    -- cod scurt, din football_data_org.py (ex. "PL")

    O sursa care esueaza (fara meciuri viitoare, eroare API, cota depasita
    etc.) nu opreste scanarea celorlalte.
    """
    toti = []
    for i, (tip, ident) in enumerate(surse):
        if progres_callback:
            progres_callback(i, len(surse), f"{tip}:{ident}")
        try:
            if tip == "rapidapi":
                toti.extend(_candidati_din_liga_rapidapi(ident, zile_inainte, min_istoric))
            elif tip == "football_data":
                toti.extend(_candidati_din_competitie_fd(ident, zile_inainte, min_istoric))
        except RuntimeError:
            continue
    return toti


PIETE_SIGURE = ["1", "X", "2", "1X", "X2"]
PIETE_GOLURI = ["Peste_1.5", "Peste_2.5", "Sub_3.5"]

NUME_PIATA = {
    "1": "1 (victorie gazdă)",
    "X": "X (egal)",
    "2": "2 (victorie oaspete)",
    "1X": "1X",
    "X2": "X2",
    "12": "12 (fără egal)",
    "Peste_1.5": "Peste 1.5 goluri",
    "Peste_2.5": "Peste 2.5 goluri",
    "Sub_3.5": "Sub 3.5 goluri",
    "Gazde_marcheaza": "Gazdele marchează",
    "Oaspeti_marcheaza": "Oaspeții marchează",
    "GG": "Ambele echipe marchează (GG)",
}


def construieste_bilete(
    candidati: list[dict], cota_min_sigur: float = 1.30, cota_max_sigur: float = 1.80,
) -> dict:
    """
    Categoriile de bilet, cate 2 selectii fiecare (cand sunt destule
    meciuri gasite). Un meci apare o singura data in tot biletul.

    Pentru "sigur": cota_min_sigur..cota_max_sigur — un interval, nu doar
    un prag minim. Fara plafon superior, algoritmul ar putea alege tehnic
    o piata care trece de 1.30 dar are de fapt cota 4-5 (nesigura), doar
    pentru ca restul pietelor acelui meci erau si mai proaste.
    """
    folosite = set()

    def _cheie(c):
        return (c["echipa_gazda"], c["echipa_oaspete"], c["data"])

    def _alege(cands, piete_permise, cota_min=1.0, cota_max=float("inf"), n=2):
        optiuni = []
        for c in cands:
            if _cheie(c) in folosite:
                continue
            for piata in piete_permise:
                prob = c["piete"].get(piata)
                if not prob or prob <= 0:
                    continue
                cota = 1 / prob
                if not (cota_min <= cota <= cota_max):
                    continue
                optiuni.append((cota, c, piata, prob))
        optiuni.sort(key=lambda x: x[0])  # cele mai sigure (cota mica) primele

        alese = []
        for cota, c, piata, prob in optiuni:
            if _cheie(c) in folosite:
                continue
            alese.append(SelectieBilet(
                data=c["data"], echipa_gazda=c["echipa_gazda"],
                echipa_oaspete=c["echipa_oaspete"], piata=piata,
                probabilitate=prob, cota=cota,
            ))
            folosite.add(_cheie(c))
            if len(alese) >= n:
                break
        return alese

    return {
        "sigur": _alege(candidati, PIETE_SIGURE, cota_min=cota_min_sigur, cota_max=cota_max_sigur, n=2),
        "goluri": _alege(candidati, PIETE_GOLURI, cota_min=1.0, cota_max=2.0, n=2),
        "scor_echipe": _alege(candidati, ["Gazde_marcheaza", "Oaspeti_marcheaza"], cota_min=1.0, cota_max=2.0, n=2),
        "gg": _alege(candidati, ["GG"], cota_min=1.0, cota_max=2.5, n=2),
    }
