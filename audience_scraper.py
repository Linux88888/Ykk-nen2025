import os
import re
import time
import json
import logging
import datetime
from pathlib import Path
from collections import Counter

from bs4 import BeautifulSoup
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
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audience_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Asetukset
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
START_ID = 3748452
MAX_MATCHES = 100
REQUEST_DELAY = 2
CACHE_DIR = "audience_cache"
OUTPUT_FILE = "audience_data.json"
LAST_ID_FILE = "last_audience_id.txt"

# Alusta hakemistot
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class AudienceScraper:
    def __init__(self):
        self.driver = None
        self.current_id = self.load_last_id()
        self.audience_data = self.load_data()

    def setup_driver(self):
        """Alusta Selenium WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            raise

    def load_last_id(self):
        """Lataa viimeisin käsitelty ID"""
        try:
            if os.path.exists(LAST_ID_FILE):
                with open(LAST_ID_FILE, 'r') as f:
                    return int(f.read().strip())
            return START_ID - 1
        except Exception as e:
            logger.error(f"Virhe ladattaessa ID:tä: {str(e)}")
            return START_ID - 1

    def save_last_id(self):
        """Tallenna nykyinen ID"""
        try:
            with open(LAST_ID_FILE, 'w') as f:
                f.write(str(self.current_id))
        except Exception as e:
            logger.error(f"Virhe tallennettaessa ID:tä: {str(e)}")

    def load_data(self):
        """Lataa olemassa oleva data"""
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Virhe ladattaessa dataa: {str(e)}")
            return []

    def save_data(self):
        """Tallenna data JSON-muodossa"""
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.audience_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Virhe tallennettaessa dataa: {str(e)}")

    def fetch_page(self, url):
        """Hae sivu Seleniumilla"""
        for attempt in range(3):
            try:
                if not self.driver:
                    self.setup_driver()
                
                self.driver.get(url)
                
                # Odota pääotsikkoa
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'h1'))
                )
                
                # Skrollaa ja odota
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                return self.driver.page_source
                
            except TimeoutException:
                logger.warning(f"Timeout yrityksellä {attempt+1}/3")
            except Exception as e:
                logger.error(f"Virhe sivun haussa: {str(e)}")
            finally:
                time.sleep(1)
        
        logger.error(f"Sivun haku epäonnistui: {url}")
        return None

    def save_debug_files(self, match_id, html, text):
        """Tallenna debug-tiedostot"""
        try:
            # HTML
            html_path = os.path.join(CACHE_DIR, f"{match_id}_page.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            # Teksti
            text_path = os.path.join(CACHE_DIR, f"{match_id}_text.txt")
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)
                
        except Exception as e:
            logger.error(f"Debug-tiedostojen tallennus epäonnistui: {str(e)}")

    def extract_audience(self, soup):
        """Etsi yleisömäärä sivulta"""
        try:
            # Strategia 1: Etsi isolla numerolla
            elements = soup.find_all(class_=re.compile(r'big-number|stat-value', re.I))
            for el in elements:
                text = el.get_text(strip=True)
                if text and text.isdigit():
                    return int(text)
            
            # Strategia 2: Etsi taulukoista
            for table in soup.find_all('table'):
                headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
                if 'yleisö' in headers or 'katsojat' in headers:
                    for row in table.find_all('tr'):
                        cells = [td.get_text(strip=True) for td in row.find_all('td')]
                        if len(cells) >= 2 and ('yleisö' in cells[0].lower() or 'katsojat' in cells[0].lower()):
                            return int(cells[1].replace(' ', ''))
            
            # Strategia 3: Etsi tekstistä
            text = soup.get_text()
            numbers = re.findall(r'\b\d{3,5}\b', text)
            valid = [int(n) for n in numbers if 100 <= int(n) <= 50000]
            if valid:
                return max(valid)
            
            return None
            
        except Exception as e:
            logger.error(f"Virhe analysoinnissa: {str(e)}")
            return None

    def process_match(self, match_id):
        """Prosessoi yksittäinen ottelu"""
        url = BASE_URL.format(match_id=match_id)
        logger.info(f"Käsitellään ottelua {match_id}")
        
        try:
            html = self.fetch_page(url)
            if not html:
                return {'status': 'page_load_failed'}
            
            soup = BeautifulSoup(html, 'html.parser')
            text_content = soup.get_text(separator='\n', strip=True)
            
            # Tallenna debug-tiedostot
            self.save_debug_files(match_id, html, text_content)
            
            # Tarkista validius
            if not self.is_valid_page(soup):
                return {'status': 'invalid_page'}
            
            # Etsi yleisömäärä
            audience = self.extract_audience(soup)
            
            return {
                'status': 'success' if audience else 'no_audience_found',
                'audience': audience
            }
            
        except Exception as e:
            logger.error(f"Kriittinen virhe: {str(e)}")
            return {'status': 'critical_error'}

    def is_valid_page(self, soup):
        """Tarkista onko sivu validi ottelusivu"""
        checks = [
            bool(soup.find('h1', string=re.compile(r'Ottelutilastot', re.I))),
            bool(soup.find('table', class_='spl-table')),
            len(soup.find_all('div', class_='team-logo')) >= 2
        ]
        return any(checks)

    def run(self):
        """Suorita päälogiikka"""
        logger.info("Käynnistetään skraper")
        processed = 0
        
        try:
            self.setup_driver()
            
            while processed < MAX_MATCHES:
                self.current_id += 1
                result = self.process_match(self.current_id)
                
                # Tallenna tulos
                entry = {
                    'match_id': self.current_id,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'url': BASE_URL.format(match_id=self.current_id),
                    **result
                }
                self.audience_data.append(entry)
                
                # Päivitä edistymistä
                processed += 1
                if result['status'] not in ['success', 'no_audience_found']:
                    break
                
                time.sleep(REQUEST_DELAY)
                
        except Exception as e:
            logger.error(f"Päälogiikan virhe: {str(e)}")
        finally:
            if self.driver:
                self.driver.quit()
            self.save_data()
            self.save_last_id()
            logger.info(f"Prosessoitu {processed} ottelua")

if __name__ == '__main__':
    scraper = AudienceScraper()
    scraper.run()
    logger.info("Skrapaus valmis")
