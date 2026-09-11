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
    page_title="Sonoff Smart Heating - Dashboard 2026",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"

# ---------------------------------------------------------
# DYNAMICZNY STYL iOS 18 (DYNAMIC ISLAND & BALANCE WIDGETS)
# ---------------------------------------------------------
st.markdown("""
    <style>
    /* Czcionka Systemowa iOS */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }
    
    .main { 
        background-color: #F2F2F7; 
    }
    
    /* Animacja pulsowania statusu */
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(52, 199, 89, 0); }
        100% { box-shadow: 0 0 0 0 rgba(52, 199, 89, 0); }
    }
    
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(52, 199, 89, 0.12);
        color: #1E7E34;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid rgba(52, 199, 89, 0.3);
    }
    
    .status-dot {
        width: 9px;
        height: 9px;
        background-color: #34C759;
        border-radius: 50%;
        animation: pulse-green 2s infinite;
    }

    /* iOS 18 DYNAMIC WIDGETS (Na plusie / Na minusie) */
    .ios-balance-widget-plus {
        background: linear-gradient(135deg, rgba(52, 199, 89, 0.18) 0%, rgba(255, 255, 255, 0.95) 100%);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border: 2px solid #34C759;
        border-radius: 24px;
        padding: 20px 26px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(52, 199, 89, 0.15);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .ios-balance-widget-plus:hover {
        transform: translateY(-3px);
        box-shadow: 0 14px 35px rgba(52, 199, 89, 0.25);
    }

    .ios-balance-widget-minus {
        background: linear-gradient(135deg, rgba(255, 59, 48, 0.18) 0%, rgba(255, 255, 255, 0.95) 100%);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border: 2px solid #FF3B30;
        border-radius: 24px;
        padding: 20px 26px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px rgba(255, 59, 48, 0.15);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .ios-balance-widget-minus:hover {
        transform: translateY(-3px);
        box-shadow: 0 14px 35px rgba(255, 59, 48, 0.25);
    }

    .widget-title {
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 4px;
    }
    .widget-amount-plus {
        font-size: 32px;
        font-weight: 800;
        color: #145A25;
        letter-spacing: -0.5px;
    }
    .widget-amount-minus {
        font-size: 32px;
        font-weight: 800;
        color: #D32F2F;
        letter-spacing: -0.5px;
    }
    .widget-subtext {
        font-size: 14px;
        color: #3A3A3C;
        margin-top: 6px;
        font-weight: 500;
    }

    /* Karty iOS 18 */
    div[data-testid="stMetric"], .ios-card {
        background: rgba(255, 255, 255, 0.88);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border-radius: 20px;
        padding: 18px 22px;
        border: 1px solid rgba(255, 255, 255, 0.6);
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.03);
        transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        margin-bottom: 14px;
    }
    
    div[data-testid="stMetric"]:hover, .ios-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.08);
        border-color: rgba(0, 122, 255, 0.4);
    }

    [data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
        font-weight: 600 !important;
        color: #8E8E93 !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    
    /* Zakładki Tabs iOS Style */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #E5E5EA;
        padding: 6px;
        border-radius: 16px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        border-radius: 12px;
        background-color: transparent;
        border: none;
        font-weight: 600;
        font-size: 14px;
        transition: all 0.2s ease;
    }

    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.12);
    }
    
    /* Przycisk akcji */
    .stButton > button {
        border-radius: 14px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 122, 255, 0.3);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# USTAWIENIA OGRZEWANIA I OKRESÓW
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "desc": "Główny strefowy kaloryfer w salonie"},
    "Sypialnia": {"icon": "🛏️", "desc": "Kaloryfer sypialniany"},
    "Pokój Dziecka": {"icon": "🧒", "desc": "Strefa dziecięca"},
    "Licznik Główny": {"icon": "🏢", "desc": "Główny ciepłomierz budynku (GJ)"}
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
EST_PLN_PER_UNIT = 2.45

# ---------------------------------------------------------
# OBSŁUGA DANYCH
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
            df[col] = 0.0 if any(k in col for k in ["start", "end", "delta", "cost"]) else None
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
# INTERFEJS I NAGŁÓWEK DYNAMICZNY
# ---------------------------------------------------------
df = load_data()

if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

head_col1, head_col2 = st.columns([3, 1])
with head_col1:
    st.title("🔥 Sonoff Heating Analytics")
    st.caption("Inteligentne zarządzanie zużyciem ciepła • Sezon 2026/2027 od 01.09.2026")
with head_col2:
    st.markdown('<div style="text-align: right; margin-top: 15px;">'
                '<div class="status-badge"><div class="status-dot"></div>Sonoff System Active</div>'
                '</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# OBLICZENIA GLOBALNE I DLA WYBRANEGO POKOJU
# ---------------------------------------------------------
period_order = list(PERIODS.keys())
df["period_order"] = df["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)

current_room = st.session_state["selected_room"]
df_room = df[df["room_name"] == current_room].sort_values("period_order")

base_df = df_room[df_room["season"] == "2025/2026 (Bazowy)"]
sonoff_df = df_room[df_room["season"] == "2026/2027 (Sonoff od 09.2026)"]

recorded_periods = sonoff_df["period_code"].unique()
base_comparable = base_df[base_df["period_code"].isin(recorded_periods)]

u_sonoff_total = sonoff_df["delta_units"].sum()
u_base_comparable = base_comparable["delta_units"].sum()
u_diff = u_base_comparable - u_sonoff_total
pln_balance = u_diff * EST_PLN_PER_UNIT

# ---------------------------------------------------------
# WIDGET EKRANOWY iOS 18: "CZY JESTEŚMY NA PLUSIE CZY MINUSIE?"
# ---------------------------------------------------------
if len(recorded_periods) > 0:
    if u_diff >= 0:
        eff = ((u_diff / u_base_comparable) * 100) if u_base_comparable > 0 else 0
        st.markdown(
            f"""
            <div class="ios-balance-widget-plus">
                <div class="widget-title" style="color: #1E7E34;">🟢 STAN BILANSU: JESTEŚ NA PLUSIE!</div>
                <div class="widget-amount-plus">+{pln_balance:.2f} PLN</div>
                <div class="widget-subtext">
                    🎉 <b>Świetna robota!</b> W pomieszczeniu <b>{current_room}</b> zaoszczędziłeś <b>{u_diff:.0f} U</b> w porównaniu do ubiegłego roku. 
                    Zużycie jest niższe o <b>{eff:.1f}%</b>. Głowice Sonoff TRVZB działają bardzo efektywnie!
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        diff_abs = abs(u_diff)
        increase = ((diff_abs / u_base_comparable) * 100) if u_base_comparable > 0 else 0
        st.markdown(
            f"""
            <div class="ios-balance-widget-minus">
                <div class="widget-title" style="color: #D32F2F;">🔴 STAN BILANSU: JESTEŚ NA MINUSIE</div>
                <div class="widget-amount-minus">{pln_balance:.2f} PLN</div>
                <div class="widget-subtext">
                    ⚠️ <b>Uwaga!</b> W pomieszczeniu <b>{current_room}</b> zużyłeś o <b>{diff_abs:.0f} U więcej</b> niż w analogicznym okresie rok temu (+{increase:.1f}%). 
                    Sprawdź harmonogram i upewnij się, że obniżasz temperaturę do min. <b>18.5°C</b> w trybie oszczędnym.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
else:
    st.markdown(
        """
        <div class="ios-card" style="border-left: 5px solid #007AFF;">
            ℹ️ <b>Brak wpisów w sezonie 2026/2027.</b><br>
            Wprowadź pierwszy odczyt dla wybranego pomieszczenia w panelu bocznym po lewej stronie, aby aktywować kalkulator zysków i strat w czasie rzeczywistym.
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------------------------------------------------
# KAFLIKI WYBORU POKOJU
# ---------------------------------------------------------
st.markdown("##### 📍 Wybierz Pomieszczenie")
room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (st.session_state["selected_room"] == room_key)
    btn_type = "primary" if is_active else "secondary"
    with room_cols[idx]:
        if st.button(f"{info['icon']} {room_key}", key=f"btn_{room_key}", use_container_width=True, type=btn_type):
            st.session_state["selected_room"] = room_key
            st.rerun()

# ---------------------------------------------------------
# SIDEBAR - SMART FORM
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📥 Nowy Odczyt: {ROOMS_CONFIG[current_room]['icon']}")
    st.caption(f"Wprowadzasz dane dla: **{current_room}**")
    
    season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
    period_code_input = st.selectbox("Okres rozliczeniowy", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
    
    prev_entries = df[(df["room_name"] == current_room) & (df["season"] == season_input)]
    default_start_u = float(prev_entries.iloc[-1]["units_end"]) if not prev_entries.empty and pd.notna(prev_entries.iloc[-1]["units_end"]) else 0.0
    default_start_gj = float(prev_entries.iloc[-1]["gj_end"]) if not prev_entries.empty and pd.notna(prev_entries.iloc[-1]["gj_end"]) else 0.0

    st.caption("✨ *Stan początkowy został uzupełniony automatycznie z poprzedniego odczytu.*")

    with st.form("entry_form"):
        meter_number = st.text_input("Identyfikator podzielnika", value=f"POD-{current_room[:3].upper()}-2026")
        
        st.markdown("---")
        st.markdown("**1. Podzielnik Kaloryfera [Jednostki U]**")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Początek", min_value=0.0, value=default_start_u, step=1.0)
        units_end = col_u2.number_input("Koniec", min_value=0.0, value=default_start_u, step=1.0)
        manual_delta_u = st.number_input("Wpisz bezpośrednio ΔU (opcja)", min_value=0.0, value=0.0, step=1.0)

        st.markdown("---")
        st.markdown("**2. Licznik Główny [GJ]**")
        col_g1, col_g2 = st.columns(2)
        gj_start = col_g1.number_input("GJ początek", min_value=0.0, value=default_start_gj, step=0.01)
        gj_end = col_g2.number_input("GJ koniec", min_value=0.0, value=default_start_gj, step=0.01)
        manual_delta_gj = st.number_input("Wpisz bezpośrednio ΔGJ (opcja)", min_value=0.0, value=0.0, step=0.01)

        st.markdown("---")
        preset_note = st.selectbox(
            "Szybka nastawa Sonoff", 
            ["20.0°C Harmonogram Eco", "21.5°C Comfort", "Tryb Nocny (19.0°C)", "Tryb Wyjazdowe 16.0°C", "Własna nastawa"]
        )
        notes = st.text_input("Komentarz / Opis", value=preset_note)
        cost_per_gj = st.number_input("Cena 1 GJ (PLN)", min_value=0.0, value=105.0, step=1.0)
        target_limit = st.number_input("Target limit (ΔU)", min_value=0.0, value=120.0, step=10.0)
        date_entry = st.date_input("Data wpisu", date.today())

        if st.form_submit_button("⚡ Zapisz Odczyt", use_container_width=True):
            delta_units = (units_end - units_start) if (units_end > units_start and manual_delta_u == 0) else manual_delta_u
            delta_gj = (gj_end - gj_start) if (gj_end > gj_start and manual_delta_gj == 0) else manual_delta_gj

            if delta_units <= 0 and delta_gj <= 0:
                st.error("Proszę podać poprawne zużycie!")
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
                if save_data(df, commit_message=f"Wpis: {current_room} {period_code_input}"):
                    st.success("Zapisano pomyślnie!")
                    st.rerun()

# ---------------------------------------------------------
# METRYKI PODSUMOWUJĄCE
# ---------------------------------------------------------
st.markdown(f"### 📊 Szczegółowe Podsumowanie: {current_room}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Zużycie Sonoff 2026", f"{u_sonoff_total:.0f} U")
c2.metric("Poprzedni Sezon (Ten sam okres)", f"{u_base_comparable:.0f} U")
c3.metric("Bilans Różnicowy", f"{u_diff:+.0f} U", delta=f"{pln_balance:+.2f} PLN")
c4.metric("Postęp Sezonu", f"{len(recorded_periods)} / {len(PERIODS)} okresów")

st.divider()

# ---------------------------------------------------------
# ZAKŁADKI I GRAFIKA DYNAMICZNA PLOTLY
# ---------------------------------------------------------
tab_charts, tab_pacing, tab_advisor, tab_table = st.tabs([
    "📈 Wykresy i Porównania", 
    "🎯 Pacing i Prognoza Sezonu", 
    "💡 Smart Thermostat Advisor", 
    "📋 Pełne Zestawienie Wpisów"
])

with tab_charts:
    st.markdown("#### Porównanie Okresowe: Bazowy 2025/2026 vs Sonoff 2026/2027")
    
    fig_bar = go.Figure()
    if not base_df.empty:
        fig_bar.add_trace(go.Bar(
            x=base_df["period_label"], y=base_df["delta_units"],
            name="2025/2026 (Bez Sonoff)", marker_color="#C7C7CC",
            hovertemplate="Okres: %{x}<br>Zużycie: %{y:.0f} U"
        ))
    if not sonoff_df.empty:
        fig_bar.add_trace(go.Bar(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"],
            name="2026/2027 (Sonoff)", marker_color="#007AFF",
            hovertemplate="Okres: %{x}<br>Zużycie: %{y:.0f} U"
        ))
    fig_bar.update_layout(
        barmode='group', template="plotly_white",
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with tab_pacing:
    st.markdown("#### Dynamiczna Ścieżka Skumulowana (Pacing Chart)")
    
    fig_cum = go.Figure()
    if not base_df.empty:
        fig_cum.add_trace(go.Scatter(
            x=base_df["period_label"], y=base_df["delta_units"].cumsum(),
            mode='lines+markers', name="Skumulowane 2025/2026",
            line=dict(color="#8E8E93", width=2, dash='dash')
        ))
    if not sonoff_df.empty:
        line_color = "#34C759" if u_diff >= 0 else "#FF3B30"
        fig_cum.add_trace(go.Scatter(
            x=sonoff_df["period_label"], y=sonoff_df["delta_units"].cumsum(),
            mode='lines+markers', name="Skumulowane 2026/2027 (Sonoff)",
            line=dict(color=line_color, width=4)
        ))
    fig_cum.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_cum, use_container_width=True)

    if len(recorded_periods) > 0 and len(base_df) > 0:
        total_base_full = base_df["delta_units"].sum()
        ratio = (u_sonoff_total / u_base_comparable) if u_base_comparable > 0 else 1.0
        projected_total = total_base_full * ratio
        projected_sav_pln = (total_base_full - projected_total) * EST_PLN_PER_UNIT

        st.markdown("##### 🔮 Prognoza na Koniec Sezonu (Kwiecień 2027)")
        p_col1, p_col2 = st.columns(2)
        p_col1.metric("Szacowane Zużycie Roczne", f"{projected_total:.0f} U", delta=f"{projected_total - total_base_full:+.0f} U vs zeszły rok")
        p_col2.metric("Prognozowana Oszczędność / Dopłata", f"{projected_sav_pln:+.2f} PLN")

with tab_advisor:
    st.markdown("#### 💡 Rekomendacje Optymalizacyjne Sonoff & Optymalny Harmonogram")
    
    st.markdown("""
    <div class="ios-card">
    <b>🏛️ Zasada Bezwładności Termicznej Budynku</b><br>
    Utrzymanie progu <b>18.5°C</b> jako dolnej granicy pozwala zachować stabilność strukturalną – głowice <b>Sonoff TRVZB</b> jedynie korygują małe wahania temperatury, zamiast za każdym razem walczyć z wychłodzonym betonem stropu.
    </div>
    """, unsafe_allow_html=True)

    schedule_data = [
        {"Strefa": "Przedpokój & Łazienka", "Stan normalny / Komfort": "Stała „4” (~21°C)", "Stan oszczędny": "Brak obniżeń (24/7)", "Dlaczego nie niżej?": "Działają jako stała tarcza termiczna dla całego mieszkania, ogrzewając strefę centralną od dołu i środka."},
        {"Strefa": "Salon (ściana z suszarnią)", "Stan normalny / Komfort": "20.5°C", "Stan oszczędny": "18.5°C", "Dlaczego nie niżej?": "Granica, poniżej której ściana z suszarnią i strop zaczynają oddawać zbyt dużo energii na zewnątrz."},
        {"Strefa": "Sypialnia / Pokój Dzieci", "Stan normalny / Komfort": "21.0°C", "Stan oszczędny": "18.5°C / 19.0°C (noc)", "Dlaczego nie niżej?": "Pustka pod dachem najmocniej daje o sobie znać w nocy; wyższa baza zapobiega wychłodzeniu głowy i sufitu."},
        {"Strefa": "Mały Pokój", "Stan normalny / Komfort": "20.5°C", "Stan oszczędny": "18.5°C", "Dlaczego nie niżej?": "Płytkie obniżenie utrzymuje stabilność termiczną konstrukcji."}
    ]
    st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)
    
    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        st.markdown("""
        <div class="ios-card">
        <b>🌡️ Nastawy Temperatury</b><br>
        • <b>Sypialnia:</b> Zalecana temperatura nocna to 18.5°C – 19.0°C. Obniżenie o 1°C to około 6% oszczędności ciepła.<br>
        • <b>Salon:</b> Utrzymuj 20.5°C podczas obecności domowników i 18.5°C w trybie ekologicznym.
        </div>
        """, unsafe_allow_html=True)
    with adv_col2:
        st.markdown("""
        <div class="ios-card">
        <b>🪟 Wietrzenie i Algorytmy Sonoff</b><br>
        • Korzystaj z funkcji <b>Open Window Detection</b> w głowicach Sonoff, aby automatycznie zamykać zawór na czas wietrzenia.<br>
        • Wietrz pomieszczenia krótko i intensywnie (ok. 5 minut przy szeroko otwartym oknie).
        </div>
        """, unsafe_allow_html=True)

with tab_table:
    st.markdown("#### Wszystkie Wpisy dla Wybranego Pomieszczenia")
    st.dataframe(df_room.sort_values(by=["season", "period_order"]), use_container_width=True)
    
    st.divider()
    del_id = st.number_input("ID wpisu do usunięcia:", min_value=1, step=1)
    if st.button("Usuń Wpis", type="primary"):
        if del_id in df["id"].values:
            df = df[df["id"] != del_id]
            save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
            st.success(f"Usunięto wpis {del_id}")
            st.rerun()
