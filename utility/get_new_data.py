import io
import os
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import create_engine
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL_PLAYER = "https://www.nba.com/stats/players/boxscores?SeasonType=Regular%20Season&DateFrom={date_from}&DateTo={date_to}"
BASE_URL_TEAM = "https://www.nba.com/stats/teams/boxscores?SeasonType=Regular%20Season&DateFrom={date_from}&DateTo={date_to}"
WAIT_TIMEOUT = 25
POST_LOAD_PAUSE = 3


def load_player_positions(conn):
    if not conn:
        return None
    try:
        query = "SELECT player, pos FROM latest_player_teams;"
        df = pd.read_sql(query, conn)
        df.rename(columns={"player": "Player", "pos": "Pos."}, inplace=True)
        return df[["Player", "Pos."]]
    except Exception:
        return None


def scrape_team_scores(driver, url):
    try:
        driver.get(url)
        table_selector = "table.Crom_table__p1iZz"
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, table_selector))
        )

        try:
            dropdown_selector = (
                "div[class*='Pagination_pageDropdown'] select[class*='DropDown_select']"
            )
            all_option_selector = "option[value='-1']"

            rows_dropdown = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, dropdown_selector))
            )
            driver.execute_script("arguments[0].click();", rows_dropdown)
            time.sleep(1)

            all_option = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, all_option_selector))
            )
            all_option.click()
            time.sleep(POST_LOAD_PAUSE)

        except TimeoutException:
            pass
        except NoSuchElementException:
            pass
        except Exception as e:
            pass

        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, table_selector))
        )
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "lxml")
        table_element = soup.find("table", class_="Crom_table__p1iZz")

        if table_element:
            dataframes = pd.read_html(io.StringIO(str(table_element)))
            if dataframes:
                return dataframes[0]
            else:
                return pd.DataFrame()
        else:
            return pd.DataFrame()

    except TimeoutException:
        return pd.DataFrame()
    except ImportError:
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def create_game_result_lookup(team_scores_df):
    if team_scores_df.empty:
        return {}
    df = team_scores_df.copy()
    rename_map = {
        "Team": "Team",
        "Game Date": "Date",
        "W/L": "WL",
        "PTS": "Pts",
        "Match Up": "MATCH UP",
    }
    actual_cols = {k: v for k, v in rename_map.items() if k in df.columns}
    df.rename(columns=actual_cols, inplace=True)

    required_cols = ["Date", "Team", "MATCH UP", "WL", "Pts"]
    if not all(col in df.columns for col in required_cols):
        return {}

    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    df["Pts"] = pd.to_numeric(df["Pts"], errors="coerce")
    df = df.dropna(subset=["Pts"])
    df["Pts"] = df["Pts"].astype(int)

    def get_teams_from_matchup(matchup_str):
        try:
            parts = matchup_str.split(" ")
            if len(parts) == 3:
                return tuple(sorted((parts[0], parts[2])))
            return None
        except:
            return None

    df["GameTeams"] = df["MATCH UP"].apply(get_teams_from_matchup)
    df = df.dropna(subset=["GameTeams"])
    df["GameID"] = df["Date"] + "_" + df["GameTeams"].apply(lambda x: "_".join(x))

    game_details = {}
    for name, group in df.groupby("GameID"):
        if len(group) == 2:
            team1_row = group.iloc[0]
            team2_row = group.iloc[1]
            game_details[name] = {
                "Date": team1_row["Date"],
                team1_row["Team"]: {"WL": team1_row["WL"], "Pts": team1_row["Pts"]},
                team2_row["Team"]: {"WL": team2_row["WL"], "Pts": team2_row["Pts"]},
            }

    result_lookup = {}
    for game_id, details in game_details.items():
        teams = list(details.keys())
        teams.remove("Date")
        team1, team2 = teams[0], teams[1]
        team1_data = details[team1]
        team2_data = details[team2]
        result_lookup[(details["Date"], team1)] = (
            f"{team1_data['WL']} {team1_data['Pts']}-{team2_data['Pts']}"
        )
        result_lookup[(details["Date"], team2)] = (
            f"{team2_data['WL']} {team2_data['Pts']}-{team1_data['Pts']}"
        )
    return result_lookup


def get_new_data(start_date: date = None, end_date: date = None):

    if end_date is None:
        try:
            end_date = datetime.now().date() - timedelta(days=1)
        except Exception as e:
            print(f"Error setting end_date: {e}")
            return pd.DataFrame()
    elif isinstance(end_date, str):
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid end_date format")
            return pd.DataFrame()
    elif not isinstance(end_date, date):
        print("Invalid end_date type")
        return pd.DataFrame()

    if start_date is None:
        start_date = end_date
    elif isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid start_date format")
            return pd.DataFrame()
    elif not isinstance(start_date, date):
        print("Invalid start_date type")
        return pd.DataFrame()

    if start_date > end_date:
        print("start_date cannot be after end_date")
        return pd.DataFrame()

    start_date_url_fmt = start_date.strftime("%m%%2F%d%%2F%Y")
    end_date_url_fmt = end_date.strftime("%m%%2F%d%%2F%Y")

    player_target_url = BASE_URL_PLAYER.format(
        date_from=start_date_url_fmt, date_to=end_date_url_fmt
    )
    team_target_url = BASE_URL_TEAM.format(
        date_from=start_date_url_fmt, date_to=end_date_url_fmt
    )

    db_engine = None
    db_connection_string = os.getenv("SQL_ENGINE")
    if db_connection_string:
        try:
            db_engine = create_engine(db_connection_string)
        except Exception as e:
            print(f"Database connection failed: {e}")
            db_engine = None

    driver = None
    player_stats_df = pd.DataFrame()
    team_scores_raw_df = pd.DataFrame()
    game_results_lookup = {}
    df_final = pd.DataFrame()

    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        )
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Chrome driver initialization failed: {e}")
            return pd.DataFrame()

        # Set a shorter timeout for web scraping
        driver.set_page_load_timeout(30)
        
        try:
            team_scores_raw_df = scrape_team_scores(driver, team_target_url)
            if not team_scores_raw_df.empty:
                game_results_lookup = create_game_result_lookup(team_scores_raw_df)
        except Exception as e:
            print(f"Team scores scraping failed: {e}")

        try:
            driver.get(player_target_url)
            dropdown_selector = (
                "div[class*='Pagination_pageDropdown'] select[class*='DropDown_select']"
            )
            try:
                rows_dropdown = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, dropdown_selector))
                )
                driver.execute_script("arguments[0].click();", rows_dropdown)
                time.sleep(1)
                all_option_selector = "option[value='-1']"
                try:
                    all_option = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, all_option_selector))
                    )
                    all_option.click()
                    time.sleep(POST_LOAD_PAUSE)
                except TimeoutException:
                    print("Timeout waiting for all option")
                except Exception as e:
                    print(f"Error clicking all option: {e}")
            except TimeoutException:
                print("Timeout waiting for dropdown")
            except Exception as e:
                print(f"Error with dropdown: {e}")

            try:
                page_source = driver.page_source
                dataframes = pd.read_html(io.StringIO(page_source))
                if dataframes:
                    found_table = False
                    for i, df_check in enumerate(dataframes):
                        if "PLAYER" in df_check.columns and "MIN" in df_check.columns:
                            player_stats_df = df_check
                            found_table = True
                            break
                    if not found_table and dataframes:
                        player_stats_df = dataframes[0]
            except Exception as e:
                print(f"Error parsing player stats: {e}")

        except Exception as e:
            print(f"Player stats scraping failed: {e}")

        if player_stats_df is None or player_stats_df.empty:
            print("No player stats data found")
            return pd.DataFrame()

        # Continue with data processing...
        df = player_stats_df.copy()
        percentage_cols = ["FG%", "3P%", "FT%"]
        numeric_cols = [
            "MIN",
            "PTS",
            "FGM",
            "FGA",
            "3PM",
            "3PA",
            "FTM",
            "FTA",
            "OREB",
            "DREB",
            "REB",
            "AST",
            "STL",
            "BLK",
            "TOV",
            "PF",
            "+/-",
        ]
        for col in percentage_cols:
            df[col] = round(pd.to_numeric(df[col], errors="coerce") / 100.0, 3)
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        rename_map = {
            "PLAYER": "Player",
            "GAME DATE": "Date",
            "TEAM": "Team",
            "MIN": "MP",
            "FGM": "FG",
            "FGA": "FGA",
            "3PM": "3P",
            "3PA": "3PA",
            "FTM": "FT",
            "FTA": "FTA",
            "OREB": "ORB",
            "DREB": "DRB",
            "REB": "TRB",
            "AST": "AST",
            "STL": "STL",
            "BLK": "BLK",
            "TOV": "TOV",
            "PF": "PF",
            "PTS": "PTS",
        }
        df.rename(columns=rename_map, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime(
            "%Y-%m-%d"
        )

        def parse_matchup(row):
            matchup_str = row["MATCH UP"]
            team = row["Team"]
            if pd.isna(matchup_str):
                return ("", "")
            parts = matchup_str.split(" ")
            if len(parts) == 3:
                team1, separator, team2 = parts[0], parts[1], parts[2]
                if team == team1 and separator == "vs.":
                    return ("", team2)
                elif team == team2 and separator == "vs.":
                    return ("", team1)
                elif team == team1 and separator == "@":
                    return ("", team2)
                elif team == team2 and separator == "@":
                    return ("@", team1)
                else:
                    return ("", "")
            else:
                return ("", "")

        df[["HOA", "Opp"]] = df.apply(parse_matchup, axis=1, result_type="expand")

        if "W/L" in df.columns:
            original_wl = df["W/L"].copy()
        else:
            original_wl = pd.Series(index=df.index, dtype=object).fillna("")
        df["Result"] = df.apply(
            lambda row: game_results_lookup.get((row["Date"], row["Team"]), None),
            axis=1,
        )
        df["Result"] = df["Result"].fillna(original_wl)

        df["2P"] = (df["FG"] - df["3P"]).fillna(0).astype(int)
        df["2PA"] = (df["FGA"] - df["3PA"]).fillna(0).astype(int)
        df["2P%"] = (
            round(df["2P"].astype(float) / df["2PA"].replace(0, np.nan), 3)
        ).replace([np.inf, -np.inf], np.nan)
        denominator_ts = 2 * (df["FGA"] + 0.44 * df["FTA"])
        df["TS%"] = (
            round(df["PTS"].astype(float) / denominator_ts.replace(0, np.nan), 3)
        ).replace([np.inf, -np.inf], np.nan)
        df["GmSc"] = (
            round(
                df["PTS"]
                + 0.4 * df["FG"]
                - 0.7 * df["FGA"]
                - 0.4 * (df["FTA"] - df["FT"])
                + 0.7 * df["ORB"]
                + 0.3 * df["DRB"]
                + df["STL"]
                + 0.7 * df["AST"]
                + 0.7 * df["BLK"]
                - 0.4 * df["PF"]
                - df["TOV"],
                3,
            )
        ).fillna(0)

        player_positions_df = None
        if db_engine:
            player_positions_df = load_player_positions(db_engine)
        if player_positions_df is not None and not player_positions_df.empty:
            df = pd.merge(df, player_positions_df, on="Player", how="left")
            df["Pos."] = df["Pos."].fillna("G")
        else:
            df["Pos."] = "G"

        df["Rk"] = 1
        df["Age"] = "29-333"
        df["GS"] = ""
        df["BPM"] = 25
        df["Player-additional"] = "new_data"

        final_columns = [
            "Rk",
            "Player",
            "Date",
            "Age",
            "Team",
            "HOA",
            "Opp",
            "Result",
            "GS",
            "MP",
            "FG",
            "FGA",
            "FG%",
            "2P",
            "2PA",
            "2P%",
            "3P",
            "3PA",
            "3P%",
            "FT",
            "FTA",
            "FT%",
            "TS%",
            "ORB",
            "DRB",
            "TRB",
            "AST",
            "STL",
            "BLK",
            "TOV",
            "PF",
            "PTS",
            "GmSc",
            "BPM",
            "+/-",
            "Pos.",
            "Player-additional",
        ]
        for col in final_columns:
            if col not in df.columns:
                df[col] = np.nan
        df_final = df[final_columns].copy()
        int_cols = [
            "MP",
            "FG",
            "FGA",
            "3P",
            "3PA",
            "FT",
            "FTA",
            "ORB",
            "DRB",
            "TRB",
            "AST",
            "STL",
            "BLK",
            "TOV",
            "PF",
            "PTS",
        ]
        for col in int_cols:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors="coerce").astype(
                    "Int64"
                )

        if db_engine:
            try:
                db_engine.dispose()
            except Exception:
                pass
        return df_final

    except Exception as e:
        print(f"Error in get_new_data: {e}")
        if db_engine:
            try:
                db_engine.dispose()
            except Exception:
                pass
        return pd.DataFrame()

    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Error closing driver: {e}")
                pass


if __name__ == "__main__":
    df = get_new_data(start_date="2025-04-13")
    print(df.head(2000))
