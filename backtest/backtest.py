import csv
import glob
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.utility.run_backtest import run as run_backtest_run
from processor import CSV_FIELDNAMES
from utility.initialize_database import create_database
from utility.nba_stats import (
    extract_player_stats,
    get_nba_game_event_ids,
    get_nba_game_summary,
)

HIST_DIR: str = "backtest/historical"
CSV_OUTPUT_FILE: str = "csv/output.csv"
NBA_STATS_FILE: str = "json/nba_stats.json"

YEAR: int = 2025


def generate_nba_stats(date_yyyymmdd: str) -> List[Dict[str, Any]]:
    event_ids = get_nba_game_event_ids(date_yyyymmdd)
    all_stats: List[Dict[str, Any]] = []
    for eid in event_ids:
        summary = get_nba_game_summary(eid)
        if summary:
            all_stats.extend(extract_player_stats(summary))
            time.sleep(0.3)
    os.makedirs(os.path.dirname(NBA_STATS_FILE), exist_ok=True)
    with open(NBA_STATS_FILE, "w", encoding="utf-8") as fh:
        json.dump(all_stats, fh, indent=2)
    return all_stats


def calculate_day_profit(
    stats_lookup: Dict[str, Dict[str, str]],
    date_iso: str,
) -> Tuple[float, int, int]:

    if not os.path.exists(CSV_OUTPUT_FILE):
        return 0.0, 0, 0

    total_gross = 0.0
    total_rows = 0
    wins = 0
    losses = 0
    day_bets = []

    with open(CSV_OUTPUT_FILE, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total_rows += 1
            player = row.get("Player", "")
            market = row.get("Market", "").lower()
            line_str = row.get("Line", "")
            odds_str = row.get("Odds", "")
            predicted_str = row.get("Predicted", "")

            try:
                line_val = float(line_str)
                odds_val = int(float(odds_str))
                predicted_val = float(predicted_str)
            except (ValueError, TypeError):
                continue

            player_stats = stats_lookup.get(player, {})
            real_val_str = player_stats.get(market, "")
            try:
                real_val = float(real_val_str)
            except (ValueError, TypeError):
                continue

            is_win = (predicted_val > line_val and real_val > line_val) or (
                predicted_val < line_val and real_val < line_val
            )

            if is_win:
                wins += 1
                gross_return = (
                    ((-100 / odds_val) + 1) if odds_val < 0 else ((odds_val / 100) + 1)
                )
                total_gross += gross_return
                profit = gross_return - 1
            else:
                losses += 1
                profit = -1

            bet_info = {
                "player": player,
                "market": market,
                "line": line_val,
                "odds": odds_val,
                "stake": 1,
                "profit": round(profit,2),
            }
            day_bets.append(bet_info)

    total_rows = wins + losses
    net_profit = total_gross - total_rows
    print(f"Found {total_rows} bets | W-L: {wins}-{losses}")

    results_file = "backtest/picks.json"
    all_results = {}
    
    if os.path.exists(results_file):
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            all_results = {}
    
    all_results[date_iso] = day_bets
    
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    return net_profit, wins, losses


def seed_output_csv():
    os.makedirs(os.path.dirname(CSV_OUTPUT_FILE), exist_ok=True)
    with open(CSV_OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()


def calculate_injury_time_for_date(date_iso):
    return "06PM"


def run_processor(date_iso):
    cmd = [
        "python",
        "processor.py",
        "json/props.json",
        date_iso,
    ]
    subprocess.run(cmd, check=True)


def get_ordered_historical_files():
    historical_files = glob.glob(os.path.join(HIST_DIR, "*_props.json"))

    december_2024_files = []
    other_files = []

    for file_path in historical_files:
        basename = os.path.basename(file_path)
        mm_dd = basename.split("_props.json")[0]
        month, day = mm_dd.split("_")

        if month == "12" or month == "11":
            december_2024_files.append(file_path)
        else:
            other_files.append(file_path)

    december_2024_files.sort()
    other_files.sort()

    return december_2024_files + other_files


def main():
    historical_files = get_ordered_historical_files()

    if not historical_files:
        print("No historical odds files found – aborting.")
        return
    first_basename = os.path.basename(historical_files[0])
    first_mm_dd = first_basename.split("_props.json")[0]
    first_month, first_day = first_mm_dd.split("_")
    first_year = 2024 if (first_month == "12" or first_month == "11") else 2025
    first_date_iso = f"{first_year}-{first_month}-{first_day}"

    try:
        df_full = pd.read_csv("csv/all_data_full.csv")
        df_initial = df_full[df_full["Date"] < first_date_iso]
        df_initial.to_csv("csv/all_data.csv", index=False)
        create_database()
    except Exception as e:
        print("Failed to bootstrap database:", e)

    running_total = 0.0
    total_wins = 0
    total_losses = 0
    print("Starting back-test across", len(historical_files), "days…\n")

    for hist_path in historical_files:
        basename = os.path.basename(hist_path)
        mm_dd = basename.split("_props.json")[0]
        month, day = mm_dd.split("_")

        year = 2024 if (month == "12" or month == "11") else 2025

        date_iso = f"{year}-{month}-{day}"
        yyyymmdd = f"{year}{month}{day}"

        print(f"=== {date_iso} ===")

        seed_output_csv()

        injury_time = calculate_injury_time_for_date(date_iso)
        run_backtest_run(date_iso, get_odds=False, injury_time=injury_time)

        run_processor(date_iso)

        stats = generate_nba_stats(yyyymmdd)
        stats_lookup = {p["Player"]: p["Stats"] for p in stats}

        day_profit, day_wins, day_losses = calculate_day_profit(stats_lookup, date_iso)
        running_total += day_profit
        total_wins += day_wins
        total_losses += day_losses

        print(
            f"Day profit: {day_profit:.2f} units | Running total: {running_total:.2f} units "
            f"| Day W-L: {day_wins}-{day_losses} | Overall W-L: {total_wins}-{total_losses} ({total_wins * 100 / (total_wins + total_losses):.2f}%)\n"
        )

    print(
        "Back-test completed. Final total:",
        f"{running_total:.2f}",
        "units | Overall W-L:",
        f"{total_wins}-{total_losses}",
    )


if __name__ == "__main__":
    main()
