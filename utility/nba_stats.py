import json
import time
from datetime import datetime, timedelta, timezone

import requests


def get_nba_game_event_ids(date_yyyymmdd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_yyyymmdd}"
    try:
        data = requests.get(url, timeout=10).json()
        return [event["id"] for event in data.get("events", []) if "id" in event]
    except (requests.RequestException, json.JSONDecodeError):
        return []


def get_nba_game_summary(event_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
    try:
        return requests.get(url, timeout=15).json()
    except (requests.RequestException, json.JSONDecodeError):
        return None


def extract_player_stats(summary_data):
    if not summary_data:
        return []
    players_out = []
    for team in summary_data.get("boxscore", {}).get("players", []):
        team_name = team.get("team", {}).get("displayName", "Unknown Team")
        for stat_group in team.get("statistics", []):
            labels = stat_group.get("labels", [])
            for athlete in stat_group.get("athletes", []):
                player_name = athlete.get("athlete", {}).get(
                    "displayName", "Unknown Player"
                )

                player_name = player_name.replace("Jimmy Butler", "Jimmy Butler III")
                player_name = player_name.replace("Ronald Holland II", "Ron Holland")
                player_name = player_name.replace(
                    "Bub Carrington", "Carlton Carrington"
                )
                player_name = player_name.replace("Luka Doncic", "Luka Dončić")
                player_name = player_name.replace("Nikola Jokic", "Nikola Jokić")
                player_name = player_name.replace("Nikola Vucevic", "Nikola Vučević")
                player_name = player_name.replace(
                    "Jonas Valanciunas", "Jonas Valančiūnas"
                )
                player_name = player_name.replace(
                    "Bojan Bogdanovic", "Bojan Bogdanović"
                )
                player_name = player_name.replace("Dario Saric", "Dario Šarić")
                player_name = player_name.replace(
                    "Bogdan Bogdanovic", "Bogdan Bogdanović"
                )
                player_name = player_name.replace("Karlo Matkovic", "Karlo Matković")
                player_name = player_name.replace(
                    "Boban Marjanovic", "Boban Marjanović"
                )
                player_name = player_name.replace("Jusuf Nurkic", "Jusuf Nurkić")
                player_name = player_name.replace("Luka Samanic", "Luka Šamanić")
                player_name = player_name.replace("Nikola Jovic", "Nikola Jović")
                player_name = player_name.replace("Vasilije Micic", "Vasilije Micić")
                player_name = player_name.replace("Vit Krejci", "Vít Krejčí")
                player_name = player_name.replace(
                    "Tristan Vukcevic", "Tristan Vukčević"
                )

                raw_stats = athlete.get("stats", [])
                if len(raw_stats) != len(labels):
                    continue
                row = dict(zip(labels, raw_stats))
                pts = safe_int(row.get("PTS"))
                trb = safe_int(row.get("REB"))
                ast = safe_int(row.get("AST"))
                tpm = safe_three_point(row.get("3PT"))

                def combine(*vals):
                    nums = [v for v in vals if v is not None]
                    return "" if len(nums) != len(vals) else str(sum(nums))

                stats_proc = {
                    "pts": str(pts) if pts is not None else "",
                    "trb": str(trb) if trb is not None else "",
                    "ast": str(ast) if ast is not None else "",
                    "tpm": str(tpm) if tpm is not None else "",
                    "p_r": combine(pts, trb),
                    "p_a": combine(pts, ast),
                    "a_r": combine(ast, trb),
                    "p_r_a": combine(pts, trb, ast),
                }
                players_out.append(
                    {"Team": team_name, "Player": player_name, "Stats": stats_proc}
                )
    return players_out


def safe_int(value):
    if value in ("N/A", None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def safe_three_point(value):
    if value in ("N/A", None, ""):
        return None
    try:
        parts = str(value).split("-")
        return int(parts[0]) if parts else None
    except (ValueError, IndexError, TypeError):
        return None