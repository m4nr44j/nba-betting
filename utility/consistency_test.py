import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

from config import GAMES_FOR_CONSISTENCY

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
                    rn <= {GAMES_FOR_CONSISTENCY}
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
    finally:
        if conn:
            conn.dispose()
