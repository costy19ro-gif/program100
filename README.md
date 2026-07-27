# Miliardarul — BetMachine (unificat)

Aplicatie Streamlit cu doua motoare de analiza fotbal, intr-un singur loc:

1. **Motor principal — Poisson + Dixon-Coles** (`pipeline.py`), pe date reale
   trase din API-Football via RapidAPI (`data_source.py` → `api_football.py`).
2. **Semnal secundar — RandomForest** (`model_1x2.joblib`), folosit doar cand ai
   statistici reale per meci (xG, sut-uri, cornere) — nu completeaza niciodata
   automat cu valori inventate.

## Ce am reparat fata de fisierele originale

Proiectul asa cum a fost incarcat avea trei probleme care il impiedicau sa
porneasca deloc:

1. **`api_client.py` lipsea complet.** `api_football.py` facea
   `from api_client import RapidAPIClient`, dar fisierul nu exista — deci
   aplicatia pica la primul `import`. L-am creat (foloseste caching prin
   `cache.py`, ca sa nu arda cota gratuita).
2. **`data_source.py` si `api_football.py` nu se potriveau.** `data_source.py`
   apela `af.meciuri_azi()`, `af.istoric_echipa()`, `af.predictie_oficiala()`,
   dar `api_football.py` avea alte nume de functii, organizate ca o clasa.
   Am rescris `api_football.py` sa expuna exact functiile pe care le astepta
   `data_source.py`.
3. **`app.py` era o aplicatie complet separata**, fara nicio legatura cu
   `pipeline.py`/`data_source.py` — folosea un model RandomForest simplu si
   o cheie RapidAPI hardcodata (`INTRODU_CHEIA_TA_AICI`). L-am rescris ca sa
   uneasca ambele motoare in tab-uri, si am scos cheia hardcodata (acum vine
   din `secrets.toml`/variabila de mediu, ca restul proiectului).

Am scos si `football_api.py` din pachetul final — era un al treilea client
API, aproape identic cu `api_football.py`, dar neconectat la nimic. Pastrarea
lui ar fi creat aceeasi confuzie care a dus la problema #2.

## Instalare si rulare (local)

```bash
# 1. intra in folderul proiectului
cd miliardarul

# 2. (recomandat) mediu virtual
python3 -m venv .venv
source .venv/bin/activate      # pe Windows: .venv\Scripts\activate

# 3. instaleaza dependintele
pip install -r requirements.txt

# 4. configureaza cheia RapidAPI
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# deschide .streamlit/secrets.toml si pune cheia ta reala

# 5. porneste aplicatia
streamlit run app.py
```

Se va deschide automat in browser, de obicei la `http://localhost:8501`.

### Alternativa: variabila de mediu in loc de secrets.toml

```bash
export RAPIDAPI_KEY="cheia_ta"
streamlit run app.py
```

## Deploy pe Streamlit Community Cloud

1. Urca folderul pe un repo GitHub (fara `.streamlit/secrets.toml` — e deja
   in `.gitignore`, nu-l urca niciodata).
2. In Streamlit Cloud → Settings → Secrets, adauga:
   ```toml
   RAPIDAPI_KEY = "cheia_ta"
   ```
3. Deploy.

## Structura fisierelor

| Fisier | Rol |
|---|---|
| `pipeline.py` | Motorul matematic pur (Decay, Shrinkage, Dixon-Coles, scanner piete). Nu atinge reteaua. |
| `api_client.py` | Client HTTP generic pentru gateway-ul RapidAPI, cu cache. |
| `api_football.py` | Foloseste `api_client.py`, expune functiile de nivel inalt pentru `data_source.py`. |
| `data_source.py` | Strat de orchestrare — combina API-Football (principal) + RapidAPI bonus. |
| `rapidapi_predictions.py` | Client bonus optional (predictii externe, doar comparatie). |
| `cache.py` | Cache simplu in memorie, cu TTL. |
| `app.py` | Interfata Streamlit — tab motor Poisson, tab model rapid, tab Despre. |
| `model_1x2.joblib` | Modelul RandomForest antrenat (semnal secundar). |

## Cota zilnica (planuri gratuite)

API-Football/RapidAPI au limite pe planul gratuit. `api_client.py` cacheaza
raspunsurile 6 ore, ca sa nu consume cota degeaba la reincarcari repetate.
Daca vezi erori de tip "quota exceeded", asteapta resetarea zilnica sau
verifica planul din dashboard-ul RapidAPI.
