import os
import hashlib
import requests
from datetime import datetime, timedelta, timezone, date
from icalendar import Calendar
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from zoneinfo import ZoneInfo # <-- ADICIONADO


# ================= CONFIGURAÇÃO =================
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]
ICS_URL = "https://moodle.ggte.unicamp.br/calendar/export_execute.php?userid=117227&authtoken=232ada9dbb9e0cc90ddfec2df033bfa25098e439&preset_what=all&preset_time=custom"
TIMEZONE = "America/Sao_Paulo"
TAKS_KEYWORDS = ["Exercícios", "Exercício", "Entrega", "Oficina", "Tarefa", "Tarefas", "Atividade"]
IGNORE_KEYWORDS = ["Frequência","Aula", "Presença"]
CREDENTIALS_PATH = '/home/otbox/Documentos/Projetos/tmp/CalendarP/credentials.json'


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


# ... (outras funções do seu script permanecem iguais) ...

def process_events(calendar_service, tasks_service, ical_data, replace_existing=True):
    cal = Calendar.from_ical(ical_data)
    tasklist_id = '@default'
    local_tz = ZoneInfo(TIMEZONE)

    # --- CORREÇÃO: BUSCAR TODAS AS TAREFAS USANDO PAGINAÇÃO ---
    print("Buscando a lista completa de tarefas existentes...")
    all_tasks = []
    page_token = None
    try:
        while True:
            tasks_result = tasks_service.tasks().list(
                tasklist=tasklist_id,
                showHidden=True,
                maxResults=100,  # Máximo permitido por página
                pageToken=page_token
            ).execute()

            items = tasks_result.get("items", [])
            all_tasks.extend(items)

            page_token = tasks_result.get("nextPageToken")
            if not page_token:
                break
        print(f"Encontradas {len(all_tasks)} tarefas no total.")
    except Exception as e:
        print(f"ERRO CRÍTICO ao buscar lista de tarefas: {e}")
        # Se não puder buscar as tarefas, é mais seguro parar para não criar duplicatas.
        return

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID"))
        summary = str(component.get("SUMMARY", "Sem título"))
        description = str(component.get("DESCRIPTION", "")).replace("\\n", "\n").replace("\\,", ",")
        
        dtstart_raw = component.get("DTSTART").dt
        dtend_raw = component.get("DTEND").dt if component.get("DTEND") else dtstart_raw + timedelta(hours=1)

        def get_timezone_aware_datetime(dt_object):
            if isinstance(dt_object, date) and not isinstance(dt_object, datetime):
                return datetime.combine(dt_object, datetime.max.time()).replace(microsecond=0, tzinfo=local_tz)
            if dt_object.tzinfo is None:
                return dt_object.replace(tzinfo=local_tz)
            return dt_object.astimezone(local_tz)
        
        dtstart = get_timezone_aware_datetime(dtstart_raw)
        dtend = get_timezone_aware_datetime(dtend_raw)

        if should_ignore(summary, IGNORE_KEYWORDS):
            continue

        if should_create_task(summary):
            ics_uid_tag = f"ics_uid:{uid}"
            due_time_str = dtend.strftime('%H:%M')
            original_title = summary.replace('[TAREFA] ', '')
            task_title = f"[{due_time_str}] {original_title}"
            
            due_utc = dtend.astimezone(timezone.utc)
            due_utc_iso_string = due_utc.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z'
            
            task_notes = f"{description}\n\n{ics_uid_tag}"
            task_body = {'title': task_title, 'notes': task_notes, 'due': due_utc_iso_string}

            try:
                # A busca agora é feita na lista completa de tarefas
                existing_task = next((t for t in all_tasks if ics_uid_tag in t.get("notes", "")), None)

                if existing_task:
                    # Se encontrou, ATUALIZA
                    tasks_service.tasks().update(tasklist=tasklist_id, task=existing_task['id'], body=task_body).execute()
                    print(f"Tarefa ATUALIZADA: {task_title}")
                else:
                    # Se não encontrou, CRIA
                    tasks_service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
                    print(f"Tarefa CRIADA: {task_title}")
            except Exception as e:
                print(f"ERRO ao processar tarefa {task_title}: {e}")
        else:
            # Lógica para eventos da agenda (continua igual)
            safe_id = uid_to_id(uid)
            event_body = {
                "id": safe_id, "summary": summary, "description": description,
                "start": {"dateTime": dtstart.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": dtend.isoformat(), "timeZone": TIMEZONE},
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
    