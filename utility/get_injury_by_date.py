from datetime import datetime, timedelta
import json
import os
import re
import shutil
import sys
from collections import defaultdict

import fitz
from pandas._libs.tslibs import delta_to_nanoseconds
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import JSON_INJURY_FILE, NBA_TEAMS, PDF_DOWNLOAD_DIR

load_dotenv()

INJURY_FILE = JSON_INJURY_FILE
TEAM_ABBR = NBA_TEAMS

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
    if raw_status == "Questionable" or raw_status == "Probable":
        return "Game Time Decision"
    if raw_status in {"Out", "Doubtful"}:
        return "Out"
    return None


def clear_pdf_folder(folder: str = PDF_DOWNLOAD_DIR):
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)


def download_injury_report_pdf(date_str: str, time_str: str) -> str:
    filename = f"Injury-Report_{date_str}.pdf"
    filepath = os.path.join(PDF_DOWNLOAD_DIR, filename)

    url = (
        f"https://ak-static.cms.nba.com/referee/injury/"
        f"Injury-Report_{date_str}_{time_str}.pdf"
    )

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
            fallback_url = (
                "https://ak-static.cms.nba.com/referee/injury/"
                f"Injury-Report_{date_str}_12PM.pdf"
            )
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


def fetch_and_process_injury_report(
    date_str: str,
    time_str: str,
    local_pdf_dir: str | None = None,
):
    if local_pdf_dir:
        local_pdf_path = os.path.join(local_pdf_dir, f"Injury-Report_{date_str}.pdf")
        if os.path.exists(local_pdf_path):
            injury_data = parse_injury_report_pdf(local_pdf_path)
            write_injury_data_to_json(injury_data)
            return injury_data
        else:
            print(
                f"Local injury report not found at {local_pdf_path}; falling back to download."
            )

    clear_pdf_folder(PDF_DOWNLOAD_DIR)
    pdf_path = download_injury_report_pdf(date_str, time_str)
    injury_data = parse_injury_report_pdf(pdf_path)
    write_injury_data_to_json(injury_data)
    return injury_data


flip = normalize_player_name
norm_status = normalize_injury_status


def get(date_str, time_str, local_pdf_dir: str | None = None):
    return fetch_and_process_injury_report(date_str, time_str, local_pdf_dir=local_pdf_dir)


if __name__ == "__main__":
    today = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%d")
    get(today, "06PM")
