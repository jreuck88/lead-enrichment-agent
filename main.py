import os
import time
import re
import gspread
import openai
import serpapi
from dotenv import load_dotenv
from datetime import datetime
from gspread.exceptions import APIError

# Load environment variables
load_dotenv()

SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT") or "/etc/secrets/service_account.json"

# Authenticate clients
openai.api_key = OPENAI_API_KEY
gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
sheet = gc.open_by_url(SHEET_URL)
agent_tab = sheet.worksheet("Agent")
dashboard_tab = None
try:
    dashboard_tab = sheet.worksheet("Dashboard")
except:
    dashboard_tab = sheet.add_worksheet("Dashboard", rows=10, cols=2)

# Constants
START_ROW = 10
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds

# Markers
GENERIC_NAMES = ["john doe", "jon doe", "jane doe", "n/a"]

# Utilities
def should_enrich(cell_value):
    if not cell_value or cell_value.strip().lower() in ("manual search required", *GENERIC_NAMES):
        return True
    return False

def safe_update_cell(ws, row, col, value):
    try:
        ws.update_cell(row, col, value)
    except APIError as e:
        print(f"API Error on update_cell({row},{col}): {e}")
        time.sleep(RETRY_DELAY)
        ws.update_cell(row, col, value)

def log_progress(text):
    print(f"🔍 {text}")
    dashboard_tab.update("B2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dashboard_tab.update("B3", text)

# Enrichment

def enrich_row(row_num, row):
    company = row[0]
    log_progress(f"Enriching: {company}")

    enriched_data = []
    for i, value in enumerate(row):
        if should_enrich(value):
            prompt = f"Find accurate {agent_tab.row_values(1)[i]} for the brand '{company}' using the brand's website and digital footprint."
            retries = 0
            while retries < MAX_RETRIES:
                try:
                    completion = openai.ChatCompletion.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.5,
                    )
                    enriched_value = completion.choices[0].message.content.strip()
                    enriched_data.append((i + 1, enriched_value))
                    break
                except Exception as e:
                    retries += 1
                    print(f"Retry {retries}/{MAX_RETRIES} for {company}: {e}")
                    time.sleep(RETRY_DELAY * retries)
        else:
            enriched_data.append((i + 1, value))

    for col, new_val in enriched_data:
        safe_update_cell(agent_tab, row_num, col, new_val)

    # Mark as enriched
    status_col = 16
    agent_tab.update_cell(row_num, status_col, f"✅ Enriched via GPT on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    time.sleep(1.5)  # rate limiting

# Main

def main():
    all_rows = agent_tab.get_all_values()[START_ROW - 1:]
    for i, row in enumerate(all_rows):
        if row[0]:
            enrich_row(i + START_ROW, row)

    dashboard_tab.update("B2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dashboard_tab.update("B3", "✔️ Finished")

if __name__ == '__main__':
    main()
