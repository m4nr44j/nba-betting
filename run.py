import json
import os
import subprocess
from datetime import datetime, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

from utility.load_injuries import load_injuries
from utility.pipeline import run_pipeline
from utility.process_props import process_props

load_dotenv()

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
        url = f"{BASE_URL}/{game_id}/odds?apiKey={API_KEY}&markets={market_type}&oddsFormat=american&bookmakers=draftkings"
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
        "player_rebounds_assists",
    ]
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
    df = pd.read_csv(SQL_DATA_FILE)
    date_column = pd.to_datetime(df["date"], errors="coerce").dt.date
    max_date_in_csv: datetime.date = date_column.max()
    next_day_to_process: datetime.date = max_date_in_csv + timedelta(days=1)
    yesterday: datetime.date = datetime.now().date() - timedelta(days=1)
    if next_day_to_process <= yesterday:
        print("Running Pipeline")
        run_pipeline(next_day_to_process)
    else:
        print("Data is up to date")


def run():
    data_update()
    load_injuries()
    today = datetime.now()
    tomorrow = today + timedelta(days=2)
    tomorrow_at_5am = tomorrow.replace(hour=5, minute=0, second=0, microsecond=0)

    commence_time_to = tomorrow_at_5am.isoformat() + "Z"
    games = game_ids(commence_time_to)

    with open("json/props.json", "w") as f:
        ids = [game_id for game_id, commence_time in games]
        json.dump(process_props(collect_all_odds(ids)), f, indent=4)

    cmd = [
        "python",
        "processor.py",
        "json/props.json",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    run()
