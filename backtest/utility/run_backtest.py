import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from config import (
    BACKTEST_HISTORICAL_24_25_DIR,
    BACKTEST_HISTORICAL_25_26_DIR,
    BACKTEST_INJURY_REPORTS_25_26_DIR,
    CSV_ALL_DATA_FILE,
    CSV_ALL_DATA_PROCESSED_FILE,
    CSV_NEW_DATA_FILE,
    CSV_OUTPUT_FILE,
    CSV_SQL_DATA_FILE,
    EASTERN_TIMEZONE,
    GAME_IDS_TIME_SUFFIX,
    JSON_INJURY_FILE,
    JSON_PROPS_FILE,
    NBA_TEAMS,
    PDF_DOWNLOAD_DIR,
    ODDS_API_BOOKMAKER,
    ODDS_API_FORMAT,
    ODDS_API_HISTORICAL_BASE_URL,
    ODDS_API_REGIONS,
    USE_2025_26_SEASON,
    get_market_types,
)
from utility.get_injury_by_date import get
from utility.initialize_database import create_database
from utility.process_props import props
from .backtest_pipeline import run_pipeline

load_dotenv()

DATE = "2025-03-14"

API_KEY = os.getenv("ODDS_KEY")
BASE_URL = ODDS_API_HISTORICAL_BASE_URL
EASTERN_TZ = pytz.timezone(EASTERN_TIMEZONE)

BACKTEST_24_25_PATH = Path(BACKTEST_HISTORICAL_24_25_DIR)
BACKTEST_25_26_PATH = Path(BACKTEST_HISTORICAL_25_26_DIR)
INJURY_REPORTS_25_26_PATH = Path(BACKTEST_INJURY_REPORTS_25_26_DIR)
PDF_DOWNLOAD_PATH = Path(PDF_DOWNLOAD_DIR)


def _parse_date(date_str: str) -> datetime:
    if "T" in date_str:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return datetime.strptime(date_str, "%Y-%m-%d")


def _resolve_hist_dir(hist_dir: str | None) -> Path:
    if hist_dir:
        return Path(hist_dir)
    default_dir = BACKTEST_25_26_PATH if USE_2025_26_SEASON else BACKTEST_24_25_PATH
    return default_dir


def game_ids(commence_time_to: str):
    formatted_time = (
        commence_time_to.replace("+00:00", "Z")
        if "+00:00" in commence_time_to
        else commence_time_to
    )

    url = (
        f"{BASE_URL}?apiKey={API_KEY}"
        f"&date={DATE}{GAME_IDS_TIME_SUFFIX}"
        f"&regions={ODDS_API_REGIONS}&oddsFormat={ODDS_API_FORMAT}"
        f"&commenceTimeTo={formatted_time}"
    )

    try:
        response = requests.get(url, timeout=3)

        if response.status_code == 200:
            payload = response.json()
            games = payload.get("data", [])
            return [(g["id"], g["commence_time"]) for g in games]
        else:
            print("Failed:", response.text)
            return []
    except requests.RequestException as e:
        print("Request failed:", e)
        return []


def get_odds(game_id: str, market_types, date_for_url: str):
    market_data: dict[str, dict[str, list]] = {}

    for market_type in market_types:
        url = (
            f"{BASE_URL}/{game_id}/odds"
            f"?apiKey={API_KEY}"
            f"&markets={market_type}"
            f"&oddsFormat={ODDS_API_FORMAT}"
            f"&bookmakers={ODDS_API_BOOKMAKER}"
            f"&date={date_for_url}"
        )

        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code != 200:
                print(f"Failed {market_type}: {resp.status_code} – {resp.text}")
                continue

            payload = resp.json()
            event = payload.get("data", {})

            for bookmaker in event.get("bookmakers", []):
                title = bookmaker["title"]
                market_data.setdefault(title, {}).setdefault(market_type, [])

                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        market_data[title][market_type].append(
                            {
                                "description": outcome["description"],
                                "home_team": NBA_TEAMS.get(event["home_team"]),
                                "away_team": NBA_TEAMS.get(event["away_team"]),
                                "name": outcome["name"],
                                "point": outcome.get("point"),
                                "price": outcome["price"],
                                "game_id": game_id,
                            }
                        )

        except requests.RequestException as e:
            print(f"Request failed for {market_type}: {e}")

    return market_data


def collect_all_odds(game_ids, date_for_url: str):
    market_types = get_market_types(use_alternate=True)
    all_bookmakers_data = {}

    for game_id in game_ids:
        game_odds = get_odds(game_id, market_types, date_for_url)
        for bookmaker, markets in game_odds.items():
            if bookmaker not in all_bookmakers_data:
                all_bookmakers_data[bookmaker] = {
                    market_type: [] for market_type in market_types
                }
            for market_type, data in markets.items():
                all_bookmakers_data[bookmaker][market_type].extend(data)
    return all_bookmakers_data


def data_update():

    try:
        df_full = pd.read_csv(CSV_ALL_DATA_FILE, low_memory=False)
    except Exception as e:
        print(f"Error reading {CSV_ALL_DATA_FILE}: {e}")
        return

    target_dt = _parse_date(DATE).date()
    target_date_str = target_dt.strftime("%Y-%m-%d")

    if not os.path.exists(CSV_SQL_DATA_FILE):
        try:
            df_initial = df_full[df_full["Date"] < target_date_str]
            df_initial.to_csv(CSV_ALL_DATA_PROCESSED_FILE, index=False)
            create_database()
        except Exception as e:
            print(f"Error during initial database creation: {e}")
        return

    try:
        df_sql = pd.read_csv(CSV_SQL_DATA_FILE)
        date_col = (
            "date"
            if "date" in df_sql.columns
            else ("Date" if "Date" in df_sql.columns else None)
        )
        if date_col is None:
            return
        df_sql[date_col] = pd.to_datetime(df_sql[date_col], errors="coerce")
        last_date_in_db = df_sql[date_col].max().date()
    except Exception as e:
        print(f"Error reading {CSV_SQL_DATA_FILE} to determine last date: {e}")
        return

    start_dt = last_date_in_db + timedelta(days=1)
    end_dt = target_dt - timedelta(days=1)

    if start_dt > end_dt:
        return

    df_full["Date_dt"] = pd.to_datetime(df_full["Date"], errors="coerce")
    mask = (df_full["Date_dt"] >= pd.Timestamp(start_dt)) & (
        df_full["Date_dt"] <= pd.Timestamp(end_dt)
    )
    df_incremental = df_full[mask].drop(columns=["Date_dt"])

    if df_incremental.empty:
        return

    df_incremental.to_csv(CSV_NEW_DATA_FILE, index=False)

    run_pipeline()


def run(
    date: str | None = None,
    get_odds: bool = True,
    injury_time: str | None = None,
    hist_dir: str | None = None,
):

    global DATE

    if date:
        DATE = date

    data_update()

    date_obj = _parse_date(DATE)
    ymd_str = date_obj.strftime("%Y-%m-%d")
    mm_dd_str = date_obj.strftime("%m_%d")

    resolved_hist_dir = _resolve_hist_dir(hist_dir)
    resolved_hist_dir.mkdir(parents=True, exist_ok=True)
    resolved_hist_dir_abs = resolved_hist_dir.resolve()
    backtest_25_26_abs = BACKTEST_25_26_PATH.resolve()
    use_local_injury_reports = resolved_hist_dir_abs == backtest_25_26_abs

    injury_reports_dir = resolved_hist_dir / "injury_reports"
    if use_local_injury_reports:
        injury_reports_dir.mkdir(parents=True, exist_ok=True)

    if get_odds:
        tomorrow = date_obj + timedelta(days=1)
        tomorrow_at_5am = tomorrow.replace(hour=5, minute=0, second=0, microsecond=0)
        commence_time_to = tomorrow_at_5am.strftime("%Y-%m-%dT%H:%M:%SZ")
        id_times = game_ids(commence_time_to)
        if not id_times:
            return
        id_times.sort(key=lambda x: x[1])
        first_game_time = id_times[0][1]
        first_game_dt = _parse_date(first_game_time)

        one_hour_before = first_game_dt - timedelta(hours=1)

        if one_hour_before.tzinfo is None:
            one_hour_before = pytz.utc.localize(one_hour_before)

        one_hour_before_et = one_hour_before.astimezone(EASTERN_TZ)

        hour_24 = one_hour_before_et.hour
        if hour_24 == 0:
            time_str = "12AM"
        elif hour_24 < 12:
            time_str = f"{hour_24:02d}AM"
        elif hour_24 == 12:
            time_str = "12PM"
        else:
            time_str = f"{hour_24 - 12:02d}PM"
        get(ymd_str, time_str)

        if use_local_injury_reports:
            pdf_filename = f"Injury-Report_{ymd_str}.pdf"
            downloaded_pdf = PDF_DOWNLOAD_PATH / pdf_filename
            if downloaded_pdf.exists():
                shutil.copyfile(downloaded_pdf, injury_reports_dir / pdf_filename)

        one_hour_before_dt = first_game_dt - timedelta(minutes=30)
        date_for_url = one_hour_before_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        game_id_list = [gid for gid, _ in id_times]
        all_bookmakers_data = collect_all_odds(game_id_list, date_for_url)

        hist_path = resolved_hist_dir / f"{mm_dd_str}_props.json"
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(all_bookmakers_data, f, indent=4)
    else:
        time_str = injury_time if injury_time else "12PM"
        local_pdf_dir = str(injury_reports_dir) if use_local_injury_reports else None
        get(ymd_str, time_str, local_pdf_dir=local_pdf_dir)

    props(mm_dd_str, hist_dir=str(resolved_hist_dir))


if __name__ == "__main__":
    run()
