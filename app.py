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
    page_title="Analiza Oszczędności Ogrzewania - Sonoff & GJ",
    page_icon="🔥",
    layout="wide"
)

FILE_PATH = "data/consumption.csv"

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
    """Tworzenie pustej struktury DataFrame z obsługą jednostek U oraz energii w GJ."""
    return pd.DataFrame(columns=[
        "id", "season", "period_code", "period_label", "date_entry",
        "room_name", "units_start", "units_end", "delta_units",
        "gj_start", "gj_end", "delta_gj", "hdd", "sgi", "sgi_gj",
        "cost_per_gj", "notes"
    ])

def load_data():
    """Ładowanie danych z GitHub lub lokalnego pliku fallback."""
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

    # Zapewnienie obecności wszystkich wymaganych kolumn (dla starszych wersji pliku CSV)
    required_cols = create_empty_df().columns
    for col in required_cols:
        if col not in df.columns:
            if col in ["gj_start", "gj_end", "delta_gj", "sgi_gj", "cost_per_gj"]:
                df[col] = 0.0
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
        st.info("Zapisano lokalnie (brak aktywnej konfiguracji GitHub Secrets).")
        return True

# ---------------------------------------------------------
# SŁOWNIKI I STAŁE
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# INTERFEJS UŻYTKOWNIKA & FORMULARZ
# ---------------------------------------------------------
st.title("🔥 Monitor Efektywności Termostatów Sonoff & Licznika GJ")
st.caption("Aplikacja analizuje zużycie energii z podzielników (U) oraz głównego ciepłomierza (GJ) po normalizacji pogodowej HDD.")

df = load_data()

with st.sidebar:
    st.header("📥 Wprowadź Odczyt")
    with st.form("entry_form", clear_on_submit=False):
        season = st.selectbox("Sezon grzewczy", SEASONS)
        period_code = st.selectbox("Okres (2 razy w miesiącu)", list(PERIODS.keys()), format_func=lambda x: PERIODS[x])
        room_name = st.selectbox("Pomieszczenie / Licznik", ROOMS)
        
        st.markdown("---")
        st.subheader("1. Odczyty z Podzielnika (Jednostki U)")
        col_u1, col_u2 = st.columns(2)
        units_start = col_u1.number_input("Jednostki początek", min_value=0.0, value=0.0, step=1.0)
        units_end = col_u2.number_input("Jednostki koniec", min_value=0.0, value=0.0, step=1.0)
        
        manual_delta_u = st.number_input("Lub bezpośrednio różnica jednostek (ΔU)", min_value=0.0, value=0.0, step=1.0,
                                         help="Użyj tego pola, jeśli podajesz wyliczone zużycie bez stanu początkowego/końcowego.")
        
        st.markdown("---")
        st.subheader("2. Odczyt Ciepłomierza Głównego (GJ)")
        col_gj1, col_gj2 = st.columns(2)
        gj_start = col_gj1.number_input("GJ początek", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        gj_end = col_gj2.number_input("GJ koniec", min_value=0.0, value=0.0, step=0.01, format="%.2f")
        
        manual_delta_gj = st.number_input("Lub bezpośrednio zużycie w GJ (ΔGJ)", min_value=0.0, value=0.0, step=0.01, format="%.2f",
                                          help="Podaj pobór energii w gigadżulach z głównego licznika za ten okres.")

        st.markdown("---")
        st.subheader("3. Pogoda i Koszty")
        hdd_input = st.number_input("Liczba Stopniodni (HDD)", min_value=0.1, value=150.0, step=0.1,
                                    help="Suma HDD dla Twojej miejscowości dla ostatnich 2 tygodni.")
        
        cost_per_gj = st.number_input("Cena za 1 GJ (PLN)", min_value=0.0, value=95.0, step=1.0,
                                      help="Koszt 1 GJ wg taryfy dostawcy ciepła.")
        
        date_entry = st.date_input("Data wpisu", date.today())
        notes = st.text_input("Uwagi / Nastawy harmonogramu", value="")
        
        submitted = st.form_submit_button("💾 Zapisz i Przelicz Odczyt")
        
        if submitted:
            # Wyliczenie różnicy dla Podzielników
            if (units_end > units_start) and (manual_delta_u == 0):
                delta_units = units_end - units_start
            else:
                delta_units = manual_delta_u
                
            # Wyliczenie różnicy dla Ciepłomierza GJ
            if (gj_end > gj_start) and (manual_delta_gj == 0):
                delta_gj = gj_end - gj_start
            else:
                delta_gj = manual_delta_gj

            if delta_units <= 0 and delta_gj <= 0:
                st.error("Podaj poprawne wartości zużycia (ΔU > 0 lub ΔGJ > 0)!")
            else:
                sgi_u = round(delta_units / hdd_input, 4) if hdd_input > 0 else 0.0
                sgi_gj = round(delta_gj / hdd_input, 6) if hdd_input > 0 else 0.0
                
                # Usunięcie dubla dla danego okresu, pomieszczenia i sezonu
                if not df.empty and all(col in df.columns for col in ["season", "period_code", "room_name"]):
                    df = df[~((df["season"] == season) & 
                              (df["period_code"] == period_code) & 
                              (df["room_name"] == room_name))]
                
                next_id = int(df["id"].max() + 1) if not df.empty and "id" in df.columns and pd.notna(df["id"].max()) else 1
                
                new_row = pd.DataFrame([{
                    "id": next_id,
                    "season": season,
                    "period_code": period_code,
                    "period_label": PERIODS[period_code],
                    "date_entry": str(date_entry),
                    "room_name": room_name,
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
                if save_data(df, commit_message=f"Dodano odczyt: {season} - {PERIODS[period_code]} ({room_name})"):
                    st.success("Wpis został zapisany i przeliczony!")
                    st.rerun()

# ---------------------------------------------------------
# ANALIZA I WIZUALIZACJE
# ---------------------------------------------------------
if df.empty or len(df) == 0:
    st.info("👋 Baza danych jest obecnie pusta. Wprowadź pierwsze odczyty w panelu bocznym.")
else:
    available_rooms = df["room_name"].unique() if "room_name" in df.columns else ROOMS
    selected_room = st.selectbox("🔍 Wybierz obszar do analizy:", available_rooms)
    
    df_filtered = df[df["room_name"] == selected_room].copy()
    
    # Sortowanie po kolejności okresów
    period_order = list(PERIODS.keys())
    df_filtered["period_order"] = df_filtered["period_code"].map(lambda x: period_order.index(x) if x in period_order else 99)
    df_filtered = df_filtered.sort_values("period_order")

    base_df = df_filtered[df_filtered["season"] == "2024/2025 (Bazowy)"]
    sonoff_df = df_filtered[df_filtered["season"] == "2025/2026 (Sonoff)"]

    # ---------------------------------------------------------
    # KPI METRICS (U oraz GJ)
    # ---------------------------------------------------------
    st.markdown("### 📊 Kluczowe Wskaźniki Efektywności (KPI)")
    col1, col2, col3, col4 = st.columns(4)
    
    avg_sgi_base = base_df["sgi"].mean() if not base_df.empty else 0.0
    avg_sgi_sonoff = sonoff_df["sgi"].mean() if not sonoff_df.empty else 0.0
    
    pct_savings_u = ((avg_sgi_base - avg_sgi_sonoff) / avg_sgi_base * 100) if avg_sgi_base > 0 and avg_sgi_sonoff > 0 else 0.0

    # Łączenie okresów do porównania
    merged_comp = pd.merge(
        sonoff_df, base_df, 
        on="period_code", 
        suffixes=('_sonoff', '_base')
    )
    
    if not merged_comp.empty:
        merged_comp["expected_units"] = merged_comp["sgi_base"] * merged_comp["hdd_sonoff"]
        merged_comp["units_saved"] = merged_comp["expected_units"] - merged_comp["delta_units_sonoff"]
        total_units_saved = merged_comp["units_saved"].sum()
        
        # Wyliczenia dla GJ jeśli dostępne
        if "sgi_gj_base" in merged_comp.columns and "sgi_gj_sonoff" in merged_comp.columns:
            merged_comp["expected_gj"] = merged_comp["sgi_gj_base"] * merged_comp["hdd_sonoff"]
            merged_comp["gj_saved"] = merged_comp["expected_gj"] - merged_comp["delta_gj_sonoff"]
            total_gj_saved = merged_comp["gj_saved"].sum()
        else:
            total_gj_saved = 0.0
    else:
        total_units_saved = 0.0
        total_gj_saved = 0.0

    avg_cost_gj = df["cost_per_gj"].replace(0, pd.NA).dropna().mean()
    if pd.isna(avg_cost_gj) or avg_cost_gj == 0:
        avg_cost_gj = 95.0
    
    pln_saved = total_gj_saved * avg_cost_gj

    col1.metric(
        "Średnie SGI (Bazowe vs Sonoff)", 
        f"{avg_sgi_sonoff:.3f} U/HDD",
        delta=f"{pct_savings_u:+.1f}% oszczędności" if pct_savings_u != 0 else None,
        delta_color="normal" if pct_savings_u >= 0 else "inverse"
    )
    col2.metric(
        "Zaoszczędzona Energia (GJ)", 
        f"{total_gj_saved:+.2f} GJ",
        help="Suma zaoszczędzonego ciepła w gigadżulach skorygowana o stopniodnie HDD."
    )
    col3.metric(
        "Szacowana Oszczędność (PLN)", 
        f"{pln_saved:+.2f} PLN",
        help=f"Oszczędność w PLN przeliczona według średniej ceny {avg_cost_gj:.2f} PLN / 1 GJ."
    )
    col4.metric(
        "Zaoszczędzone Jednostki U", 
        f"{total_units_saved:+.1f} U"
    )

    st.divider()

    # ---------------------------------------------------------
    # TABY Z WYKRESAMI I AUDYTEM GJ
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Efektywność SGI (U & GJ)", 
        "🔍 Audyt & Weryfikacja Stanu GJ", 
        "🛡️ Rzeczywiste vs Oczekiwane", 
        "🌡️ Regresja: Zużycie vs HDD", 
        "📋 Tabela i ZARZĄDZANIE"
    ])

    with tab1:
        st.subheader("Wskaźniki Efektywności SGI (Normalizacja Weather-HDD)")
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.markdown("#### SGI Podzielników [Jednostki / HDD]")
            fig_sgi = go.Figure()
            if not base_df.empty:
                fig_sgi.add_trace(go.Bar(
                    x=base_df["period_label"], y=base_df["sgi"],
                    name="2024/2025 (Bazowy)", marker_color="#95a5a6",
                    text=base_df["sgi"].apply(lambda x: f"{x:.3f}"), textposition='auto'
                ))
            if not sonoff_df.empty:
                fig_sgi.add_trace(go.Bar(
                    x=sonoff_df["period_label"], y=sonoff_df["sgi"],
                    name="2025/2026 (Sonoff)", marker_color="#2ecc71" if pct_savings_u >= 0 else "#e74c3c",
                    text=sonoff_df["sgi"].apply(lambda x: f"{x:.3f}"), textposition='auto'
                ))
            fig_sgi.update_layout(barmode='group', xaxis_title="Okres", yaxis_title="SGI [U / HDD]", template="plotly_white")
            st.plotly_chart(fig_sgi, use_container_width=True)

        with col_c2:
            st.markdown("#### SGI Ciepłomierza [GJ / HDD]")
            fig_sgi_gj = go.Figure()
            if not base_df.empty and "sgi_gj" in base_df.columns:
                fig_sgi_gj.add_trace(go.Bar(
                    x=base_df["period_label"], y=base_df["sgi_gj"],
                    name="2024/2025 (Bazowy)", marker_color="#7f8c8d",
                    text=base_df["sgi_gj"].apply(lambda x: f"{x:.4f}"), textposition='auto'
                ))
            if not sonoff_df.empty and "sgi_gj" in sonoff_df.columns:
                fig_sgi_gj.add_trace(go.Bar(
                    x=sonoff_df["period_label"], y=sonoff_df["sgi_gj"],
                    name="2025/2026 (Sonoff)", marker_color="#3498db",
                    text=sonoff_df["sgi_gj"].apply(lambda x: f"{x:.4f}"), textposition='auto'
                ))
            fig_sgi_gj.update_layout(barmode='group', xaxis_title="Okres", yaxis_title="SGI [GJ / HDD]", template="plotly_white")
            st.plotly_chart(fig_sgi_gj, use_container_width=True)

    with tab2:
        st.subheader("🔎 Moduł Weryfikacji Odczytów GJ i Spójności Danych")
        st.caption("Ponowna analiza ciągłości stanów licznika GJ oraz przelicznika Jednostek (U) na 1 GJ ciepła.")
        
        # Wyliczenie przelicznika U / GJ
        df_audit = df_filtered.copy()
        df_audit["u_per_gj"] = df_audit.apply(
            lambda r: (r["delta_units"] / r["delta_gj"]) if r["delta_gj"] > 0 else 0.0, axis=1
        )
        
        col_aud1, col_aud2 = st.columns([2, 1])
        
        with col_aud1:
            st.markdown("#### Przelicznik: Ile Jednostek U przypada na 1 GJ Ciepła?")
            fig_ratio = px.line(
                df_audit, x="period_label", y="u_per_gj", color="season", markers=True,
                title="Stałość współczynnika oddawania ciepła (U / GJ)",
                labels={"u_per_gj": "Stosunek U / GJ", "period_label": "Okres"}
            )
            fig_ratio.update_layout(template="plotly_white")
            st.plotly_chart(fig_ratio, use_container_width=True)
            
        with col_aud2:
            st.markdown("#### Weryfikacja Anomalii")
            anomalies = []
            
            # Sprawdzanie nieciągłości stanów GJ
            for season_name in SEASONS:
                sdf = df_audit[df_audit["season"] == season_name].sort_values("period_order")
                if len(sdf) > 1:
                    for i in range(len(sdf) - 1):
                        row_curr = sdf.iloc[i]
                        row_next = sdf.iloc[i+1]
                        if row_curr["gj_end"] > 0 and row_next["gj_start"] > 0:
                            if abs(row_curr["gj_end"] - row_next["gj_start"]) > 0.01:
                                anomalies.append(
                                    f"⚠️ Nieciągłość GJ w {season_name}: {row_curr['period_code']} koniec ({row_curr['gj_end']:.2f}) != {row_next['period_code']} początek ({row_next['gj_start']:.2f})"
                                )
            
            # Sprawdzanie wpisów z brakiem GJ lub brakiem U
            zero_gj = df_audit[(df_audit["delta_units"] > 0) & (df_audit["delta_gj"] == 0)]
            if not zero_gj.empty:
                for _, r in zero_gj.iterrows():
                    anomalies.append(f"ℹ️ {r['season']} ({r['period_code']}): Podano jednostki ΔU={r['delta_units']:.0f}, ale brak odczytu GJ.")
            
            if anomalies:
                for an in anomalies:
                    st.warning(an)
            else:
                st.success("✅ Brak krytycznych niezgodności. Odczyty GJ są ciągłe i spójne!")
                
        st.markdown("#### Tabela Audytowa Odczytów Licznika GJ")
        audit_display = df_audit[[
            "season", "period_label", "gj_start", "gj_end", "delta_gj", 
            "delta_units", "u_per_gj", "hdd", "sgi_gj"
        ]].copy()
        audit_display.columns = [
            "Sezon", "Okres", "GJ Start", "GJ Koniec", "ΔGJ", 
            "ΔJednostki (U)", "Przelicznik (U/GJ)", "HDD", "SGI (GJ/HDD)"
        ]
        st.dataframe(audit_display.style.format({
            "GJ Start": "{:.2f}", "GJ Koniec": "{:.2f}", "ΔGJ": "{:.2f}",
            "ΔJednostki (U)": "{:.1f}", "Przelicznik (U/GJ)": "{:.2f}",
            "HDD": "{:.1f}", "SGI (GJ/HDD)": "{:.5f}"
        }), use_container_width=True)

    with tab3:
        st.subheader("Ile energii i PLN zużyłbyś bez termostatów Sonoff?")
        st.caption("Symulacja zużycia GJ oraz koszcie w PLN na podstawie bazowego wskaźnika SGI przy obecnych stopniodniach HDD.")
        
        if not merged_comp.empty and "expected_gj" in merged_comp.columns:
            merged_comp["expected_cost_pln"] = merged_comp["expected_gj"] * avg_cost_gj
            merged_comp["actual_cost_pln"] = merged_comp["delta_gj_sonoff"] * avg_cost_gj
            
            fig_exp = go.Figure()
            fig_exp.add_trace(go.Bar(
                x=merged_comp["period_label_sonoff"], y=merged_comp["expected_cost_pln"],
                name="Gdyby NIE było Sonoff (Koszt Oczekiwany)", marker_color="#e67e22"
            ))
            fig_exp.add_trace(go.Bar(
                x=merged_comp["period_label_sonoff"], y=merged_comp["actual_cost_pln"],
                name="Rzeczywisty Koszt (Sonoff)", marker_color="#27ae60"
            ))
            fig_exp.update_layout(
                barmode='group', xaxis_title="Okres", yaxis_title="Koszt Ogrzewania [PLN]", template="plotly_white"
            )
            st.plotly_chart(fig_exp, use_container_width=True)
            
            st.markdown("#### Wyliczenie Oszczędności w GJ i PLN per Okres")
            disp_savings = merged_comp[[
                "period_label_sonoff", "hdd_sonoff", "delta_gj_sonoff", 
                "expected_gj", "gj_saved", "expected_cost_pln", "actual_cost_pln"
            ]].copy()
            disp_savings["pln_saved"] = disp_savings["expected_cost_pln"] - disp_savings["actual_cost_pln"]
            disp_savings.columns = [
                "Okres", "HDD", "Zużycie Sonoff [GJ]", 
                "Zużycie Oczekiwane [GJ]", "Zaoszczędzono [GJ]",
                "Koszt Oczekiwany [PLN]", "Koszt Sonoff [PLN]", "Zaoszczędzono [PLN]"
            ]
            st.dataframe(disp_savings.style.format({
                "HDD": "{:.1f}", "Zużycie Sonoff [GJ]": "{:.2f}",
                "Zużycie Oczekiwane [GJ]": "{:.2f}", "Zaoszczędzono [GJ]": "{:+.2f}",
                "Koszt Oczekiwany [PLN]": "{:.2f} zł", "Koszt Sonoff [PLN]": "{:.2f} zł",
                "Zaoszczędzono [PLN]": "{:+.2f} zł"
            }), use_container_width=True)
        else:
            st.warning("Brak wystarczających danych do przeprowadzenia porównania okresów.")

    with tab4:
        st.subheader("Wpływ Pogody (HDD) na Zużycie GJ i Jednostek")
        col_reg1, col_reg2 = st.columns(2)
        
        with col_reg1:
            fig_scat_u = px.scatter(
                df_filtered, x="hdd", y="delta_units", color="season", text="period_code", trendline="ols",
                labels={"hdd": "HDD (Suma Stopniodni)", "delta_units": "Jednostki U (ΔU)"},
                title="Regresja: Jednostki U vs HDD"
            )
            fig_scat_u.update_traces(marker=dict(size=10))
            st.plotly_chart(fig_scat_u, use_container_width=True)

        with col_reg2:
            fig_scat_gj = px.scatter(
                df_filtered[df_filtered["delta_gj"] > 0], x="hdd", y="delta_gj", color="season", text="period_code", trendline="ols",
                labels={"hdd": "HDD (Suma Stopniodni)", "delta_gj": "Energia w GJ (ΔGJ)"},
                title="Regresja: Zużycie Ciepła w GJ vs HDD"
            )
            fig_scat_gj.update_traces(marker=dict(size=10))
            st.plotly_chart(fig_scat_gj, use_container_width=True)

    with tab5:
        st.subheader("Wszystkie Wpisy w Bazie Danych")
        st.dataframe(df_filtered.sort_values(by=["season", "period_order"]), use_container_width=True)
        
        st.divider()
        st.subheader("🗑️ Usuwanie Wpisu")
        del_id = st.number_input("Podaj ID wpisu do usunięcia:", min_value=1, step=1)
        if st.button("Usuń wpis z bazy"):
            if del_id in df["id"].values:
                df = df[df["id"] != del_id]
                save_data(df, commit_message=f"Usunięto wpis ID {del_id}")
                st.success(f"Wpis ID {del_id} został usunięty.")
                st.rerun()
            else:
                st.error("Nie znaleziono wpisu o podanym ID.")
