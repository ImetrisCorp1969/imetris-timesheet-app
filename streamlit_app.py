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
    days_to_friday = (end_weekday - when.weekday()) % 7
    fri = when + timedelta(days=days_to_friday)
    mon = fri - timedelta(days=4)
    sat = fri + timedelta(days=1)
    sun = fri + timedelta(days=2)
    return mon, fri, sat, sun

def default_day_rows():
    return {
        "mon": (8.0, "Worked"),
        "tue": (8.0, "Worked"),
        "wed": (8.0, "Worked"),
        "thu": (8.0, "Worked"),
        "fri": (8.0, "Worked"),
        "sat": (0.0, "Off"),
        "sun": (0.0, "Off"),
    }

STATUS_CHOICES = ["Worked", "Leave", "Absent", "Holiday", "Off"]

# -------------------------------
# Simple login (email + 6-digit PIN)
# -------------------------------
def login_panel(emp_df: pd.DataFrame):
    st.subheader("Sign in")
    email = st.text_input("Work Email")
    pin = st.text_input("PIN (6 digits)", type="password")

    if st.button("Continue", type="primary"):
        email_in = (email or "").strip().lower()
        pin_in   = (pin or "").strip()

        # Compare against normalized columns (robust to whitespace/formatting)
        rec = emp_df[
            (emp_df["email_norm"] == email_in) &
            (emp_df["pin_norm"]   == pin_in) &
            (emp_df["active_norm"])
        ]

        if not rec.empty:
            r = rec.iloc[0].to_dict()
            st.session_state.user = {
                "email": r.get("email"),
                "name": r.get("name",""),
                "role": r.get("role","employee"),
                "timezone": r.get("timezone","America/Detroit")
            }
            st.rerun()
        else:
            st.error("Invalid email or PIN, or not active.")
    st.caption("MVP uses an email + PIN from the roster. You can switch to Google Sign‑In later.")

# -------------------------------
# Submission form
# -------------------------------
def submission_form(user, emp_df):
    st.subheader("Submit Weekly Timesheet")
    week_choice = st.radio("Week", ["Current week", "Previous week"], horizontal=True)
    today = date.today()
    base_date = today if week_choice == "Current week" else (today - timedelta(days=7))
    mon, fri, sat, sun = week_dates(base_date)

    st.info(f"**Week ending:** {fri.isoformat()}")

    rows = default_day_rows()
    cols = st.columns(2)
    project = cols[0].text_input("Project / Client")
    notes   = cols[1].text_area("Notes", height=100, placeholder="Optional context")

    total_hours = 0.0
    day_labels = ["mon","tue","wed","thu","fri","sat","sun"]
    display_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    for i, d in enumerate(day_labels):
        hours_default, status_default = rows[d]
        c1, c2, c3 = st.columns([2,2,4])
        with c1:
            h = st.number_input(f"{display_names[i]} hours", min_value=0.0, max_value=24.0, step=0.5, value=hours_default, key=f"h_{d}")
        with c2:
            s = st.selectbox(f"{display_names[i]} status", STATUS_CHOICES, index=STATUS_CHOICES.index(status_default), key=f"s_{d}")
        if s in ["Leave","Absent","Holiday","Off"] and h != 0:
            h = 0.0
            st.session_state[f"h_{d}"] = 0.0
        total_hours += h
        rows[d] = (h, s)

    for d,(h,s) in rows.items():
        if s == "Worked" and h > 8:
            st.warning(f"{d.title()}: worked hours exceed 8.")
    if total_hours > 40:
        st.warning("Weekly hours exceed 40.")

    if st.button("Submit timesheet", type="primary", use_container_width=True):
        tsid = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat()
        append_timesheet_row([
            tsid, user["email"], fri.isoformat(),
            rows["mon"][0], rows["mon"][1],
            rows["tue"][0], rows["tue"][1],
            rows["wed"][0], rows["wed"][1],
            rows["thu"][0], rows["thu"][1],
            rows["fri"][0], rows["fri"][1],
            rows["sat"][0], rows["sat"][1],
            rows["sun"][0], rows["sun"][1],
            project, notes, total_hours, now_iso,
            "Submitted",""
        ])
        st.success("Submitted. You can review it in **My Submissions**.")
        st.balloons()

# -------------------------------
# My Submissions
# -------------------------------
def my_submissions(user):
    _, ws_ts, _, _ = get_ws()
    df = pd.DataFrame(ws_ts.get_all_records())
    if df.empty:
        st.info("No submissions yet.")
        return
    df = df[df["employee_email"].str.lower()==user["email"].lower()].copy()
    df.sort_values("submitted_at", ascending=False, inplace=True)
    st.dataframe(df[["week_ending","total_hours","project","approval_status","notes"]], use_container_width=True)

# -------------------------------
# Admin
# -------------------------------
def admin_page(user):
    st.subheader("Admin – Approvals & Oversight")
    _, ws_ts, _, _ = get_ws()
    df = pd.DataFrame(ws_ts.get_all_records())
    if df.empty:
        st.info("No timesheets submitted yet.")
        return
    week = st.selectbox("Filter by week ending", sorted(df["week_ending"].unique(), reverse=True))
    fil = df[df["week_ending"]==week].copy()
    st.dataframe(fil[["ts_id","employee_email","total_hours","project","approval_status","submitted_at","notes"]], use_container_width=True, height=350)
    st.markdown("---")
    tsid = st.text_input("Timesheet ID to update (ts_id)")
    new_status = st.selectbox("New status", ["Approved","Rejected","Submitted"])
    if st.button("Update status"):
        update_timesheet_status(tsid, new_status, user["email"])
        st.success("Updated. Refresh the grid to see the change.")

# -------------------------------
# App
# -------------------------------
def main():
    settings = load_settings()
    st.title("🕒 Imetris Weekly Timesheets (MVP)")
    st.caption("Week ending Friday. Weekend hours allowed per company policy.")

    emp_df = load_employees_df()

    # (Optional) Enable this while testing to see data as app reads it
    # st.expander("Debug: Employees loaded").write(
    #     emp_df[["email","email_norm","pin","pin_norm","active","active_norm"]].head(20)
    # )

    user = st.session_state.get("user")

    if not user:
        login_panel(emp_df)
        return

    st.sidebar.write(f"Signed in: **{user['name'] or user['email']}**  \nRole: **{user['role']}**")
    choice = st.sidebar.radio("Navigate", ["Submit Timesheet","My Submissions"] + (["Admin"] if user["role"] in ["admin","owner"] else []))

    if choice == "Submit Timesheet":
        submission_form(user, emp_df)
    elif choice == "My Submissions":
        my_submissions(user)
    elif choice == "Admin":
        admin_page(user)

if __name__ == "__main__":
    main()

