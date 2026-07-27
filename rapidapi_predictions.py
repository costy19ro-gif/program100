"""
Client BONUS pentru RapidAPI "Sports Betting Predictions" (tipstar)
=====================================================================
ATENTIE: endpoint-ul exact (path + parametri) NU a putut fi confirmat
automat din documentatia RapidAPI (pagina e randata prin JavaScript).
Acest modul e OPTIONAL — daca esueaza sau nu e configurat, aplicatia
principala (API-Football + pipeline Poisson) continua sa functioneze
normal, fara nicio eroare vizibila pentru tine.

CUM COMPLETEZI CORECT (5 minute):
1. Intra pe https://rapidapi.com/tipstar/api/sports-betting-predictions/playground/...
2. In stanga, alege endpoint-ul dorit (ex. "Today Predictions" / "Predictions by date").
3. In panoul "Code Snippets" din dreapta, alege limbajul Python.
4. Copiaza EXACT:
   - path-ul din URL (dupa domeniu, ex: "/predictions/today")
   - parametrii folositi in exemplu (ex: {"date": "2026-07-06"})
   - numele host-ului din header-ul X-RapidAPI-Host (daca difera de cel de jos)
5. Inlocuieste ENDPOINT_PATH si HOST mai jos cu valorile reale.

Pana completezi asta, functia predictii_bonus() returneaza None automat
(cheia RapidAPI e valida si salvata, dar endpoint-ul e inca un placeholder).
"""

from __future__ import annotations
import os
import requests

BASE_URL = "https://sports-betting-predictions.p.rapidapi.com"
HOST = "sports-betting-predictions.p.rapidapi.com"

# TODO: inlocuieste cu path-ul REAL copiat din "Code Snippets" (Python) de pe RapidAPI
ENDPOINT_PATH = None  # ex: "/predictions/today"


def _get_key() -> str | None:
    try:
        import streamlit as st
        if "RAPIDAPI_KEY" in st.secrets:
            return st.secrets["RAPIDAPI_KEY"]
    except Exception:
        pass
    return os.environ.get("RAPIDAPI_KEY")


def predictii_bonus(params: dict | None = None) -> list[dict] | None:
    """
    Returneaza predictiile brute de la tipstar API, sau None daca:
    - cheia lipseste
    - endpoint-ul (ENDPOINT_PATH) nu a fost inca completat
    - apelul esueaza din orice motiv

    Aplicatia principala NU depinde de acest apel — e doar un bonus
    de comparatie afisat intr-o sectiune separata daca functioneaza.
    """
    if not ENDPOINT_PATH:
        return None

    api_key = _get_key()
    if not api_key:
        return None

    headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": HOST}
    try:
        resp = requests.get(f"{BASE_URL}{ENDPOINT_PATH}", headers=headers, params=params or {}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("data") or data.get("response") or [data]
    except Exception:
        return None
