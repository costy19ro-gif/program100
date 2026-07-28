import logging
import pandas as pd
import soccerdata as sd
import api_football as af  # Clientul tău original pentru API-Football / RapidAPI

logger = logging.getLogger(__name__)

def leagues_cu_tari():
    """
    Punct de intrare pentru app.py (Linia 60). 
    Încearcă să aducă ligile din API-Football. Dacă cota a expirat, 
    returnează o structură compatibilă bazată pe ligile suportate de SoccerData.
    """
    try:
        logger.info("Se încarcă ligile din API-Football...")
        return af.leagues_cu_tari()
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            logger.warning("Cota RapidAPI a expirat la încărcarea ligilor! Activare fallback SoccerData...")
            
            # Returnăm o structură identică cu cea din API-Football pentru ca app.py să nu dea eroare
            return [
                {
                    "name": "Anglia",
                    "leagues": [{"name": "Premier League", "id": "ENG-Premier League"}]
                },
                {
                    "name": "Spania",
                    "leagues": [{"name": "La Liga", "id": "ESP-La Liga"}]
                },
                {
                    "name": "Italia",
                    "leagues": [{"name": "Serie A", "id": "ITA-Serie A"}]
                },
                {
                    "name": "Germania",
                    "leagues": [{"name": "Bundesliga", "id": "GER-Bundesliga"}]
                },
                {
                    "name": "Franta",
                    "leagues": [{"name": "Ligue 1", "id": "FRA-Ligue 1"}]
                }
            ]
        else:
            raise e

def meciuri_liga(league_id):
    """
    Aduce meciurile pentru liga selectată (Afișate la linia 77 în app.py).
    Dacă league_id este un string (ex: 'ENG-Premier League'), știe că provine din fallback-ul SoccerData.
    """
    # Verificăm dacă league_id este ID numeric (API-Football) sau text (SoccerData)
    if isinstance(league_id, str) and "-" in league_id:
        logger.info(f"Se folosește direct SoccerData (FBref) pentru liga: {league_id}")
        return _incarca_meciuri_din_soccerdata(league_id)
        
    try:
        return af.meciuri_liga(league_id)
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            logger.warning("Cota RapidAPI a expirat la încărcarea meciurilor! Încercăm conversia ID-ului pentru SoccerData...")
            # Mapare rapidă în cazul în care utilizatorul apucase să încarce ID-uri numerice înainte ca cota să expire
            mapare_id_ligi = {
                39: "ENG-Premier League",
                140: "ESP-La Liga",
                135: "ITA-Serie A",
                78: "GER-Bundesliga",
                61: "FRA-Ligue 1"
            }
            soccerdata_id = mapare_id_ligi.get(league_id, "ENG-Premier League")
            return _incarca_meciuri_din_soccerdata(soccerdata_id)
        else:
            raise e

def _incarca_meciuri_din_soccerdata(league_id, season="24-25"):
    """
    Descarcă meciurile dintr-un anumit sezon (ex: '24-25' sau '23-24') 
    folosind pachetul soccerdata (sursa FBref).
    """
    try:
        # soccerdata acceptă formate ca '24-25' sau '2024-2025'
        fbref = sd.FBref(leagues=league_id, seasons=season)
        schedule_df = fbref.read_schedule().reset_index()
        
        meciuri_formatate = []
        for idx, row in schedule_df.iterrows():
            meciuri_formatate.append({
                "echipa_gazda": row['home_team'],
                "echipa_gazda_id": row['home_team'],  # ID-ul devine numele echipei pentru aliniere text
                "echipa_oaspete": row['away_team'],
                "echipa_oaspete_id": row['away_team'],
                # Conversie sigură în float/int pentru scoruri istorice
                "goals_home": int(row['home_score']) if pd.notna(row['home_score']) else None,
                "goals_away": int(row['away_score']) if pd.notna(row['away_score']) else None,
                "status": "Match Finished" if pd.notna(row['home_score']) else "Not Started"
            })
        return meciuri_formatate
    except Exception as es:
        print(f"Eroare la citirea meciurilor istorice prin soccerdata: {es}")
        return []
def istoric_echipa_din_liga(meciuri_liga, echipa_id, n_meciuri):
    """
    Filtrează istoricul meciurilor dintr-o listă deja încărcată.
    Păstrează neschimbată logica din aplicația ta.
    """
    # Dacă datele vin din API-Football, filtrarea se face pe ID, altfel pe nume (string)
    meciuri_terminate = [m for m in meciuri_liga if m["status"] in ["Match Finished", "FT", "AET"]]
    
    istoric = []
    for m in meciuri_terminate:
        if m["echipa_gazda_id"] == echipa_id or m["echipa_oaspete_id"] == echipa_id:
            istoric.append(m)
            
    # Returnează ultimele n meciuri jucate
    return istoric[-n_meciuri:]
def obtine_status_api():
    """
    Verifică starea creditelor pe serverul RapidAPI (API-Football).
    Returnează un string formatat cu limita curentă.
    """
    try:
        response = af.requests.get(url=af.apifootball_url + "status", headers=af.headers).json()
        curent = response['response']['requests']['current']
        limita = response['response']['requests']['limit_day']
        return f"📊 Credite API folosite azi: {curent} / {limita}"
    except Exception:
        return "⚠️ Status API indisponibil (Se rulează pe modul Fallback/SoccerData)"
