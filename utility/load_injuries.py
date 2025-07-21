import requests
import pandas as pd
import json
import os
from dotenv import load_dotenv

load_dotenv()

INJURY_FILE = 'json/injury.json'

def write_injury_data_to_json(data: dict, path: str = None):
    """Write injury data to JSON file"""
    if path is None:
        path = INJURY_FILE
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_injuries_from_api():
    """Load injury data from RotoWire API"""
    api_endpoint_url = "https://www.rotowire.com/basketball/tables/injury-report.php?team=ALL&pos=ALL"

    try:
        response = requests.get(api_endpoint_url)
        response.raise_for_status() 
        data = response.json()

        if not isinstance(data, list) or not data:
            print("Warning: Received empty or unexpected data format from API.")
            team_grouped = {} 
        else:
            df = pd.DataFrame(data)

            required_cols = ['player', 'team', 'status']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"Missing required columns in API response. Found: {df.columns}. Needed: {required_cols}")

            df_final = df[required_cols].copy()
            df_final['player'] = df_final['player'].replace('Jimmy Butler', 'Jimmy Butler III')

            team_grouped = (
                df_final
                .groupby('team')
                .apply(lambda group: group[['player', 'status']].to_dict(orient='records'), include_groups=False)
                .to_dict()
            )

        write_injury_data_to_json(team_grouped)
        return team_grouped

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from API: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        return {}
    except KeyError as e:
        print(f"Error processing data: Missing key {e}")
        return {}
    except ValueError as e:
        print(f"Error: {e}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {}

def load_injuries():
    """Load injury data from RotoWire API"""
    return load_injuries_from_api()

if __name__ == '__main__':
    load_injuries()