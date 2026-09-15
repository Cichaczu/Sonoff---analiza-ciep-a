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
from PIL import Image

# ---------------------------------------------------------
# KONFIGURACJA STRONY I LOKALIZACJI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Dynamic Analytics",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
APARTMENT_AREA_M2 = 66.54  # Dokładna powierzchnia lokalu

# Oficjalne dane ze Spółdzielni (SSM) dla lokalu 66,54 m²
SSM_CO_MONTHLY_ADVANCE = 774.53  # Zaliczka miesięczna CO (11.64 zł / m²)
SSM_NON_HEATING_RENT = 1121.87   # Opłaty stałe (eksploatacja, woda itp.)
SSM_TOTAL_MONTHLY_RENT = 1896.40 # Całkowity miesięczny czynsz do SSM

SSM_SEASON_MONTHS = 7            # Sezon grzewczy
SSM_TOTAL_WEEKS = 30             # Przybliżona liczba tygodni w sezonie
SSM_ANNUAL_CO_BUDGET = SSM_CO_MONTHLY_ADVANCE * SSM_SEASON_MONTHS  # Całkowity budżet zaliczkowy CO

# Precyzyjne współrzędne dla: Siemianowice Śląskie, Bytków, ul. Związku Harcerstwa Polskiego 3
LAT_LOCATION = 50.3168
LON_LOCATION = 18.9839
LOCATION_NAME = "Siemianowice Śl. - Bytków (ul. Związku Harcerstwa Polskiego 3)"

# ---------------------------------------------------------
# MODUŁ OCR (ROZPOZNAWANIE STANU LICZNIKA ZE ZDJĘCIA - PILLOW)
# ---------------------------------------------------------
def process_meter_ocr(image_file, fallback_value):
    """
    UWAGA: To jest tylko SZKIELET pod przyszłą integrację z prawdziwym silnikiem
    OCR / Vision API. Obecnie NIE odczytuje realnej wartości z obrazu - Pillow
    jest tu użyte wyłącznie do walidacji, że plik to poprawny obraz (dekodowanie
    + konwersja do skali szarości). Zwracamy `fallback_value` (czyli ostatni
    znany stan licznika danej strefy), żeby formularz miał sensowny punkt
    startowy do ręcznej korekty przez użytkownika, zamiast podstawiać stałą,
    nierealną liczbę (np. 1514.5) niezależną od wybranej strefy.

    Gdy podłączysz prawdziwe API (np. Google Vision / Tesseract), podmień
    blok poniżej na faktyczne rozpoznawanie cyfr z obrazu.
    """
    try:
        bytes_data = image_file.getvalue()
        image = Image.open(io.BytesIO(bytes_data))

        # Konwersja do skali szarości w celu optymalizacji analizy kontrastu cyfr
        gray_image = image.convert('L')
        _ = gray_image.size  # walidacja, że obraz został poprawnie zdekodowany

        # Brak realnego silnika OCR - zwracamy fallback i jasno o tym informujemy
        return False, float(fallback_value), (
            "Obraz wczytany poprawnie, ale automatyczne rozpoznawanie cyfr nie jest "
            "jeszcze podłączone - wpisz stan licznika ręcznie."
        )
    except Exception as e:
        return False, float(fallback_value), f"Błąd przetwarzania obrazu: {str(e)}"

# ---------------------------------------------------------
# DYNAMICZNE POBIERANIE POGODY (OPENWEATHERMAP / OPEN-METEO FALLBACK)
# ---------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_outdoor_temp():
    api_key = st.secrets.get("openweathermap", {}).get("api_key", "")
    if not api_key and "custom_owm_key" in st.session_state:
        api_key = st.session_state["custom_owm_key"]

    if api_key:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT_LOCATION}&lon={LON_LOCATION}&appid={api_key}&units=metric"
            res = requests.get(url, timeout=4)
            if res.status_code == 200:
                return float(res.json()['main']['temp'])
        except Exception:
            pass

    try:
        url_fallback = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_LOCATION}&longitude={LON_LOCATION}&current=temperature_2m"
        res = requests.get(url_fallback, timeout=4)
        if res.status_code == 200:
            return float(res.json()['current']['temperature_2m'])
    except Exception:
        pass

    return 12.5

@st.cache_data(ttl=300, show_spinner=False)
def get_weather_forecast():
    try:
        api_key = st.secrets.get("openweathermap", {}).get("api_key", "")
        if not api_key and "custom_owm_key" in st.session_state:
            api_key = st.session_state["custom_owm_key"]

        if api_key:
            url = f"https://api.openweathermap.org/data/2.5/forecast?lat={LAT_LOCATION}&lon={LON_LOCATION}&appid={api_key}&units=metric"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                # Naprawiono: dla każdego dnia zawsze preferujemy odczyt z godz. 12:00,
                # niezależnie od tego, który rekord API przyszedł jako pierwszy.
                forecasts_by_date = {}
                for item in data.get('list', []):
                    dt_txt = item['dt_txt']
                    date_str = dt_txt.split(' ')[0]
                    is_noon = "12:00:00" in dt_txt
                    if date_str not in forecasts_by_date or is_noon:
                        forecasts_by_date[date_str] = {
                            "date": date_str,
                            "temp": item['main']['temp'],
                            "desc": item['weather'][0]['description'],
                            "icon": item['weather'][0]['icon'],
                            "_is_noon": is_noon
                        }
                ordered_dates = sorted(forecasts_by_date.keys())
                forecasts = [
                    {k: v for k, v in forecasts_by_date[d].items() if k != "_is_noon"}
                    for d in ordered_dates
                ]
                return forecasts[:7]
    except Exception:
        pass

    try:
        url_f_fallback = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_LOCATION}&longitude={LON_LOCATION}&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
        res = requests.get(url_f_fallback, timeout=5)
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
                    "desc": "Prognoza dynamiczna (Open-Meteo)",
                    "icon": "01d"
                })
            return forecasts
    except Exception:
        pass

    return []

# ---------------------------------------------------------
# STYLIZACJA W STYLU iOS 18
# ---------------------------------------------------------
st.markdown("""
    <style>
    @import url('https://fonts.cdnfonts.com/css/sf-pro-display');

    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif !important;
        color: #1C1C1E !important;
    }
    .main {
        background: linear-gradient(180deg, #F2F2F7 0%, #E5E5EA 100%) !important;
    }

    .ios-dynamic-island {
        background: #000000;
        color: #FFFFFF;
        border-radius: 28px;
        padding: 10px 22px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        max-width: 820px;
        margin: 0 auto 20px auto;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
        font-size: 14px;
        font-weight: 500;
        letter-spacing: -0.2px;
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    .island-item {
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .island-dot {
        width: 8px;
        height: 8px;
        background-color: #34C759;
        border-radius: 50%;
        box-shadow: 0 0 8px #34C759;
    }

    .ios-room-info-card {
        background: rgba(255, 255, 255, 0.85) !important;
        backdrop-filter: blur(30px) saturate(190%);
        -webkit-backdrop-filter: blur(30px) saturate(190%);
        border-radius: 24px !important;
        padding: 24px 28px !important;
        border: 1.5px solid rgba(255, 255, 255, 0.9) !important;
        box-shadow: 0 10px 35px rgba(0, 0, 0, 0.06) !important;
        transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
        margin-bottom: 22px;
    }
    .ios-room-info-card:hover {
        transform: translateY(-3px) scale(1.005) !important;
        box-shadow: 0 18px 45px rgba(0, 122, 255, 0.15) !important;
        border-color: rgba(0, 122, 255, 0.4) !important;
    }

    .room-header {
        font-size: 22px;
        font-weight: 700;
        color: #1C1C1E;
        letter-spacing: -0.4px;
    }

    .ios-live-badge {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(0, 122, 255, 0.2);
        padding: 10px 18px;
        border-radius: 16px;
        font-size: 15px;
        font-weight: 600;
        color: #1C1C1E;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        display: inline-block;
    }

    .meter-badge {
        background: rgba(120, 120, 128, 0.12);
        color: #3A3A3C;
        padding: 5px 12px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
        font-family: monospace;
    }

    .val-box {
        background: rgba(248, 249, 250, 0.9);
        border-radius: 16px;
        padding: 14px 16px;
        border: 1px solid rgba(229, 229, 234, 0.8);
        text-align: center;
        transition: all 0.25s ease;
    }
    .val-box:hover {
        border-color: #007AFF;
        box-shadow: 0 4px 15px rgba(0, 122, 255, 0.15);
        transform: scale(1.02);
    }
    .val-title {
        font-size: 11px;
        text-transform: uppercase;
        color: #8E8E93;
        font-weight: 700;
        letter-spacing: 0.6px;
    }
    .val-num {
        font-size: 24px;
        font-weight: 800;
        color: #007AFF;
        margin-top: 3px;
    }

    .fancy-alert-card {
        background: linear-gradient(135deg, rgba(0, 122, 255, 0.1) 0%, rgba(52, 199, 89, 0.1) 100%);
        border: 2px solid #007AFF;
        border-radius: 20px;
        padding: 20px 24px;
        box-shadow: 0 10px 30px rgba(0, 122, 255, 0.2);
        margin-bottom: 25px;
        animation: fadeIn 0.5s ease-out;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# KONFIGURACJA POMIESZCZEŃ I GITHUB
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "device_id": "11420", "meter_default": "503 754 417", "units_start": 1509.0},
    "Dzieciaki": {"icon": "🧒", "device_id": "11420", "meter_default": "503 754 240", "units_start": 1104.0},
    "Sypialnia": {"icon": "🛏️", "device_id": "11420", "meter_default": "503 754 493", "units_start": 1267.0},
    "Licznik Główny": {"icon": "🏢", "device_id": "-", "meter_default": "GJ-MAIN-2026", "units_start": 0.0}
}
# Uwaga: usunięto nieużywany klucz "share" (0.45/0.30/0.25) - realny udział
# procentowy każdej strefy jest liczony dynamicznie z rzeczywistych danych
# (patrz zmienna `room_share_pct`), więc statyczne wartości były martwym
# kodem mogącym wprowadzać w błąd przy edycji configu.

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff - Wtorki)"]
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

def create_initial_df():
    return pd.DataFrame([
        {
            "id": 1,
            "season": "2026/2027 (Sonoff - Wtorki)",
            "week_num": 37,
            "period_label": "Tydzień 37 (Stan Zero)",
            "date_entry": "2026-09-08",
            "room_name": "Salon",
            "meter_number": "503 754 417",
            "units_start": 1509.0,
            "units_end": 1509.0,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 14.2,
            "temp_wewnetrzna": 20.5,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Stan zero wrzesień 2026 - Salon"
        },
        {
            "id": 2,
            "season": "2026/2027 (Sonoff - Wtorki)",
            "week_num": 37,
            "period_label": "Tydzień 37 (Stan Zero)",
            "date_entry": "2026-09-08",
            "room_name": "Dzieciaki",
            "meter_number": "503 754 240",
            "units_start": 1104.0,
            "units_end": 1104.0,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 14.2,
            "temp_wewnetrzna": 20.5,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Stan zero wrzesień 2026 - Dzieciaki"
        },
        {
            "id": 3,
            "season": "2026/2027 (Sonoff - Wtorki)",
            "week_num": 37,
            "period_label": "Tydzień 37 (Stan Zero)",
            "date_entry": "2026-09-08",
            "room_name": "Sypialnia",
            "meter_number": "503 754 493",
            "units_start": 1267.0,
            "units_end": 1267.0,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 14.2,
            "temp_wewnetrzna": 20.8,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Stan zero wrzesień 2026 - Sypialnia"
        }
    ])

@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    df = None
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            df = pd.read_csv(io.StringIO(file_content.decoded_content.decode('utf-8')))
        except Exception:
            df = load_local_fallback()
    else:
        df = load_local_fallback()

    if df is not None and not df.empty:
        required_columns = {
            "id": 1,
            "season": "2026/2027 (Sonoff - Wtorki)",
            "week_num": 37,
            "period_label": "Tydzień 37",
            "date_entry": str(date.today()),
            "room_name": "Salon",
            "meter_number": "503 754 417",
            "units_start": 1509.0,
            "units_end": 1509.0,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 12.0,
            "temp_wewnetrzna": 20.5,
            "mode_tag": "Standard (Automatyczny)",
            "notes": ""
        }
        for col, default_val in required_columns.items():
            if col not in df.columns:
                df[col] = default_val

        # Normalizacja typów - zapewnia poprawne sortowanie chronologiczne
        # (istotne dla wykresu skumulowanego w zakładce "Porównanie Sezonów")
        df["date_entry"] = pd.to_datetime(df["date_entry"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["week_num"] = pd.to_numeric(df["week_num"], errors="coerce").fillna(0).astype(int)
        df["delta_units"] = pd.to_numeric(df["delta_units"], errors="coerce").fillna(0.0)

    return df

def load_local_fallback():
    if os.path.exists(FILE_PATH):
        try: return pd.read_csv(FILE_PATH)
        except Exception: return create_initial_df()
    df = create_initial_df()
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    df.to_csv(FILE_PATH, index=False)
    return df

def save_data(df, commit_message="Aktualizacja odczytu"):
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    csv_string = df.to_csv(index=False)
    success = False
    is_cloud_sync = False

    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(FILE_PATH, commit_message, csv_string, file_content.sha, branch=branch)
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
            success = True
            is_cloud_sync = True
        except Exception:
            success = False
            is_cloud_sync = False

    if not success or not repo:
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        success = True

    if success:
        st.cache_data.clear()
        if not is_cloud_sync and repo:
            st.warning("⚠️ Zapisano zmiany lokalnie (fallback). Synchronizacja z chmurą GitHub nie powiodła się.")

    return success

df = load_data()

# ---------------------------------------------------------
# SPRAWDŹ CZY DZIŚ JEST WTOREK
# ---------------------------------------------------------
today = date.today()
is_tuesday = (today.weekday() == 1)

if "fancy_alert" in st.session_state:
    elapsed = time.time() - st.session_state["fancy_alert"]["timestamp"]
    if elapsed > 300:
        del st.session_state["fancy_alert"]

# ---------------------------------------------------------
# PANEL BOCZNY: KAFELKI
# ---------------------------------------------------------
if "sidebar_section" not in st.session_state:
    st.session_state["sidebar_section"] = "Ustawienia Symulacji"

with st.sidebar:
    st.header("⚙️ Panel Sterowania")
    st.caption("Wybierz moduł (kafelki):")

    sections = [
        ("⚙️ Ustawienia Symulacji", "Ustawienia Symulacji", "Stawka PLN/U i parametry"),
        ("💡 Zwrot z Inwestycji (ROI)", "Zwrot z Inwestycji (ROI)", "Spłata kosztów systemu"),
        ("🌤️ Prognoza 7D & Sonoff AI", "Prognoza 7D (Bytków) & Sonoff AI", "Pogoda i anomalie"),
        ("🎛️ Symulator „Co jeśli?”", "Symulator „Co jeśli?”", "Test zmian temperatury"),
        ("📄 Generuj Raport SSM", "Generuj Raport SSM (HTML)", "Eksport rozliczeń HTML")
    ]

    for title, key_name, desc in sections:
        is_sel = (st.session_state["sidebar_section"] == key_name)
        if st.button(f"{title}\n_{desc}_", key=f"tile_{key_name}", use_container_width=True, type="primary" if is_sel else "secondary"):
            st.session_state["sidebar_section"] = key_name
            st.rerun()

    selected_sidebar_section = st.session_state["sidebar_section"]

# NAWIGACJA GŁÓWNA I NAGŁÓWEK
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

current_room = st.session_state["selected_room"]
if current_room not in ROOMS_CONFIG:
    current_room = "Salon"
    st.session_state["selected_room"] = current_room

st.title("🔥 Sonoff Smart Heating - Panel Sterowania & SSM Analytics")
st.caption(f"Lokalizacja: **{LOCATION_NAME}** | Pełna kontrola kosztów vs Spółdzielnia Mieszkaniowa (SSM)")

# Przygotowanie danych dla wybranej strefy lub Licznika Głównego
if current_room == "Licznik Główny":
    df_filtered = df.copy()
else:
    df_filtered = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"]) if not df.empty else pd.DataFrame()

df_room_sonoff = df_filtered[df_filtered["season"].str.contains("Sonoff", na=False)] if not df_filtered.empty else pd.DataFrame()
if not df_room_sonoff.empty:
    df_room_sonoff = df_room_sonoff.sort_values(by=["date_entry", "id"])

if not df_room_sonoff.empty and current_room != "Licznik Główny":
    val_start = float(df_room_sonoff.iloc[0]["units_start"])
    last_row = df_room_sonoff.iloc[-1]
    val_end = float(last_row.get("units_end", val_start))
    last_meter = str(last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"]))
    total_delta_room = df_room_sonoff["delta_units"].sum()
elif current_room == "Licznik Główny":
    df_sonoff_all_rooms = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")]
    total_delta_room = df_sonoff_all_rooms["delta_units"].sum() if not df_sonoff_all_rooms.empty else 0.0
    val_start = 0.0
    val_end = total_delta_room
    last_meter = "GJ-MAIN-SUMA"
else:
    val_start = ROOMS_CONFIG[current_room]["units_start"]
    val_end = val_start
    last_meter = ROOMS_CONFIG[current_room]["meter_default"]
    total_delta_room = 0.0

# NAPRAWIONO: dla widoku "Licznik Główny" ostatni przyrost to suma ostatnich
# przyrostów każdej pojedynczej strefy, a nie sztywne 0.0.
if current_room == "Licznik Główny":
    last_delta = 0.0
    for room_name in ROOMS_CONFIG:
        if room_name == "Licznik Główny":
            continue
        room_df = df[(df["room_name"] == room_name) & (df["season"].str.contains("Sonoff", na=False))]
        if not room_df.empty:
            room_df = room_df.sort_values(by=["date_entry", "id"])
            last_delta += float(room_df.iloc[-1]["delta_units"])
elif not df_room_sonoff.empty:
    last_delta = float(df_room_sonoff.iloc[-1]["delta_units"])
else:
    last_delta = 0.0

live_outdoor_temp = get_outdoor_temp()

df_sonoff_all = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")] if not df.empty else pd.DataFrame()
if df_sonoff_all.empty:
    df_sonoff_all = df[df["season"].str.contains("Sonoff", na=False)] if not df.empty else pd.DataFrame()

total_apartment_units = df_sonoff_all["delta_units"].sum() if not df_sonoff_all.empty else 0.0
EST_PLN_PER_UNIT = st.session_state.get("est_pln_per_unit_val", 2.45)

total_realtime_cost = total_apartment_units * EST_PLN_PER_UNIT
weeks_logged_count = max(1, df_sonoff_all["week_num"].nunique()) if not df_sonoff_all.empty else 1
ssm_paid_advances_to_date = (weeks_logged_count / SSM_TOTAL_WEEKS) * SSM_ANNUAL_CO_BUDGET
ssm_net_balance_to_date = ssm_paid_advances_to_date - total_realtime_cost

island_status_color = "#34C759" if ssm_net_balance_to_date >= 0 else "#FF3B30"
island_balance_txt = f"+{ssm_net_balance_to_date:.1f} zł" if ssm_net_balance_to_date >= 0 else f"{ssm_net_balance_to_date:.1f} zł"

st.markdown(f"""
<div class="ios-dynamic-island">
    <div class="island-item"><div class="island-dot"></div><span>Strefa: <b>{current_room}</b></span></div>
    <div class="island-item"><span>🌡️ Bytków: <b>{live_outdoor_temp}°C</b></span></div>
    <div class="island-item"><span>Bilans SSM: <b style="color: {island_status_color};">{island_balance_txt}</b></span></div>
</div>
""", unsafe_allow_html=True)

if "fancy_alert" in st.session_state:
    fa = st.session_state["fancy_alert"]
    st.markdown(f"""
    <div class="fancy-alert-card">
        <h3 style="margin: 0 0 8px 0; color: #007AFF;">⚡ Sukces! Nowy odczyt zapisany dla strefy: {fa['room']}</h3>
        <p style="margin: 4px 0; font-size: 16px;"><b>Przyrost w tym tygodniu (&Delta;U):</b> <span style="color: #34C759; font-weight: 700;">+{fa['delta']:.1f} U</span> ({fa['delta']*EST_PLN_PER_UNIT:.2f} PLN)</p>
        <p style="margin: 4px 0; font-size: 16px;"><b>Porównanie tydzień do tygodnia:</b> <span style="color: {'#34C759' if fa['diff_vs_prev'] <= 0 else '#FF3B30'}; font-weight: 700;">{fa['diff_vs_prev']:+.1f}%</span> względem poprz. odczytu</p>
        <p style="margin: 4px 0; font-size: 16px;"><b>Całkowity bilans strefy w sezonie:</b> <b style="color: #AF52DE;">{fa['total_room_units']:.1f} U</b> (~{fa['total_room_units']*EST_PLN_PER_UNIT:.2f} PLN)</p>
    </div>
    """, unsafe_allow_html=True)

room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (current_room == room_key)
    btn_label = f"{info['icon']} {room_key}" if room_key != "Licznik Główny" else f"{info['icon']} {room_key} (Suma)"
    with room_cols[idx]:
        if st.button(btn_label, key=f"btn_{room_key}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state["selected_room"] = room_key
            st.rerun()

st.divider()

ssm_projected_full_season_cost = (total_realtime_cost / weeks_logged_count) * SSM_TOTAL_WEEKS
ssm_projected_refund_or_extra = SSM_ANNUAL_CO_BUDGET - ssm_projected_full_season_cost
cost_per_m2_actual = total_realtime_cost / APARTMENT_AREA_M2
ssm_advance_per_m2_to_date = ssm_paid_advances_to_date / APARTMENT_AREA_M2
room_share_pct = 100.0 if current_room == "Licznik Główny" else ((total_delta_room / total_apartment_units * 100) if total_apartment_units > 0 else 0.0)

# FORMULARZ WTORKOWY Z OCR DLA AKTYWNEJ STREFY
if is_tuesday and current_room != "Licznik Główny":
    current_year, current_iso_w, _ = today.isocalendar()
    already_added_this_week = False
    if not df_room_sonoff.empty:
        already_added_this_week = ((df_room_sonoff["week_num"] == current_iso_w) & (df_room_sonoff["season"] == "2026/2027 (Sonoff - Wtorki)")).any()

    if not already_added_this_week:
        with st.expander(f"🚨 WTOREK – Wymagany Odczyt dla strefy: {current_room} (Tydzień {current_iso_w})", expanded=True):
            st.warning(f"Dziś jest wtorek! Podaj aktualny stan podzielnika oraz temperaturę wewnętrzną dla strefy **{current_room}**.")

            last_row_room = df_room_sonoff.iloc[-1] if not df_room_sonoff.empty else None
            default_units_start = float(last_row_room["units_end"]) if last_row_room is not None else ROOMS_CONFIG[current_room]["units_start"]
            default_meter = str(last_row_room["meter_number"]) if last_row_room is not None else ROOMS_CONFIG[current_room]["meter_default"]

            with st.form(f"auto_tuesday_form_{current_room}"):
                st.markdown("#### 📷 Szybki odczyt OCR ze zdjęcia")
                ocr_image_input = st.file_uploader(
                    "Wgraj zdjęcie podzielnika (opcjonalnie)",
                    type=["jpg", "jpeg", "png"],
                    key=f"ocr_file_{current_room}"
                )

                # NAPRAWIONO: fallback to ostatni znany stan TEJ strefy (nie stała
                # 1514.5 dla wszystkich stref), a wynik jest zawsze >= default_units_start,
                # więc number_input poniżej nigdy nie crashuje na min_value.
                suggested_end_units = default_units_start
                if ocr_image_input is not None:
                    success_ocr, extracted_val, ocr_msg = process_meter_ocr(ocr_image_input, default_units_start)
                    suggested_end_units = max(extracted_val, default_units_start)
                    if success_ocr:
                        st.success(f"✨ {ocr_msg}: **{extracted_val} U**")
                    else:
                        st.info(ocr_msg)

                c1, c2, c3 = st.columns(3)
                with c1:
                    meter_num = st.text_input("Nr podzielnika", value=default_meter)
                with c2:
                    units_start = st.number_input("Poprzedni stan [U]", value=default_units_start, disabled=True)
                with c3:
                    # NAPRAWIONO: dopuszczamy też wartość równą poprzedniemu stanowi
                    # (min_value = default_units_start, ale suggested_end_units już
                    # zawsze >= default_units_start, więc value nigdy nie jest
                    # mniejsze niż min_value - to był dokładny powód crasha).
                    units_end = st.number_input(
                        "Nowy stan [U]",
                        min_value=default_units_start,
                        value=float(suggested_end_units),
                        step=0.1
                    )

                temp_in = st.number_input("Temp. wewnątrz [°C]", min_value=10.0, max_value=30.0, value=21.0, step=0.1)
                mode_tag = st.selectbox("Tryb pracy grzania", MODES, index=0)
                notes = st.text_input("Uwagi / Nastawa", value="Odczyt wtorkowy z OCR" if ocr_image_input else "Odczyt wtorkowy")

                if st.form_submit_button("⚡ Zapisz odczyt wtorkowy", use_container_width=True):
                    delta_u = units_end - units_start
                    next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1

                    new_row = {
                        "id": next_id,
                        "season": "2026/2027 (Sonoff - Wtorki)",
                        "week_num": current_iso_w,
                        "period_label": f"Tydzień {current_iso_w:02d} (Wtorek)",
                        "date_entry": str(today),
                        "room_name": current_room,
                        "meter_number": meter_num,
                        "units_start": units_start,
                        "units_end": units_end,
                        "delta_units": delta_u,
                        "gj_start": 0.0,
                        "gj_end": 0.0,
                        "delta_gj": 0.0,
                        "temp_zewnetrzna": live_outdoor_temp,
                        "temp_wewnetrzna": temp_in,
                        "mode_tag": mode_tag,
                        "notes": notes
                    }

                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    if save_data(df, commit_message=f"Odczyt wtorkowy {current_room} T{current_iso_w}"):
                        prev_delta = last_delta if last_delta > 0 else 1.0
                        diff_vs_prev = ((delta_u - prev_delta) / prev_delta * 100) if prev_delta > 0 else 0.0
                        new_total_room = total_delta_room + delta_u
                        st.session_state["fancy_alert"] = {
                            "timestamp": time.time(),
                            "room": current_room,
                            "delta": delta_u,
                            "diff_vs_prev": diff_vs_prev,
                            "total_room_units": new_total_room
                        }
                        st.success(f"Zapisano odczyt dla strefy {current_room}!")
                        st.rerun()

room_desc_subtitle = "Suma wszystkich pokoi w mieszkaniu" if current_room == "Licznik Główny" else f"Pojedyncza strefa grzewcza ({room_share_pct:.1f}% udziału w mieszkaniu)"

st.markdown(f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 12px;">
        <div>
            <div class="room-header">
                {ROOMS_CONFIG[current_room]['icon']} Strefa: <b>{current_room}</b>
                <span class="meter-badge">Urządzenie: {ROOMS_CONFIG[current_room]['device_id']} | {last_meter}</span>
            </div>
            <div style="font-size: 13px; color: #8E8E93; margin-top: 2px;">ℹ️ {room_desc_subtitle}</div>
        </div>
        <div class="ios-live-badge">
            🌡️ Zewn. (Bytków): <b style="color: #007AFF;">{live_outdoor_temp}°C</b> &nbsp;|&nbsp; Udział: <b style="color: #AF52DE;">{room_share_pct:.1f}%</b>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;">
        <div class="val-box">
            <div class="val-title">Stały Stan Początkowy</div>
            <div class="val-num">{val_start:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Aktualny Stan Licznika</div>
            <div class="val-num">{val_end:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Ostatni Przyrost (&Delta;U)</div>
            <div class="val-num" style="color: #34C759;">+{last_delta:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Suma Sezon Strefa</div>
            <div class="val-num" style="color: #AF52DE;">{total_delta_room:.1f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if ssm_net_balance_to_date >= 0:
    ssm_status_html = f"<span style='color: #34C759; font-weight: 800;'>🟢 NADPŁATA: +{ssm_net_balance_to_date:.2f} PLN</span>"
else:
    ssm_status_html = f"<span style='color: #FF3B30; font-weight: 800;'>🔴 NIEDOPŁATA: {ssm_net_balance_to_date:.2f} PLN</span>"

kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
with kpi_col1:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">🏢 Bilans na dziś vs Zaliczki SSM</div>
        <div class="val-num" style="font-size: 22px;">{ssm_status_html}</div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Wpłacono zaliczek: <b>{ssm_paid_advances_to_date:.1f} zł</b> | Zużyto: <b>{total_realtime_cost:.1f} zł</b></div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col2:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">📐 Koszt na 1 m² Lokalu ({APARTMENT_AREA_M2} m²)</div>
        <div class="val-num" style="color: #007AFF; font-size: 24px;">{cost_per_m2_actual:.2f} zł / m²</div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Zaliczka SSM: <b>{ssm_advance_per_m2_to_date:.2f} zł/m²</b></div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col3:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">🔮 Prognoza Końcowa Sezonu SSM</div>
        <div class="val-num" style="color: {'#34C759' if ssm_projected_refund_or_extra >= 0 else '#FF3B30'}; font-size: 22px;">
            {'ZWROT: +' if ssm_projected_refund_or_extra >= 0 else 'DOPŁATA: '}{ssm_projected_refund_or_extra:.2f} PLN
        </div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Szacowany koszt 7 mc-y: <b>{ssm_projected_full_season_cost:.1f} zł</b></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("---")
    if selected_sidebar_section == "Ustawienia Symulacji":
        st.subheader("⚙️ Ustawienia Symulacji")
        st.session_state["est_pln_per_unit_val"] = st.slider(
            "Stawka jednostkowa [PLN / U]", min_value=1.00, max_value=5.00, value=2.45, step=0.05
        )

    elif selected_sidebar_section == "Zwrot z Inwestycji (ROI)":
        st.subheader("💡 Zwrot z Inwestycji (ROI)")
        HARDWARE_COST_EST = 775.79
        df_base_sum = df[df["season"].str.contains("Bazowy", na=False)]["delta_units"].sum() if not df.empty else 0.0
        if df_base_sum > 0:
            total_saved_units = max(0.0, df_base_sum - total_apartment_units)
            total_saved_pln = total_saved_units * EST_PLN_PER_UNIT
            payback_ratio = min(1.0, total_saved_pln / HARDWARE_COST_EST) if HARDWARE_COST_EST > 0 else 1.0
            st.caption(f"Koszt systemu: **{HARDWARE_COST_EST:.2f} PLN**")
            st.progress(payback_ratio, text=f"Spłacono: {total_saved_pln:.2f} PLN ({payback_ratio*100:.1f}%)")
        else:
            # NAPRAWIONO: informujemy wprost, dlaczego ROI = 0%, zamiast cicho
            # pokazywać pusty pasek postępu. Sezon "Bazowy" nie ma dziś żadnego
            # sposobu na dodanie wpisów przez UI - trzeba je dopisać ręcznie
            # w zakładce "Historia i Edycja Wpisów" (kolumna `season`), żeby
            # ten moduł zaczął liczyć realne oszczędności.
            st.caption(f"Koszt systemu: **{HARDWARE_COST_EST:.2f} PLN**")
            st.info(
                "Brak danych dla sezonu bazowego (2025/2026), więc ROI nie może "
                "być jeszcze policzone. Dodaj historyczne zużycie z sezonu "
                "bazowego w zakładce „Historia i Edycja Wpisów”, ustawiając "
                "kolumnę `season` na `2025/2026 (Bazowy)`."
            )

    elif selected_sidebar_section == "Prognoza 7D (Bytków) & Sonoff AI":
        st.subheader("🌤️ Prognoza 7D & Sonoff AI")

        custom_key_input = st.text_input("Opcjonalny klucz OpenWeatherMap", value=st.session_state.get("custom_owm_key", ""), type="password")
        if custom_key_input:
            st.session_state["custom_owm_key"] = custom_key_input

        forecast_list = get_weather_forecast()
        if forecast_list:
            min_temp_f = min([f['temp'] for f in forecast_list])
            if min_temp_f < 5.0:
                st.warning(f"⚠️ Ochłodzenie do **{min_temp_f}°C**. Zalecane włączenie komfortu.")
            else:
                st.success("✅ Stabilne warunki pogodowe.")
            for f in forecast_list[:4]:
                st.markdown(f"📅 **{f['date']}**: 🌡️ **{f['temp']:.1f}°C**")
        else:
            st.info("Pobieranie prognozy automatycznej...")

    elif selected_sidebar_section == "Symulator „Co jeśli?”":
        st.subheader("🎛️ Symulator „Co jeśli?”")
        temp_change_slider = st.slider("Zmiana temp. w mieszkaniu [°C]", -3.0, 3.0, 0.0, 0.5)
        sim_diff_u = total_apartment_units * (temp_change_slider * 0.07)
        sim_diff_pln = sim_diff_u * EST_PLN_PER_UNIT
        if temp_change_slider < 0:
            st.success(f"💡 Oszczędność: ~**{abs(sim_diff_pln):.2f} PLN**")
        elif temp_change_slider > 0:
            st.error(f"⚠️ Wzrost kosztu: ~**+{sim_diff_pln:.2f} PLN**")
        else:
            st.info("Brak zmian temperatury.")

    elif selected_sidebar_section == "Generuj Raport SSM (HTML)":
        st.subheader("📄 Generuj Raport SSM (HTML)")
        html_report_content = f"""
        <html><head><meta charset='utf-8'><title>Raport CO SSM</title></head>
        <body style='font-family: Arial; padding: 20px;'>
            <h2>Oficjalny Raport Rozliczeniowy Ciepła CO - SSM</h2>
            <p><b>Lokalizacja:</b> {LOCATION_NAME}</p>
            <p><b>Budżet zaliczkowy:</b> {SSM_ANNUAL_CO_BUDGET:.2f} PLN</p>
            <p><b>Rzeczywisty koszt:</b> {total_realtime_cost:.2f} PLN</p>
            <p><b>Bilans:</b> {ssm_net_balance_to_date:+.2f} PLN</p>
        </body></html>
        """
        st.download_button("📥 Pobierz Raport HTML", html_report_content.encode("utf-8"), "raport_co.html", "text/html", use_container_width=True)

    if not df.empty:
        st.markdown("---")
        if st.button("↩️ Cofnij ostatni wpis", use_container_width=True):
            df = df.iloc[:-1]
            save_data(df, "Cofnięcie ostatniego wpisu")
            st.warning("Usunięto ostatni wpis!")
            st.rerun()

tab_charts, tab_season_comp, tab_analytics, tab_schedule, tab_ai_pred, tab_history = st.tabs([
    "📈 Wykres, Skumulowany & Pogoda",
    "📊 Porównanie Sezonów i Koszt Narastający",
    "💸 Zyski i Straty & Heatmapa",
    "📅 Harmonogram i Sterowanie",
    "🤖 Predykcja AI i Raport",
    "📋 Historia i Edycja Wpisów"
])

with tab_charts:
    st.markdown(f"#### Korelacja Zużycia &Delta;U oraz Temperatury Zewnętrznej dla: **{current_room}**")
    if not df_filtered.empty:
        fig_dual = px_go.Figure()
        fig_dual.add_trace(px_go.Bar(x=df_filtered["period_label"], y=df_filtered["delta_units"], name="Zużycie [U]", marker_color="#007AFF"))
        fig_dual.add_trace(px_go.Scatter(x=df_filtered["period_label"], y=df_filtered["temp_zewnetrzna"], name="Temp. Zewn. [°C]", mode="lines+markers", yaxis="y2", line=dict(color="#FF9500", width=3)))
        fig_dual.update_layout(template="plotly_white", yaxis=dict(title="Zużycie [U]"), yaxis2=dict(title="Temperatura [°C]", overlaying="y", side="right"), height=360)
        st.plotly_chart(fig_dual, use_container_width=True)

with tab_season_comp:
    st.markdown("### 📊 Porównanie Sezonów i Koszt Narastający")
    if not df.empty:
        # NAPRAWIONO: poprzednia wersja grupowała i sumowała kumulatywnie po
        # `week_num` (numer tygodnia ISO 1-53), który resetuje się do 1 po
        # Nowym Roku. Dla sezonu grzewczego (wrzesień -> kwiecień) powodowało
        # to, że tygodnie styczniowe (1, 2, 3...) były sortowane PRZED
        # tygodniami grudniowymi (49, 50, 51), a skumulowany koszt na
        # wykresie "cofał się" zamiast rosnąć.
        # Teraz sortujemy chronologicznie po realnej dacie wpisu (`date_entry`)
        # w obrębie każdego sezonu, a numer tygodnia sezonu liczymy jako
        # kolejną, sekwencyjną pozycję (1, 2, 3...) - niezależną od numeru
        # tygodnia ISO.
        df_valid = df[df["room_name"] != "Licznik Główny"].copy()
        df_valid["date_entry_dt"] = pd.to_datetime(df_valid["date_entry"], errors="coerce")
        df_valid = df_valid.dropna(subset=["date_entry_dt"])

        weekly = (
            df_valid.groupby(["season", "week_num"])
            .agg(delta_units=("delta_units", "sum"), date_entry_dt=("date_entry_dt", "min"))
            .reset_index()
        )
        weekly = weekly.sort_values(["season", "date_entry_dt"])
        weekly["cumulative_units"] = weekly.groupby("season")["delta_units"].cumsum()
        weekly["cumulative_pln"] = weekly["cumulative_units"] * EST_PLN_PER_UNIT
        # Sekwencyjny numer tygodnia W RAMACH sezonu (1, 2, 3...), odporny na
        # reset numeracji ISO po Nowym Roku - używany tylko do osi X i do
        # liczenia linii zaliczek SSM.
        weekly["season_week_seq"] = weekly.groupby("season").cumcount() + 1
        weekly["date_label"] = weekly["date_entry_dt"].dt.strftime("%d.%m.%Y")

        fig_cum = px_go.Figure()
        for season_name in weekly["season"].unique():
            sub_df = weekly[weekly["season"] == season_name]
            fig_cum.add_trace(px_go.Scatter(
                x=sub_df["season_week_seq"],
                y=sub_df["cumulative_pln"],
                name=season_name,
                mode="lines+markers",
                customdata=sub_df["date_label"],
                hovertemplate="Tydzień sezonu %{x}<br>Data: %{customdata}<br>Koszt narastająco: %{y:.2f} PLN<extra></extra>"
            ))

        max_week_seq = int(weekly["season_week_seq"].max()) if not weekly.empty else SSM_TOTAL_WEEKS
        weeks_seq = list(range(1, max(max_week_seq, SSM_TOTAL_WEEKS) + 1))
        ssm_advances_line = [(w / SSM_TOTAL_WEEKS) * SSM_ANNUAL_CO_BUDGET for w in weeks_seq]
        fig_cum.add_trace(px_go.Scatter(x=weeks_seq, y=ssm_advances_line, name="Wpłaty Zaliczek SSM", line=dict(color="#34C759", width=3, dash="dash")))
        fig_cum.update_layout(
            template="plotly_white",
            height=360,
            xaxis_title="Tydzień sezonu (kolejność chronologiczna)",
            yaxis_title="Koszt narastająco [PLN]"
        )
        st.plotly_chart(fig_cum, use_container_width=True)

with tab_analytics:
    st.markdown("### 💸 Bilans Finansowy")
    st.info("Moduł analityczny aktywny i zsynchronizowany.")

with tab_schedule:
    st.markdown("### 📅 Harmonogram i Sterowanie Głowicami TRVZB")
    st.caption("Poniżej zaprezentowano aktywne harmonogramy czasowo-temperaturne dla poszczególnych stref grzewczych w mieszkaniu.")

    sched_col1, sched_col2, sched_col3 = st.columns(3)

    with sched_col1:
        st.markdown("""
        <div class="ios-room-info-card" style="padding: 18px !important;">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 12px; color: #1C1C1E;">🛋️ Salon (Strefa dzienna)</div>
            <div style="font-size: 13px; line-height: 1.6; color: #3A3A3C;">
                <b>06:00 – 08:00</b> | <b>20.0°C</b><br>Poranny rozruch termiczny.<br><br>
                <b>08:00 – 14:00</b> | <b>18.0°C</b><br>Redukcja dzienna w pustym mieszkaniu.<br><br>
                <b>14:00 – 15:00</b> | <b>19.5°C</b><br>Faza buforowa przed powrotem.<br><br>
                <b>15:00 – 22:30</b> | <b>21.5°C</b><br>Komfort popołudniowo-wieczorny.<br><br>
                <b>22:30 – 06:00</b> | <b>19.0°C</b><br>Nocna stabilizacja.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with sched_col2:
        st.markdown("""
        <div class="ios-room-info-card" style="padding: 18px !important;">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 12px; color: #1C1C1E;">🛏️ Sypialnia (z balkonem)</div>
            <div style="font-size: 13px; line-height: 1.6; color: #3A3A3C;">
                <b>06:00 – 07:30</b> | <b>19.5°C</b><br>Poranne wstawanie.<br><br>
                <b>07:30 – 20:00</b> | <b>18.0°C</b><br>Dniowa redukcja.<br><br>
                <b>20:00 – 21:00</b> | <b>19.0°C</b><br>Wstępne wygrzanie przed snem.<br><br>
                <b>21:00 – 06:00</b> | <b>18.0°C</b><br>Chłodniejsza strefa nocna.<br><br>
                <hr style="margin: 8px 0; border-top: 1px solid rgba(0,0,0,0.1);">
                <span style="font-size: 12px; color: #007AFF;"><b>Współczynnik balkonu:</b> Zawór trzyma minimum 18°C.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with sched_col3:
        st.markdown("""
        <div class="ios-room-info-card" style="padding: 18px !important;">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 12px; color: #1C1C1E;">🧒 Pokój Dziecięcy</div>
            <div style="font-size: 13px; line-height: 1.6; color: #3A3A3C;">
                <b>05:30 – 07:20</b> | <b>21.0°C</b><br>Poranny rozruch.<br><br>
                <b>07:20 – 14:00</b> | <b>18.0°C</b><br>Dzienna redukcja eco.<br><br>
                <b>14:00 – 15:00</b> | <b>19.5°C</b><br>Faza buforowa przed powrotem.<br><br>
                <b>15:00 – 21:30</b> | <b>21.5°C</b><br>Komfort popołudniowy.<br><br>
                <b>21:30 – 05:30</b> | <b>19.0°C</b><br>Stabilna temperatura nocna.
            </div>
        </div>
        """, unsafe_allow_html=True)

with tab_ai_pred:
    st.markdown("### 🤖 Predykcja AI i Raport SSM")
    st.info(f"Szacowany wynik końcowy sezonu SSM: **{ssm_projected_refund_or_extra:+.2f} PLN**")

with tab_history:
    st.markdown("### 📋 Historia i Edycja Wpisów")
    if not df.empty:
        df_editable = df.copy()
        if "Zaznacz" not in df_editable.columns:
            df_editable.insert(0, "Zaznacz", False)
        edited_table = st.data_editor(df_editable, use_container_width=True, hide_index=True)
        if st.button("🗑️ Usuń zaznaczone wiersze", type="primary"):
            rows_to_keep = edited_table[edited_table["Zaznacz"] == False].drop(columns=["Zaznacz"])
            save_data(rows_to_keep, "Usunięcie wybranych wierszy")
            st.rerun()
