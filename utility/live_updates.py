import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import gspread
import requests
from dateutil import parser as dateparser
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_FILE = os.getenv("GOOGLE_API")

CSV_OUTPUT_FILENAME = "csv/output.csv"
TXT_OUTPUT_FILENAME = "output.txt"
NBA_JSON_FILE = "json/nba_stats.json"

CSV_CHECK_INTERVAL_SECONDS  = 15
TXT_CHECK_INTERVAL_SECONDS  = 15
NBA_CHECK_INTERVAL_SECONDS  = 30

TXT_TARGET_CELL   = "N2"
NBA_TARGET_RANGE  = (2, 200)
NBA_TARGET_COLUMN = "J"

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

def format_date(date_string: str) -> str:
    try:
        return f"{int(date_string[4:6])}/{int(date_string[6:])}/{date_string[2:4]}"
    except (IndexError, ValueError):
        return "Invalid Date"


def resolve_target_date(cli_str: str | None) -> str:
    if cli_str:
        try:
            dt = dateparser.parse(cli_str)
        except (ValueError, OverflowError):
            sys.exit(f"Invalid --date '{cli_str}'. Use YYYYMMDD or YYYY-MM-DD.")
        return dt.strftime("%Y%m%d")
    return (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y%m%d")


def get_current_sheet(client, sheet_id):
    worksheet = None
    sheet_name = "Unknown"
    try:
        now_utc = datetime.now(timezone.utc)
        target_time = now_utc - timedelta(hours=4)
        today_date_str = target_time.strftime("%Y%m%d")
        sheet_name = format_date(today_date_str)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        return worksheet, sheet_name
    except gspread.exceptions.WorksheetNotFound:
        return None, sheet_name
    except gspread.exceptions.APIError:
        return None, sheet_name
    except Exception:
        return None, sheet_name


def update_range_in_first_empty(worksheet, sheet_name, row_data):
    try:
        row_to_write = (row_data + [""] * 8)[:8]
        col_a_values = worksheet.col_values(1)
        next_row_index = len(col_a_values) + 1
        target_range = f"A{next_row_index}:H{next_row_index}"
        worksheet.update([row_to_write], target_range, value_input_option="USER_ENTERED")
        return True
    except (gspread.exceptions.APIError, Exception):
        return False


def update_google_sheet_cell(client, sheet_id, content_to_paste, target_cell):
    worksheet = None
    sheet_name = "Unknown"
    try:
        utc_now = datetime.now(timezone.utc)
        today_date_obj = (utc_now - timedelta(hours=10)).strftime("%Y%m%d")
        sheet_name = format_date(today_date_obj)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.update_acell(target_cell, content_to_paste)
        return True
    except (gspread.exceptions.WorksheetNotFound, gspread.exceptions.APIError, Exception):
        return False


def safe_int(value):
    if value in ("N/A", None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def safe_three_point(value):
    if value in ("N/A", None, ""):
        return None
    try:
        parts = str(value).split("-")
        return int(parts[0]) if parts else None
    except (ValueError, IndexError, TypeError):
        return None


def get_nba_game_event_ids(date_yyyymmdd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_yyyymmdd}"
    try:
        data = requests.get(url, timeout=10).json()
        return [event["id"] for event in data.get("events", []) if "id" in event]
    except (requests.RequestException, json.JSONDecodeError):
        return []


def get_nba_game_summary(event_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
    try:
        return requests.get(url, timeout=15).json()
    except (requests.RequestException, json.JSONDecodeError):
        return None


def extract_player_stats(summary_data):
    if not summary_data:
        return []
    players_out = []
    for team in summary_data.get("boxscore", {}).get("players", []):
        team_name = team.get("team", {}).get("displayName", "Unknown Team")
        for stat_group in team.get("statistics", []):
            labels = stat_group.get("labels", [])
            for athlete in stat_group.get("athletes", []):
                player_name = athlete.get("athlete", {}).get("displayName", "Unknown Player")
                
                player_name = player_name.replace('Jimmy Butler', 'Jimmy Butler III')
                player_name = player_name.replace('Ronald Holland II', 'Ron Holland')
                player_name = player_name.replace('Bub Carrington', 'Carlton Carrington')
                player_name = player_name.replace('Luka Doncic', 'Luka Dončić')
                player_name = player_name.replace('Nikola Jokic', 'Nikola Jokić')
                player_name = player_name.replace('Nikola Vucevic', 'Nikola Vučević')
                player_name = player_name.replace('Jonas Valanciunas', 'Jonas Valančiūnas')
                player_name = player_name.replace('Bojan Bogdanovic', 'Bojan Bogdanović')
                player_name = player_name.replace('Dario Saric', 'Dario Šarić')
                player_name = player_name.replace('Bogdan Bogdanovic', 'Bogdan Bogdanović')
                player_name = player_name.replace('Karlo Matkovic', 'Karlo Matković')
                player_name = player_name.replace('Boban Marjanovic', 'Boban Marjanović')
                player_name = player_name.replace('Jusuf Nurkic', 'Jusuf Nurkić')
                player_name = player_name.replace('Luka Samanic', 'Luka Šamanić')
                player_name = player_name.replace('Nikola Jovic', 'Nikola Jović')
                player_name = player_name.replace('Vasilije Micic', 'Vasilije Micić')
                player_name = player_name.replace('Vit Krejci', 'Vít Krejčí')
                player_name = player_name.replace('Tristan Vukcevic', 'Tristan Vukčević')
                
                raw_stats = athlete.get("stats", [])
                if len(raw_stats) != len(labels):
                    continue
                row = dict(zip(labels, raw_stats))
                pts = safe_int(row.get("PTS"))
                trb = safe_int(row.get("REB"))
                ast = safe_int(row.get("AST"))
                tpm = safe_three_point(row.get("3PT"))

                def combine(*vals):
                    nums = [v for v in vals if v is not None]
                    return "" if len(nums) != len(vals) else str(sum(nums))

                stats_proc = {
                    "pts": str(pts) if pts is not None else "",
                    "trb": str(trb) if trb is not None else "",
                    "ast": str(ast) if ast is not None else "",
                    "tpm": str(tpm) if tpm is not None else "",
                    "p_r": combine(pts, trb),
                    "p_a": combine(pts, ast),
                    "a_r": combine(ast, trb),
                    "p_r_a": combine(pts, trb, ast),
                }
                players_out.append({"Team": team_name, "Player": player_name, "Stats": stats_proc})
    return players_out


def updateGoogleSheetWithNBAStats(client, sheet_id, column_range, date_yyyymmdd,
                                  column_letter, json_stats_file):
    try:
        sheet = client.open_by_key(sheet_id).worksheet(format_date(date_yyyymmdd))
    except gspread.exceptions.WorksheetNotFound:
        return False

    try:
        with open(json_stats_file, encoding="utf-8") as fh:
            nba_data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    stats_lookup = {p["Player"]: p["Stats"] for p in nba_data}

    read_range = f"A{column_range[0]}:B{column_range[1]}"
    sheet_data = sheet.get_values(read_range)

    market_key_map = {
        "points": "pts", "rebounds": "trb", "assists": "ast",
        "steals": "Steals", "blocks": "Blocks", "turnovers": "Turnovers",
        "pts+rebs+asts": "p_r_a", "pts+rebs": "p_r",
        "pts+asts": "p_a", "asts+rebs": "a_r",
        "three pointers made": "tpm",
    }

    updates = []
    for row in sheet_data:
        if len(row) < 2:
            updates.append([""])
            continue
        player, market = row[0].strip(), row[1].strip().lower()
        key = market_key_map.get(market, market)
        val = stats_lookup.get(player, {}).get(key, "")
        updates.append([val])

    update_range = f"{column_letter}{column_range[0]}:{column_letter}{column_range[1]}"
    sheet.update(updates, update_range, value_input_option="USER_ENTERED")
    return True


def run_nba_update(client, sheet_id, date_yyyymmdd, range_rows,
                   column_letter, json_file):
    os.makedirs(os.path.dirname(json_file), exist_ok=True)
    all_stats = []
    for eid in get_nba_game_event_ids(date_yyyymmdd):
        summary = get_nba_game_summary(eid)
        all_stats.extend(extract_player_stats(summary)) if summary else None
        time.sleep(0.5)
    if not all_stats:
        return
    with open(json_file, "w", encoding="utf-8") as fh:
        json.dump(all_stats, fh, indent=2)
    updateGoogleSheetWithNBAStats(client, sheet_id, range_rows,
                                  date_yyyymmdd, column_letter, json_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push NBA stats to Google Sheets")
    parser.add_argument("--date", help="Target NBA date (YYYYMMDD or YYYY-MM-DD). "
                                       "Default: today minus 10h (UTC).")
    args = parser.parse_args()
    target_nba_date = resolve_target_date(args.date)

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gs_client = gspread.authorize(creds)
    except Exception as exc:
        sys.exit(f"Google auth failed: {exc}")

    last_run_time_nba = 0

    while True:
        now = time.time()

        if now - last_run_time_nba >= NBA_CHECK_INTERVAL_SECONDS:
            try:
                run_nba_update(gs_client, SHEET_ID, target_nba_date,
                               NBA_TARGET_RANGE, NBA_TARGET_COLUMN, NBA_JSON_FILE)
            except gspread.exceptions.APIError:
                time.sleep(NBA_CHECK_INTERVAL_SECONDS)
            last_run_time_nba = now

        try:
            time.sleep(5)
        except KeyboardInterrupt:
            break
