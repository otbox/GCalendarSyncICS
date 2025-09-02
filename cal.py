import os
import hashlib
import requests
from datetime import datetime, timedelta, timezone, date
from icalendar import Calendar
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from zoneinfo import ZoneInfo


# ================= CONFIGURAÇÃO =================
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]
ICS_URL = "url"
TIMEZONE = "America/Sao_Paulo"
TAKS_KEYWORDS = ["Exercícios", "Exercício", "Entrega", "Oficina", "Tarefa", "Tarefas", "Atividade"]
IGNORE_KEYWORDS = ["Frequência","Aula", "Presença"]
CREDENTIALS_PATH = 'path'


# ================= FUNÇÕES =================

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
    """Gera ID seguro para Google Calendar usando hash."""
    return hashlib.sha256(uid.encode('utf-8')).hexdigest()[:32]

def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # CORRIGIDO: Utilizando a variável CREDENTIALS_PATH
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
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
    local_tz = ZoneInfo(TIMEZONE)

    print("Buscando a lista completa de tarefas existentes...")
    all_tasks = []
    page_token = None
    try:
        while True:
            tasks_result = tasks_service.tasks().list(
                tasklist=tasklist_id,
                showHidden=True,
                maxResults=100,
                pageToken=page_token
            ).execute()
            all_tasks.extend(tasks_result.get("items", []))
            page_token = tasks_result.get("nextPageToken")
            if not page_token:
                break
        print(f"Encontradas {len(all_tasks)} tarefas no total.")
    except Exception as e:
        print(f"ERRO CRÍTICO ao buscar lista de tarefas: {e}")
        return

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID"))
        summary = str(component.get("SUMMARY", "Sem título"))
        description = str(component.get("DESCRIPTION", "")).replace("\\n", "\n").replace("\\,", ",")
        
        dtstart_raw = component.get("DTSTART").dt
        dtend_raw = component.get("DTEND").dt if component.get("DTEND") else dtstart_raw + timedelta(hours=1)

        # Converte a data/hora original para o fuso horário local do usuário
        dtstart_local = dtstart_raw.astimezone(local_tz)
        dtend_local = dtend_raw.astimezone(local_tz)
        
        if should_ignore(summary, IGNORE_KEYWORDS):
            continue

        if should_create_task(summary):
            ics_uid_tag = f"ics_uid:{uid}"
            
            # O horário exibido no título vem da data/hora local correta
            due_time_str = dtend_local.strftime('%H:%M')
            original_title = summary.replace('[TAREFA] ', '')
            task_title = f"[{due_time_str}] {original_title}"
            
            # CORREÇÃO PRINCIPAL: Usar apenas a data local, sem conversão para UTC
            # O Google Tasks interpreta 'due' como data apenas, não data/hora
            due_date_local = dtend_local.date()
            due_date_string = due_date_local.isoformat() + "T00:00:00.000Z"
            
            print(f"DEBUG - Data original: {dtend_raw}")
            print(f"DEBUG - Data local: {dtend_local}")
            print(f"DEBUG - Data para task: {due_date_string}")
            print(f"DEBUG - Data final task: {due_date_local}")

            task_notes = f"{description}\n\n{ics_uid_tag}"
            task_body = {'title': task_title, 'notes': task_notes, 'due': due_date_string}

            try:
                existing_task = next((t for t in all_tasks if ics_uid_tag in t.get("notes", "")), None)

                if existing_task:
                    tasks_service.tasks().update(tasklist=tasklist_id, task=existing_task['id'], body=task_body).execute()
                    print(f"Tarefa ATUALIZADA: {task_title} (Venc: {due_date_local.strftime('%d/%m/%Y')})")
                else:
                    tasks_service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
                    print(f"Tarefa CRIADA: {task_title} (Venc: {due_date_local.strftime('%d/%m/%Y')})")
            except Exception as e:
                print(f"ERRO ao processar tarefa {task_title}: {e}")
        else:
            # Eventos do Google Agenda usam a data/hora completa e já funcionavam corretamente
            safe_id = uid_to_id(uid)
            event_body = {
                "id": safe_id, "summary": summary, "description": description,
                "start": {"dateTime": dtstart_local.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": dtend_local.isoformat(), "timeZone": TIMEZONE},
            }
            try:
                calendar_service.events().get(calendarId="primary", eventId=safe_id).execute()
                calendar_service.events().update(calendarId="primary", eventId=safe_id, body=event_body).execute()
            except:
                try:
                    calendar_service.events().insert(calendarId="primary", body=event_body).execute()
                except Exception as e:
                    print(f"Erro ao criar/atualizar evento {summary}: {e}")


def clear_all(calendar_service, tasks_service, calendar_id="primary", tasklist_id="@default"):
    try:
        now = datetime.utcnow().isoformat() + "Z"
        events_result = calendar_service.events().list(
            calendarId=calendar_id, timeMin=now, maxResults=2500, singleEvents=True, orderBy="startTime"
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
if __name__ == '__main__':
    calendar_service, tasks_service = authenticate()
    ical_text = load_ics(ICS_URL)

    process_events(calendar_service, tasks_service, ical_text)
    # Para apagar tudo, descomente a linha abaixo:
    # for x in range(0,2):
    #     clear_all(calendar_service, tasks_service) 