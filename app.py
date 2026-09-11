from datetime import date, datetime, timedelta
import io
import os
import time
import urllib.parse
from github import Github, GithubException
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as px_go
import requests
from sklearn.linear_model import LinearRegression
import streamlit as st

# ---------------------------------------------------------
# KONFIGURACJA STRONY I LOKALIZACJI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Sonoff Heating - iOS 18 Dynamic Analytics",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

FILE_PATH = "data/consumption.csv"
EST_PLN_PER_UNIT = 2.45

SSM_CO_MONTHLY_ADVANCE = 774.53
SSM_SEASON_MONTHS = 7
SSM_ANNUAL_CO_BUDGET = SSM_CO_MONTHLY_ADVANCE * SSM_SEASON_MONTHS

LAT_LOCATION = 50.3264
LON_LOCATION = 19.0295
LOCATION_NAME = "Siemianowice Śl. - Bytków (ZHP)"


def get_outdoor_temp():
  api_key = st.secrets.get("openweathermap", {}).get("api_key", None)
  if not api_key:
    return 12.5
  try:
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT_LOCATION}&lon={LON_LOCATION}&appid={api_key}&units=metric"
    res = requests.get(url, timeout=3)
    if res.status_code == 200:
      return float(res.json()["main"]["temp"])
  except Exception:
    pass
  return 12.5


def send_webhook_notification(message):
  webhook_cfg = st.secrets.get("webhook", {})
  service = webhook_cfg.get("service", "").lower()
  url = webhook_cfg.get("url", "")
  if not url and service != "telegram":
    return
  try:
    if service == "telegram":
      token = webhook_cfg.get("token")
      chat_id = webhook_cfg.get("chat_id")
      requests.get(
          f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(message)}",
          timeout=3,
      )
    elif service == "discord":
      requests.post(url, json={"content": message}, timeout=3)
    elif service == "pushover":
      requests.post(
          "https://pushover.net/1/messages.json",
          data={
              "token": webhook_cfg.get("token"),
              "user": webhook_cfg.get("user_key"),
              "message": message,
          },
          timeout=3,
      )
  except Exception:
    pass


def validate_new_entry(u_end, prev_val_end, week_num, season, df_existing, room_name):
  errors = []
  if u_end < prev_val_end:
    errors.append("Wartość końcowa nie może być mniejsza od poprzedniego stanu!")
  if not df_existing.empty:
    duplicate = not df_existing[
        (df_existing["room_name"] == room_name)
        & (df_existing["week_num"] == week_num)
        & (df_existing["season"] == season)
    ].empty
    if duplicate:
      errors.append(
          f"Wpis dla tygodnia {week_num} w sezonie {season} dla strefy"
          f" {room_name} już istnieje w bazie!"
      )
  return errors


def run_advanced_ml_prediction(df_all):
  df_sonoff = df_all[df_all["season"].str.contains("Sonoff", na=False)]
  if df_sonoff.empty or len(df_sonoff) < 2:
    current_units = df_sonoff["delta_units"].sum() if not df_sonoff.empty else 0.0
    return current_units * EST_PLN_PER_UNIT, current_units

  X = df_sonoff[["week_num", "temp_zewnetrzna"]].values
  y = df_sonoff["delta_units"].values

  model = LinearRegression()
  model.fit(X, y)

  total_weeks_in_season = 28
  current_weeks = df_sonoff["week_num"].nunique()
  remaining_weeks = max(0, total_weeks_in_season - current_weeks)

  avg_winter_temp = 1.5
  future_X = np.array(
      [
          [df_sonoff["week_num"].max() + i + 1, avg_winter_temp]
          for i in range(remaining_weeks)
      ]
  )

  if len(future_X) > 0:
    pred_future = model.predict(future_X)
    pred_future = np.maximum(pred_future, 0.0)
    total_predicted_units = df_sonoff["delta_units"].sum() + pred_future.sum()
  else:
    total_predicted_units = df_sonoff["delta_units"].sum()

  total_cost_pred = total_predicted_units * EST_PLN_PER_UNIT
  return total_cost_pred, total_predicted_units


st.markdown(
    """
    <style>
    @import url('https://fonts.cdnfonts.com/css/sf-pro-display');
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif !important;
        color: #1C1C1E !important;
    }
    .main { background: linear-gradient(180deg, #F2F2F7 0%, #E5E5EA 100%) !important; }
    .ios-room-info-card {
        background: rgba(255, 255, 255, 0.85) !important;
        backdrop-filter: blur(30px) saturate(190%);
        border-radius: 24px !important;
        padding: 24px 28px !important;
        border: 1.5px solid rgba(255, 255, 255, 0.9) !important;
        box-shadow: 0 10px 35px rgba(0, 0, 0, 0.06) !important;
        margin-bottom: 22px;
    }
    .room-header { font-size: 22px; font-weight: 700; color: #1C1C1E; letter-spacing: -0.4px; }
    .ios-live-badge {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(0, 122, 255, 0.2);
        padding: 10px 18px; border-radius: 16px; font-size: 15px; font-weight: 600; color: #1C1C1E;
    }
    .meter-badge { background: rgba(120, 120, 128, 0.12); color: #3A3A3C; padding: 5px 12px; border-radius: 12px; font-size: 13px; font-weight: 600; font-family: monospace; }
    .val-box {
        background: rgba(248, 249, 250, 0.9); border-radius: 16px; padding: 14px 16px; border: 1px solid rgba(229, 229, 234, 0.8); text-align: center;
    }
    .val-title { font-size: 11px; text-transform: uppercase; color: #8E8E93; font-weight: 700; letter-spacing: 0.6px; }
    .val-num { font-size: 24px; font-weight: 800; color: #007AFF; margin-top: 3px; }
    .fancy-alert-card {
        background: linear-gradient(135deg, rgba(0, 122, 255, 0.1) 0%, rgba(52, 199, 89, 0.1) 100%);
        border: 2px solid #007AFF; border-radius: 20px; padding: 20px 24px; margin-bottom: 25px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

ROOMS_CONFIG = {
    "Salon": {"icon": "🛋️", "meter_default": "POD-SAL-2026"},
    "Sypialnia": {"icon": "🛏️", "meter_default": "11420"},
    "Pokój Dziecka": {"icon": "🧒", "meter_default": "11420"},
    "Licznik Główny": {"icon": "🏢", "meter_default": "GJ-MAIN-2026"},
}

SEASONS = ["2025/2026 (Bazowy)", "2026/2027 (Sonoff - Wtorki)"]
MODES = [
    "Standard (Automatyczny)",
    "Eco / Redukcja niska",
    "Nieobecność domowników",
    "Intensywne grzanie",
]


def get_github_repo():
  try:
    github_config = st.secrets.get("github", {})
    token = github_config.get("token")
    repo_name = github_config.get("repo")
    if token and repo_name:
      return Github(token).get_repo(repo_name)
  except Exception:
    return None
  return None


def create_initial_df():
  return pd.DataFrame([
      {
          "id": 1,
          "season": "2026/2027 (Sonoff - Wtorki)",
          "week_num": 37,
          "period_label": "Tydzień 37 (Stan Zero)",
          "date_entry": "2026-09-08",
          "room_name": "Sypialnia",
          "meter_number": "11420",
          "units_start": 126.7,
          "units_end": 126.7,
          "delta_units": 0.0,
          "gj_start": 0.0,
          "gj_end": 0.0,
          "delta_gj": 0.0,
          "temp_zewnetrzna": 14.2,
          "mode_tag": "Standard (Automatyczny)",
          "notes": "Stan zero - wrzesień 2026",
      },
      {
          "id": 2,
          "season": "2026/2027 (Sonoff - Wtorki)",
          "week_num": 37,
          "period_label": "Tydzień 37 (Stan Zero)",
          "date_entry": "2026-09-08",
          "room_name": "Pokój Dziecka",
          "meter_number": "11420",
          "units_start": 110.4,
          "units_end": 110.4,
          "delta_units": 0.0,
          "gj_start": 0.0,
          "gj_end": 0.0,
          "delta_gj": 0.0,
          "temp_zewnetrzna": 14.2,
          "mode_tag": "Standard (Automatyczny)",
          "notes": "Stan zero - wrzesień 2026",
      },
  ])


def load_data():
  repo = get_github_repo()
  branch = st.secrets.get("github", {}).get("branch", "main")
  df = None
  if repo:
    try:
      file_content = repo.get_contents(FILE_PATH, ref=branch)
      df = pd.read_csv(
          io.StringIO(file_content.decoded_content.decode("utf-8"))
      )
    except Exception:
      df = load_local_fallback()
  else:
    df = load_local_fallback()

  if df is not None and not df.empty:
    if "temp_zewnetrzna" not in df.columns:
      df["temp_zewnetrzna"] = 12.0
    if "mode_tag" not in df.columns:
      df["mode_tag"] = "Standard (Automatyczny)"
  return df


def load_local_fallback():
  if os.path.exists(FILE_PATH):
    try:
      return pd.read_csv(FILE_PATH)
    except Exception:
      return create_initial_df()
  df = create_initial_df()
  os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
  df.to_csv(FILE_PATH, index=False)
  return df


def save_data(df, commit_message="Aktualizacja odczytu"):
  repo = get_github_repo()
  branch = st.secrets.get("github", {}).get("branch", "main")
  csv_string = df.to_csv(index=False)
  if repo:
    try:
      try:
        file_content = repo.get_contents(FILE_PATH, ref=branch)
        repo.update_file(
            FILE_PATH,
            commit_message,
            csv_string,
            file_content.sha,
            branch=branch,
        )
      except GithubException as e:
        if e.status == 404:
          repo.create_file(FILE_PATH, commit_message, csv_string, branch=branch)
      return True
    except Exception:
      return False
  os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
  df.to_csv(FILE_PATH, index=False)
  return True


def get_tuesday_for_iso_week(year, week):
  first_day = date(year, 1, 4)
  start_of_year = first_day - timedelta(days=first_day.weekday())
  return start_of_year + timedelta(weeks=week - 1, days=1)


df = load_data()
today = date.today()
is_tuesday = today.weekday() == 1

if "fancy_alert" in st.session_state:
  if time.time() - st.session_state["fancy_alert"]["timestamp"] > 300:
    del st.session_state["fancy_alert"]

if "selected_room" not in st.session_state:
  st.session_state["selected_room"] = "Sypialnia"
current_room = st.session_state["selected_room"]

st.title("🔥 Sonoff Smart Heating - Panel Sterowania")
st.caption(
    f"Lokalizacja: **{LOCATION_NAME}** | Płynne zarządzanie i inteligentna"
    " predykcja AI"
)

if "fancy_alert" in st.session_state:
  fa = st.session_state["fancy_alert"]
  st.markdown(
      f"""
    <div class="fancy-alert-card">
        <h3 style="margin: 0 0 8px 0; color: #007AFF;">⚡ Sukces! Nowy odczyt zapisany dla strefy: {fa['room']}</h3>
        <p style="margin: 4px 0; font-size: 16px;"><b>Przyrost ($\Delta U$):</b> <span style="color: #34C759; font-weight: 700;">+{fa['delta']:.1f} U</span> ({fa['delta']*EST_PLN_PER_UNIT:.2f} PLN)</p>
        <p style="margin: 4px 0; font-size: 16px;"><b>Bilans strefy:</b> <b style="color: #AF52DE;">{fa['total_room_units']:.1f} U</b> (~{fa['total_room_units']*EST_PLN_PER_UNIT:.2f} PLN)</p>
    </div>
    """,
      unsafe_allow_html=True,
  )

room_cols = st.columns(len(ROOMS_CONFIG))
for idx, (room_key, info) in enumerate(ROOMS_CONFIG.items()):
  is_active = current_room == room_key
  with room_cols[idx]:
    if st.button(
        f"{info['icon']} {room_key}",
        key=f"btn_{room_key}",
        use_container_width=True,
        type="primary" if is_active else "secondary",
    ):
      st.session_state["selected_room"] = room_key
      st.rerun()

st.divider()

df_room = (
    df[df["room_name"] == current_room].sort_values(by=["date_entry", "id"])
    if not df.empty
    else pd.DataFrame()
)
df_room_sonoff = (
    df_room[df_room["season"].str.contains("Sonoff", na=False)]
    if not df_room.empty
    else pd.DataFrame()
)

if not df_room_sonoff.empty:
  val_start = float(df_room_sonoff.iloc[0]["units_start"])
  last_row = df_room_sonoff.iloc[-1]
  val_end = float(last_row.get("units_end", val_start))
  last_meter = str(
      last_row.get("meter_number", ROOMS_CONFIG[current_room]["meter_default"])
  )
  total_delta_room = df_room_sonoff["delta_units"].sum()
else:
  val_start = (
      110.4
      if current_room == "Pokój Dziecka"
      else (126.7 if current_room == "Sypialnia" else 0.0)
  )
  val_end = val_start
  last_meter = ROOMS_CONFIG[current_room]["meter_default"]
  total_delta_room = 0.0

last_delta = (
    df_room_sonoff.iloc[-1]["delta_units"]
    if not df_room_sonoff.empty
    else 0.0
)
live_outdoor_temp = get_outdoor_temp()

if current_room == "Licznik Główny":
  df_sonoff_all_rooms = df[
      df["season"].str.contains("Sonoff", na=False)
      & (df["room_name"] != "Licznik Główny")
  ]
  total_delta_room = (
      df_sonoff_all_rooms["delta_units"].sum()
      if not df_sonoff_all_rooms.empty
      else 0.0
  )
  val_start = 0.0
  val_end = total_delta_room

df_sonoff_all = (
    df[df["season"].str.contains("Sonoff", na=False)]
    if not df.empty
    else pd.DataFrame()
)
total_apartment_units = (
    df_sonoff_all["delta_units"].sum() if not df_sonoff_all.empty else 0.0
)
total_realtime_cost = total_apartment_units * EST_PLN_PER_UNIT
room_share_pct = (
    (total_delta_room / total_apartment_units * 100)
    if total_apartment_units > 0
    else 0.0
)
season_budget_pln = SSM_ANNUAL_CO_BUDGET

if is_tuesday:
  current_year, current_iso_w, _ = today.isocalendar()
  already_added = False
  if not df_room.empty:
    already_added = (
        (df_room["week_num"] == current_iso_w)
        & (df_room["season"] == "2026/2027 (Sonoff - Wtorki)")
    ).any()

  if not already_added:
    with st.expander(
        f"🚨 WTOREK – Wymagany Odczyt dla strefy: {current_room} (Tydzień"
        f" {current_iso_w})",
        expanded=True,
    ):
      with st.form("auto_tuesday_modal_form"):
        m_input = st.text_input("Numer Podzielnika", value=last_meter)
        u_e = st.number_input(
            "Wartość Końcowa",
            min_value=0.0,
            value=max(val_end, val_start),
            step=0.1,
        )
        m_tag = st.selectbox("Tryb pracy grzania", MODES, index=0)
        col_g1, col_g2 = st.columns(2)
        with col_g1:
          gj_s_m = st.number_input(
              "Licznik Główny Początek [GJ]", min_value=0.0, value=0.0, step=0.01
          )
        with col_g2:
          gj_e_m = st.number_input(
              "Licznik Główny Koniec [GJ]", min_value=0.0, value=0.0, step=0.01
          )
        modal_notes = st.text_input(
            "Uwagi", value="Wtorkowa synchronizacja automatyczna"
        )

        if st.form_submit_button(
            "⚡ Zapisz i zsynchronizuj", use_container_width=True
        ):
          prev_val_end = val_end if not df_room_sonoff.empty else val_start
          validation_errors = validate_new_entry(
              u_e,
              prev_val_end,
              current_iso_w,
              "2026/2027 (Sonoff - Wtorki)",
              df,
              current_room,
          )

          if validation_errors:
            for err in validation_errors:
              st.error(err)
          else:
            delta_u_m = u_e - prev_val_end
            delta_g_m = gj_e_m - gj_s_m if gj_e_m > gj_s_m else 0.0
            next_id = (
                int(df["id"].max() + 1)
                if not df.empty and pd.notna(df["id"].max())
                else 1
            )

            new_row_modal = pd.DataFrame([{
                "id": next_id,
                "season": "2026/2027 (Sonoff - Wtorki)",
                "week_num": current_iso_w,
                "period_label": f"Tydzień {current_iso_w:02d} (Wtorek)",
                "date_entry": str(today),
                "room_name": current_room,
                "meter_number": m_input,
                "units_start": prev_val_end,
                "units_end": u_e,
                "delta_units": delta_u_m,
                "gj_start": gj_s_m,
                "gj_end": gj_e_m,
                "delta_gj": delta_g_m,
                "temp_zewnetrzna": live_outdoor_temp,
                "mode_tag": m_tag,
                "notes": modal_notes,
            }])

            df = pd.concat([df, new_row_modal], ignore_index=True)
            if save_data(
                df,
                commit_message=(
                    f"Wtorkowy odczyt: {current_room} T{current_iso_w}"
                ),
            ):
              new_total = total_delta_room + delta_u_m
              st.session_state["fancy_alert"] = {
                  "timestamp": time.time(),
                  "room": current_room,
                  "delta": delta_u_m,
                  "total_room_units": new_total,
              }
              send_webhook_notification(
                  f"🔥 Nowy odczyt Sonoff ({current_room}): +{delta_u_m:.1f} U"
                  f" (~{delta_u_m*EST_PLN_PER_UNIT:.2f} PLN). Łącznie w strefie:"
                  f" {new_total:.1f} U."
              )
              st.success("Zapisano pomyślnie!")
              st.rerun()

st.markdown(
    f"""
<div class="ios-room-info-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 12px;">
        <div class="room-header">
            {ROOMS_CONFIG[current_room]['icon']} Strefa: <b>{current_room}</b> 
            <span class="meter-badge">{last_meter}</span>
        </div>
        <div class="ios-live-badge">
            🌡️ Temp. zewn.: <b style="color: #007AFF;">{live_outdoor_temp}°C</b> &nbsp;|&nbsp; 📊 Udział: <b style="color: #AF52DE;">{room_share_pct:.1f}%</b>
        </div>
    </div>
""",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
with c1:
  st.markdown(
      f"""
    <div class="val-box">
        <div class="val-title">Początek Sezonu</div>
        <div class="val-num">{val_start:.1f} U</div>
        <div style="font-size: 11px; color: #8E8E93; margin-top: 2px;">{val_start*EST_PLN_PER_UNIT:.2f} PLN</div>
    </div>
    """,
      unsafe_allow_html=True,
  )
with c2:
  st.markdown(
      f"""
    <div class="val-box">
        <div class="val-title">Stan Aktualny</div>
        <div class="val-num">{val_end:.1f} U</div>
        <div style="font-size: 11px; color: #8E8E93; margin-top: 2px;">{val_end*EST_PLN_PER_UNIT:.2f} PLN</div>
    </div>
    """,
      unsafe_allow_html=True,
  )
with c3:
  st.markdown(
      f"""
    <div class="val-box">
        <div class="val-title">Ostatni Przyrost</div>
        <div class="val-num" style="color: #34C759;">+{last_delta:.1f} U</div>
        <div style="font-size: 11px; color: #34C759; margin-top: 2px;">+{last_delta*EST_PLN_PER_UNIT:.2f} PLN</div>
    </div>
    """,
      unsafe_allow_html=True,
  )
with c4:
  st.markdown(
      f"""
    <div class="val-box">
        <div class="val-title">Suma Strefa</div>
        <div class="val-num" style="color: #AF52DE;">{total_delta_room:.1f} U</div>
        <div style="font-size: 11px; color: #AF52DE; margin-top: 2px;">{total_delta_room*EST_PLN_PER_UNIT:.2f} PLN</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

st.markdown("</div>", unsafe_allow_html=True)

with st.sidebar:
  st.header("📥 Nowy Odczyt (Ręczny)")
  season_input = st.selectbox("Sezon grzewczy", SEASONS, index=1)
  current_year, current_iso_w, _ = date.today().isocalendar()
  week_input = st.number_input(
      "Tydzień Roku", min_value=1, max_value=52, value=current_iso_w
  )
  tuesday_date = get_tuesday_for_iso_week(2026, week_input)

  with st.form("tuesday_form"):
    meter_input = st.text_input("Numer Podzielnika", value=last_meter)
    u_start = st.number_input(
        "Początek", min_value=0.0, value=val_start, disabled=True
    )
    u_end = st.number_input(
        "Wartość Końcowa",
        min_value=0.0,
        value=max(val_end, val_start),
        step=0.1,
    )
    mode_input = st.selectbox("Tryb pracy", MODES, index=0)
    gj_s = st.number_input("GJ Początek", min_value=0.0, value=0.0, step=0.01)
    gj_e = st.number_input("GJ Koniec", min_value=0.0, value=0.0, step=0.01)
    entry_date = st.date_input("Data wpisu", tuesday_date)
    notes = st.text_input("Uwagi", value="Sonoff Auto")

    if st.form_submit_button(
        "⚡ Zapisz i Synchronizuj", use_container_width=True
    ):
      prev_val_end = val_end if not df_room_sonoff.empty else val_start
      validation_errors = validate_new_entry(
          u_end,
          prev_val_end,
          week_input,
          season_input,
          df,
          current_room,
      )

      if validation_errors:
        for err in validation_errors:
          st.error(err)
      else:
        delta_u = u_end - prev_val_end
        delta_g = gj_e - gj_s if gj_e > gj_s else 0.0
        next_id = (
            int(df["id"].max() + 1)
            if not df.empty and pd.notna(df["id"].max())
            else 1
        )

        new_row = pd.DataFrame([{
            "id": next_id,
            "season": season_input,
            "week_num": week_input,
            "period_label": f"Tydzień {week_input:02d} (Wtorek)",
            "date_entry": str(entry_date),
            "room_name": current_room,
            "meter_number": meter_input,
            "units_start": prev_val_end,
            "units_end": u_end,
            "delta_units": delta_u,
            "gj_start": gj_s,
            "gj_end": gj_e,
            "delta_gj": delta_g,
            "temp_zewnetrzna": live_outdoor_temp,
            "mode_tag": mode_input,
            "notes": notes,
        }])

        df = pd.concat([df, new_row], ignore_index=True)
        if save_data(df, commit_message=f"Odczyt: {current_room} T{week_input}"):
          new_total = total_delta_room + delta_u
          send_webhook_notification(
              f"🔥 Ręczny wpis ({current_room}): +{delta_u:.1f} U"
              f" (~{delta_u*EST_PLN_PER_UNIT:.2f} PLN)."
          )
          st.success("Zapisano pomyślnie!")
          st.rerun()

  st.markdown("---")
  st.header("🎛️ Symulator „Co jeśli?”")
  temp_change_slider = st.slider(
      "Zmiana temp. w mieszkaniu [°C]", -3.0, 3.0, 0.0, 0.5
  )
  sim_units = total_apartment_units * (temp_change_slider * 0.07)
  sim_pln = sim_units * EST_PLN_PER_UNIT
  if temp_change_slider < 0:
    st.success(
        f"💡 Oszczędność: ok. {abs(sim_units):.1f} U (~{abs(sim_pln):.2f} PLN)"
    )
  elif temp_change_slider > 0:
    st.error(f"⚠️ Wzrost kosztu: ok. +{sim_units:.1f} U (+{sim_pln:.2f} PLN)")

(
    tab_charts,
    tab_season_comp,
    tab_analytics,
    tab_ai_pred,
    tab_history,
) = st.tabs([
    "📈 Wykresy",
    "📊 Porównanie Sezonów",
    "💸 Finanse & Heatmapa",
    "🤖 Predykcja ML i AI",
    "📋 Historia",
])

with tab_charts:
  st.markdown(f"#### Korelacja Zużycia i Temperatury: {current_room}")
  if not df_room.empty:
    fig_dual = px_go.Figure()
    fig_dual.add_trace(
        px_go.Bar(
            x=df_room["period_label"],
            y=df_room["delta_units"],
            name="Zużycie [U]",
            marker_color="#007AFF",
        )
    )
    fig_dual.add_trace(
        px_go.Scatter(
            x=df_room["period_label"],
            y=df_room["temp_zewnetrzna"],
            name="Temp. Zewn. [°C]",
            yaxis="y2",
            line=dict(color="#FF9500", width=3),
        )
    )
    fig_dual.update_layout(
        template="plotly_white",
        yaxis=dict(title="Zużycie [U]"),
        yaxis2=dict(title="Temperatura [°C]", overlaying="y", side="right"),
        height=360,
    )
    st.plotly_chart(fig_dual, use_container_width=True)

with tab_ai_pred:
  st.markdown("### 🤖 Zaawansowany Model Predykcyjny Sezonu (Machine Learning)")
  pred_cost, pred_units = run_advanced_ml_prediction(df)

  col_m1, col_m2 = st.columns(2)
  with col_m1:
    st.markdown(
        f"""
        <div class="val-box">
            <div class="val-title">Przewidywany Koszt Sezonu (ML)</div>
            <div class="val-num" style="color: #AF52DE;">{pred_cost:.2f} PLN</div>
            <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">Szacowane jednostki: {pred_units:.1f} U</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with col_m2:
    surplus_deficit = SSM_ANNUAL_CO_BUDGET - pred_cost
    status_text = (
        f"Prognozowana nadpłata: +{surplus_deficit:.2f} PLN"
        if surplus_deficit >= 0
        else f"Prognozowana niedopłata: {surplus_deficit:.2f} PLN"
    )
    st.markdown(
        f"""
        <div class="val-box">
            <div class="val-title">Budżet SSM vs Predykcja</div>
            <div class="val-num" style="color: {'#34C759' if surplus_deficit >= 0 else '#FF3B30'}; font-size: 22px;">{surplus_deficit:+.2f} PLN</div>
            <div style="font-size: 12px; color: #8E8E93; margin-top: 4px;">{status_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_history:
  st.markdown("### 📋 Pełna Historia Wpisów")
  st.dataframe(df, use_container_width=True)
