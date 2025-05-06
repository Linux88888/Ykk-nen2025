import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
import datetime
import calendar
import os
import warnings
import json # Added for potential use, though pandas handles JSON loading
from datetime import timedelta

# Suppress warning messages
warnings.filterwarnings('ignore')

# Configuration
DEBUG = False
OUTPUT_DIR = "output"
PLOTS_DIR = os.path.join(OUTPUT_DIR, "plots")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
MODELS_DIR = os.path.join(OUTPUT_DIR, "models")

# Create output directories
for directory in [OUTPUT_DIR, PLOTS_DIR, DATA_DIR, MODELS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Set visualization styles
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("viridis")

def debug_print(message):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"DEBUG: {message}")

def load_data(filepath):
    """Load match data from JSON file"""
    try:
        df = pd.read_json(filepath, orient='records')
        if df.empty and os.path.exists(filepath) and os.path.getsize(filepath) > 2: # >2 for "[]"
             debug_print(f"Data loaded from {filepath} is empty, but file exists and is not empty. Check JSON structure.")
        elif df.empty:
             debug_print(f"Data loaded from {filepath} is empty. This might be expected if no data was scraped.")
        else:
            debug_print(f"Data loaded successfully from {filepath}. Shape: {df.shape}")
        return df
    except FileNotFoundError:
        print(f"Error: Data file not found at {filepath}")
        return None
    except ValueError as ve: # pd.read_json can raise ValueError on malformed JSON
        print(f"Error: Could not parse JSON from {filepath}. It might be malformed or not a list of records. Error: {ve}")
        return None
    except Exception as e:
        print(f"Error loading data from {filepath}: {e}")
        return None

def preprocess_data(df):
    """Clean and preprocess the data"""
    if df is None or df.empty:
        print("Error: Input DataFrame is None or empty in preprocess_data.")
        return None
    processed_df = df.copy()

    # Rename columns from JSON fields to names expected by the script
    rename_map = {
        'score': 'Tulos',
        'team_home': 'Koti',
        'team_away': 'Vieras',
        'audience': 'Yleisö',
        'venue': 'Stadion',
        'match_datetime_raw': 'PvmAikaRaw'
    }
    existing_rename_map = {k: v for k, v in rename_map.items() if k in processed_df.columns}
    processed_df.rename(columns=existing_rename_map, inplace=True)
    debug_print(f"Columns after renaming: {processed_df.columns.tolist()}")

    # Initialize Pvm and Aika columns
    processed_df['Pvm'] = None
    processed_df['Aika'] = None

    # Parse PvmAikaRaw into Pvm and Aika if PvmAikaRaw exists
    if 'PvmAikaRaw' in processed_df.columns:
        valid_dt_raw_mask = processed_df['PvmAikaRaw'].notna() & (processed_df['PvmAikaRaw'] != '')
        temp_pvm_aika_raw_str = processed_df.loc[valid_dt_raw_mask, 'PvmAikaRaw'].astype(str)
        
        split_dt = temp_pvm_aika_raw_str.str.split('|', n=1, expand=True)

        if not split_dt.empty:
            processed_df.loc[valid_dt_raw_mask, 'Aika'] = split_dt[0].str.strip()
            if split_dt.shape[1] > 1 and split_dt[1] is not None:
                raw_pvm_series = split_dt[1].str.strip()
                # Extract DD.MM.YYYY or DD.MM.YY or DD.MM. from Pvm string
                # Regex captures DD.MM or D.M, optionally followed by .YY or .YYYY, and an optional trailing dot
                date_extract_series = raw_pvm_series.str.extract(r'(\d{1,2}\.\d{1,2}(?:\.(?:\d{2}|\d{4}))?\.?)')[0]
                processed_df.loc[valid_dt_raw_mask, 'Pvm'] = date_extract_series.str.rstrip('.')
        # Optionally drop PvmAikaRaw after parsing
        # processed_df.drop(columns=['PvmAikaRaw'], inplace=True, errors='ignore')
    else:
        debug_print("PvmAikaRaw column not found for Pvm/Aika parsing.")

    # Check for required columns that feed into the rest of the script
    required_cols = ['Tulos', 'Pvm', 'Aika', 'Koti', 'Vieras']
    missing_req = [col for col in required_cols if col not in processed_df.columns or processed_df[col].isnull().all()]
    # If Pvm or Aika are all None because PvmAikaRaw was missing or unparseable, it's a problem for datetime conversion
    if 'Pvm' in missing_req or 'Aika' in missing_req:
         debug_print("Warning: 'Pvm' or 'Aika' columns are missing or all null. Datetime conversion might fail for many rows.")
    
    # If critical columns like Tulos, Koti, Vieras are entirely missing (not just all NaN, but column itself)
    critical_missing = [col for col in ['Tulos', 'Koti', 'Vieras'] if col not in processed_df.columns]
    if critical_missing:
        print(f"Error: Critically missing columns for analysis: {critical_missing}. Cannot proceed.")
        return None
        
    processed_df['home_goals'] = None
    processed_df['away_goals'] = None
    # Ensure 'Tulos' column exists before trying to iterate over it
    if 'Tulos' in processed_df.columns:
        for idx, row in processed_df.iterrows():
            if pd.notna(row['Tulos']):
                try:
                    score_str = str(row['Tulos']).strip()
                    # Common separators can be '-' or '–' (en-dash)
                    score_parts = re.split(r'\s*[-\u2013]\s*', score_str) # Handles dash or en-dash with optional spaces
                    if len(score_parts) == 2:
                        processed_df.at[idx, 'home_goals'] = int(score_parts[0].strip())
                        processed_df.at[idx, 'away_goals'] = int(score_parts[1].strip())
                    else:
                        debug_print(f"Could not parse score: {row['Tulos']} at index {idx} using regex split")
                except ValueError:
                    debug_print(f"Non-integer score part found: {row['Tulos']} at index {idx}")
                except Exception as e:
                    debug_print(f"General error parsing score {row['Tulos']} at index {idx}: {e}")
    else:
        debug_print("Warning: 'Tulos' column not found for parsing home/away goals.")


    processed_df['home_goals'] = pd.to_numeric(processed_df['home_goals'], errors='coerce')
    processed_df['away_goals'] = pd.to_numeric(processed_df['away_goals'], errors='coerce')
    
    processed_df['total_goals'] = processed_df['home_goals'].add(processed_df['away_goals'], fill_value=0)
    processed_df.loc[processed_df['home_goals'].isna() | processed_df['away_goals'].isna(), 'total_goals'] = np.nan

    conditions = [
        (processed_df['home_goals'] > processed_df['away_goals']),
        (processed_df['home_goals'] < processed_df['away_goals']),
        (processed_df['home_goals'] == processed_df['away_goals']) & (processed_df['home_goals'].notna())
    ]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None)
    
    processed_df['match_datetime'] = None
    # Ensure 'Pvm' and 'Aika' columns exist before trying to iterate
    if 'Pvm' in processed_df.columns and 'Aika' in processed_df.columns:
        for idx, row in processed_df.iterrows():
            if pd.notna(row['Pvm']) and pd.notna(row['Aika']):
                try:
                    date_str = str(row['Pvm']).strip()
                    time_str = str(row['Aika']).strip()
                    
                    date_parts = date_str.split('.')
                    time_parts = time_str.split(':')
                    
                    if len(date_parts) >= 2 and len(time_parts) >= 1: # Min D.M and H
                        day = int(date_parts[0])
                        month = int(date_parts[1])
                        
                        if len(date_parts) > 2 and date_parts[2]: # Year part exists
                             year_part_str = date_parts[2].strip()
                             if year_part_str: # Ensure year part is not empty string
                                year_part = int(year_part_str)
                                year = year_part if year_part > 100 else (2000 + year_part if year_part < 50 else 1900 + year_part)
                             else: # Year part was empty after split (e.g. "1.1.")
                                year = datetime.datetime.now().year 
                        else: 
                             year = datetime.datetime.now().year 
                        
                        hour = int(time_parts[0])
                        minute = int(time_parts[1]) if len(time_parts) > 1 and time_parts[1] else 0
                        
                        dt = datetime.datetime(year, month, day, hour, minute)
                        processed_df.at[idx, 'match_datetime'] = dt
                    else:
                         debug_print(f"Could not parse date/time parts: Pvm='{row['Pvm']}' Aika='{row['Aika']}'")
                except ValueError:
                     debug_print(f"Date/Time conversion error (ValueError): Pvm='{row['Pvm']}' Aika='{row['Aika']}'")
                except Exception as e:
                    debug_print(f"General date parsing error: {e} for Pvm='{row['Pvm']}' Aika='{row['Aika']}'")
    else:
        debug_print("Warning: 'Pvm' or 'Aika' columns not found for datetime parsing loop.")

    processed_df['match_datetime'] = pd.to_datetime(processed_df['match_datetime'], errors='coerce')
    
    processed_df['date'] = processed_df['match_datetime'].dt.date
    processed_df['year'] = processed_df['match_datetime'].dt.year
    processed_df['month'] = processed_df['match_datetime'].dt.month
    processed_df['day'] = processed_df['match_datetime'].dt.day
    processed_df['weekday'] = processed_df['match_datetime'].dt.weekday
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['hour'] = processed_df['match_datetime'].dt.hour
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    
    if 'Yleisö' in processed_df.columns:
        processed_df['attendance'] = processed_df['Yleisö'].astype(str).str.replace(r'[\sN/A]+', '', regex=True) # Remove whitespace and N/A
        processed_df['attendance'] = pd.to_numeric(processed_df['attendance'], errors='coerce')
    else:
        debug_print("Warning: 'Yleisö' column not found for attendance processing.")
        processed_df['attendance'] = np.nan # Ensure column exists if other functions expect it
        
    # Drop rows where essential data for league table is missing
    # Koti and Vieras should exist if they were in the JSON
    essential_cols_for_dropna = ['home_goals', 'away_goals', 'result']
    if 'Koti' in processed_df.columns: essential_cols_for_dropna.append('Koti')
    if 'Vieras' in processed_df.columns: essential_cols_for_dropna.append('Vieras')
    
    original_rows = len(processed_df)
    processed_df.dropna(subset=essential_cols_for_dropna, inplace=True)
    debug_print(f"Rows before dropna on essentials: {original_rows}, after: {len(processed_df)}")

    return processed_df

def calculate_league_table(df):
    """Calculate league standings"""
    teams = {}
    # Filter only matches with valid results and teams
    # Ensure Koti and Vieras columns exist before filtering on them
    filter_conditions = df['result'].notna()
    if 'Koti' in df.columns:
        filter_conditions &= df['Koti'].notna()
    if 'Vieras' in df.columns:
        filter_conditions &= df['Vieras'].notna()
        
    match_df = df[filter_conditions].copy()
    
    if len(match_df) == 0:
        print("No valid match data found to calculate league table (after filtering for result, Koti, Vieras).")
        return None
        
    for _, match in match_df.iterrows():
        home_goals = int(match['home_goals'])
        away_goals = int(match['away_goals'])
        home_team = match['Koti']
        away_team = match['Vieras']
        
        for team in [home_team, away_team]:
            if team not in teams:
                teams[team] = {
                    'played': 0, 
                    'wins': 0, 
                    'draws': 0, 
                    'losses': 0,
                    'goals_for': 0, 
                    'goals_against': 0, 
                    'points': 0,
                    'clean_sheets': 0,
                    'failed_to_score': 0
                }
        teams[home_team]['played'] += 1
        teams[away_team]['played'] += 1
        teams[home_team]['goals_for'] += home_goals
        teams[home_team]['goals_against'] += away_goals
        teams[away_team]['goals_for'] += away_goals
        teams[away_team]['goals_against'] += home_goals
        
        if home_goals == 0:
            teams[home_team]['failed_to_score'] += 1
            if away_team in teams: teams[away_team]['clean_sheets'] += 1 # Ensure away_team key exists
        if away_goals == 0:
            teams[away_team]['failed_to_score'] += 1
            if home_team in teams: teams[home_team]['clean_sheets'] += 1 # Ensure home_team key exists
            
        if match['result'] == 'home_win':
            teams[home_team]['wins'] += 1
            teams[home_team]['points'] += 3
            teams[away_team]['losses'] += 1
        elif match['result'] == 'away_win':
            teams[away_team]['wins'] += 1
            teams[away_team]['points'] += 3
            teams[home_team]['losses'] += 1
        else: # Draw
            teams[home_team]['draws'] += 1
            teams[home_team]['points'] += 1
            teams[away_team]['draws'] += 1
            teams[away_team]['points'] += 1
            
    pk35_key = next((key for key in teams if isinstance(key, str) and key.upper() == "PK-35"), None)
    if pk35_key:
        debug_print(f"Handling {pk35_key} with -2 point start")
        teams[pk35_key]['points'] -= 2
        
    for team_name, stats in teams.items():
        if stats['played'] > 0:
            stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
            stats['avg_goals_for'] = round(stats['goals_for'] / stats['played'], 2)
            stats['avg_goals_against'] = round(stats['goals_against'] / stats['played'], 2)
            stats['win_percentage'] = round((stats['wins'] / stats['played']) * 100, 1)
        else:
             stats['goal_difference'] = 0
             stats['avg_goals_for'] = 0
             stats['avg_goals_against'] = 0
             stats['win_percentage'] = 0
        stats['team'] = team_name
        
    if not teams:
         return None

    table_df = pd.DataFrame(list(teams.values()))
    sort_cols = ['points', 'goal_difference', 'goals_for']
    if all(col in table_df.columns for col in sort_cols):
        table_df = table_df.sort_values(by=sort_cols, ascending=[False, False, False])
    else:
         print("Warning: Could not sort league table due to missing columns (points, goal_difference, goals_for).")
         if 'points' in table_df.columns:
              table_df = table_df.sort_values(by='points', ascending=False)

    table_df.reset_index(drop=True, inplace=True)
    table_df.index += 1 
    table_df['rank'] = table_df.index

    ordered_cols = ['rank', 'team', 'played', 'wins', 'draws', 'losses', 'goals_for', 'goals_against', 'goal_difference', 'points']
    for col in ['avg_goals_for', 'avg_goals_against', 'win_percentage', 'clean_sheets', 'failed_to_score']:
         if col in table_df.columns:
              ordered_cols.append(col)
    
    # Ensure all ordered_cols actually exist in table_df before trying to reorder
    final_ordered_cols = [col for col in ordered_cols if col in table_df.columns]
    table_df = table_df[final_ordered_cols]

    return table_df

def analyze_attendance_patterns(df):
    """Analyze attendance patterns to identify optimal scheduling"""
    if 'attendance' not in df.columns or df['attendance'].isnull().all():
        print("Attendance data ('Yleisö' column mapped to 'attendance') not found or all null.")
        return None
        
    attendance_df = df[df['attendance'].notna() & df['weekday_name'].notna() & df['hour'].notna()].copy()
    if len(attendance_df) == 0:
        print("No valid attendance data found for pattern analysis (after filtering for notna attendance, weekday, hour).")
        return None
        
    day_attendance = attendance_df.groupby('weekday_name')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_attendance['weekday_name'] = pd.Categorical(day_attendance['weekday_name'], categories=day_order, ordered=True)
    day_attendance = day_attendance.sort_values('weekday_name')
    
    hour_attendance = attendance_df.groupby('hour')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    hour_attendance = hour_attendance.sort_values('hour')
    
    month_attendance = attendance_df.groupby(['month', 'month_name'])['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    month_attendance = month_attendance.sort_values('month')
    
    # Team home attendance requires 'Koti' column
    team_home_attendance = None
    if 'Koti' in attendance_df.columns:
        team_home_attendance = attendance_df.groupby('Koti')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
        team_home_attendance = team_home_attendance.rename(columns={'Koti': 'team'})
        team_home_attendance = team_home_attendance.sort_values('mean', ascending=False)
    else:
        debug_print("Warning: 'Koti' column not found for team_home_attendance analysis.")

    top_matchups = None
    if 'Koti' in attendance_df.columns and 'Vieras' in attendance_df.columns and len(attendance_df) > 10:
        matchups = attendance_df.groupby(['Koti', 'Vieras'])['attendance'].mean().reset_index()
        matchups = matchups.sort_values('attendance', ascending=False)
        top_matchups = matchups.head(5)
    elif not ('Koti' in attendance_df.columns and 'Vieras' in attendance_df.columns):
        debug_print("Warning: 'Koti' or 'Vieras' columns not found for top_matchups analysis.")


    day_hour_data = None
    if len(attendance_df) > 15:
        try:
            day_hour_data = pd.crosstab(
                index=attendance_df['weekday_name'], 
                columns=attendance_df['hour'], 
                values=attendance_df['attendance'], 
                aggfunc='mean'
            )
            day_hour_data = day_hour_data.reindex(day_order).fillna(0) 
        except Exception as e:
            print(f"Could not create day-hour heatmap data: {e}")
            day_hour_data = None

    return {
        'day_attendance': day_attendance,
        'hour_attendance': hour_attendance,
        'month_attendance': month_attendance,
        'team_attendance': team_home_attendance,
        'top_matchups': top_matchups,
        'day_hour_heatmap': day_hour_data
    }

def analyze_venue_performance(df):
    """Analyze venue performance metrics"""
    # Ensure Koti column exists for fallback logic
    if 'Koti' not in df.columns:
        print("Error: 'Koti' column missing, cannot analyze venue performance reliably.")
        return None

    venue_df = df[df['result'].notna() & df['Koti'].notna()].copy() # Koti is essential here
    
    if len(venue_df) == 0:
        print("No valid data for venue performance analysis (after filtering for result, Koti).")
        return None

    if 'Stadion' not in venue_df.columns or venue_df['Stadion'].isnull().all():
        debug_print("Using 'Koti' column as fallback for venue ('Stadion') analysis.")
        venue_df['Stadion_derived'] = venue_df['Koti'] 
    else:
         venue_df['Stadion_derived'] = venue_df['Stadion'].fillna(venue_df['Koti'])

    agg_dict = {
        'matches': ('result', 'count'),
        'home_wins': ('result', lambda x: (x == 'home_win').sum()),
        'away_wins': ('result', lambda x: (x == 'away_win').sum()),
        'draws': ('result', lambda x: (x == 'draw').sum()),
        'total_goals': ('total_goals', 'sum'),
        'avg_goals': ('total_goals', 'mean'),
    }
    if 'attendance' in venue_df.columns and venue_df['attendance'].notna().any():
         agg_dict['avg_attendance'] = ('attendance', 'mean')
         agg_dict['total_attendance'] = ('attendance', 'sum')

    venues = venue_df.groupby('Stadion_derived').agg(**agg_dict).reset_index()
    venues.rename(columns={'Stadion_derived': 'Stadion'}, inplace=True) # Rename back for consistency
    
    venues['home_win_percent'] = venues.apply(lambda row: round((row['home_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['draw_percent'] = venues.apply(lambda row: round((row['draws'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['away_win_percent'] = venues.apply(lambda row: round((row['away_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    
    sort_key = 'avg_attendance' if 'avg_attendance' in venues.columns else 'avg_goals'
    if sort_key not in venues.columns: # Fallback if neither exists
        sort_key = 'matches'
    
    if sort_key in venues.columns:
        return venues.sort_values(sort_key, ascending=False)
    else:
        debug_print(f"Warning: Sort key '{sort_key}' not found in venue_stats. Returning unsorted.")
        return venues


def analyze_team_performance_over_time(df):
    """Analyze how team performance changes over time"""
    # Essential columns for this analysis
    required_perf_cols = ['result', 'match_datetime', 'Koti', 'Vieras', 'home_goals', 'away_goals']
    if not all(col in df.columns and df[col].notna().any() for col in required_perf_cols):
        missing_or_all_null = [col for col in required_perf_cols if col not in df.columns or not df[col].notna().any()]
        print(f"Not enough valid data for temporal analysis. Missing or all-null essential columns: {missing_or_all_null}.")
        return None
        
    time_df = df[df['result'].notna() & df['match_datetime'].notna() & \
                 df['Koti'].notna() & df['Vieras'].notna() & \
                 df['home_goals'].notna() & df['away_goals'].notna()].copy()
    
    if len(time_df) < 5: 
        print(f"Not enough time-based data for temporal analysis (need at least 5 matches with datetime and results, found {len(time_df)}).")
        return None
        
    all_teams = pd.concat([time_df['Koti'], time_df['Vieras']]).unique()
    all_teams = [team for team in all_teams if pd.notna(team)] # Filter out potential NaNs if Koti/Vieras had them

    team_results = []
    for team in all_teams:
        team_matches = time_df[(time_df['Koti'] == team) | (time_df['Vieras'] == team)].sort_values('match_datetime')
        
        if len(team_matches) == 0:
             continue

        for _, match in team_matches.iterrows():
            is_home = match['Koti'] == team
            # Ensure goals are int, though they should be after preprocessing
            home_goals = int(match['home_goals']) 
            away_goals = int(match['away_goals'])

            if is_home:
                points = 3 if match['result'] == 'home_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = home_goals
                goals_against = away_goals
            else: 
                points = 3 if match['result'] == 'away_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = away_goals
                goals_against = home_goals
            
            team_results.append({
                'team': team,
                'match_datetime': match['match_datetime'],
                'opponent': match['Vieras'] if is_home else match['Koti'],
                'is_home': is_home,
                'points': points,
                'goals_for': goals_for,
                'goals_against': goals_against,
                'goal_difference': goals_for - goals_against
            })
            
    if not team_results:
         print("No team results generated for temporal analysis.")
         return None

    team_perf_df = pd.DataFrame(team_results)
    team_perf_df = team_perf_df.sort_values(['team', 'match_datetime'])

    team_cumulative = team_perf_df.copy()
    team_cumulative['cumulative_points'] = team_cumulative.groupby('team')['points'].cumsum()
    team_cumulative['cumulative_goals_for'] = team_cumulative.groupby('team')['goals_for'].cumsum()
    team_cumulative['cumulative_goals_against'] = team_cumulative.groupby('team')['goals_against'].cumsum()
    team_cumulative['cumulative_goal_diff'] = team_cumulative['cumulative_goals_for'] - team_cumulative['cumulative_goals_against']
    team_cumulative['games_played'] = team_cumulative.groupby('team').cumcount() + 1
    
    N = 5
    # Calculate form based on points from the actual 'points' column for each match
    # The .groupby('team')['points'] ensures it's per team
    # .rolling().sum() calculates sum over the window
    # .shift(0) would include current game, .shift(1) is form *before* current game.
    # For "form entering the game", use shift(1). For "form after N games", use shift(0) on cumulative or re-calculate.
    # Let's define form as points from last N *completed* games.
    form_series = team_cumulative.groupby('team')['points'].rolling(window=N, min_periods=1).sum()
    # The result of rolling is multi-indexed, so we need to drop the group index to align it back
    team_cumulative[f'form_points_last_{N}_games'] = form_series.reset_index(level=0, drop=True)
    team_cumulative[f'form_points_last_{N}_games'].fillna(0, inplace=True)

    return team_cumulative

def optimize_match_schedule(attendance_data):
    """Generate recommendations for optimal match scheduling based on attendance patterns"""
    if attendance_data is None:
        print("Cannot optimize schedule without attendance analysis results.")
        return None
        
    if attendance_data.get('day_attendance') is None or attendance_data['day_attendance'].empty or \
       attendance_data.get('hour_attendance') is None or attendance_data['hour_attendance'].empty:
        print("Attendance analysis results for day/hour are empty or missing, cannot generate recommendations.")
        return None

    day_attendance = attendance_data['day_attendance'].sort_values('mean', ascending=False)
    best_days = day_attendance['weekday_name'].tolist()
    
    hour_attendance = attendance_data['hour_attendance'].sort_values('mean', ascending=False)
    best_hours = hour_attendance['hour'].tolist()
    
    month_attendance = attendance_data.get('month_attendance') # Might be None
    day_hour_matrix = attendance_data.get('day_hour_heatmap') # Might be None
    
    recommendations = []
    
    if not best_days or not best_hours:
        print("Best days or best hours list is empty. Cannot proceed with day/time recommendations.")
    else:
        for day in best_days[:3]:
            for hour in best_hours[:3]:
                day_mean_series = day_attendance[day_attendance['weekday_name'] == day]['mean']
                hour_mean_series = hour_attendance[hour_attendance['hour'] == hour]['mean']

                if day_mean_series.empty or hour_mean_series.empty: continue # Should not happen if best_days/hours populated

                day_mean = day_mean_series.iloc[0]
                hour_mean = hour_mean_series.iloc[0]
                
                specific_value = 0
                if day_hour_matrix is not None and day in day_hour_matrix.index and hour in day_hour_matrix.columns:
                    specific_value = day_hour_matrix.loc[day, hour]
                
                priority_score = specific_value if specific_value > 0 else (day_mean + hour_mean) / 2
                
                # Use overall mean from day_attendance if available and not empty
                overall_mean_attendance = 0
                if not attendance_data['day_attendance']['mean'].empty:
                    overall_mean_attendance = attendance_data['day_attendance']['mean'].mean()
                else: # Fallback if day_attendance mean is empty for some reason
                    overall_mean_attendance = (day_mean + hour_mean) / 2 # very rough fallback
                
                priority_cat = "Low" # Default
                if overall_mean_attendance > 0 : # Avoid division by zero or weirdness if 0
                    if priority_score > overall_mean_attendance * 1.2: priority_cat = "High"
                    elif priority_score > overall_mean_attendance * 0.8: priority_cat = "Medium"
                elif priority_score > 0 : # If overall is 0, any positive score is better
                    priority_cat = "Medium"


                notes = []
                if day in ['Saturday', 'Sunday']: notes.append("Weekend slot")
                if isinstance(hour, (int, float)) and 16 <= hour <= 19 : notes.append("Evening slot")
                if specific_value > 0: notes.append(f"Specific combo avg: {round(specific_value)}")
                else: notes.append(f"General day/hour avg: {round(priority_score)}")

                recommendations.append({
                    'day': day,
                    'time': f"{int(hour):02d}:00" if isinstance(hour, (int, float)) else str(hour),
                    'priority': priority_cat,
                    'estimated_attendance_impact_score': round(priority_score),
                    'notes': "; ".join(notes) if notes else "Standard slot"
                })
            
    if month_attendance is not None and not month_attendance.empty:
        best_months = month_attendance.sort_values('mean', ascending=False)
        for _, month_row in best_months.head(2).iterrows():
            recommendations.append({
                'day': 'Any', 'time': 'Any', 'priority': 'Seasonal High',
                'estimated_attendance_impact_score': round(month_row['mean']),
                'notes': f"Consider scheduling key matches in {month_row['month_name']} (historically high attendance)"
            })
            
    top_matchups_data = attendance_data.get('top_matchups')
    if top_matchups_data is not None and not top_matchups_data.empty:
        # Ensure Koti and Vieras columns exist in top_matchups_data
        if 'Koti' in top_matchups_data.columns and 'Vieras' in top_matchups_data.columns:
            for _, matchup in top_matchups_data.head(3).iterrows():
                recommendations.append({
                    'day': best_days[0] if best_days else 'Saturday',
                    'time': f"{int(best_hours[0]):02d}:00" if best_hours and isinstance(best_hours[0], (int,float)) else '18:00',
                    'priority': 'High (Matchup)',
                    'estimated_attendance_impact_score': round(matchup['attendance']),
                    'notes': f"Featured Match: {matchup['Koti']} vs {matchup['Vieras']} draws large crowds."
                })
        else:
            debug_print("Warning: Koti/Vieras columns missing in top_matchups data for recommendations.")
            
    if not recommendations:
         print("Could not generate any schedule recommendations.")
         return None

    recommendations_df = pd.DataFrame(recommendations)
    priority_order = ['High (Matchup)', 'High', 'Seasonal High', 'Medium', 'Low', 'Seasonal Low']
    recommendations_df['priority'] = pd.Categorical(recommendations_df['priority'], categories=priority_order, ordered=True)
    recommendations_df = recommendations_df.sort_values(by=['priority', 'estimated_attendance_impact_score'], ascending=[True, False])
    recommendations_df = recommendations_df.drop_duplicates(subset=['day', 'time'], keep='first')

    return recommendations_df

def visualize_league_standings(league_table):
    """Create visualizations for league table and save them"""
    if league_table is None or len(league_table) == 0:
        print("No league table data available for visualization.")
        return
        
    os.makedirs(PLOTS_DIR, exist_ok=True)
    
    try: # Matplotlib: Basic Points Bar Chart
        plt.figure(figsize=(12, 8))
        bars = plt.bar(league_table['team'], league_table['points'], color=sns.color_palette("viridis", len(league_table)))
        plt.title('Ykkösliiga Points Standings', fontsize=16)
        plt.xlabel('Team', fontsize=12); plt.ylabel('Points', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.5, f"{int(height)}", ha='center', va='bottom', fontsize=10)
        plt.tight_layout()
        plt.savefig(os.path.join(PLOTS_DIR, 'standings_points.png'))
        plt.close()
        debug_print("Points bar chart saved.")
    except Exception as e: print(f"Error creating/saving points bar chart: {e}")

    try: # Plotly: Interactive Standings with Goal Difference
        fig = go.Figure()
        fig.add_trace(go.Bar(x=league_table['team'], y=league_table['points'], name='Points', marker_color='darkblue', text=league_table['points'], textposition='auto'))
        if 'goal_difference' in league_table.columns:
            fig.add_trace(go.Scatter(x=league_table['team'], y=league_table['goal_difference'], name='Goal Difference', mode='lines+markers', marker=dict(size=8, color='red'), yaxis='y2'))
        
        fig.update_layout(
            title='Ykkösliiga Standings with Goal Difference', xaxis_title='Team', yaxis=dict(title='Points'),
            yaxis2=dict(title='Goal Difference', overlaying='y', side='right', showgrid=False) if 'goal_difference' in league_table.columns else {},
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            barmode='group', height=600,
            xaxis={'categoryorder':'array', 'categoryarray': league_table['team'].tolist()}
        )
        fig.write_html(os.path.join(PLOTS_DIR, 'standings_interactive.html'))
        debug_print("Interactive standings chart saved.")
    except Exception as e: print(f"Error creating/saving interactive standings chart: {e}")

    try: # Matplotlib: Stacked Bar Chart for Wins/Draws/Losses
        if all(col in league_table.columns for col in ['wins', 'draws', 'losses']):
            plt.figure(figsize=(14, 10)); width = 0.8
            plt.bar(league_table['team'], league_table['wins'], width, label='Wins', color='forestgreen')
            plt.bar(league_table['team'], league_table['draws'], width, bottom=league_table['wins'], label='Draws', color='gold')
            plt.bar(league_table['team'], league_table['losses'], width, bottom=league_table['wins'] + league_table['draws'], label='Losses', color='firebrick')
            
            plt.title('Match Results Breakdown by Team', fontsize=16)
            plt.xlabel('Team', fontsize=12); plt.ylabel('Number of Matches', fontsize=12)
            plt.xticks(rotation=45, ha='right'); plt.legend()
            
            if all(col in league_table.columns for col in ['played', 'points']):
                 for i, team_name_iter in enumerate(league_table['team']): # Renamed to avoid conflict with 'team' variable
                      total_played = league_table['played'].iloc[i]
                      points_val = league_table['points'].iloc[i]
                      plt.text(i, total_played + 0.5, f"Pts: {int(points_val)}", ha='center', va='bottom', fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, 'team_results_breakdown.png'))
            plt.close()
            debug_print("Results breakdown chart saved.")
        else: print("Skipping results breakdown chart: Missing wins, draws, or losses columns.")
    except Exception as e: print(f"Error creating/saving results breakdown chart: {e}")

    try: # Save League Table to CSV
        os.makedirs(DATA_DIR, exist_ok=True)
        csv_path = os.path.join(DATA_DIR, 'league_standings.csv')
        league_table.to_csv(csv_path, index=False)
        debug_print(f"League table saved to {csv_path}")
    except Exception as e: print(f"Error saving league table to CSV: {e}")

# ===============================================
# Main execution block
# ===============================================
if __name__ == "__main__":
    data_file = "match_data.json"  # Changed to use JSON file
    print(f"Starting analysis using data file: {data_file}")

    match_data_df = load_data(data_file)

    if match_data_df is not None and not match_data_df.empty:
        print(f"Data loaded successfully. Rows: {len(match_data_df)}, Columns: {len(match_data_df.columns)}")
        
        processed_data = preprocess_data(match_data_df.copy()) # Pass a copy

        if processed_data is not None and not processed_data.empty:
            print(f"Data preprocessed successfully. Rows after preprocessing: {len(processed_data)}")

            league_table = calculate_league_table(processed_data.copy()) # Pass a copy
            if league_table is not None and not league_table.empty:
                 print("League table calculated.")
                 visualize_league_standings(league_table.copy()) # Pass a copy
                 print(f"League table visualizations saved to {PLOTS_DIR}")
                 print(f"League table data saved to {os.path.join(DATA_DIR, 'league_standings.csv')}")
            else:
                 print("Could not calculate league table or table is empty.")

            attendance_analysis = analyze_attendance_patterns(processed_data.copy()) # Pass a copy
            if attendance_analysis:
                print("Attendance patterns analyzed.")
                try:
                     if attendance_analysis.get('day_attendance') is not None:
                         attendance_analysis['day_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_day.csv'), index=False)
                     if attendance_analysis.get('hour_attendance') is not None:
                         attendance_analysis['hour_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_hour.csv'), index=False)
                     if attendance_analysis.get('team_attendance') is not None:
                          attendance_analysis['team_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_team_home.csv'), index=False)
                     if attendance_analysis.get('top_matchups') is not None:
                          attendance_analysis['top_matchups'].to_csv(os.path.join(DATA_DIR, 'attendance_top_matchups.csv'), index=False)
                     print(f"Attendance analysis summaries saved to {DATA_DIR}")
                except Exception as e: print(f"Error saving attendance summaries: {e}")

                schedule_recommendations = optimize_match_schedule(attendance_analysis) # No need to copy dict
                if schedule_recommendations is not None and not schedule_recommendations.empty:
                    try:
                         recommendations_path = os.path.join(DATA_DIR, 'schedule_recommendations.csv')
                         schedule_recommendations.to_csv(recommendations_path, index=False)
                         print(f"Schedule recommendations saved to {recommendations_path}")
                    except Exception as e: print(f"Error saving schedule recommendations: {e}")
                else: print("Could not generate schedule recommendations or they are empty.")
            else: print("Attendance pattern analysis skipped, failed, or produced no results.")

            venue_stats = analyze_venue_performance(processed_data.copy()) # Pass a copy
            if venue_stats is not None and not venue_stats.empty:
                try:
                     venue_path = os.path.join(DATA_DIR, 'venue_performance.csv')
                     venue_stats.to_csv(venue_path, index=False)
                     print(f"Venue performance analysis saved to {venue_path}")
                except Exception as e: print(f"Error saving venue performance analysis: {e}")
            else: print("Venue performance analysis skipped, failed, or produced no results.")

            team_perf_over_time = analyze_team_performance_over_time(processed_data.copy()) # Pass a copy
            if team_perf_over_time is not None and not team_perf_over_time.empty :
                try:
                     team_perf_path = os.path.join(DATA_DIR, 'team_performance_over_time.csv')
                     team_perf_over_time.to_csv(team_perf_path, index=False)
                     print(f"Team performance over time analysis saved to {team_perf_path}")
                except Exception as e: print(f"Error saving team performance over time analysis: {e}")
            else: print("Team performance over time analysis skipped, failed, or produced no results.")

            print("\nAnalysis script finished.")
        else:
            print("Data preprocessing failed or resulted in empty data. Halting analysis.")
    else:
        print(f"Data loading from {data_file} failed or file is empty. Halting analysis.")
        # Create an error file in output to signal failure in the workflow
        try:
            with open(os.path.join(OUTPUT_DIR, "analysis_error.log"), "w") as f:
                f.write(f"Failed to load or process data from {data_file} at {datetime.datetime.utcnow().isoformat()}Z. Input data was None or empty.")
        except Exception as e:
            print(f"Failed to write analysis_error.log: {e}")
