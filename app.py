import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, date
import io
import json
import base64

# ReportLab dla generatora PDF
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Konfiguracja strony
st.set_page_config(
    page_title="Panel Rozliczeń Ciepła - Siemianowice Śląskie",
    page_icon="🌡️",
    layout="wide"
)

# Stylizacja CSS (Glassmorphism / iOS 18 style)
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Konfiguracja stałych
CITY = "Siemianowice Slaskie"
DEFAULT_TEMP = 12.5
COST_PER_UNIT = 2.45  # PLN za jednostkę (U)
MONTHLY_ADVANCE = 350.0  # Miesięczna zaliczka na c.o. (PLN)

# Pobieranie kluczy z st.secrets z obsługą bezpieczeństwa
OWM_API_KEY = st.secrets.get("openweathermap", {}).get("api_key", "")
GITHUB_TOKEN = st.secrets.get("github", {}).get("token", "")
GITHUB_REPO = st.secrets.get("github", {}).get("repo", "")
GITHUB_PATH = st.secrets.get("github", {}).get("path", "odczyty_ciepla.csv")

@st.cache_data(ttl=1800)
def get_outdoor_temp():
    if not OWM_API_KEY:
        return DEFAULT_TEMP
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={CITY},PL&units=metric&appid={OWM_API_KEY}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data["main"]["temp"]
    except Exception:
        pass
    return DEFAULT_TEMP

def load_data():
    try:
        if GITHUB_TOKEN and GITHUB_REPO:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                content = res.json()["content"]
                decoded = base64.b64decode(content).decode("utf-8")
                return pd.read_csv(io.StringIO(decoded))
    except Exception:
        pass
    
    # Fallback lokalny
    try:
        return pd.read_csv("odczyty_ciepla.csv")
    except FileNotFoundError:
        return create_initial_df()

def create_initial_df():
    data = {
        "data": ["2026-01-06", "2026-01-13", "2026-01-20", "2026-01-27"],
        "odczyt_calkowity": [1200, 1245, 1290, 1330],
        "zuzycie_tygodniowe": [45, 45, 45, 40],
        "temp_zewnetrzna": [-2.0, 0.5, 3.0, 1.2],
        "koszt_pln": [110.25, 110.25, 110.25, 98.00],
        "mode_tag": ["Automatyczny", "Automatyczny", "Automatyczny", "Automatyczny"]
    }
    return pd.DataFrame(data)

def save_data(df):
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_str = csv_buffer.getvalue()
    
    # Zapis lokalny
    with open("odczyty_ciepla.csv", "w", encoding="utf-8") as f:
        f.write(csv_str)
        
    # Zapis do GitHub jeśli skonfigurowany
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
            
            # Pobierz SHA istniejącego pliku
            get_res = requests.get(url, headers=headers)
            sha = get_res.json().get("sha") if get_res.status_code == 200 else None
            
            payload = {
                "message": "Automatyczna aktualizacja odczytów ciepła",
                "content": base64.b64encode(csv_str.encode("utf-8")).decode("utf-8")
            }
            if sha:
                payload["sha"] = sha
                
            requests.put(url, headers=headers, json=payload, timeout=10)
        except Exception:
            pass
            
    st.cache_data.clear()

# Generowanie raportu PDF
def generate_pdf(df, projection_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor("#1e293b"))
    subtitle_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#64748b"))
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#334155"))
    
    story.append(Paragraph("RAPORT ROZLICZENIA ZUŻYCIA CIEPŁA", title_style))
    story.append(Paragraph(f"Lokalizacja: Siemianowice Śląskie | Data generowania: {date.today().strftime('%Y-%m-%d')}", subtitle_style))
    story.append(Spacer(1, 15))
    
    # Sekcja podsumowania predykcyjnego
    story.append(Paragraph("<b>Prognoza Finansowa do Końca Okresu Rozliczeniowego:</b>", normal_style))
    story.append(Paragraph(f"• Szacowany koszt całkowity: <b>{projection_data['total_cost']:.2f} PLN</b>", normal_style))
    story.append(Paragraph(f"• Suma wniesionych zaliczek: <b>{projection_data['total_advances']:.2f} PLN</b>", normal_style))
    story.append(Paragraph(f"• Prognozowany wynik: <b>{projection_data['balance_type']} w wysokości {abs(projection_data['balance_amount']):.2f} PLN</b>", normal_style))
    story.append(Spacer(1, 15))
    
    # Tabela historyczna
    story.append(Paragraph("<b>Szczegółowa Historia Odczytów:</b>", normal_style))
    story.append(Spacer(1, 5))
    
    table_data = [["Data", "Stan Licznika", "Zużycie (U)", "Temp. Zewn. (°C)", "Koszt (PLN)"]]
    for _, row in df.iterrows():
        table_data.append([
            str(row['data']),
            str(row['odczyt_calkowity']),
            str(row['zuzycie_tygodniowe']),
            str(row['temp_zewnetrzna']),
            f"{row['koszt_pln']:.2f}"
        ])
        
    t = Table(table_data, colWidths=[80, 90, 80, 90, 90])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 25))
    story.append(Paragraph("Niniejszy dokument został wygenerowany automatycznie w celach informacyjnych oraz weryfikacji wskazań rozliczeniowych dla Spółdzielni Mieszkaniowej.", subtitle_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# Główna aplikacja
def main():
    df = load_data()
    current_temp = get_outdoor_temp()
    today = date.today()
    
    st.title("Panel Monitorowania i Predykcji Ciepła")
    st.markdown(f"**Lokalizator:** Siemianowice Śląskie | **Aktualna temperatura zewn.:** {current_temp}°C")
    
    # Sprawdzenie okna wtorkowego
    is_tuesday = (today.weekday() == 1)
    df['data_dt'] = pd.to_datetime(df['data'])
    latest_date = df['data_dt'].max().date() if not df.empty else None
    needs_tuesday_sync = is_tuesday and (latest_date != today)
    
    if needs_tuesday_sync:
        st.warning("Dzisiaj jest wtorek! Wymagana synchronizacja i wpis odczytów podzielników.")
        with st.form("tuesday_form"):
            st.subheader("Wtorkowy wpis odczytów")
            new_reading = st.number_input("Aktualny stan liczników/podzielników", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Zapisz odczyt")
            if submitted:
                last_val = df['odczyt_calkowity'].iloc[-1] if not df.empty else new_reading
                consumption = max(0.0, new_reading - last_val)
                cost = consumption * COST_PER_UNIT
                
                new_row = pd.DataFrame([{
                    "data": today.strftime("%Y-%m-%d"),
                    "odczyt_calkowity": new_reading,
                    "zuzycie_tygodniowe": consumption,
                    "temp_zewnetrzna": current_temp,
                    "koszt_pln": cost,
                    "mode_tag": "Wtorkowy Automatyczny"
                }])
                df = pd.concat([df, new_row], ignore_index=True)
                save_data(df)
                st.success("Zapisano pomyślnie!")
                st.rerun()

    # Panel boczny - Szybki wpis / Narzędzia
    st.sidebar.header("Zarządzanie danymi")
    with st.sidebar.form("manual_add"):
        st.subheader("Dodaj ręczny wpis")
        m_date = st.date_input("Data", value=today)
        m_reading = st.number_input("Stan całkowity", min_value=0.0, value=float(df['odczyt_calkowity'].iloc[-1]) if not df.empty else 0.0)
        m_temp = st.number_input("Temp. zewnętrzna (°C)", value=float(current_temp))
        m_submit = st.form_submit_button("Dodaj wpis")
        if m_submit:
            last_val = df['odczyt_calkowity'].iloc[-1] if not df.empty else m_reading
            consumption = max(0.0, m_reading - last_val)
            cost = consumption * COST_PER_UNIT
            new_row = pd.DataFrame([{
                "data": m_date.strftime("%Y-%m-%d"),
                "odczyt_calkowity": m_reading,
                "zuzycie_tygodniowe": consumption,
                "temp_zewnetrzna": m_temp,
                "koszt_pln": cost,
                "mode_tag": "Ręczny"
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.sidebar.successję("Dodano wpis!")
            st.rerun()

    # Algorytm predykcyjny kosztów
    total_spent = df['koszt_pln'].sum() if not df.empty else 0.0
    months_elapsed = max(1, len(df) / 4.33)  # przybliżenie tygodni na miesiące
    avg_monthly_cost = total_spent / months_elapsed
    
    # Szacunek do końca sezonu (np. przyjęcie 6 miesięcy grzewczych łącznie)
    total_projected_cost = avg_monthly_cost * 6
    total_advances_paid = MONTHLY_ADVANCE * 6
    balance = total_advances_paid - total_projected_cost
    
    projection_data = {
        "total_cost": total_projected_cost,
        "total_advances": total_advances_paid,
        "balance_amount": balance,
        "balance_type": "Nadpłata" if balance >= 0 else "Niedopłata"
    }

    # Metryki główne
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Suma kosztów (historia)", f"{total_spent:.2f} PLN")
    with col2:
        st.metric("Opłacone zaliczki", f"{total_advances_paid:.2f} PLN")
    with col3:
        st.metric("Prognoza końcowa kosztów", f"{total_projected_cost:.2f} PLN")
    with col4:
        st.metric(projection_data['balance_type'], f"{abs(balance):.2f} PLN", 
                  delta=f"{'Nadpłata' if balance >= 0 else 'Niedopłata'}")

    st.markdown("---")
    
    # Wykresy analityczne Plotly
    tab1, tab2 = st.tabs(["Wykresy Zużycia", "Generator Raportów PDF"])
    
    with tab1:
        st.subheader("Dynamika zużycia jednostek i temperatury")
        fig = px.line(df, x="data", y=["zuzycie_tygodniowe", "temp_zewnetrzna"], markers=True,
                      labels={"value": "Wartość", "data": "Data odczytu"},
                      title="Tygodniowe zużycie energii vs Temperatura zewnętrzna")
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.subheader("Generowanie oficjalnego raportu do Spółdzielni Mieszkaniowej")
        st.markdown("Pobierz kompletny raport PDF zawierający szczegółową historię odczytów, wykresy oraz podsumowanie bilansu finansowego lokalu.")
        
        pdf_bytes = generate_pdf(df, projection_data)
        st.download_button(
            label="Pobierz Raport PDF",
            data=pdf_bytes,
            file_name=f"raport_ciepla_siemianowice_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )

if __name__ == "__main__":
    main()
