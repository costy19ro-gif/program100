"""
Client HTTP generic pentru API-uri de fotbal, rutat prin gateway-ul RapidAPI.

Nu presupune un format anume de raspuns (fiecare API de pe RapidAPI are
alta structura JSON) — intoarce raspunsul brut, parsat, si lasa modulul
specific (api_football.py) sa-l interpreteze.

Host-ul curent: free-api-live-football-data.p.rapidapi.com
(API-Football clasic, de la api-sports, nu mai e disponibil pe RapidAPI —
a fost inlocuit dupa ce cautarile repetate nu l-au mai gasit in marketplace.)

Cheia se ia, in ordine:
1. st.secrets["RAPIDAPI_KEY"]           (recomandat pe Streamlit Cloud)
2. variabila de mediu RAPIDAPI_KEY       (recomandat local)
"""

from __future__ import annotations

import os
import requests

from cache import SimpleCache

HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{HOST}"

# cache pe disc/memorie, 6 ore — vezi README, planurile gratuite au cota mica
_cache = SimpleCache(ttl=6 * 3600)


def _get_key() -> str | None:
    try:
        import streamlit as st
        if "RAPIDAPI_KEY" in st.secrets:
            return st.secrets["RAPIDAPI_KEY"]
    except Exception:
        pass
    return os.environ.get("RAPIDAPI_KEY")


class RapidAPIClient:
    """Wrapper subtire peste requests, cu headerele corecte pt. gateway-ul RapidAPI."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _get_key()
        if not self.api_key:
            raise RuntimeError(
                "Lipseste RAPIDAPI_KEY. Adauga-l in .streamlit/secrets.toml "
                '(RAPIDAPI_KEY = "cheia_ta") sau ca variabila de mediu:\n'
                "  export RAPIDAPI_KEY=cheia_ta"
            )
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": HOST,
        }

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """Intoarce JSON-ul brut, parsat (dict). Interpretarea structurii
        (ex. raw['response']['matches']) e responsabilitatea apelantului,
        pentru ca difera de la un API la altul."""
        cache_key = f"{endpoint}?{sorted((params or {}).items())}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{BASE_URL}/{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params or {}, timeout=15)

        # Prindem eroarea HTTP noi insine si aratam cauza reala (fara cheie),
        # in loc sa lasam exceptia bruta sa urce pana la Streamlit — care
        # redacteaza mesajul original ("This app has encountered an error...")
        # si nu mai vezi de fapt DE CE a picat cererea.
        if resp.status_code == 401:
            raise RuntimeError(
                "RapidAPI a raspuns 401 Unauthorized — cheia RAPIDAPI_KEY este "
                "gresita sau nu e trimisa corect. Verifica in Settings -> Secrets."
            )
        if resp.status_code == 403:
            raise RuntimeError(
                "RapidAPI a raspuns 403 Forbidden — cheia ta nu e abonata la "
                f"acest API ({HOST}). Verifica pe rapidapi.com daca esti "
                "abonat (butonul 'Subscribe')."
            )
        if resp.status_code == 429:
            raise RuntimeError(
                "RapidAPI a raspuns 429 Too Many Requests — ai depasit cota "
                "zilnica/lunara de pe planul curent. Asteapta resetarea sau "
                "verifica planul din dashboard-ul RapidAPI."
            )
        if not resp.ok:
            raise RuntimeError(
                f"RapidAPI a raspuns cu eroare HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        _cache.set(cache_key, data)
        return data
