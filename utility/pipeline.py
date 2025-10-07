import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json
from sqlalchemy import create_engine
from datetime import datetime, timedelta

load_dotenv()


PLAYER_POSITIONS = {
    "Aaron Nesmith": "F",
    "Adem Bona": "C",
    "Admiral Schofield": "F",
    "Al Horford": "C",
    "Alperen Sengun": "C",
    "Andrew Wiggins": "F",
    "Anthony Davis": "F",
    "Anthony Edwards": "G",
    "Bam Adebayo": "C",
    "Ben Simmons": "G",
    "Bennedict Mathurin": "G",
    "Bismack Biyombo": "C",
    "Bojan Bogdanović": "F",
    "Bol Bol": "C",
    "Brandon Boston Jr.": "G",
    "Brandon Miller": "F",
    "Bruce Brown": "F",
    "Bryce McGowens": "G",
    "Buddy Hield": "G",
    "Caleb Houstan": "G",
    "Caris LeVert": "G",
    "Chet Holmgren": "F",
    "Chimezie Metu": "F",
    "Cody Martin": "F",
    "Cody Williams": "F",
    "Cody Zeller": "C",
    "Corey Kispert": "F",
    "DaQuan Jeffries": "G",
    "Dalano Banton": "G",
    "Damian Jones": "C",
    "Daniel Gafford": "C",
    "Dario Šarić": "F",
    "DeMar DeRozan": "F",
    "Deni Avdija": "F",
    "Devin Vassell": "G",
    "Dillon Brooks": "F",
    "Domantas Sabonis": "F",
    "Duncan Robinson": "F",
    "Dwight Powell": "C",
    "Dylan Windler": "G",
    "Eric Gordon": "G",
    "Evan Fournier": "G",
    "Evan Mobley": "F",
    "Filip Petrušev": "C",
    "Franz Wagner": "F",
    "Giannis Antetokounmpo": "F",
    "Gordon Hayward": "F",
    "Harry Giles": "F",
    "Isaac Okoro": "F",
    "Isaiah Jackson": "F",
    "Isaiah Stewart": "C",
    "Jaime Jaquez Jr.": "G",
    "Jarrett Allen": "C",
    "Jay Huff": "C",
    "Jaylen Brown": "G",
    "Jeremy Sochan": "F",
    "Jimmy Butler III": "F",
    "Joe Ingles": "G",
    "Johnny Furphy": "F",
    "Jontay Porter": "C",
    "Jordan Walsh": "G",
    "Josh Green": "G",
    "Julius Randle": "F",
    "Kai Jones": "F",
    "Karl-Anthony Towns": "C",
    "Karlo Matković": "C",
    "Kelly Olynyk": "F",
    "Kendall Brown": "G",
    "Kenrich Williams": "F",
    "Kevin Durant": "F",
    "Kevin Love": "F",
    "Kevon Looney": "F",
    "Khris Middleton": "F",
    "Klay Thompson": "G",
    "Kobe Brown": "G",
    "Kristaps Porziņģis": "C",
    "Kyle Anderson": "F",
    "Kyle Filipowski": "F",
    "Larry Nance Jr.": "F",
    "Lauri Markkanen": "F",
    "LeBron James": "F",
    "Luka Dončić": "G",
    "Luka Garza": "C",
    "Luke Kornet": "C",
    "Marvin Bagley III": "F",
    "Mason Plumlee": "C",
    "Mikal Bridges": "F",
    "Mike Muscala": "C",
    "Miles Bridges": "F",
    "Moritz Wagner": "C",
    "Myles Turner": "C",
    "Nick Richards": "C",
    "Nicolas Batum": "F",
    "Nikola Jokić": "F",
    "Nikola Jović": "F",
    "Pascal Siakam": "F",
    "Patrick Baldwin Jr.": "F",
    "Paul George": "F",
    "Peyton Watson": "F",
    "RJ Barrett": "G",
    "Reggie Bullock": "F",
    "Richaun Holmes": "F",
    "Robert Covington": "F",
    "Robert Williams": "C",
    "Sandro Mamukelashvili": "F",
    "Scottie Barnes": "F",
    "Seth Lundy": "G",
    "Svi Mykhailiuk": "G",
    "Taj Gibson": "F",
    "Talen Horton-Tucker": "F",
    "Terance Mann": "G",
    "Terry Taylor": "F",
    "Torrey Craig": "F",
    "Trentyn Flowers": "C",
    "Tristan Thompson": "C",
    "Tristan Vukcevic": "F",
    "Troy Brown Jr.": "F",
    "Ulrich Chomche": "C",
    "Victor Wembanyama": "C",
    "Wendell Moore Jr.": "G",
    "Zach Collins": "F",
    "Zach LaVine": "G",
    "Zion Williamson": "F",
    "Alex Ducas": "G",
    "Alperen Şengün": "C",
    "Guerschon Yabusele": "F",
    "Tony Bradley": "F",
}


def safe_to_float(value):
    val_str = str(value).strip()
    if val_str == "":
        return None
    try:
        return float(val_str)
    except ValueError:
        return None


def process_csv(start_date):
    from utility.get_new_data import get_new_data

    csv_columns = [
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

    sql_columns = [
        "player",
        "date",
        "age",
        "team",
        "hoa",
        "opp",
        "result",
        "gs",
        "mp",
        "fg",
        "fga",
        "fg_percent",
        "twop",
        "twopa",
        "twop_percent",
        "tpm",
        "threepa",
        "threep_percent",
        "ft",
        "fta",
        "ft_percent",
        "ts_percent",
        "orb",
        "drb",
        "trb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "pts",
        "gmsc",
        "bpm",
        "plus_minus",
        "pos",
        "player_additional",
    ]

    column_mapping = dict(zip(csv_columns, sql_columns))

    # Get new data from start_date to yesterday
    yesterday = datetime.now().date() - timedelta(days=1)
    df = get_new_data(start_date=start_date, end_date=yesterday)
    
    if df.empty:
        print("No new data available for the specified date range.")
        empty_df = pd.DataFrame(columns=csv_columns)
        empty_df.to_csv("csv/modified_data.csv", index=False, na_rep="None")
        return

    csv_file = "csv/all_data_full.csv"
    df.to_csv(csv_file, mode="a", header=False, index=False)

    df["BPM"] = 0
    df = df.drop(["Rk"], axis=1, errors="ignore")
    df.rename(columns=column_mapping, inplace=True)

    numeric_columns = [
        "fg_percent",
        "twop_percent",
        "threep_percent",
        "ft_percent",
        "ts_percent",
        "plus_minus",
    ]

    for column in numeric_columns:
        df[column] = df[column].apply(safe_to_float)

    df.to_csv("csv/modified_data.csv", index=False, na_rep="None")


def reset_tables(cursor):
    cursor.execute("DROP TABLE IF EXISTS public.nba_append;")
    cursor.execute("DROP TABLE IF EXISTS public.game_stats_append;")
    cursor.execute("DROP TABLE IF EXISTS public.latest_player_teams;")


def create_table(cursor):
    cursor.execute(
        """
        CREATE TABLE public.nba_append
        (
            id SERIAL PRIMARY KEY,
            player VARCHAR(50),
            date DATE,
            age VARCHAR(10),
            team VARCHAR(10),
            hoa CHAR(1),
            opp VARCHAR(10),
            result VARCHAR(20),
            gs CHAR(1),
            mp INTEGER,
            fg INTEGER,
            fga INTEGER,
            fg_percent NUMERIC(5,3) NULL,
            twop INTEGER,
            twopa INTEGER,
            twop_percent NUMERIC(5,3) NULL,
            tpm INTEGER,
            threepa INTEGER,
            threep_percent NUMERIC(5,3) NULL,
            ft INTEGER,
            fta INTEGER,
            ft_percent NUMERIC(5,3) NULL,
            ts_percent NUMERIC(5,3) NULL,
            orb INTEGER,
            drb INTEGER,
            trb INTEGER,
            ast INTEGER,
            stl INTEGER,
            blk INTEGER,
            tov INTEGER,
            pf INTEGER,
            pts INTEGER,
            gmsc NUMERIC(5,1),
            bpm NUMERIC(5,1),
            plus_minus NUMERIC(5,1),
            pos VARCHAR(4),
            player_additional VARCHAR(20)
        );
    """
    )


def load_data(cursor):
    csv_path = "csv/modified_data.csv"
    with open(csv_path, "r") as f:
        next(f)
        cursor.copy_from(
            f,
            "nba_append",
            sep=",",
            null="None",
            columns=(
                "player",
                "date",
                "age",
                "team",
                "hoa",
                "opp",
                "result",
                "gs",
                "mp",
                "fg",
                "fga",
                "fg_percent",
                "twop",
                "twopa",
                "twop_percent",
                "tpm",
                "threepa",
                "threep_percent",
                "ft",
                "fta",
                "ft_percent",
                "ts_percent",
                "orb",
                "drb",
                "trb",
                "ast",
                "stl",
                "blk",
                "tov",
                "pf",
                "pts",
                "gmsc",
                "bpm",
                "plus_minus",
                "pos",
                "player_additional",
            ),
        )


def perform_updates(cursor):
    updates = [
        "UPDATE public.nba_append SET result = REPLACE(result, ' (OT)', '');",
        "ALTER TABLE public.nba_append ADD COLUMN resultChar CHAR(1), ADD COLUMN score1 INTEGER, ADD COLUMN score2 INTEGER;",
        "UPDATE public.nba_append SET resultChar = TRIM(SUBSTRING(result FROM '^[WL]')), score1 = CAST(TRIM(SPLIT_PART(SUBSTRING(result FROM '[0-9]+-[0-9]+'), '-', 1)) AS INTEGER), score2 = CAST(TRIM(SPLIT_PART(SUBSTRING(result FROM '[0-9]+-[0-9]+'), '-', 2)) AS INTEGER);",
        "ALTER TABLE public.nba_append ADD COLUMN total_score INTEGER;",
        "UPDATE public.nba_append SET total_score = score1 + score2;",
        "ALTER TABLE public.nba_append DROP COLUMN result, DROP COLUMN score1, DROP COLUMN score2;",
        "ALTER TABLE public.nba_append ADD COLUMN p_r_a INTEGER GENERATED ALWAYS AS (pts + trb + ast) STORED, ADD COLUMN p_r INTEGER GENERATED ALWAYS AS (pts + trb) STORED, ADD COLUMN p_a INTEGER GENERATED ALWAYS AS (pts + ast) STORED, ADD COLUMN a_r INTEGER GENERATED ALWAYS AS (ast + trb) STORED;",
        "UPDATE public.nba_append SET age = CAST(SUBSTRING(age FROM 1 FOR 2) AS INTEGER);",
        "ALTER TABLE public.nba_append ALTER COLUMN age TYPE INTEGER USING CAST(age AS INTEGER);",
        "UPDATE public.nba_append SET hoa = CASE WHEN hoa = '' THEN '0' WHEN hoa = '@' THEN '1' END;",
        "ALTER TABLE public.nba_append ALTER COLUMN hoa TYPE INTEGER USING CAST(hoa AS INTEGER);",
        "UPDATE public.nba_append SET gs = CASE WHEN gs = '' THEN '0' WHEN gs = '*' THEN '1' END;",
        "ALTER TABLE public.nba_append ALTER COLUMN gs TYPE INTEGER USING CAST(gs AS INTEGER);",
        "DELETE FROM public.nba_append WHERE mp = 0;",
        "UPDATE public.nba_append SET fg_percent = COALESCE(fg_percent, 0), twop_percent = COALESCE(twop_percent, 0);",
        "DELETE FROM public.nba_append WHERE fg_percent = 0;",
        "ALTER TABLE public.nba_append ADD COLUMN month INTEGER;",
        "UPDATE public.nba_append SET month = EXTRACT(MONTH FROM date);",
        "ALTER TABLE public.nba_append ADD COLUMN days_since INTEGER;",
        "UPDATE public.nba_append SET days_since = date - DATE '2023-10-24';",
        "ALTER TABLE public.nba_append DROP COLUMN threepa, DROP COLUMN threep_percent, DROP COLUMN fta, DROP COLUMN twopa;",
        "ALTER TABLE public.nba_append RENAME COLUMN resultChar TO result;",
        "UPDATE public.nba_append SET result = CASE WHEN result = 'L' THEN 0 WHEN result = 'W' THEN 1 END;",
        "ALTER TABLE public.nba_append ALTER COLUMN result TYPE INTEGER USING CAST(result AS INTEGER);",
        "UPDATE public.nba_append SET team = REPLACE(team, 'CHO', 'CHA'), opp = REPLACE(opp, 'CHO', 'CHA');",
        "UPDATE public.nba_append SET team = REPLACE(team, 'PHO', 'PHX'), opp = REPLACE(opp, 'PHO', 'PHX');",
        "UPDATE public.nba_append SET team = REPLACE(team, 'BRK', 'BKN'), opp = REPLACE(opp, 'BRK', 'BKN');",
        """INSERT INTO public.nba
            (player, date, age, team, hoa, opp, result, total_score, gs, mp, fg, fga, fg_percent, twop, twop_percent, tpm, ft, ft_percent, ts_percent, orb, drb, trb, ast, stl, blk, tov, pf, pts, gmsc, bpm, plus_minus, pos, player_additional, month, days_since)
        SELECT 
            player, date, age, team, hoa, opp, result, total_score, gs, mp, fg, fga, fg_percent, twop, twop_percent, tpm, ft, ft_percent, ts_percent, orb, drb, trb, ast, stl, blk, tov, pf, pts, gmsc, bpm, plus_minus, pos, player_additional, month, days_since
        FROM public.nba_append;
        """,
    ]
    for command in updates:
        cursor.execute(command)


def update_game_stats_schema(cursor):
    new_columns = [
        "teammates_tpm JSONB",
        "teammates_pr JSONB", 
        "teammates_pa JSONB",
        "teammates_ar JSONB",
        "teammates_pra JSONB",
        "teammates_blocks JSONB",
        "teammates_minutes JSONB",
        "opponents_tpm JSONB",
        "opponents_pr JSONB",
        "opponents_pa JSONB", 
        "opponents_ar JSONB",
        "opponents_pra JSONB",
        "opponents_minutes JSONB"
    ]
    
    for column_def in new_columns:
        column_name = column_def.split()[0]
        try:
            cursor.execute(f"ALTER TABLE public.game_stats ADD COLUMN {column_def};")
        except Exception:
            pass


def create_game_stats_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_stats_append
        (
            game_id SERIAL PRIMARY KEY,
            date DATE,
            team VARCHAR(10),
            opp VARCHAR(10),
            teammates_points JSONB,
            teammates_rebounds JSONB,
            teammates_assists JSONB,
            teammates_tpm JSONB,
            teammates_pr JSONB,
            teammates_pa JSONB,
            teammates_ar JSONB,
            teammates_pra JSONB,
            teammates_blocks JSONB,
            teammates_turnovers JSONB,
            teammates_minutes JSONB,
            opponents_points JSONB,
            opponents_rebounds JSONB,
            opponents_assists JSONB,
            opponents_tpm JSONB,
            opponents_pr JSONB,
            opponents_pa JSONB,
            opponents_ar JSONB,
            opponents_pra JSONB,
            opponents_blocks JSONB,
            opponents_turnovers JSONB,
            opponents_minutes JSONB
        );
    """
    )


def update_game_stats(cursor):
    cursor.execute("SELECT DISTINCT date, team, opp FROM public.nba_append;")
    new_games = cursor.fetchall()

    if not new_games:
        return

    rows_to_insert = []
    for game_date, team, opponent in new_games:
        team_stats = {
            metric: {}
            for metric in [
                "points",
                "rebounds",
                "assists",
                "tpm",
                "pr",
                "pa",
                "ar",
                "pra",
                "blocks",
                "turnovers",
                "minutes",
            ]
        }
        opponent_stats = {
            metric: {}
            for metric in [
                "points",
                "rebounds",
                "assists",
                "tpm",
                "pr",
                "pa",
                "ar",
                "pra",
                "blocks",
                "turnovers",
                "minutes",
            ]
        }

        for relation, team_to_query in [("teammates", team), ("opponent", opponent)]:
            cursor.execute(
                """
                SELECT player, 
                       COALESCE(pts,0), COALESCE(trb,0), COALESCE(ast,0), 
                       COALESCE(tpm,0), COALESCE(blk,0), COALESCE(tov,0), COALESCE(mp,0)
                FROM public.nba
                WHERE date = %s AND team = %s;
            """,
                (game_date, team_to_query),
            )
            stats_for_game = cursor.fetchall()

            if not stats_for_game:
                print(
                    f"Warning: No player stats found for {relation} ({team_to_query}) on {game_date}."
                )

            for player, pts, trb, ast, tpm, blk, tov, mp in stats_for_game:
                metrics = {
                    "points": pts,
                    "rebounds": trb,
                    "assists": ast,
                    "tpm": tpm,
                    "pr": pts + trb,
                    "pa": pts + ast,
                    "ar": ast + trb,
                    "pra": pts + trb + ast,
                    "blocks": blk,
                    "turnovers": tov,
                    "minutes": mp,
                }
                target_dict = team_stats if relation == "teammates" else opponent_stats
                for metric_name, value in metrics.items():
                    target_dict[metric_name][player] = value

        rows_to_insert.append(
            [
                game_date,
                team,
                opponent,
                Json(team_stats["points"]),
                Json(team_stats["rebounds"]),
                Json(team_stats["assists"]),
                Json(team_stats["tpm"]),
                Json(team_stats["pr"]),
                Json(team_stats["pa"]),
                Json(team_stats["ar"]),
                Json(team_stats["pra"]),
                Json(team_stats["blocks"]),
                Json(team_stats["turnovers"]),
                Json(team_stats["minutes"]),
                Json(opponent_stats["points"]),
                Json(opponent_stats["rebounds"]),
                Json(opponent_stats["assists"]),
                Json(opponent_stats["tpm"]),
                Json(opponent_stats["pr"]),
                Json(opponent_stats["pa"]),
                Json(opponent_stats["ar"]),
                Json(opponent_stats["pra"]),
                Json(opponent_stats["blocks"]),
                Json(opponent_stats["turnovers"]),
                Json(opponent_stats["minutes"]),
            ]
        )

    if rows_to_insert:
        cursor.executemany(
            """
            INSERT INTO game_stats_append
            (date, team, opp, teammates_points, teammates_rebounds, teammates_assists,
             teammates_tpm, teammates_pr, teammates_pa, teammates_ar, teammates_pra, teammates_blocks, teammates_turnovers, teammates_minutes,
             opponents_points, opponents_rebounds, opponents_assists, opponents_tpm, opponents_pr, opponents_pa, opponents_ar, opponents_pra, opponents_blocks, opponents_turnovers, opponents_minutes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            rows_to_insert,
        )

        cursor.execute(
            """
            INSERT INTO public.game_stats
            SELECT * FROM public.game_stats_append gsa
            WHERE NOT EXISTS (
                SELECT 1 FROM public.game_stats gs 
                WHERE gs.date = gsa.date 
                AND gs.team = gsa.team 
                AND gs.opp = gsa.opp
            )
        """
        )


def create_most_recent_player_team_table(cursor):
    for player, pos in PLAYER_POSITIONS.items():
        cursor.execute(
            "UPDATE public.nba SET pos = %s WHERE player = %s;", (pos, player)
        )

    cursor.execute(
        """
        WITH RankedPlayerTeams AS (
            SELECT
                player, team, pos, date, pts, trb, ast, tpm, stl, blk, tov, p_r, p_a, a_r, p_r_a,
                ROW_NUMBER() OVER (PARTITION BY player ORDER BY date DESC) AS rn
            FROM public.nba
        ), Last15Games AS (
            SELECT
                player, pts, trb, ast, tpm, stl, blk, tov, p_r, p_a, a_r, p_r_a
            FROM (
                SELECT
                    player, pts, trb, ast, tpm, stl, blk, tov, p_r, p_a, a_r, p_r_a,
                    ROW_NUMBER() OVER (PARTITION BY player ORDER BY date DESC) AS game_number
                FROM public.nba
            ) AS recent_games
            WHERE game_number <= 15
        ), Averages AS (
            SELECT
                player,
                ROUND(AVG(pts), 2) AS avg_pts,
                ROUND(AVG(trb), 2) AS avg_trb,
                ROUND(AVG(ast), 2) AS avg_ast,
                ROUND(AVG(tpm), 2) AS avg_tpm,
                ROUND(AVG(stl), 2) AS avg_stl,
                ROUND(AVG(blk), 2) AS avg_blk,
                ROUND(AVG(tov), 2) AS avg_tov,
                ROUND(AVG(p_r), 2) AS avg_p_r,
                ROUND(AVG(p_a), 2) AS avg_p_a,
                ROUND(AVG(a_r), 2) AS avg_a_r,
                ROUND(AVG(p_r_a), 2) AS avg_p_r_a
            FROM Last15Games
            GROUP BY player
        )
        SELECT
            r.player, r.team, r.pos, a.avg_pts, a.avg_trb, a.avg_ast, a.avg_tpm,
            a.avg_stl, a.avg_blk, a.avg_tov, a.avg_p_r, a.avg_p_a, a.avg_a_r, a.avg_p_r_a
        INTO public.latest_player_teams
        FROM RankedPlayerTeams r
        JOIN Averages a ON r.player = a.player
        WHERE r.rn = 1;
    """
    )


def load_data_csv():
    conn = create_engine(os.getenv("SQL_ENGINE"))
    df = pd.read_sql("SELECT * FROM nba;", conn)
    df.to_csv("csv/sql.csv", encoding="utf-8", index=False)
    conn.dispose()


def run_pipeline(start_date):
    conn = None
    cursor = None
    
    try:
        process_csv(start_date)
        
        import os
        if not os.path.exists("csv/modified_data.csv"):
            print("No new data available for the specified date range.")
            return
            
        import pandas as pd
        try:
            df_check = pd.read_csv("csv/modified_data.csv")
            if df_check.empty:
                print("No new data available for the specified date range.")
                return
        except (pd.errors.EmptyDataError, FileNotFoundError):
            print("No new data available for the specified date range.")
            return
        
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            port=os.getenv("DB_PORT"),
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1")
        cursor.fetchone()
        reset_tables(cursor)
        conn.commit()
        create_table(cursor)
        load_data(cursor)
        perform_updates(cursor)
        update_game_stats_schema(cursor)
        create_most_recent_player_team_table(cursor)
        create_game_stats_table(cursor)
        update_game_stats(cursor)
        conn.commit()
        print("Pipeline executed successfully.")
        load_data_csv()
        
    except Exception as e:
        print(f"An error occurred in pipeline: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                print(f"Rollback failed: {rollback_error}")
                if cursor:
                    cursor.close()
                conn.close()
                try:
                    conn = psycopg2.connect(
                        host=os.getenv("DB_HOST"),
                        dbname=os.getenv("DB_NAME"),
                        user=os.getenv("DB_USER"),
                        password=os.getenv("DB_PASS"),
                        port=os.getenv("DB_PORT"),
                    )
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":

    start_date = datetime.now().date() - timedelta(days=7)
    run_pipeline(start_date)
