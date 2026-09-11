import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date, datetime, timedelta

# ---------------------------------------------------------
# KONFIGURACJA STRONY & STYLE iOS 18
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Analytics",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45

st.markdown("""
    <style>
    @import url('https://fonts.cdnfonts.com/css/sf-pro-display');
    
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif !important;
        background-color: #F2F2F7 !important;
        color: #1C1C1E;
    }

    .stApp { background: linear-gradient(180deg, #F2F2F7 0%, #E5E5EA 100%); }

    .ios-card {
        background: rgba(255, 255, 255, 0.8) !important;
        backdrop-filter: blur(30px) saturate(190%);
        border-radius: 24px !important;
        padding: 22px 26px !important;
        border: 1.5px solid rgba(255, 255, 255, 0.85) !important;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.04) !important;
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
        margin-bottom: 20px;
    }
    
    .ios-card:hover {
        transform: translateY(-4px) scale(1.015) !important;
        box-shadow: 0 16px 40px rgba(0, 122, 255, 0.12) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(120, 120, 128, 0.12) !important;
        backdrop-filter: blur(20px);
        padding: 5px;
        border-radius: 18px !important;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.12) !important;
    }
    </style>
""", unsafe_allow_html=True)

ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "meter": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter": "POD-SYP-2026"},
    "Pokój Dziecka": {"icon": "🧒", "meter": "POD-DZI-2026"},
    "Licznik Główny": {"icon": "🏢", "meter": "GJ-MAIN-2026"}
}

# ---------------------------------------------------------
# OBSŁUGA DANYCH
# ---------------------------------------------------------
def create_empty_df():
    return pd.DataFrame(columns=[
        "id", "season", "week_num", "period_label", "date_entry",
        "room_name", "meter_number", "units_start", "units_end", "delta_units",
        "gj_start", "gj_end", "delta_gj", "notes"
    ])

def load_data():
    if os.path.exists(FILE_PATH):
        try: return pd.read_csv(FILE_PATH)
        except Exception: return create_empty_df()
    return create_empty_df()

df = load_data()

st.title("🔥 Sonoff Smart Heating - Centrum Analityczne iOS 18")

# ---------------------------------------------------------
# TABY Z WYKRESAMI I RAPORTAMI
# ---------------------------------------------------------
tab_analytics, tab_zones, tab_raw = st.tabs([
    "📊 Wykresy Zysków i Podziału", 
    "🛋️ Analiza Strefowa", 
    "📋 Dane Źródłowe"
])

with tab_analytics:
    st.markdown("### 💸 Osobny Wykres Oszczędności i Strat (PLN)")
    
    if not df.empty:
        # Przygotowanie danych zagregowanych per tydzień dla sezonu Sonoff vs Bazowy
        df_sonoff = df[df["season"].str.contains("Sonoff", na=False)].copy()
        df_base = df[df["season"].str.contains("Bazowy", na=False)].copy()

        # Łączenie i wyliczanie różnicy
        df_weekly = df_sonoff.groupby(["week_num", "period_label"])["delta_units"].sum().reset_index()
        df_weekly_base = df_base.groupby(["week_num"])["delta_units"].sum().reset_index().rename(columns={"delta_units": "base_units"})
        
        df_merged = pd.merge(df_weekly, df_weekly_base, on="week_num", how="left").fillna(0)
        df_merged["units_saved"] = df_merged["base_units"] - df_merged["delta_units"]
        df_merged["pln_balance"] = df_merged["units_saved"] * EST_PLN_PER_UNIT
        df_merged["color"] = df_merged["pln_balance"].apply(lambda x: "#34C759" if x >= 0 else "#FF3B30")

        # 1. WYKRES BILANSU ZYSKÓW / STRAT (PLN)
        fig_balance = go.Figure()
        fig_balance.add_trace(go.Bar(
            x=df_merged["period_label"],
            y=df_merged["pln_balance"],
            marker_color=df_merged["color"],
            hovertemplate="Tydzień: %{x}<br>Bilans: <b>%{y:.2f} PLN</b>",
            text=df_merged["pln_balance"].apply(lambda x: f"{'++' if x>=0 else ''}{x:.1f} zł"),
            textposition="outside"
        ))
        fig_balance.update_layout(
            title="Tygodniowy Bilans Finansowy (Zysk = Zielony / Strata = Czerwony)",
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=380,
            font=dict(family="-apple-system, SF Pro Display", color="#1C1C1E"),
            yaxis_title="Bilans [PLN]"
        )
        
        st.markdown('<div class="ios-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_balance, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        col_left, col_right = st.columns(2)

        with col_left:
            # 2. KUMULACJA ZYSKÓW W CZASIE (AREA CHART)
            df_merged["cum_pln"] = df_merged["pln_balance"].cumsum()
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=df_merged["period_label"],
                y=df_merged["cum_pln"],
                mode="lines+markers",
                fill="tozeroy",
                line=dict(color="#34C759" if df_merged["cum_pln"].iloc[-1]>=0 else "#FF3B30", width=3),
                marker=dict(size=8),
                hovertemplate="Skumulowany Bilans: <b>%{y:.2f} PLN</b>"
            ))
            fig_cum.update_layout(
                title="Skumulowane Oszczędności w Sezonie [PLN]",
                template="plotly_white",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=320,
                font=dict(family="-apple-system, SF Pro Display")
            )
            st.markdown('<div class="ios-card">', unsafe_allow_html=True)
            st.plotly_chart(fig_cum, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_right:
            # 3. STRUKTURA ZUŻYCIA POKOJÓW (PIE / DONUT CHART)
            df_rooms_pie = df_sonoff.groupby("room_name")["delta_units"].sum().reset_index()
            fig_pie = px.pie(
                df_rooms_pie, 
                values="delta_units", 
                names="room_name", 
                hole=0.55,
                color_discrete_sequence=["#007AFF", "#5856D6", "#FF9500", "#FF2D55"]
            )
            fig_pie.update_layout(
                title="Udział Pomieszczeń w Całkowitym Zużyciu",
                template="plotly_white",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=320,
                font=dict(family="-apple-system, SF Pro Display")
            )
            st.markdown('<div class="ios-card">', unsafe_allow_html=True)
            st.plotly_chart(fig_pie, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # 4. PORÓWNANIE SEZON DO SEZONA (BAR BAZOWY VS SONOFF)
        st.markdown("### 🔄 Porównanie Zużycia: Rok Baza vs Rok Sonoff")
        
        df_comp = df.groupby(["period_label", "season"])["delta_units"].sum().reset_index()
        fig_comp = px.bar(
            df_comp, 
            x="period_label", 
            y="delta_units", 
            color="season",
            barmode="group",
            color_discrete_map={
                "2025/2026 (Bazowy)": "#8E8E93",
                "2026/2027 (Sonoff - Wtorki)": "#007AFF"
            }
        )
        fig_comp.update_layout(
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=360,
            font=dict(family="-apple-system, SF Pro Display"),
            yaxis_title="Jednostki Podzielnika [U]"
        )
        st.markdown('<div class="ios-card">', unsafe_allow_html=True)
        st.plotly_chart(fig_comp, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.info("Dodaj odczyty w panelu bocznym, aby odblokować zaawansowane wykresy bilansowe.")
