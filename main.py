# GPT-Powered Lead Enrichment Agent with Google Sheet Dashboard

import os
import time
import openai
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

# --- API KEYS ---
openai.api_key = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(os.getenv("GOOGLE_SHEET_URL"))
agent_tab = sheet.worksheet("Agent")

# --- Parameters ---
START_ROW = 10
MAX_ROWS = 25

# --- Enrichment Function ---
def enrich_lead(company_name):
    print(f"\n🔍 Enriching: {company_name}")
    serp_url = f"https://serpapi.com/search.json?q={company_name}+official+site&api_key={SERPAPI_KEY}"
    serp_response = requests.get(serp_url).json()
    urls = [r.get("link") for r in serp_response.get("organic_results", []) if r.get("link")]
    if not urls:
        return {"Website": "Manual search required"}

    top_sites = "\n".join(urls[:3])

    prompt = f"""
    You are a smart research assistant. Analyze the websites below and extract details for the company:

    Company Name: {company_name}
    Websites:
    {top_sites}

    Return:
    - Company Email
    - Location
    - Best Point of Contact (name + role)
    - Email of POC
    - Company LinkedIn
    - Company Instagram
    - Company Services
    - Value Prop / Why a good fit for outdoor brand photographer
    - Company Size (employees)
    - Annual Revenue (if available)
    - Lead Score (1-100)
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    content = response["choices"][0]["message"]["content"]
    return parse_gpt_response(content)

# --- Parse GPT Output ---
def parse_gpt_response(text):
    fields = [
        "Company Email", "Location", "Best Point of Contact", "Email of POC",
        "Company LinkedIn", "Company Instagram", "Company Services",
        "Value Prop", "Company Size", "Annual Revenue", "Lead Score"
    ]
    result = {}
    for field in fields:
        if field in text:
            try:
                val = text.split(f"{field}:")[1].split("\n")[0].strip()
                result[field] = val if val else "Manual search required"
            except:
                result[field] = "Manual search required"
        else:
            result[field] = "Manual search required"
    return result

# --- Update Agent Sheet Row ---
def update_sheet_row(row_num, data):
    col_map = {
        "Company Email": 2, "Location": 3, "Best Point of Contact": 4,
        "Email of POC": 5, "Company LinkedIn": 6, "Company Instagram": 7,
        "Company Services": 8, "Value Prop": 9, "Company Size": 10,
        "Annual Revenue": 11, "Lead Score": 12
    }
    for key, col in col_map.items():
        current = agent_tab.cell(row_num, col).value
        if current in ["", "Manual search required", None]:
            agent_tab.update_cell(row_num, col, data.get(key, "Manual search required"))
            if data.get(key) == "Manual search required":
                agent_tab.format(gspread.utils.rowcol_to_a1(row_num, col), {"backgroundColor": {"red": 0.105, "green": 0.839, "blue": 0.576}})

# --- Update Dashboard Tab ---
def update_dashboard():
    try:
        dashboard = sheet.worksheet("Dashboard")
    except:
        dashboard = sheet.add_worksheet(title="Dashboard", rows="20", cols="6")

    all_data = agent_tab.get_all_values()[1:]  # skip header
    total = len(all_data)
    enriched = sum(1 for row in all_data if any(val.strip() and val != "Manual search required" for val in row[1:]))
    manual_count = sum(row.count("Manual search required") for row in all_data)

    scores = []
    for row in all_data:
        try:
            score = int(row[11])
            scores.append(score)
        except:
            pass

    avg_score = round(sum(scores)/len(scores), 1) if scores else "N/A"
    high_score = sum(1 for s in scores if s >= 90)
    mid_score = sum(1 for s in scores if 70 <= s < 90)
    low_score = sum(1 for s in scores if s < 70)

    dashboard.update("A1", [
        ["Metric", "Value"],
        ["Total Companies", total],
        ["Leads Enriched", enriched],
        ["Manual Search Required", manual_count],
        ["Average Lead Score", avg_score],
        ["Score 90+", high_score],
        ["Score 70–89", mid_score],
        ["Score < 70", low_score],
    ])

# --- Main Execution ---
def main():
    data = agent_tab.get_all_values()
    for i in range(START_ROW - 1, min(len(data), START_ROW - 1 + MAX_ROWS)):
        company_name = data[i][0]
        if not company_name:
            continue
        enrichment = enrich_lead(company_name)
        update_sheet_row(i + 1, enrichment)
        time.sleep(1.5)

    update_dashboard()

if __name__ == "__main__":
    main()
