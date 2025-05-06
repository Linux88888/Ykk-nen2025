import os
import re
import time
import json
import logging
import datetime
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

# --- Loggausasetukset ja Globaalit muuttujat ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("match_scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
MAX_MATCHES = 10 # Hakee 10 ID:tä per ajo. Voit nostaa tätä väliaikaisesti, jos haluat nopeuttaa alkukeräystä.
REQUEST_DELAY = 2.5
CACHE_DIR = "scrape_cache"
OUTPUT_FILE = "match_data.json"
LAST_ID_FILE = "last_match_id.txt"
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# --- MatchDataScraper -luokka ---
class MatchDataScraper:
    def __init__(self):
        self.current_id = self.load_last_id()
        self.match_data = self.load_data()

    def setup_driver_local(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--lang=fi-FI")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            'intl.accept_languages': 'fi,fi_FI'
        }
        chrome_options.add_experimental_option('prefs', prefs)
        try:
            # Yritetään asentaa Chromedriver käyttäen Service-objektia, joka on suositeltu tapa
            service = Service(ChromeDriverManager().install(), log_output=os.devnull) # log_output ohjaa driverin lokit pois
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(60) # Pidennetty timeout
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})") # Piilota webdriver-ominaisuus
            logger.debug("Selain alustettu ilman kuvien latausta.")
            return driver
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            # Fallback: Yritetään ilman Service-objektia, jos yllä oleva epäonnistuu
            try:
                logger.info("Yritetään yksinkertaisempaa driverin alustusta...")
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(60)
                logger.debug("Yksinkertaistettu selain alustettu ilman kuvien latausta.")
                return driver
            except Exception as e2:
                logger.critical(f"Driverin alustus epäonnistui täysin: {e2}")
                raise # Heitä virhe eteenpäin, jos kumpikaan ei onnistu

    def fetch_page(self, url):
        driver = None
        last_exception = None
        wait_element_selector = "div.widget-match" # Odotettava elementti, joka indikoi sivun latautumista

        for attempt in range(1, 4): # Yritä enintään 3 kertaa
            try:
                logger.debug(f"fetch_page yritys {attempt}/3 URL: {url}")
                driver = self.setup_driver_local()
                if not driver:
                    raise WebDriverException("Driverin alustus epäonnistui setup_driver_local-metodissa.")

                driver.get(url)
                logger.debug(f"Sivu {url} avattu yrityksellä {attempt}")

                try:
                    logger.debug(f"Odotetaan elementtiä '{wait_element_selector}' enintään 60 sekuntia...")
                    WebDriverWait(driver, 60).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_element_selector))
                    )
                    logger.debug(f"Odotettu elementti '{wait_element_selector}' löytyi.")
                except TimeoutException:
                    page_title = driver.title
                    logger.warning(
                        f"Elementti '{wait_element_selector}' ei löytynyt ajoissa sivulla {url} (Otsikko: {page_title}). "
                        f"Todennäköisesti sivu on tyhjä tai ei sisällä otteludataa. "
                        f"Tarkista {CACHE_DIR}-kansiosta mahdolliset kuvakaappaukset."
                    )
                    # Tallenna kuvakaappaus, jos elementtiä ei löydy
                    screenshot_path = os.path.join(CACHE_DIR, f"{url.split('/')[-2]}_wait_timeout_err.png")
                    try:
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Kuvakaappaus tallennettu (wait timeout): {screenshot_path}")
                    except Exception as ss_err:
                        logger.error(f"Kuvakaappauksen tallennus epäonnistui (wait timeout): {ss_err}")
                    # Ei palauteta None heti, vaan annetaan mahdollisuus jatkaa ja katsoa, onko sivulla silti jotain
                
                time.sleep(2) # Anna dynaamiselle sisällölle lisäaikaa latautua odotuksen jälkeen

                page_source = driver.page_source
                logger.debug(f"Sivun lähdekoodi haettu (pituus: {len(page_source)} merkkiä)")

                if len(page_source) < 10000: # Tarkistus, että sivu ei ole epäilyttävän lyhyt
                    logger.warning(f"Sivu {url} vaikuttaa lyhyeltä (koko: {len(page_source)}), mahdollinen virhe tai data puuttuu.")
                    self.save_debug_files(url.split('/')[-2], page_source, "LYHYT_SIVU") # Tallenna lyhyt sivu debuggausta varten
                    # Ei palauteta None tässä, vaan annetaan extract_data yrittää
                    # return None

                logger.info(f"Sivun {url} haku onnistui yrityksellä {attempt}")
                return page_source

            except (TimeoutException, WebDriverException, NoSuchElementException) as e:
                logger.warning(f"{type(e).__name__} yrityksellä {attempt}/3 haettaessa {url}: {e}")
                last_exception = e
            except Exception as e: # Yleinen poikkeus
                logger.error(f"Yleinen virhe sivun haussa yrityksellä {attempt}/3 ({url}): {type(e).__name__} - {str(e)}", exc_info=True)
                last_exception = e
            finally:
                if driver:
                    logger.debug(f"Suljetaan driver yrityksen {attempt} jälkeen.")
                    driver.quit()
                if attempt < 3: # Jos ei ollut viimeinen yritys
                    wait_time = REQUEST_DELAY + attempt * 3 # Kasvava odotusaika
                    logger.debug(f"Odotetaan {wait_time}s ennen seuraavaa yritystä...")
                    time.sleep(wait_time)
        
        logger.error(f"Sivun {url} haku epäonnistui {attempt} yrityksen jälkeen. Viimeisin virhe: {last_exception}")
        return None

    def save_debug_files(self, match_id, html_content, context_text):
        try:
            match_id_str = str(match_id)
            debug_dir = os.path.join(CACHE_DIR, match_id_str)
            Path(debug_dir).mkdir(parents=True, exist_ok=True)
            
            html_to_write = html_content if html_content else "<!-- HTML content was empty or None -->"
            
            # Poistetaan vanhat vastaavat tiedostot ennen uuden tallennusta
            for old_file in Path(debug_dir).glob(f"{match_id_str}_{context_text}_*.html"):
                old_file.unlink()

            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            html_path = os.path.join(debug_dir, f"{match_id_str}_{context_text}_{timestamp}.html")
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_to_write)
            logger.debug(f"Tallennettu debug HTML: {html_path}")
        except Exception as e:
            logger.error(f"Debug HTML -tiedoston tallennus epäonnistui (ID: {match_id_str}): {e}")


    def load_last_id(self):
        start_id_default = 3748451 # Oletusaloitus ID, jos tiedostoa ei löydy tai se on virheellinen
        try:
            if os.path.exists(LAST_ID_FILE):
                with open(LAST_ID_FILE, 'r') as f:
                    last_id = int(f.read().strip())
                logger.info(f"Ladatty viimeisin ID: {last_id} tiedostosta {LAST_ID_FILE}")
                # Varmistetaan, että ID ei ole negatiivinen
                return max(0, last_id)
            else:
                logger.info(f"Tiedostoa {LAST_ID_FILE} ei löytynyt. Aloitetaan ID:stä {start_id_default -1} (jotta ensimmäinen haettava ID on {start_id_default}).")
                # Palautetaan ID, joka on yhtä pienempi kuin haluttu aloitus ID
                return start_id_default - 1 
        except (ValueError, Exception) as e:
            logger.error(f"Virhe ladattaessa viimeisintä ID:tä tiedostosta {LAST_ID_FILE}: {e}. Aloitetaan ID:stä {start_id_default - 1}.")
            return start_id_default - 1

    def save_last_id(self):
        try:
            with open(LAST_ID_FILE, 'w') as f:
                f.write(str(self.current_id))
            logger.info(f"Tallennettu viimeisin käsitelty ID: {self.current_id} tiedostoon {LAST_ID_FILE}")
        except Exception as e:
            logger.error(f"Virhe tallennettaessa viimeisintä ID:tä ({self.current_id}) tiedostoon {LAST_ID_FILE}: {e}")

    def load_data(self):
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        logger.info(f"Ladatty {len(data)} tietuetta tiedostosta {OUTPUT_FILE}.")
                        return data if isinstance(data, list) else [] # Varmista, että palautetaan lista
                    except json.JSONDecodeError:
                        logger.error(f"Virhe JSON-datan dekoodauksessa tiedostosta {OUTPUT_FILE}. Aloitetaan tyhjästä listasta.")
                        return [] # Palauta tyhjä lista, jos JSON on korruptoitunut
            else:
                logger.info(f"Tiedostoa {OUTPUT_FILE} ei löytynyt, aloitetaan tyhjästä listasta.")
                return []
        except Exception as e: # Yleinen poikkeus
            logger.error(f"Yleinen virhe datan latauksessa tiedostosta {OUTPUT_FILE}: {e}. Aloitetaan tyhjästä listasta.")
            return []

    def save_data(self):
        try:
            # Varmistetaan, että data on lista ennen tallennusta
            if not isinstance(self.match_data, list):
                logger.error(f"Tallennusyritys epäonnistui: self.match_data ei ole lista (tyyppi: {type(self.match_data)}). Ei tallenneta.")
                return

            # Poistetaan duplikaatit ID:n perusteella ennen lopullista tallennusta, pitäen viimeisimmän version
            final_data_map = {}
            for item in self.match_data:
                if isinstance(item, dict) and item.get('match_id') is not None:
                    # Jos ID on jo olemassa, uudempi (myöhemmin listalla oleva) korvaa sen
                    final_data_map[item.get('match_id')] = item 
            
            # Järjestä ID:n mukaan
            sorted_data = sorted(list(final_data_map.values()), key=lambda x: x.get('match_id', 0))

            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Tallennettu {len(sorted_data)} tietuetta tiedostoon {OUTPUT_FILE}.")
        except Exception as e:
            logger.error(f"Virhe tallennettaessa dataa tiedostoon {OUTPUT_FILE}: {e}")
    
    # --- Selektorit ---
    HOME_TEAM_SELECTOR = "a#team_A span.teamname"
    AWAY_TEAM_SELECTOR = "a#team_B span.teamname"
    SCORE_SELECTOR = "div.widget-match-header-score span.score"
    HALF_TIME_SCORE_SELECTOR = "div.widget-match-header-score span.halftime"
    STATUS_SELECTOR = "div.widget-match-header-status span.status-name"
    INFO_BLOCK_SELECTOR = "div.widget-match-info"
    MATCH_DATE_ID_SELECTOR = "span.match-date" # Sisältää myös ottelunumeron
    MATCH_VENUE_TIME_SELECTOR = "span.match-venue" # Sisältää ajan ja paikan
    ATTENDANCE_SELECTOR = "div.widget-match-info-item--attendance span.value"
    FORMATION_SELECTOR = "div.widget-match-info-item--formation span.value"
    MATCH_DURATION_SELECTOR = "div.widget-match-info-item--duration span.value"
    SUBSTITUTIONS_SELECTOR = "div.widget-match-info-item--substitutions span.value"
    WEATHER_SELECTOR = "div.widget-match-info-item--weather span.value"
    AWARD_CONTAINER_SELECTOR = "div.awards-container" # Palkintojen kontti
    AWARD_PLAYER_DIV_SELECTOR = "div.player" # Yksittäisen pelaajan div
    AWARD_LINK_SELECTOR = "a[href*='/pelaaja/']" # Linkki pelaajan profiiliin
    AWARD_SPAN_SELECTOR = "span.name" # Pelaajan nimen sisältävä span
    AWARD_STAR_CONTAINER_SELECTOR = "span.stars" # Tähtien kontti
    AWARD_STAR_ICON_SELECTOR = "i.fa-star" # Tähti-ikoni
    STATS_WRAPPER_SELECTOR = "div.stats-wrapper div.stat" # Yksittäinen tilastorivi
    STATS_NAME_SELECTOR = "div.name"
    STATS_HOME_VALUE_SELECTOR = "div.value-A"
    STATS_AWAY_VALUE_SELECTOR = "div.value-B"
    GOAL_ASSIST_HEADING_SELECTOR = "h3.section-title"
    GOAL_ASSIST_ROW_SELECTOR = "div.row.gutter-12" # Rivi, joka sisältää molempien joukkueiden sarakkeet
    GOAL_ASSIST_COL_SELECTOR = "div.col-md-6" # Yksittäisen joukkueen sarake
    GOAL_ASSIST_TEAM_NAME_SELECTOR = "h3.subsection-title" # Joukkueen nimi sarakkeen sisällä
    GOAL_ASSIST_TABLE_SELECTOR = "table.table-stats" # Tilastotaulukko sarakkeen sisällä
    GOAL_ASSIST_TABLE_BODY_SELECTOR = "tbody"
    GOAL_ASSIST_TABLE_ROW_SELECTOR = "tr" # Pelaajarivi taulukossa
    GOAL_ASSIST_JERSEY_SELECTOR = "td.jersey"
    GOAL_ASSIST_PLAYER_SELECTOR = "td.player a"
    GOAL_ASSIST_CONTRIBUTION_SELECTOR = "td.contribution"

    def extract_events(self, soup, team_id_suffix): # team_id_suffix 'A' tai 'B'
        events = {'goals': [], 'yellow_cards': [], 'red_cards': []}
        try:
            # Maalit
            scorers_container_selector = f"div#scorers_{team_id_suffix} div.football.scorernames"
            scorers_container = soup.select_one(scorers_container_selector)
            if scorers_container:
                scorer_spans = scorers_container.find_all('span', recursive=False) # Vain suorat lapsielementit
                for scorer_span in scorer_spans:
                     scorer_link = scorer_span.find('a', class_='scorer')
                     if scorer_link:
                         player_name = scorer_link.get_text(strip=True)
                         player_href = scorer_link.get('href')
                         time_node = scorer_link.next_sibling # Oletetaan, että aika on heti linkin jälkeen
                         goal_times_str = time_node.strip() if time_node and isinstance(time_node, NavigableString) else ""
                         if player_name and goal_times_str:
                             goal_times = re.findall(r"(\d+'?)", goal_times_str) # Etsii numeroita ja valinnaista heittomerkkiä
                             for time_val in goal_times:
                                 events['goals'].append({'player': player_name, 'time': time_val.replace("'", "") + "'", 'link': player_href})
                                 logger.debug(f"Maali ({team_id_suffix}): {player_name} ({time_val})")

            # Punaiset kortit
            red_card_selector = f"div.redcard_{team_id_suffix} span" # Olettaen että span sisältää nimen ja ajan
            red_card_spans = soup.select(red_card_selector)
            for span in red_card_spans:
                text_content = span.get_text(strip=True)
                # Yritä purkaa nimi ja aika, esim. "Pelaaja Nimi 78'"
                match_obj = re.match(r"(.+)\s+(\d+'?)", text_content)
                if match_obj:
                    player_name = match_obj.group(1).strip()
                    time_str = match_obj.group(2).replace("'", "") + "'" # Varmista heittomerkki
                    events['red_cards'].append({'player': player_name, 'time': time_str})
                    logger.debug(f"Punainen kortti ({team_id_suffix}): {player_name} ({time_str})")

            # Keltaiset kortit
            yellow_card_selector = f"div.yellowcard_{team_id_suffix} span"
            yellow_card_spans = soup.select(yellow_card_selector)
            for span in yellow_card_spans:
                text_content = span.get_text(strip=True)
                match_obj = re.match(r"(.+)\s+(\d+'?)", text_content)
                if match_obj:
                    player_name = match_obj.group(1).strip()
                    time_str = match_obj.group(2).replace("'", "") + "'"
                    events['yellow_cards'].append({'player': player_name, 'time': time_str})
                    logger.debug(f"Keltainen kortti ({team_id_suffix}): {player_name} ({time_str})")

        except Exception as e:
            logger.error(f"Virhe tapahtumien purussa ({team_id_suffix}): {e}", exc_info=True)
        return events

    def extract_data(self, soup, match_id):
        data = {'match_id': match_id, 'match_id_from_page': None}
        logger.debug(f"Aloitetaan datan purku ID:lle {match_id}")

        # Sivun otsikko
        try: data['page_title'] = soup.find('title').get_text(strip=True) if soup.find('title') else None
        except Exception as e: logger.warning(f"Virhe otsikko: {e}"); data['page_title'] = None
        
        # Joukkueet
        try: data['team_home'] = soup.select_one(self.HOME_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(self.HOME_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe kotijoukkue: {e}"); data['team_home'] = None
        try: data['team_away'] = soup.select_one(self.AWAY_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(self.AWAY_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe vierasjoukkue: {e}"); data['team_away'] = None

        # Tulos ja puoliaikatulos
        try: 
            score_el = soup.select_one(self.SCORE_SELECTOR)
            score_text = score_el.get_text(strip=True).replace(" ", "") if score_el else None # Poista välilyönnit
            # Varmista, että tulos sisältää viivan, muuten se ei ole validi tulos
            data['score'] = score_text if score_text and '–' in score_text else None
        except Exception as e: logger.warning(f"Virhe tulos: {e}"); data['score'] = None
        try:
            ht_el = soup.select_one(self.HALF_TIME_SCORE_SELECTOR)
            ht_text = ht_el.get_text(strip=True).replace("(", "").replace(")", "").replace(" ", "") if ht_el else ""
            data['score_halftime'] = ht_text if ht_text and '–' in ht_text else None
        except Exception as e: logger.warning(f"Virhe puoliaikatulos: {e}"); data['score_halftime'] = None
        
        # Ottelun tila
        try:
            status_element = soup.select_one(self.STATUS_SELECTOR)
            data['match_status_raw'] = status_element.get_text(strip=True) if status_element else None
        except Exception as e: logger.warning(f"Virhe ottelun tila: {e}"); data['match_status_raw'] = None

        # Pvm, aika, paikka ja ottelunumero sivulta
        data['match_datetime_raw'] = None
        data['venue'] = None
        date_match_obj = None # Alustetaan, jotta sitä voidaan käyttää myöhemmin

        try:
            info_block = soup.select_one(self.INFO_BLOCK_SELECTOR)
            if info_block:
                # Ottelunumero sivulta
                match_date_el = info_block.select_one(self.MATCH_DATE_ID_SELECTOR)
                if match_date_el:
                    id_match = re.search(r'Ottelu\s+(\d+)', match_date_el.get_text())
                    data['match_id_from_page'] = int(id_match.group(1)) if id_match else None
                
                # Aika ja paikka
                match_venue_el = info_block.select_one(self.MATCH_VENUE_TIME_SELECTOR)
                extracted_datetime_str = None
                venue_text_for_extraction = ""
                venue_raw_text = ""

                if match_venue_el:
                    venue_raw_text = match_venue_el.get_text(strip=True) # Koko teksti ilman separointia
                    venue_text_for_extraction = match_venue_el.get_text(separator='|', strip=True) # Teksti separoitu |
                    logger.debug(f"Raw venue/time text (for datetime extraction): '{venue_text_for_extraction}'")
                    logger.debug(f"Raw venue text (for venue cleanup): '{venue_raw_text}'")

                    # Yritä ensin tarkkaa regexiä ajalle ja päivämäärälle
                    # Olettaa muodon "HH:MM | Viikonpäivä DD.MM." tai "HH:MM | Viikonpäivä DD.MM.YYYY"
                    time_date_match = re.search(r'(\d{1,2}:\d{2})\s*\|\s*([a-zA-ZÄÖÅäöå\s]+\s+\d{1,2}\.\d{1,2}\.?(\d{4})?)', venue_text_for_extraction)
                    if time_date_match:
                        extracted_datetime_str = f"{time_date_match.group(1)} | {time_date_match.group(2).strip().rstrip('.')}"
                        logger.debug(f"Extracted datetime with strict regex: {extracted_datetime_str}")
                        # Otetaan päivämääräosa talteen myöhempää paikan siivousta varten
                        date_match_obj = re.search(r'([a-zA-ZÄÖÅäöå\s]+\s+\d{1,2}\.\d{1,2}\.?(\d{4})?)', time_date_match.group(2).strip())

                    else: # Jos tarkka ei toimi, yritä erillisiä kuvioita
                        logger.debug("Strict regex failed for datetime, trying separate patterns.")
                        time_match = re.search(r'(\d{1,2}:\d{2})', venue_text_for_extraction)
                        # Yritä löytää päivämäärä, joka voi olla muodossa "Viikonpäivä DD.MM." tai "DD.MM.YYYY"
                        date_match_obj = re.search(r'([A-ZÄÖÅa-zäöå]{2,}\s+\d{1,2}\.\d{1,2}\.?(\d{4})?)', venue_text_for_extraction) # Esim. "Tiistai 01.01." tai "Ti 1.1.2024"
                        if not date_match_obj: # Jos edellinen ei löydy, kokeile pelkkää DD.MM.YYYY
                            date_match_obj = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', venue_text_for_extraction)
                        
                        time_str = time_match.group(1) if time_match else "??:??"
                        date_str = date_match_obj.group(1).strip().rstrip('.') if date_match_obj else "Pvm Tuntematon"
                        
                        if time_match or date_match_obj: # Jos edes jompikumpi löytyi
                            extracted_datetime_str = f"{time_str} | {date_str}"
                        else:
                            logger.warning(f"Could not extract time or date from: '{venue_text_for_extraction}'")
                            extracted_datetime_str = None
                        if extracted_datetime_str: logger.debug(f"Extracted datetime with separate patterns: {extracted_datetime_str}")

                    data['match_datetime_raw'] = extracted_datetime_str
                    
                    # Paikan purku
                    venue_link = match_venue_el.find('a') # Onko paikalla linkki?
                    if venue_link:
                        # Yritä ottaa teksti ennen linkkiä ja linkin teksti
                        venue_text_before = venue_link.previous_sibling
                        venue_parts = [
                            venue_text_before.strip() if venue_text_before and isinstance(venue_text_before, NavigableString) else None,
                            venue_link.get_text(strip=True)
                        ]
                        data['venue'] = ', '.join(filter(None, venue_parts))
                        logger.debug(f"Extracted venue using link: {data['venue']}")
                    else: # Jos ei linkkiä, yritä siivota koko venue_raw_text
                        cleaned_venue = venue_raw_text
                        if time_match: # Poista kellonaika, jos löytyi
                            cleaned_venue = cleaned_venue.replace(time_match.group(0), '').strip()
                        if date_match_obj: # Poista päivämäärä, jos löytyi
                            cleaned_venue = cleaned_venue.replace(date_match_obj.group(0), '').strip()
                        # Poista mahdolliset jäljelle jääneet erottimet ja ylimääräiset välilyönnit
                        data['venue'] = cleaned_venue.replace('|','').strip(',').strip()
                        logger.debug(f"Extracted venue by cleaning raw text: {data['venue']}")
            else:
                logger.warning(f"Info block ({self.INFO_BLOCK_SELECTOR}) not found for ID {match_id}")
        except Exception as e:
            logger.error(f"Virhe info blockin (pvm/aika/paikka) purussa: {e}", exc_info=True)

        # Muut tiedot
        data['formation'] = None; data['match_duration_format'] = None; data['substitutions_allowed'] = None; data['weather'] = None; data['audience'] = None;
        try: data['formation'] = soup.select_one(self.FORMATION_SELECTOR).get_text(strip=True) if soup.select_one(self.FORMATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe formation: {e}")
        try: data['match_duration_format'] = soup.select_one(self.MATCH_DURATION_SELECTOR).get_text(strip=True) if soup.select_one(self.MATCH_DURATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe duration format: {e}")
        try: data['substitutions_allowed'] = soup.select_one(self.SUBSTITUTIONS_SELECTOR).get_text(strip=True) if soup.select_one(self.SUBSTITUTIONS_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe substitutions: {e}")
        try: data['weather'] = soup.select_one(self.WEATHER_SELECTOR).get_text(strip=True) if soup.select_one(self.WEATHER_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe weather: {e}")
        try:
            audience_el = soup.select_one(self.ATTENDANCE_SELECTOR)
            audience_text = audience_el.get_text(strip=True) if audience_el else None
            data['audience'] = int(audience_text) if audience_text and audience_text.isdigit() else None # Varmista, että on numero
        except Exception as e: logger.warning(f"Virhe yleisömäärä: {e}")
        
        # Palkinnot
        data['awards'] = []
        try:
             award_container = soup.select_one(self.AWARD_CONTAINER_SELECTOR)
             if award_container:
                  player_divs = award_container.select(self.AWARD_PLAYER_DIV_SELECTOR)
                  for player_div in player_divs:
                    link = player_div.select_one(self.AWARD_LINK_SELECTOR)
                    if link:
                        player_href = link.get('href')
                        player_name = None
                        # Yritä ensin span.name sisällä
                        award_span = link.select_one(self.AWARD_SPAN_SELECTOR);
                        if award_span:
                            crest = award_span.select_one("span.crest"); # Poista mahdollinen crest-spani
                            if crest: crest.extract() 
                            player_name = award_span.get_text(strip=True)
                        
                        # Jos span.name ei tuottanut tulosta tai oli tyhjä, yritä suoraa tekstisisältöä linkistä
                        if not player_name:
                            name_parts = [text.strip() for text in link.find_all(string=True, recursive=False) if text.strip()]
                            player_name = " ".join(name_parts) if name_parts else link.get_text(strip=True) # Fallback koko linkin tekstiin

                        star_count = 0
                        star_container = link.select_one(self.AWARD_STAR_CONTAINER_SELECTOR)
                        star_count = len(star_container.select(self.AWARD_STAR_ICON_SELECTOR)) if star_container else 0
                        
                        if player_name and player_href:
                            data['awards'].append({'player': player_name, 'link': player_href, 'stars': star_count})
                            logger.debug(f"Löytyi palkittu: {player_name} ({star_count} tähteä)")
                        else:
                            logger.warning(f"Ei saatu purettua palkitun nimeä/linkkiä: {link.prettify()}")
        except Exception as e: logger.warning(f"Virhe palkinnot: {e}")

        # Tilastot
        data['stats'] = {}
        try:
            stat_wrappers = soup.select(self.STATS_WRAPPER_SELECTOR)
            logger.debug(f"Löytyi {len(stat_wrappers)} tilasto-wrapperia.")
            for wrapper in stat_wrappers:
                name_el = wrapper.select_one(self.STATS_NAME_SELECTOR)
                home_el = wrapper.select_one(self.STATS_HOME_VALUE_SELECTOR)
                away_el = wrapper.select_one(self.STATS_AWAY_VALUE_SELECTOR)
                if name_el and home_el and away_el:
                    stat_name_raw = name_el.get_text(strip=True)
                    # Siivoa tilaston nimi: poista sulut, pienet kirjaimet, välilyönnit alaviivoiksi, skandit
                    stat_name_clean = re.sub(r'[()]', '', stat_name_raw.lower().replace(" ", "_").replace("ä", "a").replace("ö", "o"))
                    home_val_raw = home_el.get_text(strip=True)
                    away_val_raw = away_el.get_text(strip=True)
                    try: home_val = int(home_val_raw)
                    except ValueError: home_val = home_val_raw # Jätä merkkijonoksi jos ei ole numero
                    try: away_val = int(away_val_raw)
                    except ValueError: away_val = away_val_raw
                    data['stats'][stat_name_clean] = {'home': home_val, 'away': away_val}
                    logger.debug(f"Tilasto: '{stat_name_clean}' Koti: {home_val}, Vieras: {away_val}")
                else:
                    logger.warning(f"Ei voitu purkaa tilastoa tästä wrapperista (puuttuvia elementtejä): {wrapper.prettify()}")
        except Exception as e: logger.error(f"Virhe tilastojen purussa: {e}")

        # Tapahtumat (maalit, kortit) puretaan erikseen
        data['events_from_list'] = {};
        try:
            home_events = self.extract_events(soup, 'A') # Kotijoukkueen ID on usein 'A'
            away_events = self.extract_events(soup, 'B') # Vierasjoukkueen ID on usein 'B'
            data['events_from_list']['home'] = home_events
            data['events_from_list']['away'] = away_events
        except Exception as e:
            logger.error(f"Yllättävä virhe extract_events-kutsussa ID {match_id}: {e}", exc_info=True)
            data['events_from_list'] = {'home': {}, 'away': {}} # Alusta tyhjäksi virhetilanteessa

        # Maalit ja syötöt -taulukko
        data['goal_assist_details'] = {'home': [], 'away': []}
        try:
            heading = soup.find(self.GOAL_ASSIST_HEADING_SELECTOR, string=re.compile(r'Maalit\s+ja\s+syötöt', re.IGNORECASE))
            if heading:
                logger.debug("Löytyi 'Maalit ja syötöt' -otsikko.")
                parent_row = heading.find_next_sibling(self.GOAL_ASSIST_ROW_SELECTOR) # Olettaa, että data on seuraavassa rivielementissä
                if parent_row:
                    cols = parent_row.select(self.GOAL_ASSIST_COL_SELECTOR) # Koti- ja vierasjoukkueen sarakkeet
                    logger.debug(f"Löytyi {len(cols)} saraketta maali/syöttö-datalle.")
                    for col in cols:
                        team_name_h3 = col.select_one(self.GOAL_ASSIST_TEAM_NAME_SELECTOR)
                        team_name = team_name_h3.get_text(strip=True) if team_name_h3 else None
                        team_key = None
                        # Määritä, onko kyseessä koti- vai vierasjoukkue
                        if team_name and data['team_home'] and team_name in data['team_home']: team_key = 'home'
                        elif team_name and data['team_away'] and team_name in data['team_away']: team_key = 'away'
                        else: logger.warning(f"Ei tunnistettu joukkuetta '{team_name}' maali/syöttö-taulukosta."); continue
                        
                        logger.debug(f"Käsitellään maali/syöttö-taulukkoa joukkueelle: {team_name} ({team_key})")
                        table = col.select_one(self.GOAL_ASSIST_TABLE_SELECTOR)
                        if table:
                            tbody = table.select_one(self.GOAL_ASSIST_TABLE_BODY_SELECTOR)
                            if tbody:
                                rows = tbody.select(self.GOAL_ASSIST_TABLE_ROW_SELECTOR)
                                logger.debug(f"Löytyi {len(rows)} pelaajariviä taulukosta ({team_key}).")
                                for row in rows:
                                    jersey_el = row.select_one(self.GOAL_ASSIST_JERSEY_SELECTOR)
                                    player_link_el = row.select_one(self.GOAL_ASSIST_PLAYER_SELECTOR)
                                    contrib_el = row.select_one(self.GOAL_ASSIST_CONTRIBUTION_SELECTOR)
                                    
                                    if jersey_el and player_link_el and contrib_el:
                                        jersey = jersey_el.get_text(strip=True)
                                        player_name = player_link_el.get_text(strip=True)
                                        player_link = player_link_el.get('href')
                                        contrib_str = contrib_el.get_text(strip=True) # Esim. "2+1=3"
                                        
                                        goals, assists, total = 0, 0, 0
                                        contrib_match = re.match(r'(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)', contrib_str)
                                        if contrib_match:
                                            try:
                                                goals = int(contrib_match.group(1))
                                                assists = int(contrib_match.group(2))
                                                total = int(contrib_match.group(3))
                                            except ValueError:
                                                logger.warning(f"Virhe muunnettaessa G+A numeroiksi: {contrib_str}")

                                        player_data = {
                                            'jersey': jersey, 'player': player_name, 'link': player_link, 
                                            'contribution_raw': contrib_str, 'goals': goals, 'assists': assists, 'total_points': total
                                        }
                                        data['goal_assist_details'][team_key].append(player_data)
                                    else:
                                        logger.warning(f"Ei voitu purkaa kaikkia tietoja maali/syöttö-riviltä: {row.prettify()}")
                            else: logger.warning(f"Ei löytynyt tbody-elementtiä maali/syöttö-taulukosta ({team_key}).")
                        else: logger.warning(f"Ei löytynyt table-elementtiä maali/syöttö-sarakkeesta ({team_key}).")
                else: logger.warning("Ei löytynyt rivielementtiä 'Maalit ja syötöt' -otsikon jälkeen.")
            else: logger.debug("Ei löytynyt 'Maalit ja syötöt' -otsikkoa.")
        except Exception as e:
            logger.error(f"Virhe maali/syöttö-taulukon purussa: {e}")

        logger.debug(f"Datan purku valmis ID:lle {match_id}")
        return data

    def process_match(self, match_id):
        url = BASE_URL.format(match_id=match_id)
        logger.info(f"--- Käsittely alkaa: ID {match_id} ({url}) ---")
        scrape_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        result_data = {'match_id': match_id, 'scrape_timestamp': scrape_timestamp, 'status_details': []}

        try:
            html = self.fetch_page(url)
            if not html: # Jos fetch_page palauttaa None, sivu ei latautunut kunnolla
                result_data['status'] = 'page_load_failed'
                result_data['status_details'].append('HTML content was empty after fetch attempts.')
                logger.error(f"HTML-sisältö tyhjä ID:lle {match_id} kaikkien yritysten jälkeen.")
                return result_data # Palauta tässä vaiheessa, ei ole järkeä jatkaa ilman HTML:ää
            
            soup = BeautifulSoup(html, 'html.parser')
            extracted_data = self.extract_data(soup, match_id)
            result_data.update(extracted_data) # Yhdistä purettu data result_data-sanakirjaan

            # Tarkistus ID-epäsuhdalle
            if result_data.get('match_id_from_page') is not None and result_data['match_id_from_page'] != match_id:
                logger.warning(f"ID {match_id} eroaa sivulta löydetystä ID:stä {result_data['match_id_from_page']}")
                result_data['status_details'].append('match_id_mismatch')

            # Tilamääritys
            raw_status_value = result_data.get('match_status_raw')
            raw_status = raw_status_value.lower() if isinstance(raw_status_value, str) else ''
            score_value = result_data.get('score') or '' # Varmista, ettei ole None

            if 'päättynyt' in raw_status:
                result_data['status'] = 'success_finished' if result_data.get('team_home') else 'success_finished_partial'
            elif 'ei alkanut' in raw_status:
                result_data['status'] = 'success_not_started'
            elif 'käynnissä' in raw_status or ('–' in score_value and ':' not in score_value) : # Käynnissä tai jos tulos on esim "1 – 0" ilman aikaa
                result_data['status'] = 'success_live'
            elif result_data.get('team_home'): # Jos joukkueet löytyy, mutta tila epäselvä
                result_data['status'] = 'success_data_found_unknown_state'
            elif result_data.get('page_title') and 'Tulospalvelu' in result_data.get('page_title'): # Jos sivu on tulospalvelun sivu, mutta dataa vähän
                result_data['status'] = 'success_partial_data' # Esim. tyhjä ottelusivu
            else: # Muuten oletetaan, että parsiminen epäonnistui
                result_data['status'] = 'parsing_failed_no_data'
                result_data['status_details'].append('No meaningful data extracted.')
            
            # Lisätarkistus: jos status on success, mutta oleellista dataa puuttuu
            if result_data['status'].startswith('success') and not (result_data.get('team_home') and result_data.get('score') and result_data.get('stats')):
                 if result_data['status'] != 'success_not_started': # Ei varoiteta jos ottelu ei ole alkanut
                    logger.warning(f"Vaikka status on '{result_data['status']}', oleellista dataa (joukkueet/tulos/tilastot) puuttuu ID:llä {match_id}.")
                    result_data['status_details'].append('missing_core_data')
                 else:
                    logger.info(f"Ottelu {match_id} ei ole alkanut, core data puuttuu odotetusti.")


            logger.info(f"Käsittely valmis: ID {match_id}. Tila: {result_data.get('status')}, Yleisö: {result_data.get('audience')}, Tulos: {result_data.get('score')}, Tilastoja: {len(result_data.get('stats', {}))}")
            events_home = result_data.get('events_from_list', {}).get('home', {})
            events_away = result_data.get('events_from_list', {}).get('away', {})
            logger.info(f"  Tapahtumat (G/Y/R): Koti={len(events_home.get('goals',[]))}/{len(events_home.get('yellow_cards',[]))}/{len(events_home.get('red_cards',[]))}, Vieras={len(events_away.get('goals',[]))}/{len(events_away.get('yellow_cards',[]))}/{len(events_away.get('red_cards',[]))}")
            return result_data
        except Exception as e:
            logger.exception(f"Kriittinen virhe käsiteltäessä ID {match_id}: {e}")
            result_data['status'] = 'critical_error_processing'
            result_data['error_message'] = str(e)
            return result_data

    def run(self):
        logger.info(f"Skraperi käynnistyy. Aloitus ID (seuraava haettava): {self.current_id + 1}, Max ID:t tälle ajolle: {MAX_MATCHES}")
        processed_count = 0
        success_count = 0
        failed_count = 0
        start_time = time.time()

        # Luo joukko olemassa olevista ID:istä nopeampaa tarkistusta varten
        existing_ids = {match.get('match_id') for match in self.match_data if isinstance(match,dict) and match.get('match_id') is not None}

        try:
            while processed_count < MAX_MATCHES:
                # Varmistetaan, että current_id ei ole negatiivinen (voi tapahtua jos last_id.txt on tyhjä ja oletus -1)
                if self.current_id < 0: self.current_id = 0 

                next_id = self.current_id + 1
                logger.info(f"Käsitellään {processed_count + 1}/{MAX_MATCHES} : ID {next_id}")
                
                result = self.process_match(next_id)
                processed_count += 1

                if isinstance(result, dict): # Varmista, että saatiin sanakirja takaisin
                    # Etsi, onko tämä ID jo datassa
                    existing_index = -1
                    for i, existing_item in enumerate(self.match_data):
                        if isinstance(existing_item, dict) and existing_item.get('match_id') == result.get('match_id'):
                            existing_index = i
                            break
                    
                    if existing_index != -1: # Jos ID löytyi, päivitä se
                        logger.info(f"Päivitetään olemassa oleva data ID:lle {result.get('match_id')}")
                        self.match_data[existing_index] = result
                    else: # Jos ID on uusi, lisää se listaan
                        self.match_data.append(result)
                        existing_ids.add(result.get('match_id')) # Lisää myös settiin

                    if result.get('status', '').startswith('success'):
                        success_count += 1
                    else:
                        failed_count += 1
                else: # Jos process_match ei palauttanut sanakirjaa (epätodennäköistä, mutta varmuuden vuoksi)
                    logger.error(f"process_match palautti virheellisen tyypin ({type(result)}) ID:lle {next_id}. Ohitetaan tallennus.")
                    # Lisätään virheellinen tulos vain jos ID:tä ei jo ole, jotta ei luoda duplikaatteja virheistä
                    error_result = {'match_id': next_id, 'status': 'internal_error_invalid_result_type', 'scrape_timestamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
                    if next_id not in existing_ids:
                         self.match_data.append(error_result)
                         existing_ids.add(next_id)
                    failed_count += 1
                
                self.current_id = next_id # Siirry seuraavaan ID:hen vasta onnistuneen käsittelyn jälkeen

                # Välitallennus joka 10. ID:n jälkeen tai jos MAX_MATCHES on 1 (testausta varten)
                if MAX_MATCHES == 1 or processed_count % 10 == 0:
                    logger.info(f"Välitallennus {processed_count} ID:n jälkeen...")
                    self.save_data()
                    self.save_last_id() # Tallenna viimeisin KÄSITELTY ID
                    logger.info(f"Tallennettu. Viimeisin käsitelty ID: {self.current_id}")

                if processed_count < MAX_MATCHES: # Pieni tauko ennen seuraavaa, jos ei olla vielä valmiita
                    time.sleep(REQUEST_DELAY)
        
        except KeyboardInterrupt:
            logger.warning("Käyttäjä keskeytti suorituksen (KeyboardInterrupt).")
        except Exception as e:
            logger.exception(f"Odottamaton virhe pääsilmukassa: {e}")
        finally:
            logger.info("Tallennetaan lopulliset tiedot ennen lopetusta...")
            # Siivotaan ja järjestetään data ennen lopullista tallennusta
            # Tämä poistaa duplikaatit ID:n perusteella, pitäen viimeisimmän version, ja järjestää
            final_data = {}
            for item in self.match_data:
                if isinstance(item, dict) and item.get('match_id') is not None:
                    final_data[item.get('match_id')] = item # Uudempi korvaa vanhemman, jos sama ID
            
            self.match_data = sorted(list(final_data.values()), key=lambda x: x.get('match_id', 0))

            self.save_data()
            self.save_last_id() # Tallenna lopullinen käsitelty ID
            duration = time.time() - start_time
            logger.info(f"--- Skrapaus valmis --- Kesto: {duration:.2f}s")
            logger.info(f"Yritetty käsitellä (uutta/päivitettyä): {processed_count}, Onnistuneita: {success_count}, Epäonnistuneita: {failed_count}")

# --- Pääsuoritus ---
if __name__ == '__main__':
    scraper = MatchDataScraper()
    scraper.run()
    logger.info("Skraperin suoritus päättyi.")
