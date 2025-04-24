import requests
from bs4 import BeautifulSoup
import re
import datetime
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


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
    """Hakee sarjataulukon oikeasta osoitteesta ilman JS:ää"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'spl-table'})
        teams = []
        for row in table.find_all('tr', {'class': 'spl-row'}):
            cols = row.find_all('td')
            if len(cols) >= 3:
                position = cols[0].text.strip()
                name = cols[1].text.strip()
                try:
                    pos_int = int(position)
                except ValueError:
                    continue
                teams.append({'position': pos_int, 'name': name, 'source': 'web'})
        return teams
    except Exception as e:
        print(f"Virhe sarjataulukossa: {e}")
        return []


def fetch_player_stats():
    """Hakee pelaajatilastot oikeasta osoitteesta JS:n jälkeen Seleniumilla"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points"
    driver = None
    try:
        driver = setup_driver()
        driver.get(url)
        # Odota taulukon latautumista (puuttuvat sulkeet korjattu)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'spl-table'))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'spl-table'})
        players = []
        for row in table.find_all('tr', {'class': 'spl-row'}):
            cols = row.find_all('td')
            if len(cols) >= 5:
                name = cols[0].text.strip()
                team = cols[1].text.strip()
                goals_txt = cols[3].text.strip()
                assists_txt = cols[4].text.strip()
                goals = int(goals_txt) if goals_txt.isdigit() else 0
                assists = int(assists_txt) if assists_txt.isdigit() else 0
                players.append({
                    'name': name,
                    'team': team,
                    'goals': goals,
                    'assists': assists,
                    'source': 'web'
                })
        return players
    except Exception as e:
        print(f"Virhe pelaajatilastoissa: {e}")
        return []
    finally:
        if driver:
            driver.quit()


def parse_predictions(filename):
    """Lue veikkaukset markdown-tiedostosta"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        # Joukkueet listana
        teams = re.findall(r'\d+\.\s+(.*?)\n', content)
        # Pelaajat ja maalimäärät
        players = re.findall(r'-\s+(.*?)\s+\((\d+)\)', content)
        return {
            'teams': [t.strip() for t in teams],
            'players': [{'name': p[0].strip(), 'goals': int(p[1])} for p in players],
            'promotion': teams[0].strip() if len(teams) > 0 else '',
            'playoff': teams[1].strip() if len(teams) > 1 else ''
        }
    except Exception as e:
        print(f"Virhe veikkauksessa: {e}")
        return {'teams': [], 'players': []}


def normalize(text):
    """Normalisoi teksti vertailua varten"""
    return re.sub(r'\W+', '', text.lower())


def calculate_points(actual_table, actual_players, predictions):
    """Laske veikkauspisteet joukkue- ja pelaajaennusteille"""
    points = 0
    breakdown = []
    # Joukkuepisteet: 3p per oikein sijoitettu
    for idx, pred in enumerate(predictions['teams']):
        if idx < len(actual_table):
            actual = actual_table[idx]['name']
            if normalize(actual) == normalize(pred):
                points += 3
                breakdown.append(f"3p: oikea sija {idx+1} ({actual})")
    # Pelaajapisteet: 2p per maali, 1p per syöttö
    for pred_player in predictions['players']:
        for act in actual_players:
            if normalize(pred_player['name']) == normalize(act['name']):
                pts = pred_player['goals'] * 2 + act['assists']
                points += pts
                breakdown.append(f"{pts}p: {act['name']} (maalit {pred_player['goals']}, syötöt {act['assists']})")
    # Nousijapisteet: 5p
    if actual_table and predictions['promotion']:
        if normalize(actual_table[0]['name']) == normalize(predictions['promotion']):
            points += 5
            breakdown.append(f"5p: oikea nousija ({predictions['promotion']})")
    return {'points': points, 'breakdown': breakdown}


def generate_report():
    """Generoi Markdown-raportti veikkauksen tilanteesta"""
    league_table = fetch_league_table()
    player_stats = fetch_player_stats()
    dude_pred = parse_predictions('DudeIslandVeikkaus.md')
    simple_pred = parse_predictions('ykkonen_prediction_2025_simple.md')
    dude_pts = calculate_points(league_table, player_stats, dude_pred)
    simple_pts = calculate_points(league_table, player_stats, simple_pred)

    now = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    report = [
        f"# Veikkausliiga 2025 - Tilanne {now}",
        "",
        "## Pistetilanne",
        f"- DudeIsland: **{dude_pts['points']} pistettä**",
        f"- Simple: **{simple_pts['points']} pistettä**",
        "",
        "## Sarjataulukko",
        "| Sija | Joukkue | Source |",
        "|-----:|---------|--------|"
    ]
    for team in sorted(league_table, key=lambda x: x['position']):
        report.append(f"| {team['position']} | {team['name']} | {team['source']} |")
    report += ["", "## Maalintekijät", "| Pelaaja | Joukkue | Maalit | Syötöt |", "|--------|---------|-------:|------:|"]
    for pl in sorted(player_stats, key=lambda x: x['goals'], reverse=True):
        report.append(f"| {pl['name']} | {pl['team']} | {pl['goals']} | {pl['assists']} |")
    report += ["", "## Pisteiden erittely", "### DudeIsland"]
    report += [f"- {line}" for line in dude_pts['breakdown']]
    report += ["", "### Simple"]
    report += [f"- {line}" for line in simple_pts['breakdown']]

    return "\n".join(report)


if __name__ == '__main__':
    out = generate_report()
    with open('Veikkaustilanne.md', 'w', encoding='utf-8') as f:
        f.write(out)
    print("✅ Veikkaustilanne.md päivitetty!")
