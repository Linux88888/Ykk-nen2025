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
from collections import Counter

# Loggaustasetukset
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audience_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ominaisuudet
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
START_ID = 3748452
CACHE_DIR = "audience_cache"
OUTPUT_FILE = "audience_data.json"
LAST_ID_FILE = "last_audience_id.txt"

# Varmistetaan hakemistojen olemassaolo
Path(CACHE_DIR).mkdir(exist_ok=True)

def setup_driver(headless=True):
    """Konfiguroi Chrome-selain"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
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
        logger.error(f"Selaimen alustus epäonnistui: {e}")
        try:
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e2:
            logger.critical(f"Kriittinen virhe: {e2}")
            raise

def hae_viimeisin_id():
    """Hae viimeisin käsitelty match ID"""
    try:
        with open(LAST_ID_FILE, 'r') as f:
            sisalto = f.read().strip()
            if sisalto.isdigit():
                return int(sisalto)
    except (FileNotFoundError, ValueError):
        pass
    # Palauta oletusarvo jos tiedostoa ei ole tai se on virheellinen
    return START_ID - 1

def tallenna_viimeisin_id(match_id):
    """Päivitä viimeisin käsitelty match ID"""
    try:
        with open(LAST_ID_FILE, 'w') as f:
            f.write(str(match_id))
    except IOError as e:
        logger.error(f"Virhe tallennettaessa viimeisintä ID:tä: {e}")

def lataa_data():
    """Lataa olemassa oleva data"""
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def tallenna_data(data):
    """Tallenna data JSON-muodossa"""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_valid_stats_page(soup):
    """Tarkista onko sivu validi ottelutilastosivu"""
    # Tarkista useita tunnisteita
    if soup.find('h1', string=re.compile(r'Ottelutilastot', re.I)):
        return True
    if soup.find('table', class_='spl-table'):
        return True
    if len(soup.find_all('div', class_='team-logo')) >= 2:
        return True
    return False

def extract_audience_number(soup):
    """Etsi yleisömäärä eri menetelmillä"""
    # Strategia 1: Etsi suoraan isolla numerolla
    big_number = soup.find(class_=re.compile(r'big-number|stat-value', re.I))
    if big_number:
        try:
            return int(re.sub(r'\D', '', big_number.get_text()))
        except ValueError:
            pass

    # Strategia 2: Etsi taulukosta
    for table in soup.find_all('table'):
        headers = [th.get_text().lower() for th in table.find_all('th')]
        if any(x in ''.join(headers) for x in ['yleisö', 'katsojat']):
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2 and 'yleis' in cells[0].get_text().lower():
                    try:
                        return int(re.sub(r'\D', '', cells[1].get_text()))
                    except ValueError:
                        continue

    # Strategia 3: Etsi tekstistä numeropalat
    text_blocks = soup.find_all(string=re.compile(r'\b(yleis|katsojat|public)\b', re.I))
    for text in text_blocks:
        numbers = re.findall(r'\b\d{3,5}\b', text)
        if numbers:
            try:
                return int(numbers[-1])
            except (ValueError, IndexError):
                continue

    # Strategia 4: Analysoi kaikki suuret numerot
    all_numbers = re.findall(r'\b[1-9]\d{2,4}\b', soup.get_text())
    valid_numbers = [int(n) for n in all_numbers if 100 <= int(n) <= 50000]
    if valid_numbers:
        counts = Counter(valid_numbers)
        return counts.most_common(1)[0][0]

    return None

def fetch_match_data(match_id):
    """Hae yksittäisen ottelun data"""
    url = BASE_URL.format(match_id=match_id)
    logger.info(f"Käsitellään ottelua: {match_id}")
    
    html = None
    try:
        html = fetch_with_selenium(url)
    except Exception as e:
        logger.error(f"Virhe haettaessa ottelua {match_id}: {e}")
        return None
    
    if not html:
        logger.info(f"Sivua ei löytynyt: {match_id}")
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Tallenna raakadata debuggausta varten
    debug_path = os.path.join(CACHE_DIR, f'match_{match_id}_raw.html')
    with open(debug_path, 'w', encoding='utf-8') as f:
        f.write(str(soup.prettify()))
    
    if not is_valid_stats_page(soup):
        logger.info(f"Ei tilastosivua: {match_id}")
        return None
    
    return soup

def paivita_yleisodata():
    """Päivitä kaikki saatavilla olevat yleisömäärät"""
    logger.info("Aloitetaan yleisömäärien haku")
    
    viimeisin_id = hae_viimeisin_id()
    nykyinen_id = viimeisin_id + 1
    yleisodata = lataa_data()
    max_otteluita = 100  # Estä ikuinen looppi
    
    for _ in range(max_otteluita):
        match_data = fetch_match_data(nykyinen_id)
        if not match_data:
            break
        
        yleisomaara = extract_audience_number(match_data)
        otteludata = {
            'ottelu_id': nykyinen_id,
            'yleisomaara': yleisomaara,
            'hakuhetki': datetime.datetime.now().isoformat(),
            'url': BASE_URL.format(match_id=nykyinen_id)
        }
        
        yleisodata.append(otteludata)
        tallenna_viimeisin_id(nykyinen_id)
        nykyinen_id += 1
        
        time.sleep(2)  # Kohtelias viive
    
    tallenna_data(yleisodata)
    logger.info(f"Tallennettu {len(yleisodata)} ottelua")

def fetch_with_selenium(url, attempts=3):
    """Hae sivu Seleniumilla uudelleenyrityksin"""
    driver = None
    for yritys in range(1, attempts+1):
        try:
            driver = setup_driver()
            driver.get(url)
            
            # Odota pääotsikon latautumista
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'h1'))
            )
            
            # Skrollaa ja odota
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            return driver.page_source
        except TimeoutException:
            logger.warning(f"Timeout yrityksellä {yritys}/{attempts}")
        except Exception as e:
            logger.error(f"Virhe yrityksellä {yritys}: {str(e)}")
        finally:
            if driver:
                driver.quit()
        time.sleep(5)
    
    logger.error(f"Kaikki {attempts} yritystä epäonnistuivat: {url}")
    return None

if __name__ == '__main__':
    # Varmista että viimeisin ID-tiedosto on olemassa
    if not os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, 'w') as f:
            f.write(str(START_ID - 1))
    
    try:
        paivita_yleisodata()
        logger.info("Yleisödatapäivitys valmis")
    except Exception as e:
        logger.error(f"Kriittinen virhe: {str(e)}", exc_info=True)
