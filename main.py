import os
import sys
import json
from datetime import datetime, timedelta
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from google import genai

# ==========================================
# 1. CONFIGURATION & LOCATION (Rest Bay)
# ==========================================
LATITUDE = 51.4820
LONGITUDE = -3.7025
SOLO_LEAD_TIME_MINS = 155   # Poole -> Rest Bay + prep
GROUP_LEAD_TIME_MINS = 165  # Poole -> Corfe Mullen -> Rest Bay + prep
CORFE_PICKUP_OFFSET_MINS = 15

# Telegram & Gemini Secrets
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# 2. GOOGLE CALENDAR FETCHER
# ==========================================
def fetch_calendar_events():
    """Reads the next 7 days of events using service account credentials."""
    service_account_info = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    try:
        if service_account_info:
            # Loaded directly from environment secret string
            creds_dict = json.loads(service_account_info)
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
        elif os.path.exists("service_account.json"):
            # Loaded from local file fallback
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
        else:
            print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON missing and service_account.json not found. Skipping calendar.")
            return []

        service = build("calendar", "v3", credentials=creds)

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=7)).isoformat() + "Z"

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        extracted = []
        for item in events_result.get("items", []):
            start = item["start"].get("dateTime", item["start"].get("date"))
            end = item["end"].get("dateTime", item["end"].get("date"))
            extracted.append({
                "summary": item.get("summary", "Busy"),
                "start": start,
                "end": end
            })
        return extracted
    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []

# ==========================================
# 3. SURF & WEATHER FETCHER
# ==========================================
def fetch_surf_summary():
    """Fetches Open-Meteo forecast data for Rest Bay."""
    try:
        url_marine = f"https://marine-api.open-meteo.com/v1/marine?latitude={LATITUDE}&longitude={LONGITUDE}&hourly=wave_height,wave_period,wave_direction&timezone=Europe/London&forecast_days=7"
        url_weather = f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&hourly=wind_speed_10m,wind_direction_10m&timezone=Europe/London&forecast_days=7"

        res_m = requests.get(url_marine, timeout=10).json()
        res_w = requests.get(url_weather, timeout=10).json()

        today_wave = res_m["hourly"]["wave_height"][12] if "hourly" in res_m and "wave_height" in res_m["hourly"] else 0
        today_period = res_m["hourly"]["wave_period"][12] if "hourly" in res_m and "wave_period" in res_m["hourly"] else 0
        today_wind = res_w["hourly"]["wind_speed_10m"][12] if "hourly" in res_w and "wind_speed_10m" in res_w["hourly"] else 0
        
        return {
            "noon_wave_m": today_wave,
            "noon_wave_ft": round(today_wave * 3.28084, 1) if today_wave else 0,
            "noon_period": today_period,
            "noon_wind_kmh": today_wind
        }
    except Exception as e:
        print(f"Error fetching surf: {e}")
        return {}

# ==========================================
# 4. AI PROMPT ENGINE (GEMINI)
# ==========================================
def generate_ai_briefing(calendar_events, surf_data):
    """Sends schedule, surf data, and master prompt to Gemini API."""
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY missing.")
        return "⚠️ Could not generate briefing: GEMINI_API_KEY missing."

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    events_json_str = json.dumps(calendar_events, indent=2)
    surf_json_str = json.dumps(surf_data, indent=2)
    is_sunday = datetime.now().weekday() == 6

    prompt = f"""
You are an executive assistant and sports performance assistant. 
Analyze the user's schedule and surf conditions to produce a clear Telegram update.

CALENDAR EVENTS (NEXT 7 DAYS):
{events_json_str}

SURF DATA (REST BAY TODAY AT NOON):
{surf_json_str}

DAY OF WEEK: {"Sunday" if is_sunday else "Workday/Weekday"}

RULES FOR OUTPUT:
1. TODAY'S SCHEDULE & CONFLICTS:
   - Highlight today's events.
   - Flag conflicts (e.g., Monday 18:00 Tennis vs Tag Rugby). Suggest which to prioritize based on match schedules.
   - Point out optimal 30-min windows for packing if weekend travel is detected.

2. SURF OUTLOOK:
   - Summarize Rest Bay conditions based on provided data.

3. MEAL & FUELING RECOMMENDATION:
   - Give dinner timing and quick meal recommendations based on sports timings (e.g. high-protein post-workout options for 20:00+ finishes).

4. SUNDAY GROCERY BONUS (ONLY INCLUDE IF TODAY IS SUNDAY):
   - Provide an itemized grocery shopping list categorized by aisle (Produce, Protein, Dairy, Pantry) based on the upcoming week's schedule constraints.

Keep the formatting clean with bold headings and emojis for Telegram Markdown.
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )
    return response.text

# ==========================================
# 5. TELEGRAM DISPATCHER
# ==========================================
def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram credentials missing.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    print("Fetching Calendar...")
    calendar_events = fetch_calendar_events()

    print("Fetching Surf Data...")
    surf_data = fetch_surf_summary()

    print("Generating AI Briefing...")
    briefing = generate_ai_briefing(calendar_events, surf_data)

    print("Sending to Telegram...")
    send_telegram_message(briefing)
    print("Done!")

if __name__ == "__main__":
    main()
