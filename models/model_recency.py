import math
import os

import numpy as np
import pandas as pd
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
    get_recent_team_form,
    get_soft_predictions,
    load_game_stats,
    load_nba,
    load_player_positions,
)

load_dotenv()



def gradient_boost_recency(player, market, conn, n_estimators, feature_weights=None):
    nba_data = load_nba(player)
    game_stats = load_game_stats(player, conn)
    if nba_data is None or game_stats.empty:
        return None, float("inf")
    df = nba_data.merge(game_stats, on=["team", "opp", "date"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    max_date = df["date"].max()
    df["days_since"] = (max_date - df["date"]).dt.days
    recency_decay = 0.015
    df["sample_weight"] = np.exp(-recency_decay * df["days_since"])
    df["sample_weight"] = df["sample_weight"] * len(df) / df["sample_weight"].sum()
    numerical_features = [
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
    ]
    if feature_weights:
        for feature in numerical_features:
            if feature in df.columns and feature in feature_weights:
                weight = feature_weights[feature]
                df[feature] = df[feature] * weight
    transformers = [
        ("num", StandardScaler(), numerical_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["opp"]),
    ]
    preprocessor = ColumnTransformer(transformers=transformers)
    a = 0
    if a == 1:
        model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            learning_rate=0.08,
            max_depth=4,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            n_jobs=-1,
        )
    else:
        model = xgb.XGBRegressor(
            n_estimators=n_estimators, learning_rate=0.1, max_depth=3, n_jobs=-1
        )
    pipeline = Pipeline([("preprocessor", preprocessor), ("regressor", model)])
    features = [
        col
        for col in df.columns
        if col not in ["date", market, "days_since", "sample_weight"]
    ]
    X_train, X_test, y_train, y_test = train_test_split(
        df[features], df[market], test_size=0.2
    )
    train_indices = X_train.index
    sample_weights_train = df.loc[train_indices, "sample_weight"].values
    pipeline.fit(X_train, y_train, regressor__sample_weight=sample_weights_train)
    y_pred = pipeline.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    error = math.sqrt(mse)
    return pipeline, error


def run_recency(player, team, opp, hoa, market, nestimators, feature_weights=None):
    conn = create_engine(os.getenv("SQL_ENGINE"))
    avg_mp, avg_plus_minus = get_last_data(player, conn)
    if avg_mp < 10:
        return 0, 0
    pipeline, error = gradient_boost_recency(
        player, market, conn, nestimators, feature_weights
    )
    player_df = load_player_positions(conn)
    df = get_soft_predictions(team, opp, player_df, player)

    team_form = get_recent_team_form(team, opp, conn)

    df["plus_minus"] = avg_plus_minus
    df["opp"] = opp
    df["mp"] = avg_mp

    for key, value in team_form.items():
        df[key] = value

    if feature_weights:
        numerical_features = [
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
            "team_recent_pts",
            "team_recent_plus_minus",
            "team_recent_pace",
            "opp_recent_pts_allowed",
            "opp_recent_plus_minus",
            "opp_recent_pace",
        ]

        for feature in numerical_features:
            if feature in df.columns and feature in feature_weights:
                weight = feature_weights[feature]
                df[feature] = df[feature] * weight

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

    team_form_adjustment = 0
    if "team_recent_plus_minus" in team_form and "opp_recent_plus_minus" in team_form:
        form_diff = (
            team_form["team_recent_plus_minus"] - team_form["opp_recent_plus_minus"]
        )
        team_form_adjustment = form_diff * 0.05

    adjusted_prediction = prediction + team_form_adjustment

    return float(adjusted_prediction), float(error)


if __name__ == "__main__":
    conn = create_engine(os.getenv("SQL_ENGINE"))

    player_name = "Donovan Mitchell"
    team_name = "CLE"
    opp_name = "IND"
    market_name = "pts"

    feature_weights = {
        "mp": 2.5,
        "plus_minus": 1.8,
        "opp": 3.0,
        "teammates_points_G": 1.3,
        "teammates_points_F": 1.4,
        "teammates_points_C": 1.2,
        "team_recent_plus_minus": 1.2,
        "opp_recent_plus_minus": 1.3,
    }

    prediction, error = run_recency(
        player_name, team_name, opp_name, 0, market_name, 20, feature_weights
    )
    print(f"Recency Prediction: {prediction} ± {error}")
