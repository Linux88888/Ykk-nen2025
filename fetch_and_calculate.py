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
        logging.FileHandler("veikkausliiga_scraper.log", encoding='utf-8'), # Yhtenäinen lokitiedoston nimi
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
LEAGUE_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/group/1"
STATS_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/points" # HUOM: Tämä URL on pistepörssi, ei pelaajatilastot kuten maalit/syötöt
                                                                                        # Pelaajatilastoille (maalit, syötöt) tarvitaan eri URL tai eri kohta sivulta
PLAYER_STATS_GOALS_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/goals" # Oletettu URL maalipörssille
PLAYER_STATS_ASSISTS_URL = "https://tulospalvelu.palloliitto.fi/category/M1L!spljp25/statistics/assists" # Oletettu URL syöttöpörssille


OUTPUT_DIR = "data" # Pääkansion sisällä oleva data-kansio
CACHE_DIR = os.path.join(OUTPUT_DIR, "cache") # data/cache

# Current time stamp for this run
TIMESTAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

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
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    prefs = {'intl.accept_languages': 'fi,fi_FI'}
    chrome_options.add_experimental_option('prefs', prefs)
    
    try:
        service = Service(ChromeDriverManager().install(), log_output=os.devnull)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(45) # Hieman pidempi timeout
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.error(f"Failed to setup Chrome driver with Service: {e}")
        try:
            logger.info("Falling back to simpler Chrome driver setup...")
            driver = webdriver.Chrome(options=chrome_options) # Fallback
            driver.set_page_load_timeout(45)
            return driver
        except Exception as e2:
            logger.critical(f"Complete failure setting up Chrome: {e2}")
            raise

def save_cache(data, filename):
    """Save data to cache file"""
    cache_path = os.path.join(CACHE_DIR, filename)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Cached data to {filename}")
    except Exception as e:
        logger.error(f"Error saving cache to {cache_path}: {e}")


def load_cache(filename, max_age_hours=6): # Lyhennetty välimuistin ikä 6 tuntiin
    """Load data from cache if it exists and is not too old"""
    cache_path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(cache_path):
        logger.info(f"Cache file not found: {cache_path}")
        return None
    
    try:
        file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(cache_path))
        file_age = datetime.datetime.now() - file_mod_time
        
        if file_age > datetime.timedelta(hours=max_age_hours):
            logger.info(f"Cache {filename} expired (age: {file_age}, max_age: {max_age_hours}h). Will refetch.")
            return None # Välimuisti vanhentunut
        
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded data from cache {filename} (age: {file_age})")
        return data
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to decode JSON from cache file {cache_path}: {e}. Will refetch.")
        return None
    except Exception as e:
        logger.warning(f"Failed to load cache {filename}: {e}. Will refetch.")
        return None

def fetch_with_selenium(url, wait_for_selector=None, wait_type="CLASS_NAME", debug_file=None, attempts=3, wait_time=25):
    """Fetch page using Selenium with multiple retry attempts and flexible wait condition"""
    driver = None
    for attempt in range(1, attempts + 1):
        try:
            driver = setup_driver()
            if not driver:
                logger.error(f"Driver setup failed on attempt {attempt} for {url}")
                if attempt < attempts: time.sleep(5); continue
                else: return None

            logger.info(f"Fetching with Selenium (attempt {attempt}/{attempts}): {url}")
            driver.get(url)
            
            time.sleep(3) # Lyhyt alkuodotus
            
            if wait_for_selector:
                try:
                    logger.info(f"Waiting for element with {wait_type} '{wait_for_selector}' (max {wait_time}s)")
                    if wait_type.upper() == "CLASS_NAME":
                        WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CLASS_NAME, wait_for_selector))
                        )
                    elif wait_type.upper() == "CSS_SELECTOR":
                         WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                        )
                    else: # Oletus ID
                         WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.ID, wait_for_selector))
                        )
                    logger.info(f"Found element '{wait_for_selector}'")
                except TimeoutException:
                    logger.warning(f"Timed out waiting for '{wait_for_selector}' at {url}, continuing anyway...")
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            page_source = driver.page_source
            
            if debug_file:
                # Uniikki tiedostonimi aikaleimalla, jotta ei ylikirjoiteta
                unique_debug_file = f"{TIMESTAMP}_{os.path.splitext(debug_file)[0]}{os.path.splitext(debug_file)[1]}"
                debug_path = os.path.join(CACHE_DIR, unique_debug_file)
                try:
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(page_source if page_source else "<!-- Page source was empty -->")
                    logger.info(f"Saved raw HTML to {debug_path}")
                except Exception as e:
                    logger.error(f"Error saving debug HTML to {debug_path}: {e}")

            if not page_source or len(page_source) < 1000: # Tarkistus, onko sivu validi
                logger.warning(f"Page {url} may not have loaded correctly (size: {len(page_source) if page_source else 0} bytes)")
                if attempt < attempts: time.sleep(5); continue # Yritä uudelleen
                else: return None # Kaikki yritykset epäonnistuivat
            
            return page_source
        except WebDriverException as e: # Käsittele erikseen WebDriver-spesifit virheet
             logger.error(f"WebDriverException on attempt {attempt} for {url}: {e}")
             if "net::ERR_NAME_NOT_RESOLVED" in str(e) or "net::ERR_CONNECTION_REFUSED" in str(e):
                 logger.error(f"Network error for {url}. Stopping retries for this URL.")
                 return None # Ei yritetä uudelleen verkkovirheissä
        except Exception as e:
            logger.error(f"General error on Selenium attempt {attempt} for {url}: {e}", exc_info=True)
        finally:
            if driver:
                driver.quit()
            if attempt < attempts: # Jos ei ollut viimeinen yritys ja virhe tapahtui
                time.sleep(5 + attempt * 2) # Kasvava odotus

    logger.error(f"All {attempts} attempts to fetch {url} failed.")
    return None

def fetch_league_table():
    """Fetch the league table data"""
    cache_filename = 'league_table_cache.json' # Selkeämpi nimi välimuistille
    cached_data = load_cache(cache_filename, max_age_hours=6) # Käytä lyhyempää ikää
    if cached_data:
        return cached_data
    
    html = fetch_with_selenium(
        LEAGUE_URL, 
        wait_for_selector='spl-table', # Odotetaan tätä luokkaa
        wait_type="CLASS_NAME",
        debug_file='league_table_raw.html', 
        wait_time=30 
    )
    
    if not html:
        logger.error("Failed to fetch league table HTML from Palloliitto.")
        # Palautetaan tyhjä lista virhetilanteessa, esimerkkidatan sijaan
        return [] 
    
    # Tallennetaan aina tuorein haettu HTML debuggausta varten
    # (fetch_with_selenium hoitaa tämän jo, jos debug_file on annettu)

    soup = BeautifulSoup(html, 'html.parser')
    teams = []
    
    # Yritetään löytää taulukko, jolla on luokka 'spl-table'
    # Tämä on spesifisempi ja todennäköisemmin oikea taulukko
    table = soup.select_one('table.spl-table') 

    if not table:
        logger.warning("Could not find 'table.spl-table'. Trying generic 'table' selector.")
        # Fallback: jos .spl-table ei löydy, kokeillaan ensimmäistä geneeristä taulukkoa
        # Tämä voi olla epäluotettava, mutta parempi kuin ei mitään
        table = soup.select_one('table') 
        if not table:
            logger.error("No tables found on the league page. Cannot extract standings.")
            return [] # Palauta tyhjä, jos mitään taulukkoa ei löydy

    # Parsi taulukon rivit
    # Oletetaan, että ensimmäinen rivi on otsikkorivi ja se ohitetaan
    rows = table.select('tr') 
    if not rows or len(rows) < 2 : # Tarvitaan vähintään otsikko ja yksi datarivi
        logger.warning(f"Table at {LEAGUE_URL} has too few rows ({len(rows)}). Cannot extract standings.")
        return []

    start_row_index = 0
    # Tarkista onko ensimmäinen rivi otsikkorivi (sisältää th-elementtejä)
    if rows[0].find('th'):
        start_row_index = 1
        logger.info("Skipping header row in league table.")
    else:
        logger.info("No clear header row with <th> found, processing all rows. First row might be data.")


    for idx, row in enumerate(rows[start_row_index:]): # Aloita datan parsiminen otsikkorivin jälkeen (tai alusta)
        cols = row.select('td')
        if len(cols) < 3: # Oletetaan vähintään Sija, Joukkue, Pisteet
            logger.warning(f"Skipping row {idx+start_row_index} in league table: not enough columns (found {len(cols)}). Row content: {row.get_text('|', strip=True)}")
            continue
        
        try:
            # Sijoitus: Yritä ensin sarakkeesta 0, sitten sarakkeesta 1
            position_text = cols[0].get_text(strip=True)
            position_match = re.search(r'^\d+', position_text) # Etsi numero rivin alusta
            if not position_match and len(cols) > 1: # Jos ei löytynyt ekasta, kokeile tokaa
                position_text_col2 = cols[1].get_text(strip=True)
                position_match_col2 = re.search(r'^\d+', position_text_col2)
                if position_match_col2: # Jos toisesta löytyi numero, oleta se sijoitukseksi
                     position = int(position_match_col2.group(0))
                     # Ja oleta joukkueen nimi olevan sarakkeessa 2
                     team_name_col_index = 2
                else: # Jos kummastakaan ei löytynyt numeroa, käytä indeksiä
                    position = idx + 1 # Käytä rivin indeksiä (0-pohjainen) + 1 sijoituksena
                    team_name_col_index = 1 # Oleta joukkueen nimi olevan sarakkeessa 1
                    logger.info(f"Could not parse position for row {idx+start_row_index}, using index {position}. Text: '{position_text}'")

            else: # Jos ekasta sarakkeesta löytyi numero
                position = int(position_match.group(0))
                team_name_col_index = 1 # Oleta joukkueen nimi olevan sarakkeessa 1

            if team_name_col_index >= len(cols):
                logger.warning(f"Team name column index {team_name_col_index} is out of bounds for row {idx+start_row_index}. Skipping.")
                continue
            
            team_name = cols[team_name_col_index].get_text(strip=True)
            
            # Poista mahdolliset ylimääräiset tiedot joukkueen nimestä (esim. "(Siirretty)")
            team_name = re.sub(r'\s*\(.*?\)\s*$', '', team_name).strip()

            if not team_name: # Jos joukkueen nimi on tyhjä, ohita rivi
                logger.warning(f"Empty team name for row {idx+start_row_index} at position {position}. Skipping.")
                continue

            teams.append({
                'position': position, 
                'name': team_name, 
                'source': 'web' # Merkitään, että data on haettu webistä
            })
            logger.info(f"Extracted team: Pos: {position}, Name: {team_name}")

        except Exception as e:
            logger.warning(f"Error parsing row {idx+start_row_index} in league table: {e}. Row: {row.get_text('|', strip=True)}")

    if teams:
        teams = sorted(teams, key=lambda x: x['position']) # Järjestä sijoituksen mukaan
        save_cache(teams, cache_filename)
        logger.info(f"Successfully extracted and cached {len(teams)} teams from league table.")
    else:
        logger.warning("No teams extracted from league table. Check HTML structure and selectors.")
        # Palauta tyhjä lista, jos mitään ei löytynyt
        return []
        
    return teams

def fetch_player_stats_category(stats_url, category_name, debug_file_suffix):
    """Fetches and parses a specific player statistics category (e.g., goals, assists)."""
    cache_filename = f'player_stats_{category_name}_cache.json'
    cached_data = load_cache(cache_filename, max_age_hours=6)
    if cached_data:
        return cached_data

    html = fetch_with_selenium(
        stats_url,
        wait_for_selector='spl-table', # Odotetaan tätä luokkaa
        wait_type="CLASS_NAME",
        debug_file=f'player_stats_{debug_file_suffix}_raw.html',
        wait_time=30
    )

    if not html:
        logger.error(f"Failed to fetch HTML for {category_name} from {stats_url}")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    players = []
    table = soup.select_one('table.spl-table')

    if not table:
        logger.warning(f"Player stats table ('table.spl-table') not found for {category_name} at {stats_url}")
        return []

    rows = table.select('tr')
    if not rows or len(rows) < 2:
        logger.warning(f"Stats table for {category_name} has too few rows ({len(rows)}).")
        return []
    
    start_row_index = 0
    if rows[0].find('th'): # Tarkista onko header
        start_row_index = 1
        logger.info(f"Skipping header row in {category_name} table.")

    # Yritetään dynaamisesti päätellä sarakkeiden indeksit otsikoiden perusteella
    name_idx, team_idx, stat_value_idx = -1, -1, -1
    if start_row_index == 1: # Jos header löytyi
        headers = [th.get_text(strip=True).lower() for th in rows[0].select('th, td')]
        logger.info(f"Headers for {category_name}: {headers}")
        try: name_idx = headers.index('pelaaja') # Oletus 'pelaaja'
        except ValueError: 
            try: name_idx = headers.index('nimi') # Fallback 'nimi'
            except ValueError: name_idx = 1 # Viimeinen fallback indeksiin 1
        
        try: team_idx = headers.index('joukkue')
        except ValueError: team_idx = 2 # Fallback indeksiin 2
        
        # Tilastoarvon indeksi (maalit/syötöt)
        # Yleensä se on viimeinen tai toiseksi viimeinen sarake
        # Kokeillaan ensin "maalit", "syötöt", sitten "m", "s"
        # Ja jos ei löydy, oletetaan, että se on kolmas numeerinen sarake tai viimeinen.
        possible_stat_headers = [category_name.rstrip('s'), category_name[0]] # esim. "maali", "m"
        stat_value_idx = next((i for i, h in enumerate(headers) if any(ps in h for ps in possible_stat_headers) or h == "yht."), -1)

        if stat_value_idx == -1: # Jos ei löytynyt suoraan, etsi saraketta, joka sisältää vain numeroita
            for i, h_text in enumerate(headers):
                # Yritä löytää sarake, joka todennäköisesti sisältää numeroarvon
                # Esim. jos otsikko on tyhjä tai lyhyt ja ei ole nimi/joukkue
                 if i > team_idx and (not h_text or len(h_text) < 3):
                    stat_value_idx = i
                    break
        if stat_value_idx == -1: # Jos vieläkään ei löytynyt, oleta esim. 3 tai viimeinen
            stat_value_idx = 3 if len(headers) > 3 else len(headers) -1


        logger.info(f"Determined column indices for {category_name}: Name={name_idx}, Team={team_idx}, StatValue={stat_value_idx}")


    else: # Jos ei headeria, käytä oletusindeksejä
        name_idx, team_idx, stat_value_idx = 1, 2, 3 # Oletus: Pelaaja, Joukkue, Maalit/Syötöt
        logger.info(f"No header row found for {category_name}, using default indices: Name={name_idx}, Team={team_idx}, StatValue={stat_value_idx}")


    for idx, row in enumerate(rows[start_row_index:]):
        cols = row.select('td')
        if len(cols) <= max(name_idx, team_idx, stat_value_idx): # Varmista, että kaikki tarvittavat sarakkeet ovat olemassa
            logger.warning(f"Skipping row in {category_name} table: not enough columns (need up to {max(name_idx, team_idx, stat_value_idx)}, found {len(cols)}). Row: {row.get_text('|', strip=True)}")
            continue

        try:
            name = cols[name_idx].get_text(strip=True)
            team = cols[team_idx].get_text(strip=True)
            stat_text = cols[stat_value_idx].get_text(strip=True)
            
            # Puhdista stat_text ja ota vain numero
            stat_value_match = re.search(r'(\d+)', stat_text)
            stat_value = int(stat_value_match.group(1)) if stat_value_match else 0

            if name and team: # Varmista, että nimi ja joukkue eivät ole tyhjiä
                players.append({
                    'name': name,
                    'team': team,
                    category_name: stat_value, # Käytä dynaamista avainta (esim. 'goals' tai 'assists')
                    'source': 'web'
                })
            else:
                logger.warning(f"Skipping player in {category_name}: empty name or team. Row: {row.get_text('|', strip=True)}")

        except IndexError:
            logger.warning(f"IndexError parsing row in {category_name} table (cols: {len(cols)}, needed: {name_idx}, {team_idx}, {stat_value_idx}). Row: {row.get_text('|', strip=True)}")
        except ValueError:
            logger.warning(f"ValueError parsing stat value '{stat_text}' for player {name} in {category_name}. Setting to 0. Row: {row.get_text('|', strip=True)}")
        except Exception as e:
            logger.warning(f"Error parsing player row in {category_name} table: {e}. Row: {row.get_text('|', strip=True)}")

    if players:
        save_cache(players, cache_filename)
        logger.info(f"Successfully extracted and cached {len(players)} players for {category_name}.")
    else:
        logger.warning(f"No players extracted for {category_name}. Check HTML structure and selectors at {stats_url}")
    
    return players

def merge_player_stats(goals_data, assists_data):
    """Merges player statistics from goals and assists lists."""
    merged_stats = {} # Käytä sanakirjaa pelaajan nimen ja joukkueen perusteella

    for player in goals_data:
        key = (normalize(player['name']), normalize(player['team']))
        if key not in merged_stats:
            merged_stats[key] = {'name': player['name'], 'team': player['team'], 'goals': 0, 'assists': 0, 'source': 'web'}
        merged_stats[key]['goals'] = player.get('goals', 0)

    for player in assists_data:
        key = (normalize(player['name']), normalize(player['team']))
        if key not in merged_stats:
            merged_stats[key] = {'name': player['name'], 'team': player['team'], 'goals': 0, 'assists': 0, 'source': 'web'}
        merged_stats[key]['assists'] = player.get('assists', 0)
    
    return list(merged_stats.values())


def fetch_all_player_stats():
    """Fetches both goal and assist stats and merges them."""
    logger.info("Fetching player goals statistics...")
    goals_stats = fetch_player_stats_category(PLAYER_STATS_GOALS_URL, 'goals', 'goals')
    
    logger.info("Fetching player assists statistics...")
    assists_stats = fetch_player_stats_category(PLAYER_STATS_ASSISTS_URL, 'assists', 'assists')
    
    if not goals_stats and not assists_stats:
        logger.warning("No data fetched for either goals or assists. Returning empty list.")
        return []

    logger.info("Merging player goals and assists statistics...")
    all_players = merge_player_stats(goals_stats, assists_stats)
    
    if all_players:
        logger.info(f"Successfully merged player stats. Total unique players: {len(all_players)}")
    else:
        logger.warning("Merged player stats list is empty.")
        
    return all_players


def parse_predictions(filename):
    """Parse prediction files with better error handling and format flexibility"""
    if not os.path.exists(filename):
        logger.warning(f"Prediction file not found: {filename}")
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''} # Palauta tyhjä rakenne
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pura joukkue-ennusteet: etsi numeroituja listoja
        team_pattern = r'^\s*(\d+)\s*[.:\)]\s+(.+?)(?=\n\s*\d+\s*[.:\)]|\n\n|\Z)'
        # ^\s*(\d+)\s*[.:\)]\s+  -> rivin alussa numero, piste/kaksoispiste/sulkumerkki, välilyöntejä
        # (.+?)                     -> joukkueen nimi (ei-ahne)
        # (?=\n\s*\d+\s*[.:\)]|\n\n|\Z) -> loppuu seuraavaan numeroituun riviin, tuplarevivinvaihtoon tai tiedoston loppuun
        
        team_matches = re.findall(team_pattern, content, re.MULTILINE)
        teams = [match[1].strip() for match in sorted(team_matches, key=lambda x: int(x[0]))]
        
        # Pura pelaajaennusteet: tukee useampia formaatteja
        # - Pelaaja Nimi (10)
        # * Pelaaja Nimi (10)
        # 1. Pelaaja Nimi (10)
        player_patterns = [
            r'^\s*-\s+(.+?)\s*\((\d+)\)',      # Format: - Player Name (10)
            r'^\s*\*\s+(.+?)\s*\((\d+)\)',    # Format: * Player Name (10)
            r'^\s*\d+\.\s+(.+?)\s*\((\d+)\)' # Format: 1. Player Name (10)
        ]
        
        players = []
        for pattern in player_patterns:
            # Etsi kaikki osumat koko sisällöstä, rivi kerrallaan (re.MULTILINE)
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                for match in matches:
                    # Olettaen, että match on tuple (nimi, maalit) tai (numero, nimi, maalit)
                    name = match[0].strip() if len(match) == 2 else match[1].strip()
                    goals_str = match[1] if len(match) == 2 else match[2]
                    try:
                        goals = int(goals_str)
                        players.append({'name': name, 'goals': goals})
                    except ValueError:
                        logger.warning(f"Could not parse goals '{goals_str}' for player '{name}' in {filename}")
        
        logger.info(f"Parsed predictions from {filename}: {len(teams)} teams, {len(players)} players")
        
        promotion = teams[0] if teams else ''
        playoff = teams[1] if len(teams) > 1 else '' # Toiseksi sijoittunut playoffiin
        
        return {
            'teams': teams,
            'players': players,
            'promotion': promotion,
            'playoff': playoff
        }
    except Exception as e:
        logger.error(f"Error parsing predictions from {filename}: {e}", exc_info=True)
        return {'teams': [], 'players': [], 'promotion': '', 'playoff': ''} # Palauta tyhjä rakenne virhetilanteessa

def normalize(text):
    """Normalize text for comparison, with enhanced cleaning"""
    if not text:
        return ''
    # Pieniksi kirjaimiksi, poista kaikki paitsi kirjaimet, numerot ja välilyönnit, normalisoi välilyönnit
    normalized = text.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized) # Poista erikoismerkit paitsi alaviiva
    normalized = re.sub(r'\s+', ' ', normalized).strip() # Korvaa useat välilyönnit yhdellä
    return normalized

def find_matching_item(name_to_find, item_list, key_in_item='name'):
    """Find a matching item using normalized comparison with multiple fallbacks"""
    if not name_to_find or not item_list:
        return None
    
    norm_name_to_find = normalize(name_to_find)
    
    # 1. Tarkka normalisoitu osuma
    for item in item_list:
        if normalize(item.get(key_in_item, '')) == norm_name_to_find:
            logger.debug(f"Exact match found for '{name_to_find}' -> '{item.get(key_in_item)}'")
            return item
    
    # 2. Osittainen osuma (normalisoitu nimi sisältyy kohteen normalisoituun nimeen)
    for item in item_list:
        if norm_name_to_find in normalize(item.get(key_in_item, '')):
            logger.debug(f"Substring match found for '{name_to_find}' in '{item.get(key_in_item)}'")
            return item

    # 3. Osittainen osuma (kohteen normalisoitu nimi sisältyy etsittävään normalisoituun nimeen)
    for item in item_list:
        item_norm_name = normalize(item.get(key_in_item, ''))
        if item_norm_name and item_norm_name in norm_name_to_find : # Varmista ettei item_norm_name ole tyhjä
            logger.debug(f"Substring match (reversed) found for '{item.get(key_in_item)}' in '{name_to_find}'")
            return item

    # 4. Sumea osuma: vähintään etu- ja sukunimi täsmäävät (jos nimessä osia)
    name_parts = norm_name_to_find.split()
    if len(name_parts) >= 2:
        first_part = name_parts[0]
        last_part = name_parts[-1]
        for item in item_list:
            item_norm = normalize(item.get(key_in_item, ''))
            if first_part in item_norm and last_part in item_norm:
                logger.debug(f"Fuzzy (first/last) match for '{name_to_find}' with '{item.get(key_in_item)}'")
                return item
    
    logger.debug(f"No match found for '{name_to_find}'")
    return None


def calculate_points(actual_table, actual_players, predictions):
    """Calculate prediction points with improved matching algorithm"""
    points = 0
    breakdown = []
    
    # Joukkuesijoitukset: 3 pistettä täysin oikeasta sijoituksesta
    if predictions.get('teams') and actual_table:
        for pred_idx, pred_team_name in enumerate(predictions['teams']):
            actual_pos_for_pred = pred_idx + 1 # Ennustettu sijoitus
            
            # Etsi ennustettua joukkuetta oikeasta sarjataulukosta
            found_actual_team_data = find_matching_item(pred_team_name, actual_table, key_in_item='name')

            if found_actual_team_data:
                actual_team_name = found_actual_team_data['name']
                actual_team_pos = found_actual_team_data['position']

                if actual_team_pos == actual_pos_for_pred: # Jos oikea joukkue on oikealla ennustetulla sijalla
                    team_points = 3
                    points += team_points
                    breakdown.append(f"{team_points}p: Oikea sija {actual_team_pos}. ({actual_team_name})")
            else:
                logger.warning(f"calculate_points: Predicted team '{pred_team_name}' not found in actual league table.")


    # Pelaajatilastot:
    # Maalikuningas: 5 pistettä jos osui täysin oikein, 2 pistettä jos pelaaja top 3:ssa.
    # Syöttökuningas (jos ennusteissa): 3 pistettä jos osui oikein.
    # (Nykyinen ennustetiedosto ei taida sisältää syöttökuningasveikkausta erikseen)
    if predictions.get('players') and actual_players:
        # Järjestä oikeat pelaajat maalien ja syöttöjen mukaan
        actual_top_scorers = sorted([p for p in actual_players if p.get('goals', 0) > 0], key=lambda x: x.get('goals', 0), reverse=True)
        # actual_top_assisters = sorted([p for p in actual_players if p.get('assists', 0) > 0], key=lambda x: x.get('assists', 0), reverse=True)

        for pred_player_entry in predictions['players']: # Oletetaan, että tämä on lista maalintekijäveikkauksista
            pred_player_name = pred_player_entry.get('name')
            # pred_player_goals = pred_player_entry.get('goals') # Ennustettuja maaleja ei käytetä pisteisiin

            if not pred_player_name: continue

            # Onko ennustettu pelaaja oikeasti maalikuningas?
            if actual_top_scorers:
                # Tarkista onko pelaaja jaettu ykkönen tai yksin ykkönen
                top_goal_count = actual_top_scorers[0].get('goals',0)
                all_actual_top_scorers_names = [normalize(p['name']) for p in actual_top_scorers if p.get('goals',0) == top_goal_count]

                if normalize(pred_player_name) in all_actual_top_scorers_names:
                    player_points = 5 # Täysin oikea maalikuningas
                    points += player_points
                    breakdown.append(f"{player_points}p: Oikea maalikuningas ({pred_player_name} - {top_goal_count} maalia)")
                else: # Jos ei ollut maalikuningas, tarkista oliko top 3
                    top_3_scorers_names = [normalize(p['name']) for p in actual_top_scorers[:3]]
                    if normalize(pred_player_name) in top_3_scorers_names:
                        player_points = 2 # Pelaaja top 3:ssa
                        points += player_points
                        actual_player_data = find_matching_item(pred_player_name, actual_top_scorers)
                        actual_g = actual_player_data.get('goals',0) if actual_player_data else '?'
                        breakdown.append(f"{player_points}p: Maalintekijäveikkaus top 3 ({pred_player_name} - {actual_g} maalia)")
    
    # Nousijajoukkueen bonus: 5 pistettä
    if predictions.get('promotion') and actual_table and len(actual_table) > 0:
        actual_promoted_team_name = actual_table[0].get('name') # Sarjataulukon ensimmäinen
        if normalize(actual_promoted_team_name) == normalize(predictions['promotion']):
            promo_points = 5
            points += promo_points
            breakdown.append(f"{promo_points}p: Oikea nousija ({predictions['promotion']})")

    # Karsijan bonus (Playoff-joukkue): 2 pistettä
    if predictions.get('playoff') and actual_table and len(actual_table) > 1:
        actual_playoff_team_name = actual_table[1].get('name') # Sarjataulukon toinen
        if normalize(actual_playoff_team_name) == normalize(predictions['playoff']):
            playoff_points = 2
            points += playoff_points
            breakdown.append(f"{playoff_points}p: Oikea karsija ({predictions['playoff']})")
            
    logger.info(f"Calculated total points: {points} with {len(breakdown)} scoring events. Breakdown: {'; '.join(breakdown)}")
    return {'points': points, 'breakdown': breakdown}

def generate_report():
    """Generate the full report with all available data"""
    logger.info("Starting report generation")
    
    # Fetch data
    league_table_data = fetch_league_table()
    # Pelaajatilastot haetaan nyt yhdistettynä funktiona
    player_stats_data = fetch_all_player_stats() 
    
    # Parse predictions
    prediction_files = {
        'DudeIsland': 'DudeIslandVeikkaus.md',
        'Simple': 'ykkonen_prediction_2025_simple.md' # Varmista, että tämä tiedosto on olemassa
    }
    
    # Luo tyhjät ennustetiedostot, jos niitä ei ole, jotta skripti ei kaadu
    for pred_file_path in prediction_files.values():
        if not os.path.exists(pred_file_path):
            logger.warning(f"Prediction file {pred_file_path} not found. Creating an empty template.")
            try:
                with open(pred_file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Ennusteet tiedostolle {os.path.basename(pred_file_path)}\n\n")
                    f.write("## Sarjataulukko\n1. Joukkue A\n2. Joukkue B\n3. Joukkue C\n\n")
                    f.write("## Maalintekijäveikkaus (top 1)\n- Pelaaja X (maalimäärä ei vaikuta pisteisiin)\n")
            except Exception as e:
                logger.error(f"Could not create template prediction file {pred_file_path}: {e}")

    predictions_by_user = {name: parse_predictions(file) for name, file in prediction_files.items()}
    
    # Calculate points
    points_by_user = {name: calculate_points(league_table_data, player_stats_data, pred) 
                      for name, pred in predictions_by_user.items()}
    
    # Generate the report
    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    report_lines = [
        f"# Ykkösliiga 2025 - Veikkaustilanne {now_str}",
        "",
        "## Pistetilanne"
    ]
    
    # Lisää pisteet jokaiselle osallistujalle, järjestettynä pisteiden mukaan
    sorted_points_by_user = sorted(points_by_user.items(), key=lambda item: item[1]['points'], reverse=True)
    for name, pts_info in sorted_points_by_user:
        report_lines.append(f"- {name}: **{pts_info['points']} pistettä**")
    
    # Sarjataulukko
    report_lines.extend([
        "",
        "## Sarjataulukko (Palloliitto)",
        "| Sija | Joukkue | Lähde |", # Lähde-sarake voi olla hyödyllinen debuggaukseen
        "|-----:|:--------|:------|"
    ])
    
    if league_table_data: # Varmista, että dataa on
        for team_entry in league_table_data: # Oletetaan, että fetch_league_table palauttaa jo valmiiksi järjestetyn listan
            report_lines.append(f"| {team_entry.get('position', 'N/A')} | {team_entry.get('name', 'N/A')} | {team_entry.get('source', 'N/A')} |")
    else:
        report_lines.append("| - | *Sarjataulukon tietoja ei saatavilla* | - |")
    
    # Pelaajatilastot (maalit ja syötöt)
    report_lines.extend([
        "",
        "## Pelaajatilastot (Palloliitto)",
        "| Pelaaja | Joukkue | Maalit | Syötöt |",
        "|:--------|:--------|-------:|-------:|"
    ])
    
    if player_stats_data: # Varmista, että dataa on
        # Järjestä pelaajat maalien mukaan, sitten syöttöjen, sitten nimen
        sorted_players = sorted(
            player_stats_data, 
            key=lambda x: (x.get('goals', 0), x.get('assists', 0), x.get('name', '')), 
            reverse=True
        )
        for player_entry in sorted_players:
            # Näytä vain jos pelaajalla on maaleja tai syöttöjä
            if player_entry.get('goals', 0) > 0 or player_entry.get('assists', 0) > 0:
                report_lines.append(
                    f"| {player_entry.get('name', 'N/A')} | {player_entry.get('team', 'N/A')} | "
                    f"{player_entry.get('goals', 0)} | {player_entry.get('assists', 0)} |"
                )
    else:
        report_lines.append("| *Pelaajatilastoja ei saatavilla* | - | - | - |")
    
    # Pisteiden erittely
    report_lines.append("")
    report_lines.append("## Pisteiden erittely")
    
    for name, pts_info in sorted_points_by_user: # Käytä samaa järjestystä kuin pistetaulukossa
        report_lines.append(f"### {name} ({pts_info['points']}p)")
        if pts_info['breakdown']:
            for line in pts_info['breakdown']:
                report_lines.append(f"- {line}")
        else:
            report_lines.append("- *Ei pisteitä tästä kategoriasta*")
        report_lines.append("") # Tyhjä rivi erottimeksi
    
    return "\n".join(report_lines)

if __name__ == '__main__':
    try:
        logger.info("Starting Veikkausliiga tracker script: fetch_and_calculate.py")
        report_output = generate_report()
        
        output_md_file = 'Veikkaustilanne.md'
        with open(output_md_file, 'w', encoding='utf-8') as f:
            f.write(report_output)
        logger.info(f"✅ {output_md_file} päivitetty onnistuneesti!")
        
    except Exception as e:
        logger.error(f"❌ Virhe ohjelman suorituksessa (fetch_and_calculate.py): {e}", exc_info=True)
