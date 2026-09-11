import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date

# ---------------------------------------------------------
# KONFIGURACJA STRONY & STYLIZACJA iOS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Ogrzewanie Sonoff - Bilans & Oszczędności",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"

st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }
    .main { background-color: #F2F2F7; }
    
    /* Karty iOS Glassmorphism */
    div[data-testid="stMetric"], .ios-card {
        background: rgba(255, 255, 255, 0.88);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 18px;
        padding: 16px 20px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
    }
    
    /* Wskaźniki Zysku / Straty */
    .profit-card {
        background: rgba(52, 199, 89, 0.12);
        border: 1px solid #34C759;
        border-radius: 16px;
        padding: 14px 18px;
        color: #1B5E20;
        margin-bottom: 15px;
    }
    .loss-card {
        background: rgba(255, 59, 48, 0.12);
        border: 1px solid #FF3B30;
        border-radius: 16px;
        padding: 14px 18px;
        color: #B71C1C;
        margin-bottom: 15px;
    }

    [data-testid="stMetricValue"] {
        font-size: 26px !important;
        font-weight: 700 !important;
        color: #1C1C1E !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
        font-weight: 600 !important;
        color: #8E8E93 !important;
        text-transform: uppercase;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px; background-color: #E5E5EA; padding: 5px; border-radius: 14px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px; border-radius: 10px; background-color: transparent; border: none; font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important; color: #000000 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SŁOWNIKI I DANE
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "desc": "Główny kaloryfer w salonie"},
    "Sypialnia": {"icon": "🛏️", "desc": "Kaloryfer w sypialni"},
    "Pokój Dziecka": {"icon": "🧒", "desc": "Kaloryfer w pokoju dziecka"},
    "Licznik Główny": {"icon": "🏢", "desc": "Główny ciepłomierz (GJ)"}
}

PERIODS = {
    "09-1": "Wrzesień I (1-15)", "09-2": "Wrzesień II (16-30)",
    "10-1": "Październik I (1-15)", "10-2": "Październik II (16-31)",
    "11-1": "Listopad I (1-15)", "11-2": "Listopad II (16-30)",
    "12-1": "Grudzień I (1-15)", "12-2": "Grudzień II (16-31)",
    "01-1": "Styczeń I (1-15)", "01-2": "Styczeń II (16-31)",
    "02-1": "Luty I (1-15)", "02-2": "Luty II (16-28/29)",
    "03-1": "Marzec I (1-15)", "03-2": "Marzec II (16-31)",
    "04-1": "Kwiecień I (1-15)", "04-2": "Kwiecień II (16-30)"
}

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff od 09.2026)"]

# ---------------------------------------------------------
# OBSŁUGA BAZY DANYCH (GITHUB / BAZA LOKALNA)
# ---------------------------------------------------------
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
        "id", "season", "period_code", "period_label", "date_entry",
        "room_name", "meter_number", "units_start", "units_end", "delta_units",
        "gj_start", "gj_end", "delta_gj", "cost_per_gj", "target_limit", "notes"
    ])

def load_data():
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            csv_raw = file_content.decoded_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_raw))
        except Exception:
            df = load_local_fallback()
    else:
        df = load_local_fallback()

    required_cols = create_empty_df().columns
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0.0 if "start" in col or "end" in col or "delta" in col or "cost" in col else None
    return df

def load_local_fallback():
    if os.path.exists(FILE_PATH):
        try: return pd.read_csv(FILE_PATH)
        except Exception: return create_empty_df()
    else:
        df = create_empty_df()
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        return df

def save_data(df, commit_message="Aktualizacja odczytu"):
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_string = csv_buffer.getvalue()

    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(FILE_PATH, commit_message, csv_string, file_content.sha, branch=branch)
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
            return True
        except Exception:
            return False
    else:
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        return True

# ---------------------------------------------------------
# INTERFEJS GŁÓWNY
# ---------------------------------------------------------
df = load_data()

if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

st.title("🔥 Sonoff Smart Heating")
st.caption("System monitorowania zużycia ciepła, bilansu zysków/strat i optymalizacji nastaw głowic.")

# Wybór pokoju (iOS Segmented Control)
cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (st.session_state["selected_room"] == room_key)
    btn_type = "primary" if is_active else "secondary"
    with cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"btn_{room_key}", use_container_width=True, type=btn_type):
            st.session_state["selected_room"] = room_key
            st.rerun()

current_room = st.session_state["selected_room"]

# ---------------------------------------------------------
# SIDEBAR - SMART DATA ENTRY (AUTOMATYCZNE PODPOWIADANIE)
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📥 Odczyt: {ROOMS_CONFIG[current_room]['icon']} {current_room}")
    
    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    period_code_input = st.selectbox("Okres rozliczeniowy", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
    
    # Auto-fetch poprzedniego stanu końcowego dla wybranego pokoju i sezonu
    prev_entries = df[(df["room_name"] == current_room) & (df["season"] == season_input)]
    default_start_u = float(prev_entries.iloc[-1]["units_end"]) if not prev_entries.empty and pd.notna(prev_entries.iloc[-1]["units_end"]) else 0.0
    default_start_gj = float(prev_entries.iloc[-1]["gj_end"]) if not prev_entries.empty and pd.notna(prev_entries.iloc[-1]["gj_end"]) else 0.0

    st.caption("💡 Stan początkowy został pobrany automatycznie z ostatniego wpisu.")

    with st.form("entry_form"):
        meter_number = st.text_input("Numer podzielnika/licznika", value=f"POD-{current_room[:3].upper()}-2026")
        
        st.markdown("---")
        st.subheader("Podzielnik (Jednostki U)")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Początek", min_value=0.0, value=default_start_u, step=1.0)
        units_end = col_u2.number_input("Koniec", min_value=0.0, value=default_start_u, step=1.0)
        manual_delta_u = st.number_input("Lub wpisz gotowe ΔU", min_value=0.0, value=0.0, step=1.0)

        st.markdown("---")
        st.subheader("Ciepłomierz Główny (GJ)")
        col_g1, col_g2 = st.columns(2)
        gj_start = col_g1.number_input("GJ początek", min_value=0.0, value=default_start_gj, step=0.01)
        gj_end = col_g2.number_input("GJ koniec", min_value=0.0, value=default_start_gj, step=0.01)
        manual_delta_gj = st.number_input("Lub wpisz gotowe ΔGJ", min_value=0.0, value=0.0, step=0.01)

        st.markdown("---")
        preset_note = st.selectbox(
            "Szybki szablon nastawy Sonoff", 
            ["20.0°C Eco (Harmonogram Praca)", "21.5°C Comfort", "Tryb Wyjazd (16.0°C)", "Tryb Nocny (19.0°C)", "Inne / Ręcznie"]
        )
        notes = st.text_input("Szczegóły / Uwagi", value=preset_note)
        
        cost_per_gj = st.number_input("Cena 1 GJ (PLN)", min_value=0.0, value=105.0, step=1.0)
        target_limit = st.number_input("Cel limitu na okres (ΔU)", min_value=0.0, value=120.0, step=10.0)
        date_entry = st.date_input("Data odczytu", date.today())

        if st.form_submit_button("💾 Zapisz Szybki Odczyt", use_container_width=True):
            delta_units = (units_end - units_start) if (units_end > units_start and manual_delta_u == 0) else manual_delta_u
            delta_gj = (gj_end - gj_start) if (gj_end > gj_start and manual_delta_gj == 0) else manual_delta_gj

            if delta_units <= 0 and delta_gj <= 0:
                st.error("Podaj poprawne zużycie!")
            else:
                df = df[~((df["season"] == season_input) & (df["period_code"] == period_code_input) & (df["room_name"] == current_room))]
                next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1

                new_row = pd.DataFrame([{
                    "id": next_id, "season": season_input, "period_code": period_code_input,
                    "period_label": PERIODS[period_code_input], "date_entry": str(date_entry),
                    "room_name": current_room, "meter_number": meter_number,
                    "units_start": units_start, "units_end": units_end, "delta_units": delta_units,
                    "gj_start": gj_start, "gj_end": gj_end, "delta_gj": delta_gj,
                    "cost_per_gj": cost_per_gj, "target_limit": target_limit, "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Odczyt: {current_room} {period_code_input}"):
                    st.success("Wpis dodany!")
                    st.rerun()

# ---------------------------------------------------------
# CALCULATIONS & PACING (PORÓWNANIE JABŁKO DO JABŁKA)
# ---------------------------------------------------------
period_order = list(PERIODS.keys())
df["period_order"] = df["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)

df_room = df[df["room_name"] == current_room].sort_values("period_order")

base_df = df_room[df_room["season"] == "2025/2026 (Bazowy)"]
sonoff_df = df_room[df_room["season"] == "2026/2027 (Sonoff od 09.2026)"]

# Filtrowanie bazowego roku tylko do okresów, które MOGŁY już wystąpić w tym sezonie
recorded_periods = sonoff_df["period_code"].unique()
base_comparable = base_df[base_df["period_code"].isin(recorded_periods)]

u_sonoff_total = sonoff_df["delta_units"].sum()
u_base_comparable = base_comparable["delta_units"].sum()
u_diff = u_base_comparable - u_sonoff_total  # Dodatnie = zaoszczędzono, Ujemne = przekroczono

# Przelicznik jednostek U na PLN na podstawie kosztu GJ
avg_cost_gj = df["cost_per_gj"].replace(0, pd.NA).dropna().mean()
if pd.isna(avg_cost_gj) or avg_cost_gj == 0: avg_cost_gj = 105.0

# Szacunkowy przelicznik 1 U na PLN na podstawie danych z całego budynku lub estymacji
est_pln_per_unit = 2.45  # Średnio przelicznik jednostki w budynku
pln_balance = u_diff * est_pln_per_unit

# ---------------------------------------------------------
# SEKCJABILANSU FINANSOWEGO (ZYSK / STRATA)
# ---------------------------------------------------------
st.markdown(f"### 📊 Status Rozliczenia: {ROOMS_CONFIG[current_room]['icon']} {current_room}")

if len(recorded_periods) > 0:
    if u_diff >= 0:
        st.markdown(
            f"""<div class="profit-card">
            🎉 <b>ZYSK / OSZCZĘDNOŚĆ: +{pln_balance:.2f} PLN</b><br>
            W dotychczasowych {len(recorded_periods)} okresach zużyto o <b>{u_diff:.0f} U mniej</b> niż w analogicznym czasie rok temu.
            Oszczędność wynosi <b>{((u_diff / u_base_comparable)*100 if u_base_comparable > 0 else 0):.1f}%</b>.
            </div>""",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""<div class="loss-card">
            ⚠️ <b>NADWYŻKA / STRATA: {pln_balance:.2f} PLN</b><br>
            W dotychczasowych {len(recorded_periods)} okresach zużyto o <b>{abs(u_diff):.0f} U więcej</b> niż w analogicznym czasie rok temu.
            Wzrost zużycia o <b>{((abs(u_diff) / u_base_comparable)*100 if u_base_comparable > 0 else 0):.1f}%</b>.
            </div>""",
            unsafe_allow_html=True
        )
else:
    st.info("Brak wpisów dla sezonu 2026/2027. Wprowadź pierwszy odczyt z września w panelu bocznym.")

# Kafelki Metryk
c1, c2, c3, c4 = st.columns(4)
c1.metric("Zużycie Sonoff 2026", f"{u_sonoff_total:.0f} U")
c2.metric("Rok Temu (Ten Sam Okres)", f"{u_base_comparable:.0f} U")
c3.metric("Różnica Bilansu", f"{u_diff:+.0f} U", delta=f"{pln_balance:+.2f} PLN")
c4.metric("Liczba Zarejestrowanych Okresów", f"{len(recorded_periods)} / {len(PERIODS)}")

st.divider()

# ---------------------------------------------------------
# ZAKŁADKI I WIZUALIZACJA DANYCH
# ---------------------------------------------------------
tab_charts, tab_pacing, tab_roi, tab_data = st.tabs([
    "📈 Wykresy i Porównania", 
    "🎯 Tempo & Prognoza Sezonowa", 
    "💡 ROI Sonoff & Innowacje", 
    "📋 Zestawienie Wpisów"
])

with tab_charts:
    st.markdown("#### Zużycie w Okresach: Sonoff 2026 vs Rok Temu [Jednostki U]")
    
    fig_u = go.Figure()
    if not base_df.empty:
        fig_u.add_trace(go.Bar(
            x=base_df["period_label"], y=base_df["delta_units"],
            name="2025/2026 (Bazowy)", marker_color="#D1D1D6"
        ))
    if not sonoff_df.empty:
        fig_u.add_trace(go.Bar(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"],
            name="2026/2027 (Sonoff)", marker_color="#007AFF"
        ))
    fig_u.update_layout(barmode='group', template="plotly_white", xaxis_title="Okres (od Września)", yaxis_title="Zużycie [U]")
    st.plotly_chart(fig_u, use_container_width=True)

with tab_pacing:
    st.markdown("#### Skumulowane Tempo Zużycia Ciepła (Pacing Chart)")
    st.caption("Linia pokazuje, czy w danym momencie sezonu jesteś poniżej czy powyżej skumulowanego zużycia z zeszłego roku.")
    
    fig_cum = go.Figure()
    if not base_df.empty:
        fig_cum.add_trace(go.Scatter(
            x=base_df["period_label"], y=base_df["delta_units"].cumsum(),
            mode='lines+markers', name="Skumulowane 2025/2026", line=dict(color="#8E8E93", dash='dash')
        ))
    if not sonoff_df.empty:
        fig_cum.add_trace(go.Scatter(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"].cumsum(),
            mode='lines+markers', name="Skumulowane 2026/2027 (Sonoff)", line=dict(color="#34C759" if u_diff >= 0 else "#FF3B30", width=4)
        ))
    fig_cum.update_layout(template="plotly_white", xaxis_title="Okres", yaxis_title="Skumulowane ΔU")
    st.plotly_chart(fig_cum, use_container_width=True)

    # Prognoza na koniec sezonu
    if len(recorded_periods) > 0 and len(base_df) > 0:
        total_base_full_season = base_df["delta_units"].sum()
        avg_saving_ratio = (u_sonoff_total / u_base_comparable) if u_base_comparable > 0 else 1.0
        projected_full_season_u = total_base_full_season * avg_saving_ratio
        projected_pln_diff = (total_base_full_season - projected_full_season_u) * est_pln_per_unit

        st.markdown("##### 🔮 Prognoza na Koniec Sezonu (Kwiecień 2027)")
        col_p1, col_p2 = st.columns(2)
        col_p1.metric("Prognozowane Całkowite Zużycie", f"{projected_full_season_u:.0f} U", delta=f"{projected_full_season_u - total_base_full_season:+.0f} U vs rok temu")
        col_p2.metric("Prognozowany Bilans Zwrotu / Dopłaty", f"{projected_pln_diff:+.2f} PLN")

with tab_roi:
    st.markdown("#### 💡 Kalkulator Zwrotu z Inwestycji (ROI) w Głowice Sonoff")
    
    col_r1, col_r2 = st.columns(2)
    trv_count = col_r1.number_input("Liczba zainstalowanych głowic Sonoff", min_value=1, value=3, step=1)
    trv_cost_per_item = col_r2.number_input("Koszt jednej głowicy (PLN)", min_value=0.0, value=120.0, step=10.0)
    
    total_investment = trv_count * trv_cost_per_item
    st.info(f"Całkowity koszt zakupu głowic: **{total_investment:.2f} PLN**")
    
    if pln_balance > 0:
        months_active = len(recorded_periods) * 0.5  # każdy okres to pół miesiąca
        payback_ratio = (pln_balance / total_investment) * 100
        st.success(f"📈 Dotychczasowe oszczędności pokryły **{payback_ratio:.1f}%** kosztu zakupu głowic w ciągu {months_active:.1f} miesiąca grzewczego!")
    else:
        st.warning("Obecnie zużycie jest wyższe niż rok temu. Dostosuj harmonogramy głowic Sonoff, aby generować oszczędności.")

with tab_data:
    st.markdown("#### Wszystkie Odczyty w Bazie Danych")
    st.dataframe(df_room.sort_values(by=["season", "period_order"]), use_container_width=True)
    
    st.divider()
    del_id = st.number_input("ID wpisu do usunięcia:", min_value=1, step=1)
    if st.button("Usuń Wpis", type="primary"):
        if del_id in df["id"].values:
            df = df[df["id"] != del_id]
            save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
            st.success(f"Usunięto wpis {del_id}")
            st.rerun()
