from __future__ import print_function
import os.path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# Scope para acceso completo a Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']


# Ruta al JSON de la Service Account
SERVICE_ACCOUNT_FILE = '/home/mauricio/github/digimon/service_account.json'


def get_calendar_service():
    """Conecta al Google Calendar usando Service Account"""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    service = build('calendar', 'v3', credentials=creds)
    return service


def remove_all_events(service, calendar_id='817c60d271b59bfb03165accd74514cd7cda43b3455e3378804a6e4ceb12b3cb@group.calendar.google.com'):
    """Elimina todos los eventos en un calendario específico"""

    # Eliminar eventos en ese calendario
    page_token = None
    total_deleted = 0
    while True:
        events_result = service.events().list(
            calendarId=calendar_id,
            singleEvents=True,
            orderBy='startTime',
            pageToken=page_token
        ).execute()

        events = events_result.get('items', [])
        for event in events:
            service.events().delete(calendarId=calendar_id,
                                    eventId=event['id']).execute()
            print(f"Deleted event: {event.get('summary')}")
            total_deleted += 1

        page_token = events_result.get('nextPageToken')
        if not page_token:
            break

    print(f"All events deleted'. Total: {total_deleted}")


def remove_future_events(service, calendar_id='817c60d271b59bfb03165accd74514cd7cda43b3455e3378804a6e4ceb12b3cb@group.calendar.google.com'):
    """Elimina solo los eventos futuros en un calendario específico"""

    page_token = None
    total_deleted = 0
    while True:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=datetime.utcnow().isoformat() + 'Z',  # Solo eventos futuros
            singleEvents=True,
            orderBy='startTime',
            pageToken=page_token
        ).execute()

        events = events_result.get('items', [])
        for event in events:
            service.events().delete(calendarId=calendar_id,
                                    eventId=event['id']).execute()
            print(f"Deleted event: {event.get('summary')}")
            total_deleted += 1

        page_token = events_result.get('nextPageToken')
        if not page_token:
            break

    print(f"All future events deleted. Total: {total_deleted}")


def add_event(service, name, dt, duration_minutes=60, calendar_id='817c60d271b59bfb03165accd74514cd7cda43b3455e3378804a6e4ceb12b3cb@group.calendar.google.com'):
    """Agrega un evento al calendario con nombre y datetime"""
    event = {
        'summary': name,
        'start': {
            'dateTime': dt.isoformat(),
            'timeZone': 'Asia/Bangkok',  # ajusta tu zona horaria
        },
        'end': {
            'dateTime': (dt + timedelta(minutes=duration_minutes)).isoformat(),
            'timeZone': 'Asia/Bangkok',
        },
    }
    created_event = service.events().insert(
        calendarId=calendar_id, body=event).execute()
    print(f"Event created: {created_event.get('summary')}")


def show_events(service, calendar_id='817c60d271b59bfb03165accd74514cd7cda43b3455e3378804a6e4ceb12b3cb@group.calendar.google.com', max_results=20):
    """Muestra los próximos eventos del calendario"""
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=datetime.utcnow().isoformat() + 'Z',  # solo eventos futuros
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    if not events:
        print("No upcoming events found.")
        return

    print(f"Next {len(events)} events:")
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"{start} - {event.get('summary')}")


def main():
    service = get_calendar_service()

    # Ejemplo: eliminar todos los eventos futuros
    # remove_all_events(service)
    show_events(service)

    # # Ejemplo: agregar un evento
    dt = datetime(2025, 11, 20, 16, 30)  # año, mes, día, hora, minuto
    add_event(service, "Prueba Evento", dt)


if __name__ == '__main__':
    main()
