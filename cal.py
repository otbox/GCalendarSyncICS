import os
import hashlib
import requests
from datetime import datetime, timedelta
from icalendar import Calendar
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import timezone


TAKS_KEYWORDS = ["Exercícios", "Entrega", "Oficina", "Tarefa", "Tarefas", "Atividade"]
IGNORE_KEYWORDS = ["Aula", "Presença"]

# ================= CONFIGURAÇÃO =================
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]
ICS_URL = "url"  # caminho local ou URL real
TIMEZONE = "America/Sao_Paulo"

def should_create_task(summary: str) -> bool:
    summary_upper = summary.upper()
    for ignore in IGNORE_KEYWORDS:
        if ignore.upper() in summary_upper:
            return False
    for kw in TAKS_KEYWORDS:
        if kw.upper() in summary_upper:
            return True
    return False


def uid_to_id(uid):
    return hashlib.sha256(uid.encode('utf-8')).hexdigest()[:32]

def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    calendar_service = build('calendar', 'v3', credentials=creds)
    tasks_service = build('tasks', 'v1', credentials=creds)
    return calendar_service, tasks_service

def load_ics(url):
    if url.startswith("http"):
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.text
    else:
        with open(url, "r", encoding="utf-8") as f:
            return f.read()

def should_ignore(title: str, ignore_list: list[str]) -> bool:
    title_lower = title.lower()
    return any(word.lower() in title_lower for word in ignore_list)

def process_events(calendar_service, tasks_service, ical_data, replace_existing=True):
    cal = Calendar.from_ical(ical_data)
    tasklist_id = '@default'

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID"))
        summary = str(component.get("SUMMARY", "Sem título"))
        description = str(component.get("DESCRIPTION", "")).replace("\\n", "\n").replace("\\,", ",")

        dtstart = component.get("DTSTART").dt
        dtend = component.get("DTEND").dt if component.get("DTEND") else dtstart + timedelta(hours=1)
        
        if should_ignore(summary, IGNORE_KEYWORDS):
            print(f"Ignorado: {summary}")
            continue

        if should_create_task(summary):
            task_body = {
                'title': summary.replace('[TAREFA] ', '')[:250],  # limita 250 chars
                'notes': description.replace("\\n", "\n").replace("\\,", ","),
                'due': dtend.astimezone(timezone.utc).isoformat(timespec='seconds')
            }
            try:
                tasks_service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
                print(f"Tarefa criada: {summary}")
            except Exception as e:
                print(f"Erro ao criar tarefa {summary}: {e}")
        else:
            safe_id = uid_to_id(uid)
            event_body = {
                "id": safe_id,
                "summary": summary,
                "description": description,
                "start": {"dateTime": dtstart.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": dtend.isoformat(), "timeZone": TIMEZONE},
            }
            try:
                if replace_existing:
                    calendar_service.events().update(calendarId="primary", eventId=safe_id, body=event_body).execute()
                    print(f"Evento atualizado/criado: {summary}")
                else:
                    calendar_service.events().insert(calendarId="primary", body=event_body).execute()
                    print(f"Evento criado: {summary}")
            except Exception as e:
                print(f"Erro ao criar/atualizar evento {summary}: {e}")

def clear_all(calendar_service, tasks_service, calendar_id="primary", tasklist_id="@default"):
    try:
        now = datetime.utcnow().isoformat() + "Z"  # 'Z' = UTC
        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=2500,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])

        for event in events:
            try:
                calendar_service.events().delete(calendarId=calendar_id, eventId=event["id"]).execute()
                print(f"Evento apagado: {event.get('summary')}")
            except Exception as e:
                print(f"Erro ao apagar evento {event.get('summary')}: {e}")
    except Exception as e:
        print("Erro ao listar/apagar eventos:", e)

    try:
        tasks_result = tasks_service.tasks().list(tasklist=tasklist_id).execute()
        tasks = tasks_result.get("items", [])

        for task in tasks:
            try:
                tasks_service.tasks().delete(tasklist=tasklist_id, task=task["id"]).execute()
                print(f"Tarefa apagada: {task.get('title')}")
            except Exception as e:
                print(f"Erro ao apagar tarefa {task.get('title')}: {e}")
    except Exception as e:
        print("Erro ao listar/apagar tarefas:", e)

    print("Limpeza concluída!")


# ================= EXECUÇÃO =================
calendar_service, tasks_service = authenticate()
ical_text = load_ics(ICS_URL)

process_events(calendar_service, tasks_service, ical_text, replace_existing=True)

# --- Para apagar todos os eventos e tarefas importados ---
# clear_all(calendar_service, tasks_service, calendar_id="primary", tasklist_id="@default")

