# Imetris Timesheet App — MVP

A lightweight, free, Streamlit‑based weekly timesheet system for Imetris Corporation.

## Features
- Simple login via email + PIN
- Weekly timesheet submission (week ending Friday)
- Admin approvals
- Google Sheets backend
- Automatic Friday reminders via Apps Script

## Project Structure
```
imetris-timesheet-app/
├── streamlit_app.py
├── requirements.txt
└── .streamlit/
```

## Google Sheet Tabs
### Employees
```
email,name,role,timezone,pin,manager_email,client,active
```
### Timesheets
```
ts_id,employee_email,week_ending,mon_hours,mon_status,tue_hours,tue_status,wed_hours,wed_status,thu_hours,thu_status,fri_hours,fri_status,sat_hours,sat_status,sun_hours,sun_status,project,notes,total_hours,submitted_at,approval_status,approver_email
```
### Reminders
```
employee_email,week_ending,reminder_sent_at,timezone,send_window_label
```
### Settings
```
key,value
company_name,Imetris
week_ending,Friday
app_url,https://<your-app-url>.streamlit.app
```

## Streamlit Secrets
```
[gcp_service_account]
...
[gsheet]
id="<sheet-id>"
[app]
company_email="ImetrisTimesheets@gmail.com"
```

## Deployment
1. Push repo to GitHub
2. Deploy via Streamlit Cloud
3. Add Secrets
4. Done
