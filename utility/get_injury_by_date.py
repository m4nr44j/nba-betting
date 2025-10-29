import json
import os
import re
import shutil
from collections import defaultdict

import fitz
import requests
from dotenv import load_dotenv

load_dotenv()

INJURY_FILE = "json/injury.json"

TEAM_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Detroit Pistons": "DET",
    "Indiana Pacers": "IND",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "New York Knicks": "NYK",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Toronto Raptors": "TOR",
    "Washington Wizards": "WAS",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Los Angeles Clippers": "LAC",
    "LA Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "Oklahoma City Thunder": "OKC",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Utah Jazz": "UTA",
}

PLAYER_ENTRY_PAT = re.compile(
    r"(?P<player>[\w.'\- ]+,\s*[\w.'\- ]+)\s+"
    r"(?P<status>Available|Out|Questionable|Probable|Doubtful)\b"
    r"(?P<reason>.*?)(?="
    r"[\w.'\- ]+,\s*[\w.'\- ]+\s+(?:Available|Out|Questionable|Probable|Doubtful)\b|$"
    r")",
    re.DOTALL,
)

SUFFIXES = {"Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV", "V"}


def normalize_player_name(name: str) -> str:
    try:
        last_part, first_part = [s.strip() for s in name.split(",", 1)]
    except ValueError:
        return name.strip()

    suffix = None
    last_tokens = last_part.split()
    if last_tokens and last_tokens[-1] in SUFFIXES:
        suffix = last_tokens.pop()
    last_clean = " ".join(last_tokens)

    full = f"{first_part} {last_clean}".strip()
    if suffix:
        full = f"{full} {suffix}"
    return full


def normalize_injury_status(raw_status: str) -> str | None:
    if raw_status == "Questionable":
        return "Game Time Decision"
    if raw_status in {"Out", "Doubtful"}:
        return "Out"
    return None


def clear_pdf_folder(folder="pdf"):
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)


def download_injury_report_pdf(date_str: str, time_str: str) -> str:
    url = f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date_str}_{time_str}.pdf"
    filename = f"Injury-Report_{date_str}.pdf"
    filepath = os.path.join("pdf", filename)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Referer": "https://www.nba.com/",
        "Accept": "application/pdf,*/*",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            f.write(response.content)

        return filepath

    except requests.exceptions.RequestException as e:
        
        if time_str == "06PM":
            fallback_url = f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date_str}_12PM.pdf"
            try:
                response = requests.get(fallback_url, headers=headers, timeout=10)
                response.raise_for_status()

                with open(filepath, "wb") as f:
                    f.write(response.content)
                return filepath

            except requests.exceptions.RequestException as fallback_e:
                return ""
        
        return ""


def write_injury_data_to_json(data: dict, path: str | None = None):
    if path is None:
        path = INJURY_FILE

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_injury_report_pdf(pdf_path: str) -> dict:
    if not pdf_path or not os.path.exists(pdf_path):
        return {}

    injury_data = defaultdict(list)

    try:
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            current_team = None
            i = 0
            while i < len(lines):
                line = lines[i]

                if line in TEAM_ABBR.values() or line in TEAM_ABBR.keys():
                    current_team = TEAM_ABBR.get(line)
                    i += 1
                    continue

                if current_team and i + 2 < len(lines):
                    if line in [
                        "Player Name",
                        "Current Status",
                        "Reason",
                        "Game Date",
                        "Game Time",
                        "Matchup",
                        "Team",
                    ]:
                        i += 1
                        continue

                    if ("," in line and any(c.isalpha() for c in line)) or (
                        line.replace(" ", "").replace("'", "").isalnum()
                        and len(line) > 3
                    ):
                        player_name = line
                        potential_status = lines[i + 1] if i + 1 < len(lines) else ""
                        potential_reason = lines[i + 2] if i + 2 < len(lines) else ""

                        if potential_status in [
                            "Out",
                            "Questionable",
                            "Probable",
                            "Doubtful",
                            "Available",
                        ]:

                            if "," in player_name:
                                normalized_name = normalize_player_name(player_name)
                            else:
                                normalized_name = player_name

                            normalized_status = normalize_injury_status(
                                potential_status
                            )
                            if normalized_status:
                                injury_data[current_team].append(
                                    {
                                        "player": normalized_name,
                                        "status": normalized_status,
                                        "reason": potential_reason,
                                    }
                                )

                            i += 3
                            continue

                i += 1

        doc.close()

    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return {}

    return dict(injury_data)


def fetch_and_process_injury_report(date_str: str, time_str: str):
    clear_pdf_folder("pdf")
    pdf_path = download_injury_report_pdf(date_str, time_str)
    injury_data = parse_injury_report_pdf(pdf_path)
    write_injury_data_to_json(injury_data)
    return injury_data


flip = normalize_player_name
norm_status = normalize_injury_status


def get(date_str, time_str):
    return fetch_and_process_injury_report(date_str, time_str)


if __name__ == "__main__":
    get("2025-10-27", "06PM")
