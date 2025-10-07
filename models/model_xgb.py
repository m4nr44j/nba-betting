import math
import os

import xgboost as xgb
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine

from models.common import (
    get_last_data,
    get_soft_predictions,
    load_game_stats,
    load_nba,
    load_player_positions,
)

load_dotenv()



def gradient_boost(player, market, conn, n_estimators):
    nba_data = load_nba(player)
    game_stats = load_game_stats(player, conn)
    if nba_data is None or game_stats.empty:
        return None, float("inf")
    df = nba_data.merge(game_stats, on=["team", "opp", "date"])
    transformers = [
        (
            "num",
            StandardScaler(),
            [
                "plus_minus",
                "mp",
                "teammates_points_G",
                "teammates_points_F",
                "teammates_points_C",
                "teammates_rebounds_G",
                "teammates_rebounds_F",
                "teammates_rebounds_C",
                "teammates_assists_G",
                "teammates_assists_F",
                "teammates_assists_C",
                "opponents_points_G",
                "opponents_points_F",
                "opponents_points_C",
                "opponents_rebounds_G",
                "opponents_rebounds_F",
                "opponents_rebounds_C",
                "opponents_assists_G",
                "opponents_assists_F",
                "opponents_assists_C",
                "teammates_turnovers_F",
                "teammates_turnovers_C",
                "teammates_turnovers_G",
                "opponents_blocks_F",
                "opponents_blocks_C",
                "opponents_blocks_G",
                "opponents_turnovers_F",
                "opponents_turnovers_C",
                "opponents_turnovers_G",
            ],
        ),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["opp"]),
    ]
    preprocessor = ColumnTransformer(transformers=transformers)
    model = xgb.XGBRegressor(
        n_estimators=n_estimators, learning_rate=0.1, max_depth=3, n_jobs=-1
    )
    pipeline = Pipeline([("preprocessor", preprocessor), ("regressor", model)])
    features = [col for col in df.columns if col not in ["date", market]]
    X_train, X_test, y_train, y_test = train_test_split(
        df[features], df[market], test_size=0.2
    )
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    error = math.sqrt(mse)
    return pipeline, error


def run_xgb(player, team, opp, hoa, market, nestimators):
    conn = create_engine(os.getenv("SQL_ENGINE"))
    avg_mp, avg_plus_minus = get_last_data(player, conn)
    if avg_mp < 10:
        return 0, 0
    pipeline, error = gradient_boost(player, market, conn, nestimators)
    player_df = load_player_positions(conn)
    df = get_soft_predictions(team, opp, player_df, player)

    df["plus_minus"] = avg_plus_minus
    df["opp"] = opp
    df["mp"] = avg_mp

    expected_columns = [
        "plus_minus",
        "opp",
        "mp",
        "teammates_points_G",
        "teammates_points_F",
        "teammates_points_C",
        "teammates_rebounds_G",
        "teammates_rebounds_F",
        "teammates_rebounds_C",
        "teammates_assists_G",
        "teammates_assists_F",
        "teammates_assists_C",
        "opponents_points_G",
        "opponents_points_F",
        "opponents_points_C",
        "opponents_rebounds_G",
        "opponents_rebounds_F",
        "opponents_rebounds_C",
        "opponents_assists_G",
        "opponents_assists_F",
        "opponents_assists_C",
        "teammates_turnovers_F",
        "teammates_turnovers_C",
        "teammates_turnovers_G",
        "opponents_blocks_F",
        "opponents_blocks_C",
        "opponents_blocks_G",
        "opponents_turnovers_F",
        "opponents_turnovers_C",
        "opponents_turnovers_G",
    ]

    pred_vector_df = df[expected_columns].iloc[0:1]
    prediction = pipeline.predict(pred_vector_df)[0]
    return float(prediction), float(error)


if __name__ == "__main__":

    player_name = "Donovan Mitchell"
    team_name = "CLE"
    opp_name = "IND"
    market_name = "pts"

    prediction, error = run_xgb(player_name, team_name, opp_name, 0, market_name, 20)
    print(f"Predicted Output: {prediction} + - {(error)}")
