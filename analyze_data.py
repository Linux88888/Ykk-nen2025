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
import json
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
    """Load match data from CSV file"""
    try:
        df = pd.read_csv(filepath)
        debug_print(f"Data loaded successfully from {filepath}")
        return df
    except FileNotFoundError:
        print(f"Error: Data file not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error loading data from {filepath}: {e}")
        return None

def preprocess_data(df):
    """Clean and preprocess the data"""
    processed_df = df.copy()
    
    # Ensure required columns exist, otherwise return None or raise error
    required_cols = ['Tulos', 'Pvm', 'Aika', 'Koti', 'Vieras']
    if not all(col in processed_df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in processed_df.columns]
        print(f"Error: Missing required columns in data: {missing}")
        return None
        
    processed_df['home_goals'] = None
    processed_df['away_goals'] = None
    for idx, row in processed_df.iterrows():
        if pd.notna(row['Tulos']):
            try:
                # Handle potential extra characters or spaces around the score
                score_str = str(row['Tulos']).strip()
                score_parts = score_str.split('-')
                if len(score_parts) == 2:
                    processed_df.at[idx, 'home_goals'] = int(score_parts[0].strip())
                    processed_df.at[idx, 'away_goals'] = int(score_parts[1].strip())
                else:
                     debug_print(f"Could not parse score: {row['Tulos']} at index {idx}")
            except ValueError:
                 debug_print(f"Non-integer score part found: {row['Tulos']} at index {idx}")
            except Exception as e:
                 debug_print(f"General error parsing score {row['Tulos']} at index {idx}: {e}")


    processed_df['home_goals'] = pd.to_numeric(processed_df['home_goals'], errors='coerce')
    processed_df['away_goals'] = pd.to_numeric(processed_df['away_goals'], errors='coerce')
    
    # Calculate total_goals only where both home and away goals are valid numbers
    processed_df['total_goals'] = processed_df['home_goals'].add(processed_df['away_goals'], fill_value=0)
    processed_df.loc[processed_df['home_goals'].isna() | processed_df['away_goals'].isna(), 'total_goals'] = np.nan # Ensure total is NaN if parts are missing


    conditions = [
        (processed_df['home_goals'] > processed_df['away_goals']),
        (processed_df['home_goals'] < processed_df['away_goals']),
        (processed_df['home_goals'] == processed_df['away_goals']) & (processed_df['home_goals'].notna()) # Only draw if goals are not NaN
    ]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None)
    
    processed_df['match_datetime'] = None
    for idx, row in processed_df.iterrows():
        if pd.notna(row['Pvm']) and pd.notna(row['Aika']):
            try:
                # Assume date format DD.MM.YYYY or DD.MM.YY
                date_str = str(row['Pvm']).strip()
                time_str = str(row['Aika']).strip()
                
                date_parts = date_str.split('.')
                time_parts = time_str.split(':')
                
                if len(date_parts) >= 2 and len(time_parts) >= 1:
                    day = int(date_parts[0])
                    month = int(date_parts[1])
                    # Handle 2-digit or 4-digit year
                    if len(date_parts) > 2:
                         year_part = int(date_parts[2])
                         year = year_part if year_part > 100 else (2000 + year_part if year_part < 50 else 1900 + year_part) # Heuristic for 2-digit year
                    else: 
                         year = datetime.datetime.now().year # Default to current year if missing
                    
                    hour = int(time_parts[0])
                    minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                    
                    dt = datetime.datetime(year, month, day, hour, minute)
                    processed_df.at[idx, 'match_datetime'] = dt
                else:
                     debug_print(f"Could not parse date/time parts: {row['Pvm']} {row['Aika']}")

            except ValueError:
                 debug_print(f"Date/Time conversion error (ValueError): {row['Pvm']} {row['Aika']}")
            except Exception as e:
                debug_print(f"General date parsing error: {e} for {row['Pvm']} {row['Aika']}")

    processed_df['match_datetime'] = pd.to_datetime(processed_df['match_datetime'], errors='coerce')
    
    # Extract date features only if datetime is valid
    processed_df['date'] = processed_df['match_datetime'].dt.date
    processed_df['year'] = processed_df['match_datetime'].dt.year
    processed_df['month'] = processed_df['match_datetime'].dt.month
    processed_df['day'] = processed_df['match_datetime'].dt.day
    processed_df['weekday'] = processed_df['match_datetime'].dt.weekday
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['hour'] = processed_df['match_datetime'].dt.hour
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    
    # Clean attendance data if column exists
    if 'Yleisö' in processed_df.columns:
        processed_df['attendance'] = processed_df['Yleisö'].astype(str).str.replace(r'\s+', '', regex=True) # Remove all whitespace
        processed_df['attendance'] = pd.to_numeric(processed_df['attendance'], errors='coerce')
        
    # Drop rows where essential data (like goals for calculating table) is missing
    processed_df.dropna(subset=['home_goals', 'away_goals', 'result', 'Koti', 'Vieras'], inplace=True)

    return processed_df

def calculate_league_table(df):
    """Calculate league standings"""
    teams = {}
    # Filter only matches with valid results and teams
    match_df = df[df['result'].notna() & df['Koti'].notna() & df['Vieras'].notna()].copy()
    
    if len(match_df) == 0:
        print("No valid match data found to calculate league table.")
        return None
        
    for _, match in match_df.iterrows():
        # Ensure goals are integers for calculation
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
            teams[away_team]['clean_sheets'] += 1
        if away_goals == 0:
            teams[away_team]['failed_to_score'] += 1
            teams[home_team]['clean_sheets'] += 1
            
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
            
    # PK-35 special handling: started with -2 points (case-insensitive check)
    pk35_key = next((key for key in teams if key.upper() == "PK-35"), None)
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
    # Ensure sorting columns exist before sorting
    sort_cols = ['points', 'goal_difference', 'goals_for']
    if all(col in table_df.columns for col in sort_cols):
        table_df = table_df.sort_values(by=sort_cols, ascending=[False, False, False])
    else:
         print("Warning: Could not sort league table due to missing columns.")
         # Fallback sort by points if possible
         if 'points' in table_df.columns:
              table_df = table_df.sort_values(by='points', ascending=False)

    # Add rank
    table_df.reset_index(drop=True, inplace=True)
    table_df.index += 1 # Start rank from 1
    table_df['rank'] = table_df.index

    # Reorder columns for better readability
    ordered_cols = ['rank', 'team', 'played', 'wins', 'draws', 'losses', 'goals_for', 'goals_against', 'goal_difference', 'points']
    # Add optional columns if they exist
    for col in ['avg_goals_for', 'avg_goals_against', 'win_percentage', 'clean_sheets', 'failed_to_score']:
         if col in table_df.columns:
              ordered_cols.append(col)
    table_df = table_df[ordered_cols]

    return table_df

def analyze_attendance_patterns(df):
    """Analyze attendance patterns to identify optimal scheduling"""
    if 'attendance' not in df.columns:
        print("Attendance data ('Yleisö' column) not found.")
        return None
        
    attendance_df = df[df['attendance'].notna() & df['weekday_name'].notna() & df['hour'].notna()].copy()
    if len(attendance_df) == 0:
        print("No valid attendance data found for pattern analysis.")
        return None
        
    # Analyze by day of week
    day_attendance = attendance_df.groupby('weekday_name')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    # Use pd.Categorical for sorting
    day_attendance['weekday_name'] = pd.Categorical(day_attendance['weekday_name'], categories=day_order, ordered=True)
    day_attendance = day_attendance.sort_values('weekday_name')
    
    # Analyze by hour
    hour_attendance = attendance_df.groupby('hour')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    hour_attendance = hour_attendance.sort_values('hour')
    
    # Analyze by month
    month_attendance = attendance_df.groupby(['month', 'month_name'])['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    month_attendance = month_attendance.sort_values('month')
    
    # Analyze by team (home attendance)
    team_home_attendance = attendance_df.groupby('Koti')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    team_home_attendance = team_home_attendance.rename(columns={'Koti': 'team'})
    team_home_attendance = team_home_attendance.sort_values('mean', ascending=False)
    
    top_matchups = None
    if len(attendance_df) > 10: # Only if enough data
        matchups = attendance_df.groupby(['Koti', 'Vieras'])['attendance'].mean().reset_index()
        matchups = matchups.sort_values('attendance', ascending=False)
        top_matchups = matchups.head(5)

    day_hour_data = None
    if len(attendance_df) > 15: # Only if enough data
        try:
            day_hour_data = pd.crosstab(
                index=attendance_df['weekday_name'], 
                columns=attendance_df['hour'], 
                values=attendance_df['attendance'], 
                aggfunc='mean'
            )
            # Reindex to ensure all days are in correct order and fill NaNs
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
    # Use only matches with valid results and teams
    venue_df = df[df['result'].notna() & df['Koti'].notna()].copy()
    
    if len(venue_df) == 0:
        print("No valid data for venue performance analysis.")
        return None

    # Create venue field if 'Stadion' column doesn't exist
    if 'Stadion' not in venue_df.columns or venue_df['Stadion'].isnull().all():
        debug_print("Using 'Koti' column as fallback for venue analysis.")
        venue_df['Stadion'] = venue_df['Koti'] # Use home team as proxy for venue if missing
    else:
         # Fill missing Stadion values if some exist but not all
         venue_df['Stadion'] = venue_df['Stadion'].fillna(venue_df['Koti'])


    # Define aggregations, handle optional attendance
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

    venues = venue_df.groupby('Stadion').agg(**agg_dict).reset_index()
    
    # Calculate percentages safely (avoid division by zero)
    venues['home_win_percent'] = venues.apply(lambda row: round((row['home_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['draw_percent'] = venues.apply(lambda row: round((row['draws'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['away_win_percent'] = venues.apply(lambda row: round((row['away_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    
    # Sort by a relevant metric, e.g., average goals or attendance
    sort_key = 'avg_attendance' if 'avg_attendance' in venues.columns else 'avg_goals'
    return venues.sort_values(sort_key, ascending=False)

def analyze_team_performance_over_time(df):
    """Analyze how team performance changes over time"""
    # Ensure datetime is properly set and result exists
    time_df = df[df['result'].notna() & df['match_datetime'].notna() & df['Koti'].notna() & df['Vieras'].notna()].copy()
    
    if len(time_df) < 5: # Need at least a few games for meaningful temporal analysis
        print("Not enough time-based data for temporal analysis (need at least 5 matches with datetime).")
        return None
        
    # Get unique teams from both home and away columns
    all_teams = pd.concat([time_df['Koti'], time_df['Vieras']]).unique()
    
    team_results = []
    for team in all_teams:
        # Get all matches where this team played (home or away)
        team_matches = time_df[(time_df['Koti'] == team) | (time_df['Vieras'] == team)].sort_values('match_datetime')
        
        if len(team_matches) == 0:
             continue # Skip if somehow a team has no matches in the filtered data

        for _, match in team_matches.iterrows():
            is_home = match['Koti'] == team
            home_goals = int(match['home_goals'])
            away_goals = int(match['away_goals'])

            if is_home:
                points = 3 if match['result'] == 'home_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = home_goals
                goals_against = away_goals
            else: # Away team
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
    # Sort globally by time before calculating cumulative stats per team
    team_perf_df = team_perf_df.sort_values(['team', 'match_datetime'])

    # Calculate running totals per team
    team_cumulative = team_perf_df.copy()
    team_cumulative['cumulative_points'] = team_cumulative.groupby('team')['points'].cumsum()
    team_cumulative['cumulative_goals_for'] = team_cumulative.groupby('team')['goals_for'].cumsum()
    team_cumulative['cumulative_goals_against'] = team_cumulative.groupby('team')['goals_against'].cumsum()
    team_cumulative['cumulative_goal_diff'] = team_cumulative['cumulative_goals_for'] - team_cumulative['cumulative_goals_against']
    team_cumulative['games_played'] = team_cumulative.groupby('team').cumcount() + 1
    
    # Calculate form (points in last N games, e.g., 5)
    N = 5
    # Use rolling window on points, sum over the last N games for each team
    # shift(1) ensures the form is based on games *before* the current one
    team_cumulative[f'form_points_last_{N}'] = team_cumulative.groupby('team')['points'].rolling(window=N, min_periods=1).sum().shift(1).reset_index(level=0, drop=True)
    # Fill NaN for the first game's "form"
    team_cumulative[f'form_points_last_{N}'].fillna(0, inplace=True)


    return team_cumulative

def optimize_match_schedule(attendance_data):
    """Generate recommendations for optimal match scheduling based on attendance patterns"""
    if attendance_data is None:
        print("Cannot optimize schedule without attendance analysis results.")
        return None
        
    # Check if analysis results are empty or missing
    if attendance_data['day_attendance'].empty or attendance_data['hour_attendance'].empty:
        print("Attendance analysis results are empty, cannot generate recommendations.")
        return None

    # Get top days/hours by mean attendance
    day_attendance = attendance_data['day_attendance'].sort_values('mean', ascending=False)
    best_days = day_attendance['weekday_name'].tolist()
    
    hour_attendance = attendance_data['hour_attendance'].sort_values('mean', ascending=False)
    best_hours = hour_attendance['hour'].tolist()
    
    month_attendance = attendance_data['month_attendance']
    day_hour_matrix = attendance_data['day_hour_heatmap'] # This might be None
    
    recommendations = []
    
    # 1. Best Day-Time Combinations based on individual means
    # Take top 3 days and top 3 hours
    for day in best_days[:3]:
        for hour in best_hours[:3]:
            day_mean = day_attendance[day_attendance['weekday_name'] == day]['mean'].iloc[0]
            hour_mean = hour_attendance[hour_attendance['hour'] == hour]['mean'].iloc[0]
            
            # Use specific day-hour mean if available from heatmap, otherwise average the individual means
            specific_value = 0
            if day_hour_matrix is not None and day in day_hour_matrix.index and hour in day_hour_matrix.columns:
                specific_value = day_hour_matrix.loc[day, hour]
            
            # Priority score: prefer specific intersection, fallback to average
            priority_score = specific_value if specific_value > 0 else (day_mean + hour_mean) / 2
            
            # Simple priority category based on score relative to overall mean
            overall_mean_attendance = attendance_data['day_attendance']['mean'].mean() # Rough estimate
            if priority_score > overall_mean_attendance * 1.2:
                priority_cat = "High"
            elif priority_score > overall_mean_attendance * 0.8:
                 priority_cat = "Medium"
            else:
                 priority_cat = "Low"
                 
            notes = []
            if day in ['Saturday', 'Sunday']:
                notes.append("Weekend slot")
            if 16 <= hour <= 19:
                notes.append("Evening slot (post-work potential)")
            if specific_value > 0:
                 notes.append(f"Specific combo avg: {round(specific_value)}")
            else:
                 notes.append(f"General day/hour avg: {round(priority_score)}")


            recommendations.append({
                'day': day,
                'time': f"{int(hour):02d}:00", # Format hour nicely
                'priority': priority_cat,
                'estimated_attendance_impact_score': round(priority_score),
                'notes': "; ".join(notes) if notes else "Standard slot"
            })
            
    # 2. Month-specific recommendations
    if not month_attendance.empty:
        best_months = month_attendance.sort_values('mean', ascending=False)
        for _, month_row in best_months.head(2).iterrows():
            recommendations.append({
                'day': 'Any',
                'time': 'Any',
                'priority': 'Seasonal High',
                'estimated_attendance_impact_score': round(month_row['mean']),
                'notes': f"Consider scheduling key matches in {month_row['month_name']} (historically high attendance)"
            })
            
    # 3. Derby/Rivalry recommendations
    if attendance_data['top_matchups'] is not None and not attendance_data['top_matchups'].empty:
        for _, matchup in attendance_data['top_matchups'].head(3).iterrows():
            # Suggest placing these high-drawing matchups in the best overall slots
            recommendations.append({
                'day': best_days[0] if best_days else 'Saturday', # Fallback
                'time': f"{int(best_hours[0]):02d}:00" if best_hours else '18:00', # Fallback
                'priority': 'High (Matchup)',
                'estimated_attendance_impact_score': round(matchup['attendance']),
                'notes': f"Featured Match: {matchup['Koti']} vs {matchup['Vieras']} draws large crowds. Schedule in prime slot."
            })
            
    if not recommendations:
         print("Could not generate any schedule recommendations.")
         return None

    recommendations_df = pd.DataFrame(recommendations)
    
    # Define priority order for sorting
    priority_order = ['High (Matchup)', 'High', 'Seasonal High', 'Medium', 'Low', 'Seasonal Low']
    recommendations_df['priority'] = pd.Categorical(recommendations_df['priority'], categories=priority_order, ordered=True)

    # Sort by priority, then by estimated impact
    recommendations_df = recommendations_df.sort_values(
        by=['priority', 'estimated_attendance_impact_score'], 
        ascending=[True, False]
        )
    # Remove duplicates based on day/time, keeping the one with highest score/priority
    recommendations_df = recommendations_df.drop_duplicates(subset=['day', 'time'], keep='first')

    return recommendations_df

def visualize_league_standings(league_table):
    """Create visualizations for league table and save them"""
    if league_table is None or len(league_table) == 0:
        print("No league table data available for visualization.")
        return
        
    # Ensure the output directory exists
    os.makedirs(PLOTS_DIR, exist_ok=True)
    
    # --- Matplotlib: Basic Points Bar Chart ---
    try:
        plt.figure(figsize=(12, 8))
        bars = plt.bar(league_table['team'], league_table['points'], color=sns.color_palette("viridis", len(league_table)))
        plt.title('Ykkösliiga Points Standings', fontsize=16)
        plt.xlabel('Team', fontsize=12)
        plt.ylabel('Points', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                     f"{int(height)}",
                     ha='center', va='bottom', fontsize=10)
        plt.tight_layout()
        plt.savefig(os.path.join(PLOTS_DIR, 'standings_points.png'))
        plt.close() # Close the plot to free memory
        debug_print("Points bar chart saved.")
    except Exception as e:
        print(f"Error creating/saving points bar chart: {e}")

    # --- Plotly: Interactive Standings with Goal Difference ---
    try:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=league_table['team'],
            y=league_table['points'],
            name='Points',
            marker_color='darkblue',
            text=league_table['points'],
            textposition='auto'
        ))
        # Add Goal Difference line only if the column exists
        if 'goal_difference' in league_table.columns:
            fig.add_trace(go.Scatter(
                x=league_table['team'],
                y=league_table['goal_difference'],
                name='Goal Difference',
                mode='lines+markers',
                marker=dict(size=8, color='red'),
                yaxis='y2' # Assign to secondary y-axis
            ))
        
        fig.update_layout(
            title='Ykkösliiga Standings with Goal Difference',
            xaxis_title='Team',
            yaxis=dict(title='Points'),
            yaxis2=dict(
                title='Goal Difference',
                overlaying='y',
                side='right',
                showgrid=False, # Hide grid for secondary axis if desired
            ) if 'goal_difference' in league_table.columns else {}, # Add secondary axis only if GD exists
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            barmode='group',
            height=600,
            xaxis={'categoryorder':'array', 'categoryarray': league_table['team'].tolist()} # Ensure order matches table
        )
        fig.write_html(os.path.join(PLOTS_DIR, 'standings_interactive.html'))
        debug_print("Interactive standings chart saved.")
    except Exception as e:
        print(f"Error creating/saving interactive standings chart: {e}")

    # --- Matplotlib: Stacked Bar Chart for Wins/Draws/Losses ---
    try:
        plt.figure(figsize=(14, 10))
        width = 0.8
        # Check if W/D/L columns exist
        if all(col in league_table.columns for col in ['wins', 'draws', 'losses']):
            plt.bar(league_table['team'], league_table['wins'], width, label='Wins', color='forestgreen')
            plt.bar(league_table['team'], league_table['draws'], width, bottom=league_table['wins'], label='Draws', color='gold')
            plt.bar(league_table['team'], league_table['losses'], width, 
                       bottom=league_table['wins'] + league_table['draws'], label='Losses', color='firebrick')
            
            plt.title('Match Results Breakdown by Team', fontsize=16)
            plt.xlabel('Team', fontsize=12)
            plt.ylabel('Number of Matches', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.legend()
            
            # Add points labels at the top if 'played' and 'points' columns exist
            if all(col in league_table.columns for col in ['played', 'points']):
                 for i, team in enumerate(league_table['team']):
                      total_played = league_table['played'].iloc[i]
                      points_val = league_table['points'].iloc[i]
                      plt.text(i, total_played + 0.5, f"Points: {int(points_val)}", 
                              ha='center', va='bottom', fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(os.path.join(PLOTS_DIR, 'team_results_breakdown.png'))
            plt.close() # Close the plot
            debug_print("Results breakdown chart saved.")
        else:
             print("Skipping results breakdown chart: Missing wins, draws, or losses columns.")
             
    except Exception as e:
        print(f"Error creating/saving results breakdown chart: {e}")

    # --- Save League Table to CSV ---
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        csv_path = os.path.join(DATA_DIR, 'league_standings.csv')
        league_table.to_csv(csv_path, index=False)
        debug_print(f"League table saved to {csv_path}")
    except Exception as e:
        print(f"Error saving league table to CSV: {e}")

# ===============================================
# Main execution block
# ===============================================
if __name__ == "__main__":
    # --- Configuration ---
    # Define the path to your data file here. 
    # It could be relative to the script location or an absolute path.
    # Make sure this file exists when the script runs in the GitHub Action.
    data_file = "ottelut.csv"  # <-- !!! VAIHDA TÄHÄN OIKEA TIEDOSTONIMI JA SIJAINTI !!!

    print(f"Starting analysis using data file: {data_file}")

    # 1. Load Data
    match_data = load_data(data_file)

    if match_data is not None:
        print("Data loaded successfully.")
        
        # 2. Preprocess Data
        processed_data = preprocess_data(match_data)

        if processed_data is not None and not processed_data.empty:
            print("Data preprocessed successfully.")

            # 3. Calculate League Table
            league_table = calculate_league_table(processed_data)
            if league_table is not None:
                 print("League table calculated.")
                 # 4. Visualize League Table (also saves table to CSV)
                 visualize_league_standings(league_table)
                 print(f"League table visualizations saved to {PLOTS_DIR}")
                 print(f"League table data saved to {os.path.join(DATA_DIR, 'league_standings.csv')}")
            else:
                 print("Could not calculate league table.")


            # 5. Analyze Attendance Patterns
            attendance_analysis = analyze_attendance_patterns(processed_data)
            if attendance_analysis:
                print("Attendance patterns analyzed.")
                try:
                     # Save key attendance summaries
                     attendance_analysis['day_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_day.csv'), index=False)
                     attendance_analysis['hour_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_hour.csv'), index=False)
                     if attendance_analysis['team_attendance'] is not None:
                          attendance_analysis['team_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_team_home.csv'), index=False)
                     if attendance_analysis['top_matchups'] is not None:
                          attendance_analysis['top_matchups'].to_csv(os.path.join(DATA_DIR, 'attendance_top_matchups.csv'), index=False)
                     print(f"Attendance analysis summaries saved to {DATA_DIR}")
                except Exception as e:
                     print(f"Error saving attendance summaries: {e}")

                # 6. Optimize Match Schedule based on attendance
                schedule_recommendations = optimize_match_schedule(attendance_analysis)
                if schedule_recommendations is not None:
                    try:
                         recommendations_path = os.path.join(DATA_DIR, 'schedule_recommendations.csv')
                         schedule_recommendations.to_csv(recommendations_path, index=False)
                         print(f"Schedule recommendations saved to {recommendations_path}")
                    except Exception as e:
                         print(f"Error saving schedule recommendations: {e}")
                else:
                     print("Could not generate schedule recommendations.")
            else:
                 print("Attendance pattern analysis skipped or failed.")

            # 7. Analyze Venue Performance
            venue_stats = analyze_venue_performance(processed_data)
            if venue_stats is not None:
                try:
                     venue_path = os.path.join(DATA_DIR, 'venue_performance.csv')
                     venue_stats.to_csv(venue_path, index=False)
                     print(f"Venue performance analysis saved to {venue_path}")
                except Exception as e:
                     print(f"Error saving venue performance analysis: {e}")
            else:
                 print("Venue performance analysis skipped or failed.")

            # 8. Analyze Team Performance Over Time
            team_perf_over_time = analyze_team_performance_over_time(processed_data)
            if team_perf_over_time is not None:
                try:
                     team_perf_path = os.path.join(DATA_DIR, 'team_performance_over_time.csv')
                     team_perf_over_time.to_csv(team_perf_path, index=False)
                     print(f"Team performance over time analysis saved to {team_perf_path}")
                except Exception as e:
                     print(f"Error saving team performance over time analysis: {e}")

            else:
                 print("Team performance over time analysis skipped or failed.")

            print("\nAnalysis script finished.")

        else:
            print("Data preprocessing failed or resulted in empty data. Halting analysis.")
    else:
        print("Data loading failed. Halting analysis.")
        # Create an error file in output to signal failure in the workflow
        with open(os.path.join(OUTPUT_DIR, "analysis_error.log"), "w") as f:
            f.write(f"Failed to load data from {data_file} at {datetime.datetime.utcnow().isoformat()}Z")
