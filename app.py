import streamlit as st
import pandas as pd
import plotly.graph_objects as px_go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date, datetime, timedelta

# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - Stabilna Wersja + Analityka",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45

# ---------------------------------------------------------
# STYLIZACJA (CZYSTY, SPRAWDZONY DESIGN iOS)
# ---------------------------------------------------------
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }
    .main { background-color: #F2F2F7; }

    .ios-room-info-card {
        background: rgba(255, 255, 255, 0.92);
        backdrop-filter: blur(25px);
        border-radius: 20px;
        padding: 20px 24px;
        border: 1px solid rgba(255, 255, 255, 0.8);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.04);
        margin-bottom: 20px;
    }
    .room-header {
        font-size: 19px;
        font-weight: 700;
        color: #1C1C1E;
    }
    .meter-badge {
        background: #E5E5EA;
        color: #3A3A3C;
        padding: 4px 10px;
        border-radius: 10px;
        font-size: 12px;
        font-weight: 600;
        font-family: monospace;
    }
    .val-box {
        background: #F8F9FA;
        border-radius: 12px;
        padding: 10px 14px;
        border: 1px solid #E5E5EA;
        text-align: center;
    }
    .val-title {
        font-size: 10px;
        text-transform: uppercase;
        color: #8E8E93;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .val-num {
        font-size: 22px;
        font-weight: 800;
        color: #007AFF;
    }
    
    .ios-balance-plus {
        background: linear-gradient(135deg, rgba(52, 199, 89, 0.15) 0%, rgba(255, 255, 255, 0.95) 100%);
        border: 2px solid #34C759;
        border-radius: 18px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
    .ios-balance-minus {
        background: linear-gradient(135deg, rgba(255, 59, 48, 0.15) 0%, rgba(255, 255, 255, 0.95) 100%);
        border: 2px solid #FF3B30;
        border-radius: 18px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #E5E5EA;
        padding: 4px;
        border-radius: 14px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# KONFIGURACJA POMIESZCZEŃ I GITHUB
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "meter_default": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter_default": "POD-SYP-2026"},
    "Pokój Dziecka": {"icon": "🧒", "meter_default": "POD-DZI-2026"},
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
    return start_of_year + timedelta(weeks=week-1, days=1)

df = load_data()

# ---------------------------------------------------------
# NAWIGACJA GŁÓWNA
# ---------------------------------------------------------
if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

current_room = st.session_state["selected_room"]

st.title("🔥 Sonoff Smart Heating - Panel Sterowania i Odczytów")
st.caption("Stabilny układ z cotygodniowymi odczytami (Wtorki) oraz rozbudowaną analityką zysków i strat")

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
df_room = df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"])

if not df_room.empty:
    last_row = df_room.iloc[-1]
    last_meter = last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"])
    val_start = float(last_row.get("units_start", 0.0))
    val_end = float(last_row.get("units_end", 0.0))
    last_date = str(last_row.get("date_entry", "Brak wpisów"))
    total_delta_room = df_room[df_room["season"] == "2026/2027 (Sonoff - Wtorki)"]["delta_units"].sum()
else:
    last_meter = ROOMS_CONFIG[current_room]["meter_default"]
    val_start = 0.0
    val_end = 0.0
    last_date = "Brak odczytów"
    total_delta_room = 0.0

# ---------------------------------------------------------
# KARTA INFORMACYJNA POMIESZCZENIA
# ---------------------------------------------------------
st.markdown(f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
        <div class="room-header">
            {ROOMS_CONFIG[current_room]['icon']} Strefa: <b>{current_room}</b> 
            <span class="meter-badge">{last_meter}</span>
        </div>
        <div style="font-size: 13px; color: #8E8E93; font-weight: 500;">
            📅 Ostatni wtorek: <b>{last_date}</b>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
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
            <div class="val-title">Suma Sezon Sonoff</div>
            <div class="val-num" style="color: #5856D6;">{total_delta_room:.0f} U</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Bilans finansowy pokoju
base_room = df_room[df_room["season"] == "2025/2026 (Bazowy)"]["delta_units"].sum()
diff_units = base_room - total_delta_room
pln_balance = diff_units * EST_PLN_PER_UNIT

if total_delta_room > 0:
    if diff_units >= 0:
        st.markdown(f"""
        <div class="ios-balance-plus">
            <span style="font-size: 16px; font-weight: 800; color: #1E7E34;">🟢 JESTEŚ NA PLUSIE! (+{pln_balance:.2f} PLN)</span><br>
            <span style="font-size: 13px; color: #2C3E50;">
                W strefie <b>{current_room}</b> zaoszczędziłeś <b>{diff_units:.0f} U</b> względem roku bazowego.
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ios-balance-minus">
            <span style="font-size: 16px; font-weight: 800; color: #D32F2F;">🔴 JESTEŚ NA MINUSIE ({pln_balance:.2f} PLN)</span><br>
            <span style="font-size: 13px; color: #2C3E50;">
                W strefie <b>{current_room}</b> zużycie wzrosło o <b>{abs(diff_units):.0f} U</b>. Rozważ korektę harmonogramu.
            </span>
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR: FORMULARZ WTORKOWY
# ---------------------------------------------------------
with st.sidebar:
    st.header("📥 Nowy Odczyt (Wtorek)")
    st.caption(f"Strefa: **{current_room}**")

    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    
    current_year, current_iso_w, _ = date.today().isocalendar()
    week_input = st.number_input("Tydzień Roku (1 - 52)", min_value=1, max_value=52, value=current_iso_w)
    
    tuesday_date = get_tuesday_for_iso_week(2026, week_input)
    period_tag = f"Tydzień {week_input:02d} (Wtorek)"

    st.info(f"📆 Domyślny Wtorek: **{tuesday_date.strftime('%d.%m.%Y')}**")
    suggested_start = val_end if val_end > 0 else 0.0

    with st.form("tuesday_form"):
        meter_input = st.text_input("Numer Podzielnika", value=last_meter)
        
        st.markdown("---")
        st.markdown("##### 🔢 Stan Podzielnika [U]")
        u_start = st.number_input("Wartość Początkowa", min_value=0.0, value=suggested_start, step=1.0)
        u_end = st.number_input("Wartość Końcowa (z Wtorku)", min_value=0.0, value=suggested_start + 10.0, step=1.0)
        
        st.markdown("---")
        st.markdown("##### 🏢 Licznik Główny [GJ]")
        gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
        gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)

        entry_date = st.date_input("Data wpisu", tuesday_date)
        notes = st.text_input("Nastawa / Uwagi", value="Sonoff Auto 20.5°C")

        if st.form_submit_button("⚡ Zapisz Odczyt Wtorkowy", use_container_width=True):
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
                    st.success("Zapisano pomyślnie!")
                    st.rerun()

# ---------------------------------------------------------
# ZAKŁADKI: WYKRESY I HISTORIA
# ---------------------------------------------------------
tab_charts, tab_analytics, tab_history = st.tabs([
    "📈 Wykres Pokoju", 
    "💸 Zaawansowane Zyski i Straty (PLN)", 
    "📋 Historia Wpisów"
])

with tab_charts:
    st.markdown(f"#### Tygodniowe Zużycie ΔU dla: {current_room}")
    if not df_room.empty:
        fig = px_go.Figure()
        fig.add_trace(px_go.Bar(
            x=df_room["period_label"],
            y=df_room["delta_units"],
            marker_color="#007AFF",
            hovertemplate="Okres: %{x}<br>Zużycie: %{y:.1f} U"
        ))
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=20, b=20),
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Brak danych dla wybranego pokoju.")

with tab_analytics:
    st.markdown("### 📊 Kompleksowy Bilans Finansowy i Struktura Zużycia")
    
    if not df.empty:
        df_sonoff = df[df["season"].str.contains("Sonoff", na=False)].copy()
        df_base = df[df["season"].str.contains("Bazowy", na=False)].copy()

        df_weekly = df_sonoff.groupby(["week_num", "period_label"])["delta_units"].sum().reset_index()
        df_weekly_base = df_base.groupby(["week_num"])["delta_units"].sum().reset_index().rename(columns={"delta_units": "base_units"})
        
        df_merged = pd.merge(df_weekly, df_weekly_base, on="week_num", how="left").fillna(0)
        df_merged["units_saved"] = df_merged["base_units"] - df_merged["delta_units"]
        df_merged["pln_balance"] = df_merged["units_saved"] * EST_PLN_PER_UNIT
        df_merged["color"] = df_merged["pln_balance"].apply(lambda x: "#34C759" if x >= 0 else "#FF3B30")

        # 1. Wykres zysków i strat PLN
        fig_bal = px_go.Figure()
        fig_bal.add_trace(px_go.Bar(
            x=df_merged["period_label"],
            y=df_merged["pln_balance"],
            marker_color=df_merged["color"],
            text=df_merged["pln_balance"].apply(lambda x: f"{x:.1f} zł"),
            textposition="outside"
        ))
        fig_bal.update_layout(
            title="Tygodniowy Bilans PLN (Zielony = Oszczędność, Czerwony = Strata)",
            template="plotly_white",
            height=350,
            yaxis_title="PLN"
        )
        st.plotly_chart(fig_bal, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            # 2. Skumulowane oszczędności
            df_merged["cum_pln"] = df_merged["pln_balance"].cumsum()
            fig_cum = px_go.Figure()
            fig_cum.add_trace(px_go.Scatter(
                x=df_merged["period_label"],
                y=df_merged["cum_pln"],
                mode="lines+markers",
                fill="tozeroy",
                line=dict(color="#34C759", width=3)
            ))
            fig_cum.update_layout(title="Skumulowany Bilans Finansowy [PLN]", template="plotly_white", height=300)
            st.plotly_chart(fig_cum, use_container_width=True)

        with col2:
            # 3. Udział stref
            df_pie = df_sonoff.groupby("room_name")["delta_units"].sum().reset_index()
            fig_pie = px.pie(df_pie, values="delta_units", names="room_name", hole=0.5, title="Udział Stref w Zużyciu")
            fig_pie.update_layout(template="plotly_white", height=300)
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Brak wystarczających danych do wygenerowania wykresów analitycznych.")

with tab_history:
    st.markdown("### 📋 Rejestr Wszystkich Wpisów")
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Baza danych jest pusta.")
