import csv
import json
import math
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from tqdm import tqdm

from utility.consistency_test import get_consistency

MODEL_RECENCY = True

if MODEL_RECENCY:
    from models.soft_predictor import soft
else:
    from models.model_xgb import run_xgb

CSV_OUTPUT_FILE = "csv/output.csv"
TEXT_OUTPUT_FILE = "output.txt"
INJURY_FILE = "json/injury.json"
SQL_DATA_FILE = "csv/sql.csv"

FEATURE_WEIGHTS = {
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

MARKET_DISPLAY_MAPPING = {
    "pts": "PTS",
    "trb": "REB",
    "ast": "AST",
    "p_r": "P+R",
    "p_a": "P+A",
    "p_r_a": "P+R+A",
    "a_r": "A+R",
}
BANNED = [
    "Aaron Wiggins",
    "Isaiah Joe",
    "Nikola Vučević",
    "Brook Lopez",
    "Kyle Kuzma"
]
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


def get_season_phase_threshold(date_str=None):
    if date_str is None:
        date_obj = datetime.now()
    else:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"Warning: Invalid date format '{date_str}', using current date")
            date_obj = datetime.now()
    
    if (date_obj.month == 3 and date_obj.day >= 30) or date_obj.month in [4, 5, 6]:
        return 6
    
    return 7


def write_rows_to_csv(rows, filename=CSV_OUTPUT_FILE):
    try:
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    except IOError as e:
        print(f"Error writing to CSV {filename}: {e}")


def append_to_text(row, filename=TEXT_OUTPUT_FILE):
    player = row["Player"]
    line_value = row["Line"]
    game = row["Game"]
    market_key = row["Market"].lower()
    odds = row["Odds"]
    direction = "Over"
    market_formatted = MARKET_DISPLAY_MAPPING.get(market_key, market_key.upper())
    formatted_line = (
        f"{game}: {player} {direction} {line_value} {market_formatted} ({odds} FD)"
    )
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(formatted_line + "\n")
    except IOError as e:
        print(f"Error writing to text file {filename}: {e}")


def load_injury_report(filename=INJURY_FILE):
    injured_players = set()
    try:
        with open(filename, "r", encoding="utf-8") as file:
            rosters = json.load(file)
        for team_players in rosters.values():
            for player_info in team_players:
                injured_players.add(player_info["player"])
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading injury report from {filename}: {e}")
    return injured_players


def get_consistent_players(features, consistency_limit, minutes):
    consistent_players = {}
    for feature in features:
        try:
            player_names, _ = get_consistency(feature, consistency_limit, minutes)
            consistent_players[feature] = player_names
        except Exception as e:
            print(f"Error getting consistency for feature {feature}: {e}")
            consistent_players[feature] = []
    return consistent_players


def transform_props_data(original_data):
    transformed_data = {}
    if not isinstance(original_data, dict):
        return transformed_data

    for bookmaker_name, entries_list in original_data.items():
        player_grouped_props = defaultdict(list)
        if not isinstance(entries_list, list):
            transformed_data[bookmaker_name] = {}
            continue

        for prop_entry in entries_list:
            if isinstance(prop_entry, dict):
                player_name = prop_entry.get("player")
                if player_name:
                    player_grouped_props[player_name].append(prop_entry)
                else:
                    print(
                        f"Warning: Prop entry missing 'player' key in {bookmaker_name}: {prop_entry}"
                    )
            else:
                print(
                    f"Warning: Found non-dictionary prop entry in {bookmaker_name}: {prop_entry}"
                )

        transformed_data[bookmaker_name] = dict(player_grouped_props)
    return transformed_data


def get_rank(player, consistent_players_map, market):
    try:
        return consistent_players_map.get(market, []).index(player)
    except ValueError:
        return float("inf")


def get_player_last_ten_stats(player, market, line, data_source_path=SQL_DATA_FILE):
    try:
        df = pd.read_csv(data_source_path)
        df["date"] = pd.to_datetime(df["date"])
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError) as e:
        print(f"Error reading or processing player stats from {data_source_path}: {e}")
        return 0

    player_df = df[df["player"] == player].copy()
    if player_df.empty:
        return 0

    player_df = player_df.sort_values(["date"], ascending=False)
    last_ten = player_df.head(10)

    if last_ten.empty:
        return 0
    if line > 30.5:
        over_check_line = line - 3
    elif line > 20.5:
        over_check_line = line - 2
    elif line > 8.5:
        over_check_line = line - 1
    else:
        over_check_line = line
    over_count = (last_ten[market] >= abs(over_check_line)).sum()

    return over_count


def process_player_entry(
    entry, consistent_players_map, current_best_rank, current_best_row, conn, threshold=7
):
    try:
        player = entry["player"]
        market = entry["market"]
        line = float(entry["line"])
        odds = entry["over"]

        if player not in consistent_players_map.get(market, []) or player in BANNED:
            return current_best_rank, current_best_row
        rank = get_rank(player, consistent_players_map, market)
        last_ten_over = get_player_last_ten_stats(player, market, line)

        last_ten_trend_is_over = last_ten_over > threshold

        if rank < current_best_rank and last_ten_trend_is_over:
            team = entry["team"]
            opponent = entry["opp"]
            home_or_away = entry["hoa"]

            if line <= 8.5:
                error = 2
            elif line <= 18.5:
                error = 3
            elif line <= 30.5:
                error = 4
            else:
                error = 6

            if MODEL_RECENCY:
                # predicted_stat, error = run_recency(player, team, opponent, home_or_away, market, 20, FEATURE_WEIGHTS)
                predicted_stat = soft(player, opponent, market, home_or_away)
            else:
                predicted_stat, error = run_xgb(
                    player, team, opponent, home_or_away, market, 20
                )

            is_good_over_bet = predicted_stat is not None and (
                math.ceil(predicted_stat) >= line + error
            )
            if not is_good_over_bet:
                return current_best_rank, current_best_row

            current_best_rank = rank
            current_best_row = {
                "Player": player,
                "Market": market,
                "Predicted": round((predicted_stat) * 2) / 2,
                "Buffer": (round((error) * 2) / 2),
                "Line": line,
                "Rank": rank,
                "Last Ten": f"{int(last_ten_over)}/10",
                "Odds": odds,
                "Game": f"{team} vs {opponent}",
            }
        return current_best_rank, current_best_row

    except KeyError as e:
        print(f"Error processing entry: Missing key {e}. Entry data: {entry}")
        return current_best_rank, current_best_row
    except Exception as e:
        player_name = entry.get("player", "Unknown")
        print(f"Unexpected error processing data for player {player_name}: {e}")
        return current_best_rank, current_best_row


def run_analysis(props_data, date_str=None):
    load_dotenv()
    sql_engine = os.getenv("SQL_ENGINE")
    if not sql_engine:
        raise ValueError("SQL_ENGINE environment variable is not set")
    conn = create_engine(sql_engine)

    transformed_odds = transform_props_data(props_data)
    features_to_analyze = ["pts", "trb", "ast", "p_r", "p_a", "a_r", "p_r_a"]
    consistent_map = get_consistent_players(features_to_analyze, 300, 8)
    injuries = load_injury_report()
    
    threshold = get_season_phase_threshold(date_str)\

    all_players_props = defaultdict(list)
    for bookmaker in transformed_odds.values():
        for player, props in bookmaker.items():
            all_players_props[player].extend(props)

    total_props = sum(len(v) for v in all_players_props.values())
    warnings.filterwarnings("ignore", category=FutureWarning)

    all_best_rows = []

    pbar = tqdm(total=total_props, desc="Processing props", ncols=80, unit="prop")

    for player, entries in all_players_props.items():
        if player in injuries:
            pbar.update(len(entries))
            continue

        best_rank = float("inf")
        best_row = None

        for entry in entries:
            best_rank, best_row = process_player_entry(
                entry, consistent_map, best_rank, best_row, conn, threshold
            )
            pbar.update(1)

        if best_row:
            all_best_rows.append(best_row)

    pbar.close()
    conn.dispose()

    if all_best_rows:
        sorted_rows = sorted(all_best_rows, key=lambda x: x["Rank"])
        top_15_rows = sorted_rows[:20]

        write_rows_to_csv(top_15_rows, CSV_OUTPUT_FILE)

        try:
            with open(TEXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("")
        except IOError as e:
            print(f"Error clearing text file {TEXT_OUTPUT_FILE}: {e}")

        for row in top_15_rows:
            append_to_text(row, TEXT_OUTPUT_FILE)


def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    file_path = sys.argv[1]
    date_str = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            props_json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from {file_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while loading {file_path}: {e}")
        sys.exit(1)

    run_analysis(props_json_data, date_str)


if __name__ == "__main__":
    main()
