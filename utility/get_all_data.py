import os
import io
import time
import numpy as np
import pandas as pd
from datetime import date, timedelta, datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

REGULAR_SEASON_START = date(2024, 10, 22)
REGULAR_SEASON_END   = date(2025, 4, 13)
PLAYOFFS_START       = date(2025, 4, 14)
PLAYOFFS_END         = date(2025, 6, 22)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "csv", "all_data_full.csv")
POST_LOAD_PAUSE = 3

NEW_BASE_URL_PLAYER_TEMPLATE = (
    "https://www.nba.com/stats/players/boxscores"
    "?SeasonType={season_type}&DateFrom={date_from}&DateTo={date_to}&Season={season_str}"
)
NEW_BASE_URL_TEAM_TEMPLATE = (
    "https://www.nba.com/stats/teams/boxscores"
    "?SeasonType={season_type}&DateFrom={date_from}&DateTo={date_to}&Season={season_str}"
)

def month_batches(start_date, end_date):
    batches = []
    current = start_date
    while current <= end_date:
        first_day = current.replace(day=1)
        if current.month == 12:
            next_month = current.replace(year=current.year+1, month=1, day=1)
        else:
            next_month = current.replace(month=current.month+1, day=1)
        last_day = min(next_month - timedelta(days=1), end_date)
        batch_start = max(current, first_day)
        batches.append( (batch_start, last_day) )
        current = next_month
    return batches

def safe_to_float(val):
    try:
        return float(val)
    except Exception:
        return None

def scrape_team_scores(driver, url):
    try:
        driver.get(url)
        table_selector = "table.Crom_table__p1iZz"
        WebDriverWait(driver, 25).until(
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
        except (TimeoutException, NoSuchElementException):
            pass
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
    except Exception:
        return pd.DataFrame()

def create_game_result_lookup(team_scores_df):
    if team_scores_df is None or team_scores_df.empty:
        return {}
    df = team_scores_df.copy()

    rename_map = {
        "TEAM": "Team",
        "Team": "Team",
        "DATE": "Date",
        "Game Date": "Date",
        "W/L": "WL",
        "PTS": "Pts",
        "Match Up": "MATCH UP",
        "MATCH UP": "MATCH UP",
    }
    actual_cols = {k: v for k, v in rename_map.items() if k in df.columns}
    df.rename(columns=actual_cols, inplace=True)

    required_cols = ["Date", "Team", "MATCH UP", "WL", "Pts"]
    if not all(col in df.columns for col in required_cols):
        return {}

    try:
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        except Exception:
            return {}
    df["Pts"] = pd.to_numeric(df["Pts"], errors="coerce")
    df = df.dropna(subset=["Pts"]).copy()
    df["Pts"] = df["Pts"].astype(int)

    def get_teams_from_matchup(matchup_str):
        try:
            parts = str(matchup_str).split(" ")
            if len(parts) == 3:
                return tuple(sorted((parts[0], parts[2])))
            return None
        except Exception:
            return None

    df["GameTeams"] = df["MATCH UP"].apply(get_teams_from_matchup)
    df = df.dropna(subset=["GameTeams"])
    df["GameID"] = df["Date"] + "_" + df["GameTeams"].apply(lambda x: "_".join(x))

    result_lookup = {}
    for _, group in df.groupby("GameID"):
        if len(group) != 2:
            continue
        team1_row, team2_row = group.iloc[0], group.iloc[1]
        date_str = team1_row["Date"]
        t1, t2 = team1_row["Team"], team2_row["Team"]
        t1_wl, t2_wl = str(team1_row["WL"]).strip(), str(team2_row["WL"]).strip()
        t1_pts, t2_pts = int(team1_row["Pts"]), int(team2_row["Pts"])
        result_lookup[(date_str, t1)] = f"{t1_wl} {t1_pts}-{t2_pts}"
        result_lookup[(date_str, t2)] = f"{t2_wl} {t2_pts}-{t1_pts}"

    return result_lookup

def fetch_and_format_batch(driver, season_type, start_dt, end_dt, max_retries=3, retry_sleep=7):
    str_start = start_dt.strftime("%m/%d/%Y")
    str_end = end_dt.strftime("%m/%d/%Y")
    player_url = NEW_BASE_URL_PLAYER_TEMPLATE.format(season_type=season_type, date_from=str_start, date_to=str_end, season_str="2024-25")
    team_url   = NEW_BASE_URL_TEAM_TEMPLATE.format(season_type=season_type, date_from=str_start, date_to=str_end, season_str="2024-25")
    
    team_scores_df = scrape_team_scores(driver, team_url)
    result_lookup = create_game_result_lookup(team_scores_df)
    
    attempt = 0
    player_stats_df = pd.DataFrame()
    while attempt < max_retries:
        driver.get(player_url)
        dropdown_selector = (
            "div[class*='Pagination_pageDropdown'] select[class*='DropDown_select']"
        )
        all_option_selector = "option[value='-1']"
        try:
            rows_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, dropdown_selector))
            )
            driver.execute_script("arguments[0].click();", rows_dropdown)
            time.sleep(1)
            all_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, all_option_selector))
            )
            all_option.click()
            time.sleep(POST_LOAD_PAUSE)
        except (TimeoutException, NoSuchElementException):
            pass
        try:
            page_source = driver.page_source
            dataframes = pd.read_html(io.StringIO(page_source))
            for df in dataframes:
                if "PLAYER" in df.columns and "MIN" in df.columns:
                    player_stats_df = df
                    break
            else:
                if dataframes:
                    player_stats_df = dataframes[0]
                else:
                    player_stats_df = pd.DataFrame()
        except Exception:
            player_stats_df = pd.DataFrame()
        req_cols = ["GAME DATE", "PLAYER", "MIN"]
        if all(col in player_stats_df.columns for col in req_cols):
            break
        else:
            attempt += 1
            if attempt < max_retries:
                print(f"\n[WARN] Batch {start_dt} - {end_dt}: Required columns missing ({player_stats_df.columns.tolist()}), retrying ({attempt}/{max_retries}) after sleep...")
                time.sleep(retry_sleep)
            else:
                print(f"\n[ERROR] Batch {start_dt} - {end_dt}: Required columns missing after {max_retries} attempts. Skipping batch. Columns: {player_stats_df.columns.tolist()}")
                return pd.DataFrame()

    if player_stats_df.empty: return pd.DataFrame()
    df = player_stats_df.copy()
    perc_cols = ["FG%", "3P%", "FT%"]
    for col in perc_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").div(100).round(3)
    numeric_cols = [
        "MIN", "PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA",
        "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "+/-"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    rename_map = {
        "PLAYER": "Player", "GAME DATE": "Date", "TEAM": "Team", "MIN": "MP",
        "FGM": "FG", "FGA": "FGA", "3PM": "3P", "3PA": "3PA", "FTM": "FT", "FTA": "FTA",
        "OREB": "ORB", "DREB": "DRB", "REB": "TRB", "AST": "AST", "STL": "STL",
        "BLK": "BLK", "TOV": "TOV", "PF": "PF", "PTS": "PTS"
    }
    df.rename(columns=rename_map, inplace=True)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    def parse_matchup(row):
        matchup_str = row.get("MATCH UP", "")
        team = row.get("Team", "")
        parts = matchup_str.split(" ")
        if len(parts) == 3:
            team1, sep, team2 = parts
            if team == team1 and sep == "vs.": return ("", team2)
            if team == team1 and sep == "@":   return ("@", team2)
            if team == team2 and sep == "@":   return ("", team1)
            if team == team2 and sep == "vs.": return ("@", team1)
        return ("", "")
    df[["HOA", "Opp"]] = df.apply(parse_matchup, axis=1, result_type="expand")
    df["Result"] = df.apply(
        lambda row: result_lookup.get((row["Date"], row["Team"]), ""), axis=1
    )
    df["2P"] = (df["FG"] - df["3P"]).fillna(0).astype(int)
    df["2PA"] = (df["FGA"] - df["3PA"]).fillna(0).astype(int)
    df["2P%"] = (
        np.where(df["2PA"] == 0, np.nan,
        (df["2P"].astype(float) / df["2PA"]).round(3))
    )
    denominator_ts = 2 * (df["FGA"] + 0.44 * df["FTA"])
    df["TS%"] = (
        np.where(denominator_ts == 0, np.nan,
        (df["PTS"].astype(float) / denominator_ts).round(3))
    )
    df["GmSc"] = (
        (df["PTS"] + 0.4 * df["FG"] - 0.7 * df["FGA"]
        - 0.4 * (df["FTA"] - df["FT"])
        + 0.7 * df["ORB"] + 0.3 * df["DRB"]
        + df["STL"] + 0.7*df["AST"] + 0.7*df["BLK"]
        - 0.4*df["PF"] - df["TOV"]).round(3)
    ).fillna(0)
    df["BPM"] = 0
    df["Player-additional"] = "new_data"
    df["GS"] = ""
    df["Age"] = ""
    if "+/-" not in df.columns: df["+/-"] = None
    df["Pos."] = "G"
    column_order = [
        "Rk","Player","Date","Age","Team","HOA","Opp","Result","GS","MP",
        "FG","FGA","FG%","2P","2PA","2P%","3P","3PA","3P%","FT","FTA",
        "FT%","TS%","ORB","DRB","TRB","AST","STL","BLK","TOV","PF",
        "PTS","GmSc","BPM","+/-","Pos.","Player-additional"
    ]
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    df["Rk"] = 1
    return df[column_order]

def fetch_and_format_batch_for_season(driver, season_type, start_dt, end_dt, season_str, max_retries=3, retry_sleep=7):
    str_start = start_dt.strftime("%m/%d/%Y")
    str_end = end_dt.strftime("%m/%d/%Y")
    player_url = NEW_BASE_URL_PLAYER_TEMPLATE.format(season_type=season_type, date_from=str_start, date_to=str_end, season_str=season_str)
    team_url = NEW_BASE_URL_TEAM_TEMPLATE.format(season_type=season_type, date_from=str_start, date_to=str_end, season_str=season_str)

    team_scores_df = scrape_team_scores(driver, team_url)
    result_lookup = create_game_result_lookup(team_scores_df)
    attempt = 0
    player_stats_df = pd.DataFrame()
    while attempt < max_retries:
        driver.get(player_url)
        dropdown_selector = (
            "div[class*='Pagination_pageDropdown'] select[class*='DropDown_select']"
        )
        all_option_selector = "option[value='-1']"
        try:
            rows_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, dropdown_selector))
            )
            driver.execute_script("arguments[0].click();", rows_dropdown)
            time.sleep(1)
            all_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, all_option_selector))
            )
            all_option.click()
            time.sleep(POST_LOAD_PAUSE)
        except (TimeoutException, NoSuchElementException):
            pass
        try:
            page_source = driver.page_source
            dataframes = pd.read_html(io.StringIO(page_source))
            for df in dataframes:
                if "PLAYER" in df.columns and "MIN" in df.columns:
                    player_stats_df = df
                    break
            else:
                if dataframes:
                    player_stats_df = dataframes[0]
                else:
                    player_stats_df = pd.DataFrame()
        except Exception:
            player_stats_df = pd.DataFrame()
        req_cols = ["GAME DATE", "PLAYER", "MIN"]
        if all(col in player_stats_df.columns for col in req_cols):
            break
        else:
            attempt += 1
            if attempt < max_retries:
                print(f"\n[WARN] Batch {start_dt} - {end_dt} ({season_str}): Required columns missing ({player_stats_df.columns.tolist()}), retrying ({attempt}/{max_retries}) after sleep...")
                time.sleep(retry_sleep)
            else:
                print(f"\n[ERROR] Batch {start_dt} - {end_dt} ({season_str}): Required columns missing after {max_retries} attempts. Skipping batch. Columns: {player_stats_df.columns.tolist()}")
                return pd.DataFrame()
    if player_stats_df.empty: return pd.DataFrame()
    df = player_stats_df.copy()
    perc_cols = ["FG%", "3P%", "FT%"]
    for col in perc_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").div(100).round(3)
    numeric_cols = [
        "MIN", "PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA",
        "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "+/-"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    rename_map = {
        "PLAYER": "Player", "GAME DATE": "Date", "TEAM": "Team", "MIN": "MP",
        "FGM": "FG", "FGA": "FGA", "3PM": "3P", "3PA": "3PA", "FTM": "FT", "FTA": "FTA",
        "OREB": "ORB", "DREB": "DRB", "REB": "TRB", "AST": "AST", "STL": "STL",
        "BLK": "BLK", "TOV": "TOV", "PF": "PF", "PTS": "PTS"
    }
    df.rename(columns=rename_map, inplace=True)
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    def parse_matchup(row):
        matchup_str = row.get("MATCH UP", "")
        team = row.get("Team", "")
        parts = matchup_str.split(" ")
        if len(parts) == 3:
            team1, sep, team2 = parts
            if team == team1 and sep == "vs.": return ("", team2)
            if team == team1 and sep == "@":   return ("@", team2)
            if team == team2 and sep == "@":   return ("", team1)
            if team == team2 and sep == "vs.": return ("@", team1)
        return ("", "")
    df[["HOA", "Opp"]] = df.apply(parse_matchup, axis=1, result_type="expand")
    df["Result"] = df.apply(
        lambda row: result_lookup.get((row["Date"], row["Team"]), ""), axis=1
    )
    df["2P"] = (df["FG"] - df["3P"]).fillna(0).astype(int)
    df["2PA"] = (df["FGA"] - df["3PA"]).fillna(0).astype(int)
    df["2P%"] = (
        np.where(df["2PA"] == 0, np.nan,
        (df["2P"].astype(float) / df["2PA"]).round(3))
    )
    denominator_ts = 2 * (df["FGA"] + 0.44 * df["FTA"])
    df["TS%"] = (
        np.where(denominator_ts == 0, np.nan,
        (df["PTS"].astype(float) / denominator_ts).round(3))
    )
    df["GmSc"] = (
        (df["PTS"] + 0.4 * df["FG"] - 0.7 * df["FGA"]
        - 0.4 * (df["FTA"] - df["FT"])
        + 0.7 * df["ORB"] + 0.3 * df["DRB"]
        + df["STL"] + 0.7*df["AST"] + 0.7*df["BLK"]
        - 0.4*df["PF"] - df["TOV"]).round(3)
    ).fillna(0)
    df["BPM"] = 0
    df["Player-additional"] = "new_data"
    df["GS"] = ""
    df["Age"] = ""
    if "+/-" not in df.columns: df["+/-"] = None
    df["Pos."] = "G"
    column_order = [
        "Rk","Player","Date","Age","Team","HOA","Opp","Result","GS","MP",
        "FG","FGA","FG%","2P","2PA","2P%","3P","3PA","3P%","FT","FTA",
        "FT%","TS%","ORB","DRB","TRB","AST","STL","BLK","TOV","PF",
        "PTS","GmSc","BPM","+/-","Pos.","Player-additional"
    ]
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    df["Rk"] = 1
    return df[column_order]

def run_manual_batches(driver):
    custom_batches = [
        (date(2025,10,21), date.today(), "Regular%20Season", "2025-26", "2025-10-21 to 2025-10-29 (25-26 REG)"),
        (date(2024,2,22), date(2024,4,14), "Regular%20Season", "2023-24", "2024-02-22 to 2024-04-14 (23-24 REG)"),
        (date(2024,4,18), date(2024,6,17), "Playoffs", "2023-24", "2024-04-18 to 2024-06-17 (23-24 PO)")
    ]
    for start_dt, end_dt, season_type, season_str, label in custom_batches:
        print(f"\n[MANUAL RUN] Batch {label}...")
        batch_df = fetch_and_format_batch_for_season(driver, season_type, start_dt, end_dt, season_str)
        if batch_df is not None and not batch_df.empty:
            append_batch_to_csv(batch_df, OUTPUT_CSV)
            print(f"Appended {len(batch_df)} rows to {OUTPUT_CSV} for {label}")
        else:
            print(f"(No data found for {label})")

def append_batch_to_csv(df, csv_path):
    if df is None or df.empty:
        return
    df = sanitize_numeric_fields(df)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    write_header = True
    if os.path.exists(csv_path):
        try:
            write_header = os.path.getsize(csv_path) == 0
        except Exception:
            write_header = False
    df.to_csv(csv_path, mode="a", header=write_header, index=False, na_rep="None")

def sanitize_numeric_fields(df):
    if df is None or df.empty:
        return df
    df = df.copy()

    int_cols = [
        "MP","FG","FGA","2P","2PA","3P","3PA","FT","FTA",
        "ORB","DRB","TRB","AST","STL","BLK","TOV","PF","PTS","+/-"
    ]
    float_cols = ["FG%","2P%","3P%","FT%","TS%","GmSc","BPM"]

    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace({"": np.nan, " ": np.nan}), errors="coerce").astype("Int64")

    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace({"": np.nan, " ": np.nan}), errors="coerce")

    return df


def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    if os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
            print(f"Cleared existing file: {OUTPUT_CSV}")
        except Exception as e:
            print(f"Warning: Could not remove existing file {OUTPUT_CSV}: {e}")

    try:
        print("\nScraping REGULAR SEASON data...\n")
        for batch_start, batch_end in month_batches(REGULAR_SEASON_START, REGULAR_SEASON_END):
            print(f"REGULAR: {batch_start} to {batch_end}")
            batch_df = fetch_and_format_batch(driver, "Regular%20Season", batch_start, batch_end)
            if batch_df is not None and not batch_df.empty:
                append_batch_to_csv(batch_df, OUTPUT_CSV)
                print(f"Appended {len(batch_df)} rows to {OUTPUT_CSV}")
            else:
                print(f"(No data found for {batch_start})")

        print("\nScraping PLAY-IN data...\n")
        playin_24_25_start = date(2025, 4, 14)
        playin_24_25_end = date(2025, 4, 18)
        print(f"PLAY-IN 24-25: {playin_24_25_start} to {playin_24_25_end}")
        batch_df = fetch_and_format_batch(driver, "PlayIn", playin_24_25_start, playin_24_25_end)
        if batch_df is not None and not batch_df.empty:
            append_batch_to_csv(batch_df, OUTPUT_CSV)
            print(f"Appended {len(batch_df)} rows to {OUTPUT_CSV}")
        else:
            print(f"(No data found for {playin_24_25_start})")

        playin_23_24_start = date(2024, 4, 16)
        playin_23_24_end = date(2024, 4, 19)
        print(f"PLAY-IN 23-24: {playin_23_24_start} to {playin_23_24_end}")
        batch_df = fetch_and_format_batch_for_season(
            driver,
            "PlayIn",
            playin_23_24_start,
            playin_23_24_end,
            "2023-24",
        )
        if batch_df is not None and not batch_df.empty:
            append_batch_to_csv(batch_df, OUTPUT_CSV)
            print(f"Appended {len(batch_df)} rows to {OUTPUT_CSV}")
        else:
            print(f"(No data found for {playin_23_24_start})")

        print("\nScraping PLAYOFFS data...\n")
        for batch_start, batch_end in month_batches(PLAYOFFS_START, PLAYOFFS_END):
            print(f"PLAYOFFS: {batch_start} to {batch_end}")
            batch_df = fetch_and_format_batch(driver, "Playoffs", batch_start, batch_end)
            if batch_df is not None and not batch_df.empty:
                append_batch_to_csv(batch_df, OUTPUT_CSV)
                print(f"Appended {len(batch_df)} rows to {OUTPUT_CSV}")
            else:
                print(f"(No data found for {batch_start})")

        print("Done writing batches.")

        run_manual_batches(driver)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()