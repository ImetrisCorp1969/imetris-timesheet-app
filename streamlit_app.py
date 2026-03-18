
    
import os
import uuid
from datetime import datetime, timedelta, date
from dateutil import tz
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Imetris Timesheets (MVP)", page_icon="🕒", layout="centered")

# -------------------------------
# Google Sheets client
# -------------------------------
@st.cache_resource(show_spinner=False)
def get_gs_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    skey = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(skey, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_ws():
    gc = get_gs_client()
    sh = gc.open_by_key(st.secrets["gsheet"]["id"])
    ws_emp = sh.worksheet("Employees")
    ws_ts = sh.worksheet("Timesheets")
    ws_rem = sh.worksheet("Reminders")
    ws_settings = sh.worksheet("Settings")
    return ws_emp, ws_ts, ws_rem, ws_settings

# -------------------------------
# Normalization helper for robust login
# -------------------------------
def normalize_employees_df(df: pd.DataFrame) -> pd.DataFrame:
    """Create normalized columns that are resilient to Sheets formatting."""
    df = df.copy()

    # Ensure expected columns exist (defensive)
    for col in ["email", "pin", "active", "name", "role", "timezone", "manager_email", "client"]:
        if col not in df.columns:
            df[col] = None

    # Normalize fields used for matching
    df["email_norm"]  = df["email"].astype(str).str.strip().str.lower()
    df["pin_norm"]    = df["pin"].astype(str).str.strip()
    df["active_norm"] = df["active"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
    return df

def load_employees_df():
    ws_emp, _, _, _ = get_ws()
    rows = ws_emp.get_all_records()  # list[dict] from gspread
    df = pd.DataFrame(rows)
    df = normalize_employees_df(df)
    return df

def load_settings():
    _, _, _, ws_settings = get_ws()
    kv = dict(ws_settings.get_all_values())
    return kv

def append_timesheet_row(row_values:list):
    _, ws_ts, _, _ = get_ws()
    ws_ts.append_row(row_values, value_input_option="USER_ENTERED")

def update_timesheet_status(ts_id:str, approval_status:str, approver_email:str):
    _, ws_ts, _, _ = get_ws()
    data = ws_ts.get_all_values()
    header = data[0]
    try:
        id_idx = header.index("ts_id")
        status_idx = header.index("approval_status")
        approver_idx = header.index("approver_email")
    except ValueError:
        st.error("Timesheets sheet missing required headers.")
        return
    for i, row in enumerate(data[1:], start=2):
        if len(row) > id_idx and row[id_idx] == ts_id:
            ws_ts.update(range_name=f"{chr(65+status_idx)}{i}", values=[[approval_status]])
            ws_ts.update(range_name=f"{chr(65+approver_idx)}{i}", values=[[approver_email]])
            return

# -------------------------------
# Week helpers (week ending Friday)
# -------------------------------
def week_dates(when:date, end_weekday=4):  # Mon=0..Fri=4
    days_to_friday
