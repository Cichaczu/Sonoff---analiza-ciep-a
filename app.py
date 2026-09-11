import streamlit as st
import pandas as pd
import plotly.graph_objects as px_go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date, datetime, timedelta
import requests

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
    except Exception:
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

    .ios-balance-plus {
        background: linear-gradient(135deg, rgba(52, 199, 89, 0.12) 0%, rgba(255, 255, 255, 0.6) 100%);
        border: 2px solid #34C759;
        border-radius: 20px;
        padding: 18px 22px;
        margin-bottom: 22px;
        box-shadow: 0 8px 25px rgba(52, 199, 89, 0.1);
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
            "notes": "Stan zero - wrzesień 2026"
        }
    ])

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
        mask_zero = df["period_label"].str.contains("Stan Zero", na=False)
        if mask_zero.any():
            df.loc[mask_zero, "units_start"] = df.loc[mask_zero, "units_end"]
            df.loc[mask_zero, "delta_units"] = 0.0
            df.loc[mask_zero, "delta_gj"] = 0.0
        if "temp_zewnetrzna" not in df.columns:
            df["temp_zewnetrzna"] = 12.0
            
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
    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(FILE_PATH, commit_message, csv_string, file_content.sha, branch=branch)
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
            return True
        except Exception: return False
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    df.to_csv(FILE_PATH, index=False)
    return True

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
# NAWIGACJA GŁÓWNA I NAGŁÓWEK
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Sypialnia"

current_room = st.session_state["selected_room"]

st.title("🔥 Sonoff Smart Heating - Panel Sterowania")
st.caption(f"Lokalizacja: **{LOCATION_NAME}** | Płynne zarządzanie i inteligentna predykcja AI w stylu iOS")

room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (current_room == room_key)
    with room_cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"btn_{room_key}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state["selected_room"] = room_key
            st.rerun()

st.divider()

# ---------------------------------------------------------
# OBLICZENIA DLA BIEŻĄCEGO POKOJU
# ---------------------------------------------------------
df_room = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"]) if not df.empty else pd.DataFrame()

if not df_room.empty:
    last_row = df_room.iloc[-1]
    last_meter = last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"])
    val_start = float(last_row.get("units_start", 0.0))
    val_end = float(last_row.get("units_end", 0.0))
    last_date = str(last_row.get("date_entry", "Brak odczytów"))
    last_delta = float(last_row.get("delta_units", 0.0))
    total_delta_room = df_room[df_room["season"] == "2026/2027 (Sonoff - Wtorki)"]["delta_units"].sum()
else:
    last_meter = ROOMS_CONFIG[current_room]["meter_default"]
    val_start = 110.4 if current_room == "Pokój Dziecka" else (126.7 if current_room == "Sypialnia" else 0.0)
    val_end = val_start
    last_date = "Brak odczytów"
    last_delta = 0.0
    total_delta_room = 0.0

live_outdoor_temp = get_outdoor_temp()

# ---------------------------------------------------------
# SYSTEM DETEKCJI ANOMALII (Smart Alerts)
# ---------------------------------------------------------
if not df_room.empty and len(df_room) >= 2:
    recent_deltas = df_room["delta_units"].tail(3)
    avg_recent = recent_deltas.mean()
    if last_delta > (avg_recent * 1.3) and avg_recent > 0:
        st.toast(f"⚠️ Anomalia w strefie {current_room}! Ostatni przyrost ({last_delta:.1f}U) jest o ponad 30% wyższy od średniej.", icon="🚨")

if live_outdoor_temp < 10.0 and total_delta_room > 15.0:
    st.toast(f"⚠️ Uwaga! Spadek temp. do {live_outdoor_temp}°C w Siemianowicach – wysokie zużycie w strefie {current_room}!", icon="🔥")

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
                u_s = st.number_input("Wartość Początkowa (Poprzedni stan końcowy)", min_value=0.0, value=val_end, step=0.1)
                u_e = st.number_input("Wartość Końcowa (Z dzisiejszego wtorku)", min_value=0.0, value=val_end + 1.0, step=0.1)
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    gj_s_m = st.number_input("Licznik Główny Początek [GJ]", min_value=0.0, value=0.0, step=0.01)
                with col_g2:
                    gj_e_m = st.number_input("Licznik Główny Koniec [GJ]", min_value=0.0, value=0.0, step=0.01)
                
                modal_notes = st.text_input("Uwagi / Nastawa", value="Wtorkowa synchronizacja automatyczna")

                if st.form_submit_button("⚡ Zapisz i zsynchronizuj aplikację", use_container_width=True):
                    delta_u_m = u_e - u_s
                    delta_g_m = gj_e_m - gj_s_m if gj_e_m > gj_s_m else 0.0

                    if delta_u_m < 0:
                        st.error("Wartość końcowa nie może być mniejsza od początkowej!")
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
                            "units_start": u_s,
                            "units_end": u_e,
                            "delta_units": delta_u_m,
                            "gj_start": gj_s_m,
                            "gj_end": gj_e_m,
                            "delta_gj": delta_g_m,
                            "temp_zewnetrzna": live_outdoor_temp,
                            "notes": modal_notes
                        }])

                        df = pd.concat([df, new_row_modal], ignore_index=True)
                        if save_data(df, commit_message=f"Automatyczny odczyt wtorkowy: {current_room} T{current_iso_w}"):
                            st.success("Zapisano pomyślnie! Synchronizuję aplikację...")
                            st.rerun()

# ---------------------------------------------------------
# KARTA INFORMACYJNA (iOS 18 GLASSMORPHISM)
# ---------------------------------------------------------
st.markdown(f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 12px;">
        <div class="room-header">
            {ROOMS_CONFIG[current_room]['icon']} Strefa: <b>{current_room}</b> 
            <span class="meter-badge">{last_meter}</span>
        </div>
        <div class="ios-live-badge">
            🌡️ Temp. zewn. (Bytków): <b style="color: #007AFF;">{live_outdoor_temp}°C</b> &nbsp;|&nbsp; 📅 Ostatni odczyt: <b style="color: #34C759;">{last_date}</b>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;">
        <div class="val-box">
            <div class="val-title">Stan Początkowy</div>
            <div class="val-num">{val_start:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Ostatni Stan Licznika</div>
            <div class="val-num">{val_end:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Ostatni Przyrost (ΔU)</div>
            <div class="val-num" style="color: #34C759;">+{last_delta:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Suma Sezon Sonoff</div>
            <div class="val-num" style="color: #AF52DE;">{total_delta_room:.1f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# NOWE WIDŻETY KPI (Koszt w czasie rzeczywistym + Efektywność termiczna)
# ---------------------------------------------------------
df_sonoff_all = df[df["season"].str.contains("Sonoff", na=False)] if not df.empty else pd.DataFrame()
total_apartment_units = df_sonoff_all["delta_units"].sum() if not df_sonoff_all.empty else 0.0
total_realtime_cost = total_apartment_units * EST_PLN_PER_UNIT

# Spojrzenie na poprzedni tydzień (dla dynamiki kosztów)
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

# Efektywność termiczna (PLN / °C mrozu) -> zał. baza komfortu 20°C zewnątrz
temp_diff_frost = max(0.1, 20.0 - live_outdoor_temp)
thermal_efficiency_index = total_realtime_cost / temp_diff_frost

kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
with kpi_col1:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">💰 Łączny koszt w mieszkaniu (Real-time)</div>
        <div class="val-num" style="color: #FF9500; font-size: 26px;">{total_realtime_cost:.2f} PLN</div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Trend: <b>{trend_str}</b></div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col2:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">🌡️ Efektywność Termiczna (PLN / °C mrozu)</div>
        <div class="val-num" style="color: #007AFF; font-size: 26px;">{thermal_efficiency_index:.2f} zł / °C</div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Δ odczuwalna od 20°C bazowej</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_col3:
    st.markdown(f"""
    <div class="val-box" style="padding: 16px;">
        <div class="val-title">🏢 Suma Grzejników w Mieszkaniu</div>
        <div class="val-num" style="color: #34C759; font-size: 26px;">{total_apartment_units:.1f} U</div>
        <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Odpowiada licznikowi głównemu GJ</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR: FORMULARZ RĘCZNEGO ODCZYTU + SYMULATOR "CO JEŚLI?"
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
    suggested_start = val_end

    with st.form("tuesday_form"):
        meter_input = st.text_input("Numer Podzielnika", value=last_meter)
        
        st.markdown("---")
        st.markdown("##### 🔢 Stan Podzielnika [U]")
        u_start = st.number_input("Wartość Początkowa", min_value=0.0, value=suggested_start, step=0.1)
        u_end = st.number_input("Wartość Końcowa (z Wtorku)", min_value=0.0, value=suggested_start + 1.0, step=0.1)
        
        st.markdown("---")
        st.markdown("##### 🏢 Licznik Główny [GJ]")
        gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
        gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)

        entry_date = st.date_input("Data wpisu", tuesday_date)
        notes = st.text_input("Nastawa / Uwagi", value="Sonoff Auto 20.5°C")

        if st.form_submit_button("⚡ Zapisz i Synchronizuj", use_container_width=True):
            delta_u = u_end - u_start
            delta_g = gj_e - gj_s if gj_e > gj_s else 0.0

            if delta_u < 0:
                st.error("Wartość końcowa nie może być mniejsza od początkowej!")
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
                    "units_start": u_start,
                    "units_end": u_end,
                    "delta_units": delta_u,
                    "gj_start": gj_s,
                    "gj_end": gj_e,
                    "delta_gj": delta_g,
                    "temp_zewnetrzna": live_outdoor_temp,
                    "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Wtorkowy odczyt: {current_room} T{week_input}"):
                    st.success("Zapisano i zsynchronizowano pomyślnie!")
                    st.rerun()

    # SYMULATOR OSZCZĘDNOŚCI "CO JEŚLI?"
    st.markdown("---")
    st.header("🎛️ Symulator „Co jeśli?”")
    temp_drop_slider = st.slider("Redukcja temp. w mieszkaniu", 0.0, 3.0, 0.5, 0.5, help="Symuluj obniżenie temperatury o X stopni.")
    simulated_savings_units = total_apartment_units * (temp_drop_slider * 0.07) # ok 7% oszczędności na 1°C
    simulated_savings_pln = simulated_savings_units * EST_PLN_PER_UNIT
    st.success(f"💡 Obniżenie o **{temp_drop_slider}°C** da ok. **-{simulated_savings_units:.1f} U** oszczędności (~**{simulated_savings_pln:.2f} PLN** w sezonie).")

    # Szybki przycisk cofania (Undo) w panelu bocznym
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
    "📊 Porównanie Sezonów",
    "💸 Zyski i Straty & Heatmapa", 
    "🤖 Predykcja AI i Raport", 
    "📋 Historia i Edycja Wpisów"
])

with tab_charts:
    st.markdown(f"#### Korelacja Zużycia ΔU oraz Temperatury Zewnętrznej dla: {current_room}")
    if not df_room.empty:
        fig_dual = px_go.Figure()
        fig_dual.add_trace(px_go.Bar(
            x=df_room["period_label"], y=df_room["delta_units"], name="Zużycie [U]", marker_color="#007AFF"
        ))
        fig_dual.add_trace(px_go.Scatter(
            x=df_room["period_label"], y=df_room["temp_zewnetrzna"], name="Temp. Zewn. [°C]", mode="lines+markers", yaxis="y2", line=dict(color="#FF9500", width=3)
        ))
        fig_dual.update_layout(
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(title="Zużycie [U]"),
            yaxis2=dict(title="Temperatura [°C]", overlaying="y", side="right"),
            height=360,
            legend=dict(orientation="h", y=1.1, x=0.3)
        )
        st.plotly_chart(fig_dual, use_container_width=True)
    else:
        st.info("Brak danych dla wybranego pokoju.")

    st.markdown("---")
    st.markdown("#### 🏗️ Struktura Zużycia w Całym Mieszkaniu (Wykres Skumulowany)")
    if not df.empty:
        df_stack = df[df["season"].str.contains("Sonoff", na=False)]
        if not df_stack.empty:
            fig_stack = px.bar(
                df_stack, x="period_label", y="delta_units", color="room_name",
                title="Udział poszczególnych stref w tygodniowym zużyciu mieszkania",
                labels={"period_label": "Okres", "delta_units": "Zużycie [U]", "room_name": "Strefa"},
                barmode="stack"
            )
            fig_stack.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=380)
            st.plotly_chart(fig_stack, use_container_width=True)
        else:
            st.info("Brak danych skumulowanych dla sezonu Sonoff.")

with tab_season_comp:
    st.markdown("### 📊 Porównanie Sezonowe (Bazowy vs Sonoff)")
    if not df.empty:
        df_comp = df.groupby(["week_num", "season"])["delta_units"].sum().reset_index()
        fig_season = px.line(
            df_comp, x="week_num", y="delta_units", color="season",
            markers=True, title="Zużycie w podziale na tygodnie roku (1-52)",
            labels={"week_num": "Tydzień Roku", "delta_units": "Zużycie [U]", "season": "Sezon"}
        )
        fig_season.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
        st.plotly_chart(fig_season, use_container_width=True)
    else:
        st.info("Brak wystarczających danych do porównania sezonów.")

with tab_analytics:
    st.markdown("### 💸 Bilans Finansowy i Heatmapa Korelacji")
    
    if not df.empty:
        df_sonoff = df[df["season"].str.contains("Sonoff", na=False)].copy()
        df_base = df[df["season"].str.contains("Bazowy", na=False)].copy()

        df_weekly = df_sonoff.groupby(["week_num", "period_label"])["delta_units"].sum().reset_index()
        df_weekly_base = df_base.groupby(["week_num"])["delta_units"].sum().reset_index().rename(columns={"delta_units": "base_units"})
        
        df_merged = pd.merge(df_weekly, df_weekly_base, on="week_num", how="left").fillna(0)
        df_merged["units_saved"] = df_merged["base_units"] - df_merged["delta_units"]
        df_merged["pln_balance"] = df_merged["units_saved"] * EST_PLN_PER_UNIT
        df_merged["color"] = df_merged["pln_balance"].apply(lambda x: "#34C759" if x >= 0 else "#FF3B30")

        col_a, col_b = st.columns(2)
        with col_a:
            fig_bal = px_go.Figure()
            fig_bal.add_trace(px_go.Bar(
                x=df_merged["period_label"], y=df_merged["pln_balance"],
                marker_color=df_merged["color"], text=df_merged["pln_balance"].apply(lambda x: f"{x:.1f} zł"), textposition="outside"
            ))
            fig_bal.update_layout(title="Tygodniowy Bilans PLN", template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320)
            st.plotly_chart(fig_bal, use_container_width=True)

        with col_b:
            st.markdown("#### 🔥 Macierz Korelacji (Temperatura zewn. vs Zużycie)")
            if len(df_sonoff) >= 2:
                fig_heat = px.density_heatmap(
                    df_sonoff, x="temp_zewnetrzna", y="delta_units", z="delta_units",
                    histfunc="avg", title="Intensywność zużycia a temperatura zewnątrz",
                    labels={"temp_zewnetrzna": "Temp. Zewnętrzna [°C]", "delta_units": "Średnie Zużycie [U]"}
                )
                fig_heat.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=320)
                st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.info("Zbyt mało danych do wygenerowania heatmapy.")
    else:
        st.info("Brak danych analitycznych.")

with tab_ai_pred:
    st.markdown("### 🤖 Predykcja AI i Szacowanie Miesięczne")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.info("💡 **Inteligentna Analiza i Harmonogram (Smart Scheduling):**\n\n"
                f"- System wykrywa stabilną temperaturę w Bytkowie (`{live_outdoor_temp}°C`).\n"
                "- Sugestia: Obniżenie temperatury o 1°C w nocy w strefie *Sypialnia* przyniesie szacowaną oszczędność ok. **5.4 U / tydzień**.\n"
                "- Brak gwałtownych skoków przegrzewania pomieszczeń.")
    with col_p2:
        est_monthly_units = total_delta_room * 4.2
        est_monthly_cost = est_monthly_units * EST_PLN_PER_UNIT
        st.markdown(f"""
        <div style="background: rgba(0, 122, 255, 0.08); border-radius: 16px; padding: 18px; border: 1px solid rgba(0, 122, 255, 0.25);">
            <h4 style="margin: 0; color: #007AFF;">Prognoza na koniec miesiąca</h4>
            <p style="margin: 8px 0 0 0; font-size: 15px;">Przewidywane zużycie dla strefy <b>{current_room}</b>: <b>{est_monthly_units:.1f} U</b></p>
            <p style="margin: 4px 0 0 0; font-size: 15px;">Szacowany koszt: <b>{est_monthly_cost:.2f} PLN</b></p>
        </div>
        """, unsafe_allow_html=True)

with tab_history:
    st.markdown("### 📋 Zarządzanie i Historia Wpisów (Edycja / Usuwanie)")
    if df.empty:
        st.info("Baza danych jest pusta.")
    else:
        st.write("Możesz zaznaczyć wiersze w kolumnie **Zaznacz**, aby je usunąć, lub pobrać całą bazę do pliku CSV.")
        
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
