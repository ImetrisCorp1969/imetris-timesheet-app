import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz, gspread
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive']

TZ = os.getenv('TIMEZONE','America/Detroit')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
SMTP_SERVER = os.getenv('SMTP_SERVER','smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT','587'))
FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USER)

SERVICE_ACCOUNT_JSON = os.getenv('SERVICE_ACCOUNT_JSON')

if not all([SPREADSHEET_ID, SMTP_USER, SMTP_PASS, SERVICE_ACCOUNT_JSON]):
    raise SystemExit('Missing required environment variables')

creds = Credentials.from_service_account_info(eval(SERVICE_ACCOUNT_JSON), scopes=SCOPES)
client = gspread.authorize(creds)
sh = client.open_by_key(SPREADSHEET_ID)
ws_users = sh.worksheet('Users')
ws_ts    = sh.worksheet('Timesheets')

users = ws_users.get_all_records()

# Week ending Friday
now = datetime.now(pytz.timezone(TZ))
weekday = now.weekday()  # Mon=0 ... Sun=6
friday = now + timedelta(days=(4 - weekday) % 7)
week_start = friday - timedelta(days=6)

week_end_str = friday.strftime('%Y-%m-%d')
week_start_str = week_start.strftime('%Y-%m-%d')

submitted = set()
for rec in ws_ts.get_all_records():
    if rec.get('WeekEnd') == week_end_str and str(rec.get('Status','')).strip() in ('Submitted','Approved','Rejected'):
        submitted.add(rec.get('Email','').lower())

pending = [u for u in users
           if str(u.get('Active','TRUE')).upper()=='TRUE'
           and not str(u.get('ReminderOptOut','FALSE')).upper()=='TRUE'
           and u.get('Email','').lower() not in submitted]

if not pending:
    print('No pending users. Exiting.')
    raise SystemExit

server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
server.starttls()
server.login(SMTP_USER, SMTP_PASS)

submit_url = "https://YOUR-STREAMLIT-APP-URL"

for u in pending:
    to_email = u.get('Email')
    mgr = u.get('ManagerEmail') or ''
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Imetris Timesheet Reminder – Week ending {week_end_str}"
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    if mgr:
        msg['Cc'] = mgr
    body = f"""
Hi {u.get('Name','')},

This is a friendly reminder to submit your Imetris timesheet for {week_start_str} to {week_end_str}.

Submit here: {submit_url}

If you've already submitted, please ignore.

Thank you!
– Imetris Timesheets Bot
"""
    msg.attach(MIMEText(body, 'plain'))
    recipients = [to_email] + ([mgr] if mgr else [])
    server.sendmail(FROM_EMAIL, recipients, msg.as_string())

server.quit()
print(f"Sent reminders to {len(pending)} user(s)")
