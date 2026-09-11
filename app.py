import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date

# ---------------------------------------------------------
# KONFIGURACJA STRONY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Zużycie Ogrzewania Sonoff - iOS Style",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"

# ---------------------------------------------------------
# STYLIZACJA W STYLU iOS (APPLE DESIGN SYSTEM)
# ---------------------------------------------------------
st.markdown("""
    <style>
    /* Czcionka i tło w stylu iOS */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    .main {
        background-color: #F2F2F7;
    }
    
    /* Karty iOS z efektami glassmorphism */
    div[data-testid="stMetric"], .ios-card {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 18px;
        padding: 16px 20px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
        margin-bottom: 12px;
    }
    
    /* Metryki iOS */
    [data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700 !important;
        color: #1C1C1E !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 13px !important;
        font-weight: 600 !important;
        color: #8E8E93 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Paski postępu iOS */
    .stProgress > div > div > div > div {
        background-color: #007AFF !important;
        border-radius: 10px;
    }
    
    /* Stylizacja zakładek Tabs iOS */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #E5E5EA;
        padding: 5px;
        border-radius: 14px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 10px;
        background-color: transparent;
        border: none;
        color: #3A3A3C;
        font-weight: 600;
        font-size: 14px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    }
    
    /* iOS Alert Box */
    .ios-alert {
        background-color: #FFF2F2;
        border-left: 5px solid #FF3B30;
        padding: 12px 16px;
        border-radius: 12px;
        color: #D70015;
        font-weight: 500;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SŁOWNIKI I KONFIGURACJA POKOI / OKRESÓW
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "desc": "Główny kaloryfer w salonie"},
    "Sypialnia": {"icon": "🛏️", "desc": "Kaloryfer w sypialni"},
    "Pokój Dziecka": {"icon": "🧒", "desc": "Kaloryfer w pokoju dziecka"},
    "Licznik Główny": {"icon": "🏢", "desc": "Główny ciepłomierz (GJ)"}
}

PERIODS = {
    "09-1": "Wrzesień I (1-15)",
    "09-2": "Wrzesień II (16-30)",
    "10-1": "Październik I (1-15)",
    "10-2": "Październik II (16-31)",
    "11-1": "Listopad I (1-15)",
    "11-2": "Listopad II (16-30)",
    "12-1": "Grudzień I (1-15)",
    "12-2": "Grudzień II (16-31)",
    "01-1": "Styczeń I (1-15)",
    "01-2": "Styczeń II (16-31)",
    "02-1": "Luty I (1-15)",
    "02-2": "Luty II (16-28/29)",
    "03-1": "Marzec I (1-15)",
    "03-2": "Marzec II (16-31)",
    "04-1": "Kwiecień I (1-15)",
    "04-2": "Kwiecień II (16-30)"
}

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff od 09.2026)"]

# ---------------------------------------------------------
# OBSŁUGA BAZY DANYCH
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
    
    df = None
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
            if col in ["gj_start", "gj_end", "delta_gj", "cost_per_gj", "target_limit"]:
                df[col] = 0.0
            elif col == "meter_number":
                df[col] = "—"
            else:
                df[col] = None
    return df

def load_local_fallback():
    if os.path.exists(FILE_PATH):
        try:
            return pd.read_csv(FILE_PATH)
        except Exception:
            return create_empty_df()
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
# INTERFEJS GŁÓWNY I KAFELKI iOS
# ---------------------------------------------------------
df = load_data()

if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

st.title("🔥 Ogrzewanie Sonoff")
st.caption("Monitoring zużycia z kaloryferów od Września 2026 w porównaniu do zeszłego sezonu.")

# Kafelki iOS
st.markdown("##### 📍 Wybierz Pokój")
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
# SIDEBAR - WPROWADZANIE DANYCH
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📥 Odczyt: {ROOMS_CONFIG[current_room]['icon']} {current_room}")
    
    with st.form("entry_form", clear_on_submit=False):
        season = st.selectbox("Sezon grzewczy", SEASONS, index=1)
        period_code = st.selectbox("Okres (od Września)", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
        
        st.markdown("---")
        meter_number = st.text_input("Numer licznika / podzielnika", value=f"POD-{current_room[:3].upper()}-2026")
        
        st.markdown("---")
        st.subheader("1. Podzielnik (Jednostki U)")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Początek", min_value=0.0, value=0.0, step=1.0)
        units_end = col_u2.number_input("Koniec", min_value=0.0, value=0.0, step=1.0)
        manual_delta_u = st.number_input("Lub zużycie bezpośrednie (ΔU)", min_value=0.0, value=0.0, step=1.0)

        st.markdown("---")
        st.subheader("2. Licznik Główny (GJ)")
        col_g1, col_g2 = st.columns(2)
        gj_start = col_g1.number_input("GJ początek", min_value=0.0, value=0.0, step=0.01)
        gj_end = col_g2.number_input("GJ koniec", min_value=0.0, value=0.0, step=0.01)
        manual_delta_gj = st.number_input("Lub zużycie w GJ (ΔGJ)", min_value=0.0, value=0.0, step=0.01)

        st.markdown("---")
        st.subheader("3. Ustawienia i Cel")
        target_limit = st.number_input("Cel / Limit jednostek dla pokoju", min_value=0.0, value=100.0, step=10.0, help="Docelowe maks. zużycie w 2 tygodnie")
        cost_per_gj = st.number_input("Cena za 1 GJ (PLN)", min_value=0.0, value=105.0, step=1.0)
        date_entry = st.date_input("Data odczytu", date.today())
        notes = st.text_input("Uwagi / Nastawa głowicy", value="Harmonogram Sonoff 20.0°C")

        submitted = st.form_submit_button("💾 Zapisz Odczyt")

        if submitted:
            delta_units = (units_end - units_start) if (units_end > units_start and manual_delta_u == 0) else manual_delta_u
            delta_gj = (gj_end - gj_start) if (gj_end > gj_start and manual_delta_gj == 0) else manual_delta_gj

            if delta_units <= 0 and delta_gj <= 0:
                st.error("Podaj poprawne zużycie (ΔU > 0 lub ΔGJ > 0)!")
            else:
                if not df.empty:
                    df = df[~((df["season"] == season) & (df["period_code"] == period_code) & (df["room_name"] == current_room))]

                next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1

                new_row = pd.DataFrame([{
                    "id": next_id, "season": season, "period_code": period_code,
                    "period_label": PERIODS[period_code], "date_entry": str(date_entry),
                    "room_name": current_room, "meter_number": meter_number,
                    "units_start": units_start, "units_end": units_end, "delta_units": delta_units,
                    "gj_start": gj_start, "gj_end": gj_end, "delta_gj": delta_gj,
                    "cost_per_gj": cost_per_gj, "target_limit": target_limit, "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Wpis: {current_room} {period_code}"):
                    st.success("Zapisano pomyślnie!")
                    st.rerun()

# ---------------------------------------------------------
# ANALIZA DANYCH I PRZYGOTOWANIE WSKAŹNIKÓW
# ---------------------------------------------------------
period_order = list(PERIODS.keys())
df["period_order"] = df["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)

df_filtered = df[df["room_name"] == current_room].sort_values("period_order")

base_df = df_filtered[df_filtered["season"] == "2025/2026 (Bazowy)"]
sonoff_df = df_filtered[df_filtered["season"] == "2026/2027 (Sonoff od 09.2026)"]

# Powiadomienia iOS Alert o nietypowym skoku zużycia
if len(sonoff_df) >= 2:
    last_u = sonoff_df.iloc[-1]["delta_units"]
    prev_u = sonoff_df.iloc[-2]["delta_units"]
    if prev_u > 0 and last_u > prev_u * 1.3:
        st.markdown(
            f"""<div class="ios-alert">
            🚨 <b>iOS Alert: Wykryto nietypowy skok zużycia!</b><br>
            W okresie <b>{sonoff_df.iloc[-1]['period_label']}</b> zużycie wzrosło o <b>{((last_u - prev_u)/prev_u)*100:.0f}%</b> w porównaniu do poprzedniego okresu. Sprawdź głowicę lub okna w pokoju.
            </div>""", 
            unsafe_allow_html=True
        )

# Metryki Główne
st.markdown(f"### 📊 Podsumowanie: {ROOMS_CONFIG[current_room]['icon']} {current_room}")

col1, col2, col3, col4 = st.columns(4)

total_u_base = base_df["delta_units"].sum() if not base_df.empty else 0.0
total_u_sonoff = sonoff_df["delta_units"].sum() if not sonoff_df.empty else 0.0

diff_u = total_u_base - total_u_sonoff
pct_saved = ((total_u_base - total_u_sonoff) / total_u_base * 100) if total_u_base > 0 else 0.0

col1.metric("Suma ΔU (Sonoff 2026)", f"{total_u_sonoff:.0f} U")
col2.metric("Suma ΔU (Poprzedni Sezon)", f"{total_u_base:.0f} U")
col3.metric("Różnica Bezpośrednia", f"{diff_u:+.0f} U", delta=f"{pct_saved:+.1f}% zużycia" if pct_saved != 0 else None)

# Wyliczenie szacunkowego kosztu na pokój z przelicznika U -> GJ
total_gj_sonoff = sonoff_df["delta_gj"].sum() if not sonoff_df.empty else 0.0
avg_cost_gj = df["cost_per_gj"].replace(0, pd.NA).dropna().mean()
if pd.isna(avg_cost_gj) or avg_cost_gj == 0:
    avg_cost_gj = 105.0

est_cost_pln = total_gj_sonoff * avg_cost_gj
col4.metric("Szacowany Koszt Pokoju", f"{est_cost_pln:.2f} PLN")

# 🎯 Target Activity Progress Bar (iOS Health Style)
if not sonoff_df.empty and sonoff_df.iloc[-1]["target_limit"] > 0:
    last_period_u = sonoff_df.iloc[-1]["delta_units"]
    target_u = sonoff_df.iloc[-1]["target_limit"]
    progress = min(last_period_u / target_u, 1.0)
    
    st.markdown(f"**🎯 Cel Zużycia w Ostatnim Okresie ({sonoff_df.iloc[-1]['period_label']}): {last_period_u:.0f} / {target_u:.0f} U**")
    st.progress(progress)

st.divider()

# ---------------------------------------------------------
# WYKRESY I ZAKŁADKI
# ---------------------------------------------------------
tab_charts, tab_breakdown, tab_audit, tab_table = st.tabs([
    "📈 Wykresy Zużycia (Sonoff vs Bazowy)", 
    "🍕 Struktura Mieszkania", 
    "🔢 Licznik i Audyt", 
    "📋 Tabela Wpisów"
])

with tab_charts:
    st.markdown("#### Porównanie Zużycia Kaloryferów Okres po Okresie [Jednostki U]")
    
    fig_u = go.Figure()
    if not base_df.empty:
        fig_u.add_trace(go.Bar(
            x=base_df["period_label"], y=base_df["delta_units"],
            name="2025/2026 (Bez Sonoff)", marker_color="#C7C7CC",
            text=base_df["delta_units"].apply(lambda x: f"{x:.0f}"), textposition='auto'
        ))
    if not sonoff_df.empty:
        fig_u.add_trace(go.Bar(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"],
            name="2026/2027 (Sonoff od 09.2026)", marker_color="#007AFF",
            text=sonoff_df["delta_units"].apply(lambda x: f"{x:.0f}"), textposition='auto'
        ))
    fig_u.update_layout(
        barmode='group', xaxis_title="Okres Rozliczeniowy (od Września)", 
        yaxis_title="Zużycie [Jednostki U]", template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_u, use_container_width=True)

    st.markdown("#### Skumulowany Pobór Ciepła w Sezonie [Jednostki U]")
    fig_cum = go.Figure()
    if not base_df.empty:
        fig_cum.add_trace(go.Scatter(
            x=base_df["period_label"], y=base_df["delta_units"].cumsum(),
            mode='lines+markers', name="Suma 2025/2026", line=dict(color="#FF9500", width=3)
        ))
    if not sonoff_df.empty:
        fig_cum.add_trace(go.Scatter(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"].cumsum(),
            mode='lines+markers', name="Suma 2026/2027 (Sonoff)", line=dict(color="#34C759", width=4)
        ))
    fig_cum.update_layout(xaxis_title="Okres", yaxis_title="Skumulowane ΔU", template="plotly_white")
    st.plotly_chart(fig_cum, use_container_width=True)

with tab_breakdown:
    st.markdown("#### Udział Procentowy Pokojów w Łącznym Zużyciu Mieszkania (2026/2027)")
    
    sonoff_all_rooms = df[(df["season"] == "2026/2027 (Sonoff od 09.2026)") & (df["room_name"] != "Licznik Główny")]
    
    if not sonoff_all_rooms.empty:
        room_summary = sonoff_all_rooms.groupby("room_name")["delta_units"].sum().reset_index()
        
        fig_pie = px.pie(
            room_summary, values="delta_units", names="room_name",
            hole=0.5, color_discrete_sequence=["#007AFF", "#5856D6", "#FF9500", "#FF2D55"]
        )
        fig_pie.update_traces(textinfo='percent+label', textfont_size=14)
        fig_pie.update_layout(template="plotly_white", showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Brak wpisów dla sezonu 2026/2027 w pokojach, aby pokazać strukturę.")

with tab_audit:
    st.markdown(f"#### Przypisany Numer Licznika dla Pokoju: `{current_room}`")
    meters = df_filtered["meter_number"].unique()
    st.info(f"Oznaczenie podzielnika w bazie: **{', '.join([str(m) for m in meters])}**")
    
    st.dataframe(df_filtered[[
        "season", "period_label", "meter_number", "units_start", "units_end", "delta_units", "delta_gj", "target_limit", "notes"
    ]], use_container_width=True)

with tab_table:
    st.markdown("#### Wszystkie Wpisy w Bazie Danych dla Wybranego Pokoju")
    st.dataframe(df_filtered.sort_values(by=["season", "period_order"]), use_container_width=True)

    st.divider()
    del_id = st.number_input("Podaj ID wpisu do usunięcia:", min_value=1, step=1)
    if st.button("Usuń Wpis", type="primary"):
        if del_id in df["id"].values:
            df = df[df["id"] != del_id]
            save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
            st.success(f"Usunięto wpis {del_id}")
            st.rerun()
        else:
            st.error("Nie znaleziono podanego ID.")
