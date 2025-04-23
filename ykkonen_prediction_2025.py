import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# Ykkönen 2025 Season Prediction

This repository contains prediction models and analysis for the Finnish Ykkönen (second tier) football league for the 2025 season.

## Current Status

Last updated: **April 23, 2025 11:16:04 UTC** by [Linux88888a](https://github.com/Linux88888a)

The 2025 Ykkönen season has just begun with some teams having played their first matches. The early leaders are Jippo and TPS, both with 3 points from their opening matches.

## Key League Information

- **Competition Format**: 10 teams, double round-robin (18 rounds total)
- **Points Deduction**: PK-35 starts the season with a 2-point deduction per License Committee decision
- **Promotion**: 1st place directly promoted to Veikkausliiga, 2nd place enters promotion playoff
- **Relegation**: 9th and 10th places relegated to Kakkonen (third tier)

## Current Standings (April 23, 2025)

| Pos | Team | MP | W | D | L | GF | GA | GD | Pts |
|-----|------|----|----|----|----|----|----|----|----|
| 1 | Jippo | 1 | 1 | 0 | 0 | 2 | 0 | 2 | 3 |
| 2 | TPS | 1 | 1 | 0 | 0 | 4 | 3 | 1 | 3 |
| 3 | EIF | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | KäPa | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | FC Lahti | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | JäPS | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | HJK Klubi 04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | SJK Akatemia | 1 | 0 | 0 | 1 | 3 | 4 | -1 | 0 |
| 9 | SalPa | 1 | 0 | 0 | 1 | 0 | 2 | -2 | 0 |
| 10 | PK-35 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2 |

## Teams for 2025 Season

1. **Jippo** - Based in Joensuu, strong start to the season with a 2-0 win over SalPa
2. **TPS** - Traditional powerhouse from Turku, won 4-3 against SJK Akatemia showing attacking quality
3. **EIF** - From Ekenäs (Tammisaari), yet to play their first match
4. **KäPa** - Helsinki-based club with solid grassroots development
5. **FC Lahti** - Recently relegated from Veikkausliiga, bringing top-tier experience
6. **PK-35** - Helsinki club, starting with a 2-point deduction due to License Committee decision
7. **JäPS** - From Järvenpää, north of Helsinki
8. **HJK Klubi 04** - Development team of Finnish giants HJK
9. **SJK Akatemia** - Academy team of SJK from Seinäjoki, lost 4-3 to TPS showing offensive capabilities
10. **SalPa** - From Salo, lost 2-0 to Jippo in their opening match

## Repository Contents

- **ykkonen_prediction_2025.py**: Python script that generates predictions
- **ykkonen_2025_current.csv**: Current league standings (as of April 23, 2025)
- **ykkonen_2025_prediction.csv**: End-of-season prediction
- **ykkonen_2025_odds.csv**: Promotion and relegation probabilities
- **ykkonen_2025_upcoming.csv**: Upcoming fixture predictions
- **ykkonen_2025_schedule.csv**: Complete schedule for all 18 rounds

## Prediction Model

The prediction uses a statistical model that considers:

- Actual results from the early matches of the 2025 season
- PK-35's 2-point deduction
- Team strength ratings based on squad quality and historical performance
- Home advantage factors
- Form/momentum indicators
- Poisson distribution for realistic score modeling

## How to Use

1. Run the prediction script:
```bash
python ykkonen_prediction_2025.py
# Current date information (exactly as provided by user)
CURRENT_DATETIME = "2025-04-23 11:16:04"
USER = "Linux88888a"

def create_ykkonen_prediction():
    """
    Create a prediction for the Finnish Ykkönen 2025 season
    Based on actual teams and current standings
    """
    # Actual teams for Ykkönen 2025
    teams = [
        "Jippo", "TPS", "EIF", "KäPa", "FC Lahti", 
        "PK-35", "JäPS", "HJK Klubi 04", "SJK Akatemia", "SalPa"
    ]
    
    # Create table with current standings
    table = pd.DataFrame({
        'Team': teams,
        'MP': [1, 1, 0, 0, 0, 0, 0, 0, 1, 1], # Matches played
        'W': [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],  # Wins
        'D': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # Draws
        'L': [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],  # Losses
        'GF': [2, 4, 0, 0, 0, 0, 0, 0, 3, 0], # Goals for
        'GA': [0, 3, 0, 0, 0, 0, 0, 0, 4, 2], # Goals against
        'GD': [2, 1, 0, 0, 0, 0, 0, 0, -1, -2], # Goal difference
        'Pts': [3, 3, 0, 0, 0, 0, 0, 0, 0, 0]  # Points
    })
    
    # Apply PK-35's 2-point deduction
    table.loc[table['Team'] == "PK-35", 'Pts'] = -2
    
    # Sort by current standings (points, then goal difference)
    table = table.sort_values(['Pts', 'GD', 'GF'], ascending=[False, False, False])
    
    # Team strength ratings based on history, squad quality, and current form
    team_strength = {
        "Jippo": 75,         # Strong start with clean sheet win
        "TPS": 78,           # Traditional strong team with attacking prowess
        "EIF": 70,           # Mid-table team with some inconsistency
        "KäPa": 72,          # Helsinki club with decent resources
        "FC Lahti": 76,      # Recently from Veikkausliiga, strong squad
        "PK-35": 67,         # Starting with negative points suggests challenges
        "JäPS": 69,          # Mid-to-lower table expectations
        "HJK Klubi 04": 68,  # HJK's development team, young talent but inconsistent
        "SJK Akatemia": 71,  # Academy team but scored 3 in first match
        "SalPa": 65,         # Struggling in early matches
    }
    
    # Home advantage factor (additional points added to home team strength)
    home_advantage = {
        "Jippo": 5,         # Good home support 
        "TPS": 6,           # Strong home advantage at Veritas Stadium
        "EIF": 4,           # Moderate home advantage
        "KäPa": 4,          # Moderate home advantage in Helsinki
        "FC Lahti": 5,      # Good home support at Lahti Stadium
        "PK-35": 4,         # Standard home advantage
        "JäPS": 4,          # Standard home advantage
        "HJK Klubi 04": 3,  # Smaller home advantage as a reserve team
        "SJK Akatemia": 3,  # Smaller home advantage as an academy team
        "SalPa": 4,         # Standard home advantage
    }
    
    # Form factor based on recent performances
    form_factor = {
        "Jippo": 1.05,         # Boosted by strong start
        "TPS": 1.04,           # Good attacking form despite conceding
        "EIF": 1.00,           # No matches yet to gauge form
        "KäPa": 1.00,          # No matches yet to gauge form
        "FC Lahti": 1.00,      # No matches yet to gauge form
        "PK-35": 0.97,         # Slightly negative due to points deduction
        "JäPS": 1.00,          # No matches yet to gauge form
        "HJK Klubi 04": 1.00,  # No matches yet to gauge form
        "SJK Akatemia": 0.98,  # Lost but showed attacking potential
        "SalPa": 0.96,         # Poor start with no goals scored
    }
    
    # Matches already played
    played_matches = [
        ["Jippo", "SalPa", 2, 0],
        ["TPS", "SJK Akatemia", 4, 3]
    ]
    
    # Create a copy for current standings display
    current_table = table.copy()
    
    # Generate full fixture list for a double round-robin tournament (18 rounds)
    fixtures = []
    for home_team in teams:
        for away_team in teams:
            if home_team != away_team:
                # First round (home and away)
                fixtures.append([home_team, away_team])
    
    # Remove fixtures that have already been played
    for match in played_matches:
        home_team, away_team = match[0], match[1]
        if [home_team, away_team] in fixtures:
            fixtures.remove([home_team, away_team])
    
    # Simulate remaining matches
    for home_team, away_team in fixtures:
        # Calculate match outcome based on team strength, home advantage, and form
        home_strength = team_strength[home_team] * form_factor[home_team] + home_advantage[home_team]
        away_strength = team_strength[away_team] * form_factor[away_team]
        
        # Calculate expected goals using Poisson-like model with randomization
        home_xg = home_strength / 10 * (1 + np.random.normal(0, 0.15))
        away_xg = away_strength / 12 * (1 + np.random.normal(0, 0.15))
        
        # Convert to actual goals (rounded to integers)
        home_goals = max(0, int(np.random.poisson(home_xg)))
        away_goals = max(0, int(np.random.poisson(away_xg)))
        
        # Update match played
        table.loc[table['Team'] == home_team, 'MP'] += 1
        table.loc[table['Team'] == away_team, 'MP'] += 1
        
        # Update goals
        table.loc[table['Team'] == home_team, 'GF'] += home_goals
        table.loc[table['Team'] == home_team, 'GA'] += away_goals
        table.loc[table['Team'] == away_team, 'GF'] += away_goals
        table.loc[table['Team'] == away_team, 'GA'] += home_goals
        
        # Update results
        if home_goals > away_goals:
            # Home win
            table.loc[table['Team'] == home_team, 'W'] += 1
            table.loc[table['Team'] == home_team, 'Pts'] += 3
            table.loc[table['Team'] == away_team, 'L'] += 1
        elif home_goals < away_goals:
            # Away win
            table.loc[table['Team'] == away_team, 'W'] += 1
            table.loc[table['Team'] == away_team, 'Pts'] += 3
            table.loc[table['Team'] == home_team, 'L'] += 1
        else:
            # Draw
            table.loc[table['Team'] == home_team, 'D'] += 1
            table.loc[table['Team'] == home_team, 'Pts'] += 1
            table.loc[table['Team'] == away_team, 'D'] += 1
            table.loc[table['Team'] == away_team, 'Pts'] += 1
    
    # Update goal differences
    table['GD'] = table['GF'] - table['GA']
    
    # Sort final table
    table = table.sort_values(['Pts', 'GD', 'GF'], ascending=[False, False, False])
    current_table = current_table.sort_values(['Pts', 'GD', 'GF'], ascending=[False, False, False])
    
    # Reset indexes for clean display
    current_table = current_table.reset_index(drop=True)
    current_table.index = current_table.index + 1
    current_table = current_table.reset_index().rename(columns={'index': 'Pos'})
    
    table = table.reset_index(drop=True)
    table.index = table.index + 1
    table = table.reset_index().rename(columns={'index': 'Pos'})
    
    return table, current_table

def calculate_promotion_relegation_odds(prediction_table):
    """
    Calculate promotion and relegation odds based on the prediction table
    """
    teams = prediction_table['Team'].tolist()
    positions = prediction_table['Pos'].tolist()
    
    # Create a dataframe for the odds
    odds = pd.DataFrame({
        'Team': teams,
        'Promotion (%)': 0,
        'Playoff (%)': 0,
        'Mid-table (%)': 0,
        'Relegation (%)': 0
    })
    
    # Run multiple simulations with slight variations
    num_simulations = 1000
    for _ in range(num_simulations):
        # Add random variation to positions
        position_with_noise = {}
        for i, team in enumerate(teams):
            # Add noise to positions (more noise for mid-table teams)
            base_pos = positions[i]
            if 4 <= base_pos <= 7:
                # Mid-table teams can vary more
                noise = np.random.normal(0, 2.0)
            else:
                # Top and bottom teams vary less
                noise = np.random.normal(0, 1.0)
            
            new_pos = max(1, min(10, base_pos + noise))
            position_with_noise[team] = new_pos
        
        # Sort teams by noisy positions
        sorted_teams = sorted(teams, key=lambda x: position_with_noise[x])
        
        # Update odds based on this simulation
        for i, team in enumerate(sorted_teams):
            sim_pos = i + 1
            if sim_pos == 1:
                odds.loc[odds['Team'] == team, 'Promotion (%)'] += 1
            elif sim_pos == 2:
                odds.loc[odds['Team'] == team, 'Playoff (%)'] += 1
            elif 3 <= sim_pos <= 8:
                odds.loc[odds['Team'] == team, 'Mid-table (%)'] += 1
            else:
                odds.loc[odds['Team'] == team, 'Relegation (%)'] += 1
    
    # Convert counts to percentages
    odds['Promotion (%)'] = (odds['Promotion (%)'] / num_simulations * 100).round(1)
    odds['Playoff (%)'] = (odds['Playoff (%)'] / num_simulations * 100).round(1)
    odds['Mid-table (%)'] = (odds['Mid-table (%)'] / num_simulations * 100).round(1)
    odds['Relegation (%)'] = (odds['Relegation (%)'] / num_simulations * 100).round(1)
    
    # Sort by original table positions
    odds['Pos'] = prediction_table['Pos']
    odds = odds.sort_values('Pos')
    odds = odds.reset_index(drop=True)
    odds.index = odds.index + 1
    odds = odds.reset_index().rename(columns={'index': 'Pos'})
    
    return odds

def generate_schedule():
    """
    Generate a complete 18-round schedule for the league
    """
    teams = [
        "Jippo", "TPS", "EIF", "KäPa", "FC Lahti", 
        "PK-35", "JäPS", "HJK Klubi 04", "SJK Akatemia", "SalPa"
    ]
    
    # Matches already played
    played = [
        ["2025-04-16", "Jippo", "SalPa", 2, 0],
        ["2025-04-19", "TPS", "SJK Akatemia", 4, 3]
    ]
    
    # Create schedule - each team plays against every other team home and away
    all_matches = []
    
    # First round (everyone plays everyone once)
    start_date = datetime(2025, 4, 15)
    match_id = 0
    
    for round_num in range(1, 10):  # 9 rounds in first half (each team plays 9 matches)
        round_matches = []
        round_date = start_date + timedelta(days=(round_num-1)*7)  # Weekly rounds
        
        # In each round, 5 matches are played (10 teams / 2)
        for i in range(0, len(teams), 2):
            if i+1 < len(teams):
                home_team = teams[i]
                away_team = teams[i+1]
                
                # Check if already played
                already_played = False
                result = [None, None]
                for p in played:
                    if p[1] == home_team and p[2] == away_team:
                        already_played = True
                        result = [p[3], p[4]]
                
                match_id += 1
                match = {
                    'MatchID': match_id,
                    'Round': round_num,
                    'Date': round_date.strftime('%Y-%m-%d'),
                    'Home': home_team,
                    'Away': away_team,
                    'Played': already_played
                }
                
                if already_played:
                    match['HomeGoals'] = result[0]
                    match['AwayGoals'] = result[1]
                    match['Result'] = f"{result[0]}-{result[1]}"
                
                round_matches.append(match)
        
        # Rotate teams for next round except first team
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
        
        all_matches.extend(round_matches)
    
    # Second round (reverse fixtures)
    start_date = datetime(2025, 7, 1)  # Second half starts in July
    
    for match in all_matches[:45]:  # First 45 matches (9 rounds * 5 matches)
        match_id += 1
        second_round = {
            'MatchID': match_id,
            'Round': match['Round'] + 9,
            'Date': (datetime.strptime(match['Date'], '%Y-%m-%d') + timedelta(days=90)).strftime('%Y-%m-%d'),
            'Home': match['Away'],  # Reverse home/away
            'Away': match['Home'],
            'Played': False
        }
        all_matches.append(second_round)
    
    # Convert to DataFrame
    schedule_df = pd.DataFrame(all_matches)
    
    # Sort by round and matchID
    schedule_df = schedule_df.sort_values(['Round', 'MatchID'])
    
    return schedule_df

def generate_upcoming_matches(schedule):
    """
    Generate upcoming matches based on the schedule
    """
    # Get current date
    current_date = pd.to_datetime(CURRENT_DATETIME.split()[0])
    
    # Filter upcoming matches (not played and scheduled after current date)
    upcoming = schedule[
        (~schedule['Played']) & 
        (pd.to_datetime(schedule['Date']) >= current_date)
    ].copy()
    
    # Sort by date
    upcoming = upcoming.sort_values('Date')
    
    # Take next 6 matches (approximately one matchday)
    upcoming = upcoming.head(6)
    
    # Format for display
    upcoming['FormattedDate'] = pd.to_datetime(upcoming['Date']).dt.strftime('%d.%m.%Y')
    
    # Add predictions based on teams
    team_strength = {
        "Jippo": 75, "TPS": 78, "EIF": 70, "KäPa": 72, "FC Lahti": 76,
        "PK-35": 67, "JäPS": 69, "HJK Klubi 04": 68, "SJK Akatemia": 71, "SalPa": 65
    }
    
    # Simple prediction function
    def predict_score(home, away):
        home_str = team_strength[home]
        away_str = team_strength[away]
        
        # Basic prediction
        if home_str > away_str + 5:
            return "2-0"
        elif home_str > away_str:
            return "2-1" 
        elif abs(home_str - away_str) <= 5:
            return "1-1"
        else:
            return "0-1"
    
    upcoming['Prediction'] = upcoming.apply(lambda x: predict_score(x['Home'], x['Away']), axis=1)
    
    return upcoming

# Set random seed for reproducibility
np.random.seed(42)

# Generate prediction
prediction_table, current_table = create_ykkonen_prediction()

# Calculate odds
odds_table = calculate_promotion_relegation_odds(prediction_table)

# Generate league schedule
schedule = generate_schedule()

# Generate upcoming matches
upcoming_matches = generate_upcoming_matches(schedule)

# Print results
print(f"Ykkönen 2025 - Current Standings as of {CURRENT_DATETIME}")
print("=" * 80)
print(current_table.to_string(index=False))
print("\n")

print(f"Upcoming Matches")
print("=" * 80)
print(upcoming_matches[['Round', 'FormattedDate', 'Home', 'Away', 'Prediction']].to_string(index=False))
print("\n")

print(f"Ykkönen 2025 - End of Season Prediction")
print("=" * 80)
print(prediction_table.to_string(index=False))
print("\n")

print("Promotion and Relegation Probability")
print("=" * 80)
print(odds_table.to_string(index=False))
print("\n")

print("Promotion/Relegation Key:")
print("- 1st: Directly promoted to Veikkausliiga")
print("- 2nd: Promotion playoff")
print("- 9th-10th: Relegated to Kakkonen")
print("\nPrediction by:", USER)

# Save to CSV files
current_table.to_csv('ykkonen_2025_current.csv', index=False)
prediction_table.to_csv('ykkonen_2025_prediction.csv', index=False)
odds_table.to_csv('ykkonen_2025_odds.csv', index=False)
upcoming_matches.to_csv('ykkonen_2025_upcoming.csv', index=False)
schedule.to_csv('ykkonen_2025_schedule.csv', index=False)

if __name__ == "__main__":
    # Script already executed above
    pass
