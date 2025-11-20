import json
import os
import sys

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    JSON_PROPS_FILE,
    LOWEST_PRICE_THRESHOLD,
    HIGHEST_PRICE_THRESHOLD,
    MIN_PROP_LINE,
    MARKET_MAPPING,
    NBA_TEAMS,
    PLAYER_NAME_CORRECTIONS,
)

load_dotenv()


def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
        return data


def fetch_player_details(cursor, description, home_team, away_team):
    for old_name, new_name in PLAYER_NAME_CORRECTIONS.items():
        description = description.replace(old_name, new_name)
    cursor.execute(
        """
    SELECT team, pos FROM public.latest_player_teams WHERE player = %s;
    """,
        (description,),
    )
    result = cursor.fetchone()
    if result:
        player_team, player_position = result
        hoa = 0 if player_team == home_team else 1
        opp_team = home_team if player_team == away_team else away_team

        return {"player": description, "team": player_team, "opp": opp_team, "hoa": hoa}
    else:
        return None


def process_props_and_output(cursor, data):
    market_mapping = MARKET_MAPPING

    results = {}
    for platform, markets in data.items():
        platform_results = []
        for market, props in markets.items():
            best_props_for_market = {}

            feature_column = market_mapping.get(market)
            if not feature_column:
                print(
                    f"Warning: Skipping unmapped market '{market}' for platform '{platform}'"
                )
                continue

            for prop in props:
                if not all(
                    k in prop for k in ["description", "game_id", "point", "price", "name"]
                ):
                    print(f"Warning: Skipping prop due to missing keys: {prop}")
                    continue

                # Filter out "Under" props - only process "Over" props
                prop_name = prop.get("name", "").lower()
                if prop_name != "over":
                    continue

                if (
                    LOWEST_PRICE_THRESHOLD <= prop["price"] <= HIGHEST_PRICE_THRESHOLD
                    and prop["point"] > MIN_PROP_LINE
                ):
                    key = (prop["description"], prop["game_id"])
                    current_line = prop["point"]
                    current_price = prop["price"]

                    if key in best_props_for_market:
                        if (
                            current_line < best_props_for_market[key]["line"]
                            and LOWEST_PRICE_THRESHOLD
                            <= current_price
                            <= HIGHEST_PRICE_THRESHOLD
                        ):
                            best_props_for_market[key]["line"] = current_line
                            best_props_for_market[key]["over"] = current_price
                    else:
                        player_info = fetch_player_details(
                            cursor,
                            prop["description"],
                            prop["home_team"],
                            prop["away_team"],
                        )
                        if player_info:
                            best_props_for_market[key] = {
                                **player_info,
                                "line": current_line,
                                "market": feature_column,
                                "over": current_price,
                            }

            platform_results.extend(best_props_for_market.values())

        results[platform] = platform_results

    return results


def write_json_file(data, file_path):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    print(f"Data written to {file_path} successfully.")


def process_props(data):
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT"),
    )
    cursor = conn.cursor()

    try:
        detailed_player_props = process_props_and_output(cursor, data)
        conn.commit()
        return detailed_player_props
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def props(date, hist_dir=None):
    from config import BACKTEST_HISTORICAL_24_25_DIR, get_historical_dir
    
    if hist_dir is None:
        hist_dir = BACKTEST_HISTORICAL_24_25_DIR
    
    with open(f"{hist_dir}/{date}_props.json", "r", encoding="utf-8") as f:
        props_json_data = json.load(f)
    data = process_props(props_json_data)
    with open(JSON_PROPS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    from config import BACKTEST_HISTORICAL_25_26_DIR
    
    with open(f"{BACKTEST_HISTORICAL_25_26_DIR}/11_20_props.json", "r", encoding="utf-8") as f:
        props_json_data = json.load(f)
    data = process_props(props_json_data)
    with open(JSON_PROPS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
