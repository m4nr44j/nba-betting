import csv
import glob
import json
import os
import subprocess
import sys
from typing import Dict, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.utility.run_backtest import run as run_backtest_run
from config import (
    BACKTEST_HISTORICAL_24_25_DIR,
    BACKTEST_HISTORICAL_25_26_DIR,
    CSV_ALL_DATA_FILE,
    CSV_ALL_DATA_PROCESSED_FILE,
    CSV_OUTPUT_FILE,
    JSON_PROPS_FILE,
    USE_2025_26_SEASON,
)
from processor import CSV_FIELDNAMES
from utility.initialize_database import create_database

if USE_2025_26_SEASON:
    HIST_DIR: str = BACKTEST_HISTORICAL_25_26_DIR
    BASE_YEAR: int = 2025
else:
    HIST_DIR: str = BACKTEST_HISTORICAL_24_25_DIR
    BASE_YEAR: int = 2024

YEAR: int = BASE_YEAR


def calculate_day_profit(
    all_data: pd.DataFrame,
    date_iso: str,
) -> Tuple[float, int, int]:
    total_gross = 0.0
    total_row = 0
    wins = 0
    losses = 0
    day_bets = []
    date_mask = all_data["Date"] == date_iso
    day_stats = all_data[date_mask]

    for row in csv.DictReader(open(CSV_OUTPUT_FILE, newline="", encoding="utf-8")):
        total_row += 1
        player = row.get("Player", "")
        market = row.get("Market", "").lower()
        line_str = row.get("Line", "")
        odds_str = row.get("Odds", "")
        predicted_str = row.get("Predicted", "")
        if not player or not market or not line_str:
            continue
        try:
            line_val = float(line_str)
            odds_val = int(float(odds_str))
            predicted_val = float(predicted_str)
        except (ValueError, TypeError):
            continue
        stat_row = day_stats[day_stats["Player"] == player]
        if stat_row.empty:
            print(f"No stats found for {player} on {date_iso}")
            continue
        s = stat_row.iloc[0]
        def get_stat(market):
            if market in ["pts", "points"]:
                return float(s["PTS"])
            if market in ["reb", "rebounds", "trb"]:
                return float(s["TRB"])
            if market in ["ast", "assists"]:
                return float(s["AST"])
            if market in ["tpm", "3p"]:
                return float(s["3P"])
            if market == "p_r":
                return float(s["PTS"]) + float(s["TRB"])
            if market == "p_a":
                return float(s["PTS"]) + float(s["AST"])
            if market == "a_r":
                return float(s["AST"]) + float(s["TRB"])
            if market == "p_r_a":
                return float(s["PTS"]) + float(s["TRB"]) + float(s["AST"])
            return None
        real_val = get_stat(market)
        if real_val is None:
            print(f"Market {market} not supported for {player} on {date_iso}")
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
    print(f"Found {total_row} bets | W-L: {wins}-{losses}")
    results_file = os.path.join(os.path.dirname(HIST_DIR), "picks.json") if HIST_DIR else "backtest/picks.json"
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
    import datetime as _dt
    try:
        dt = _dt.datetime.fromisoformat(date_iso)
    except ValueError:
        return "06PM"
    return "02PM" if dt.weekday() == 6 else "06PM"


def run_processor(date_iso):
    cmd = [
        "python",
        "processor.py",
        JSON_PROPS_FILE,
        date_iso,
    ]
    subprocess.run(cmd, check=True)


def get_ordered_historical_files():
    historical_files = glob.glob(os.path.join(HIST_DIR, "*_props.json"))
    
    if USE_2025_26_SEASON:
        historical_files.sort()
    else:
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
        historical_files = december_2024_files + other_files
    
    return historical_files


def main():
    historical_files = get_ordered_historical_files()

    if not historical_files:
        print("No historical odds files found – aborting.")
        return
    first_basename = os.path.basename(historical_files[0])
    first_mm_dd = first_basename.split("_props.json")[0]
    first_month, first_day = first_mm_dd.split("_")
    
    if USE_2025_26_SEASON:
        first_year = 2025
    else:
        first_year = 2024 if (first_month == "12" or first_month == "11") else 2025
    
    first_date_iso = f"{first_year}-{first_month}-{first_day}"

    try:
        all_data_full = pd.read_csv(CSV_ALL_DATA_FILE, low_memory=False)
    except Exception as e:
        print(f"Failed to read {CSV_ALL_DATA_FILE}:", e)
        return

    try:
        df_initial = all_data_full[all_data_full["Date"] < first_date_iso]
        df_initial.to_csv(CSV_ALL_DATA_PROCESSED_FILE, index=False)
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

        if USE_2025_26_SEASON:
            year = 2025 if (month == "12" or month == "11" or month == "10") else 2026
        else:
            year = 2024 if (month == "12" or month == "11") else 2025
        
        date_iso = f"{year}-{month}-{day}"
        yyyymmdd = f"{year}{month}{day}"

        print(f"=== {date_iso} ===")

        seed_output_csv()

        injury_time = calculate_injury_time_for_date(date_iso)
        run_backtest_run(date_iso, get_odds=False, injury_time=injury_time, hist_dir=HIST_DIR)

        run_processor(date_iso)

        day_profit, day_wins, day_losses = calculate_day_profit(all_data_full, date_iso)
        running_total += day_profit
        total_wins += day_wins
        total_losses += day_losses

        print(
            f"Day profit: {day_profit:.2f} units | Running total: {running_total:.2f} units "
            f"| Day W-L: {day_wins}-{day_losses} | Overall W-L: {total_wins}-{total_losses} ("
            + (f"{total_wins * 100 / (total_wins + total_losses):.2f}%" if (total_wins + total_losses) else "0.00%")
            + ")\n"
        )

    print(
        "Back-test completed. Final total:",
        f"{running_total:.2f}",
        "units | Overall W-L:",
        f"{total_wins}-{total_losses}",
    )


if __name__ == "__main__":
    main()
