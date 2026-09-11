import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from github import Github, GithubException
import io
import os
from datetime import date

# ---------------------------------------------------------
# KONFIGURACJA STRONY STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Zarządzanie Ogrzewaniem - Sonoff (od 10.2026)",
    page_icon="🔥",
    layout="wide"
)

FILE_PATH = "data/consumption.csv"

# ---------------------------------------------------------
# SŁOWNIKI I MAPOWANIE POKOI
# ---------------------------------------------------------
ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "desc": "Główna strefa dzienna"},
    "Sypialnia": {"icon": "🛏️", "desc": "Strefa nocna"},
    "Kuchnia": {"icon": "🍳", "desc": "Strefa kuchenna"},
    "Pokój Dziecka": {"icon": "🧒", "desc": "Strefa dziecięca"},
    "Łazienka": {"icon": "🛁", "desc": "Strefa sanitarna"},
    "Licznik Główny": {"icon": "🏢", "desc": "Ciepłomierze / Cały budynek"}
}

PERIODS = {
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

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff od 10.2026)"]

# ---------------------------------------------------------
# OBSŁUGA BAZY DANYCH I INTEGRACJA Z GITHUB
# ---------------------------------------------------------
def get_github_repo():
    """Bezpieczne pobieranie repozytorium z GitHub z obsługą błędów."""
    try:
        github_config = st.secrets.get("github", {})
        token = github_config.get("token")
        repo_name = github_config.get("repo")
        
        if token and repo_name and len(token.strip()) > 0 and len(repo_name.strip()) > 0:
            g = Github(token)
            return g.get_repo(repo_name)
    except Exception:
        return None
    return None

def create_empty_df():
    """Tworzenie pustej struktury DataFrame z obsługą nr licznika, jednostek U i GJ."""
    return pd.DataFrame(columns=[
        "id", "season", "period_code", "period_label", "date_entry",
        "room_name", "meter_number", "units_start", "units_end", "delta_units",
        "gj_start", "gj_end", "delta_gj", "hdd", "sgi", "sgi_gj",
        "cost_per_gj", "notes"
    ])

def load_data():
    """Ładowanie danych z GitHub lub lokalnego pliku fallback z migracją kolumn."""
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    
    df = None
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            csv_raw = file_content.decoded_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_raw))
        except GithubException as e:
            if e.status == 404:
                df = create_empty_df()
                save_data(df, commit_message="Inicjalizacja pliku data/consumption.csv")
            else:
                st.warning(f"Brak dostępu do GitHub (Kod HTTP {e.status}). Przełączono w tryb lokalny.")
                df = load_local_fallback()
        except Exception:
            df = load_local_fallback()
    else:
        df = load_local_fallback()

    # Zapewnienie wstecznej kompatybilności dla nowych kolumn (np. meter_number)
    required_cols = create_empty_df().columns
    for col in required_cols:
        if col not in df.columns:
            if col in ["gj_start", "gj_end", "delta_gj", "sgi_gj", "cost_per_gj"]:
                df[col] = 0.0
            elif col == "meter_number":
                df[col] = "—"
            else:
                df[col] = None
    return df

def load_local_fallback():
    """Wczytywanie z lokalnego pliku na dysku."""
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

def save_data(df, commit_message="Aktualizacja odczytów zużycia ciepła"):
    """Zapisywanie danych do GitHub (auto-commit) lub na dysk lokalny."""
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_string = csv_buffer.getvalue()

    if repo:
        try:
            try:
                file_content = repo.get_contents(FILE_PATH, ref=branch)
                repo.update_file(
                    path=FILE_PATH,
                    message=commit_message,
                    content=csv_string,
                    sha=file_content.sha,
                    branch=branch
                )
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(
                        path=FILE_PATH,
                        message=commit_message,
                        content=csv_string,
                        branch=branch
                    )
                else:
                    raise e
            return True
        except Exception as e:
            st.error(f"Nie udało się zapisać danych na GitHubie: {e}")
            return False
    else:
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        st.info("Zapisano lokalnie.")
        return True

# ---------------------------------------------------------
# STAN APLIKACJI & GRAFICZNY WYBÓR POKOJU
# ---------------------------------------------------------
df = load_data()

if "selected_room" not in st.session_state:
    st.session_state["selected_room"] = "Salon"

st.title("🔥 System Analizy Ogrzewania: Głowice Sonoff vs Sezon Ubiegły")
st.caption("Porównanie zużycia ciepła od Października 2026 (z głowicami smart Sonoff) z zeszłorocznym bazowym sezonem 2025/2026.")

st.markdown("### 🏠 Wybierz Pokój / Licznik")

# Graficzne kafelki wyboru pomieszczenia
cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
    is_active = (st.session_state["selected_room"] == room_key)
    button_label = f"{info['icon']} {room_key}"
    if is_active:
        button_label = f"✅ {room_key}"
    
    with cols[idx]:
        if st.button(
            button_label, 
            key=f"btn_room_{room_key}", 
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state["selected_room"] = room_key
            st.rerun()

current_room = st.session_state["selected_room"]

st.info(f"Wybrany obszar: **{ROOMS_CONFIG[current_room]['icon']} {current_room}** — {ROOMS_CONFIG[current_room]['desc']}")

st.divider()

# ---------------------------------------------------------
# FORMULARZ WPROWADZANIA ODCZYTÓW & NUMER LICZNIKA
# ---------------------------------------------------------
with st.sidebar:
    st.header(f"📥 Odczyt: {ROOMS_CONFIG[current_room]['icon']} {current_room}")
    
    with st.form("entry_form", clear_on_submit=False):
        season = st.selectbox("Sezon grzewczy", SEASONS, index=1)
        period_code = st.selectbox("Okres rozliczeniowy", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
        
        st.markdown("---")
        st.subheader("🔢 Identyfikator Licznika")
        meter_number = st.text_input(
            "Numer licznika / podzielnika", 
            value=f"POD-{current_room.upper()[:3]}-01" if current_room != "Licznik Główny" else "GJ-MAIN-2026",
            help="Podaj ciąg cyfr lub oznaczenie nadrukowane na podzielniku / ciepłomierzu."
        )

        st.markdown("---")
        st.subheader("1. Odczyt Podzielnika (Jednostki U)")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Stan początkowy", min_value=0.0, value=0.0, step=1.0)
        units_end = col_u2.number_input("Stan końcowy", min_value=0.0, value=0.0, step=1.0)
        
        manual_delta_u = st.number_input("Lub zużycie bezpośrednie (ΔU)", min_value=0.0, value=0.0, step=1.0)

        st.markdown("---")
        st.subheader("2. Odczyt Ciepłomierza Głównego (GJ)")
        col_gj1, col_gj2 = st.columns(2)
        gj_start = col_gj1.number_input("GJ początek", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        gj_end = col_gj2.number_input("GJ koniec", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        manual_delta_gj = st.number_input("Lub zużycie w GJ (ΔGJ)", min_value=0.0, value=0.0, step=0.01, format="%.2f")

        st.markdown("---")
        st.subheader("3. Pogoda i Finanse")
        hdd_input = st.number_input("Stopniodni (HDD)", min_value=0.1, value=150.0, step=0.1,
                                    help="Suma HDD z Państwowej Stacji Meteo dla minionego okresu 2 tygodni.")
        cost_per_gj = st.number_input("Cena za 1 GJ (PLN)", min_value=0.0, value=105.0, step=1.0)
        date_entry = st.date_input("Data spisania odczytu", date.today())
        notes = st.text_input("Uwagi (np. temp. zadana w Sonoff)", value="Nastawa 20.5°C")

        submitted = st.form_submit_button("💾 Zapisz Odczyt w Bazie")

        if submitted:
            # Obliczenie zużycia ΔU
            if (units_end > units_start) and (manual_delta_u == 0):
                delta_units = units_end - units_start
            else:
                delta_units = manual_delta_u

            # Obliczenie zużycia ΔGJ
            if (gj_end > gj_start) and (manual_delta_gj == 0):
                delta_gj = gj_end - gj_start
            else:
                delta_gj = manual_delta_gj

            if delta_units <= 0 and delta_gj <= 0:
                st.error("Wprowadź poprawne zużycie (ΔU > 0 lub ΔGJ > 0)!")
            else:
                sgi_u = round(delta_units / hdd_input, 4) if hdd_input > 0 else 0.0
                sgi_gj = round(delta_gj / hdd_input, 6) if hdd_input > 0 else 0.0

                # Nadpisanie dubla dla danego sezonu, okresu i pokoju
                if not df.empty:
                    df = df[~((df["season"] == season) & 
                              (df["period_code"] == period_code) & 
                              (df["room_name"] == current_room))]

                next_id = int(df["id"].max() + 1) if not df.empty and pd.notna(df["id"].max()) else 1

                new_row = pd.DataFrame([{
                    "id": next_id,
                    "season": season,
                    "period_code": period_code,
                    "period_label": PERIODS[period_code],
                    "date_entry": str(date_entry),
                    "room_name": current_room,
                    "meter_number": meter_number,
                    "units_start": units_start,
                    "units_end": units_end,
                    "delta_units": delta_units,
                    "gj_start": gj_start,
                    "gj_end": gj_end,
                    "delta_gj": delta_gj,
                    "hdd": hdd_input,
                    "sgi": sgi_u,
                    "sgi_gj": sgi_gj,
                    "cost_per_gj": cost_per_gj,
                    "notes": notes
                }])

                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Odczyt {current_room} ({meter_number}): {season} - {PERIODS[period_code]}"):
                    st.success("Wpis został pomyślnie zapisany!")
                    st.rerun()

# ---------------------------------------------------------
# AUTOMATYCZNE WYKRESY I ANALIZA PORÓWNAWCZA
# ---------------------------------------------------------
df_filtered = df[df["room_name"] == current_room].copy()

# Sortowanie według kolejności chronologicznej okresów grzewczych
period_order = list(PERIODS.keys())
df_filtered["period_order"] = df_filtered["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)
df_filtered = df_filtered.sort_values("period_order")

base_df = df_filtered[df_filtered["season"] == "2025/2026 (Bazowy)"]
sonoff_df = df_filtered[df_filtered["season"] == "2026/2027 (Sonoff od 10.2026)"]

# Nagłówek KPI
st.markdown(f"### 📊 Podsumowanie Efektywności: {ROOMS_CONFIG[current_room]['icon']} {current_room}")

col1, col2, col3, col4 = st.columns(4)

avg_sgi_base = base_df["sgi"].mean() if not base_df.empty else 0.0
avg_sgi_sonoff = sonoff_df["sgi"].mean() if not sonoff_df.empty else 0.0

sgi_change = ((avg_sgi_base - avg_sgi_sonoff) / avg_sgi_base * 100) if avg_sgi_base > 0 and avg_sgi_sonoff > 0 else 0.0

# Porównanie zestawione okres po okresie
merged_comp = pd.merge(
    sonoff_df, base_df, 
    on="period_code", 
    suffixes=('_sonoff', '_base')
)

if not merged_comp.empty:
    merged_comp["expected_units"] = merged_comp["sgi_base"] * merged_comp["hdd_sonoff"]
    merged_comp["units_saved"] = merged_comp["expected_units"] - merged_comp["delta_units_sonoff"]
    total_u_saved = merged_comp["units_saved"].sum()

    if "sgi_gj_base" in merged_comp.columns and "sgi_gj_sonoff" in merged_comp.columns:
        merged_comp["expected_gj"] = merged_comp["sgi_gj_base"] * merged_comp["hdd_sonoff"]
        merged_comp["gj_saved"] = merged_comp["expected_gj"] - merged_comp["delta_gj_sonoff"]
        total_gj_saved = merged_comp["gj_saved"].sum()
    else:
        total_gj_saved = 0.0
else:
    total_u_saved = 0.0
    total_gj_saved = 0.0

avg_cost_gj = df["cost_per_gj"].replace(0, pd.NA).dropna().mean()
if pd.isna(avg_cost_gj) or avg_cost_gj == 0:
    avg_cost_gj = 105.0

pln_saved = total_gj_saved * avg_cost_gj

col1.metric(
    "Średnie SGI (U / HDD)", 
    f"{avg_sgi_sonoff:.3f}",
    delta=f"{sgi_change:+.1f}% oszczędności" if sgi_change != 0 else None,
    delta_color="normal" if sgi_change >= 0 else "inverse"
)
col2.metric("Oszczędność Energii", f"{total_gj_saved:+.2f} GJ")
col3.metric("Zysk Finansowy", f"{pln_saved:+.2f} PLN")
col4.metric("Zaoszczędzone Jednostki", f"{total_u_saved:+.1f} U")

st.divider()

# ---------------------------------------------------------
# TABY I WYKRESY ZUŻYCIA (AUTOMATYCZNIE GENEROWANE)
# ---------------------------------------------------------
tab_charts, tab_audit, tab_sim, tab_table = st.tabs([
    "📈 Wykresy Porównawcze (Sonoff vs Bazowy)", 
    "🔎 Audyt Licznika & Przelicznik", 
    "💰 Symulacja Kosztów PLN", 
    "📋 Pełna Tabela Wpisów"
])

with tab_charts:
    st.subheader("Automatyczne Wykresy Zużycia: Październik 2026 vs Zeszły Sezon")
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.markdown("#### Dynamiczne Wskaźniki $SGI = \\frac{\\Delta U}{\\text{HDD}}$")
        fig_sgi = go.Figure()
        
        if not base_df.empty:
            fig_sgi.add_trace(go.Bar(
                x=base_df["period_label"], y=base_df["sgi"],
                name="2025/2026 (Bez Sonoff)", marker_color="#95a5a6",
                text=base_df["sgi"].apply(lambda x: f"{x:.3f}"), textposition='auto'
            ))
            
        if not sonoff_df.empty:
            fig_sgi.add_trace(go.Bar(
                x=sonoff_df["period_label"], y=sonoff_df["sgi"],
                name="2026/2027 (Sonoff od 10.2026)", marker_color="#2ecc71",
                text=sonoff_df["sgi"].apply(lambda x: f"{x:.3f}"), textposition='auto'
            ))
            
        fig_sgi.update_layout(
            barmode='group', 
            xaxis_title="Okres Rozliczeniowy", 
            yaxis_title="SGI [Jednostki U / HDD]",
            template="plotly_white"
        )
        st.plotly_chart(fig_sgi, use_container_width=True)

    with col_g2:
        st.markdown("#### Zużycie Energii Ciepłomierza $SGI_{\\text{GJ}} = \\frac{\\Delta \\text{GJ}}{\\text{HDD}}$")
        fig_gj = go.Figure()
        
        if not base_df.empty and "sgi_gj" in base_df.columns:
            fig_gj.add_trace(go.Bar(
                x=base_df["period_label"], y=base_df["sgi_gj"],
                name="2025/2026 (Bez Sonoff)", marker_color="#7f8c8d",
                text=base_df["sgi_gj"].apply(lambda x: f"{x:.4f}"), textposition='auto'
            ))
            
        if not sonoff_df.empty and "sgi_gj" in sonoff_df.columns:
            fig_gj.add_trace(go.Bar(
                x=sonoff_df["period_label"], y=sonoff_df["sgi_gj"],
                name="2026/2027 (Sonoff od 10.2026)", marker_color="#3498db",
                text=sonoff_df["sgi_gj"].apply(lambda x: f"{x:.4f}"), textposition='auto'
            ))
            
        fig_gj.update_layout(
            barmode='group', 
            xaxis_title="Okres Rozliczeniowy", 
            yaxis_title="SGI [GJ / HDD]",
            template="plotly_white"
        )
        st.plotly_chart(fig_gj, use_container_width=True)

    # Wykres skumulowanego zużycia
    st.markdown("#### Kumulatywne Zużycie Jednostek w Sezonie")
    fig_cum = go.Figure()
    if not base_df.empty:
        base_df_sorted = base_df.sort_values("period_order")
        fig_cum.add_trace(go.Scatter(
            x=base_df_sorted["period_label"], y=base_df_sorted["delta_units"].cumsum(),
            mode='lines+markers', name="Suma 2025/2026 (Bazowy)", line=dict(color="#e74c3c", width=3)
        ))
    if not sonoff_df.empty:
        sonoff_df_sorted = sonoff_df.sort_values("period_order")
        fig_cum.add_trace(go.Scatter(
            x=sonoff_df_sorted["period_label"], y=sonoff_df_sorted["delta_units"].cumsum(),
            mode='lines+markers', name="Suma 2026/2027 (Sonoff)", line=dict(color="#27ae60", width=3)
        ))
    fig_cum.update_layout(xaxis_title="Okres", yaxis_title="Suma ΔU [Jednostki]", template="plotly_white")
    st.plotly_chart(fig_cum, use_container_width=True)

with tab_audit:
    st.subheader(f"🔍 Kontrola Nr Licznika i Spójności: {ROOMS_CONFIG[current_room]['icon']} {current_room}")
    
    if not df_filtered.empty:
        # Pobieranie unikalnych numerów liczników dla tego pokoju
        meters_used = df_filtered["meter_number"].unique()
        st.write(f" Przypisany numer licznika / podzielnika w bazie: **{', '.join([str(m) for m in meters_used])}**")
        
        # Wyliczenie przelicznika U / GJ
        df_filtered["u_per_gj"] = df_filtered.apply(
            lambda r: (r["delta_units"] / r["delta_gj"]) if r["delta_gj"] > 0 else 0.0, axis=1
        )
        
        fig_audit = px.line(
            df_filtered, x="period_label", y="u_per_gj", color="season", markers=True,
            title="Spójność współczynnika oddawania ciepła (Jednostki U / GJ)",
            labels={"u_per_gj": "Stosunek U / GJ", "period_label": "Okres"}
        )
        fig_audit.update_layout(template="plotly_white")
        st.plotly_chart(fig_audit, use_container_width=True)
        
        st.dataframe(df_filtered[[
            "season", "period_label", "meter_number", "units_start", "units_end", 
            "delta_units", "delta_gj", "u_per_gj", "hdd", "sgi"
        ]], use_container_width=True)
    else:
        st.info("Brak wpisów dla wybranego pokoju.")

with tab_sim:
    st.subheader("💰 Prognoza i Realna Oszczędność w PLN")
    if not merged_comp.empty and "expected_gj" in merged_comp.columns:
        merged_comp["expected_cost"] = merged_comp["expected_gj"] * avg_cost_gj
        merged_comp["actual_cost"] = merged_comp["delta_gj_sonoff"] * avg_cost_gj
        merged_comp["pln_saved_period"] = merged_comp["expected_cost"] - merged_comp["actual_cost"]

        fig_cost = go.Figure()
        fig_cost.add_trace(go.Bar(
            x=merged_comp["period_label_sonoff"], y=merged_comp["expected_cost"],
            name="Szacowany koszt bez głowic Sonoff", marker_color="#e67e22"
        ))
        fig_cost.add_trace(go.Bar(
            x=merged_comp["period_label_sonoff"], y=merged_comp["actual_cost"],
            name="Rzeczywisty koszt z Sonoff (2026/2027)", marker_color="#27ae60"
        ))
        fig_cost.update_layout(barmode='group', yaxis_title="Koszt PLN", template="plotly_white")
        st.plotly_chart(fig_cost, use_container_width=True)

        st.dataframe(merged_comp[[
            "period_label_sonoff", "hdd_sonoff", "delta_gj_sonoff", 
            "expected_gj", "gj_saved", "expected_cost", "actual_cost", "pln_saved_period"
        ]].rename(columns={
            "period_label_sonoff": "Okres",
            "hdd_sonoff": "HDD",
            "delta_gj_sonoff": "Rzeczywiste GJ",
            "expected_gj": "Oczekiwane GJ (bez Sonoff)",
            "gj_saved": "Zaoszczędzono GJ",
            "expected_cost": "Koszt Oczekiwany [PLN]",
            "actual_cost": "Koszt Realny [PLN]",
            "pln_saved_period": "Zysk [PLN]"
        }).style.format({
            "HDD": "{:.1f}", "Rzeczywiste GJ": "{:.2f}", "Oczekiwane GJ (bez Sonoff)": "{:.2f}",
            "Zaoszczędzono GJ": "{:+.2f}", "Koszt Oczekiwany [PLN]": "{:.2f} zł",
            "Koszt Realny [PLN]": "{:.2f} zł", "Zysk [PLN]": "{:+.2f} zł"
        }), use_container_width=True)
    else:
        st.warning("Dodaj odczyty z obu sezonów (2025/2026 oraz 2026/2027), aby wygenerować wyliczenia kosztowe.")

with tab_table:
    st.subheader(f"📋 Wszystkie Wpisy dla Pokoju: {current_room}")
    st.dataframe(df_filtered.sort_values(by=["season", "period_order"]), use_container_width=True)

    st.divider()
    st.subheader("🗑️ Usuwanie Wpisu po ID")
    del_id = st.number_input("Podaj ID wpisu do usunięcia:", min_value=1, step=1)
    if st.button("Usuń Wpis"):
        if del_id in df["id"].values:
            df = df[df["id"] != del_id]
            save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
            st.success(f"Wpis o ID {del_id} został usunięty.")
            st.rerun()
        else:
            st.error("Nie znaleziono wpisu o podanym ID.")
