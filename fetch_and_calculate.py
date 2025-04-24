import requests
from bs4 import BeautifulSoup
import re
import datetime
import os
import time
import json
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# -------------------------------------------------------
# Fetch & Calculate - Veikkausliigan tilastot ja veikkaukset
# -------------------------------------------------------

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("veikkausliiga_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
LEAGUE_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
STATS_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points"
OUTPUT_DIR = "data"
CACHE_DIR = os.path.join(OUTPUT_DIR, "cache")

# Ensure directories exist
Path(OUTPUT_DIR).mkdir(exist_ok=True)
Path(CACHE_DIR).mkdir(exist_ok=True)

def setup_driver(headless=True):
    """Configure and return a Chrome WebDriver with enhanced settings"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")  # Updated headless mode
    
    # Add more robust arguments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        logger.error(f"Failed to setup Chrome driver: {e}")
        # Fallback to simple Chrome setup
        try:
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e2:
            logger.critical(f"Complete failure setting up Chrome: {e2}")
            raise

def save_cache(data, filename):
    """Save data to cache file"""
    cache_path = os.path.join(CACHE_DIR, filename)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Cached data to {filename}")

def load_cache(filename, max_age_hours=24):
    """Load data from cache if it exists and is not too old"""
    cache_path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(cache_path):
        return None
    
    # Check if cache is fresh enough
    file_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(cache_path))
    if file_age > datetime.timedelta(hours=max_age_hours):
        logger.info(f"Cache {filename} expired (age: {file_age})")
        return None
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded data from cache {filename}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load cache {filename}: {e}")
        return None

def fetch_with_selenium(url, wait_for_class=None, debug_file=None, attempts=3, wait_time=20):
    """Fetch page using Selenium with multiple retry attempts"""
    driver = None
    for attempt in range(1, attempts + 1):
        try:
            driver = setup_driver()
            logger.info(f"Fetching with Selenium (attempt {attempt}/{attempts}): {url}")
            driver.get(url)
            
            # Wait for page to fully load
            time.sleep(5)  # Give initial time for basic page load
            
            # If specific class to wait for was provided
            if wait_for_class:
                try:
                    WebDriverWait(driver, wait_time).until(
                        EC.presence_of_element_located((By.CLASS_NAME, wait_for_class))
                    )
                    logger.info(f"Found element with class '{wait_for_class}'")
                except TimeoutException:
                    logger.warning(f"Timed out waiting for '{wait_for_class}', continuing anyway")
            
            # Scroll down to ensure all lazy content loads
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for any scrolling effects
            
            page_source = driver.page_source
            
            # Save raw HTML for debugging if requested
            if debug_file:
                debug_path = os.path.join(CACHE_DIR, debug_file)
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.info(f"Saved raw HTML to {debug_path}")
            
            # Check if page appears to have loaded correctly
            if len(page_source) < 1000 or "Error" in page_source[:500]:
                logger.warning(f"Page may not have loaded correctly (size: {len(page_source)} bytes)")
                if attempt < attempts:
                    time.sleep(5)  # Wait before retry
                    continue
            
            return page_source
        except Exception as e:
            logger.error(f"Selenium error on attempt {attempt}: {e}")
            if attempt < attempts:
                time.sleep(5)  # Wait before retry
        finally:
            if driver:
                driver.quit()
    
    logger.error(f"All {attempts} attempts to fetch {url} failed")
    return None

def fetch_league_table():
    """Fetch the league table data with improved robustness"""
    # Try to load from cache first
    cached_data = load_cache('league_table.json')
    if cached_data:
        return cached_data
    
    # Try both the direct and alternative URL approaches
    html = fetch_with_selenium(
        LEAGUE_URL, 
        debug_file='league_table_raw.html', 
        wait_time=30  # Longer wait time for league table
    )
    
    if not html:
        logger.error("Failed to fetch league table HTML")
        # Return example data if we can't get real data
        return [
            {'position': 1, 'name': 'HJK', 'source': 'example'},
            {'position': 2, 'name': 'SJK', 'source': 'example'},
            {'position': 3, 'name': 'KuPS', 'source': 'example'},
            {'position': 4, 'name': 'Ilves', 'source': 'example'},
            {'position': 5, 'name': 'HIFK', 'source': 'example'},
            {'position': 6, 'name': 'FC Inter', 'source': 'example'},
            {'position': 7, 'name': 'FC Lahti', 'source': 'example'},
            {'position': 8, 'name': 'VPS', 'source': 'example'},
            {'position': 9, 'name': 'AC Oulu', 'source': 'example'},
            {'position': 10, 'name': 'KTP', 'source': 'example'}
        ]
    
    # Save raw HTML to a file for debugging
    debug_path = os.path.join(CACHE_DIR, 'league_table_debug.html')
    with open(debug_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    soup = BeautifulSoup(html, 'html.parser')
    teams = []
    
    # Try multiple approaches to locate the table
    
    # Approach 1: Find table with class 'spl-table'
    tables = soup.select('table.spl-table')
    if tables:
        logger.info(f"Found {len(tables)} tables with class 'spl-table'")
    else:
        logger.warning("No tables with class 'spl-table' found")
    
    # Approach 2: Find any table element
    if not tables:
        tables = soup.select('table')
        logger.info(f"Found {len(tables)} generic tables")
    
    # Approach 3: Look for divs that might contain standings
    if not tables:
        standings_divs = soup.select('div.standings, div.table-container, div.league-table')
        if standings_divs:
            for div in standings_divs:
                tables.extend(div.select('table'))
            logger.info(f"Found {len(tables)} tables in standings divs")
    
    # Process all found tables
    for table_idx, table in enumerate(tables):
        logger.info(f"Processing table #{table_idx+1}")
        
        # Try to determine if this is a standings table
        headers = [th.get_text().strip().lower() for th in table.select('th')]
        
        # Check if it looks like a standings table
        is_standings = any('joukkue' in h for h in headers) or any('team' in h for h in headers)
        if not is_standings and len(headers) >= 3:  # Position, Team, Points at minimum
            is_standings = True
        
        if not is_standings:
            logger.info(f"Table #{table_idx+1} does not appear to be a standings table, skipping")
            continue
        
        # Process rows - try with various selectors
        rows = []
        selectors = ['tr.spl-row', 'tr[data-team-id]', 'tr:not(:first-child)']
        
        for selector in selectors:
            rows = table.select(selector)
            if rows:
                logger.info(f"Found {len(rows)} rows with selector '{selector}'")
                break
        
        # If still no rows, try all rows except first (header)
        if not rows and len(table.select('tr')) > 1:
            rows = table.select('tr')[1:]
            logger.info(f"Using all {len(rows)} non-header rows")
        
        position = 0
        for row_idx, row in enumerate(rows):
            try:
                # Get all cells
                cols = row.select('td')
                if len(cols) < 2:  # Need at least position and team name
                    logger.warning(f"Row {row_idx+1} has insufficient columns ({len(cols)}), skipping")
                    continue
                
                # Try to find position
                pos_text = cols[0].get_text().strip()
                pos_match = re.search(r'\d+', pos_text)
                
                if pos_match:
                    position = int(pos_match.group())
                else:
                    # If we can't extract position, use incremental counter
                    position += 1
                
                # Find team name - might be in different column depending on table structure
                if len(cols) >= 2:
                    team_name = cols[1].get_text().strip()
                    # Check if this column actually contains a team name (not just a number)
                    if re.match(r'^\d+$', team_name):
                        # Try next column
                        team_name = cols[2].get_text().strip() if len(cols) > 2 else "Unknown"
                else:
                    team_name = "Unknown Team"
                
                # Remove any trailing numbers or parentheses from team name
                team_name = re.sub(r'\s*\(\d+\)$', '', team_name)
                team_name = re.sub(r'\s+\d+$', '', team_name)
                
                if team_name and team_name != "Unknown Team":
                    teams.append({
                        'position': position, 
                        'name': team_name, 
                        'source': 'web'
                    })
                    logger.info(f"Added team: {position}. {team_name}")
            except Exception as e:
                logger.warning(f"Error parsing row {row_idx+1}: {e}")
    
    # If we found teams, sort them by position and cache
    if teams:
        teams = sorted(teams, key=lambda x: x['position'])
        save_cache(teams, 'league_table.json')
        logger.info(f"Extracted {len(teams)} teams from league table")
        return teams
    
    logger.warning("Failed to extract teams from any tables")
    
    # If we still have no teams, try to extract from text
    standings_text = soup.get_text()
    team_matches = re.findall(r'(\d+)[\.)\s]+([A-Za-zÄÖÅäöå\s\-]+)(?:\s+\d+){2,}', standings_text)
    
    if team_matches:
        for pos_str, name in team_matches:
            try:
                position = int(pos_str)
                team_name = name.strip()
                if team_name:
                    teams.append({
                        'position': position,
                        'name': team_name,
                        'source': 'text_extract'
                    })
            except ValueError:
                continue
    
    if teams:
        teams = sorted(teams, key=lambda x: x['position'])
        save_cache(teams, 'league_table.json')
        logger.info(f"Extracted {len(teams)} teams from text pattern matching")
        return teams
    
    # If all else fails, provide example/fallback data
    logger.warning("Using example league table data as fallback")
    return [
        {'position': 1, 'name': 'HJK', 'source': 'example'},
        {'position': 2, 'name': 'SJK', 'source': 'example'},
        {'position': 3, 'name': 'KuPS', 'source': 'example'},
        {'position': 4, 'name': 'Ilves', 'source': 'example'},
        {'position': 5, 'name': 'HIFK', 'source': 'example'},
        {'position': 6, 'name': 'FC Inter', 'source': 'example'},
        {'position': 7, 'name': 'FC Lahti', 'source': 'example'},
        {'position': 8, 'name': 'VPS', 'source': 'example'},
        {'position': 9, 'name': 'AC Oulu', 'source': 'example'},
        {'position': 10, 'name': 'KTP', 'source': 'example'}
    ]

def fetch_player_stats():
    """Fetch player statistics data"""
    # Try to load from cache first
    cached_data = load_cache('player_stats.json')
    if cached_data:
        return cached_data
    
    # Fetch with Selenium
    html = fetch_with_selenium(STATS_URL, debug_file='player_stats_raw.html')
    if not html:
        logger.error("Failed to fetch player stats HTML")
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    players = []
    
    # Try different table selectors
    for table_selector in ['table.spl-table', 'table.statistics', 'table']:
        table = soup.select_one(table_selector)
        if table:
            break
    
    if not table:
        logger.warning("Player stats table not found")
        return []
    
    # Find column indices - column structure might change
    header_row = table.select_one('tr')
    if header_row:
        headers = [th.get_text().strip().lower() for th in header_row.find_all(['th', 'td'])]
        name_idx = next((i for i, h in enumerate(headers) if 'name' in h or 'nimi' in h), 0)
        team_idx = next((i for i, h in enumerate(headers) if 'team' in h or 'joukkue' in h), 1)
        goals_idx = next((i for i, h in enumerate(headers) if 'goal' in h or 'maali' in h), 3)
        assists_idx = next((i for i, h in enumerate(headers) if 'assist' in h or 'syött' in h), 4)
    else:
        # Default indices if header not found
        name_idx, team_idx, goals_idx, assists_idx = 0, 1, 3, 4
    
    # Extract player rows - try multiple patterns
    rows = table.select('tr.spl-row') or table.select('tr:not(:first-child)') or table.select('tr')[1:]
    
    for row in rows:
        cols = row.select('td')
        if len(cols) <= max(name_idx, team_idx, goals_idx, assists_idx):
            continue
        
        try:
            name = cols[name_idx].get_text().strip()
            team = cols[team_idx].get_text().strip()
            
            # Extract numeric values
            goals_text = cols[goals_idx].get_text().strip()
            assists_text = cols[assists_idx].get_text().strip()
            
            goals = int(re.search(r'\d+', goals_text).group()) if re.search(r'\d+', goals_text) else 0
            assists = int(re.search(r'\d+', assists_text).group()) if re.search(r'\d+', assists_text) else 0
            
            if name and team:
                players.append({
                    'name': name,
                    'team': team,
                    'goals': goals,
                    'assists': assists,
                    'source': 'web'
                })
        except Exception as e:
            logger.warning(f"Error parsing player row: {e}")
    
    if players:
        # Cache the results
        save_cache(players, 'player_stats.json')
        logger.info(f"Extracted {len(players)} players from stats table")
    else:
        logger.warning("No players extracted from stats table")
    
    return players

def parse_predictions(filename):
    """Parse prediction files with better error handling and format flexibility"""
    if not os.path.exists(filename):
        logger.warning(f"Prediction file not found: {filename}")
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''}
    
    try:
        content = open(filename, 'r', encoding='utf-8').read()
        
        # Extract team predictions - looking for numbered list items
        team_pattern = r'(\d+)[\.:\)]\s+(.*?)(?=\n|$)'
        team_matches = re.findall(team_pattern, content)
        teams = [t[1].strip() for t in sorted(team_matches, key=lambda x: int(x[0]))]
        
        # Extract player predictions - different formats supported
        player_patterns = [
            r'-\s+(.*?)\s+\((\d+)\)',  # Format: - Player Name (10)
            r'\*\s+(.*?)\s+\((\d+)\)',  # Format: * Player Name (10)
            r'(\d+)\.\s+(.*?)\s+\((\d+)\)'  # Format: 1. Player Name (10)
        ]
        
        players = []
        for pattern in player_patterns:
            matches = re.findall(pattern, content)
            if matches:
                if len(matches[0]) == 2:  # First pattern format
                    players.extend([{'name': p[0].strip(), 'goals': int(p[1])} for p in matches])
                elif len(matches[0]) == 3:  # Third pattern format
                    players.extend([{'name': p[1].strip(), 'goals': int(p[2])} for p in matches])
        
        logger.info(f"Parsed predictions from {filename}: {len(teams)} teams, {len(players)} players")
        
        # Promotion and playoff teams are the 1st and 2nd in the prediction
        promotion = teams[0] if teams else ''
        playoff = teams[1] if len(teams) > 1 else ''
        
        return {
            'teams': teams,
            'players': players,
            'promotion': promotion,
            'playoff': playoff
        }
    except Exception as e:
        logger.error(f"Error parsing predictions from {filename}: {e}")
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''}

def normalize(text):
    """Normalize text for comparison, with enhanced cleaning"""
    if not text:
        return ''
    # Convert to lowercase, remove all non-alphanumeric chars, normalize spaces
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def find_matching_item(name, items, key='name'):
    """Find a matching item using normalized comparison with multiple fallbacks"""
    if not name or not items:
        return None
    
    # Try exact normalized match first
    norm_name = normalize(name)
    for item in items:
        if normalize(item.get(key, '')) == norm_name:
            return item
    
    # Try substring matching if exact match failed
    for item in items:
        if norm_name in normalize(item.get(key, '')):
            return item
    
    # Try fuzzy matching - look for names where at least first and last name match
    name_parts = norm_name.split()
    if len(name_parts) >= 2:
        first, last = name_parts[0], name_parts[-1]
        for item in items:
            item_norm = normalize(item.get(key, ''))
            if first in item_norm and last in item_norm:
                return item
    
    return None

def calculate_points(actual_table, actual_players, predictions):
    """Calculate prediction points with improved matching algorithm"""
    points = 0
    breakdown = []
    
    # Team position points
    for idx, pred_team in enumerate(predictions['teams']):
        if idx < len(actual_table):
            actual_pos = idx + 1
            actual_team = actual_table[idx]['name']
            
            # Check if prediction matches actual
            if normalize(actual_team) == normalize(pred_team):
                team_points = 3
                points += team_points
                breakdown.append(f"{team_points}p: oikea sija {actual_pos} ({actual_team})")
    
    # Player stats points
    for pred_player in predictions['players']:
        # Try to find matching player in actual data
        actual_player = find_matching_item(pred_player['name'], actual_players)
        if actual_player:
            pred_goals = pred_player['goals']
            actual_goals = actual_player['goals']
            actual_assists = actual_player['assists']
            
            # Calculate points: 2 points per correct goal + 1 point per assist
            player_points = pred_goals * 2 + actual_assists
            points += player_points
            
            breakdown.append(
                f"{player_points}p: {actual_player['name']} ({pred_goals}g, {actual_assists}a)"
            )
    
    # Promotion team bonus
    if actual_table and predictions['promotion']:
        if normalize(actual_table[0]['name']) == normalize(predictions['promotion']):
            promo_points = 5
            points += promo_points
            breakdown.append(f"{promo_points}p: oikea nousija ({predictions['promotion']})")
    
    logger.info(f"Calculated total points: {points} with {len(breakdown)} scoring events")
    return {'points': points, 'breakdown': breakdown}

def generate_report():
    """Generate the full report with all available data"""
    logger.info("Starting report generation")
    
    # Fetch data
    league = fetch_league_table()
    players = fetch_player_stats()
    
    # Parse predictions
    prediction_files = {
        'DudeIsland': 'DudeIslandVeikkaus.md',
        'Simple': 'ykkonen_prediction_2025_simple.md'
    }
    
    # Create empty prediction files if they don't exist
    for filename in prediction_files.values():
        if not os.path.exists(filename):
            logger.warning(f"Creating empty prediction file: {filename}")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("# Veikkausliiga 2025 Prediction\n\n")
                f.write("## Sarjataulukko\n1. Team A\n2. Team B\n\n")
                f.write("## Maalintekijät\n- Player One (10)\n- Player Two (5)\n")
    
    predictions = {name: parse_predictions(file) for name, file in prediction_files.items()}
    
    # Calculate points
    points = {name: calculate_points(league, players, pred) 
              for name, pred in predictions.items()}
    
    # Generate the report
    now = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    report = [
        f"# Veikkausliiga 2025 - Tilanne {now}",
        "",
        "## Pistetilanne"
    ]
    
    # Add points for each participant
    for name, pts in points.items():
        report.append(f"- {name}: **{pts['points']} pistettä**")
    
    # Add league table
    report.extend([
        "",
        "## Sarjataulukko",
        "| Sija | Joukkue | Source |",
        "|-----:|--------|--------|"
    ])
    
    if league:
        for team in sorted(league, key=lambda x: x['position']):
            report.append(f"| {team['position']} | {team['name']} | {team['source']} |")
    else:
        report.append("| - | *Ei tietoja saatavilla* | - |")
    
    # Add player stats
    report.extend([
        "",
        "## Maalintekijät",
        "| Pelaaja | Joukkue | Maalit | Syötöt |",
        "|--------|---------|-------:|------:|"
    ])
    
    if players:
        for player in sorted(players, key=lambda x: x['goals'], reverse=True):
            report.append(f"| {player['name']} | {player['team']} | {player['goals']} | {player['assists']} |")
    else:
        report.append("| *Ei tietoja saatavilla* | - | - | - |")
    
    # Add point breakdowns
    report.append("")
    report.append("## Pisteiden erittely")
    
    for name, pts in points.items():
        report.append(f"### {name}")
        if pts['breakdown']:
            for line in pts['breakdown']:
                report.append(f"- {line}")
        else:
            report.append("- *Ei pisteitä*")
        report.append("")
    
    return "\n".join(report)

if __name__ == '__main__':
    try:
        logger.info("Starting Veikkausliiga tracker")
        output = generate_report()
        with open('Veikkaustilanne.md', 'w', encoding='utf-8') as f:
            f.write(output)
        logger.info("✅ Veikkaustilanne.md päivitetty onnistuneesti!")
    except Exception as e:
        logger.error(f"❌ Virhe ohjelman suorituksessa: {e}", exc_info=True)
