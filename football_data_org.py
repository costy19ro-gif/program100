"""
Sursa SECUNDARA de date: football-data.org (API v4).

De ce o a doua sursa: RapidAPI ("Free API Live Football Data") are meciurile
Ligii I dar e blocat pe sezonul vechi (2025/2026) — vezi discutia din README.
football-data.org marcheaza corect meciurile viitoare cu status=SCHEDULED,
dar in schimb planul gratuit acopera doar ~13 competitii mari (nu si Liga I).
Folosim ambele, fiecare acoperind ce-i lipseste celeilalte.

Cont si token: separat de RapidAPI — cont propriu pe football-data.org.
Plan gratuit: ~10 cereri/minut.

IMPORTANT: ID-urile de echipa de aici (din campul 'id' al football-data.org)
sunt intr-un sistem COMPLET SEPARAT de cele din api_football.py — de-aia le
prefixam cu "fd:" in echipa_gazda_id/echipa_oaspete_id, ca sa nu se amestece
niciodata accidental cu ID-uri din cealalta sursa.
"""

from __future__ import annotations

import os
from datetime import datetime

import requests

BASE_URL = "https://api.football-data.org/v4"

# Competitiile acoperite de planul gratuit (cod -> eticheta afisata).
# Lista fixa — nu are rost sa cerem /v4/competitions doar ca sa filtram,
# cand planul gratuit oricum limiteaza la astea.
COMPETITII_GRATUITE = {
    "PL": "Anglia — Premier League",
    "PD": "Spania — La Liga",
    "BL1": "Germania — Bundesliga",
    "SA": "Italia — Serie A",
    "FL1": "Franta — Ligue 1",
    "DED": "Olanda — Eredivisie",
    "PPL": "Portugalia — Primeira Liga",
    "ELC": "Anglia — Championship",
    "CL": "UEFA Champions League",
    "EC": "Campionatul European",
    "WC": "Campionatul Mondial",
    "CLI": "Copa Libertadores",
    "BSA": "Brazilia — Serie A",
}


def _get_token() -> str | None:
    try:
        import streamlit as st
        if "FOOTBALL_DATA_TOKEN" in st.secrets:
            return st.secrets["FOOTBALL_DATA_TOKEN"]
    except Exception:
        pass
    return os.environ.get("FOOTBALL_DATA_TOKEN")


def _get(endpoint: str, params: dict | None = None) -> dict:
    token = _get_token()
    if not token:
        raise RuntimeError(
            "Lipseste FOOTBALL_DATA_TOKEN. Adauga-l in .streamlit/secrets.toml "
            '(FOOTBALL_DATA_TOKEN = "cheia_ta") sau ca variabila de mediu.'
        )
    resp = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={"X-Auth-Token": token},
        params=params or {},
        timeout=15,
    )
    if resp.status_code == 429:
        raise RuntimeError(
            "football-data.org: 429 Too Many Requests — planul gratuit permite "
            "~10 cereri/minut. Asteapta putin si incearca din nou."
        )
    if resp.status_code == 403:
        raise RuntimeError(
            "football-data.org: 403 Forbidden — competitia asta nu e in planul "
            "gratuit, sau FOOTBALL_DATA_TOKEN e gresit."
        )
    if not resp.ok:
        raise RuntimeError(
            f"football-data.org a raspuns cu eroare HTTP {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


def _normalizeaza_meciuri(raw_matches: list[dict]) -> list[dict]:
    """Converteste raspunsul brut in acelasi format ca meciuri_liga() din
    api_football.py, ca sa poata fi combinate in acelasi scanner si sa
    foloseasca aceeasi functie istoric_echipa_din_liga()."""
    meciuri = []
    for m in raw_matches:
        utc = m.get("utcDate")
        data_meci = None
        if utc:
            try:
                data_meci = datetime.fromisoformat(utc.replace("Z", "+00:00")).date()
            except ValueError:
                data_meci = None

        ft = (m.get("score") or {}).get("fullTime") or {}
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        gol_gazda, gol_oaspete = ft.get("home"), ft.get("away")

        meciuri.append({
            "fixture_id": m.get("id"),
            "data": data_meci,
            "echipa_gazda": home.get("name"),
            "echipa_gazda_id": f"fd:{home.get('id')}",
            "echipa_oaspete": away.get("name"),
            "echipa_oaspete_id": f"fd:{away.get('id')}",
            "gol_gazda": gol_gazda,
            "gol_oaspete": gol_oaspete,
            "scor": f"{gol_gazda} - {gol_oaspete}" if gol_gazda is not None else None,
            "status": m.get("status"),
            "terminat": m.get("status") == "FINISHED",
        })
    return meciuri


def meciuri_competitie(cod: str, status: str = "SCHEDULED") -> list[dict]:
    """Meciuri dintr-o competitie, filtrate dupa status (SCHEDULED/FINISHED/...)."""
    raw = _get(f"competitions/{cod}/matches", {"status": status})
    return _normalizeaza_meciuri(raw.get("matches", []))


def meciuri_competitie_toate(cod: str) -> list[dict]:
    """Meciurile TERMINATE + VIITOARE ale sezonului curent, combinate — sursa
    unica pentru afisare si pentru calculul istoricului per echipa. Costa 2
    cereri (planul gratuit permite ~10/minut, deci e in regula)."""
    terminate = meciuri_competitie(cod, status="FINISHED")
    viitoare = meciuri_competitie(cod, status="SCHEDULED")
    return terminate + viitoare
