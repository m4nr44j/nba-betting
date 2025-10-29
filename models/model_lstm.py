import json
import math
import os

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine

from models.soft_predictor import soft

load_dotenv()


class LSTMWithAttention(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=2, dropout=0.3):
        super(LSTMWithAttention, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        self.attention = nn.Linear(hidden_size, 1)

        self.fc1 = nn.Linear(hidden_size, 32)
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(32, 1)
        self.relu = nn.ReLU()

    def forward(self, x):
        lstm_out, _ = self.lstm(x)

        attention_weights = torch.softmax(
            self.attention(lstm_out), dim=1
        )
        attended_output = torch.sum(
            attention_weights * lstm_out, dim=1
        )

        out = self.relu(self.fc1(attended_output))
        out = self.dropout(out)
        out = self.fc2(out)

        return out


def load_nba(player):
    try:
        df = pd.read_csv("csv/sql.csv")
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

        def aggregate_position_data(json_data, exclude_player):
            if exclude_player in json_data:
                del json_data[exclude_player]

            position_totals = {"G": 0, "F": 0, "C": 0}
            for player_name, value in json_data.items():
                pos = positions_df.loc[
                    positions_df["player"] == player_name, "pos"
                ].values
                if pos.size > 0:
                    position_totals[pos[0]] += value

            return position_totals

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
                lambda x: aggregate_position_data(x, player)
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


def get_soft_predictions(team, opp, player_df, player):
    injuries = {}
    try:
        with open("json/injury.json", "r") as file:
            rosters = json.load(file)
            for team_players in rosters.values():
                for player_info in team_players:
                    player_name = player_info["player"]
                    status = player_info["status"]
                    injuries[player_name] = status
    except:  # noqa: E722
        pass

    team_players = player_df[player_df["team"] == team]["player"].tolist()
    if player in team_players:
        team_players.remove(player)
    opp_players = player_df[player_df["team"] == opp]["player"].tolist()

    team_stats = {"pts": {}, "trb": {}, "ast": {}, "tov": {}}
    opp_stats = {"pts": {}, "trb": {}, "ast": {}, "blk": {}, "tov": {}}

    def populate_player_stats(players, stats, team_of_player):
        for player_name in players:
            status = injuries.get(player_name, "None")
            for key in stats:
                try:
                    predicted_value = soft(
                        player_name, opp if team_of_player == team else team, key, 1
                    )
                    if pd.isna(predicted_value):
                        predicted_value = player_df.loc[
                            player_df["player"] == player_name, f"avg_{key}"
                        ].values
                        if len(predicted_value) > 0:
                            predicted_value = predicted_value[0]
                        else:
                            predicted_value = 0
                except:  # noqa: E722
                    predicted_value = 0

                stats[key][player_name] = predicted_value
                if status == "OUT" or status == "Out For Season":
                    stats[key][player_name] = 0
                elif status == "Game Time Decision":
                    stats[key][player_name] *= 0.85

    populate_player_stats(team_players, team_stats, team)
    populate_player_stats(opp_players, opp_stats, opp)

    def aggregate_position_data(stat_dict, df):
        position_data = {"G": 0, "F": 0, "C": 0}
        for player_name, stat in stat_dict.items():
            position = df.loc[df["player"] == player_name, "pos"].values
            if position.size > 0:
                position_data[position[0]] += stat
        return position_data

    results = {
        "team": [team],
        "opp": [opp],
        "teammates_points": [aggregate_position_data(team_stats["pts"], player_df)],
        "teammates_rebounds": [aggregate_position_data(team_stats["trb"], player_df)],
        "teammates_assists": [aggregate_position_data(team_stats["ast"], player_df)],
        "opponents_points": [aggregate_position_data(opp_stats["pts"], player_df)],
        "opponents_rebounds": [aggregate_position_data(opp_stats["trb"], player_df)],
        "opponents_assists": [aggregate_position_data(opp_stats["ast"], player_df)],
        "teammates_turnovers": [aggregate_position_data(team_stats["tov"], player_df)],
        "opponents_blocks": [aggregate_position_data(opp_stats["blk"], player_df)],
        "opponents_turnovers": [aggregate_position_data(opp_stats["tov"], player_df)],
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


def create_sequences(X_data, y_data, seq_length=12):
    sequences = []
    targets = []

    for i in range(len(X_data) - seq_length + 1):
        sequences.append(X_data[i : i + seq_length])
        targets.append(y_data[i + seq_length - 1])

    return np.array(sequences), np.array(targets)


def rolling_lstm_train(player, market, conn, feature_weights=None):
    nba_data = load_nba(player)
    game_stats = load_game_stats(player, conn)

    if nba_data is None or game_stats.empty:
        return None, float("inf")

    df = nba_data.merge(game_stats, on=["team", "opp", "date"])
    df = df.sort_values("date").reset_index(drop=True)

    if len(df) < 20:
        return None, float("inf")

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
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["opp"]),
    ]
    preprocessor = ColumnTransformer(transformers=transformers)

    features = [col for col in df.columns if col not in ["date", market]]
    X = df[features]
    y = df[market].values

    X_processed = preprocessor.fit_transform(X)

    predictions = []
    actual_values = []
    min_train_size = 15
    seq_length = 12

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    for i in range(min_train_size + seq_length, len(X_processed)):
        X_train = X_processed[:i]
        y_train = y[:i]

        y_test = y[i]

        if len(X_train) < seq_length:
            continue

        X_seq, y_seq = create_sequences(X_train, y_train, seq_length)

        if len(X_seq) == 0:
            continue

        X_tensor = torch.FloatTensor(X_seq).to(device)
        y_tensor = torch.FloatTensor(y_seq).to(device)

        input_size = X_processed.shape[1]
        model = LSTMWithAttention(
            input_size, hidden_size=64, num_layers=2, dropout=0.3
        ).to(device)

        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.002, weight_decay=1e-5)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, "min", patience=10, factor=0.5
        )

        model.train()
        best_loss = float("inf")
        patience_counter = 0
        max_patience = 15

        for epoch in range(80):
            optimizer.zero_grad()
            outputs = model(X_tensor)
            loss = criterion(outputs.squeeze(), y_tensor)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            scheduler.step(loss)

            if loss.item() < best_loss:
                best_loss = loss.item()
                patience_counter = 0
            else:
                patience_counter += 1

            if patience_counter >= max_patience:
                break

        model.eval()
        with torch.no_grad():
            last_seq = X_train[-seq_length:].reshape(1, seq_length, -1)
            last_seq_tensor = torch.FloatTensor(last_seq).to(device)
            pred = model(last_seq_tensor).cpu().item()

        predictions.append(pred)
        actual_values.append(y_test)

    if len(predictions) == 0:
        return None, float("inf")

    mse = mean_squared_error(actual_values, predictions)
    error = math.sqrt(mse)

    X_seq_final, y_seq_final = create_sequences(X_processed, y, seq_length)
    X_tensor_final = torch.FloatTensor(X_seq_final).to(device)
    y_tensor_final = torch.FloatTensor(y_seq_final).to(device)

    final_model = LSTMWithAttention(
        X_processed.shape[1], hidden_size=64, num_layers=2, dropout=0.3
    ).to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(final_model.parameters(), lr=0.002, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, "min", patience=10, factor=0.5
    )

    final_model.train()
    best_loss = float("inf")
    patience_counter = 0

    for epoch in range(80):
        optimizer.zero_grad()
        outputs = final_model(X_tensor_final)
        loss = criterion(outputs.squeeze(), y_tensor_final)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(final_model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step(loss)

        if loss.item() < best_loss:
            best_loss = loss.item()
            patience_counter = 0
        else:
            patience_counter += 1

        if patience_counter >= 15:
            break

    return (final_model, preprocessor, seq_length, device), error


def run_lstm(player, team, opp, hoa, market, nestimators, feature_weights=None):
    conn = create_engine(os.getenv("SQL_ENGINE"))

    avg_mp, avg_plus_minus = get_last_data(player, conn)
    if avg_mp < 10:
        conn.dispose()
        return 0, 0

    print(f"      Running {market} (LSTM)")

    model_data, error = rolling_lstm_train(player, market, conn, feature_weights)

    if model_data is None:
        conn.dispose()
        return 0, float("inf")

    model, preprocessor, seq_length, device = model_data

    player_df = load_player_positions(conn)
    df = get_soft_predictions(team, opp, player_df, player)

    df["plus_minus"] = avg_plus_minus
    df["opp"] = opp
    df["mp"] = avg_mp

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

    pred_df = df[expected_columns]
    X_pred = preprocessor.transform(pred_df)

    X_pred_seq = np.tile(X_pred, (seq_length, 1)).reshape(1, seq_length, -1)
    X_pred_tensor = torch.FloatTensor(X_pred_seq).to(device)

    model.eval()
    with torch.no_grad():
        prediction = model(X_pred_tensor).cpu().item()

    conn.dispose()
    return float(prediction), float(error)


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
    }

    prediction, error = run_lstm(
        player_name, team_name, opp_name, 0, market_name, 20, feature_weights
    )
    print(f"LSTM Prediction: {prediction} ± {error}")
