import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials
import streamlit_authenticator as stauth

st.set_page_config(page_title='Imetris Timesheets', page_icon='🗓️', layout='wide')

# ====== Settings from secrets ======
TZ = st.secrets.get('app', {}).get('timezone', 'America/Detroit')
SPREADSHEET_ID = st.secrets['gsheet']['spreadsheet_id']
WEEK_ENDING = st.secrets.get('app', {}).get('week_ending', 'Friday')  # 'Friday' | 'Sunday'

# ====== Google Sheets helpers ======
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

@st.cache_resource(show_spinner=False)
def get_gs_client():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def open_sheet(spreadsheet_id: str):
    return get_gs_client().open_by_key(spreadsheet_id)

HEADERS_USERS = ["Email","Name","Role","ManagerEmail","Active","WeeklyHours","ReminderOptOut"]
HEADERS_TS = [
    "Timestamp","WeekStart","WeekEnd","Email","Name","Project",
    "MonHours","TueHours","WedHours","ThuHours","FriHours","SatHours","SunHours",
    "MonStatus","TueStatus","WedStatus","ThuStatus","FriStatus","SatStatus","SunStatus",
    "TotalHours","Notes","Status","ApprovedBy","ApprovedAt"
]

def ensure_worksheets(sh):
    try:
        ws_users = sh.worksheet('Users')
    except gspread.WorksheetNotFound:
        ws_users = sh.add_worksheet(title='Users', rows=200, cols=len(HEADERS_USERS))
        ws_users.append_row(HEADERS_USERS)

    try:
        ws_ts = sh.worksheet('Timesheets')
    except gspread.WorksheetNotFound:
        ws_ts = sh.add_worksheet(title='Timesheets', rows=2000, cols=len(HEADERS_TS))
        ws_ts.append_row(HEADERS_TS)

    # Optional Holidays
    try:
        sh.worksheet('Holidays')
    except gspread.WorksheetNotFound:
        sh.add_worksheet(title='Holidays', rows=200, cols=2)

    return ws_users, ws_ts

def get_users_df(ws_users):
    data = ws_users.get_all_records()
    df = pd.DataFrame(data)
    return df if not df.empty else pd.DataFrame(columns=HEADERS_USERS)

def upsert_timesheet(ws_ts, key_email: str, key_weekend: str, row: list):
    data = ws_ts.get_all_records()
    idx = None
    for i, rec in enumerate(data, start=2):  # worksheet data starts at row 2
        if str(rec.get('Email','')).lower()==key_email.lower() and str(rec.get('WeekEnd',''))==key_weekend:
            idx = i
            break
    if idx:
        ws_ts.update(f'A{idx}:Z{idx}', [row])
    else:
        ws_ts.append_row(row)

# ====== Auth (simple) ======
config = {
    'credentials': { 'usernames': {} },
    'cookie': {
        'name': st.secrets['auth'].get('cookie_name','imetris_ts'),
        'key': st.secrets['auth'].get('signature_key','CHANGE_ME'),
        'expiry_days': st.secrets['auth'].get('expiry_days',30),
    },
    'preauthorized': { 'emails': [] }
}

# Load users & hashed passwords from secrets
for uname, vals in st.secrets['auth']['credentials']['usernames'].items():
    config['credentials']['usernames'][uname] = {
        'email': vals.get('email'),
        'name': vals.get('name'),
        'password': vals.get('password')
    }

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

name, auth_status, username = authenticator.login('Login', location='main')

if auth_status is False:
    st.error('Invalid username or password')
elif auth_status is None:
    st.info('Please enter your credentials')
else:
    # Logged in
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f"Hello, **{name}**")

    sh = open_sheet(SPREADSHEET_ID)
    ws_users, ws_ts = ensure_worksheets(sh)
    users_df = get_users_df(ws_users)

    # Resolve role (from secrets; optionally overridden by Users sheet)
    user_email = st.secrets['auth']['credentials']['usernames'][username]['email']
    role = st.secrets['auth']['credentials']['usernames'][username].get('role','user')
    if user_email:
        m = users_df[users_df['Email'].str.lower()==user_email.lower()]
        if not m.empty:
            role = m.iloc[0].get('Role', role)

    # Week math (Friday week-ending by default)
    now = datetime.now(pytz.timezone(TZ))
    weekday = now.weekday()  # Mon=0 ... Sun=6
    if WEEK_ENDING.lower()=='friday':
        delta = (4 - weekday) % 7  # 4=Fri
    else:
        delta = (6 - weekday) % 7  # 6=Sun
    week_end = now + timedelta(days=delta)
    week_start = week_end - timedelta(days=6)

    st.title('🗓️ Imetris Weekly Timesheet')

    tabs = ["Submit Timesheet"] + (["Admin Dashboard"] if role=='admin' else [])
    sel = st.tabs(tabs)

    # --- Submit Tab ---
    with sel[0]:
        st.subheader(f"Week: {week_start.date()} → {week_end.date()} (ending {week_end.strftime('%A')})")
        project = st.text_input('Project / Client')

        days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        default_hours = [8,8,8,8,8,0,0]
        statuses, hours = {}, {}
        for i, d in enumerate(days):
            c1, c2, c3 = st.columns([1,1,2])
            with c1:
                hours[d] = st.number_input(f"{d} Hours", min_value=0.0, max_value=24.0,
                                           value=float(default_hours[i]), step=0.5, key=f"h_{d}")
            with c2:
                statuses[d] = st.selectbox(f"{d} Status", ['Worked','Leave','Absent','Holiday'], index=0, key=f"s_{d}")
            with c3:
                if statuses[d] != 'Worked':
                    st.caption('Hours set to 0 for non-work days')
                    hours[d] = 0.0

        notes = st.text_area('Notes (optional)')
        total_hours = sum(hours.values())
        st.metric('Total Hours', f"{total_hours:.1f}")
        if total_hours > 40:
            st.warning('Weekly hours exceed 40')

        if st.button('Submit / Update Timesheet', type='primary'):
            row = [
                now.strftime('%Y-%m-%d %H:%M:%S'),
                str(week_start.date()),
                str(week_end.date()),
                user_email,
                name,
                project,
                hours['Mon'],hours['Tue'],hours['Wed'],hours['Thu'],hours['Fri'],hours['Sat'],hours['Sun'],
                statuses['Mon'],statuses['Tue'],statuses['Wed'],statuses['Thu'],statuses['Fri'],statuses['Sat'],statuses['Sun'],
                total_hours,
                notes,
                'Submitted','', ''
            ]
            upsert_timesheet(ws_ts, user_email, str(week_end.date()), row)
            st.success('Timesheet saved!')

    # --- Admin Tab ---
    if role == 'admin' and len(tabs) > 1:
        with sel[1]:
            st.subheader('Admin Dashboard')

            # Filter by week end (Friday)
            week_end_sel = st.date_input('Week ending', value=week_end.date())

            data = ws_ts.get_all_records()
            df = pd.DataFrame(data)
            if df.empty:
                st.info('No data yet')
            else:
                df = df[df['WeekEnd'] == str(week_end_sel)]
                st.dataframe(df)
                st.download_button('Export CSV', data=df.to_csv(index=False), file_name=f"timesheets_{week_end_sel}.csv")

                emails = sorted(df['Email'].unique())
                sel_email = st.selectbox('Select user to update status', emails) if len(emails) else None
                new_status = st.selectbox('Set status', ['Approved','Rejected'])
                if st.button('Update Status') and sel_email:
                    all_data = ws_ts.get_all_records()

                    def col_idx(name): return HEADERS_TS.index(name) + 1

                    for i, rec in enumerate(all_data, start=2):
                        if rec.get('Email') == sel_email and rec.get('WeekEnd') == str(week_end_sel):
                            ws_ts.update_cell(i, col_idx('Status'), new_status)
                            ws_ts.update_cell(i, col_idx('ApprovedBy'), user_email)
                            ws_ts.update_cell(i, col_idx('ApprovedAt'), datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M:%S'))
                            st.success(f"Updated {sel_email} to {new_status}")
                            break

            # --- Optional: Bulk CSV Import into Users sheet ---
            st.divider()
            st.subheader("Bulk import users (CSV)")
            csv_file = st.file_uploader("Upload a CSV with users", type=["csv"])
            if csv_file is not None:
                try:
                    tmp_df = pd.read_csv(csv_file).rename(columns=lambda c: c.strip())
                    # Normalize headers
                    low = {c.lower().replace(' ','').replace('_',''): c for c in tmp_df.columns}
                    # Map to Users schema
                    def pick(*options):
                        for o in options:
                            key = o.lower().replace(' ','').replace('_','')
                            if key in low: return low[key]
                        return None
                    col_map = {
                        'Email': pick('email'),
                        'Name': pick('name'),
                        'Role': pick('role'),
                        'ManagerEmail': pick('manageremail','manager_email'),
                        'Active': pick('active'),
                        'WeeklyHours': pick('weeklyhours','weekly_hours'),
                        'ReminderOptOut': pick('reminderoptout','reminder_opt_out')
                    }
                    missing = [k for k,v in col_map.items() if v is None and k in ['Email','Name','Role']]
                    if missing:
                        st.error(f"Missing required columns in CSV: {', '.join(missing)}")
                        st.stop()

                    norm = pd.DataFrame()
                    norm['Email'] = tmp_df[col_map['Email']].astype(str).str.strip()
                    norm['Name'] = tmp_df[col_map['Name']].astype(str).str.strip()
                    role_series = tmp_df[col_map['Role']].astype(str).str.strip().str.lower()
                    norm['Role'] = role_series.apply(lambda r: 'admin' if r=='admin' else 'user')

                    norm['ManagerEmail'] = tmp_df[col_map['ManagerEmail']].astype(str).str.strip() if col_map['ManagerEmail'] else ''
                    # Booleans
                    if col_map['Active']:
                        norm['Active'] = tmp_df[col_map['Active']].astype(str).str.upper().isin(['TRUE','1','YES','Y','T']).map({True:'TRUE', False:'FALSE'})
                    else:
                        norm['Active'] = 'TRUE'
                    # Weekly hours
                    if col_map['WeeklyHours']:
                        norm['WeeklyHours'] = pd.to_numeric(tmp_df[col_map['WeeklyHours']], errors='coerce').fillna(40).clip(0,80).astype(int)
                    else:
                        norm['WeeklyHours'] = 40
                    # Opt out
                    if col_map['ReminderOptOut']:
                        norm['ReminderOptOut'] = tmp_df[col_map['ReminderOptOut']].astype(str).str.upper().isin(['TRUE','1','YES','Y','T']).map({True:'TRUE', False:'FALSE'})
                    else:
                        norm['ReminderOptOut'] = 'FALSE'

                    # Clean
                    before = len(norm)
                    norm = norm[(norm['Email']!='') & (norm['Name']!='')]
                    norm = norm.drop_duplicates(subset=['Email'], keep='first')
                    st.write("Preview:", norm.head(10))

                    if st.button("Import into Users sheet", type="primary"):
                        existing = ws_users.get_all_records()
                        existing_emails = {e.get('Email','').lower() for e in existing}

                        if not existing:
                            ws_users.append_row(HEADERS_USERS)

                        rows_to_add, added, skipped = [], 0, 0
                        for _, r in norm.iterrows():
                            if r['Email'].lower() in existing_emails:
                                skipped += 1
                                continue
                            rows_to_add.append([
                                r["Email"], r["Name"], r["Role"], r["ManagerEmail"],
                                r["Active"], int(r["WeeklyHours"]), r["ReminderOptOut"]
                            ])
                            added += 1

                        CHUNK = 200
                        for i in range(0, len(rows_to_add), CHUNK):
                            ws_users.append_rows(rows_to_add[i:i+CHUNK])

                        st.success(f"Imported {added} user(s). Skipped {skipped} duplicate(s).")
                except Exception as e:
                    st.error(f"Import failed: {e}")
