import pandas as pd
import soccerdata as sd
import logging
# Importă funcțiile tale curente din api_football
import api_football as af 

logger = logging.getLogger(__name__)

def obtine_meciuri_zi_fallback(league="ENG-Premier League", season="24-25"):
    """
    Încearcă să aducă meciurile zilei din API-Football (RapidAPI).
    Dacă limita zilnică a expirat, comută automat pe soccerdata (FBref).
    """
    try:
        logger.info("Se încearcă preluarea datelor din API-Football...")
        # Apelul tău original către API-ul bazat pe cheie token
        meciuri = af.meciuri_azi() 
        return meciuri
        
    except Exception as e:
        # Prinde eroarea de „Quota Exceeded” sau orice problemă de rețea RapidAPI
        if "quota" in str(e).lower() or "429" in str(e):
            logger.warning("Cota zilnică RapidAPI a fost depășită! Se activează fallback-ul pe SoccerData (FBref)...")
            return _incarca_date_din_soccerdata(league, season)
        else:
            # Dacă este altă eroare (ex: sintaxă), o dă mai departe
            raise e

def _incarca_date_din_soccerdata(league, season):
    """
    Funcție internă care folosește web scraping prin soccerdata ca soluție gratuită.
    """
    try:
        # Inițializează scraper-ul FBref pentru liga și sezonul curent
        # Exemplu format ligi în soccerdata: 'ENG-Premier League', 'ITA-Serie A', 'ESP-La Liga'
        fbref = sd.FBref(leagues=league, seasons=season)
        
        # Deschide programul/meciurile (read_schedule returnează un Pandas DataFrame)
        schedule_df = fbref.read_schedule()
        
        # Filtrează doar meciurile de azi (FBref oferă tot sezonul, deci le filtrăm local)
        azi = pd.Timestamp.now().strftime('%Y-%m-%d')
        
        # Resetăm indexul pentru a manipula coloanele mai ușor în Streamlit
        schedule_df = schedule_df.reset_index()
        
        meciuri_azi = schedule_df[schedule_df['date'] == azi]
        
        if meciuri_azi.empty:
            logger.info(f"Niciun meci programat azi în {league} conform FBref.")
            return []
            
        # Aliniem structura DataFrame-ului la formatul pe care app.py îl așteaptă deja
        # Înlocuiește cheile de mai jos cu structura exactă folosită în interfața ta Streamlit
        meciuri_formatate = []
        for _, row in meciuri_azi.iterrows():
            meciuri_formatate.append({
                "home_team": row['home_team'],
                "away_team": row['away_team'],
                "status": "Programat",
                "sursa": "SoccerData (Fallback)"
            })
            
        return meciuri_formatate

    except Exception as sd_error:
        logger.error(f"A eșuat și fallback-ul pe SoccerData: {sd_error}")
        return []
