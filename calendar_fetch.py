from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
SERVICE_ACCOUNT_FILE = "service_account.json"  # Path to your downloaded JSON key
CALENDAR_ID = "primary"  # Or your specific Google Calendar email address


def get_upcoming_week_events():
    """Fetches all events for the next 7 days from Google Calendar."""
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=7)).isoformat() + "Z"

    events_result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    extracted_events = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        summary = event.get("summary", "No Title")
        extracted_events.append({"start": start, "end": end, "summary": summary})

    return extracted_events


if __name__ == "__main__":
    week_events = get_upcoming_week_events()
    for e in week_events:
        print(f"{e['start']} - {e['end']}: {e['summary']}")
