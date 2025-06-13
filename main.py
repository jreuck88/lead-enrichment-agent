import os
import time
import openai
import gspread
from datetime import datetime
from dotenv import load_dotenv
from gspread.exceptions import APIError

# Load credentials
load_dotenv()
client = gspread.service_account(filename=os.getenv("GOOGLE_CREDENTIALS"))
sheet = client.open_by_url(os.getenv("GOOGLE_SHEET_URL"))
agent_tab = sheet.worksheet("Agent")
dashboard_tab = sheet.worksheet("Dashboard")

# Settings
WRITE_DELAY = 3  # seconds between each row write
MAX_RETRIES = 5
SKIP_MARKER = "Manual search required"
GENERIC_NAMES = ["john doe", "jon doe", "jane doe"]
ENRICH_NOTE = "✅ Enriched via GPT"


# === Utilities ===
def safe_update(range_name, values):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            agent_tab.update(range_name, values)
            time.sleep(WRITE_DELAY)
            return True
        except APIError as e:
            if "Quota exceeded" in str(e):
                wait_time = 15 + (retries * 5)
                print(f"Quota limit hit. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                retries += 1
            else:
                raise e
    return False


def row_needs_enrichment(row):
    critical_columns = [1, 2, 4, 7, 8, 9, 10]  # B, C, E, H, I, J, K
    for col in critical_columns:
        if len(row) <= col:
            return True
        val = row[col].strip().lower()
        if not val or val == SKIP_MARKER.lower() or any(name in val for name in GENERIC_NAMES):
            return True
    return False


def update_progress(count, total):
    try:
        dashboard_tab.update("B2", f"Last Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        dashboard_tab.update("B3", f"{count} of {total} rows updated")
    except Exception as e:
        print(f"Failed to update dashboard: {e}")


# === Core Enrichment Logic ===
def enrich_row_data(company_name, website):
    prompt = f"""
You are helping a commercial photographer who specializes in outdoor lifestyle, headshot, and product photography. Based on the brand below, analyze whether they would be a good fit for a photography partnership.

Brand: {company_name}
Website: {website}

Return the following:
1. What does the brand do?
2. Who is the best person to contact? (job title or name if possible — no placeholders like John Doe)
3. Why would this brand benefit from working with this photographer?
4. Assign a lead score (1-100) based on alignment with outdoor focus, visual storytelling needs, and growth potential.
"""
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content


def parse_and_write(row_num, company_name, website):
    enriched = enrich_row_data(company_name, website)
    enriched += f"\n\n{ENRICH_NOTE} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    target_range = f"D{row_num}"  # Example target column for enrichment output
    safe_update(f"Agent!{target_range}", [[enriched]])


# === Main ===
def main():
    data = agent_tab.get_all_values()
    header = data[0]
    rows = data[1:]  # Skip header

    total = len(rows)
    enriched_count = 0

    for i, row in enumerate(rows):
        row_num = i + 2

        if row_needs_enrichment(row):
            company_name = row[0] if len(row) > 0 else ""
            website = row[7] if len(row) > 7 else ""
            print(f"\n
