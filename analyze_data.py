import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import calendar
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LinearRegression
import warnings
import os

# Suppress FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Configuration
DEBUG = False  # Set to True to enable debug prints
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

def parse_score(score_str):
    """Parse score string into home and away goals"""
    try:
        if pd.isna(score_str) or score_str == '-':
            return None, None
        
        parts = score_str.split('-')
        home_goals = int(parts[0].strip())
        away_goals = int(parts[1].strip())
        return home_goals, away_goals
    except:
        debug_print(f"Could not parse score: {score_str}")
        return None, None

def parse_datetime(date_str, time_str):
    """Parse date and time strings into datetime object"""
    if pd.isna(date_str) or pd.isna(time_str):
        return None
    
    try:
        date_parts = date_str.split('.')
        day = int(date_parts[0])
        month = int(date_parts[1])
        year = int(date_parts[2]) if len(date_parts) > 2 else 2023
        
        time_parts = time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        
        return datetime(year, month, day, hour, minute)
    except:
        debug_print(f"Could not parse datetime: {date_str} {time_str}")
        return None

def calculate_league_table(df):
    """
    Calculate league table with points, goals, etc.
    Returns a DataFrame sorted by points (descending)
    """
    teams = {}
    
    # Process each match
    for _, match in df.iterrows():
        if pd.isna(match['Tulos']):
            continue  # Skip matches without results
            
        home_team = match['Koti']
        away_team = match['Vieras']
        home_goals, away_goals = parse_score(match['Tulos'])
        
        if home_goals is None:
            continue
            
        # Initialize teams if not already in dict
        if home_team not in teams:
            teams[home_team] = {'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 
                              'goals_for': 0, 'goals_against': 0, 'points': 0}
        if away_team not in teams:
            teams[away_team] = {'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 
                              'goals_for': 0, 'goals_against': 0, 'points': 0}
        
        # Update home team stats
        teams[home_team]['played'] += 1
        teams[home_team]['goals_for'] += home_goals
        teams[home_team]['goals_against'] += away_goals
        
        # Update away team stats
        teams[away_team]['played'] += 1
        teams[away_team]['goals_for'] += away_goals
        teams[away_team]['goals_against'] += home_goals
        
        # Update win/draw/loss and points
        if home_goals > away_goals:  # Home win
            teams[home_team]['wins'] += 1
            teams[home_team]['points'] += 3
            teams[away_team]['losses'] += 1
        elif home_goals < away_goals:  # Away win
            teams[away_team]['wins'] += 1
            teams[away_team]['points'] += 3
            teams[home_team]['losses'] += 1
        else:  # Draw
            teams[home_team]['draws'] += 1
            teams[home_team]['points'] += 1
            teams[away_team]['draws'] += 1
            teams[away_team]['points'] += 1
    
    # PK-35 special handling: started with -2 points
    if "PK-35" in teams:
        debug_print("Handling PK-35 with -2 point start")
        teams["PK-35"]['points'] -= 2
    
    # Convert to DataFrame
    table_df = pd.DataFrame.from_dict(teams, orient='index')
    table_df['goal_difference'] = table_df['goals_for'] - table_df['goals_against']
    table_df = table_df.sort_values(by=['points', 'goal_difference', 'goals_for'], 
                                   ascending=[False, False, False])
    table_df = table_df.reset_index().rename(columns={'index': 'team'})
    
    return table_df

def analyze_match_days(df):
    """Analyze match days to identify patterns and optimal scheduling"""
    # Add parsed datetime and extract day of week
    df['match_datetime'] = df.apply(lambda x: parse_datetime(x['Pvm'], x['Aika']), axis=1)
    df['day_of_week'] = df['match_datetime'].apply(lambda x: x.strftime('%A') if pd.notnull(x) else None)
    df['month'] = df['match_datetime'].apply(lambda x: x.strftime('%B') if pd.notnull(x) else None)
    df['hour'] = df['match_datetime'].apply(lambda x: x.hour if pd.notnull(x) else None)
    
    # Calculate attendance metrics by day of week and time of day
    day_attendance = df.groupby('day_of_week')['Yleisö'].agg(['mean', 'count', 'sum']).reset_index()
    day_attendance = day_attendance.sort_values('mean', ascending=False)
    
    # Hour analysis (time of day impact)
    hour_attendance = df.groupby('hour')['Yleisö'].agg(['mean', 'count', 'sum']).reset_index()
    
    # Month analysis
    month_attendance = df.groupby('month')['Yleisö'].agg(['mean', 'count', 'sum']).reset_index()
    
    # Weather impact if available
    if 'Weather' in df.columns:
        weather_attendance = df.groupby('Weather')['Yleisö'].agg(['mean', 'count']).reset_index()
    else:
        weather_attendance = None
    
    return {
        'day_attendance': day_attendance,
        'hour_attendance': hour_attendance,
        'month_attendance': month_attendance,
        'weather_attendance': weather_attendance
    }

def analyze_venue_performance(df):
    """Analyze performance at different venues"""
    # Create stats for each venue
    venues = {}
    
    for _, match in df.iterrows():
        if pd.isna(match['Tulos']):
            continue
            
        venue = match['Stadion'] if 'Stadion' in df.columns else match['Koti'] + " home"
        home_goals, away_goals = parse_score(match['Tulos'])
        
        if home_goals is None or venue is None:
            continue
            
        if venue not in venues:
            venues[venue] = {
                'matches': 0,
                'home_wins': 0,
                'draws': 0,
                'away_wins': 0,
                'total_goals': 0,
                'home_goals': 0,
                'away_goals': 0,
                'avg_attendance': 0,
                'total_attendance': 0
            }
        
        venues[venue]['matches'] += 1
        venues[venue]['total_goals'] += (home_goals + away_goals)
        venues[venue]['home_goals'] += home_goals
        venues[venue]['away_goals'] += away_goals
        
        if home_goals > away_goals:
            venues[venue]['home_wins'] += 1
        elif home_goals < away_goals:
            venues[venue]['away_wins'] += 1
        else:
            venues[venue]['draws'] += 1
            
        if 'Yleisö' in df.columns and not pd.isna(match['Yleisö']):
            try:
                attendance = int(str(match['Yleisö']).replace(" ", ""))
                venues[venue]['total_attendance'] += attendance
            except:
                pass
    
    # Calculate averages
    for venue in venues:
        if venues[venue]['matches'] > 0:
            venues[venue]['avg_goals_per_match'] = venues[venue]['total_goals'] / venues[venue]['matches']
            venues[venue]['avg_attendance'] = venues[venue]['total_attendance'] / venues[venue]['matches'] \
                if venues[venue]['total_attendance'] > 0 else 0
    
    return pd.DataFrame.from_dict(venues, orient='index').reset_index().rename(columns={'index': 'venue'})

def create_visualizations(df, league_table, match_days_analysis, venue_analysis):
    """Create visualizations for the analysis results"""
    # 1. League standings
    plt.figure(figsize=(12, 8))
    ax = sns.barplot(x='team', y='points', data=league_table)
    plt.title('Ykkösliiga Standings', fontsize=16)
    plt.xlabel('Team', fontsize=12)
    plt.ylabel('Points', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    # Add value labels on bars
    for p in ax.patches:
        ax.annotate(f'{int(p.get_height())}',
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='center', fontsize=11, color='black',
                    xytext=(0, 5), textcoords='offset points')
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/standings.png", dpi=300)
    
    # 2. Attendance by day of week
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(x='day_of_week', y='mean', data=match_days_analysis['day_attendance'])
    plt.title('Average Attendance by Day of Week', fontsize=16)
    plt.xlabel('Day of Week', fontsize=12)
    plt.ylabel('Average Attendance', fontsize=12)
    
    for p in ax.patches:
        ax.annotate(f'{int(p.get_height())}',
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='center', fontsize=11, color='black',
                    xytext=(0, 5), textcoords='offset points')
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/attendance_by_day.png", dpi=300)
    
    # 3. Attendance by hour
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(x='hour', y='mean', data=match_days_analysis['hour_attendance'])
    plt.title('Average Attendance by Kickoff Hour', fontsize=16)
    plt.xlabel('Hour of Day', fontsize=12)
    plt.ylabel('Average Attendance', fontsize=12)
    
    for p in ax.patches:
        ax.annotate(f'{int(p.get_height())}',
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='center', fontsize=11, color='black',
                    xytext=(0, 5), textcoords='offset points')
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/attendance_by_hour.png", dpi=300)
    
    # 4. Goals per match by venue (top 10)
    top_venues = venue_analysis.sort_values('avg_goals_per_match', ascending=False).head(10)
    plt.figure(figsize=(12, 8))
    ax = sns.barplot(x='venue', y='avg_goals_per_match', data=top_venues)
    plt.title('Average Goals per Match by Venue (Top 10)', fontsize=16)
    plt.xlabel('Venue', fontsize=12)
    plt.ylabel('Average Goals', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    
    for p in ax.patches:
        ax.annotate(f'{p.get_height():.2f}',
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='center', fontsize=11, color='black',
                    xytext=(0, 5), textcoords='offset points')
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/goals_by_venue.png", dpi=300)
    
    # 5. Match distribution heatmap
    # Create date-based dataframe
    df_with_dates = df[~df['match_datetime'].isna()].copy()
    df_with_dates['date'] = df_with_dates['match_datetime'].dt.date
    df_with_dates['day'] = df_with_dates['match_datetime'].dt.day_name()
    df_with_dates['month_name'] = df_with_dates['match_datetime'].dt.month_name()
    
    match_counts = df_with_dates.groupby(['day', 'month_name']).size().reset_index(name='count')
    match_counts_pivot = match_counts.pivot(index='day', columns='month_name', values='count').fillna(0)
    
    # Ensure correct month and day order
    month_order = [calendar.month_name[i] for i in range(1, 13)]
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Filter to months actually in the data
    month_order = [m for m in month_order if m in match_counts['month_name'].unique()]
    
    match_counts_pivot = match_counts_pivot.reindex(index=day_order, columns=month_order)
    
    plt.figure(figsize=(14, 8))
    ax = sns.heatmap(match_counts_pivot, cmap='YlGnBu', annot=True, fmt='g', cbar_kws={'label': 'Number of Matches'})
    plt.title('Match Distribution by Day and Month', fontsize=16)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/match_distribution_heatmap.png", dpi=300)
    
    # 6. Create interactive attendance trends with Plotly
    df_with_dates = df[~df['match_datetime'].isna()].copy()
    if 'Yleisö' in df.columns:
        # Convert attendance to numeric
        df_with_dates['attendance'] = pd.to_numeric(df_with_dates['Yleisö'].astype(str).str.replace(' ', ''), errors='coerce')
        
        # Daily average attendance
        daily_attendance = df_with_dates.groupby(df_with_dates['match_datetime'].dt.date)['attendance'].mean().reset_index()
        daily_attendance.columns = ['date', 'avg_attendance']
        daily_attendance = daily_attendance.sort_values('date')
        
        fig = px.line(daily_attendance, x='date', y='avg_attendance', 
                    title='Average Attendance Trend Over Time',
                    labels={'date': 'Match Date', 'avg_attendance': 'Average Attendance'})
        
        fig.update_layout(
            xaxis_title='Match Date',
            yaxis_title='Average Attendance',
            template='plotly_white',
            hovermode='x unified'
        )
        
        fig.write_html(f"{OUTPUT_DIR}/attendance_trend.html")

def optimize_match_days(df, match_days_analysis):
    """Provide optimization recommendations for future match scheduling"""
    best_days = match_days_analysis['day_attendance'].sort_values('mean', ascending=False)['day_of_week'].tolist()
    best_hours = match_days_analysis['hour_attendance'].sort_values('mean', ascending=False)['hour'].tolist()
    
    # Create month order for proper sorting
    month_order = {calendar.month_name[i]: i for i in range(1, 13)}
    
    # Sort months by attendance
    best_months = match_days_analysis['month_attendance'].copy()
    best_months['month_num'] = best_months['month'].apply(lambda x: month_order.get(x, 0))
    best_months = best_months.sort_values('mean', ascending=False)['month'].tolist()
    
    # Create a recommendations DataFrame with specific time slots
    recommendations = []
    
    # Add top 3 day-time combinations
    for day in best_days[:3]:
        for hour in best_hours[:2]:
            score = 100 - (best_days.index(day) * 10) - (best_hours.index(hour) * 5)
            recommendations.append({
                'day': day,
                'hour': hour,
                'priority': 'High' if score > 85 else 'Medium',
                'score': score,
                'notes': f"Optimal time slot based on historical attendance data"
            })
    
    # Add recommendations for avoiding certain times
    worst_days = match_days_analysis['day_attendance'].sort_values('mean')['day_of_week'].tolist()[:2]
    worst_hours = match_days_analysis['hour_attendance'].sort_values('mean')['hour'].tolist()[:2]
    
    for day in worst_days:
        for hour in worst_hours:
            score = 30 - (5 - worst_days.index(day) * 10) - (5 - worst_hours.index(hour) * 5)
            recommendations.append({
                'day': day,
                'hour': hour,
                'priority': 'Low',
                'score': max(score, 0),
                'notes': "Avoid this time slot due to historically low attendance"
            })
    
    # Create a proper DataFrame
    recommendations_df = pd.DataFrame(recommendations)
    recommendations_df = recommendations_df.sort_values('score', ascending=False)
    
    return recommendations_df

def main():
    print("Ykkösliiga Match Analysis Tool")
    print("=" * 40)
    
    # Load data
    data_file = "matches.csv"  # Default filename, update as needed
    df = load_data(data_file)
    
    if df is None:
        print("Failed to load data. Exiting.")
        return
        
    print(f"Loaded {len(df)} matches from {data_file}")
    
    # Calculate league table
    league_table = calculate_league_table(df)
    print("\nCurrent Ykkösliiga Standings:")
    print(league_table[['team', 'played', 'wins', 'draws', 'losses', 'points']].to_string(index=False))
    
    # Match days analysis
    match_days_analysis = analyze_match_days(df)
    
    # Venue performance analysis
    venue_analysis = analyze_venue_performance(df)
    
    # Generate visualizations
    create_visualizations(df, league_table, match_days_analysis, venue_analysis)
    
    # Generate optimization recommendations
    recommendations = optimize_match_days(df, match_days_analysis)
    
    print("\nTop Match Day Recommendations:")
    print(recommendations[['day', 'hour', 'priority', 'score']].head(5).to_string(index=False))
    
    # Save key results to CSV
    league_table.to_csv(f"{OUTPUT_DIR}/league_table.csv", index=False)
    recommendations.to_csv(f"{OUTPUT_DIR}/scheduling_recommendations.csv", index=False)
    
    print(f"\nAnalysis complete. Results saved to {OUTPUT_DIR}/ directory")

if __name__ == "__main__":
    main()
