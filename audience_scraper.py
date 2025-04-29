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

def fetch_with_selenium(url, attempts=3):
    """Hae sivu Seleniumilla"""
    driver = None
    for yritys in range(1, attempts + 1):
        try:
            driver = setup_driver()
            logger.info(f"Yritetään hakea ({yritys}/{attempts}): {url}")
            driver.get(url)
            
            time.sleep(5)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            page_source = driver.page_source
            
            if len(page_source) < 1000 or "Error" in page_source[:500]:
                logger.warning(f"Sivu saattaa olla virheellinen ({len(page_source)} tavua)")
                if yritys < attempts:
                    time.sleep(5)
                    continue
            
            return page_source
        except Exception as e:
            logger.error(f"Selenium-virhe yrityksellä {yritys}: {e}")
            if yritys < attempts:
                time.sleep(5)
        finally:
            if driver:
                driver.quit()
    
    logger.error(f"Kaikki {attempts} yritystä epäonnistuivat: {url}")
    return None

def is_valid_stats_page(soup):
    """Tarkista onko sivu validi ottelusivu"""
    stats_table = soup.find('table', class_='spl-table')
    if stats_table:
        return True
    
    otsikko = soup.find('h1', string=re.compile(r'Ottelutilastot', re.IGNORECASE))
    if otsikko:
        return True
    
    joukkueet = soup.find_all('span', class_='team-name')
    return len(joukkueet) >= 2

def extract_audience_number(soup):
    """Etsi yleisömäärä sivulta"""
    haettavat = [r'Yleisöä', r'Katsojat', r'Attendance', r'yleisö']
    
    for malli in haettavat:
        elementti = soup.find(string=re.compile(malli, re.IGNORECASE))
        if elementti:
            # Etsitään taulukkoriviltä
            rivi = elementti.find_parent('tr')
            if rivi:
                solut = rivi.find_all('td')
                if len(solut) >= 2:
                    arvo = solut[1].get_text().strip()
                    try:
                        return int(arvo.replace(' ', ''))
                    except ValueError:
                        continue
            
            # Etsitään div-elementistä
            div = elementti.find_parent('div')
            if div:
                arvo_elementti = div.find(class_='value')
                if arvo_elementti:
                    try:
                        return int(arvo_elementti.get_text().strip().replace(' ', ''))
                    except ValueError:
                        continue
                
                seuraava = elementti.find_next_sibling()
                if seuraava:
                    try:
                        return int(seuraava.get_text().strip().replace(' ', ''))
                    except ValueError:
                        continue
    return None

def hae_viimeisin_id():
    try:
        with open(LAST_ID_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return START_ID - 1

def tallenna_viimeisin_id(match_id):
    with open(LAST_ID_FILE, 'w') as f:
        f.write(str(match_id))

def lataa_data():
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def tallenna_data(data):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def paivita_yleisodata():
    logger.info("Aloitetaan yleisömäärien haku")
    
    viimeisin_id = hae_viimeisin_id()
    nykyinen_id = viimeisin_id + 1
    yleisodata = lataa_data()
    
    while True:
        url = BASE_URL.format(match_id=nykyinen_id)
        logger.info(f"Käsitellään ottelua: {nykyinen_id}")
        
        html = fetch_with_selenium(url)
        if not html:
            logger.info(f"Sivua ei löytynyt: {nykyinen_id}, lopetetaan.")
            break
        
        soup = BeautifulSoup(html, 'html.parser')
        if not is_valid_stats_page(soup):
            logger.info(f"Virheellinen ottelusivu: {nykyinen_id}, lopetetaan.")
            break
        
        yleisomaara = extract_audience_number(soup)
        if yleisomaara is not None:
            logger.info(f"Löytyi yleisöä: {yleisomaara} (ottelu {nykyinen_id})")
            yleisodata.append({
                'ottelu_id': nykyinen_id,
                'yleisomaara': yleisomaara,
                'hakuhetki': datetime.datetime.now().isoformat()
            })
            tallenna_viimeisin_id(nykyinen_id)
            nykyinen_id += 1
        else:
            logger.warning(f"Yleisömäärää ei löytynyt: {nykyinen_id}, lopetetaan.")
            break
    
    tallenna_data(yleisodata)
    logger.info(f"Tallennettu data tiedostoon {OUTPUT_FILE}")

if __name__ == '__main__':
    paivita_yleisodata()
