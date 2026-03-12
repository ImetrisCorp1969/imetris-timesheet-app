# Optional helper module (NOT required if using the app.py as provided)
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_client(info):
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

def ensure_users_timesheets(sh, headers_users, headers_ts):
    try:
        ws_users = sh.worksheet('Users')
    except gspread.WorksheetNotFound:
        ws_users = sh.add_worksheet(title='Users', rows=200, cols=len(headers_users))
        ws_users.append_row(headers_users)

    try:
        ws_ts = sh.worksheet('Timesheets')
    except gspread.WorksheetNotFound:
        ws_ts = sh.add_worksheet(title='Timesheets', rows=2000, cols=len(headers_ts))
        ws_ts.append_row(headers_ts)

    return ws_users, ws_ts
