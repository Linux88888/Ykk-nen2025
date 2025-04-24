import requests
from bs4 import BeautifulSoup
import os
import re
import datetime

def fetch_league_table():
    """Fetch the current league table data."""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    table_data = []
    # Find the league table in the HTML
    table = soup.find('table', {'class': 'table'})
    if table:
        rows = table.find_all('tr')
        # Skip header row
        for row in rows[1:]:
            cols = row.find_all('td')
            if cols:
                position = len(table_data) + 1
                team_element = cols[1].find('a')
                if team_element:
                    team_name = team_element.text.strip()
                    table_data.append({"position": position, "name": team_name})
    
    return table_data

def fetch_player_statistics():
    """Fetch player statistics (goals and assists)."""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    player_stats = []
    # Find the statistics table
    table = soup.find('table', {'class': 'statistics'})
    if table:
        rows = table.find_all('tr')
        # Skip header row
        for row in rows[1:]:
            cols = row.find_all('td')
            if cols and len(cols) >= 5:
                player_name = cols[0].text.strip()
                team_name = cols[1].text.strip()
                goals = int(cols[3].text.strip() or 0)  # Column 'm' for goals
                assists = int(cols[4].text.strip() or 0)  # Column 's' for assists
                
                player_stats.append({
                    "name": player_name,
                    "team": team_name,
                    "goals": goals,
                    "assists": assists
                })
    
    return player_stats

def parse_dude_island_predictions():
    """Parse predictions from DudeIslandVeikkaus file."""
    with open("DudeIslandVeikkaus", 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Parse goal scorers
    goals_section = re.search(r'### Maalintekijät:(.*?)##', content, re.DOTALL)
    players = []
    if goals_section:
        player_section = goals_section.group(1).strip()
        player_lines = player_section.split('\n')
        for line in player_lines:
            line = line.strip()
            if line and not line.startswith('#'):
                players.append({
                    "name": line,
                    "goals": 0,  # We don't have prediction numbers, just names
                    "assists": 0
                })
    
    # Parse team standings
    teams_section = re.search(r'### Sarjataulukko:(.*?)##', content, re.DOTALL)
    teams = []
    if teams_section:
        teams_section = teams_section.group(1).strip()
        team_lines = teams_section.split('\n')
        for line in team_lines:
            line = line.strip()
            if line and not line.startswith('#'):
                teams.append(line)
    
    # Parse promotion and playoff
    promotion = ""
    playoff = ""
    promo_match = re.search(r'nousija:\s*(.*?)(?:\s*karsija:|$)', content, re.DOTALL)
    if promo_match:
        promotion = promo_match.group(1).strip()
    
    playoff_match = re.search(r'karsija:\s*(.*?)(?:\s*ja|$)', content, re.DOTALL)
    if playoff_match:
        playoff = playoff_match.group(1).strip()
    
    return {
        "teams": teams,
        "players": players,
        "promotion": promotion,
        "playoff": playoff
    }

def parse_simple_predictions():
    """Parse predictions from the simple markdown file."""
    with open("ykkonen_prediction_2025_simple.md", 'r', encoding='utf-8') as file:
        content = file.read()
    
    teams = []
    # Find the league table section
    table_section = re.search(r'Final League Table(.*?)Top 5 Goal Scorers', content, re.DOTALL)
    if table_section:
        table_lines = table_section.group(1).strip().split('\n')
        # Skip the header lines
        for line in table_lines[2:]:
            match = re.search(r'\d+\s+(.*?)$', line.strip())
            if match:
                team_name = match.group(1).strip()
                # Remove the asterisk note if it exists
                team_name = re.sub(r'\*$', '', team_name).strip()
                teams.append(team_name)
    
    # Find the goalscorers section
    players = []
    scorers_section = re.search(r'Top 5 Goal Scorers(.*?)$', content, re.DOTALL)
    if scorers_section:
        scorer_lines = scorers_section.group(1).strip().split('\n')
        for line in scorer_lines:
            line = line.strip()
            if line.startswith('    '):  # Indented items are player lines
                match = re.search(r'(.*?)\((.*?)\)\s*-\s*(\d+)\s*goals', line)
                if match:
                    player_name = match.group(1).strip()
                    team_name = match.group(2).strip()
                    goals = int(match.group(3).strip())
                    players.append({
                        "name": player_name,
                        "team": team_name,
                        "goals": goals,
                        "assists": 0  # No assist predictions provided
                    })
    
    # Parse promotion and playoff
    promotion = ""
    playoff = ""
    promo_match = re.search(r'nousija:\s*(.*?)(?:\s*karsija:|$)', content, re.DOTALL)
    if promo_match:
        promotion = promo_match.group(1).strip()
    
    playoff_match = re.search(r'karsija:\s*(.*?)$', content, re.DOTALL)
    if playoff_match:
        playoff = playoff_match.group(1).strip()
    
    return {
        "teams": teams,
        "players": players,
        "promotion": promotion,
        "playoff": playoff
    }

def calculate_scores(league_table, player_stats, dude_island_predictions, simple_predictions):
    """Calculate scores based on predictions and actual results."""
    dude_island_score = 0
    simple_score = 0
    
    dude_island_points = []
    simple_points = []
    
    # Calculate team position points (3 points per correct position)
    for i, team in enumerate(league_table):
        # Use team name for comparison
        team_name = team["name"]
        position = i + 1
        
        if i < len(dude_island_predictions["teams"]):
            predicted_team = dude_island_predictions["teams"][i]
            if normalized_team_name(team_name) == normalized_team_name(predicted_team):
                dude_island_score += 3
                dude_island_points.append(f"3p: {team_name} on oikeassa sijoituksessa ({position})")
        
        if i < len(simple_predictions["teams"]):
            predicted_team = simple_predictions["teams"][i]
            if normalized_team_name(team_name) == normalized_team_name(predicted_team):
                simple_score += 3
                simple_points.append(f"3p: {team_name} on oikeassa sijoituksessa ({position})")
    
    # Special points for correctly predicting promotion and playoff teams
    if league_table and normalized_team_name(league_table[0]["name"]) == normalized_team_name(dude_island_predictions["promotion"]):
        dude_island_score += 5
        dude_island_points.append(f"5p: Oikea nousijajoukkue ({dude_island_predictions['promotion']})")
    
    if league_table and normalized_team_name(league_table[1]["name"]) == normalized_team_name(dude_island_predictions["playoff"]):
        dude_island_score += 5
        dude_island_points.append(f"5p: Oikea karsijajoukkue ({dude_island_predictions['playoff']})")
    
    if league_table and normalized_team_name(league_table[0]["name"]) == normalized_team_name(simple_predictions["promotion"]):
        simple_score += 5
        simple_points.append(f"5p: Oikea nousijajoukkue ({simple_predictions['promotion']})")
    
    if league_table and normalized_team_name(league_table[1]["name"]) == normalized_team_name(simple_predictions["playoff"]):
        simple_score += 5
        simple_points.append(f"5p: Oikea karsijajoukkue ({simple_predictions['playoff']})")
    
    # Calculate player stats points (2 points per goal, 1 point per assist)
    for player in player_stats:
        # For DudeIsland predictions (only checks if the player was predicted at all)
        for pred in dude_island_predictions["players"]:
            if normalized_player_name(pred["name"]) == normalized_player_name(player["name"]):
                if player["goals"] > 0:
                    dude_island_score += 2 * player["goals"]
                    dude_island_points.append(f"2p x {player['goals']}: {player['name']} maalit ({player['goals']})")
                if player["assists"] > 0:
                    dude_island_score += player["assists"]
                    dude_island_points.append(f"1p x {player['assists']}: {player['name']} syötöt ({player['assists']})")
        
        # For simple predictions (checks actual goal counts)
        for pred in simple_predictions["players"]:
            if normalized_player_name(pred["name"]) == normalized_player_name(player["name"]):
                # 2 points per goal up to the predicted amount
                goal_points = 2 * min(pred["goals"], player["goals"])
                if goal_points > 0:
                    simple_score += goal_points
                    simple_points.append(f"2p x {min(pred['goals'], player['goals'])}: {player['name']} maalit ({player['goals']} / {pred['goals']})")
                
                # 1 point per assist
                if player["assists"] > 0:
                    simple_score += player["assists"]
                    simple_points.append(f"1p x {player['assists']}: {player['name']} syötöt ({player['assists']})")
    
    return {
        "dude_island": {
            "score": dude_island_score,
            "points_breakdown": dude_island_points
        },
        "simple": {
            "score": simple_score,
            "points_breakdown": simple_points
        }
    }

def normalized_team_name(name):
    """Normalize team name for comparison by removing FC, etc."""
    name = name.lower().strip()
    name = re.sub(r'^fc\s+', '', name)  # Remove leading "FC "
    return name

def normalized_player_name(name):
    """Normalize player name for comparison."""
    name = name.lower().strip()
    # Reverse "Lastname, Firstname" to "Firstname Lastname"
    if ',' in name:
        parts = name.split(',')
        name = f"{parts[1].strip()} {parts[0].strip()}"
    return name

def generate_markdown_report(league_table, player_stats, scores):
    """Generate a markdown report with current standings and scores."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = f"# Veikkaustilanne\n\n"
    md += f"Päivitetty: {now}\n\n"
    md += f"## Pisteet\n\n"
    md += f"- DudeIsland: {scores['dude_island']['score']} pistettä\n"
    md += f"- Simple: {scores['simple']['score']} pistettä\n\n"
    
    md += f"## Pisteiden erittely\n\n"
    md += f"### DudeIsland\n\n"
    if scores['dude_island']['points_breakdown']:
        for point in scores['dude_island']['points_breakdown']:
            md += f"- {point}\n"
    else:
        md += f"Ei pisteitä vielä\n"
    
    md += f"\n### Simple\n\n"
    if scores['simple']['points_breakdown']:
        for point in scores['simple']['points_breakdown']:
            md += f"- {point}\n"
    else:
        md += f"Ei pisteitä vielä\n"
    
    md += f"\n## Nykyinen sarjataulukko\n\n"
    md += f"| Sija | Joukkue |\n"
    md += f"|------|--------|\n"
    for team in league_table:
        md += f"| {team['position']} | {team['name']} |\n"
    
    md += f"\n## Pelaajatilastot (TOP 10)\n\n"
    md += f"| Pelaaja | Joukkue | Maalit | Syötöt | Pisteet |\n"
    md += f"|---------|---------|--------|--------|--------|\n"
    
    # Sort players by goals + assists and take top 10
    sorted_players = sorted(player_stats, key=lambda x: (x['goals'] + x['assists']), reverse=True)[:10]
    for player in sorted_players:
        md += f"| {player['name']} | {player['team']} | {player['goals']} | {player['assists']} | {player['goals'] + player['assists']} |\n"
    
    return md

def main():
    """Main function to run the data fetching and processing."""
    try:
        # Fetch current data
        print("Fetching league table...")
        league_table = fetch_league_table()
        print(f"Found {len(league_table)} teams in the league table")
        
        print("Fetching player statistics...")
        player_stats = fetch_player_statistics()
        print(f"Found {len(player_stats)} players with statistics")
        
        # Parse prediction files
        print("Parsing prediction files...")
        dude_island_predictions = parse_dude_island_predictions()
        print(f"Parsed DudeIsland predictions: {len(dude_island_predictions['teams'])} teams, {len(dude_island_predictions['players'])} players")
        
        simple_predictions = parse_simple_predictions()
        print(f"Parsed Simple predictions: {len(simple_predictions['teams'])} teams, {len(simple_predictions['players'])} players")
        
        # Calculate scores
        print("Calculating scores...")
        scores = calculate_scores(league_table, player_stats, dude_island_predictions, simple_predictions)
        
        # Generate markdown report
        print("Generating report...")
        report = generate_markdown_report(league_table, player_stats, scores)
        
        # Write to file
        with open("Veikkaustilanne.md", "w", encoding="utf-8") as f:
            f.write(report)
        
        print("Done! Report saved to Veikkaustilanne.md")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
