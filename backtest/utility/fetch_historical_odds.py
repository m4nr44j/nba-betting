"""
Fetch historical NBA odds from The Odds API.

NOTE: All date/time operations run as if in US Eastern timezone, regardless of
the actual system timezone. This ensures consistent behavior when running from
different locations (e.g., India).
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytz
import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

EASTERN_TZ = pytz.timezone('US/Eastern')

def get_eastern_now():
    """Get current datetime in Eastern timezone."""
    return datetime.now(EASTERN_TZ)

API_KEY = "3b88f3f50771d9dddb421a0dd0cc31a8"
BASE_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/events"

GAME_IDS_TIME_SUFFIX = "T16:30:00Z"

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


def game_ids(date: str, commence_time_to: str):
    """Get game IDs for a given date."""
    formatted_time = (
        commence_time_to.replace("+00:00", "Z")
        if "+00:00" in commence_time_to
        else commence_time_to
    )

    url = (
        f"{BASE_URL}?apiKey={API_KEY}"
        f"&date={date}{GAME_IDS_TIME_SUFFIX}"
        f"&regions=us&oddsFormat=american"
        f"&commenceTimeTo={formatted_time}"
    )

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            payload = response.json()
            games = payload.get("data", [])
            return [(g["id"], g["commence_time"]) for g in games]
        else:
            print(f"Failed to get games for {date}: {response.status_code} - {response.text}")
            return []
    except requests.RequestException as e:
        print(f"Request failed for {date}: {e}")
        return []


def get_odds(game_id: str, market_types, date_for_url: str):
    """Get odds for a specific game at a specific date/time."""
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
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"Failed {market_type} for game {game_id}: {resp.status_code} – {resp.text}")
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
            print(f"Request failed for {market_type} (game {game_id}): {e}")

    return market_data


def collect_all_odds(game_ids, date_for_url: str):
    """Collect odds for all games and all market types."""
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


def merge_bookmaker_data(data1: dict, data2: dict) -> dict:
    """Merge two bookmaker data dictionaries, combining lists for each market type."""
    merged = {}
    
    all_bookmakers = set(data1.keys()) | set(data2.keys())
    
    market_types = set()
    for bookmaker_data in list(data1.values()) + list(data2.values()):
        market_types.update(bookmaker_data.keys())
    
    for bookmaker in all_bookmakers:
        merged[bookmaker] = {}
        
        for market_type in market_types:
            merged_list = []
            
            if bookmaker in data1 and market_type in data1[bookmaker]:
                merged_list.extend(data1[bookmaker][market_type])
            
            if bookmaker in data2 and market_type in data2[bookmaker]:
                merged_list.extend(data2[bookmaker][market_type])
            
            merged[bookmaker][market_type] = merged_list
    
    return merged


def fetch_odds_for_date(date: datetime, hours_before: int = 1):
    """
    Fetch odds for a single date, N hours before the first game.
    For Sundays, also fetches 1 hour before the last game and merges results.
    
    Args:
        date: datetime object representing the date (timezone-naive, treated as Eastern)
        hours_before: Number of hours before the first game to fetch odds (default: 1)
    """
    ymd_str = date.strftime("%Y-%m-%d")
    mm_dd_str = date.strftime("%m_%d")
    
    print(f"\nProcessing {ymd_str}...")
    
    next_day = date + timedelta(days=1)
    next_day_at_5am_et = next_day.replace(hour=5, minute=0, second=0, microsecond=0)
    next_day_at_5am_et = EASTERN_TZ.localize(next_day_at_5am_et)
    next_day_at_5am_utc = next_day_at_5am_et.astimezone(pytz.utc)
    commence_time_to = next_day_at_5am_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    id_times = game_ids(ymd_str, commence_time_to)
    if not id_times:
        print(f"No games found for {ymd_str}")
        return False
    
    id_times.sort(key=lambda x: x[1])
    first_game_time = id_times[0][1]
    last_game_time = id_times[-1][1]
    
    first_game_dt = _parse_date(first_game_time)
    last_game_dt = _parse_date(last_game_time)
    
    if first_game_dt.tzinfo is None:
        first_game_dt = pytz.utc.localize(first_game_dt)
    else:
        first_game_dt = first_game_dt.astimezone(pytz.utc)
    
    if last_game_dt.tzinfo is None:
        last_game_dt = pytz.utc.localize(last_game_dt)
    else:
        last_game_dt = last_game_dt.astimezone(pytz.utc)
    
    first_game_dt_et = first_game_dt.astimezone(EASTERN_TZ)
    last_game_dt_et = last_game_dt.astimezone(EASTERN_TZ)
    
    is_sunday = date.weekday() == 6
    
    time_before_first_dt = first_game_dt - timedelta(hours=hours_before)
    time_before_first_dt_et = time_before_first_dt.astimezone(EASTERN_TZ)
    date_for_url_first = time_before_first_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    print(f"First game: {first_game_time} UTC = {first_game_dt_et.strftime('%Y-%m-%d %H:%M:%S %Z')} ET")
    print(f"Last game: {last_game_time} UTC = {last_game_dt_et.strftime('%Y-%m-%d %H:%M:%S %Z')} ET")
    
    game_id_list = [gid for gid, _ in id_times]
    print(f"Fetching odds from: {date_for_url_first} UTC = {time_before_first_dt_et.strftime('%Y-%m-%d %H:%M:%S %Z')} ET ({hours_before} hour{'s' if hours_before != 1 else ''} before first game)")
    all_bookmakers_data = collect_all_odds(game_id_list, date_for_url_first)
    
    if is_sunday and len(id_times) > 1:
        time_after_first_dt = first_game_dt + timedelta(hours=4)
        time_after_first_dt_et = time_after_first_dt.astimezone(EASTERN_TZ)
        date_for_url_second = time_after_first_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        games_not_started = []
        for gid, commence_time in id_times:
            game_dt = _parse_date(commence_time)
            if game_dt.tzinfo is None:
                game_dt = pytz.utc.localize(game_dt)
            else:
                game_dt = game_dt.astimezone(pytz.utc)
            
            if game_dt > time_after_first_dt:
                games_not_started.append(gid)
        
        if games_not_started:
            print(f"\nSunday detected with multiple games - also fetching odds from: {date_for_url_second} UTC = {time_after_first_dt_et.strftime('%Y-%m-%d %H:%M:%S %Z')} ET (4 hours after first game starts)")
            print(f"Fetching odds for {len(games_not_started)} game(s) that haven't started yet...")
            second_fetch_data = collect_all_odds(games_not_started, date_for_url_second)
            
            print("Merging odds from both fetches...")
            all_bookmakers_data = merge_bookmaker_data(all_bookmakers_data, second_fetch_data)
        else:
            print(f"\nSunday detected but all games have already started by the second fetch time - skipping second fetch")
    
    output_dir = "backtest/historical_25-26"
    os.makedirs(output_dir, exist_ok=True)
    
    hist_path = os.path.join(output_dir, f"{mm_dd_str}_props.json")
    with open(hist_path, "w") as f:
        json.dump(all_bookmakers_data, f, indent=4)
    
    print(f"\nSaved odds to {hist_path}")
    return True


def main(start_date_str: str = "2025-10-21", end_date_str: str = None):
    """
    Fetch historical odds starting from start_date_str.
    
    All dates are interpreted in Eastern timezone. If end_date_str is not provided,
    uses "today" in Eastern time, not local system time.
    """
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    else:
        eastern_now = get_eastern_now()
        eastern_date_only = eastern_now.date()
        end_date = datetime(eastern_date_only.year, eastern_date_only.month, eastern_date_only.day) - timedelta(days=1)
        end_date_str = end_date.strftime("%Y-%m-%d")
        print(f"Using Eastern timezone - today is {end_date_str} ET")
    
    current_date = start_date
    successful = 0
    failed = 0
    
    print(f"Fetching historical odds from {start_date_str} to {end_date_str}")
    print("=" * 60)
    
    while current_date <= end_date:
        success = fetch_odds_for_date(current_date)
        if success:
            successful += 1
        else:
            failed += 1
        
        current_date += timedelta(days=1)
    
    print("\n" + "=" * 60)
    print(f"Complete! Successful: {successful}, Failed: {failed}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch historical NBA odds")
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-10-21",
        help="Start date in YYYY-MM-DD format (default: 2025-10-21)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (default: today)",
    )
    
    args = parser.parse_args()
    main(args.start_date, args.end_date)
