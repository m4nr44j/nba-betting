import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv
from utility.get_injury_by_date import get
from utility.initialize_database import create_database
from utility.process_props import props
from .backtest_pipeline import run_pipeline

load_dotenv()

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

DATE = "2025-03-14"

GAME_IDS_TIME_SUFFIX = "T16:30:00Z"

API_KEY = os.getenv("ODDS_KEY")
BASE_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/events"


CSV_OUTPUT_FILE = "csv/output.csv"
TEXT_OUTPUT_FILE = "output.txt"
INJURY_FILE = "json/injury.json"
SQL_DATA_FILE = "csv/sql.csv"


nba_teams = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


def _parse_date(date_str: str) -> datetime:
    if "T" in date_str:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return datetime.strptime(date_str, "%Y-%m-%d")


def game_ids(commence_time_to: str):
    formatted_time = (
        commence_time_to.replace("+00:00", "Z")
        if "+00:00" in commence_time_to
        else commence_time_to
    )

    url = (
        f"{BASE_URL}?apiKey={API_KEY}"
        f"&date={DATE}{GAME_IDS_TIME_SUFFIX}"
        f"&regions=us&oddsFormat=american"
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
            f"&oddsFormat=american"
            f"&bookmakers=fanduel"
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
                                "home_team": nba_teams.get(event["home_team"]),
                                "away_team": nba_teams.get(event["away_team"]),
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
    market_types = [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
        "player_rebounds_assists",
    ]
    market_types = [
        "player_points_alternate",
        "player_rebounds_alternate",
        "player_assists_alternate",
        "player_points_rebounds_assists_alternate",
        "player_points_rebounds_alternate",
        "player_points_assists_alternate",
        "player_rebounds_assists_alternate",
    ]
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
        df_full = pd.read_csv("csv/all_data_full.csv")
    except Exception as e:
        print(f"Error reading all_data_full.csv: {e}")
        return

    target_dt = _parse_date(DATE).date()
    target_date_str = target_dt.strftime("%Y-%m-%d")

    if not os.path.exists(SQL_DATA_FILE):
        try:
            df_initial = df_full[df_full["Date"] < target_date_str]
            df_initial.to_csv("csv/all_data.csv", index=False)
            create_database()
        except Exception as e:
            print(f"Error during initial database creation: {e}")
        return

    try:
        df_sql = pd.read_csv(SQL_DATA_FILE)
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
        print(f"Error reading sql.csv to determine last date: {e}")
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

    new_data_path = "csv/new_data.csv"
    df_incremental.to_csv(new_data_path, index=False)

    run_pipeline()


def run(date: str | None = None, get_odds=True):

    global DATE

    if date:
        DATE = date

    data_update()

    date_obj = _parse_date(DATE)
    ymd_str = date_obj.strftime("%Y-%m-%d")
    mm_dd_str = date_obj.strftime("%m_%d")

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

        eastern = pytz.timezone("US/Eastern")
        one_hour_before_et = one_hour_before.astimezone(eastern)

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

        one_hour_before_dt = first_game_dt - timedelta(minutes=30)
        date_for_url = one_hour_before_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        game_id_list = [gid for gid, _ in id_times]
        all_bookmakers_data = collect_all_odds(game_id_list, date_for_url)

        hist_path = f"backtest/historical/{mm_dd_str}_props.json"
        with open(hist_path, "w") as f:
            json.dump(all_bookmakers_data, f, indent=4)
    else:
        time_str = "12PM"
        get(ymd_str, time_str)

    props(mm_dd_str)


if __name__ == "__main__":
    run()
