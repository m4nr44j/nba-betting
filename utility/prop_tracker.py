#!/usr/bin/env python3

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    try:
        import psycopg2_binary as psycopg2
        PSYCOPG2_AVAILABLE = True
    except ImportError:
        psycopg2 = None
        PSYCOPG2_AVAILABLE = False
import pytz
from dotenv import load_dotenv
from utility.nba_stats import get_nba_game_event_ids, get_nba_game_summary, extract_player_stats

load_dotenv()

EASTERN_TZ = pytz.timezone('US/Eastern')

def get_eastern_now():
    return datetime.now(EASTERN_TZ)


class PropTracker:
    def __init__(self, output_file: str = "output.txt"):
        self.output_file = output_file
        self.props = []
        self.game_stats = {}
        
        self.team_mapping = {
            "ATL": "Atlanta Hawks",
            "BOS": "Boston Celtics", 
            "BKN": "Brooklyn Nets",
            "CHA": "Charlotte Hornets",
            "CHI": "Chicago Bulls",
            "CLE": "Cleveland Cavaliers",
            "DAL": "Dallas Mavericks",
            "DEN": "Denver Nuggets",
            "DET": "Detroit Pistons",
            "GSW": "Golden State Warriors",
            "HOU": "Houston Rockets",
            "IND": "Indiana Pacers",
            "LAC": "Los Angeles Clippers",
            "LAL": "Los Angeles Lakers",
            "MEM": "Memphis Grizzlies",
            "MIA": "Miami Heat",
            "MIL": "Milwaukee Bucks",
            "MIN": "Minnesota Timberwolves",
            "NOP": "New Orleans Pelicans",
            "NYK": "New York Knicks",
            "OKC": "Oklahoma City Thunder",
            "ORL": "Orlando Magic",
            "PHI": "Philadelphia 76ers",
            "PHX": "Phoenix Suns",
            "POR": "Portland Trail Blazers",
            "SAC": "Sacramento Kings",
            "SAS": "San Antonio Spurs",
            "TOR": "Toronto Raptors",
            "UTA": "Utah Jazz",
            "WAS": "Washington Wizards"
        }
        
        self.load_props()
    
    def load_props(self):
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if line:
                    prop = self.parse_prop_line(line)
                    if prop:
                        self.props.append(prop)
            
            print(f"Loaded {len(self.props)} props from {self.output_file}")
        except FileNotFoundError:
            print(f"Output file {self.output_file} not found")
        except Exception as e:
            print(f"Error loading props: {e}")
    
    def parse_prop_line(self, line: str) -> Optional[Dict]:
        try:
            game_match = re.match(r'([A-Z]{3})\s+vs\s+([A-Z]{3}):\s+(.+)', line)
            if not game_match:
                return None
            
            home_team, away_team, rest = game_match.groups()
            
            prop_match = re.match(
                r'(.+?)\s+(Over|Under)\s+([\d.]+)\s+([A-Z+]+)\s+\(([-\d]+)\s+FD\)', 
                rest
            )
            if not prop_match:
                return None
            
            player, direction, line_value, market, odds = prop_match.groups()
            
            return {
                'game': f"{home_team} vs {away_team}",
                'home_team': home_team,
                'away_team': away_team,
                'player': player.strip(),
                'direction': direction,
                'line': float(line_value),
                'market': market,
                'odds': int(odds),
                'original_line': line
            }
        except Exception as e:
            print(f"Error parsing line '{line}': {e}")
            return None
    
    def get_today_games(self) -> List[str]:
        eastern_now = get_eastern_now()
        today = eastern_now.strftime("%Y%m%d")
        return get_nba_game_event_ids(today)
    
    def update_game_stats(self):
        game_ids = self.get_today_games()
        
        for game_id in game_ids:
            if game_id not in self.game_stats:
                summary = get_nba_game_summary(game_id)
                if summary:
                    player_stats = extract_player_stats(summary)
                    self.game_stats[game_id] = {
                        'summary': summary,
                        'player_stats': player_stats,
                        'last_updated': datetime.now()
                    }
                else:
                    print(f"Could not get summary for game {game_id}")
            else:
                summary = get_nba_game_summary(game_id)
                if summary:
                    player_stats = extract_player_stats(summary)
                    self.game_stats[game_id]['summary'] = summary
                    self.game_stats[game_id]['player_stats'] = player_stats
                    self.game_stats[game_id]['last_updated'] = datetime.now()
        
        self.save_stats_to_json()
    
    def save_stats_to_json(self):
        all_stats = []
        for game_id, game_data in self.game_stats.items():
            all_stats.extend(game_data['player_stats'])
        
        os.makedirs(os.path.dirname('json/nba_stats.json'), exist_ok=True)
        with open('json/nba_stats.json', 'w') as f:
            json.dump(all_stats, f, indent=2)
    
    def find_player_stats(self, player_name: str, team_abbr: str) -> Optional[Dict]:
        team_full_name = self.team_mapping.get(team_abbr, team_abbr)
        
        for game_id, game_data in self.game_stats.items():
            for player_data in game_data['player_stats']:
                if (player_data['Player'] == player_name and 
                    player_data['Team'] == team_full_name):
                    return player_data['Stats']
        return None
    
    def determine_player_team(self, prop: Dict) -> Optional[str]:
        player_name = prop['player']
        home_team = prop['home_team']
        away_team = prop['away_team']
        
        db_team = self.get_player_team_from_db(player_name)
        if db_team:
            if db_team == home_team or db_team == away_team:
                return db_team
        
        home_stats = self.find_player_stats(player_name, home_team)
        if home_stats:
            return home_team
            
        away_stats = self.find_player_stats(player_name, away_team)
        if away_stats:
            return away_team
            
        return None
    
    def get_player_team_from_db(self, player_name: str) -> Optional[str]:
        if not PSYCOPG2_AVAILABLE:
            return None
            
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"),
                dbname=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS"),
                port=os.getenv("DB_PORT"),
            )
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT team FROM public.latest_player_teams WHERE player = %s;",
                (player_name,)
            )
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            print(f"Error getting player team from DB: {e}")
            return None
    
    def get_game_time_info(self, prop: Dict) -> Dict:
        player_team = self.determine_player_team(prop)
        if not player_team:
            return {'status': 'no_game', 'time_left': 0, 'quarter': 0, 'game_status': 'unknown'}
        
        for game_id, game_data in self.game_stats.items():
            summary = game_data['summary']
            
            home_team = summary.get('boxscore', {}).get('teams', [{}])[0].get('team', {}).get('displayName', '')
            away_team = summary.get('boxscore', {}).get('teams', [{}])[1].get('team', {}).get('displayName', '')
            
            team_full_name = self.team_mapping.get(player_team, player_team)
            if team_full_name in [home_team, away_team]:
                game_status = summary.get('header', {}).get('competitions', [{}])[0].get('status', {}).get('type', {}).get('name', 'unknown')
                
                try:
                    clock = summary.get('header', {}).get('competitions', [{}])[0].get('status', {}).get('displayClock', '')
                    period = summary.get('header', {}).get('competitions', [{}])[0].get('status', {}).get('period', 0)
                    
                    time_left = 0
                    if clock and ':' in clock:
                        minutes, seconds = clock.split(':')
                        time_left = int(minutes) * 60 + int(seconds)
                    
                    return {
                        'status': 'active',
                        'time_left': time_left,
                        'quarter': period,
                        'game_status': game_status,
                        'clock': clock
                    }
                except:
                    return {
                        'status': 'active',
                        'time_left': 0,
                        'quarter': 0,
                        'game_status': game_status,
                        'clock': 'unknown'
                    }
        
        return {'status': 'no_game', 'time_left': 0, 'quarter': 0, 'game_status': 'unknown'}

    def get_prop_progress(self, prop: Dict) -> Dict:
        player_team = self.determine_player_team(prop)
        
        if not player_team:
            return {'status': 'no_stats', 'progress': 0, 'current_value': 0}
        
        stats = self.find_player_stats(prop['player'], player_team)
        if not stats:
            return {'status': 'no_stats', 'progress': 0, 'current_value': 0}
        
        market = prop['market']
        current_value = 0
        
        if market == 'PTS':
            current_value = int(stats.get('pts', 0) or 0)
        elif market == 'REB':
            current_value = int(stats.get('trb', 0) or 0)
        elif market == 'AST':
            current_value = int(stats.get('ast', 0) or 0)
        elif market == 'P+R':
            current_value = int(stats.get('p_r', 0) or 0)
        elif market == 'P+A':
            current_value = int(stats.get('p_a', 0) or 0)
        elif market == 'A+R':
            current_value = int(stats.get('a_r', 0) or 0)
        elif market == 'P+R+A':
            current_value = int(stats.get('p_r_a', 0) or 0)
        else:
            return {'status': 'unknown_market', 'progress': 0, 'current_value': 0}
        
        line = prop['line']
        direction = prop['direction']
        
        game_info = self.get_game_time_info(prop)
        game_over = (game_info.get('game_status') == 'STATUS_FINAL' or 
                    game_info.get('game_status') == 'STATUS_POSTGAME')
        
        if direction == 'Over':
            if current_value >= line:
                status = 'hit'
                progress = 100
            elif game_over:
                status = 'miss'
                progress = (current_value / line) * 100
            else:
                status = 'active'
                progress = (current_value / line) * 100
        else:
            if current_value <= line:
                status = 'hit'
                progress = 100
            elif game_over:
                status = 'miss'
                progress = ((line - current_value) / line) * 100 if current_value > line else 100
            else:
                status = 'active'
                progress = ((line - current_value) / line) * 100 if current_value > line else 100
        
        game_info = self.get_game_time_info(prop)
        
        pace_info = self.calculate_pace(current_value, game_info, line, direction)
        
        return {
            'status': status,
            'progress': round(progress, 1),
            'current_value': current_value,
            'needed': max(0, line - current_value) if direction == 'Over' else max(0, current_value - line),
            'player_team': player_team,
            'game_info': game_info,
            'pace_info': pace_info
        }
    
    def calculate_pace(self, current_value: int, game_info: Dict, line: float, direction: str) -> Dict:
        if game_info['status'] != 'active' or game_info['quarter'] == 0:
            return {'on_track': 'unknown', 'projection': 0, 'pace': 0}
        
        quarter = game_info['quarter']
        time_left = game_info['time_left']
        
        if quarter <= 4:
            time_elapsed = (quarter - 1) * 12 * 60 + (12 * 60 - time_left)
        else:
            time_elapsed = 4 * 12 * 60 + (quarter - 4) * 5 * 60 + (5 * 60 - time_left)
        
        if time_elapsed > 0:
            current_pace = current_value / (time_elapsed / 60)
        else:
            current_pace = 0
        
        total_game_time = 48 * 60
        if quarter > 4:
            total_game_time += (quarter - 4) * 5 * 60
        
        projected_final = current_pace * (total_game_time / 60)
        
        if direction == 'Over':
            if projected_final >= line:
                on_track = '🟢'
            else:
                if projected_final >= line * 0.9:
                    on_track = '🟡'
                else:
                    on_track = '🔴'
        else:
            if projected_final <= line:
                on_track = '🟢'
            else:
                if projected_final <= line * 1.1:
                    on_track = '🟡'
                else:
                    on_track = '🔴'
        
        return {
            'on_track': on_track,
            'projection': round(projected_final, 1),
            'pace': round(current_pace, 2),
            'quarter': quarter,
            'time_left': time_left
        }
    
    def clear_screen(self):
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def display_progress(self, clear_screen=True):
        if clear_screen:
            self.clear_screen()
        
        print("="*80)
        eastern_now = get_eastern_now()
        print(f"🏀 NBA PROP TRACKER - {eastern_now.strftime('%Y-%m-%d %H:%M:%S')} ET")
        print("="*80)
        
        if not self.props:
            print("No props loaded")
            return
        
        self.update_game_stats()
        
        hit_props = []
        active_props = []
        no_stats_props = []
        miss_props = []
        
        for prop in self.props:
            progress = self.get_prop_progress(prop)
            prop['progress_data'] = progress
            
            if progress['status'] == 'hit':
                hit_props.append(prop)
            elif progress['status'] == 'no_stats':
                no_stats_props.append(prop)
            elif progress['status'] == 'miss':
                miss_props.append(prop)
            else:
                active_props.append(prop)
        
        if hit_props:
            print(f"\n🎯 HIT PROPS ({len(hit_props)})")
            print("-" * 60)
            for prop in hit_props:
                progress = prop['progress_data']
                print(f"✅ {prop['player']:<20} {prop['direction']} {prop['line']:>4} {prop['market']:<6} "
                      f"({progress['current_value']:>2}/{prop['line']:>4}) - {prop['odds']:>4} FD")
        
        if active_props:
            print(f"\n🔥 ACTIVE PROPS ({len(active_props)})")
            print("-" * 80)
            def sort_key(prop):
                pace_info = prop['progress_data'].get('pace_info', {})
                on_track = pace_info.get('on_track', '🔴')
                progress = prop['progress_data']['progress']
                
                if on_track == '🟢':
                    priority = 0
                elif on_track == '🟡':
                    priority = 1
                else:
                    priority = 2
                
                return (priority, -progress)
            
            active_props.sort(key=sort_key)
            
            for prop in active_props:
                progress = prop['progress_data']
                needed = progress['needed']
                progress_bar = self.create_progress_bar(progress['progress'], width=12)
                pace_info = progress.get('pace_info', {})
                game_info = progress.get('game_info', {})
                
                if game_info.get('clock'):
                    time_str = f"Q{pace_info.get('quarter', '?')} {game_info['clock']}"
                else:
                    time_str = "No time"
                
                if pace_info.get('projection', 0) > 0:
                    pace_str = f"{pace_info['on_track']}"
                else:
                    pace_str = "No pace"
                
                print(f"{progress_bar} {prop['player']:<18} {prop['direction']} {prop['line']:>4} {prop['market']:<4} "
                      f"({progress['current_value']:>2}) | {pace_str}")
        
        if no_stats_props:
            print(f"\n❓ NO STATS ({len(no_stats_props)})")
            print("-" * 80)
            for prop in no_stats_props[:10]:
                game_info = prop.get('progress_data', {}).get('game_info', {})
                if game_info.get('clock'):
                    time_str = f"Q{game_info.get('quarter', '?')} {game_info['clock']}"
                else:
                    time_str = "No game"
                
                print(f"❓ {prop['player']:<18} {prop['line']:>4} {prop['market']:<4} - {prop['odds']:>4} FD | {time_str}")
            if len(no_stats_props) > 10:
                print(f"... and {len(no_stats_props) - 10} more")
        
        if miss_props:
            print(f"\n❌ MISSED PROPS ({len(miss_props)})")
            print("-" * 60)
            for prop in miss_props:
                progress = prop['progress_data']
                print(f"❌ {prop['player']:<18} {prop['direction']} {prop['line']:>4} {prop['market']:<4} "
                      f"({progress['current_value']:>2}/{prop['line']:>4}) - {prop['odds']:>4} FD")
        
        total_props = len(self.props)
        hit_count = len(hit_props)
        active_count = len(active_props)
        miss_count = len(miss_props)
        hit_rate = (hit_count / total_props * 100) if total_props > 0 else 0
        
        print(f"\n📊 SUMMARY")
        print("-" * 50)
        print(f"Total: {total_props:>3} | Hit: {hit_count:>2} ({hit_rate:>5.1f}%) | Active: {active_count:>2} | Miss: {miss_count:>2} | No Stats: {len(no_stats_props):>2}")
        
        print(f"\nPress Ctrl+C to stop")
    
    def create_progress_bar(self, progress: float, width: int = 20) -> str:
        filled = int((progress / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {progress:5.1f}%"
    
    def run_continuous_tracking(self, update_interval: int = 30):
        print(f"Starting continuous prop tracking (updates every {update_interval}s)")
        print("Press Ctrl+C to stop")
        time.sleep(2)
        
        try:
            while True:
                self.display_progress(clear_screen=True)
                time.sleep(update_interval)
        except KeyboardInterrupt:
            self.clear_screen()
            print("🏀 NBA Prop Tracker stopped by user")
            print("Thanks for using the tracker!")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Track NBA prop betting progress')
    parser.add_argument('--file', '-f', default='output copy.txt', 
                       help='Path to output.txt file (default: output.txt)')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit (default: continuous)')
    parser.add_argument('--interval', '-i', type=int, default=30,
                       help='Update interval in seconds for continuous mode (default: 30)')
    
    args = parser.parse_args()
    
    tracker = PropTracker(args.file)
    
    if args.once:
        tracker.display_progress(clear_screen=False)
    else:
        tracker.run_continuous_tracking(args.interval)


if __name__ == "__main__":
    main()


