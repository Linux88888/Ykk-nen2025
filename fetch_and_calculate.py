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

# -------------------------------------------------------
# Fetch & Calculate - Veikkausliigan tilastot ja veikkaukset
# -------------------------------------------------------

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
    """Hakee sarjataulukon ilman JS:ää"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'spl-table'})
        if table is None:
            print("⚠️ DEBUG: Sarjataulukkoa ei löytynyt (spl-table)")
            return []

        teams = []
        for row in table.find_all('tr', {'class': 'spl-row'}):
            cols = row.find_all('td')
            if len(cols) >= 3:
                pos_txt = cols[0].text.strip()
                name = cols[1].text.strip()
                try:
                    pos = int(pos_txt)
                except ValueError:
                    continue
                teams.append({'position': pos, 'name': name, 'source': 'web'})
        print(f"INFO: Sarjataulukko: ladattiin {len(teams)} joukkuetta")
        return teams
    except Exception as e:
        print(f"❌ Virhe sarjataulukossa: {e}")
        return []


def fetch_player_stats():
    """Hakee pelaajatilastot JS:n jälkeen Seleniumilla"""
    url = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points"
    driver = None
    try:
        driver = setup_driver()
        driver.get(url)
        # Odota JS-ladatun taulukon elementti
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'spl-table'))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('table', {'class': 'spl-table'})
        if table is None:
            print("⚠️ DEBUG: Pelaajataulukkoa ei löytynyt (spl-table)")
            return []

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
                players.append({'name': name, 'team': team, 'goals': goals, 'assists': assists, 'source': 'web'})
        print(f"INFO: Pelaajatilastot: ladattiin {len(players)} pelaajaa")
        return players
    except Exception as e:
        print(f"❌ Virhe pelaajatilastoissa: {e}")
        return []
    finally:
        if driver:
            driver.quit()


def parse_predictions(filename):
    """Lue veikkaustiedostot ja tarkista olemassaolo"""
    if not os.path.exists(filename):
        print(f"⚠️ DEBUG: Veikkaus-tiedostoa ei löytynyt: {filename}")
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''}
    try:
        content = open(filename, 'r', encoding='utf-8').read()
        teams = re.findall(r'\d+\.\s+(.*?)\n', content)
        players = re.findall(r'-\s+(.*?)\s+\((\d+)\)', content)
        print(f"INFO: Veikkaukset '{filename}': joukkueita {len(teams)}, pelaajia {len(players)}")
        return {
            'teams': [t.strip() for t in teams],
            'players': [{'name': p[0].strip(), 'goals': int(p[1])} for p in players],
            'promotion': teams[0].strip() if teams else '',
            'playoff': teams[1].strip() if len(teams) > 1 else ''
        }
    except Exception as e:
        print(f"❌ Virhe veikkauksessa tiedostossa {filename}: {e}")
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''}


def normalize(text):
    return re.sub(r'\W+', '', text.lower())


def calculate_points(actual_table, actual_players, predictions):
    points = 0
    breakdown = []
    # Joukkueet
    for idx, pred in enumerate(predictions['teams']):
        if idx < len(actual_table):
            act = actual_table[idx]['name']
            if normalize(act) == normalize(pred):
                points += 3
                breakdown.append(f"3p: oikea sija {idx+1} ({act})")
    # Pelaajat
    for predp in predictions['players']:
        for actp in actual_players:
            if normalize(predp['name']) == normalize(actp['name']):
                pts = predp['goals']*2 + actp['assists']
                points += pts
                breakdown.append(f"{pts}p: {actp['name']} ({predp['goals']}g, {actp['assists']}a)")
    # Nousija
    if actual_table and predictions['promotion']:
        if normalize(actual_table[0]['name']) == normalize(predictions['promotion']):
            points += 5
            breakdown.append(f"5p: oikea nousija ({predictions['promotion']})")
    print(f"INFO: Lasketut pisteet: {points}")
    return {'points': points, 'breakdown': breakdown}


def generate_report():
    league = fetch_league_table()
    players = fetch_player_stats()
    dude = parse_predictions('DudeIslandVeikkaus.md')
    simple = parse_predictions('ykkonen_prediction_2025_simple.md')

    # DEBUG
    print(f"DEBUG: sarjataulukko ({len(league)}), pelaajat ({len(players)})")

    dpts = calculate_points(league, players, dude)
    spts = calculate_points(league, players, simple)

    now = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    report = [
        f"# Veikkausliiga 2025 - Tilanne {now}",
        "", "## Pistetilanne",
        f"- DudeIsland: **{dpts['points']} pistettä**",
        f"- Simple: **{spts['points']} pistettä**", "",
        "## Sarjataulukko",
        "| Sija | Joukkue | Source |",
        "|-----:|--------|--------|"
    ]
    for t in sorted(league, key=lambda x: x['position']):
        report.append(f"| {t['position']} | {t['name']} | {t['source']} |")
    report += ["", "## Maalintekijät", "| Pelaaja | Joukkue | Maalit | Syötöt |", "|--------|---------|-------:|------:|"]
    for p in sorted(players, key=lambda x: x['goals'], reverse=True):
        report.append(f"| {p['name']} | {p['team']} | {p['goals']} | {p['assists']} |")
    report += ["", "## Pisteiden erittely", "### DudeIsland"]
    report += [f"- {line}" for line in dpts['breakdown']]
    report += ["", "### Simple"]
    report += [f"- {line}" for line in spts['breakdown']]

    return "\n".join(report)

if __name__ == '__main__':
    output = generate_report()
    with open('Veikkaustilanne.md', 'w', encoding='utf-8') as f:
        f.write(output)
    print("✅ Veikkaustilanne.md päivittyi! Huom. tarkista DEBUG-viestit.")
