"""
Sursa de date reale: "Free API Live Football Data" (RapidAPI, host
free-api-live-football-data.p.rapidapi.com) — inlocuieste API-Football
clasic (api-sports), care nu mai e disponibil in marketplace-ul RapidAPI.

Structura raspunsului la /football-get-matches-by-date (confirmata din
raspuns real, nu presupusa):

{
  "status": "success",
  "response": {
    "matches": [
      {
        "id": 4621624,
        "leagueId": 894202,
        "time": "06.11.2024 21:00",      # format DD.MM.YYYY HH:MM
        "home": {"id": ..., "name": ..., "longName": ..., "score": ...},
        "away": {"id": ..., "name": ..., "longName": ..., "score": ...},
        "status": {
          "utcTime": "2024-11-06T20:00:00.000Z",
          "finished": true, "started": true, "cancelled": false,
          "scoreStr": "1 - 3",
          "reason": {"short": "FT", "long": "Full-Time"},
        },
        "timeTS": 1730923200000           # epoch ms
      },
      ...
    ]
  }
}

Important: parametrul `date` la acest endpoint e in format YYYYMMDD
(ex. "20241107"), NU "YYYY-MM-DD" ca la API-Football clasic.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from api_client import RapidAPIClient
from pipeline import MeciIstoric

_client: RapidAPIClient | None = None


def _get_client() -> RapidAPIClient:
    global _client
    if _client is None:
        _client = RapidAPIClient()
    return _client


def _parseaza_data_meci(time_str: str) -> date:
    """Converteste 'DD.MM.YYYY HH:MM' in date()."""
    return datetime.strptime(time_str, "%d.%m.%Y %H:%M").date()


def meciuri_pe_data(zi: date) -> list[dict]:
    """Meciurile programate/jucate intr-o zi anume."""
    raw = _get_client().get(
        "football-get-matches-by-date", {"date": zi.strftime("%Y%m%d")}
    )
    if raw.get("status") != "success":
        raise RuntimeError(f"API-ul a raspuns neasteptat: {raw}")

    matches = raw.get("response", {}).get("matches", [])
    meciuri = []
    for m in matches:
        status = m.get("status", {})
        meciuri.append({
            "fixture_id": m["id"],
            "league_id": m["leagueId"],
            "data": m["time"],
            "echipa_gazda": m["home"]["name"],
            "echipa_gazda_id": m["home"]["id"],
            "echipa_oaspete": m["away"]["name"],
            "echipa_oaspete_id": m["away"]["id"],
            "scor": status.get("scoreStr"),
            "status": status.get("reason", {}).get("short"),
            "terminat": status.get("finished", False),
        })
    return meciuri


def meciuri_pe_data_toate_ligile(zi: date) -> list[dict]:
    """
    Foloseste endpoint-ul global football-get-matches-by-date-and-league fara
    leagueid, care intoarce TOATE meciurile zilei din toate ligile active,
    grupate pe ligi, folosind ID-urile mici/de istoric de liga.
    """
    raw = _get_client().get(
        "football-get-matches-by-date-and-league", {"date": zi.strftime("%Y%m%d")}
    )
    if raw.get("status") != "success":
        raise RuntimeError(f"API-ul a raspuns neasteptat: {raw}")

    leagues_data = raw.get("response", {}).get("leagues", [])
    meciuri = []
    for l_item in leagues_data:
        league_id = l_item.get("id")
        matches = l_item.get("matches", [])
        for m in matches:
            status = m.get("status", {})
            utc = status.get("utcTime")
            data_meci = zi
            if utc:
                try:
                    data_meci = datetime.fromisoformat(utc.replace("Z", "+00:00")).date()
                except ValueError:
                    data_meci = zi

            home, away = m.get("home", {}), m.get("away", {})
            meciuri.append({
                "fixture_id": m.get("id"),
                "league_id": league_id,
                "data": data_meci,
                "echipa_gazda": home.get("name"),
                "echipa_gazda_id": str(home.get("id")),
                "echipa_oaspete": away.get("name"),
                "echipa_oaspete_id": str(away.get("id")),
                "gol_gazda": home.get("score"),
                "gol_oaspete": away.get("score"),
                "scor": status.get("scoreStr"),
                "status": status.get("reason", {}).get("short"),
                "terminat": bool(status.get("finished", False)),
            })
    return meciuri


def meciuri_interval(data_start: date, data_end: date) -> list[dict]:
    """Extrage toate meciurile dintr-un interval de date (zi cu zi)."""
    toate = []
    curr = data_start
    while curr <= data_end:
        toate.extend(meciuri_pe_data_toate_ligile(curr))
        curr += timedelta(days=1)
    return toate


def meciuri_azi() -> list[dict]:
    """Meciurile de azi (nume pastrat pentru compatibilitate cu data_source.py)."""
    return meciuri_pe_data(date.today())


def istoric_echipa(team_id: int, n_meciuri: int = 20):
    """DEPRECAT — pastrat doar ca sa nu sparga apeluri vechi."""
    raise RuntimeError(
        "istoric_echipa() e deprecat. Foloseste meciuri_liga(league_id) + "
        "istoric_echipa_din_liga(meciuri, team_id)."
    )


def leagues_cu_tari() -> list[dict]:
    """Toate tarile + ligile lor, cu ID-urile folosite de meciuri_liga()."""
    raw = _get_client().get("football-get-all-leagues-with-countries")
    if raw.get("status") != "success":
        raise RuntimeError(f"API-ul a raspuns neasteptat la lista de ligi: {raw}")
    return raw.get("response", {}).get("leagues", [])


def meciuri_liga(league_id: int) -> list[dict]:
    """Toate meciurile disponibile pentru o liga (sezonul curent/recent)."""
    raw = _get_client().get(
        "football-get-all-matches-by-league", {"leagueid": league_id}
    )
    if raw.get("status") != "success":
        raise RuntimeError(f"API-ul a raspuns cu eroare pentru liga {league_id}: {raw}")

    matches = raw.get("response", {}).get("matches", [])
    meciuri = []
    for m in matches:
        status = m.get("status", {})
        utc = status.get("utcTime")
        data_meci = None
        if utc:
            try:
                data_meci = datetime.fromisoformat(utc.replace("Z", "+00:00")).date()
            except ValueError:
                data_meci = None

        home, away = m.get("home", {}), m.get("away", {})
        meciuri.append({
            "fixture_id": m.get("id"),
            "data": data_meci,
            "echipa_gazda": home.get("name"),
            "echipa_gazda_id": str(home.get("id")),
            "echipa_oaspete": away.get("name"),
            "echipa_oaspete_id": str(away.get("id")),
            "gol_gazda": home.get("score"),
            "gol_oaspete": away.get("score"),
            "scor": status.get("scoreStr"),
            "status": status.get("reason", {}).get("short"),
            "terminat": bool(status.get("finished", False)),
        })
    return meciuri


def istoric_echipa_din_liga(
    meciuri: list[dict], team_id: str, n_meciuri: int = 20
) -> list[MeciIstoric]:
    """Extrage istoricul unei echipe din lista de meciuri transmisa."""
    team_id = str(team_id)
    istoric = []
    for m in meciuri:
        if not m["terminat"] or m["data"] is None:
            continue
        if m["gol_gazda"] is None or m["gol_oaspete"] is None:
            continue

        e_gazda = m["echipa_gazda_id"] == team_id
        e_oaspete = m["echipa_oaspete_id"] == team_id
        if not (e_gazda or e_oaspete):
            continue

        goluri_marcate = m["gol_gazda"] if e_gazda else m["gol_oaspete"]
        goluri_primite = m["gol_oaspete"] if e_gazda else m["gol_gazda"]
        istoric.append(MeciIstoric(
            data=m["data"],
            goluri_marcate=goluri_marcate,
            goluri_primite=goluri_primite,
        ))

    istoric.sort(key=lambda mi: mi.data, reverse=True)
    return istoric[:n_meciuri]


def predictie_oficiala(fixture_id: int) -> dict | None:
    return None
