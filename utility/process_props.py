import json
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
        return data


def fetch_player_details(cursor, description, home_team, away_team):
    description = description.replace(" Jr", " Jr.")
    description = description.replace("Jimmy Butler", "Jimmy Butler III")
    description = description.replace("Luka Doncic", "Luka Dončić")
    description = description.replace("Nikola Jokic", "Nikola Jokić")
    description = description.replace("Nikola Vucevic", "Nikola Vučević")
    description = description.replace("Jonas Valanciunas", "Jonas Valančiūnas")
    description = description.replace("Bojan Bogdanovic", "Bojan Bogdanović")
    description = description.replace("Dario Saric", "Dario Šarić")
    description = description.replace("Bogdan Bogdanovic", "Bogdan Bogdanović")
    description = description.replace("Karlo Matkovic", "Karlo Matković")
    description = description.replace("Boban Marjanovic", "Boban Marjanović")
    description = description.replace("Jusuf Nurkic", "Jusuf Nurkić")
    description = description.replace("Luka Samanic", "Luka Šamanić")
    description = description.replace("Nikola Jovic", "Nikola Jović")
    description = description.replace("Vasilije Micic", "Vasilije Micić")
    description = description.replace("Vit Krejci", "Vít Krejčí")
    description = description.replace("Tristan Vukcevic", "Tristan Vukčević")
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

    market_mapping = {
        "player_points_alternate": "pts",
        "player_rebounds_alternate": "trb",
        "player_assists_alternate": "ast",
        "player_points_rebounds_alternate": "p_r",
        "player_points_assists_alternate": "p_a",
        "player_rebounds_assists_alternate": "a_r",
        "player_points_rebounds_assists_alternate": "p_r_a",
        "player_threes": "tpm",
    }

    # market_mapping = {
    #     "player_points": "pts",
    #     "player_rebounds": "trb",
    #     "player_assists": "ast",
    #     "player_points_rebounds": "p_r",
    #     "player_points_assists": "p_a",
    #     "player_rebounds_assists": "a_r",
    #     "player_points_rebounds_assists": "p_r_a",
    #     "player_threes": "tpm",
    # }

    lowest_price_threshold = -130
    highest_price_threshold = 120

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
                    k in prop for k in ["description", "game_id", "point", "price"]
                ):
                    print(f"Warning: Skipping prop due to missing keys: {prop}")
                    continue

                if (
                    lowest_price_threshold <= prop["price"] <= highest_price_threshold
                    and prop["point"] > 2.5
                ):
                    key = (prop["description"], prop["game_id"])
                    current_line = prop["point"]
                    current_price = prop["price"]

                    if key in best_props_for_market:
                        if (
                            current_line < best_props_for_market[key]["line"]
                            and lowest_price_threshold
                            <= current_price
                            <= highest_price_threshold
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


def props(date):
    with open(f"backtest/historical/{date}_props.json", "r", encoding="utf-8") as f:
        props_json_data = json.load(f)
    data = process_props(props_json_data)
    with open("json/props.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    with open("backtest/historical/12_05_props.json", "r", encoding="utf-8") as f:
        props_json_data = json.load(f)
    data = process_props(props_json_data)
    with open("json/props.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
