import json
import numpy as np
import pandas as pd
from scipy.spatial import distance
from sklearn.preprocessing import MinMaxScaler


def load_data():
    df = pd.read_csv("csv/sql.csv")
    return df

def _compute_missing_by_position(team: str, injuries_path: str = "json/injury.json", sql_path: str = "csv/sql.csv", recent_games: int = 8) -> dict:
    try:
        with open(injuries_path, "r", encoding="utf-8") as f:
            injury_rosters = json.load(f)
    except Exception:
        injury_rosters = {}

    status_weight = {"Out": 1.0, "Out For Season": 1.0, "Game Time Decision": 0.5}
    team_entries = injury_rosters.get(team, [])
    injured_players = [(e.get("player", ""), status_weight.get(e.get("status", "None"), 0.0)) for e in team_entries]

    base_zero = {
        "missing_points_G": 0.0, "missing_points_F": 0.0, "missing_points_C": 0.0,
        "missing_rebounds_G": 0.0, "missing_rebounds_F": 0.0, "missing_rebounds_C": 0.0,
        "missing_assists_G": 0.0, "missing_assists_F": 0.0, "missing_assists_C": 0.0,
    }

    if not injured_players:
        return base_zero

    try:
        df = pd.read_csv(sql_path)
        df["date"] = pd.to_datetime(df["date"])
    except Exception:
        return base_zero

    agg = {
        ("points", "G"): 0.0, ("points", "F"): 0.0, ("points", "C"): 0.0,
        ("rebounds", "G"): 0.0, ("rebounds", "F"): 0.0, ("rebounds", "C"): 0.0,
        ("assists", "G"): 0.0, ("assists", "F"): 0.0, ("assists", "C"): 0.0,
    }

    for player_name, weight in injured_players:
        if weight <= 0:
            continue
        pdf = df[df["player"] == player_name].sort_values("date", ascending=False).head(recent_games)
        if pdf.empty:
            continue
        pos = pdf.iloc[0].get("pos", None)
        if pos not in {"G", "F", "C"}:
            continue
        try:
            pts_mean = float(pdf["pts"].mean())
            trb_mean = float(pdf["trb"].mean())
            ast_mean = float(pdf["ast"].mean())
        except Exception:
            continue
        agg[("points", pos)] += pts_mean * float(weight)
        agg[("rebounds", pos)] += trb_mean * float(weight)
        agg[("assists", pos)] += ast_mean * float(weight)

    return {
        "missing_points_G": agg[("points", "G")],
        "missing_points_F": agg[("points", "F")],
        "missing_points_C": agg[("points", "C")],
        "missing_rebounds_G": agg[("rebounds", "G")],
        "missing_rebounds_F": agg[("rebounds", "F")],
        "missing_rebounds_C": agg[("rebounds", "C")],
        "missing_assists_G": agg[("assists", "G")],
        "missing_assists_F": agg[("assists", "F")],
        "missing_assists_C": agg[("assists", "C")],
    }

def _adjust_for_missing(base_pred: float, market: str, player_pos: str, missing_ctx: dict) -> float:
    player_pos = player_pos if player_pos in {"G", "F", "C"} else "G"

    m_pts = {
        "G": float(missing_ctx.get("missing_points_G", 0.0)),
        "F": float(missing_ctx.get("missing_points_F", 0.0)),
        "C": float(missing_ctx.get("missing_points_C", 0.0)),
    }
    m_ast = {
        "G": float(missing_ctx.get("missing_assists_G", 0.0)),
        "F": float(missing_ctx.get("missing_assists_F", 0.0)),
        "C": float(missing_ctx.get("missing_assists_C", 0.0)),
    }
    m_trb = {
        "G": float(missing_ctx.get("missing_rebounds_G", 0.0)),
        "F": float(missing_ctx.get("missing_rebounds_F", 0.0)),
        "C": float(missing_ctx.get("missing_rebounds_C", 0.0)),
    }

    L_pts = {
        "G": {"G": 0.08, "F": 0.03, "C": 0.01},
        "F": {"G": 0.03, "F": 0.08, "C": 0.03},
        "C": {"G": 0.01, "F": 0.03, "C": 0.08},
    }
    L_ast = {
        "G": {"G": 0.06, "F": 0.025, "C": 0.01},
        "F": {"G": 0.025, "F": 0.05, "C": 0.02},
        "C": {"G": 0.01, "F": 0.02, "C": 0.04},
    }
    L_trb = {
        "G": {"G": 0.02, "F": 0.02, "C": 0.015},
        "F": {"G": 0.02, "F": 0.04, "C": 0.03},
        "C": {"G": 0.015, "F": 0.03, "C": 0.05},
    }

    additive = 0.0
    if market == "pts":
        for pos_missing, val in m_pts.items():
            additive += L_pts[pos_missing][player_pos] * max(val, 0.0)
    elif market == "ast":
        for pos_missing, val in m_ast.items():
            additive += L_ast[pos_missing][player_pos] * max(val, 0.0)
    elif market == "trb":
        for pos_missing, val in m_trb.items():
            additive += L_trb[pos_missing][player_pos] * max(val, 0.0)

    if market == "pts":
        total_missing = sum(max(v, 0.0) for v in m_pts.values())
    elif market == "ast":
        total_missing = sum(max(v, 0.0) for v in m_ast.values())
    elif market == "trb":
        total_missing = sum(max(v, 0.0) for v in m_trb.values())
    else:
        total_missing = 0.0
    mult_alpha = {"pts": 0.008, "ast": 0.010, "trb": 0.008}.get(market, 0.008)
    mult = 1.0 + mult_alpha * (min(total_missing, 30.0) / 10.0)

    return float(base_pred) * mult + additive


def get_injury_context(player_team, injuries):
    injured_players = []
    questionable_players = []

    if player_team in injuries:
        for player_info in injuries[player_team]:
            status = player_info.get("status", "None")
            player_name = player_info.get("player", "")

            if status in ["Out", "Out For Season"]:
                injured_players.append(player_name)
            elif status == "Game Time Decision":
                questionable_players.append(player_name)

    return {
        "injured_count": len(injured_players),
        "questionable_count": len(questionable_players),
        "injured_players": injured_players,
        "questionable_players": questionable_players,
    }


def load_injury_data():
    try:
        with open("json/injury.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        pass
        return {}


def calculate_weights(days_since, decay_rate):
    max_days = np.max(days_since)
    return np.exp(decay_rate * (days_since - max_days))


def predict_features(df, player_id, opponent, hoa, feature):
    similarity_columns = [
        "mp",
        "fg",
        "fga",
        "fg_percent",
        "twop",
        "twop_percent",
        "tpm",
        "ft",
        "ft_percent",
        "ts_percent",
        "trb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "gmsc",
        "pts",
        "total_score",
    ]

    if feature in similarity_columns:
        similarity_columns.remove(feature)
    player_data = df[df["player"] == player_id].copy()
    player_data = player_data.sort_values("date", ascending=False)

    injuries = load_injury_data()

    player_team = player_data.iloc[0]["team"]
    player_pos = player_data.iloc[0].get("pos", "G")
    decay_rate = 0.025
    if player_data.empty:
        return None
    opponent_data = player_data[player_data["opp"] == opponent].copy()
    if len(opponent_data) < 1:
        return None
    if opponent_data.empty:
        return None
    player_data_filtered = player_data[similarity_columns].fillna(
        player_data[similarity_columns].mean()
    )
    player_data_filtered = player_data_filtered.fillna(0)

    percent_columns = ["fg_percent", "twop_percent", "ft_percent", "ts_percent", "pf"]
    count_like_columns = [
        col for col in similarity_columns if col not in percent_columns + ["mp", "total_score"]
    ]

    recent_window = 6
    recent_games = player_data.head(recent_window)
    current_mp = float(recent_games["mp"].mean()) if not recent_games.empty else float(player_data["mp"].mean())

    try:
        player_data_filtered[count_like_columns] = player_data_filtered[count_like_columns].astype(float)
        player_data_filtered["mp"] = player_data_filtered["mp"].astype(float)
    except Exception:
        pass

    if not opponent_data.empty and current_mp and current_mp > 0:
        for idx in opponent_data.index:
            game_mp = float(player_data.loc[idx, "mp"]) if player_data.loc[idx, "mp"] else 0.0
            if game_mp <= 0:
                continue
            if game_mp < 6:
                continue
            scale = current_mp / game_mp
            if scale < 0.6:
                scale = 0.6
            elif scale > 2.0:
                scale = 2.0
            for col in count_like_columns:
                try:
                    player_data_filtered.at[idx, col] = float(player_data_filtered.at[idx, col]) * scale
                except Exception:
                    continue
            player_data_filtered.at[idx, "mp"] = current_mp
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(player_data_filtered)
    scaled_df = pd.DataFrame(
        scaled_data, columns=similarity_columns, index=player_data_filtered.index
    )
    weights = calculate_weights(player_data["days_since"], decay_rate)
    weighted_scaled_df = scaled_df.mul(weights, axis=0)
    specific_avg = weighted_scaled_df.loc[opponent_data.index].mean()
    distances = weighted_scaled_df.apply(
        lambda row: distance.euclidean(row, specific_avg), axis=1
    )
    player_data.loc[:, "distance"] = distances
    closest_games = player_data.nsmallest(10, "distance")

    selection_decay = 0.02
    try:
        sel_weights = calculate_weights(closest_games["days_since"], selection_decay)
        if np.isfinite(sel_weights).all() and sel_weights.sum() > 0:
            base_prediction = np.average(closest_games[feature], weights=sel_weights)
        else:
            base_prediction = closest_games[feature].mean()
    except Exception:
        base_prediction = closest_games[feature].mean()

    try:
        missing_ctx = _compute_missing_by_position(player_team)
    except Exception:
        missing_ctx = {}
    try:
        final_prediction = _adjust_for_missing(base_prediction, feature, player_pos, missing_ctx)
    except Exception:
        final_prediction = base_prediction

    return final_prediction


def soft(player, opp, feat, hoa):
    df = load_data()
    player_id = player
    opponent = opp
    return predict_features(df, player_id, opponent, hoa, feat)


def predict_player_stat(player, opponent, feature, hoa):
    return soft(player, opponent, feature, hoa)


def main():
    print(soft("Donte DiVincenzo", "BKN", "tpm", 1))


if __name__ == "__main__":
    main()

