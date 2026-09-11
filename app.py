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
# KONFIGURACJA STRONY I LOKALIZACJI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Dynamic Analytics",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45
APARTMENT_AREA_M2 = 66.54  # Dokładna powierzchnia lokalu

# Oficjalne dane ze Spółdzielni (SSM) dla lokalu 66,54 m²
SSM_CO_MONTHLY_ADVANCE = 774.53  # 11.64 zł / m² / mc (zaliczka miesięczna)
SSM_SEASON_MONTHS = 7            # Sezon grzewczy (październik - kwiecień)
SSM_TOTAL_WEEKS = 30             # Przybliżona liczba tygodni w sezonie
SSM_ANNUAL_CO_BUDGET = SSM_CO_MONTHLY_ADVANCE * SSM_SEASON_MONTHS  # Całkowity budżet zaliczkowy CO na sezon (~5421.71 zł)

# Współrzędne dla: Siemianowice Śląskie, Bytków, ul. Związku Harcerstwa Polskiego
LAT_LOCATION = 50.3264
LON_LOCATION = 19.0295
LOCATION_NAME = "Siemianowice Śl. - Bytków (ZHP)"

# ---------------------------------------------------------
# POBIERANIE POGODY Z OPENWEATHERMAP
# ---------------------------------------------------------
def get_outdoor_temp():
    api_key = st.secrets.get("openweathermap", {}).get("api_key", None)
    if not api_key:
        return 12.5
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT_LOCATION}&lon={LON_LOCATION}&appid={api_key}&units=metric"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return float(res.json()['main']['temp'])
    except requests.exceptions.RequestException:
        pass
    return 12.5

# ---------------------------------------------------------
# STYLIZACJA W STYLU iOS 18 (Czysty, nowoczesny UI)
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
    "Salon": {"icon": "🛋️", "meter_default": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter_default": "11420"},
    "Pokój Dziecka": {"icon": "🧒", "meter_default": "11420"},
    "Licznik Główny": {"icon": "🏢", "meter_default": "GJ-MAIN-2026"}
}

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
            "room_name": "Sypialnia",
            "meter_number": "11420",
            "units_start": 126.7,
            "units_end": 126.7,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 14.2,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Stan zero - wrzesień 2026"
        },
        {
            "id": 2,
            "season": "2026/2027 (Sonoff - Wtorki)",
            "week_num": 37,
            "period_label": "Tydzień 37 (Stan Zero)",
            "date_entry": "2026-09-08",
            "room_name": "Pokój Dziecka",
            "meter_number": "11420",
            "units_start": 110.4,
            "units_end": 110.4,
            "delta_units": 0.0,
            "gj_start": 0.0,
            "gj_end": 0.0,
            "delta_gj": 0.0,
            "temp_zewnetrzna": 14.2,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Stan zero - wrzesień 2026"
        },
        {
            "id": 3,
            "season": "2025/2026 (Bazowy)",
            "week_num": 37,
            "period_label": "Sezon Historyczny SSM",
            "date_entry": "2025-05-01",
            "room_name": "Licznik Główny",
            "meter_number": "GJ-MAIN-2025",
            "units_start": 0.0,
            "units_end": 2212.0,
            "delta_units": 2212.0,
            "gj_start": 0.0,
            "gj_end": 62.82,
            "delta_gj": 62.82,
            "temp_zewnetrzna": 6.5,
            "mode_tag": "Standard (Automatyczny)",
            "notes": "Oficjalne dane zużycia 62.82 GJ"
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
        if "temp_zewnetrzna" not in df.columns:
            df["temp_zewnetrzna"] = 12.0
        if "mode_tag" not in df.columns:
            df["mode_tag"] = "Standard (Automatyczny)"
            
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
    
    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(FILE_PATH, commit_message, csv_string, file_content.sha, branch=branch)
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
            success = True
        except Exception:
            success = False
            
    if not success:
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        success = True
        
    if success:
        st.cache_data.clear()
        
    return success

def get_tuesday_for_iso_week(year, week):
    first_day = date(year, 1, 4)
    start_of_year = first_day - timedelta(days=first_day.weekday())
    return start_of_year + timedelta(weeks=week-1, days=1)

df = load_data()

# ---------------------------------------------------------
# SPRAWDŻ CZY DZIŚ JEST WTOREK (Automatyczne okno alertu)
# ---------------------------------------------------------
today = date.today()
is_tuesday = (today.weekday() == 1)

# ---------------------------------------------------------
# OBSŁUGA TYMCZASOWEGO POWIADOMIENIA FANCY (5 MINUT)
# ---------------------------------------------------------
if "fancy_alert" in st.session_state:
    elapsed = time.time() - st.session_state["fancy_alert"]["timestamp"]
    if elapsed > 300:
        del st.session_state["fancy_alert"]

# ---------------------------------------------------------
# NAWIGACJA GŁÓWNA I NAGŁÓWEK
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Sypialnia"

current_room = st.session_state["selected_room"]

st.title("🔥 Sonoff Smart Heating - Panel Sterowania & SSM Analytics")
st.caption(f"Lokalizacja: **{LOCATION_NAME}** | Pełna kontrola kosztów vs Spółdzielnia Mieszkaniowa (SSM)")

# Wyświetlenie fancy powiadomienia, jeśli jest aktywne
if "fancy_alert" in st.session_state:
    fa = st.session_state["fancy_alert"]
    st.markdown(f"""
    <div class="fancy-alert-card">
        <h3 style="margin: 0 0 8px 0; color: #007AFF;">⚡ Sukces! Nowy odczyt zapisany dla strefy: {fa['room']}</h3>
        <p style="margin: 4px 0; font-size: 16px;"><b>Przyrost w tym tygodniu ($\Delta U$):</b> <span style="color: #34C759; font-weight: 700;">+{fa['delta']:.1f} U</span> ({fa['delta']*EST_PLN_PER_UNIT:.2f} PLN)</p>
        <p style="margin: 4px 0; font-size: 16px;"><b>Porównanie tydzień do tygodnia:</b> <span style="color: {'#34C759' if fa['diff_vs_prev'] <= 0 else '#FF3B30'}; font-weight: 700;">{fa['diff_vs_prev']:+.1f}%</span> względem poprz. odczytu</p>
        <p style="margin: 4px 0; font-size: 16px;"><b>Całkowity bilans strefy w sezonie:</b> <b style="color: #AF52DE;">{fa['total_room_units']:.1f} U</b> (~{fa['total_room_units']*EST_PLN_PER_UNIT:.2f} PLN)</p>
        <p style="margin: 8px 0 0 0; font-size: 12px; color: #8E8E93;">Komunikat zniknie automatycznie po kilkuset sekundach.</p>
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

# ---------------------------------------------------------
# OBLICZENIA DLA BIEŻĄCEGO POKOJU I MIESZKANIA
# ---------------------------------------------------------
df_room = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"]) if not df.empty else pd.DataFrame()
df_room_sonoff = df_room[df_room["season"].str.contains("Sonoff", na=False)] if not df_room.empty else pd.DataFrame()

if not df_room_sonoff.empty:
    val_start = float(df_room_sonoff.iloc[0]["units_start"])
    last_row = df_room_sonoff.iloc[-1]
    val_end = float(last_row.get("units_end", val_start))
    last_meter = str(last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"]))
    last_date = str(last_row.get("date_entry", "Brak"))
    total_delta_room = df_room_sonoff["delta_units"].sum()
else:
    val_start = 110.4 if current_room == "Pokój Dziecka" else (126.7 if current_room == "Sypialnia" else 0.0)
    val_end = val_start
    last_meter = ROOMS_CONFIG[current_room]["meter_default"]
    last_date = "Brak odczytów"
    total_delta_room = 0.0

last_delta = df_room_sonoff.iloc[-1]["delta_units"] if not df_room_sonoff.empty else 0.0
live_outdoor_temp = get_outdoor_temp()

# JEDNOZNACZNA LOGIKA: Licznik Główny to suma wszystkich pokoi (Salon + Sypialnia + Pokój Dziecka)
if current_room == "Licznik Główny":
    df_sonoff_all_rooms = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")]
    total_delta_room = df_sonoff_all_rooms["delta_units"].sum() if not df_sonoff_all_rooms.empty else 0.0
    val_start = 0.0
    val_end = total_delta_room
    last_meter = "GJ-MAIN-SUMA"

# Obliczenia dla całego mieszkania (Sezon Sonoff)
df_sonoff_all = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")] if not df.empty else pd.DataFrame()
if df_sonoff_all.empty:
    df_sonoff_all = df[df["season"].str.contains("Sonoff", na=False)] if not df.empty else pd.DataFrame()

total_apartment_units = df_sonoff_all["delta_units"].sum() if not df_sonoff_all.empty else 0.0
total_realtime_cost = total_apartment_units * EST_PLN_PER_UNIT

# Liczba zarejestrowanych tygodni w obecnym sezonie
weeks_logged_count = max(1, df_sonoff_all["week_num"].nunique()) if not df_sonoff_all.empty else 1

# OBLICZENIA SPÓŁDZIELNIA (SSM) W CZASIE RZECZYWISTYM
ssm_paid_advances_to_date = (weeks_logged_count / SSM_TOTAL_WEEKS) * SSM_ANNUAL_CO_BUDGET
ssm_net_balance_to_date = ssm_paid_advances_to_date - total_realtime_cost  # Dodatni = NADPŁATA, Ujemny = NIEDOPŁATA
ssm_projected_full_season_cost = (total_realtime_cost / weeks_logged_count) * SSM_TOTAL_WEEKS
ssm_projected_refund_or_extra = SSM_ANNUAL_CO_BUDGET - ssm_projected_full_season_cost

# Koszt na m² lokalu
cost_per_m2_actual = total_realtime_cost / APARTMENT_AREA_M2
ssm_advance_per_m2_to_date = ssm_paid_advances_to_date / APARTMENT_AREA_M2

# Udział procentowy strefy
room_share_pct = 100.0 if current_room == "Licznik Główny" else ((total_delta_room / total_apartment_units * 100) if total_apartment_units > 0 else 0.0)

# ---------------------------------------------------------
# AUTOMATYCZNE OKNO (MODAL) DLA WTORKOWYCH ODCZYTÓW
# ---------------------------------------------------------
if is_tuesday:
    current_year, current_iso_w, _ = today.isocalendar()
    
    already_added_this_week = False
    if not df_room.empty:
        already_added_this_week = ((df_room["week_num"] == current_iso_w) & (df_room["season"] == "2026/2027 (Sonoff - Wtorki)")).any()

    if not already_added_this_week:
        with st.expander(f"🚨 WTOREK – Wymagany Odczyt dla strefy: {current_room} (Tydzień {current_iso_w})", expanded=True):
            st.warning(f"Dziś jest wtorek! Podaj aktualny stan podzielnika dla strefy **{current_room}**, aby zsynchronizować aplikację.")
            
            with st.form("auto_tuesday_modal_form"):
                m_input = st.text_input("Numer Podzielnika", value=last_meter)
                u_s = st.number_input("Stały Stan Początkowy Sezonu", min_value=0.0, value=val_start, disabled=True)
                u_e = st.number_input("Wartość Końcowa (Z dzisiejszego wtorku)", min_value=0.0, value=max(val_end, val_start), step=0.1)
                m_tag = st.selectbox("Tryb pracy grzania", MODES, index=0)
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    gj_s_m = st.number_input("Licznik Główny Początek [GJ]", min_value=0.0, value=0.0, step=0.01)
                with col_g2:
                    gj_e_m = st.number_input("Licznik Główny Koniec [GJ]", min_value=0.0, value=0.0, step=0.01)
                
                modal_notes = st.text_input("Uwagi / Nastawa", value="Wtorkowa synchronizacja automatyczna")

                if st.form_submit_button("⚡ Zapisz i zsynchronizuj aplikację", use_container_width=True):
                    prev_val_end = val_end if not df_room_sonoff.empty else val_start
                    delta_u_m = u_e - prev_val_end
                    
                    if delta_u_m < 0:
                        delta_u_m = 0.0
                        modal_notes = f"{modal_notes} [Auto-korekta: ujemna delta]" if modal_notes else "[Auto-korekta: ujemna delta]"
                        
                    delta_g_m = gj_e_m - gj_s_m if gj_e_m > gj_s_m else 0.0

                    if u_e < prev_val_end:
                        st.error("Wartość końcowa nie może być mniejsza od poprzedniego stanu licznika!")
                    else:
                        next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1
                        new_row_modal = pd.DataFrame([{
                            "id": next_id,
                            "season": "2026/2027 (Sonoff - Wtorki)",
                            "week_num": current_iso_w,
                            "period_label": f"Tydzień {current_iso_w:02d} (Wtorek)",
                            "date_entry": str(today),
                            "room_name": current_room,
                            "meter_number": m_input,
                            "units_start": prev_val_end,
                            "units_end": u_e,
                            "delta_units": delta_u_m,
                            "gj_start": gj_s_m,
                            "gj_end": gj_e_m,
                            "delta_gj": delta_g_m,
                            "temp_zewnetrzna": live_outdoor_temp,
                            "mode_tag": m_tag,
                            "notes": modal_notes
                        }])

                        df = pd.concat([df, new_row_modal], ignore_index=True)
                        if save_data(df, commit_message=f"Automatyczny odczyt wtorkowy: {current_room} T{current_iso_w}"):
                            prev_delta = last_delta if last_delta > 0 else 1.0
                            diff_vs_prev = ((delta_u_m - prev_delta) / prev_delta * 100) if prev_delta > 0 else 0.0
                            new_total_room = total_delta_room + delta_u_m
                            
                            st.session_state["fancy_alert"] = {
                                "timestamp": time.time(),
                                "room": current_room,
                                "delta": delta_u_m,
                                "diff_vs_prev": diff_vs_prev,
                                "total_room_units": new_total_room
                            }
                            st.success("Zapisano pomyślnie! Synchronizuję aplikację...")
                            st.rerun()

# ---------------------------------------------------------
# KARTA INFORMACYJNA (iOS 18 GLASSMORPHISM)
# ---------------------------------------------------------
room_desc_subtitle = "Suma wszystkich pokoi w mieszkaniu" if current_room == "Licznik Główny" else f"Pojedyncza strefa grzewcza ({room_share_pct:.1f}% udziału w mieszkaniu)"

st.markdown(f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 12px;">
        <div>
            <div class="room-header">
                {ROOMS_CONFIG[current_room]['icon']} Strefa: <b>{current_room}</b> 
                <span class="meter-badge">{last_meter}</span>
            </div>
            <div style="font-size: 13px; color: #8E8E93; margin-top: 2px;">ℹ️ {room_desc_subtitle}</div>
        </div>
        <div class="ios-live-badge">
            🌡️ Temp. zewn. (Bytków): <b style="color: #007AFF;">{live_outdoor_temp}°C</b> &nbsp;|&nbsp; 📊 Udział w mieszkaniu: <b style="color: #AF52DE;">{room_share_pct:.1f}%</b>
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
            <div class="val-title">Ostatni Przyrost (ΔU)</div>
            <div class="val-num" style="color: #34C759;">+{last_delta:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Suma Sezon Strefa</div>
            <div class="val-num" style="color: #AF52DE;">{total_delta_room:.1f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# WIDŻETY KPI (SSM REAL-TIME + PRZELICZNIK M² + EFEKTYWNOŚĆ)
# ---------------------------------------------------------
unique_weeks = sorted(df_sonoff_all["week_num"].unique()) if not df_sonoff_all.empty else []
if len(unique_weeks) >= 2:
    w_last = unique_weeks[-1]
    w_prev = unique_weeks[-2]
    cost_last = df_sonoff_all[df_sonoff_all["week_num"] == w_last]["delta_units"].sum() * EST_PLN_PER_UNIT
    cost_prev = df_sonoff_all[df_sonoff_all["week_num"] == w_prev]["delta_units"].sum() * EST_PLN_PER_UNIT
    diff_pct = ((cost_last - cost_prev) / cost_prev * 100) if cost_prev > 0 else 0.0
    trend_str = f"{diff_pct:+.1f}% tyg. do tyg."
else:
    trend_str = "Brak danych historycznych"

# Status rozliczenia ze spółdzielnią
if ssm_net_balance_to_date >= 0:
    ssm_status_html = f"<span style='color: #34C759; font-weight: 800;'>🟢 NADPŁATA: +{ssm_net_balance_to_date:.2f} PLN</span>"
    ssm_subtext = "Refundacja gotówki ze Spółdzielni"
else:
    ssm_status_html = f"<span style='color: #FF3B30; font-weight: 800;'>🔴 NIEDOPŁATA: {ssm_net_balance_to_date:.2f} PLN</span>"
    ssm_subtext = "Wymagana dopłata na koniec sezonu"

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
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Zaliczka SSM: <b>{ssm_advance_per_m2_to_date:.2f} zł/m²</b> (Oszczędność: {ssm_advance_per_m2_to_date - cost_per_m2_actual:+.2f} zł)</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col3:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">🔮 Prognoza Końcowa Sezonu SSM</div>
        <div class="val-num" style="color: {'#34C759' if ssm_projected_refund_or_extra >= 0 else '#FF3B30'}; font-size: 22px;">
            {'ZWROT: +' if ssm_projected_refund_or_extra >= 0 else 'DOPŁATA: '}{ssm_projected_refund_or_extra:.2f} PLN
        </div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Szacowany koszt 7 mc-y: <b>{ssm_projected_full_season_cost:.1f} zł</b> (Budżet: {SSM_ANNUAL_CO_BUDGET:.1f} zł)</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR: FORMULARZ + SYMULATOR + ROI + BUFOR BEZPIECZEŃSTWA
# ---------------------------------------------------------
with st.sidebar:
    st.header("📥 Nowy Odczyt (Ręczny)")
    st.caption(f"Strefa: **{current_room}**")

    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    current_year, current_iso_w, _ = date.today().isocalendar()
    week_input = st.number_input("Tydzień Roku (1 - 52)", min_value=1, max_value=52, value=current_iso_w)
    
    tuesday_date = get_tuesday_for_iso_week(2026, week_input)
    period_tag = f"Tydzień {week_input:02d} (Wtorek)"

    st.info(f"📆 Domyślny Wtorek: **{tuesday_date.strftime('%d.%m.%Y')}**")

    with st.form("tuesday_form"):
        meter_input = st.text_input("Numer Podzielnika", value=last_meter)
        
        st.markdown("---")
        st.markdown("##### 🔢 Stan Podzielnika [U]")
        u_start = st.number_input("Stały Stan Początkowy Sezonu", min_value=0.0, value=val_start, disabled=True)
        u_end = st.number_input("Wartość Końcowa (z Wtorku)", min_value=0.0, value=max(val_end, val_start), step=0.1)
        mode_input = st.selectbox("Tryb pracy / Tag", MODES, index=0)
        
        st.markdown("---")
        st.markdown("##### 🏢 Licznik Główny [GJ]")
        gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
        gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)

        entry_date = st.date_input("Data wpisu", tuesday_date)
        notes = st.text_input("Nastawa / Uwagi", value="Sonoff Auto 20.5°C")

        if st.form_submit_button("⚡ Zapisz i Synchronizuj", use_container_width=True):
            prev_val_end = val_end if not df_room_sonoff.empty else val_start
            delta_u = u_end - prev_val_end
            
            if delta_u < 0:
                delta_u = 0.0
                notes = f"{notes} [Auto-korekta: ujemna delta]" if notes else "[Auto-korekta: ujemna delta]"
                
            delta_g = gj_e - gj_s if gj_e > gj_s else 0.0

            if u_end < prev_val_end:
                st.error("Wartość końcowa nie może być mniejsza od poprzedniego stanu licznika!")
            else:
                next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1

                new_row = pd.DataFrame([{
                    "id": next_id,
                    "season": season_input,
                    "week_num": week_input,
                    "period_label": period_tag,
                    "date_entry": str(entry_date),
                    "room_name": current_room,
                    "meter_number": meter_input,
                    "units_start": prev_val_end,
                    "units_end": u_end,
                    "delta_units": delta_u,
                    "gj_start": gj_s,
                    "gj_end": gj_e,
                    "delta_gj": delta_g,
                    "temp_zewnetrzna": live_outdoor_temp,
                    "mode_tag": mode_input,
                    "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Wtorkowy odczyt: {current_room} T{week_input}"):
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
                    st.success("Zapisano i zsynchronizowano pomyślnie!")
                    st.rerun()

    # SYMULATOR OSZCZĘDNOŚCI
    st.markdown("---")
    st.header("🎛️ Symulator „Co jeśli?”")
    temp_change_slider = st.slider(
        "Zmiana temp. w mieszkaniu [°C]", 
        min_value=-3.0, 
        max_value=3.0, 
        value=0.0, 
        step=0.5, 
        help="Ujemne wartości (-) to redukcja temperatury (oszczędność), dodatnie (+) to podwyższenie (wyższy koszt)."
    )
    
    simulated_diff_units = total_apartment_units * (temp_change_slider * 0.07)
    simulated_diff_pln = simulated_diff_units * EST_PLN_PER_UNIT

    if temp_change_slider < 0:
        st.success(f"💡 Obniżenie o **{abs(temp_change_slider)}°C** da ok. **{abs(simulated_diff_units):.1f} U** oszczędności (~**{abs(simulated_diff_pln):.2f} PLN** w sezonie).")
    elif temp_change_slider > 0:
        st.error(f"⚠️ Podwyższenie o **+{temp_change_slider}°C** zwiększy zużycie o ok. **+{simulated_diff_units:.1f} U** (~**+{simulated_diff_pln:.2f} PLN** w sezonie).")
    else:
        st.info("💡 Suwak w pozycji 0.0°C – brak zmian względem obecnego stanu.")

    # WIDŻET ROI - ZWROT Z INWESTYCJI SONOFF
    st.markdown("---")
    st.header("💡 Zwrot z Inwestycji (ROI)")
    HARDWARE_COST_EST = 550.0
    df_base_sum = df[df["season"].str.contains("Bazowy", na=False)]["delta_units"].sum() if not df.empty else 0.0
    total_saved_units = max(0.0, df_base_sum - total_apartment_units) if df_base_sum > 0 else 0.0
    total_saved_pln = total_saved_units * EST_PLN_PER_UNIT
    
    payback_ratio = min(1.0, total_saved_pln / HARDWARE_COST_EST) if HARDWARE_COST_EST > 0 else 1.0
    st.caption(f"Koszt zakupu sprzętu Sonoff: **~{HARDWARE_COST_EST:.0f} PLN**")
    st.progress(payback_ratio, text=f"Spłacono: {total_saved_pln:.2f} PLN ({payback_ratio*100:.1f}%)")

    # WSKAŹNIK BUFORA BEZPIECZEŃSTWA (NOWOŚĆ)
    weekly_avg_cost = total_realtime_cost / weeks_logged_count if weeks_logged_count > 0 else 1.0
    buffer_weeks = max(0.0, ssm_net_balance_to_date / weekly_avg_cost) if weekly_avg_cost > 0 else 0.0
    st.caption(f"🛡️ Bufor bezpiecznego grzania z zaliczek: **{buffer_weeks:.1f} tyg.**")

    # Undo
    if not df.empty:
        st.markdown("---")
        if st.button("↩️ Cofnij ostatni wpis w bazie", use_container_width=True):
            df = df.iloc[:-1]
            save_data(df, "Cofnięcie ostatniego wpisu (Undo)")
            st.warning("Usunięto ostatni wpis z bazy!")
            st.rerun()

    st.markdown("---")
    with st.expander("🛠️ Panel Debug & Opcje Zaawansowane"):
        st.warning("Opcje bezpośrednie – brak wymogu podawania PIN-u.")
        if st.button("🔄 Reset bazy do stanu początkowego", use_container_width=True):
            df_reset = create_initial_df()
            save_data(df_reset, "Reset bazy do stanu zero")
            st.success("Zresetowano bazę pomyślnie!")
            st.rerun()

# ---------------------------------------------------------
# ZAKŁADKI ANALITYCZNE
# ---------------------------------------------------------
tab_charts, tab_season_comp, tab_analytics, tab_ai_pred, tab_history = st.tabs([
    "📈 Wykres, Skumulowany & Pogoda", 
    "📊 Porównanie Sezonów i Koszt Narastający",
    "💸 Zyski i Straty & Heatmapa", 
    "🤖 Predykcja AI i Raport", 
    "📋 Historia i Edycja Wpisów"
])

with tab_charts:
    if current_room == "Licznik Główny":
        st.markdown("#### Korelacja Zużycia Licznika Głównego (Suma Stref [U] oraz Energia [GJ])")
    else:
        st.markdown(f"#### Korelacja Zużycia ΔU oraz Temperatury Zewnętrznej dla: **{current_room}**")
        
    if not df_room.empty:
        fig_dual = px_go.Figure()
        has_gj = (df_room["delta_gj"].sum() > 0)
        
        fig_dual.add_trace(px_go.Bar(
            x=df_room["period_label"], y=df_room["delta_units"], name="Zużycie Strefy [U]" if current_room != "Licznik Główny" else "Suma Wszystkich Pokoi [U]", marker_color="#007AFF"
        ))
        
        if current_room == "Licznik Główny" and has_gj:
            fig_dual.add_trace(px_go.Scatter(
                x=df_room["period_label"], y=df_room["delta_gj"], name="Energia Cieplna [GJ]", mode="lines+markers", yaxis="y2", line=dict(color="#FF3B30", width=3)
            ))
            y2_title = "Ciepło Główna [GJ]"
        else:
            fig_dual.add_trace(px_go.Scatter(
                x=df_room["period_label"], y=df_room["temp_zewnetrzna"], name="Temp. Zewn. [°C]", mode="lines+markers", yaxis="y2", line=dict(color="#FF9500", width=3)
            ))
            y2_title = "Temperatura [°C]"

        fig_dual.update_layout(
            template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(title="Zużycie [Jednostki U]"), yaxis2=dict(title=y2_title, overlaying="y", side="right"),
            height=360, legend=dict(orientation="h", y=1.1, x=0.2)
        )
        st.plotly_chart(fig_dual, use_container_width=True)
    else:
        st.info("Brak danych dla wybranego pokoju.")

    st.markdown("---")
    st.markdown("#### 🏗️ Struktura Zużycia w Całym Mieszkaniu (Wykres Skumulowany Pokoi)")
    st.caption("Wyjaśnienie: Wykres przedstawia tygodniowy udział każdego pokoju. Ich łączna wysokość daje pełny wynik Licznika Głównego.")
    
    if not df.empty:
        df_stack = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")]
        if not df_stack.empty:
            fig_stack = px.bar(
                df_stack, x="period_label", y="delta_units", color="room_name",
                title="Suma zużycia w podziale na strefy (Salon + Sypialnia + Pokój Dziecka)",
                labels={"period_label": "Tydzień", "delta_units": "Zużycie [U]", "room_name": "Strefa"},
                barmode="stack"
            )
            fig_stack.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=380)
            st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.info("Brak danych skumulowanych dla sezonu Sonoff.")

with tab_season_comp:
    st.markdown("### 📊 Porównanie Sezonów, Koszt Narastający & Linie Zaliczek SSM")
    st.caption("Wyjaśnienie: Linia przerywana przedstawia zgromadzone wpłaty zaliczek do Spółdzielni. Przebieg zużycia poniżej tej linii oznacza bezpośredni zwrot gotówki.")
    
    if not df.empty:
        col_sc1, col_sc2 = st.columns(2)
        with col_sc1:
            df_comp = df[df["room_name"] != "Licznik Główny"].groupby(["week_num", "season"])["delta_units"].sum().reset_index()
            fig_season = px.line(
                df_comp, x="week_num", y="delta_units", color="season",
                markers=True, title="Zużycie tygodniowe: Obecny Sezon vs Bazowy",
                labels={"week_num": "Tydzień Roku", "delta_units": "Suma Mieszkania [U]", "season": "Sezon"}
            )
            fig_season.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=360)
            st.plotly_chart(fig_season, use_container_width=True)

        with col_sc2:
            df_cum = df[df["room_name"] != "Licznik Główny"].groupby(["season", "week_num"])["delta_units"].sum().groupby(level=0).cumsum().reset_index()
            df_cum["cumulative_pln"] = df_cum["delta_units"] * EST_PLN_PER_UNIT
            
            fig_cum = px_go.Figure()
            for season_name in df_cum["season"].unique():
                sub_df = df_cum[df_cum["season"] == season_name]
                fig_cum.add_trace(px_go.Scatter(
                    x=sub_df["week_num"], y=sub_df["cumulative_pln"], name=season_name, mode="lines+markers"
                ))
            
            # Linia zaliczek SSM
            weeks_seq = list(df_cum["week_num"].unique())
            ssm_advances_line = [(w / SSM_TOTAL_WEEKS) * SSM_ANNUAL_CO_BUDGET for w in weeks_seq]
            fig_cum.add_trace(px_go.Scatter(
                x=weeks_seq, y=ssm_advances_line, name="💰 Skumulowane Wpłaty Zaliczek SSM",
                line=dict(color="#34C759", width=3, dash="dash")
            ))

            fig_cum.update_layout(
                title="Skumulowany Koszt vs Wpłacone Zaliczki SSM [PLN]",
                xaxis_title="Tydzień Roku", yaxis_title="Koszt Narastający [PLN]",
                template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=360
            )
            st.plotly_chart(fig_cum, use_container_width=True)
    else:
        st.info("Brak wystarczających danych do porównania sezonów.")

with tab_analytics:
    st.markdown("### 💸 Bilans Finansowy, Heatmapa oraz Analiza Trybów Grzania")
    
    if not df.empty:
        df_sonoff = df[df["season"].str.contains("Sonoff", na=False) & (df["room_name"] != "Licznik Główny")].copy()
        df_base = df[df["season"].str.contains("Bazowy", na=False) & (df["room_name"] != "Licznik Główny")].copy()

        df_weekly = df_sonoff.groupby(["week_num", "period_label"])["delta_units"].sum().reset_index()
        df_weekly_base = df_base.groupby(["week_num"])["delta_units"].sum().reset_index().rename(columns={"delta_units": "base_units"})
        
        df_merged = pd.merge(df_weekly, df_weekly_base, on="week_num", how="left").fillna(0)
        df_merged["units_saved"] = df_merged["base_units"] - df_merged["delta_units"]
        df_merged["pln_balance"] = df_merged["units_saved"] * EST_PLN_PER_UNIT
        df_merged["color"] = df_merged["pln_balance"].apply(lambda x: "#34C759" if x >= 0 else "#FF3B30")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 🟢 Tygodniowe Oszczędności PLN (Zielony = Zysk)")
            fig_bal = px_go.Figure()
            fig_bal.add_trace(px_go.Bar(
                x=df_merged["period_label"], y=df_merged["pln_balance"],
                marker_color=df_merged["color"], text=df_merged["pln_balance"].apply(lambda x: f"{x:.1f} zł"), textposition="outside"
            ))
            fig_bal.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320)
            st.plotly_chart(fig_bal, use_container_width=True)

        with col_b:
            st.markdown("#### 🍩 Podział Zużycia według Trybów Grzania (Tags)")
            if not df_sonoff.empty:
                df_mode_pie = df_sonoff.groupby("mode_tag")["delta_units"].sum().reset_index()
                fig_pie = px.pie(
                    df_mode_pie, values="delta_units", names="mode_tag", hole=0.45,
                    title="Udział trybów pracy w łącznym zużyciu",
                    color_discrete_sequence=["#007AFF", "#34C759", "#FF9500", "#AF52DE"]
                )
                fig_pie.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Brak danych o trybach pracy.")

        st.markdown("---")
        st.markdown("#### 🔥 Macierz Korelacji (Temperatura Zewnętrzna vs Zużycie Mieszkania)")
        if len(df_sonoff) >= 2:
            fig_heat = px.density_heatmap(
                df_sonoff, x="temp_zewnetrzna", y="delta_units", z="delta_units",
                histfunc="avg", title="Intensywność poboru energii w zależności od temperatury na zewnątrz",
                labels={"temp_zewnetrzna": "Temp. Zewnętrzna [°C]", "delta_units": "Średnie Zużycie Strefy [U]"}
            )
            fig_heat.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300)
            st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Brak danych analitycznych.")

with tab_ai_pred:
    st.markdown("### 🤖 Predykcja AI, Wykrywanie Anomalii & Prędkościomierz Budżetowy SSM")
    
    # SILNIK ANOMALII
    anomaly_detected = False
    anomaly_msg = ""
    if not df_room_sonoff.empty and len(df_room_sonoff) >= 2:
        last_u = df_room_sonoff.iloc[-1]["delta_units"]
        prev_u = df_room_sonoff.iloc[-2]["delta_units"]
        last_temp = df_room_sonoff.iloc[-1]["temp_zewnetrzna"]
        prev_temp = df_room_sonoff.iloc[-2]["temp_zewnetrzna"]
        
        if prev_u > 0 and (last_u - prev_u) / prev_u > 0.25 and last_temp >= prev_temp:
            anomaly_detected = True
            anomaly_msg = f"Wykryto skok zużycia w strefie {current_room} (+{((last_u-prev_u)/prev_u)*100:.1f}%) przy wyższej temp. zewn. ({last_temp}°C). Sprawdź wietrzenie lub nastawy."

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown("#### 🧠 Analiza Zachowania Systemu i Prognoza SSM")
        if anomaly_detected:
            st.error(f"⚠️ **Alert Inteligentnego Wykrywania Anomalii:**\n\n{anomaly_msg}")
        else:
            st.success("✅ **Stan Normalny (Brak Anomalii):**\n\nZużycie we wszystkich strefach jest stabilne i współgra z aktualną pogodą w Bytkowie.")
            
        st.info("💡 **Szczegółowy Raport Rozliczeniowy ze Spółdzielnią:**\n\n"
                f"- Łączny budżet zaliczkowy CO na ten sezon wynosi **{SSM_ANNUAL_CO_BUDGET:.2f} PLN**.\n"
                f"- Przy aktualnym tempie całkowity koszt wyniesie **~{ssm_projected_full_season_cost:.2f} PLN**.\n"
                f"- Przewidywany wynik końcowy rozliczenia z SSM: **{'ZWROT +' if ssm_projected_refund_or_extra>=0 else 'DOPŁATA '}{ssm_projected_refund_or_extra:.2f} PLN**.")
                
    with col_p2:
        st.markdown("#### ⏱️ Prędkościomierz Wykorzystania Zaliczki SSM")
        fig_gauge = px_go.Figure(px_go.Indicator(
            mode="gauge+number+delta",
            value=total_realtime_cost,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Zużycie Budżetu CO (PLN)", 'font': {'size': 16}},
            delta={'reference': ssm_paid_advances_to_date, 'increasing': {'color': "red"}},
            gauge={
                'axis': {'range': [None, SSM_ANNUAL_CO_BUDGET], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "#007AFF"},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, SSM_ANNUAL_CO_BUDGET*0.6], 'color': 'rgba(52, 199, 89, 0.2)'},
                    {'range': [SSM_ANNUAL_CO_BUDGET*0.6, SSM_ANNUAL_CO_BUDGET*0.9], 'color': 'rgba(255, 149, 0, 0.2)'},
                    {'range': [SSM_ANNUAL_CO_BUDGET*0.9, SSM_ANNUAL_CO_BUDGET], 'color': 'rgba(255, 59, 48, 0.2)'}
                ]
            }
        ))
        fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

with tab_history:
    st.markdown("### 📋 Zarządzanie i Historia Wpisów (Edycja / Usuwanie)")
    st.caption("Wyjaśnienie: Zbiór wszystkich wtorkowych odczytów zebranych z podzielników oraz licznika głównego.")
    
    if df.empty:
        st.info("Baza danych jest pusta.")
    else:
        st.write("Zaznacz wiersze w kolumnie **Zaznacz**, aby je usunąć, lub pobierz historię do pliku CSV.")
        
        df_editable = df.copy()
        if "Zaznacz" not in df_editable.columns:
            df_editable.insert(0, "Zaznacz", False)

        edited_table = st.data_editor(
            df_editable,
            use_container_width=True,
            hide_index=True,
            column_config={"Zaznacz": st.column_config.CheckboxColumn(required=True)}
        )

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            if st.button("🗑️ Usuń zaznaczone wiersze z bazy", type="primary"):
                rows_to_keep = edited_table[edited_table["Zaznacz"] == False]
                rows_to_keep = rows_to_keep.drop(columns=["Zaznacz"])
                save_data(rows_to_keep, "Usunięto wybrane wiersze z tabeli")
                st.success("Zaznaczone wpisy zostały usunięte!")
                st.rerun()

        with col_h2:
            csv_export = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Pobierz pełną historię CSV",
                data=csv_export,
                file_name="sonoff_heating_history.csv",
                mime="text/csv",
                use_container_width=True
            )
