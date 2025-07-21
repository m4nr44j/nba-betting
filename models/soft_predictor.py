import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from scipy.spatial import distance
import numpy as np
from sqlalchemy import create_engine
import json
import os
from dotenv import load_dotenv
load_dotenv()

def load_data():
    df = pd.read_csv('csv/sql.csv')
    return df

def get_injury_context(player_team, injuries):
    injured_players = []
    questionable_players = []
    
    if player_team in injuries:
        for player_info in injuries[player_team]:
            status = player_info.get('status', 'None')
            player_name = player_info.get('player', '')
            
            if status in ["Out", "Out For Season"]:
                injured_players.append(player_name)
            elif status == "Game Time Decision":
                questionable_players.append(player_name)
    
    return {
        'injured_count': len(injured_players),
        'questionable_count': len(questionable_players),
        'injured_players': injured_players,
        'questionable_players': questionable_players
    }

def load_injury_data():
    try:
        with open('json/injury.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("Injury file not found, assuming no injuries")
        return {}


def calculate_weights(days_since, decay_rate):
    max_days = np.max(days_since)
    return np.exp(decay_rate * (days_since - max_days))

def predict_features(df, player_id, opponent, hoa, feature):
    similarity_columns = [
        'mp','fg', 'fga', 'fg_percent', 'twop', 
        'twop_percent', 'tpm', 'ft', 'ft_percent', 'ts_percent', 
        'trb', 'ast', 'stl', 'blk', 'tov', 'pf', 'gmsc','pts', 'total_score'
    ]
    
    if(feature in similarity_columns):
        similarity_columns.remove(feature)
    player_data = df[df['player'] == player_id].copy()
    player_data = player_data.sort_values('date', ascending=False)

    injuries = load_injury_data()

    player_team = player_data.iloc[0]['team']
    decay_rate = 0.025
    if player_data.empty:
        return None
    opponent_data = player_data[player_data['opp'] == opponent].copy()
    if(len(opponent_data) < 1):
        return None
    if opponent_data.empty:
        return None
    player_data_filtered = player_data[similarity_columns].fillna(player_data[similarity_columns].mean())
    player_data_filtered = player_data_filtered.fillna(0)
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(player_data_filtered)
    scaled_df = pd.DataFrame(scaled_data, columns=similarity_columns, index=player_data_filtered.index)
    weights = calculate_weights(player_data['days_since'], decay_rate)
    weighted_scaled_df = scaled_df.mul(weights, axis=0) 
    specific_avg = weighted_scaled_df.loc[opponent_data.index].mean()
    distances = weighted_scaled_df.apply(lambda row: distance.euclidean(row, specific_avg), axis=1)
    player_data.loc[:,'distance'] = distances
    closest_games = player_data.nsmallest(10, 'distance')

    base_prediction = closest_games[feature].mean()
    injury_context = get_injury_context(player_team, injuries) if player_team else {}

    injury_multiplier = 1.0
    injured = injury_context.get('injured_count', 0)
    questionable = injury_context.get('questionable_count', 0)
    recent_15_games = player_data.head(15)
    player_avg_mp = recent_15_games['mp'].mean()  
    
    if(player_avg_mp > 25):
        injury_multiplier += 0.005*injured
    else:
        injury_multiplier += 0.005*questionable + 0.01*injured

    adjusted_prediction = base_prediction * injury_multiplier
    return adjusted_prediction

def soft(player, opp, feat, hoa):
    df = load_data()
    player_id = player
    opponent = opp
    return predict_features(df, player_id, opponent, hoa, feat)

def predict_player_stat(player, opponent, feature, hoa):
    return soft(player, opponent, feature, hoa)

def main():
    print(soft("Jrue Holiday","ORL", 'trb', 0))

if __name__ == '__main__':
    main()
