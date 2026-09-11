import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from github import Github, GithubException
import io
import os
from datetime import date, datetime, timedelta

# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Tuesday Tracker",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45

# ---------------------------------------------------------
# FULL APPLE iOS 18 GLASSMORPHISM & SF DESIGN SYSTEM
# ---------------------------------------------------------
st.markdown("""
    <style>
    /* Systemowa czcionka Apple SF Pro */
    @import url('https://fonts.cdnfonts.com/css/sf-pro-display');
    
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif !important;
        background-color: #F2F2F7 !important;
        color: #1C1C1E;
    }

    /* Główny kontener strony */
    .stApp {
        background: linear-gradient(180deg, #F2F2F7 0%, #E5E5EA 100%);
    }

    /* DYNAMIC ISLAND HEADER */
    .ios-dynamic-island {
        background: #000000;
        color: #FFFFFF;
        border-radius: 28px;
        padding: 12px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 12px 30px rgba(0,0,0,0.25);
        margin-bottom: 24px;
        border: 1px solid rgba(255,255,255,0.15);
    }
    
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0.8); }
        70% { box-shadow: 0 0 0 10px rgba(52, 199, 89, 0); }
        100% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0); }
    }
    
    .status-dot-green {
        width: 10px;
        height: 10px;
        background-color: #34C759;
        border-radius: 50%;
        animation: pulse-green 2s infinite;
        display: inline-block;
        margin-right: 8px;
    }

    /* KARTY iOS 18 GLASSMORPHISM */
    .ios-card {
        background: rgba(255, 255, 255, 0.75) !important;
        backdrop-filter: blur(25px) saturate(180%);
        -webkit-backdrop-filter: blur(25px) saturate(180%);
        border-radius: 24px !important;
        padding: 22px 26px !important;
        border: 1px solid rgba(255, 255, 255, 0.8) !important;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.04), 0 2px 6px rgba(0,0,0,0.02) !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
        margin-bottom: 18px;
    }
    
    .ios-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.08) !important;
        border-color: rgba(0, 122, 255, 0.4) !important;
    }

    /* WIDGET STATUSU BILANSU (Zysk / Dopłata) */
    .ios-balance-plus {
        background: linear-gradient(135deg, rgba(52, 199, 89, 0.18) 0%, rgba(255, 255, 255, 0.9) 100%);
        backdrop-filter: blur(30px);
        -webkit-backdrop-filter: blur(30px);
        border: 2px solid #34C759;
        border-radius: 26px;
        padding: 22px 28px;
        margin-bottom: 22px;
        box-shadow: 0 10px 30px rgba(52, 199, 89, 0.18);
    }
    
    .ios-balance-minus {
        background: linear-gradient(135deg, rgba(255, 59, 48, 0.18) 0%, rgba(255, 255, 255, 0.9) 100%);
        backdrop-filter: blur(30px);
        -webkit-backdrop-filter: blur(30px);
        border: 2px solid #FF3B30;
        border-radius: 26px;
        padding: 22px 28px;
        margin-bottom: 22px;
        box-shadow: 0 10px 30px rgba(255, 59, 48, 0.18);
    }

    /* WIDGET PODGLĄDU PODZIELNIKA (iOS Widget Style) */
    .val-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-top: 14px;
    }
    
    .val-badge {
        background: rgba(242, 242, 247, 0.8);
        border-radius: 18px;
        padding: 14px 10px;
        text-align: center;
        border: 1px solid rgba(229, 229, 234, 0.9);
    }
    
    .val-title {
        font-size: 11px;
        font-weight: 700;
        color: #8E8E93;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    
    .val-number {
        font-size: 26px;
        font-weight: 800;
        color: #007AFF;
        margin-top: 4px;
        letter-spacing: -0.5px;
    }

    /* iOS SEGMENTED TABS CONTROL */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(120, 120, 128, 0.12) !important;
        backdrop-filter: blur(20px);
        padding: 4px;
        border-radius: 16px !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 12px !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        color: #3A3A3C !important;
        transition: all 0.2s cubic-bezier(0.2, 0, 0, 1) !important;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0 3px 12px rgba(0, 0, 0, 0.12) !important;
    }

    /* SIDEBAR iOS PANEL */
    [data-testid="stSidebar"] {
        background-color: rgba(249, 249, 249, 0.85) !important;
        backdrop-filter: blur(30px);
        border-right: 1px solid rgba(0,0,0,0.05);
    }
    
    /* PRZYCISKI W STYLU iOS */
    .stButton > button {
        border-radius: 16px !important;
        font-weight: 600 !important;
        letter-spacing: -0.2px !important;
        transition: all 0.2s ease !important;
        border: none !important;
    }
    .stButton > button:hover {
        transform: scale(1.02);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# OBSŁUGA DANYCH & DAT WTORKOWYCH
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "meter": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter": "POD-SYP-2026"},
    "Pokój Dziecka": {"icon": "🧒", "meter": "POD-DZI-2026"},
    "Licznik Główny": {"icon": "🏢", "meter": "GJ-MAIN-2026"}
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

def create_empty_df():
    return pd.DataFrame(columns=[
        "id", "season", "week_num", "period_label", "date_entry",
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

def get_tuesday_for_iso_week(year, week):
    first_day = date(year, 1, 4)
    start_of_year = first_day - timedelta(days=first_day.weekday())
    target_tuesday = start_of_year + timedelta(weeks=week-1, days=1)
    return target_tuesday

df = load_data()

# ---------------------------------------------------------
# STREFA NAGŁÓWKA iOS DYNAMIC ISLAND
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

current_room = st.session_state["selected_room"]

st.markdown("""
<div class="ios-dynamic-island">
    <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 20px;">🔥</span>
        <span style="font-weight: 700; font-size: 16px; letter-spacing: -0.3px;">Sonoff Smart Heating</span>
        <span style="background: rgba(255,255,255,0.2); padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">iOS 18 v2.5</span>
    </div>
    <div style="display: flex; align-items: center; font-size: 13px; font-weight: 500;">
        <span class="status-dot-green"></span> System Aktywny • Cotygodniowe Odczyty we Wtorki
    </div>
</div>
""", unsafe_allow_html=True)

# Przełącznik stref
room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (current_room == room_key)
    with room_cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"btn_{room_key}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state["selected_room"] = room_key
            st.rerun()

st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# OBLICZENIA I DEDYKOWANE OKNO POKOJU (NP. SALON)
# ---------------------------------------------------------
df_room = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"])

if not df_room.empty:
    last_row = df_room.iloc[-1]
    last_meter = last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter"])
    val_start = float(last_row.get("units_start", 0.0))
    val_end = float(last_row.get("units_end", 0.0))
    last_date = str(last_row.get("date_entry", "Brak wpisów"))
    total_sonoff_units = df_room[df_room["season"] == "2026/2027 (Sonoff - Wtorki)"]["delta_units"].sum()
else:
    last_meter = ROOMS_CONFIG[current_room]["meter"]
    val_start = 0.0
    val_end = 0.0
    last_date = "Brak odczytów"
    total_sonoff_units = 0.0

# Podsumowanie bazowe
base_room_units = df_room[df_room["season"] == "2025/2026 (Bazowy)"]["delta_units"].sum()
diff_units = base_room_units - total_sonoff_units
pln_balance = diff_units * EST_PLN_PER_UNIT

# KARTA WIDŻETU STREFY (iOS 18 WIDGET)
st.markdown(f"""
<div class="ios-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <div style="font-size: 22px; font-weight: 800; color: #1C1C1E; display: flex; align-items: center; gap: 8px;">
            {ROOMS_CONFIG[current_room]['icon']} Pokój: <b>{current_room}</b>
            <span style="font-family: monospace; font-size: 12px; background: #E5E5EA; padding: 4px 10px; border-radius: 10px; color: #48484A;">
                {last_meter}
            </span>
        </div>
        <div style="font-size: 13px; color: #8E8E93; font-weight: 600;">
            🗓️ Ostatni wtorek: <b>{last_date}</b>
        </div>
    </div>
    <div class="val-container">
        <div class="val-badge">
            <div class="val-title">Wartość Początkowa</div>
            <div class="val-number">{val_start:.1f} U</div>
        </div>
        <div class="val-badge">
            <div class="val-title">Wartość Końcowa</div>
            <div class="val-number">{val_end:.1f} U</div>
        </div>
        <div class="val-badge">
            <div class="val-title">Ostatni Przyrost (ΔU)</div>
            <div class="val-number" style="color: #34C759;">+{(val_end - val_start):.1f} U</div>
        </div>
        <div class="val-badge">
            <div class="val-title">Suma Sezon Sonoff</div>
            <div class="val-number" style="color: #5856D6;">{total_sonoff_units:.0f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# WIDGET ZYSKU / STRATY (CZY JESTEŚMY NA PLUSIE CZY MINUSIE?)
# ---------------------------------------------------------
if total_sonoff_units > 0:
    if diff_units >= 0:
        st.markdown(f"""
        <div class="ios-balance-plus">
            <div style="font-size: 20px; font-weight: 800; color: #145A25; margin-bottom: 4px;">
                🟢 STAN BILANSU: JESTEŚ NA PLUSIE!
            </div>
            <div style="font-size: 34px; font-weight: 800; color: #1E7E34; letter-spacing: -1px;">
                +{pln_balance:.2f} PLN
            </div>
            <div style="font-size: 14px; color: #2C3E50; margin-top: 6px; font-weight: 500;">
                🎉 <b>Świetnie!</b> W pomieszczeniu <b>{current_room}</b> zużyłeś o <b>{diff_units:.0f} U mniej</b> niż w zeszłym roku. W kieszeni zostaje konkretna kwota!
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ios-balance-minus">
            <div style="font-size: 20px; font-weight: 800; color: #D32F2F; margin-bottom: 4px;">
                🔴 STAN BILANSU: JESTEŚ NA MINUSIE
            </div>
            <div style="font-size: 34px; font-weight: 800; color: #D32F2F; letter-spacing: -1px;">
                {pln_balance:.2f} PLN
            </div>
            <div style="font-size: 14px; color: #2C3E50; margin-top: 6px; font-weight: 500;">
                ⚠️ <b>Uwaga!</b> Zużycie w <b>{current_room}</b> przekracza zeszłoroczny poziom o <b>{abs(diff_units):.0f} U</b>. Zmniejsz nastawę nocną w harmonogramie Sonoff TRVZB do 18.5°C.
            </div>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR: WTORKOWY FORMULARZ DANYCH
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📅 Wtorkowy Odczyt")
    st.caption(f"Strefa: **{current_room}**")

    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    
    current_year, current_iso_w, _ = date.today().isocalendar()
    week_input = st.number_input("Tydzień Roku (1 - 52)", min_value=1, max_value=52, value=current_iso_w)
    
    # Wyznaczenie automatycznej daty wtorkowej dla danego tygodnia
    tuesday_date = get_tuesday_for_iso_week(2026, week_input)
    period_tag = f"Tydzień {week_input:02d} (Wtorek)"

    st.info(f"📆 Domyślny dzień odczytu: **Wtorek, {tuesday_date.strftime('%d.%m.%Y')}**")

    suggested_start = val_end if val_end > 0 else 0.0

    with st.form("tuesday_form"):
        meter_input = st.text_input("Numer Podzielnika", value=last_meter)
        
        st.markdown("---")
        st.markdown("##### 🔢 Podzielnik Kaloryfera [U]")
        u_start = st.number_input("Wartość Początkowa", min_value=0.0, value=suggested_start, step=1.0)
        u_end = st.number_input("Wartość Końcowa (Stan z wtorku)", min_value=0.0, value=suggested_start + 12.0, step=1.0)

        st.markdown("---")
        st.markdown("##### 🏢 Licznik Główny [GJ]")
        gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
        gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)

        entry_date = st.date_input("Data wpisu", tuesday_date)
        notes = st.text_input("Nastawa Sonoff / Uwagi", value="20.5°C Eco Schedule")

        if st.form_submit_button("⚡ Zapisz Wtorkowy Odczyt", use_container_width=True):
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
                    "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Wtorkowy odczyt: {current_room} T{week_input}"):
                    st.success("Odczyt wtorkowy został pomyślnie zapisany!")
                    st.rerun()

# ---------------------------------------------------------
# TABY Z WYKRESAMI I HISTORIĄ (iOS SEGMENTED CONTROL)
# ---------------------------------------------------------
tab_charts, tab_history = st.tabs(["📈 Wykres Tygodniowy (iOS Chart)", "📋 Historia Wtorkowa"])

with tab_charts:
    st.markdown("#### Tygodniowe Zużycie ΔU we Wtorki")
    
    if not df_room.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_room["period_label"],
            y=df_room["delta_units"],
            marker_color="#007AFF",
            marker_line_radius=8,
            hovertemplate="Okres: %{x}<br>Zużycie: %{y:.1f} U"
        ))
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="-apple-system, SF Pro Display, sans-serif", color="#1C1C1E")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Brak danych do wygenerowania wykresu. Wprowadź pierwszy wtorkowy odczyt.")

with tab_history:
    st.markdown(f"#### Rejestr Odczytów dla: {current_room}")
    if not df_room.empty:
        st.dataframe(
            df_room[["date_entry", "period_label", "meter_number", "units_start", "units_end", "delta_units", "notes"]]
            .rename(columns={
                "date_entry": "Data Wtorkowa", "period_label": "Tydzień", "meter_number": "Podzielnik",
                "units_start": "Początek", "units_end": "Koniec", "delta_units": "Przyrost ΔU", "notes": "Nastawy / Uwagi"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.caption("Brak zarejestrowanych odczytów.")
