import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import requests
import time
import json
import base64
import streamlit.components.v1 as components

# ---------------------------------------------------------
# SETUP STRONY
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff - Analiza Ciepła",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Kustomowa stylizacja CSS dla czytelności i wyglądu
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e222d;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2e364f;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e222d 0%, #252a38 100%);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #363d52;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# KONFIGURACJA POMIESZCZEŃ I STAŁE
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "units_start": 3530.0, "meter_default": "522134", "share": 0.45},
    "Dzieciaki": {"icon": "🧸", "units_start": 2100.0, "meter_default": "522135", "share": 0.30},
    "Sypialnia": {"icon": "🛏️", "units_start": 1850.0, "meter_default": "522136", "share": 0.25}
}

MODES = ["Automatyczny (Harmonogram)", "Manualny / Eko", "Komfort 21°C+", "Wietrzenie / Wyłączone"]

# ---------------------------------------------------------
# POBIERANIE POGODY (OPEN-METEO)
# ---------------------------------------------------------
@st.cache_data(ttl=1800)
def get_live_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=50.2972&longitude=18.9897&current=temperature_2m,relative_humidity_2m,weather_code"
        res = requests.get(url, timeout=5).json()
        curr = res.get("current", {})
        return curr.get("temperature_2m", 12.0), curr.get("relative_humidity_2m", 60)
    except Exception:
        return 12.0, 60

live_outdoor_temp, live_humidity = get_live_weather()

# ---------------------------------------------------------
# OBSŁUGA GITHUB API / PLIKU DATA
# ---------------------------------------------------------
DATA_PATH = "data/consumption.csv"

def load_data():
    try:
        if "github" in st.secrets:
            token = st.secrets["github"]["token"]
            repo = st.secrets["github"]["repo"]
            url = f"https://raw.githubusercontent.com/{repo}/main/{DATA_PATH}"
            headers = {"Authorization": f"token {token}"}
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                df = pd.read_csv(pd.compat.StringIO(res.text))
                return df
        return pd.read_csv(DATA_PATH)
    except Exception:
        return pd.DataFrame(columns=[
            "id", "season", "week_num", "period_label", "date_entry", 
            "room_name", "meter_number", "units_start", "units_end", 
            "delta_units", "gj_start", "gj_end", "delta_gj", 
            "temp_zewnetrzna", "temp_wewnetrzna", "mode_tag", "notes"
        ])

def save_data(df, commit_message="Aktualizacja danych"):
    try:
        csv_data = df.to_csv(index=False)
        if "github" in st.secrets:
            token = st.secrets["github"]["token"]
            repo = st.secrets["github"]["repo"]
            url = f"https://api.github.com/repos/{repo}/contents/{DATA_PATH}"
            headers = {"Authorization": f"token {token}"}
            
            get_res = requests.get(url, headers=headers)
            sha = get_res.json().get("sha", "") if get_res.status_code == 200 else ""
            
            content_b64 = base64.b64encode(csv_data.encode("utf-8")).decode("utf-8")
            payload = {
                "message": commit_message,
                "content": content_b64,
                "sha": sha
            }
            put_res = requests.put(url, headers=headers, json=payload)
            return put_res.status_code in [200, 201]
        else:
            df.to_csv(DATA_PATH, index=False)
            return True
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")
        return False

df = load_data()

# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
st.sidebar.image("https://img.icons8.com/fluency/96/thermostat.png", width=60)
st.sidebar.title("Sonoff Heat Hub")

# Przełącznik dla trybu Antigravity w Sidebarze
antigravity_active = st.sidebar.checkbox("🌀 Antigravity Mode", value=False)

st.sidebar.divider()
current_room = st.sidebar.selectbox("Wybierz Strefę", ["Licznik Główny"] + list(ROOMS_CONFIG.keys()))

st.sidebar.divider()
st.sidebar.metric("Pogoda (Bytków)", f"{live_outdoor_temp:.1f} °C", f"Wilgotność: {live_humidity}%")

# ---------------------------------------------------------
# WIDOK FIZYCZNY (ANTIGRAVITY MODE - MATTER.JS)
# ---------------------------------------------------------
if antigravity_active:
    st.title("🌀 Interactive Physical Canvas (Matter.js)")
    st.caption("Fizyczna symulacja kafelków stref grzewczych.")
    
    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js"></script>
        <style>
            body { margin: 0; padding: 0; overflow: hidden; background-color: #0e1117; }
            canvas { width: 100%; height: 500px; display: block; }
        </style>
    </head>
    <body>
    <script>
        const { Engine, Render, Runner, Bodies, Composite, Mouse, MouseConstraint } = Matter;
        const engine = Engine.create();
        const render = Render.create({
            element: document.body,
            engine: engine,
            options: { width: 800, height: 500, wireframes: false, background: '#0e1117' }
        });

        const ground = Bodies.rectangle(400, 490, 800, 20, { isStatic: true, render: { fillStyle: '#2e364f' } });
        const leftWall = Bodies.rectangle(10, 250, 20, 500, { isStatic: true, render: { fillStyle: '#2e364f' } });
        const rightWall = Bodies.rectangle(790, 250, 20, 500, { isStatic: true, render: { fillStyle: '#2e364f' } });

        const boxSalon = Bodies.rectangle(200, 100, 140, 80, { render: { fillStyle: '#ff4b4b' } });
        const boxDzieci = Bodies.rectangle(400, 100, 140, 80, { render: { fillStyle: '#00d4b1' } });
        const boxSypialnia = Bodies.rectangle(600, 100, 140, 80, { render: { fillStyle: '#ffb703' } });

        Composite.add(engine.world, [ground, leftWall, rightWall, boxSalon, boxDzieci, boxSypialnia]);

        const mouse = Mouse.create(render.canvas);
        const mouseConstraint = MouseConstraint.create(engine, {
            mouse: mouse,
            constraint: { stiffness: 0.2, render: { visible: false } }
        });
        Composite.add(engine.world, mouseConstraint);

        Render.run(render);
        Runner.run(Runner.create(), engine);
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=520)

# ---------------------------------------------------------
# PANEL GŁÓWNY (ANALIZA + ZBIORCZY WTOREK)
# ---------------------------------------------------------
else:
    st.title("🔥 Sonoff TRVZB – System Monitorowania Ciepła")
    
    # SPRAWDŹ CZY DZIŚ JEST WTOREK
    today = date.today()
    is_tuesday = (today.weekday() == 1)

    if "fancy_alert" in st.session_state:
        elapsed = time.time() - st.session_state["fancy_alert"]["timestamp"]
        if elapsed > 300:
            del st.session_state["fancy_alert"]

    if is_tuesday:
        current_year, current_iso_w, _ = today.isocalendar()
        
        df_sonoff_this_week = df[(df["week_num"] == current_iso_w) & (df["season"] == "2026/2027 (Sonoff - Wtorki)")] if not df.empty else pd.DataFrame()
        logged_rooms = df_sonoff_this_week["room_name"].unique() if not df_sonoff_this_week.empty else []
        missing_rooms = [r for r in ["Salon", "Dzieciaki", "Sypialnia"] if r not in logged_rooms]

        if missing_rooms:
            with st.expander(f"🚨 WTOREK – Wymagane Odczyty Wtorkowe (Tydzień {current_iso_w})", expanded=True):
                st.warning(f"Dziś jest wtorek! Wprowadź dzisiejsze odczyty z podzielników dla brakujących pomieszczeń: **{', '.join(missing_rooms)}**.")
                
                with st.form("auto_tuesday_all_rooms_form"):
                    inputs_data = {}
                    
                    for r_name in missing_rooms:
                        st.markdown(f"### {ROOMS_CONFIG[r_name]['icon']} {r_name}")
                        r_df = df[(df["room_name"] == r_name) & (df["season"].str.contains("Sonoff", na=False))] if not df.empty else pd.DataFrame()
                        
                        r_last_val = float(r_df.iloc[-1]["units_end"]) if not r_df.empty else ROOMS_CONFIG[r_name]["units_start"]
                        r_meter = str(r_df.iloc[-1]["meter_number"]) if not r_df.empty else ROOMS_CONFIG[r_name]["meter_default"]
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            m_num = st.text_input(f"Nr podzielnika ({r_name})", value=r_meter, key=f"m_{r_name}")
                        with c2:
                            u_start = st.number_input(f"Poprzedni stan ({r_name})", value=r_last_val, disabled=True, key=f"us_{r_name}")
                        with c3:
                            u_end = st.number_input(f"Nowy stan [U] ({r_name})", min_value=r_last_val, value=r_last_val, step=0.1, key=f"ue_{r_name}")
                        
                        t_in = st.number_input(f"Temp. wewnątrz [°C] ({r_name})", min_value=10.0, max_value=30.0, value=21.0, step=0.1, key=f"t_{r_name}")
                        
                        inputs_data[r_name] = {
                            "meter": m_num,
                            "u_start": r_last_val,
                            "u_end": u_end,
                            "temp_in": t_in
                        }
                        st.divider()

                    m_tag = st.selectbox("Wspólny tryb pracy grzania", MODES, index=0)
                    modal_notes = st.text_input("Uwagi / Nastawa", value="Zbiorczy odczyt wtorkowy")

                    if st.form_submit_button("⚡ Zapisz odczyty dla wszystkich stref", use_container_width=True):
                        new_rows = []
                        next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1
                        
                        for r_name, data in inputs_data.items():
                            delta_u = data["u_end"] - data["u_start"]
                            
                            new_rows.append({
                                "id": next_id,
                                "season": "2026/2027 (Sonoff - Wtorki)",
                                "week_num": current_iso_w,
                                "period_label": f"Tydzień {current_iso_w:02d} (Wtorek)",
                                "date_entry": str(today),
                                "room_name": r_name,
                                "meter_number": data["meter"],
                                "units_start": data["u_start"],
                                "units_end": data["u_end"],
                                "delta_units": delta_u,
                                "gj_start": 0.0,
                                "gj_end": 0.0,
                                "delta_gj": 0.0,
                                "temp_zewnetrzna": live_outdoor_temp,
                                "temp_wewnetrzna": data["temp_in"],
                                "mode_tag": m_tag,
                                "notes": modal_notes
                            })
                            next_id += 1

                        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                        if save_data(df, commit_message=f"Zbiorczy odczyt wtorkowy T{current_iso_w}"):
                            st.success("Zapisano odczyty dla wszystkich pomieszczeń!")
                            st.rerun()

    # PODTYTUŁ STREFY
    room_share_pct = ROOMS_CONFIG.get(current_room, {}).get("share", 1.0) * 100
    room_desc_subtitle = "Suma wszystkich pokoi w mieszkaniu" if current_room == "Licznik Główny" else f"Pojedyncza strefa grzewcza ({room_share_pct:.1f}% udziału w mieszkaniu)"

    st.caption(room_desc_subtitle)

    # FILTROWANIE DANYCH
    if current_room == "Licznik Główny":
        df_filtered = df.copy()
    else:
        df_filtered = df[df["room_name"] == current_room] if not df.empty else pd.DataFrame()

    # METRYKI
    m1, m2, m3, m4 = st.columns(4)
    total_units = df_filtered["delta_units"].sum() if not df_filtered.empty else 0.0
    avg_temp_in = df_filtered["temp_wewnetrzna"].mean() if not df_filtered.empty else 0.0
    last_reading = df_filtered["units_end"].iloc[-1] if not df_filtered.empty else 0.0

    m1.metric("Łącznie Zużyte Jednostki [U]", f"{total_units:.1f} U")
    m2.metric("Ostatni Stan Podzielnika", f"{last_reading:.1f}")
    m3.metric("Średnia Temp. Wewnętrzna", f"{avg_temp_in:.1f} °C")
    m4.metric("Aktualna Temp. Zewnętrzna", f"{live_outdoor_temp:.1f} °C")

    # WYKRES ZUŻYCIA
    st.divider()
    st.subheader("📈 Zużycie Ciepła w Czasie")

    if not df_filtered.empty:
        fig = px.bar(
            df_filtered, 
            x="period_label", 
            y="delta_units", 
            color="room_name", 
            title="Przyrost Zużycia Jednostek [U] wg Okresów",
            labels={"delta_units": "Zużycie [U]", "period_label": "Okres", "room_name": "Strefa"},
            barmode="group"
        )
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Brak danych do wyświetlenia wykresu. Dodaj pierwsze odczyty w bazie danych.")
