"""
Sursa de date reale — orchestreaza API-Football si predictiile bonus.
"""

from __future__ import annotations

from datetime import date
import api_football as af
import rapidapi_predictions as rp
from pipeline import MeciIstoric


def meciuri_azi() -> list[dict]:
    """Meciurile programate azi (sursa: API-Football)."""
    return af.meciuri_azi()


def meciuri_pe_data_toate_ligile(zi: date) -> list[dict]:
    """Meciurile dintr-o zi din toate ligile (API-Football)."""
    return af.meciuri_pe_data_toate_ligile(zi)


def meciuri_interval(data_start: date, data_end: date) -> list[dict]:
    """Meciurile dintr-un interval de date (API-Football)."""
    return af.meciuri_interval(data_start, data_end)


def istoric_echipa(team_id: int, n_meciuri: int = 20) -> list[MeciIstoric]:
    """Ultimele n_meciuri TERMINATE ale unei echipe."""
    return af.istoric_echipa(team_id, n_meciuri)


def predictie_oficiala(fixture_id: int) -> dict | None:
    """Bonus: predictia proprie API-Football pentru acest meci."""
    return af.predictie_oficiala(fixture_id)


def leagues_cu_tari() -> list[dict]:
    """Toate tarile + ligile lor (sistem de ID-uri pt. meciuri_liga)."""
    return af.leagues_cu_tari()


def meciuri_liga(league_id: int) -> list[dict]:
    """Toate meciurile unei ligi, un singur apel."""
    return af.meciuri_liga(league_id)


def istoric_echipa_din_liga(meciuri: list[dict], team_id: str, n_meciuri: int = 20):
    """Istoricul unei echipe, extras local (fara retea)."""
    return af.istoric_echipa_din_liga(meciuri, team_id, n_meciuri)


def predictii_bonus_rapidapi(params: dict | None = None) -> list[dict] | None:
    """Bonus: predictiile RapidAPI/tipstar."""
    return rp.predictii_bonus(params)
