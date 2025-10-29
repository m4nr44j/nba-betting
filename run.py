import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytz
import requests
from dotenv import load_dotenv

from utility.get_injury_by_date import get as get_injury_by_date
from utility.pipeline import run_pipeline
from utility.process_props import process_props

load_dotenv()

USE_ONE_HOUR_BEFORE_INJURY = False

EASTERN_TZ = pytz.timezone('US/Eastern')

def get_eastern_now():
    return datetime.now(EASTERN_TZ)

API_KEY = os.getenv("ODDS_KEY")
BASE_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/events"


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


def game_ids(commence_time_to):
    url = f"{BASE_URL}?apiKey={API_KEY}&regions=us&oddsFormat=american&commenceTimeTo={commence_time_to}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return [(game["id"], game["commence_time"]) for game in response.json()]
        else:
            print(f"Failed to retrieve data: {response.status_code}")
            return []
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return []


def get_odds(game_id, market_types):
    market_data = {}
    for market_type in market_types:
        url = f"{BASE_URL}/{game_id}/odds?apiKey={API_KEY}&markets={market_type}&oddsFormat=american&bookmakers=fanduel"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                for bookmaker in data["bookmakers"]:
                    if bookmaker["title"] not in market_data:
                        market_data[bookmaker["title"]] = {}
                    if market_type not in market_data[bookmaker["title"]]:
                        market_data[bookmaker["title"]][market_type] = []
                    for market in bookmaker["markets"]:
                        for outcome in market["outcomes"]:
                            market_data[bookmaker["title"]][market_type].append(
                                {
                                    "description": outcome["description"],
                                    "home_team": nba_teams.get(data["home_team"]),
                                    "away_team": nba_teams.get(data["away_team"]),
                                    "name": outcome["name"],
                                    "point": outcome.get("point", None),
                                    "price": outcome["price"],
                                    "game_id": game_id,
                                }
                            )
            else:
                print(
                    f"Failed to retrieve data for market {market_type}: {response.status_code}"
                )
        except requests.RequestException as e:
            print(f"Request failed for market {market_type}: {e}")
            continue
    return market_data


def collect_all_odds(game_ids):
    market_types = [
        "player_points_alternate",
        "player_rebounds_alternate",
        "player_assists_alternate",
        "player_points_rebounds_assists_alternate",
        "player_points_rebounds_alternate",
        "player_points_assists_alternate",
        "player_rebounds_assists_alternate",
    ]
    # market_types = [
    #     "player_points",
    #     "player_rebounds",
    #     "player_assists",
    #     "player_points_rebounds_assists",
    #     "player_points_rebounds",
    #     "player_points_assists",
    #     "player_rebounds_assists",
    # ]
    all_bookmakers_data = {}

    for game_id in game_ids:
        game_odds = get_odds(game_id, market_types)
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
        df = pd.read_csv(SQL_DATA_FILE)
        if df.empty:
            print(f"Warning: {SQL_DATA_FILE} is empty. Skipping data update.")
            return
        
        date_column = pd.to_datetime(df["date"], errors="coerce").dt.date
        max_date_in_csv: datetime.date = date_column.max()
        
        if pd.isna(max_date_in_csv):
            print(f"Warning: No valid dates found in {SQL_DATA_FILE}. Skipping data update.")
            return
            
        next_day_to_process: datetime.date = max_date_in_csv + timedelta(days=1)
        eastern_now = get_eastern_now()
        yesterday: datetime.date = eastern_now.date() - timedelta(days=1)
    except FileNotFoundError:
        print(f"Error: {SQL_DATA_FILE} not found. Please run database initialization first.")
        return
    except pd.errors.EmptyDataError:
        print(f"Error: {SQL_DATA_FILE} is empty or corrupted.")
        return
    except Exception as e:
        print(f"Error reading {SQL_DATA_FILE}: {e}")
        return
    
    eastern_now = get_eastern_now()
    current_date = eastern_now.date()
    
    if current_date.month >= 10: 
        current_season_start = datetime(current_date.year, 10, 21).date()  
    else:  
        current_season_start = datetime(current_date.year - 1, 10, 21).date()
    
    if max_date_in_csv < current_season_start and current_date >= current_season_start:
        next_day_to_process = current_season_start
    
    if next_day_to_process <= yesterday:
        print(f"Running Pipeline from {next_day_to_process} to {yesterday}")
        run_pipeline(next_day_to_process)
    else:
        print("Data is up to date")


def load_injury_data(games, today_str, use_one_hour_before=True):

    if games and use_one_hour_before:
        first_game_time = games[0][1]
        first_game_dt = datetime.fromisoformat(first_game_time.replace("Z", "+00:00"))
        one_hour_before = first_game_dt - timedelta(hours=1)
        
        if one_hour_before.tzinfo is None:
            one_hour_before = one_hour_before.replace(tzinfo=timezone.utc)
        
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
    else:
        time_str = "06PM"
    
    get_injury_by_date(today_str, time_str)


def run(use_one_hour_before=True):
    data_update()
    
    eastern_now = get_eastern_now()
    today_eastern = eastern_now.replace(tzinfo=None)
    tomorrow = today_eastern + timedelta(days=1)
    tomorrow_at_5am = tomorrow.replace(hour=5, minute=0, second=0, microsecond=0)

    commence_time_to = tomorrow_at_5am.isoformat() + "Z"
    games = game_ids(commence_time_to)
    today_str = today_eastern.strftime("%Y-%m-%d")
    
    load_injury_data(games, today_str, use_one_hour_before)

    ids = [game_id for game_id, commence_time in games]
    props = (collect_all_odds(ids))
    
    os.makedirs("backtest/historical_25-26", exist_ok=True)
    
    with open(f"backtest/historical_25-26/{today_eastern.strftime("%m_%d")}_props.json", "w") as f:
        json.dump(process_props(props), f, indent=4)
    with open("json/props.json", "w") as f:
        json.dump(process_props(props), f, indent=4)

    cmd = [
        "python",
        "processor.py",
        "json/props.json",
        today_str,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    run(use_one_hour_before=USE_ONE_HOUR_BEFORE_INJURY)
