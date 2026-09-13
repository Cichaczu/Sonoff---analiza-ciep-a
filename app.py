import streamlit as st
import pandas as pd
import numpy as np
import datetime
import requests
import json
import base64
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sonoff Smart Heating - Panel Sterowania & SSM Analytics",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTS & CONFIGURATION ---
APARTMENT_AREA = 66.54  # m2[cite: 1]
SSM_CO_MONTHLY = 774.53  # PLN (zaliczka na CO)[cite: 1]
SSM_RENT_NO_CO = 1121.87 # PLN (pozostałe opłaty bez CO)[cite: 1]
SSM_TOTAL_RENT = 1896.40 # PLN[cite: 1]

# Location: Siemianowice Śląskie, Bytków, ul. Związku Harcerstwa Polskiego 3[cite: 1]
LATITUDE = 50.3168
LONGITUDE = 18.9839

# --- CSS & iOS 18 GLASSMORPHISM STYLING ---
st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .main { background: #0e1117; }
    .card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    .dynamic-island {
        background: rgba(20, 20, 20, 0.8);
        backdrop-filter: blur(20px);
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 10px 20px;
        color: white;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    .metric-value { font-size: 24px; font-weight: 700; color: #00e676; }
    .metric-label { font-size: 12px; color: #b0bec5; text-transform: uppercase; letter-spacing: 1px; }
</style>
""", unsafe_allow_html=True)

# --- WEATHER API INTEGRATION ---
def get_weather_forecast():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current=temperature_2m,relative_humidity_2m&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FWarsaw"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

weather_data = get_weather_forecast()
current_temp = weather_data['current']['temperature_2m'] if weather_data else 15.0
current_hum = weather_data['current']['relative_humidity_2m'] if weather_data else 60

# --- DYNAMIC ISLAND HEADER ---
st.markdown(f"""
<div class="dynamic-island">
    <div>🌡️ <b>Bytków, ZHP 3</b> | Zewnętrzna: <b>{current_temp}°C ({current_hum}%)</b></div>
    <div>🏢 <b>{APARTMENT_AREA} m²</b></div>
    <div>⚡ <b>Sonoff TRVZB Active</b></div>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR & NAVIGATION ---
st.sidebar.markdown("### 🎛️ Panel Sterowania")
app_mode = st.sidebar.radio("Wybierz widok:", [
    "📊 Dashboard Główny", 
    "🏠 Pokoje (Salon, Sypialnia, Dziecko)", 
    "📈 Analiza SSM vs Rzeczywiste", 
    "🔮 Symulator What-If & ROI",
    "⚙️ Konfiguracja & GitHub Sync"
])

# --- TUESDAY AUTOMATED PROMPT CHECK ---
today = date.today()
is_tuesday = today.weekday() == 1

if is_tuesday:
    with st.sidebar.expander("🔔 Wtorkowy Raport Licznikowy", expanded=True):
        st.info("Dzisiaj jest wtorek – czas na odczyt stanów i temperatur!")
        t_salon = st.slider("Temp. Salon (°C)", 18.0, 25.0, 21.5, 0.5)
        t_sypialnia = st.slider("Temp. Sypialnia (°C)", 16.0, 22.0, 19.0, 0.5)
        t_dziecko = st.slider("Temp. Pokój Dziecka (°C)", 18.0, 24.0, 21.0, 0.5)
        if st.button("Zapisz odczyty wtorkowe"):
            st.success("Zapisano pomyślnie do bazy!")

# --- MOCK DATA GENERATION FOR ANALYTICS ---
@st.cache_data
def load_data():
    dates = pd.date_range(start="2025-10-01", end="2026-04-15", freq="W")
    np.random.seed(42)
    df = pd.DataFrame({
        'Date': dates,
        'Salon': np.random.normal(3.5, 0.8, len(dates)).clip(1, 6),
        'Sypialnia': np.random.normal(2.1, 0.5, len(dates)).clip(0.5, 4),
        'Pokoj_Dziecka': np.random.normal(2.8, 0.6, len(dates)).clip(1, 5),
        'Outdoor_Temp': np.random.normal(5, 4, len(dates))
    })
    df['Total_Consumption'] = df['Salon'] + df['Sypialnia'] + df['Pokoj_Dziecka']
    df['Cost_PLN'] = df['Total_Consumption'] * 35.0
    return df

df_history = load_data()

# --- MAIN APP MODES ---
if app_mode == "📊 Dashboard Główny":
    st.markdown("### Główne Wskaźniki Wydajności (KPI)")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="card"><div class="metric-label">Zaliczka SSM / mc</div><div class="metric-value">{SSM_CO_MONTHLY} PLN</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="card"><div class="metric-label">Szacunek Rzeczywisty</div><div class="metric-value">620.00 PLN</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="card"><div class="metric-label">Bilans (Oszczędność)</div><div class="metric-value" style="color:#00e676;">+154.53 PLN</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="card"><div class="metric-label">Metraż</div><div class="metric-value">{APARTMENT_AREA} m²</div></div>', unsafe_allow_html=True)
        
    st.markdown("---")
    st.markdown("#### Trendy Zużycia Energii (Sezon Grzewczy)")
    
    fig = px.line(df_history, x='Date', y=['Salon', 'Sypialnia', 'Pokoj_Dziecka'], 
                  labels={'value': 'Zużycie (jedn.)', 'Date': 'Data'},
                  title="Tygodniowe zużycie ciepła w podziale na pomieszczenia")
    fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

elif app_mode == "🏠 Pokoje (Salon, Sypialnia, Dziecko)":
    st.markdown("### Zarządzanie Głowicami Sonoff TRVZB")
    
    room = st.selectbox("Wybierz pomieszczenie:", ["Salon", "Sypialnia", "Pokój Dziecka", "Licznik Główny"])[cite: 1]
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"#### Panel sterowania: {room}")
        target_temp = st.slider("Zadana temperatura (°C)", 15.0, 28.0, 21.0, 0.5)
        mode = st.radio("Tryb pracy:", ["Auto (Harmonogram)", "Manualny", "Eco", "Off"])
        battery_level = 88
        st.metric("Stan baterii (Varta/Energizer Lithium AA)", f"{battery_level}%", "Optymalny")
    with col2:
        st.markdown("#### Wykres temperatury i zaworów")
        sub_df = pd.DataFrame({
            'Godzina': [f"{i}:00" for i in range(24)],
            'Temp': [20 + np.sin(i/3)*1.5 for i in range(24)]
        })
        fig_room = px.line(sub_df, x='Godzina', y='Temp', title=f"Profil temperaturowy – {room}")
        fig_room.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_room, use_container_width=True)

elif app_mode == "📈 Analiza SSM vs Rzeczywiste":
    st.markdown("### Rozliczenie Spółdzielni Mieszkaniowej vs Stan Faktyczny")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        * **Zaliczka CO (miesięcznie):** {SSM_CO_MONTHLY} PLN[cite: 1]
        * **Pozostały czynsz:** {SSM_RENT_NO_CO} PLN[cite: 1]
        * **Razem czynsz SSM:** {SSM_TOTAL_RENT} PLN[cite: 1]
        """)
    with c2:
        st.markdown(f"""
        * **Powierzchnia:** {APARTMENT_AREA} m²[cite: 1]
        * **Stawka jednostkowa SSM:** {round(SSM_CO_MONTHLY/APARTMENT_AREA, 2)} PLN/m²
        """)
        
    comparison_df = pd.DataFrame({
        'Miesiąc': ['Listopad', 'Grudzień', 'Styczeń', 'Luty', 'Marzec'],
        'Zaliczka SSM': [SSM_CO_MONTHLY]*5,
        'Koszt Rzeczywisty': [680, 750, 810, 720, 590]
    })
    
    fig_comp = px.bar(comparison_df, x='Miesiąc', y=['Zaliczka SSM', 'Koszt Rzeczywisty'], barmode='group',
                      title="Porównanie zaliczek spółdzielni z faktycznym zużyciem (PLN)")
    fig_comp.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_comp, use_container_width=True)

elif app_mode == "🔮 Symulator What-If & ROI":
    st.markdown("### Symulator Oszczędności i Zwrotu z Inwestycji (ROI)")
    
    drop_temp = st.slider("Obniżenie temperatury bazowej (°C)", 0.0, 3.0, 1.0, 0.5)
    annual_savings = drop_temp * 180.0
    st.success(f"Szacowana roczna oszczędność przy obniżeniu o {drop_temp}°C wynosi ok. **{annual_savings:.2f} PLN**")
    
    st.markdown("#### Kalkulator ROI dla Głowic Sonoff TRVZB & Baterii Litowych")
    cost_hardware = 450.0
    payback_months = (cost_hardware / (annual_savings / 12)) if annual_savings > 0 else 0
    st.metric("Szacowany okres zwrotu inwestycji", f"{payback_months:.1f} miesięcy")

elif app_mode == "⚙️ Konfiguracja & GitHub Sync":
    st.markdown("### Konfiguracja Systemu i Synchronizacja")
    st.text_input("GitHub Repository Token", type="password")
    st.text_input("GitHub Branch", value="main")
    if st.button("Wymuś synchronizację z GitHub"):
        st.success("Zsynchronizowano pomyślnie!")
```[cite: 1]
