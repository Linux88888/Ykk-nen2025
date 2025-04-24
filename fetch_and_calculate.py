import requests
from bs4 import BeautifulSoup
import os
import re
import markdown
import html2text
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

def parse_dude_island_predictions(file_path):
    """Parse predictions from DudeIslandVeikkaus file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # This will need to be adapted based on the actual file format
    # For now, assuming a simple format where team predictions are listed
    teams_prediction = []
    player_predictions = []
    
    # Parse logic here (will need to be adjusted based on actual file format)
    
    return {
        "teams": teams_prediction,
        "players": player_predictions
    }

def parse_simple_predictions(file_path):
    """Parse predictions from the simple markdown file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Convert markdown to plain text for easier parsing
    h = html2text.HTML2Text()
    h.ignore_links = False
    text_content = h.handle(markdown.markdown(content))
    
    # This will need to be adapted based on the actual file format
    teams_prediction = []
    player_predictions = []
    
    # Parse logic here (will need to be adjusted based on actual file format)
    
    return {
        "teams": teams_prediction,
        "players": player_predictions
    }

def calculate_scores(league_table, player_stats, dude_island_predictions, simple_predictions):
    """Calculate scores based on predictions and actual results."""
    dude_island_score = 0
    simple_score = 0
    
    # Calculate team position points (3 points per correct position)
    for i, team in enumerate(league_table):
        if i < len(dude_island_predictions["teams"]) and team["name"] == dude_island_predictions["teams"][i]:
            dude_island_score += 3
        
        if i < len(simple_predictions["teams"]) and team["name"] == simple_predictions["teams"][i]:
            simple_score += 3
    
    # Calculate player stats points (2 points per goal, 1 point per assist)
    for player in player_stats:
        # For DudeIsland predictions
        for pred in dude_island_predictions["players"]:
            if pred["name"] == player["name"]:
                dude_island_score += 2 * min(pred["goals"], player["goals"])
                dude_island_score += 1 * min(pred["assists"], player["assists"])
        
        # For simple predictions
        for pred in simple_predictions["players"]:
            if pred["name"] == player["name"]:
                simple_score += 2 * min(pred["goals"], player["goals"])
                simple_score += 1 * min(pred["assists"], player["assists"])
    
    return {
        "dude_island": dude_island_score,
        "simple": simple_score
    }

def generate_markdown_report(league_table, player_stats, scores):
    """Generate a markdown report with current standings and scores."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = f"# Veikkaustilanne\n\n"
    md += f"Päivitetty: {now}\n\n"
    md += f"## Pisteet\n\n"
    md += f"- DudeIsland: {scores['dude_island']} pistettä\n"
    md += f"- Simple: {scores['simple']} pistettä\n\n"
    
    md += f"## Nykyinen sarjataulukko\n\n"
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
    # Paths to prediction files
    dude_island_path = "DudeIslandVeikkaus"
    simple_path = "ykkonen_prediction_2025_simple.md"
    
    # Fetch current data
    print("Fetching league table...")
    league_table = fetch_league_table()
    print("Fetching player statistics...")
    player_stats = fetch_player_statistics()
    
    # Parse prediction files
    print("Parsing prediction files...")
    dude_island_predictions = parse_dude_island_predictions(dude_island_path)
    simple_predictions = parse_simple_predictions(simple_path)
    
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

if __name__ == "__main__":
    main()
