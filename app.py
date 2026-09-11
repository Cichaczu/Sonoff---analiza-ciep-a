import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from github import Github, GithubException
import io
import os
from datetime import date, datetime

# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating 2x/Week - Dashboard 2026",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45

# ---------------------------------------------------------
# STYLIZACJA iOS 18 GLASSMORPHISM
# ---------------------------------------------------------
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }
    .main { background-color: #F2F2F7; }

    /* Karta Podglądu Pokoju / Podzielnika (iOS Glass) */
    .ios-room-info-card {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border-radius: 22px;
        padding: 22px 28px;
        border: 1px solid rgba(255, 255, 255, 0.7);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
    }
    .room-header {
        font-size: 20px;
        font-weight: 700;
        color: #1C1C1E;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .meter-badge {
        background: #E5E5EA;
        color: #3A3A3C;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
        font-family: monospace;
    }
    .val-box {
        background: #F8F9FA;
        border-radius: 14px;
        padding: 12px 16px;
        border: 1px solid #E5E5EA;
        text-align: center;
    }
    .val-title {
        font-size: 11px;
        text-transform: uppercase;
        color: #8E8E93;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .val-num {
        font-size: 24px;
        font-weight: 800;
        color: #007AFF;
    }
    
    /* Dynamic Balance Banner */
    .ios-balance-plus {
        background: linear-gradient(135deg, rgba(52, 199, 89, 0.15) 0%, rgba(255, 255, 255, 0.95) 100%);
        border: 2px solid #34C759;
        border-radius: 20px;
        padding: 16px 22px;
        margin-bottom: 20px;
        box-shadow: 0 8px 25px rgba(52, 199, 89, 0.15);
    }
    .ios-balance-minus {
        background: linear-gradient(135deg, rgba(255, 59, 48, 0.15) 0%, rgba(255, 255, 255, 0.95) 100%);
        border: 2px solid #FF3B30;
        border-radius: 20px;
        padding: 16px 22px;
        margin-bottom: 20px;
        box-shadow: 0 8px 25px rgba(255, 59, 48, 0.15);
    }

    /* Tabs & Buttons */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #E5E5EA;
        padding: 5px;
        border-radius: 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# KONFIGURACJA POMIESZCZEŃ I POBIERANIE DANYCH
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "meter_default": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter_default": "POD-SYP-2026"},
    "Pokój Dziecka": {"icon": "🧒", "meter_default": "POD-DZI-2026"},
    "Licznik Główny": {"icon": "🏢", "meter_default": "GJ-MAIN-2026"}
}

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff - 2x/Tydzień)"]

def get_github_repo():
    try:
        github_config = st.secrets.get("github", {})
        token = github_config.get("token")
        repo_name = github_config.get("repo")
        if token and repo_name:
            g = Github(token)
            return g.get_repo(repo_name)
    except Exception:
        return None
    return None

def create_empty_df():
    return pd.DataFrame(columns=[
        "id", "season", "week_num", "entry_slot", "period_label", "date_entry",
        "room_name", "meter_number", "units_start", "units_end", "delta_units",
        "gj_start", "gj_end", "delta_gj", "notes"
    ])

def load_data():
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            return pd.read_csv(io.StringIO(file_content.decoded_content.decode('utf-8')))
        except Exception:
            return load_local_fallback()
    return load_local_fallback()

def load_local_fallback():
    if os.path.exists(FILE_PATH):
        try: return pd.read_csv(FILE_PATH)
        except Exception: return create_empty_df()
    df = create_empty_df()
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

df = load_data()

# ---------------------------------------------------------
# NAWIGACJA STREF
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

current_room = st.session_state["selected_room"]

st.title("🔥 Sonoff Smart Heating - Monitor Odczytów (2x / Tydzień)")
st.caption("System automatycznego przyporządkowywania wartości początkowych i końcowych dla podzielników")

# Wybór pomieszczenia
room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (current_room == room_key)
    with room_cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"btn_{room_key}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state["selected_room"] = room_key
            st.rerun()

st.divider()

# ---------------------------------------------------------
# KALKULACJA STANÓW DLA DANEGO POKOJU (NP. SALON)
# ---------------------------------------------------------
df_room = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"])

# Ostatnie znane wartości dla wybranego pokoju
if not df_room.empty:
    last_row = df_room.iloc[-1]
    last_meter = last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"])
    val_start = float(last_row.get("units_start", 0.0))
    val_end = float(last_row.get("units_end", 0.0))
    last_date = str(last_row.get("date_entry", "Brak odczytów"))
    total_delta_room = df_room[df_room["season"] == "2026/2027 (Sonoff - 2x/Tydzień)"]["delta_units"].sum()
else:
    last_meter = ROOMS_CONFIG[current_room]["meter_default"]
    val_start = 0.0
    val_end = 0.0
    last_date = "Brak wpisów"
    total_delta_room = 0.0

# ---------------------------------------------------------
# OKNO INFORMACYJNE POKOJU (DEDYKOWANA KARTA SALON / STREFA)
# ---------------------------------------------------------
st.markdown(f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div class="room-header">
            {ROOMS_CONFIG[current_room]['icon']} Pokój: <b>{current_room}</b> 
            <span class="meter-badge">Nr podzielnika: {last_meter}</span>
        </div>
        <div style="font-size: 13px; color: #8E8E93; font-weight: 500;">
            📅 Ostatni odczyt: <b>{last_date}</b>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;">
        <div class="val-box">
            <div class="val-title">Wartość Początkowa</div>
            <div class="val-num">{val_start:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Wartość Końcowa</div>
            <div class="val-num">{val_end:.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Ostatni Przyrost (ΔU)</div>
            <div class="val-num" style="color: #34C759;">+{(val_end - val_start):.1f} U</div>
        </div>
        <div class="val-box">
            <div class="val-title">Suma Sezon 2026/2027</div>
            <div class="val-num" style="color: #5856D6;">{total_delta_room:.0f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# WIDGET BILANSU ZYSKÓW / STRAT (PLUS / MINUS)
# ---------------------------------------------------------
base_room = df_room[df_room["season"] == "2025/2026 (Bazowy)"]["delta_units"].sum()
diff_units = base_room - total_delta_room
pln_balance = diff_units * EST_PLN_PER_UNIT

if total_delta_room > 0:
    if diff_units >= 0:
        st.markdown(f"""
        <div class="ios-balance-plus">
            <span style="font-size: 18px; font-weight: 800; color: #1E7E34;">🟢 JESTEŚ NA PLUSIE! (+{pln_balance:.2f} PLN)</span><br>
            <span style="font-size: 14px; color: #2C3E50;">
                W strefie <b>{current_room}</b> zaoszczędziłeś <b>{diff_units:.0f} U</b> w porównaniu do okresu bazowego. Głowica Sonoff działa optymalnie.
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ios-balance-minus">
            <span style="font-size: 18px; font-weight: 800; color: #D32F2F;">🔴 JESTEŚ NA MINUSIE ({pln_balance:.2f} PLN)</span><br>
            <span style="font-size: 14px; color: #2C3E50;">
                W strefie <b>{current_room}</b> zużycie wzrosło o <b>{abs(diff_units):.0f} U</b>. Rozważ obniżenie temperatury nocnej do 18.5°C.
            </span>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR: FORMULARZ DODAWANIA WPISÓW 2 RAZY W TYGODNIU
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📥 Nowy Odczyt (2x / Tydzień)")
    st.caption(f"Wprowadzenie wpisu dla: **{current_room}**")

    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    
    current_iso_week = date.today().isocalendar()[1]
    week_input = st.number_input("Tydzień roku (1 - 52)", min_value=1, max_value=52, value=current_iso_week)
    slot_input = st.selectbox("Częstotliwość odczytu", ["Odczyt 1 (Pn - Śr)", "Odczyt 2 (Czw - Ndz)"])
    
    # Automatyczne podpowiedzi wartości początkowej
    suggested_start = val_end if val_end > 0 else 0.0

    with st.form("quick_entry_form"):
        meter_num_input = st.text_input("Numer Podzielnika", value=last_meter)
        
        st.markdown("---")
        st.markdown("##### 🔢 Wartości Podzielnika [U]")
        u_start = st.number_input("Wartość Początkowa", min_value=0.0, value=suggested_start, step=1.0)
        u_end = st.number_input("Wartość Końcowa", min_value=0.0, value=suggested_start + 5.0, step=1.0)
        
        st.markdown("---")
        st.markdown("##### 🏢 Licznik Główny [GJ] (Opcjonalnie)")
        gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
        gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)

        entry_date = st.date_input("Data odczytu", date.today())
        notes = st.text_input("Uwagi / Nastawa TRVZB", value="Sonoff Auto 20.5°C")

        if st.form_submit_button("⚡ Zapisz Odczyt (2x/Tdz)", use_container_width=True):
            delta_u = u_end - u_start
            delta_g = gj_e - gj_s if gj_e > gj_s else 0.0

            if delta_u < 0:
                st.error("Wartość końcowa nie może być mniejsza od początkowej!")
            else:
                next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1
                period_tag = f"T{week_input:02d}-{slot_input[:7]}"

                new_entry = pd.DataFrame([{
                    "id": next_id,
                    "season": season_input,
                    "week_num": week_input,
                    "entry_slot": slot_input,
                    "period_label": period_tag,
                    "date_entry": str(entry_date),
                    "room_name": current_room,
                    "meter_number": meter_num_input,
                    "units_start": u_start,
                    "units_end": u_end,
                    "delta_units": delta_u,
                    "gj_start": gj_s,
                    "gj_end": gj_e,
                    "delta_gj": delta_g,
                    "notes": notes
                }])

                df = pd.concat([df, new_entry], ignore_index=True)
                if save_data(df, commit_message=f"Odczyt 2x/tydzień: {current_room} {period_tag}"):
                    st.success(f"Dodano odczyt dla {current_room} ({period_tag})!")
                    st.rerun()

# ---------------------------------------------------------
# HISTORIA WPISÓW DLA POKOJU
# ---------------------------------------------------------
st.markdown(f"### 📋 Historia Odczytów 2x w Tygodniu: {current_room}")
if not df_room.empty:
    st.dataframe(
        df_room[["date_entry", "period_label", "meter_number", "units_start", "units_end", "delta_units", "notes"]]
        .rename(columns={
            "date_entry": "Data", "period_label": "Okres/Tydzień", "meter_number": "Nr Podzielnika",
            "units_start": "Początek", "units_end": "Koniec", "delta_units": "Zużycie ΔU", "notes": "Uwagi"
        }),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info(f"Brak odczytów dla pomieszczenia {current_room}. Użyj formularza w panelu bocznym po lewej stronie, aby dodać pierwszy wpis.")
