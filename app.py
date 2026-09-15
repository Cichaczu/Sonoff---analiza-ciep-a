import streamlit as st
import pandas as pd
import plotly.graph_objects as px_go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date, datetime, timedelta
import requests
import time

# ---------------------------------------------------------
# KONFIGURACJA STRONY I PARAMETRÓW BAZOWYCH
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Dynamic Analytics",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
APARTMENT_AREA_M2 = 66.54  # Dokładna powierzchnia lokalu

# Parametry Spółdzielni Mieszkaniowej (SSM)
SSM_CO_MONTHLY_ADVANCE = 774.53  
SSM_NON_HEATING_RENT = 1121.87   
SSM_TOTAL_MONTHLY_RENT = 1896.40 
SSM_SEASON_MONTHS = 7            
SSM_TOTAL_WEEKS = 30             
SSM_ANNUAL_CO_BUDGET = SSM_CO_MONTHLY_ADVANCE * SSM_SEASON_MONTHS  

# Lokalizacja: Bytków, ul. Związku Harcerstwa Polskiego 3
LAT_LOCATION = 50.3168
LON_LOCATION = 18.9839
LOCATION_NAME = "Siemianowice Śl. - Bytków (ul. Związku Harcerstwa Polskiego 3)"

# ---------------------------------------------------------
# POBIERANIE POGODY Z MECHANIZMEM REDUNDANCJI (API)
# ---------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_outdoor_temp():
    api_key = st.secrets.get("openweathermap", {}).get("api_key", "")
    if not api_key and "custom_owm_key" in st.session_state:
        api_key = st.session_state["custom_owm_key"]
        
    if api_key:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT_LOCATION}&lon={LON_LOCATION}&appid={api_key}&units=metric"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                return float(res.json()['main']['temp'])
        except Exception:
            pass

    try:
        url_fallback = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_LOCATION}&longitude={LON_LOCATION}&current=temperature_2m"
        res = requests.get(url_fallback, timeout=3)
        if res.status_code == 200:
            return float(res.json()['current']['temperature_2m'])
    except Exception:
        pass
        
    return 12.5

@st.cache_data(ttl=300, show_spinner=False)
def get_weather_forecast():
    try:
        url_f_fallback = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_LOCATION}&longitude={LON_LOCATION}&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
        res = requests.get(url_f_fallback, timeout=4)
        if res.status_code == 200:
            data = res.json().get("daily", {})
            dates = data.get("time", [])
            t_max = data.get("temperature_2m_max", [])
            t_min = data.get("temperature_2m_min", [])
            forecasts = []
            for i in range(min(7, len(dates))):
                avg_t = (t_max[i] + t_min[i]) / 2.0
                forecasts.append({
                    "date": dates[i],
                    "temp": avg_t,
                    "desc": "Prognoza Open-Meteo",
                    "icon": "01d"
                })
            return forecasts
    except Exception:
        pass
    return []

# ---------------------------------------------------------
# ZARZĄDZANIE DANYMI I GITHUB SYNC
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "device_id": "11420", "meter_default": "503 754 417", "units_start": 1509.0, "share": 0.45},
    "Dzieciaki": {"icon": "🧒", "device_id": "11420", "meter_default": "503 754 240", "units_start": 1104.0, "share": 0.30},
    "Sypialnia": {"icon": "🛏️", "device_id": "11420", "meter_default": "503 754 493", "units_start": 1267.0, "share": 0.25},
    "Licznik Główny": {"icon": "🏢", "device_id": "-", "meter_default": "GJ-MAIN-2026", "units_start": 0.0, "share": 1.0}
}

MODES = ["Standard (Automatyczny)", "Eco / Redukcja niska", "Nieobecność domowników", "Intensywne grzanie"]

def get_github_repo():
    try:
        github_config = st.secrets.get("github", {})
        token = github_config.get("token")
        repo_name = github_config.get("repo")
        if token and repo_name:
            return Github(token).get_repo(repo_name)
    except Exception:
        return None
    return None

def load_data():
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            return pd.read_csv(io.StringIO(file_content.decoded_content.decode('utf-8')))
        except Exception:
            pass
    if os.path.exists(FILE_PATH):
        try:
            return pd.read_csv(FILE_PATH)
        except Exception:
            pass
    return pd.DataFrame()

def save_data(df, commit_message="Aktualizacja odczytu"):
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    csv_string = df.to_csv(index=False)
    success = False
    
    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(FILE_PATH, commit_message, csv_string, file_content.sha, branch=branch)
            except Exception:
                repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
            success = True
        except Exception:
            success = False
            
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    df.to_csv(FILE_PATH, index=False)
    st.cache_data.clear()
    return True

df = load_data()

# ---------------------------------------------------------
# INTERFEJS GŁÓWNY I KONTROLA STANU
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

current_room = st.session_state["selected_room"]
if current_room not in ROOMS_CONFIG:
    current_room = "Salon"
    st.session_state["selected_room"] = current_room

st.title("🔥 Sonoff Smart Heating - Panel Sterowania")
st.caption(f"Lokalizacja: **{LOCATION_NAME}**")

# Wybór strefy (zakładki kafelkowe)
room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (current_room == room_key)
    with room_cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"room_tab_{room_key}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state["selected_room"] = room_key
            st.rerun()

st.divider()
st.info(f"Aktywna strefa robocza: **{current_room}**. System gotowy do wdrożenia w środowisku docelowym.")
