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
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def preprocess_data(df):
    """Clean and preprocess the data"""
    processed_df = df.copy()
    processed_df['home_goals'] = None
    processed_df['away_goals'] = None
    for idx, row in processed_df.iterrows():
        if pd.notna(row['Tulos']):
            try:
                score_parts = row['Tulos'].split('-')
                if len(score_parts) == 2:
                    processed_df.at[idx, 'home_goals'] = int(score_parts[0].strip())
                    processed_df.at[idx, 'away_goals'] = int(score_parts[1].strip())
            except:
                pass
    processed_df['home_goals'] = pd.to_numeric(processed_df['home_goals'], errors='coerce')
    processed_df['away_goals'] = pd.to_numeric(processed_df['away_goals'], errors='coerce')
    processed_df['total_goals'] = processed_df['home_goals'] + processed_df['away_goals']
    conditions = [
        (processed_df['home_goals'] > processed_df['away_goals']),
        (processed_df['home_goals'] < processed_df['away_goals']),
        (processed_df['home_goals'] == processed_df['away_goals'])
    ]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None)
    processed_df['match_datetime'] = None
    for idx, row in processed_df.iterrows():
        if pd.notna(row['Pvm']) and pd.notna(row['Aika']):
            try:
                date_parts = str(row['Pvm']).split('.')
                time_parts = str(row['Aika']).split(':')
                day = int(date_parts[0])
                month = int(date_parts[1])
                year = int(date_parts[2]) if len(date_parts) > 2 else datetime.datetime.now().year
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                dt = datetime.datetime(year, month, day, hour, minute)
                processed_df.at[idx, 'match_datetime'] = dt
            except Exception as e:
                debug_print(f"Date parsing error: {e} for {row['Pvm']} {row['Aika']}")
    processed_df['match_datetime'] = pd.to_datetime(processed_df['match_datetime'])
    processed_df['date'] = processed_df['match_datetime'].dt.date
    processed_df['year'] = processed_df['match_datetime'].dt.year
    processed_df['month'] = processed_df['match_datetime'].dt.month
    processed_df['day'] = processed_df['match_datetime'].dt.day
    processed_df['weekday'] = processed_df['match_datetime'].dt.weekday
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['hour'] = processed_df['match_datetime'].dt.hour
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    if 'Yleisö' in processed_df.columns:
        processed_df['attendance'] = processed_df['Yleisö'].astype(str).str.replace(' ', '')
        processed_df['attendance'] = pd.to_numeric(processed_df['attendance'], errors='coerce')
    return processed_df

def calculate_league_table(df):
    """Calculate league standings"""
    teams = {}
    match_df = df[df['result'].notna()].copy()
    for _, match in match_df.iterrows():
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
        teams[home_team]['goals_for'] += match['home_goals']
        teams[home_team]['goals_against'] += match['away_goals']
        teams[away_team]['goals_for'] += match['away_goals']
        teams[away_team]['goals_against'] += match['home_goals']
        if match['home_goals'] == 0:
            teams[home_team]['failed_to_score'] += 1
            teams[away_team]['clean_sheets'] += 1
        if match['away_goals'] == 0:
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
        else:
            teams[home_team]['draws'] += 1
            teams[home_team]['points'] += 1
            teams[away_team]['draws'] += 1
            teams[away_team]['points'] += 1
    if "PK-35" in teams:
        debug_print("Handling PK-35 with -2 point start")
        teams["PK-35"]['points'] -= 2
    for team_name, stats in teams.items():
        stats['goal_difference'] = stats['goals_for'] - stats['goals_against']
        stats['avg_goals_for'] = round(stats['goals_for'] / stats['played'], 2) if stats['played'] > 0 else 0
        stats['avg_goals_against'] = round(stats['goals_against'] / stats['played'], 2) if stats['played'] > 0 else 0
        stats['win_percentage'] = round((stats['wins'] / stats['played']) * 100, 1) if stats['played'] > 0 else 0
        stats['team'] = team_name
    table_df = pd.DataFrame(list(teams.values()))
    table_df = table_df.sort_values(by=['points', 'goal_difference', 'goals_for'], ascending=[False, False, False])
    return table_df

def analyze_attendance_patterns(df):
    """Analyze attendance patterns to identify optimal scheduling"""
    if 'attendance' not in df.columns:
        print("No attendance data available")
        return None
    attendance_df = df[df['attendance'].notna()].copy()
    if len(attendance_df) == 0:
        print("No valid attendance data found")
        return None
    day_attendance = attendance_df.groupby('weekday_name')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_attendance['day_order'] = day_attendance['weekday_name'].apply(lambda x: day_order.index(x) if x in day_order else 999)
    day_attendance = day_attendance.sort_values('day_order')
    day_attendance = day_attendance.drop('day_order', axis=1)
    hour_attendance = attendance_df.groupby('hour')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    hour_attendance = hour_attendance.sort_values('hour')
    month_attendance = attendance_df.groupby(['month', 'month_name'])['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    month_attendance = month_attendance.sort_values('month')
    team_home_attendance = attendance_df.groupby('Koti')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    team_home_attendance = team_home_attendance.rename(columns={'Koti': 'team'})
    team_home_attendance = team_home_attendance.sort_values('mean', ascending=False)
    if len(attendance_df) > 10:
        matchups = attendance_df.groupby(['Koti', 'Vieras'])['attendance'].mean().reset_index()
        matchups = matchups.sort_values('attendance', ascending=False)
        top_matchups = matchups.head(5)
    else:
        top_matchups = None
    if len(attendance_df) > 15:
        day_hour_data = pd.crosstab(
            index=attendance_df['weekday_name'], 
            columns=attendance_df['hour'], 
            values=attendance_df['attendance'], 
            aggfunc='mean'
        )
        day_hour_data = day_hour_data.reindex(day_order)
    else:
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
    venue_df = df[df['result'].notna()].copy()
    if 'Stadion' not in venue_df.columns:
        venue_df['Stadion'] = venue_df['Koti'] + " Stadium"
    venues = venue_df.groupby('Stadion').agg(
        matches=('result', 'count'),
        home_wins=('result', lambda x: (x == 'home_win').sum()),
        away_wins=('result', lambda x: (x == 'away_win').sum()),
        draws=('result', lambda x: (x == 'draw').sum()),
        total_goals=('total_goals', 'sum'),
        avg_goals=('total_goals', 'mean'),
        avg_attendance=('attendance', 'mean') if 'attendance' in venue_df.columns else ('result', 'count'),
    ).reset_index()
    venues['home_win_percent'] = round((venues['home_wins'] / venues['matches']) * 100, 1)
    venues['draw_percent'] = round((venues['draws'] / venues['matches']) * 100, 1)
    venues['away_win_percent'] = round((venues['away_wins'] / venues['matches']) * 100, 1)
    return venues.sort_values('avg_goals', ascending=False)

def analyze_team_performance_over_time(df):
    """Analyze how team performance changes over time"""
    time_df = df[df['result'].notna()].copy()
    time_df = time_df[time_df['match_datetime'].notna()].copy()
    if len(time_df) < 5:
        print("Not enough time-based data for temporal analysis")
        return None
    team_results = []
    for team in time_df['Koti'].unique():
        team_matches = time_df[(time_df['Koti'] == team) | (time_df['Vieras'] == team)].sort_values('match_datetime')
        for _, match in team_matches.iterrows():
            is_home = match['Koti'] == team
            if is_home:
                points = 3 if match['result'] == 'home_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = match['home_goals']
                goals_against = match['away_goals']
            else:
                points = 3 if match['result'] == 'away_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = match['away_goals']
                goals_against = match['home_goals']
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
    team_perf_df = pd.DataFrame(team_results)
    team_cumulative = team_perf_df.copy()
    team_cumulative['cumulative_points'] = team_cumulative.groupby('team')['points'].cumsum()
    team_cumulative['cumulative_goals_for'] = team_cumulative.groupby('team')['goals_for'].cumsum()
    team_cumulative['cumulative_goals_against'] = team_cumulative.groupby('team')['goals_against'].cumsum()
    team_cumulative['cumulative_goal_diff'] = team_cumulative['cumulative_goals_for'] - team_cumulative['cumulative_goals_against']
    team_cumulative['games_played'] = team_cumulative.groupby('team').cumcount() + 1
    team_form = []
    for team in team_cumulative['team'].unique():
        team_data = team_cumulative[team_cumulative['team'] == team].sort_values('match_datetime')
        for i in range(len(team_data)):
            if i >= 5:
                last_5 = team_data.iloc[i-5:i]
                form_points = last_5['points'].sum()
            else:
                form_points = team_data.iloc[:i]['points'].sum() if i > 0 else 0
            team_form.append({
                'team': team,
                'match_datetime': team_data.iloc[i]['match_datetime'],
                'form_points': form_points
            })
    form_df = pd.DataFrame(team_form)
    team_analysis = pd.merge(
        team_cumulative,
        form_df,
        on=['team', 'match_datetime'],
        how='left'
    )
    return team_analysis

def optimize_match_schedule(attendance_data):
    """Generate recommendations for optimal match scheduling"""
    if attendance_data is None:
        return None
    day_attendance = attendance_data['day_attendance']
    best_days = day_attendance.sort_values('mean', ascending=False)['weekday_name'].tolist()
    hour_attendance = attendance_data['hour_attendance']
    best_hours = hour_attendance.sort_values('mean', ascending=False)['hour'].tolist()
    month_attendance = attendance_data['month_attendance']
    day_hour_matrix = attendance_data['day_hour_heatmap']
    recommendations = []
    for day in best_days[:3]:
        for hour in best_hours[:3]:
            day_mean = day_attendance[day_attendance['weekday_name'] == day]['mean'].values[0]
            hour_mean = hour_attendance[hour_attendance['hour'] == hour]['mean'].values[0]
            specific_value = None
            if day_hour_matrix is not None and day in day_hour_matrix.index and hour in day_hour_matrix.columns:
                specific_value = day_hour_matrix.loc[day, hour]
            if specific_value is not None:
                priority = specific_value
            else:
                priority = (day_mean + hour_mean) / 2
            priority_cat = "High"
            if len(recommendations) > 3:
                priority_cat = "Medium"
            if len(recommendations) > 6:
                priority_cat = "Low"
            notes = []
            if day in ['Saturday', 'Sunday']:
                notes.append("Weekend games typically draw larger crowds")
            if 16 <= hour <= 19:
                notes.append("Evening games are popular after work hours")
            recommendations.append({
                'day': day,
                'time': f"{hour}:00",
                'priority': priority_cat,
                'estimated_attendance_impact': round(priority),
                'notes': "; ".join(notes) if notes else "Standard match slot"
            })
    if len(month_attendance) > 0:
        best_months = month_attendance.sort_values('mean', ascending=False)
        for _, month_row in best_months.head(2).iterrows():
            recommendations.append({
                'day': 'Any',
                'time': 'Any',
                'priority': 'Seasonal',
                'estimated_attendance_impact': round(month_row['mean']),
                'notes': f"Schedule key matches in {month_row['month_name']} for maximum attendance"
            })
    if attendance_data['top_matchups'] is not None and len(attendance_data['top_matchups']) > 0:
        for _, matchup in attendance_data['top_matchups'].head(3).iterrows():
            recommendations.append({
                'day': best_days[0] if len(best_days) > 0 else 'Saturday',
                'time': f"{best_hours[0]}:00" if len(best_hours) > 0 else '18:00',
                'priority': 'High',
                'estimated_attendance_impact': round(matchup['attendance']),
                'notes': f"Schedule {matchup['Koti']} vs {matchup['Vieras']} as a featured match"
            })
    recommendations_df = pd.DataFrame(recommendations)
    recommendations_df = recommendations_df.sort_values(['priority', 'estimated_attendance_impact'], 
                                                       ascending=[True, False])
    return recommendations_df

def visualize_league_standings(league_table):
    """Create visualizations for league table"""
    if league_table is None or len(league_table) == 0:
        print("No league table data available for visualization")
        return
    table = league_table.sort_values('points', ascending=False)
    plt.figure(figsize=(12, 8))
    bars = plt.bar(table['team'], table['points'], color=sns.color_palette("viridis", len(table)))
    plt.title('Ykkösliiga Points Standings', fontsize=16)
    plt.xlabel('Team', fontsize=12)
    plt.ylabel('Points', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                 f"{int(height)}",
                 ha='center', va='bottom', fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'standings_points.png'))
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=table['team'],
        y=table['points'],
        name='Points',
        marker_color='darkblue',
        text=table['points'],
        textposition='auto'
    ))
    fig.add_trace(go.Scatter(
        x=table['team'],
        y=table['goal_difference'],
        name='Goal Difference',
        mode='lines+markers',
        marker=dict(size=8, color='red'),
        yaxis='y2'
    ))
    fig.update_layout(
        title='Ykkösliiga Standings with Goal Difference',
        xaxis_title='Team',
        yaxis_title='Points',
        yaxis2=dict(
            title='Goal Difference',
            overlaying='y',
            side='right',
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        barmode='group',
        height=600
    )
    fig.write_html(os.path.join(PLOTS_DIR, 'standings_interactive.html'))
    plt.figure(figsize=(14, 10))
    width = 0.8
    bars1 = plt.bar(table['team'], table['wins'], width, label='Wins', color='forestgreen')
    bars2 = plt.bar(table['team'], table['draws'], width, bottom=table['wins'], label='Draws', color='gold')
    bars3 = plt.bar(table['team'], table['losses'], width, 
                   bottom=table['wins'] + table['draws'], label='Losses', color='firebrick')
    plt.title('Match Results Breakdown by Team', fontsize=16)
    plt.xlabel('Team', fontsize=12)
    plt.ylabel('Number of Matches', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.legend()
    for i, team in enumerate(table['team']):
        plt.text(i, table['played'].iloc[i] + 0.5, f"Points: {table['points'].iloc[i]}", 
                ha='center', va='bottom', fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'team_results_breakdown.png'))
    # Output table as CSV
    table.to_csv(os.path.join(DATA_DIR, 'league_standings.csv'), index=False)
    debug_print("League table saved as CSV.")
    print("Visualizations saved to:", PLOTS_DIR)
    print("League table saved to:", os.path.join(DATA_DIR, 'league_standings.csv'))
