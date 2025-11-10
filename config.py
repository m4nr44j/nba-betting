import os
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).parent

CSV_OUTPUT_FILE = "csv/output.csv"
CSV_ALL_DATA_FILE = "csv/all_data_full.csv"
CSV_ALL_DATA_PROCESSED_FILE = "csv/all_data.csv"
CSV_MODIFIED_DATA_FILE = "csv/modified_data.csv"
CSV_NEW_DATA_FILE = "csv/new_data.csv"
CSV_SQL_DATA_FILE = "csv/sql.csv"

JSON_INJURY_FILE = "json/injury.json"
JSON_PROPS_FILE = "json/props.json"
JSON_NBA_STATS_FILE = "json/nba_stats.json"
PDF_DOWNLOAD_DIR = "pdf"

TEXT_OUTPUT_FILE = "output.txt"

BACKTEST_HISTORICAL_24_25_DIR = "backtest/historical_24-25"
BACKTEST_HISTORICAL_25_26_DIR = "backtest/historical_25-26"
BACKTEST_INJURY_REPORTS_25_26_DIR = "backtest/historical_25-26/injury_reports"

INJURY_FILE = JSON_INJURY_FILE
SQL_DATA_FILE = CSV_SQL_DATA_FILE
NBA_STATS_FILE = JSON_NBA_STATS_FILE

NBA_TEAMS: Dict[str, str] = {
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

MODEL_TYPE = "SOFT"

FEATURE_WEIGHTS: Dict[str, float] = {
    "mp": 2.5,
    "plus_minus": 1.8,
    "opp": 3.0,
    "teammates_points_G": 1.3,
    "teammates_points_F": 1.4,
    "teammates_points_C": 1.2,
    "teammates_rebounds_G": 1.1,
    "teammates_rebounds_F": 1.3,
    "teammates_rebounds_C": 1.5,
    "teammates_assists_G": 1.4,
    "teammates_assists_F": 1.2,
    "teammates_assists_C": 1.0,
    "opponents_points_G": 1.2,
    "opponents_points_F": 1.3,
    "opponents_points_C": 1.1,
    "opponents_rebounds_G": 1.1,
    "opponents_rebounds_F": 1.2,
    "opponents_rebounds_C": 1.4,
    "opponents_assists_G": 1.3,
    "opponents_assists_F": 1.1,
    "opponents_assists_C": 1.0,
    "teammates_turnovers_G": 1.2,
    "teammates_turnovers_F": 1.1,
    "teammates_turnovers_C": 1.0,
    "opponents_blocks_G": 1.1,
    "opponents_blocks_F": 1.2,
    "opponents_blocks_C": 1.4,
    "opponents_turnovers_G": 1.2,
    "opponents_turnovers_F": 1.1,
    "opponents_turnovers_C": 1.0,
}

MARKET_MAPPING: Dict[str, str] = {
    "player_points_alternate": "pts",
    "player_rebounds_alternate": "trb",
    "player_assists_alternate": "ast",
    "player_points_rebounds_alternate": "p_r",
    "player_points_assists_alternate": "p_a",
    "player_rebounds_assists_alternate": "a_r",
    "player_points_rebounds_assists_alternate": "p_r_a",
    "player_threes_alternate": "tpm",
}

MARKET_DISPLAY_MAPPING: Dict[str, str] = {
    "pts": "PTS",
    "trb": "REB",
    "ast": "AST",
    "p_r": "P+R",
    "p_a": "P+A",
    "p_r_a": "P+R+A",
    "a_r": "A+R",
}

FEATURES_TO_ANALYZE = ["pts", "trb", "ast", "p_r", "p_a", "a_r", "p_r_a"]

MARKET_TYPES_ALTERNATE = [
    "player_points_alternate",
    "player_rebounds_alternate",
    "player_assists_alternate",
    "player_points_rebounds_assists_alternate",
    "player_points_rebounds_alternate",
    "player_points_assists_alternate",
    "player_rebounds_assists_alternate",
]

MARKET_TYPES_STANDARD = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_points_rebounds_assists",
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
]

BANNED_PLAYERS = [
    "Brook Lopez",
    "Kyle Kuzma",
    "Jalen Duren",
    "Christian Braun",
    "Tyrese Haliburton",
    "Russell Westbrook",
    "Nick Richards",
    "Anthony Edwards",
]

PLAYER_NAME_CORRECTIONS: Dict[str, str] = {
    " Jr": " Jr.",
    "Jimmy Butler": "Jimmy Butler III",
    "Luka Doncic": "Luka Dončić",
    "Nikola Jokic": "Nikola Jokić",
    "Nikola Vucevic": "Nikola Vučević",
    "Jonas Valanciunas": "Jonas Valančiūnas",
    "Bojan Bogdanovic": "Bojan Bogdanović",
    "Dario Saric": "Dario Šarić",
    "Bogdan Bogdanovic": "Bogdan Bogdanović",
    "Karlo Matkovic": "Karlo Matković",
    "Boban Marjanovic": "Boban Marjanović",
    "Jusuf Nurkic": "Jusuf Nurkić",
    "Luka Samanic": "Luka Šamanić",
    "Nikola Jovic": "Nikola Jović",
    "Vasilije Micic": "Vasilije Micić",
    "Vit Krejci": "Vít Krejčí",
    "Tristan Vukcevic": "Tristan Vukčević",
}

CSV_FIELDNAMES = [
    "Player",
    "Market",
    "Predicted",
    "Buffer",
    "Line",
    "Rank",
    "Last Ten",
    "Odds",
    "Game",
]

CONSISTENCY_LIMIT = 300
MIN_MINUTES_FOR_CONSISTENCY = 8

SEASON_PHASE_THRESHOLD = 7

LOWEST_PRICE_THRESHOLD = -105
HIGHEST_PRICE_THRESHOLD = 120
MIN_PROP_LINE = 2.5

ERROR_THRESHOLDS = {
    "low": (0.0, 8.5, 2),
    "medium": (8.5, 18.5, 3),
    "high": (18.5, 30.5, 4),
    "very_high": (30.5, float("inf"), 6),
}

LAST_TEN_OVER_CHECK_LINES = {
    "high": (30.5, float("inf"), 3),
    "medium": (20.5, 30.5, 2),
    "low": (8.5, 20.5, 1),
    "very_low": (0.0, 8.5, 0),
}

TOP_PICKS_COUNT =  15

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/events"
ODDS_API_HISTORICAL_BASE_URL = (
    "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/events"
)

ODDS_API_REGIONS = "us"
ODDS_API_FORMAT = "american"
ODDS_API_BOOKMAKER = "fanduel"
ODDS_API_TIMEOUT = 10

GAME_IDS_TIME_SUFFIX = "T16:30:00Z"

EASTERN_TIMEZONE = "US/Eastern"

USE_ONE_HOUR_BEFORE_INJURY = True
USE_2025_26_SEASON = True

BACKTEST_HIST_DIR_24_25 = "backtest/historical_24-25"
BACKTEST_HIST_DIR_25_26 = "backtest/historical_25-26"

SEASON_START_MONTH = 10
SEASON_START_DAY = 21


def get_error_threshold(line: float) -> int:
    for key, (min_val, max_val, error) in ERROR_THRESHOLDS.items():
        if min_val <= line < max_val:
            return error
    return 7


def get_over_check_line(line: float) -> float:
    for key, (min_val, max_val, adjustment) in LAST_TEN_OVER_CHECK_LINES.items():
        if min_val <= line < max_val:
            return max(0, line - adjustment)
    return line


def get_historical_dir(season: str = "25-26") -> str:
    if season == "24-25":
        return BACKTEST_HISTORICAL_24_25_DIR
    return BACKTEST_HISTORICAL_25_26_DIR


def get_market_types(use_alternate: bool = True) -> list:
    if use_alternate:
        return MARKET_TYPES_ALTERNATE
    return MARKET_TYPES_STANDARD
