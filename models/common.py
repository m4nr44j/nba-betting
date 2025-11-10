import json
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


from config import CSV_SQL_DATA_FILE, JSON_INJURY_FILE

def load_nba(player):
    try:
        df = pd.read_csv(CSV_SQL_DATA_FILE)
        df["date"] = pd.to_datetime(df["date"])
        player_df = df[df["player"] == player]
        return player_df
    except Exception as e:
        print(f"Error occurred while reading the file or filtering data: {e}")
        return None


def load_player_positions(conn):
    try:
        query = "SELECT * FROM latest_player_teams;"
        df = pd.read_sql(query, conn)
        return df
    except OSError as e:
        print(
            f"Error occurred while connecting to the database or executing query: {e}"
        )
        return None


def aggregate_position_data_game_stats(json_data, exclude_player, positions_df):
    if exclude_player in json_data:
        del json_data[exclude_player]
    position_totals = {"G": 0, "F": 0, "C": 0}
    for player, value in json_data.items():
        pos = positions_df.loc[positions_df["player"] == player, "pos"].values
        if pos.size > 0:
            position_totals[pos[0]] += value
    return position_totals


def load_game_stats(player, conn):
    positions_df = load_player_positions(conn)
    if positions_df is None:
        return pd.DataFrame()
    try:
        query = """
            SELECT *
            FROM game_stats
            WHERE teammates_points::jsonb ? %s;
            """
        df = pd.read_sql(query, conn, params=(player,))

        stats_fields = [
            "teammates_points",
            "teammates_rebounds",
            "teammates_assists",
            "opponents_points",
            "opponents_rebounds",
            "opponents_assists",
            "teammates_turnovers",
            "opponents_blocks",
            "opponents_turnovers",
        ]
        for stat_field in stats_fields:
            df[stat_field] = df[stat_field].apply(
                lambda x: aggregate_position_data_game_stats(x, player, positions_df)
            )
        for field in stats_fields:
            df_field = df[field].apply(pd.Series)
            df_field.columns = [f"{field}_{col}" for col in df_field.columns]
            df = pd.concat([df, df_field], axis=1)
            df.drop(field, axis=1, inplace=True)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except OSError as e:
        print(
            f"Error occurred while connecting to the database or executing query: {e}"
        )
        return pd.DataFrame()


def get_last_data(player, conn):
    query = """
    SELECT mp, plus_minus
    FROM nba
    WHERE player = %s
    ORDER BY date DESC
    LIMIT 5
    """
    df = pd.read_sql(query, conn, params=(player,))
    avg_mp = df["mp"].mean()
    avg_plus_minus = df["plus_minus"].mean()
    return avg_mp, avg_plus_minus


def aggregate_position_data_predictions(stat_dict, df):
    position_data = {"G": 0, "F": 0, "C": 0}
    for player, stat in stat_dict.items():
        position = df.loc[df["player"] == player, "pos"].values
        if position.size > 0:
            position_data[position[0]] += stat
        else:
            continue
    return position_data


def get_soft_predictions(team, opp, player_df, player):
    from models.soft_predictor import predict_player_stat

    injuries = {}
    with open(JSON_INJURY_FILE, "r") as file:
        rosters = json.load(file)
        for team_players in rosters.values():
            for player_info in team_players:
                player_name = player_info["player"]
                status = player_info["status"]
                injuries[player_name] = status

    team_players = player_df[player_df["team"] == team]["player"].tolist()
    team_players.remove(player)
    opp_players = player_df[player_df["team"] == opp]["player"].tolist()

    team_stats = {"pts": {}, "trb": {}, "ast": {}, "tov": {}}
    opp_stats = {"pts": {}, "trb": {}, "ast": {}, "blk": {}, "tov": {}}

    def populate_player_stats(players, stats, team_of_player):
        count = 0
        player_list = []
        for player in players:
            status = "None"
            if player in injuries:
                status = injuries[player]
            for key in stats:
                predicted_value = predict_player_stat(
                    player, opp if team_of_player == team else team, key, 1
                )
                if pd.isna(predicted_value):
                    count = count + 1
                    player_list.append(player)
                    predicted_value = player_df.loc[
                        player_df["player"] == player, f"avg_{key}"
                    ].values[0]
                stats[key][player] = predicted_value
                if status == "Out" or status == "Out For Season":
                    stats[key][player] = 0
                elif status == "Game Time Decision":
                    stats[key][player] *= 0.85

    populate_player_stats(team_players, team_stats, team)
    populate_player_stats(opp_players, opp_stats, opp)

    results = {
        "team": [team],
        "opp": [opp],
        "teammates_points": [
            aggregate_position_data_predictions(team_stats["pts"], player_df)
        ],
        "teammates_rebounds": [
            aggregate_position_data_predictions(team_stats["trb"], player_df)
        ],
        "teammates_assists": [
            aggregate_position_data_predictions(team_stats["ast"], player_df)
        ],
        "opponents_points": [
            aggregate_position_data_predictions(opp_stats["pts"], player_df)
        ],
        "opponents_rebounds": [
            aggregate_position_data_predictions(opp_stats["trb"], player_df)
        ],
        "opponents_assists": [
            aggregate_position_data_predictions(opp_stats["ast"], player_df)
        ],
        "teammates_turnovers": [
            aggregate_position_data_predictions(team_stats["tov"], player_df)
        ],
        "opponents_blocks": [
            aggregate_position_data_predictions(opp_stats["blk"], player_df)
        ],
        "opponents_turnovers": [
            aggregate_position_data_predictions(opp_stats["tov"], player_df)
        ],
    }

    df = pd.DataFrame(results)
    for field in [
        "teammates_points",
        "teammates_rebounds",
        "teammates_assists",
        "opponents_points",
        "opponents_rebounds",
        "opponents_assists",
        "teammates_turnovers",
        "opponents_blocks",
        "opponents_turnovers",
    ]:
        df_field = pd.json_normalize(df[field].iloc[0])
        df_field.columns = [f"{field}_{col}" for col in df_field.columns]
        df = pd.concat([df, df_field], axis=1)
        df.drop(field, axis=1, inplace=True)
    return df


def get_recent_team_form(team, opp, conn):
    query_team = """
    SELECT AVG(pts) as recent_pts, AVG(plus_minus) as recent_plus_minus,
           AVG(total_score) as recent_pace
    FROM nba
    WHERE team = %s
    ORDER BY date DESC
    LIMIT 5
    """

    query_opp = """
    SELECT AVG(pts) as recent_pts_allowed, AVG(plus_minus) as recent_plus_minus,
           AVG(total_score) as recent_pace
    FROM nba
    WHERE team = %s
    ORDER BY date DESC
    LIMIT 5
    """

    team_form = pd.read_sql(query_team, conn, params=(team,))
    opp_form = pd.read_sql(query_opp, conn, params=(opp,))

    return {
        "team_recent_pts": team_form.iloc[0]["recent_pts"],
        "team_recent_plus_minus": team_form.iloc[0]["recent_plus_minus"],
        "team_recent_pace": team_form.iloc[0]["recent_pace"],
        "opp_recent_pts_allowed": opp_form.iloc[0]["recent_pts_allowed"],
        "opp_recent_plus_minus": opp_form.iloc[0]["recent_plus_minus"],
        "opp_recent_pace": opp_form.iloc[0]["recent_pace"],
    }


def get_consistency(feature, limit, min_minutes):
    try:
        conn = create_engine(os.getenv("SQL_ENGINE"))

        query = f"""
                WITH RecentGames AS (
                    SELECT
                        player,
                        team,
                        {feature},
                        mp,
                        ROW_NUMBER() OVER (PARTITION BY player ORDER BY date DESC) AS rn
                    FROM
                        nba
                )
                SELECT
                    player,
                    team,
                    AVG({feature}) AS average_{feature},
                    STDDEV({feature}) AS stddev_{feature},
                    CASE
                        WHEN AVG({feature}) = 0 THEN NULL
                        ELSE (STDDEV({feature}) / AVG({feature}))
                    END AS cv_{feature}
                FROM
                    RecentGames
                WHERE
                    rn <= 5
                GROUP BY
                    player, team
                HAVING
                    AVG({feature}) > 2 AND
                    AVG(mp) > {min_minutes}
                ORDER BY
                    cv_{feature} ASC
                FETCH NEXT {limit} ROWS ONLY;
        """
        player_data = pd.read_sql_query(query, conn)

        player_names = player_data["player"].tolist()
        return player_names, player_data

    except Exception as e:
        print(f"An error occurred: {e}")
        return [], pd.DataFrame()
