import os
import sys
import json
from datetime import datetime, timedelta
import zoneinfo
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from google import genai

# ==========================================
# 1. CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# 2. GOOGLE CALENDAR FETCHER (UK TIMEZONE)
# ==========================================
def fetch_calendar_events():
    """Reads events from multiple Google Calendars and converts times to UK Local Time."""
    service_account_info = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    try:
        if service_account_info:
            creds_dict = json.loads(service_account_info)
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
        elif os.path.exists("service_account.json"):
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
        else:
            print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON missing and service_account.json not found. Skipping calendar.")
            return []

        service = build("calendar", "v3", credentials=creds)

        # Set search window for next 7 days in UTC
        now_utc = datetime.now(zoneinfo.ZoneInfo("UTC"))
        start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        time_min = start_of_today.isoformat()
        time_max = (start_of_today + timedelta(days=7)).isoformat()

        CALENDAR_IDS = [
            "primary",
            "family17626229456844949933@group.calendar.google.com",
            # Add secondary calendar IDs here if needed
        ]

        uk_tz = zoneinfo.ZoneInfo("Europe/London")
        extracted = []

        for cal_id in CALENDAR_IDS:
            try:
                events_result = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )
                
                for item in events_result.get("items", []):
                    raw_start = item["start"].get("dateTime", item["start"].get("date"))
                    raw_end = item["end"].get("dateTime", item["end"].get("date"))

                    if "T" in raw_start:
                        dt_start = datetime.fromisoformat(raw_start).astimezone(uk_tz)
                        dt_end = datetime.fromisoformat(raw_end).astimezone(uk_tz)
                        formatted_start = dt_start.strftime("%Y-%m-%d %H:%M")
                        formatted_end = dt_end.strftime("%H:%M")
                    else:
                        formatted_start = raw_start  # All-day event
                        formatted_end = raw_end

                    extracted.append({
                        "summary": item.get("summary", "Busy"),
                        "start": formatted_start,
                        "end": formatted_end
                    })
            except Exception as cal_err:
                print(f"Error fetching calendar '{cal_id}': {cal_err}")

        print(f"Total events fetched across all calendars: {len(extracted)}")
        return extracted
    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []

# ==========================================
# 3. AI PROMPT ENGINE (GEMINI)
# ==========================================
def generate_ai_briefing(calendar_events):
    """Sends schedule and prompt to Gemini API formatted for Telegram HTML."""
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY missing.")
        return "⚠️ Could not generate briefing: GEMINI_API_KEY missing."

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    events_json_str = json.dumps(calendar_events, indent=2)
    is_sunday = datetime.now().weekday() == 6

    prompt = f"""
You are an executive assistant and sports performance assistant. 
Analyze the user's calendar schedule and produce a clean Telegram daily briefing.

CALENDAR EVENTS (NEXT 7 DAYS):
{events_json_str}

DAY OF WEEK: {"Sunday" if is_sunday else "Workday/Weekday"}

FORMATTING RULES:
- Strictly use Telegram HTML tag syntax for formatting.
- Bold titles using <b>text</b>.
- Italics using <i>text</i>.
- DO NOT use markdown headers (no ###, no **).
- DO NOT use raw markdown bullet points with asterisks. Use standard bullet symbols like • or emojis.

STRUCTURE:
1. <b>📅 TODAY'S SCHEDULE & CONFLICTS</b>
   - Summarize today's events with converted local times.
   - Flag direct schedule conflicts or tight transitions.
   - Suggest ideal 30-minute packing/prep windows for travel or upcoming sports sessions.

2. <b>🥗 MEAL & FUELING RECOMMENDATION</b>
   - Suggest dinner timing and high-protein meal options around evening sports/tennis finish times.

3. <b>🛒 SUNDAY GROCERY LIST</b> (ONLY INCLUDE IF DAY OF WEEK IS SUNDAY)
   - Categorize by aisle: Produce, Protein, Dairy, Pantry.

Keep it concise, clear, and cleanly formatted for mobile reading.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text

# ==========================================
# 4. TELEGRAM DISPATCHER (HTML MODE)
# ==========================================
def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram credentials missing.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    res = requests.post(url, json=payload, timeout=10)
    print(f"Telegram API response code: {res.status_code}")
    if res.status_code != 200:
        print(f"Telegram error details: {res.text}")
    res.raise_for_status()

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    print("Fetching Calendar...")
    calendar_events = fetch_calendar_events()

    print("Generating AI Briefing...")
    briefing = generate_ai_briefing(calendar_events)

    print("Sending to Telegram...")
    send_telegram_message(briefing)
    print("Done!")

if __name__ == "__main__":
    main()
