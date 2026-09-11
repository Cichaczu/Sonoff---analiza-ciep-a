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
    page_title="Analiza Oszczędności Ogrzewania - Sonoff",
    page_icon="🔥",
    layout="wide"
)

FILE_PATH = "data/consumption.csv"

# ---------------------------------------------------------
# OBSŁUGA GITHUB / OBSŁUGA PLIKÓW
# ---------------------------------------------------------
def get_github_repo():
    token = st.secrets.get("github", {}).get("token")
    repo_name = st.secrets.get("github", {}).get("repo")
    if token and repo_name:
        g = Github(token)
        return g.get_repo(repo_name)
    return None

def create_empty_df():
    return pd.DataFrame(columns=[
        "id", "season", "period_code", "period_label", "date_entry",
        "room_name", "units_start", "units_end", "delta_units",
        "hdd", "sgi", "notes"
    ])

def load_data():
    repo = get_github_repo()
    branch = st.secrets.get("github", {}).get("branch", "main")
    
    if repo:
        try:
            file_content = repo.get_contents(FILE_PATH, ref=branch)
            csv_raw = file_content.decoded_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_raw))
            return df
        except GithubException as e:
            if e.status == 404:
                df = create_empty_df()
                save_data(df, commit_message="Inicjalizacja pliku baza danych")
                return df
            else:
                st.error(f"Błąd pobierania danych z GitHub: {e}")
                return create_empty_df()
    else:
        # Tryb lokalny (fallback)
        if os.path.exists(FILE_PATH):
            return pd.read_csv(FILE_PATH)
        else:
            df = create_empty_df()
            os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
            df.to_csv(FILE_PATH, index=False)
            return df

def save_data(df, commit_message="Aktualizacja danych zużycia"):
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
            st.error(f"Nie udało się zapisać danych do GitHub: {e}")
            return False
    else:
        os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
        df.to_csv(FILE_PATH, index=False)
        st.warning("Zapisano lokalnie (brak skonfigurowanego tokena GitHub Secrets).")
        return True

# ---------------------------------------------------------
# INTERFEJS UŻYTKOWNIKA & FORMULARZ
# ---------------------------------------------------------
st.title("🔥 Monitor Efektywności Termostatów Sonoff")
st.caption("Aplikacja porównuje zużycie energii z podzielników po normalizacji pogodowej wskaźnikiem HDD (Heating Degree Days).")

df = load_data()

# Słownik okresów dwutygodniowych
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

SEASONS = ["2024/2025 (Bazowy)", "2025/2026 (Sonoff)"]
ROOMS = ["Suma Całkowita", "Salon", "Sypialnia", "Kuchnia", "Pokój Dziecka"]

with st.sidebar:
    st.header("📥 Wprowadź Odczyt")
    with st.form("entry_form", clear_on_submit=False):
        season = st.selectbox("Sezon grzewczy", SEASONS)
        period_code = st.selectbox("Okres (2 razy w miesiącu)", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
        room_name = st.selectbox("Pomieszczenie / Licznik", ROOMS)
        
        st.subheader("Odczyty z Podzielnika")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Stan początkowy", min_value=0.0, value=0.0, step=1.0)
        units_end = col_u2.number_input("Stan końcowy", min_value=0.0, value=0.0, step=1.0)
        
        manual_delta = st.number_input("Lub wpisz bezpośrednio zużycie (ΔU)", min_value=0.0, value=0.0, step=1.0,
                                       help="Wpisz tutaj, jeśli podajesz wyliczoną różnicę bez podawania stanu początkowego i końcowego.")
        
        hdd_input = st.number_input("Liczba Stopniodni (HDD)", min_value=0.1, value=150.0, step=0.1,
                                    help="Suma HDD dla danej lokalizacji z ostatnich 2 tygodni.")
        
        date_entry = st.date_input("Data wpisu", date.today())
        notes = st.text_input("Uwagi / Nastawy Sonoff", value="")
        
        submitted = st.form_submit_button("💾 Zapisz do Bazy GitHub")
        
        if submitted:
            # Obliczenie zużycia
            if (units_end > units_start) and (manual_delta == 0):
                delta_units = units_end - units_start
            else:
                delta_units = manual_delta
                
            if delta_units <= 0:
                st.error("Różnica jednostek (ΔU) musi być większa od 0!")
            else:
                sgi = round(delta_units / hdd_input, 4)
                
                # Usuń istniejący wpis dla tego samego okresu, pomieszczenia i sezonu (nadpisywanie)
                df = df[~((df["season"] == season) & 
                          (df["period_code"] == period_code) & 
                          (df["room_name"] == room_name))]
                
                new_row = pd.DataFrame([{
                    "id": len(df) + 1,
                    "season": season,
                    "period_code": period_code,
                    "period_label": PERIODS[period_code],
                    "date_entry": str(date_entry),
                    "room_name": room_name,
                    "units_start": units_start,
                    "units_end": units_end,
                    "delta_units": delta_units,
                    "hdd": hdd_input,
                    "sgi": sgi,
                    "notes": notes
                }])
                
                df = pd.concat([df, new_row], ignore_index=True)
                if save_data(df, commit_message=f"Dodano odczyt: {season} - {PERIODS[period_code]} ({room_name})"):
                    st.success("Wpis został pomyślnie zapisany w GitHub!")
                    st.rerun()

# ---------------------------------------------------------
# ANALIZA I WIZUALIZACJE
# ---------------------------------------------------------
if df.empty:
    st.info("👋 Baza danych jest obecnie pusta. Wprowadź odczyty w panelu bocznym lub wgraj plik z danymi z zeszłego sezonu.")
else:
    selected_room = st.selectbox("🔍 Wybierz obszar do analizy:", df["room_name"].unique())
    df_filtered = df[df["room_name"] == selected_room].copy()
    
    # Sortowanie po okresie
    period_order = list(PERIODS.keys())
    df_filtered["period_order"] = df_filtered["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)
    df_filtered = df_filtered.sort_values("period_order")

    base_df = df_filtered[df_filtered["season"] == "2024/2025 (Bazowy)"]
    sonoff_df = df_filtered[df_filtered["season"] == "2025/2026 (Sonoff)"]

    # --- KPI METRICS ---
    st.markdown("### 📊 Kluczowe Wskaźniki Efektywności (KPI)")
    col1, col2, col3, col4 = st.columns(4)
    
    avg_sgi_base = base_df["sgi"].mean() if not base_df.empty else 0
    avg_sgi_sonoff = sonoff_df["sgi"].mean() if not sonoff_df.empty else 0
    
    if avg_sgi_base > 0 and avg_sgi_sonoff > 0:
        pct_savings = (1 - (avg_sgi_sonoff / avg_sgi_base)) * 100
    else:
        pct_savings = 0.0

    # Obliczenie oszczędności w jednostkach (Oczekiwane vs Rzeczywiste)
    merged_comp = pd.merge(
        sonoff_df, base_df, 
        on="period_code", 
        suffixes=('_sonoff', '_base')
    )
    
    if not merged_comp.empty:
        # Oczekiwane zużycie = SGI zeszłoroczne * obecne HDD
        merged_comp["expected_units"] = merged_comp["sgi_base"] * merged_comp["hdd_sonoff"]
        merged_comp["units_saved"] = merged_comp["expected_units"] - merged_comp["delta_units_sonoff"]
        total_units_saved = merged_comp["units_saved"].sum()
    else:
        total_units_saved = 0.0

    col1.metric(
        "Średnie SGI (Bazowe 24/25)", 
        f"{avg_sgi_base:.4f} u/HDD" if avg_sgi_base else "Brak danych"
    )
    col2.metric(
        "Średnie SGI (Sonoff 25/26)", 
        f"{avg_sgi_sonoff:.4f} u/HDD" if avg_sgi_sonoff else "Brak danych",
        delta=f"{-pct_savings:.1f}% (Efektywność)" if pct_savings != 0 else None,
        delta_color="normal" if pct_savings >= 0 else "inverse"
    )
    col3.metric(
        "Realne Zaoszczędzone Jednostki", 
        f"{total_units_saved:+.1f} u",
        help="Liczba jednostek z podzielnika, które zaoszczędzono względem pogody z br."
    )
    col4.metric(
        "Liczba Porównywanych Okresów", 
        f"{len(merged_comp)} z {len(sonoff_df)}"
    )

    st.divider()

    # --- TABY Z WYKRESAMI ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Porównanie SGI (Efektywność)", 
        "🛡️ Zużycie Rzeczywiste vs Oczekiwane", 
        "🌡️ Zużycie Surowe vs HDD", 
        "📋 Tabela i Zarządzanie Danyi"
    ])

    with tab1:
        st.subheader("Wskaźnik Jednostkowy SGI (Zużycie ÷ HDD)")
        st.caption("SGI eliminuje wpływ pogody. Mniejsza wartość oznacza, że termostaty Sonoff zużywają mniej energii przy tej samej temperaturze zewnętrznej.")
        
        fig_sgi = go.Figure()
        
        if not base_df.empty:
            fig_sgi.add_trace(go.Bar(
                x=base_df["period_label"], 
                y=base_df["sgi"],
                name="2024/2025 (Bazowy)",
                marker_color="#95a5a6",
                text=base_df["sgi"].apply(lambda x: f"{x:.3f}"),
                textposition='auto'
            ))
            
        if not sonoff_df.empty:
            fig_sgi.add_trace(go.Bar(
                x=sonoff_df["period_label"], 
                y=sonoff_df["sgi"],
                name="2025/2026 (Sonoff)",
                marker_color="#2ecc71" if pct_savings >= 0 else "#e74c3c",
                text=sonoff_df["sgi"].apply(lambda x: f"{x:.3f}"),
                textposition='auto'
            ))
            
        fig_sgi.update_layout(
            barmode='group',
            xaxis_title="Okres Rozliczeniowy",
            yaxis_title="SGI [Jednostki / HDD]",
            hovermode="x unified",
            template="plotly_white"
        )
        st.plotly_chart(fig_sgi, use_container_width=True)

    with tab2:
        st.subheader("Ile jednostek zużyłbyś bez termostatów Sonoff?")
        st.caption("Wykres symuluje zużycie przy obecnej pogodzie (HDD), gdyby ogrzewanie działało ze starą efektywnością.")
        
        if not merged_comp.empty:
            fig_exp = go.Figure()
            
            fig_exp.add_trace(go.Bar(
                x=merged_comp["period_label_sonoff"],
                y=merged_comp["expected_units"],
                name="Gdyby NIE było Sonoff (Oczekiwane)",
                marker_color="#e67e22"
            ))
            
            fig_exp.add_trace(go.Bar(
                x=merged_comp["period_label_sonoff"],
                y=merged_comp["delta_units_sonoff"],
                name="Rzeczywiste Zużycie (Sonoff)",
                marker_color="#27ae60"
            ))
            
            fig_exp.update_layout(
                barmode='group',
                xaxis_title="Okres Rozliczeniowy",
                yaxis_title="Jednostki z Podzielnika [U]",
                template="plotly_white"
            )
            st.plotly_chart(fig_exp, use_container_width=True)
            
            # Podsumowanie oszczędności w tabeli
            st.markdown("#### Wyliczenie Oszczędności per Okres")
            disp_savings = merged_comp[[
                "period_label_sonoff", "hdd_sonoff", "delta_units_sonoff", 
                "expected_units", "units_saved"
            ]].copy()
            disp_savings.columns = [
                "Okres", "HDD (Pogoda)", "Zużycie Sonoff [U]", 
                "Zużycie Oczekiwane [U]", "Zaoszczędzono [U]"
            ]
            disp_savings["Oszczędność %"] = (disp_savings["Zaoszczędzono [U]"] / disp_savings["Zużycie Oczekiwane [U]"]) * 100
            st.dataframe(disp_savings.style.format({
                "HDD (Pogoda)": "{:.1f}",
                "Zużycie Sonoff [U]": "{:.1f}",
                "Zużycie Oczekiwane [U]": "{:.1f}",
                "Zaoszczędzono [U]": "{:+.1f}",
                "Oszczędność %": "{:+.1f}%"
            }), use_container_width=True)
        else:
            st.warning("Brak pokrywających się okresów między sezonem bazowym a obecnym.")

    with tab3:
        st.subheader("Wpływ Dotkliwości Zimy (HDD) na Zużycie Jednostek")
        fig_scatter = px.scatter(
            df_filtered, 
            x="hdd", 
            y="delta_units", 
            color="season",
            text="period_code",
            trendline="ols",
            labels={"hdd": "HDD (Suma Stopniodni)", "delta_units": "Zużyte Jednostki (ΔU)"},
            title="Prosta Regresji: Im bardziej płaska prosta Sonoff, tym wyższa izolacja/oszczędność"
        )
        fig_scatter.update_traces(marker=dict(size=12))
        st.plotly_chart(fig_scatter, use_container_width=True)

    with tab4:
        st.subheader("Pełna Baza Danych (Bieżące Odczyty)")
        st.dataframe(df_filtered.sort_values(by=["season", "period_order"]), use_container_width=True)
        
        st.divider()
        st.subheader("🗑️ Usuwanie Wpisu")
        del_id = st.number_input("Podaj ID wpisu do usunięcia:", min_value=1, step=1)
        if st.button("Usuń wpis z bazy GitHub"):
            if del_id in df["id"].values:
                df = df[df["id"] != del_id]
                save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
                st.success(f"Wpis o ID {del_id} został usunięty.")
                st.rerun()
            else:
                st.error("Nie znaleziono wpisu o podanym ID.")
