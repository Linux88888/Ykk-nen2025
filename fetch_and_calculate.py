# Scripts/Veikkauslaskuri.py
import requests
from bs4 import BeautifulSoup
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os

def setup_driver():
    """Valmistele ChromeDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        driver = webdriver.Chrome(
            executable_path=ChromeDriverManager().install(),
            options=chrome_options
        )
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver

def fetch_league_table():
    """Hakee sarjataulukon oikeasta osoitteesta"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', {'class': 'spl-table'})
        teams = []
        
        for row in table.find_all('tr', {'class': 'spl-row'}):
            cols = row.find_all('td')
            if len(cols) >= 3:
                position = cols[0].text.strip()
                team = cols[1].text.strip()
                teams.append({
                    'position': int(position),
                    'name': team,
                    'source': 'web'
                })
        return teams
        
    except Exception as e:
        print(f"Virhe sarjataulukossa: {str(e)}")
        return []

def fetch_player_stats():
    """Hakee pelaajatilastot oikeasta osoitteesta"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points"
    try:
        driver = setup_driver()
        driver.get(url)
        
        # Odota JavaScriptin latautumista
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'spl-table'))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'spl-table'})
        players = []
        
        for row in table.find_all('tr', {'class': 'spl-row'}):
            cols = row.find_all('td')
            if len(cols) >= 5:
                name = cols[0].text.strip()
                team = cols[1].text.strip()
                goals = int(cols[3].text.strip()) if cols[3].text.strip().isdigit() else 0
                assists = int(cols[4].text.strip()) if cols[4].text.strip().isdigit() else 0
                
                players.append({
                    'name': name,
                    'team': team,
                    'goals': goals,
                    'assists': assists,
                    'source': 'web'
                })
        return players
        
    except Exception as e:
        print(f"Virhe pelaajatilastoissa: {str(e)}")
        return []
    finally:
        driver.quit()

def parse_predictions(filename):
    """Lue veikkaus tiedostosta"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Etsi joukkueet
        teams = re.findall(r'\d+\.\s+(\S.*?)\n', content)
        
        # Etsi pelaajat ja maalimäärät
        players = re.findall(r'-\s+(.*?)\s+\((\d+)\)', content)
        
        return {
            "teams": [t.strip() for t in teams],
            "players": [{"name": p[0].strip(), "goals": int(p[1])} for p in players],
            "promotion": teams[0] if teams else "",
            "playoff": teams[1] if len(teams) > 1 else ""
        }
    except Exception as e:
        print(f"Virhe veikkauksessa: {str(e)}")
        return {"teams": [], "players": []}

def normalize(text):
    """Normalisoi nimet vertailua varten"""
    return re.sub(r'\W+', '', text.lower())

def calculate_points(actual_table, actual_players, predictions):
    """Laske pisteet"""
    points = 0
    breakdown = []
    
    # Joukkuepisteet (3p/oikea sija)
    for idx, pred_team in enumerate(predictions['teams']):
        if idx < len(actual_table):
            actual_team = actual_table[idx]['name']
            if normalize(actual_team) == normalize(pred_team):
                points += 3
                breakdown.append(f"3p: Oikea sija {idx+1} ({actual_team})")
    
    # Pelaajapisteet (2p/maali, 1p/syöttö)
    for pred_player in predictions['players']:
        for actual_player in actual_players:
            if normalize(pred_player['name']) == normalize(actual_player['name']):
                points += pred_player['goals'] * 2
                points += actual_player['assists']
                breakdown.append(
                    f"2p x {pred_player['goals']} + {actual_player['assists']}p: "
                    f"{actual_player['name']}"
                )
    
    # Nousijapisteet (5p)
    if actual_table and predictions['promotion']:
        if normalize(actual_table[0]['name']) == normalize(predictions['promotion']):
            points += 5
            breakdown.append(f"5p: Oikea nousija ({predictions['promotion']})")
    
    return {'points': points, 'breakdown': breakdown}

def generate_report():
    """Generoi raportin"""
    # Hae data
    league_table = fetch_league_table()
    player_stats = fetch_player_stats()
    
    # Lue veikkaukset
    dude_pred = parse_predictions("DudeIslandVeikkaus")
    simple_pred = parse_predictions("ykkonen_prediction_2025_simple.md")
    
    # Laske pisteet
    dude_points = calculate_points(league_table, player_stats, dude_pred)
    simple_points = calculate_points(league_table, player_stats, simple_pred)
    
    # Luo raportti
    report = f"# Veikkausliiga 2025 - Tilanne {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    
    # Pistetilanne
    report += "## Pistetilanne\n"
    report += f"- DudeIsland: **{dude_points['points']} pistettä**\n"
    report += f"- Simple: **{simple_points['points']} pistettä**\n\n"
    
    # Sarjataulukko
    report += "## Sarjataulukko\n"
    report += "| Sija | Joukkue |\n|------|--------|\n"
    for team in sorted(league_table, key=lambda x: x['position'])[:10]:
        report += f"| {team['position']} | {team['name']} |\n"
    
    # Pelaajatilastot
    report += "\n## Maalintekijät\n"
    report += "| Pelaaja | Joukkue | Maalit | Syötöt |\n|--------|---------|--------|--------|\n"
    for player in sorted(player_stats, key=lambda x: x['goals'], reverse=True)[:10]:
        report += f"| {player['name']} | {player['team']} | {player['goals']} | {player['assists']} |\n"
    
    # Pisteiden erittelyt
    report += "\n## Pisteiden erittely\n"
    report += "### DudeIsland\n"
    for line in dude_points['breakdown'][:5]:
        report += f"- {line}\n"
    report += "\n### Simple\n"
    for line in simple_points['breakdown'][:5]:
        report += f"- {line}\n"
    
    return report

if __name__ == "__main__":
    with open("Veikkaustilanne.md", "w", encoding="utf-8") as f:
        f.write(generate_report())
