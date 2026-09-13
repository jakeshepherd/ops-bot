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
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text
