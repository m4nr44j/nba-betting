import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def scrape_nba_rosters():
    driver = setup_driver()
    
    try:
        print("Loading NBA.com players page...")
        driver.get("https://www.nba.com/players")
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
        )
        
        print("Setting pagination to show all players...")
        pagination_dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "select"))
        )
        pagination_dropdown.click()
        
        all_option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//option[text()='All']"))
        )
        all_option.click()
        
        time.sleep(3)
        
        print("Scraping player data...")
        table = driver.find_element(By.CSS_SELECTOR, "table")
        rows = table.find_elements(By.TAG_NAME, "tr")[1:]
        
        player_teams = {}
        
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 2:
                    player_name = cells[0].text.strip().replace('\n', ' ')
                    team_abbr = cells[1].text.strip()
                    
                    if player_name and team_abbr:
                        player_teams[player_name] = team_abbr
            except Exception as e:
                print(f"Error processing row: {e}")
                continue
        
        print(f"Scraped {len(player_teams)} players")
        
        print("\nFirst 20 scraped players:")
        for i, (player, team) in enumerate(list(player_teams.items())[:20]):
            print(f"{i+1:2d}. {player} -> {team}")
        
        return player_teams
        
    except Exception as e:
        print(f"Error scraping data: {e}")
        return {}
    finally:
        driver.quit()

def update_database_teams(player_teams):
    if not player_teams:
        print("No player data to update")
        return
    
    try:
        engine = create_engine(os.getenv("SQL_ENGINE"))
        
        query = "SELECT player, team FROM latest_player_teams"
        current_players = pd.read_sql(query, engine)
        
        print(f"Found {len(current_players)} players in database")
        
        print("\nFirst 10 database players:")
        for i, (_, row) in enumerate(current_players.head(10).iterrows()):
            print(f"{i+1:2d}. {row['player']} -> {row['team']}")
        
        updates_made = 0
        with engine.connect() as conn:
            for _, row in current_players.iterrows():
                player_name = row['player']
                current_team = row['team']
                
                if player_name in player_teams:
                    new_team = player_teams[player_name]
                    if new_team != current_team:
                        update_query = text("""
                        UPDATE latest_player_teams 
                        SET team = :new_team 
                        WHERE player = :player_name
                        """)
                        conn.execute(update_query, {"new_team": new_team, "player_name": player_name})
                        print(f"Updated {player_name}: {current_team} -> {new_team}")
                        updates_made += 1
                    else:
                        print(f"No change needed for {player_name} ({current_team})")
                else:
                    print(f"Player {player_name} not found in current NBA roster")
            
            conn.commit()
        
        print(f"\nUpdate complete! {updates_made} players had team changes")
        
    except Exception as e:
        print(f"Error updating database: {e}")

def main():
    print("Starting NBA team update process...")
    
    player_teams = scrape_nba_rosters()
    
    if player_teams:
        update_database_teams(player_teams)
    else:
        print("Failed to scrape player data")

if __name__ == "__main__":
    main()