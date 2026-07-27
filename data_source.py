"""
Sursa de date reale — orchestreaza API-Football (sursa PRINCIPALA, sigura si
documentata) si, optional, predictiile bonus de pe RapidAPI (tipstar).

De ce am schimbat sursa principala: vechiul client (SportAPI7 via RapidAPI)
avea endpoint-ul de istoric echipa neconfirmat ("model uzual, verifica").
API-Football e documentat oficial si folosim aceeasi cheie pe care o ai deja
de la dashboard.api-football.com.

Functiile de mai jos pastreaza EXACT aceleasi nume/semnaturi pe care le
apela deja app.py, deci restul aplicatiei nu trebuie schimbat.
"""

from __future__ import annotations

import api_football as af
import rapidapi_predictions as rp
from pipeline import MeciIstoric


def meciuri_azi() -> list[dict]:
    """Meciurile programate azi (sursa: API-Football)."""
    return af.meciuri_azi()


def istoric_echipa(team_id: int, n_meciuri: int = 20) -> list[MeciIstoric]:
    """Ultimele n_meciuri TERMINATE ale unei echipe (sursa: API-Football)."""
    return af.istoric_echipa(team_id, n_meciuri)


def predictie_oficiala(fixture_id: int) -> dict | None:
    """Bonus: predictia proprie API-Football pentru acest meci (comparatie)."""
    return af.predictie_oficiala(fixture_id)


def leagues_cu_tari() -> list[dict]:
    """Toate tarile + ligile lor (sistem de ID-uri pt. meciuri_liga)."""
    return af.leagues_cu_tari()


def meciuri_liga(league_id: int) -> list[dict]:
    """Toate meciurile unei ligi (sezon curent/recent), un singur apel."""
    return af.meciuri_liga(league_id)


def istoric_echipa_din_liga(meciuri: list[dict], team_id: str, n_meciuri: int = 20):
    """Istoricul unei echipe, extras local din meciuri_liga() (fara retea)."""
    return af.istoric_echipa_din_liga(meciuri, team_id, n_meciuri)


def predictii_bonus_rapidapi(params: dict | None = None) -> list[dict] | None:
    """Bonus: predictiile RapidAPI/tipstar, daca endpoint-ul e configurat (vezi rapidapi_predictions.py)."""
    return rp.predictii_bonus(params)
