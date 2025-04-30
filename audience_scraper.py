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

# Loggaustasetukset
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("match_scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Asetukset
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
MAX_MATCHES = 100
REQUEST_DELAY = 2.5
CACHE_DIR = "scrape_cache"
OUTPUT_FILE = "match_data.json"
LAST_ID_FILE = "last_match_id.txt"

Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class MatchDataScraper:
    def __init__(self):
        self.current_id = self.load_last_id()
        self.match_data = self.load_data()

    def setup_driver_local(self):
        """Alusta Selenium WebDriver"""
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
        chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'fi,fi_FI'})

        try:
            service = Service(ChromeDriverManager().install(), log_output=os.devnull)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(60)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            try: # Fallback
                logger.info("Yritetään yksinkertaisempaa driverin alustusta...")
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(60)
                return driver
            except Exception as e2: logger.critical(f"Driverin alustus epäonnistui täysin: {e2}"); raise

    def load_last_id(self):
        start_id_default = 1
        try:
            if os.path.exists(LAST_ID_FILE):
                with open(LAST_ID_FILE, 'r') as f: last_id = int(f.read().strip()); logger.info(f"Ladatty viimeisin ID: {last_id}"); return max(0, last_id)
            logger.info(f"Ei {LAST_ID_FILE}-tiedostoa, aloitetaan ID:stä {start_id_default -1 }."); return start_id_default - 1
        except (ValueError, Exception) as e: logger.error(f"Virhe ladattaessa ID:tä: {e}"); return start_id_default - 1

    def save_last_id(self):
        try:
            with open(LAST_ID_FILE, 'w') as f: f.write(str(self.current_id))
        except Exception as e: logger.error(f"Virhe tallennettaessa ID:tä: {e}")

    def load_data(self):
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    try: data = json.load(f); logger.info(f"Ladatty {len(data)} tietuetta."); return data if isinstance(data, list) else []
                    except json.JSONDecodeError: logger.error(f"Virhe JSON-datan latauksessa."); return []
            logger.info(f"Ei {OUTPUT_FILE}-tiedostoa, aloitetaan tyhjästä."); return []
        except Exception as e: logger.error(f"Yleinen virhe datan latauksessa: {e}"); return []

    def save_data(self):
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f: json.dump(self.match_data, f, ensure_ascii=False, indent=2)
        except Exception as e: logger.error(f"Virhe tallennettaessa dataa: {e}")

    def fetch_page(self, url):
        driver = None
        last_exception = None
        wait_element_selector = "div#matchstatus" # Odota ottelun status-diviä

        for attempt in range(1, 4):
            try:
                logger.debug(f"fetch_page yritys {attempt}/3 URL: {url}")
                driver = self.setup_driver_local()
                if not driver: raise WebDriverException("Driverin alustus epäonnistui.")

                driver.get(url)
                logger.debug(f"Sivu {url} avattu yrityksellä {attempt}")

                try:
                    logger.debug(f"Odotetaan elementtiä '{wait_element_selector}' enintään 45 sekuntia...")
                    WebDriverWait(driver, 45).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_element_selector))
                    )
                    logger.debug(f"Odotettu elementti '{wait_element_selector}' löytyi.")
                except TimeoutException:
                    page_title = driver.title
                    logger.warning(f"Elementti '{wait_element_selector}' ei löytynyt ajoissa sivulla {url} (Otsikko: {page_title}). Yritetään jatkaa.")
                    screenshot_path = os.path.join(CACHE_DIR, f"{url.split('/')[-2]}_timeout_err.png")
                    try: driver.save_screenshot(screenshot_path); logger.info(f"Kuvakaappaus tallennettu: {screenshot_path}")
                    except Exception as ss_err: logger.error(f"Kuvakaappauksen tallennus epäonnistui: {ss_err}")


                time.sleep(4)
                logger.debug("Skrollataan sivun alaosaan...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                page_source = driver.page_source
                logger.debug(f"Sivun lähdekoodi haettu (pituus: {len(page_source)} merkkiä)")

                if len(page_source) < 20000:
                     logger.warning(f"Sivu {url} vaikuttaa lyhyeltä (koko: {len(page_source)}), mahdollinen virhe tai data puuttuu.")
                     self.save_debug_files(url.split('/')[-2], page_source, "LYHYT_SIVU")
                     return None

                logger.info(f"Sivun {url} haku onnistui yrityksellä {attempt}")
                return page_source

            except (TimeoutException, WebDriverException, NoSuchElementException) as e:
                logger.warning(f"{type(e).__name__} yrityksellä {attempt}/3 haettaessa {url}: {e}")
                last_exception = e
            except Exception as e:
                logger.error(f"Yleinen virhe sivun haussa yrityksellä {attempt}/3 ({url}): {type(e).__name__} - {str(e)}")
                last_exception = e
            finally:
                if driver: logger.debug(f"Suljetaan driver yrityksen {attempt} jälkeen."); driver.quit()
                if attempt < 3: wait_time = REQUEST_DELAY + attempt * 3; logger.debug(f"Odotetaan {wait_time}s..."); time.sleep(wait_time)

        logger.error(f"Sivun {url} haku epäonnistui 3 yrityksen jälkeen. Virhe: {last_exception}")
        return None

    def save_debug_files(self, match_id, html_content, context_text):
        try:
            match_id_str = str(match_id); debug_dir = os.path.join(CACHE_DIR, match_id_str); Path(debug_dir).mkdir(parents=True, exist_ok=True)
            html_path = os.path.join(debug_dir, f"{match_id_str}_{context_text}_debug.html")
            with open(html_path, 'w', encoding='utf-8') as f: f.write(str(html_content))
            logger.debug(f"Tallennettu debug HTML: {html_path}")
        except Exception as e: logger.error(f"Debug HTML tallennus epäonnistui (ID: {match_id_str}): {e}")

    def extract_events(self, soup, team_id_suffix):
        """Pura maalit ja kurinpitotapahtumat tietylle joukkueelle (A tai B)."""
        events = {'goals': [], 'yellow_cards': [], 'red_cards': []}

        # Maalit
        scorers_container_selector = f"div#scorers_{team_id_suffix} div.football.scorernames"
        scorers_container = soup.select_one(scorers_container_selector)
        if scorers_container:
            scorer_spans = scorers_container.find_all('span', recursive=False)
            for scorer_span in scorer_spans:
                 scorer_link = scorer_span.find('a', class_='scorer')
                 if scorer_link:
                      player_name = scorer_link.get_text(strip=True)
                      player_href = scorer_link.get('href')
                      time_node = scorer_link.next_sibling
                      goal_times_str = time_node.strip() if time_node and isinstance(time_node, NavigableString) else None

                      if player_name and goal_times_str:
                           goal_times = re.findall(r"(\d+'?)", goal_times_str)
                           for time_val in goal_times: # Nimeä muuttuja uudelleen
                                events['goals'].append({
                                    'player': player_name,
                                    'time': time_val.replace("'", "") + "'",
                                    'link': player_href
                                })
                                logger.debug(f"Löytyi maali ({team_id_suffix}): {player_name} {time_val}'")

        # Punaiset kortit
        red_card_selector = f"div.redcard_{team_id_suffix} span"
        red_card_spans = soup.select(red_card_selector)
        for span in red_card_spans:
             text_content = span.get_text(strip=True)
             match = re.match(r"(.+)\s+(\d+'?)", text_content)
             if match:
                  player_name = match.group(1).strip()
                  time_str = match.group(2).replace("'", "") + "'"
                  events['red_cards'].append({'player': player_name, 'time': time_str})
                  logger.debug(f"Löytyi punainen kortti ({team_id_suffix}): {player_name} {time_str}")

        # Keltaiset kortit (OLETUS/ARVAUS - TARKISTA TÄMÄ!)
        yellow_card_selector = f"div.yellowcard_{team_id_suffix} span" # TARKISTA TÄMÄ VALITSIN
        yellow_card_spans = soup.select(yellow_card_selector)
        for span in yellow_card_spans:
             text_content = span.get_text(strip=True)
             match = re.match(r"(.+)\s+(\d+'?)", text_content)
             if match:
                  player_name = match.group(1).strip()
                  time_str = match.group(2).replace("'", "") + "'"
                  events['yellow_cards'].append({'player': player_name, 'time': time_str})
                  logger.debug(f"Löytyi keltainen kortti ({team_id_suffix}): {player_name} {time_str}")

        return events


    def extract_data(self, soup, match_id):
        """Pura keskeiset tiedot ottelusivulta käyttäen päivitettyjä valitsimia."""
        data = {'match_id': match_id, 'match_id_from_page': None}
        logger.debug(f"Aloitetaan datan purku ID:lle {match_id}")

        # === VALITSIMET (Päivitetty kuvien 2-10 perusteella, TARKISTA *-merkityt) ===
        HOME_TEAM_SELECTOR = "a#team_A span.teamname"
        AWAY_TEAM_SELECTOR = "a#team_B span.teamname"
        SCORE_SELECTOR = "span.info_result"
        HALF_TIME_SCORE_SELECTOR = "div.widget-match__score-halftime"                 # *ARVAUS/EI KUVASSA - TARKISTA*
        STATUS_SELECTOR = "div#matchstatus span"
        INFO_BLOCK_SELECTOR = "div#timeandvenue"
        MATCH_DATE_ID_SELECTOR = "span.matchdate"
        MATCH_VENUE_TIME_SELECTOR = "span.matchvenue"
        # Info Snippets (Kuva 10)
        FORMATION_SELECTOR = "span.infosnippet.players"
        MATCH_DURATION_SELECTOR = "span.infosnippet.matchtim"
        SUBSTITUTIONS_SELECTOR = "span.infosnippet.substitutions"
        WEATHER_SELECTOR = "span.infosnippet.weather"
        ATTENDANCE_SELECTOR = "span.infosnippet.attendance"                           # VAHVISTETTU YLEISÖVALITSIN
        # Awards (Kuva 10)
        AWARD_CONTAINER_SELECTOR = "div.infosnippetaward"
        AWARD_LINK_SELECTOR = "a[href*='/person/']" # Etsi linkit kontin sisältä
        # Tilastot (Edelleen arvauksia)
        STATS_CONTAINER_SELECTOR = "div.widget-match-stats__container"                # *ARVAUS/EI KUVASSA - TARKISTA*
        STAT_ROW_SELECTOR = "div.widget-match-stats__item"                            # *ARVAUS/EI KUVASSA - TARKISTA*
        STAT_NAME_SELECTOR = ".widget-match-stats__item-label"                        # *ARVAUS/EI KUVASSA - TARKISTA*
        STAT_HOME_VALUE_SELECTOR = ".widget-match-stats__item-value--side-left"       # *ARVAUS/EI KUVASSA - TARKISTA*
        STAT_AWAY_VALUE_SELECTOR = ".widget-match-stats__item-value--side-right"      # *ARVAUS/EI KUVASSA - TARKISTA*
        # === VALITSIMET LOPPUU ===

        # --- Perustiedot ---
        try: data['page_title'] = soup.find('title').get_text(strip=True) if soup.find('title') else None
        except Exception as e: logger.warning(f"Virhe otsikko: {e}"); data['page_title'] = None

        # --- Joukkueet ---
        try: data['team_home'] = soup.select_one(HOME_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(HOME_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe kotijoukkue: {e}"); data['team_home'] = None
        try: data['team_away'] = soup.select_one(AWAY_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(AWAY_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe vierasjoukkue: {e}"); data['team_away'] = None

        # --- Tulos ---
        try:
            score_el = soup.select_one(SCORE_SELECTOR)
            score_text = score_el.get_text(strip=True).replace(" ", "") if score_el else None
            data['score'] = score_text if score_text and '–' in score_text else None
        except Exception as e: logger.warning(f"Virhe tulos: {e}"); data['score'] = None
        # --- Puoliaikatulos (ARVAUS) ---
        try:
            ht_el = soup.select_one(HALF_TIME_SCORE_SELECTOR) # TARKISTA TÄMÄ VALITSIN
            ht_text = ht_el.get_text(strip=True).replace("(", "").replace(")", "").replace(" ", "") if ht_el else ""
            data['score_halftime'] = ht_text if ht_text else None
        except Exception as e: logger.warning(f"Virhe puoliaikatulos: {e}"); data['score_halftime'] = None

        # --- Ottelun tila ---
        try: data['match_status_raw'] = soup.select_one(STATUS_SELECTOR).get_text(strip=True) if soup.select_one(STATUS_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe ottelun tila: {e}"); data['match_status_raw'] = None

        # --- Info Block (Aika, Pvm, Paikka, ID sivulta) ---
        data['match_datetime_raw'] = None; data['venue'] = None;
        try:
            info_block = soup.select_one(INFO_BLOCK_SELECTOR)
            if info_block:
                match_date_el = info_block.select_one(MATCH_DATE_ID_SELECTOR)
                if match_date_el:
                     id_match = re.search(r'Ottelu\s+(\d+)', match_date_el.get_text())
                     if id_match: data['match_id_from_page'] = int(id_match.group(1))

                match_venue_el = info_block.select_one(MATCH_VENUE_TIME_SELECTOR)
                if match_venue_el:
                     time_date_match = re.search(r'(\d{1,2}:\d{2})\s*\|\s*([a-zA-Z]{1,3}\s+\d{1,2}\.\d{1,2}\.?)', match_venue_el.get_text(separator='|', strip=True))
                     if time_date_match:
                          data['match_datetime_raw'] = f"{time_date_match.group(1)} | {time_date_match.group(2)}"

                     venue_link = match_venue_el.find('a')
                     if venue_link:
                          venue_text_before = venue_link.previous_sibling
                          venue_parts = [venue_text_before.strip() if venue_text_before and isinstance(venue_text_before, NavigableString) else None,
                                         venue_link.get_text(strip=True)]
                          data['venue'] = ', '.join(filter(None, venue_parts))
                     else:
                          full_venue_text = match_venue_el.get_text(strip=True)
                          if data['match_datetime_raw']:
                               cleaned_venue = full_venue_text.replace(data['match_datetime_raw'].split('|')[0].strip(), '').replace(data['match_datetime_raw'].split('|')[1].strip(), '').replace('|','').strip(',').strip()
                               data['venue'] = cleaned_venue if cleaned_venue else None
                          else: data['venue'] = full_venue_text

        except Exception as e: logger.warning(f"Virhe info block: {e}")

        # --- Info Snippets (Kuva 10) ---
        data['formation'] = None; data['match_duration_format'] = None; data['substitutions_allowed'] = None; data['weather'] = None; data['audience'] = None;
        try: data['formation'] = soup.select_one(FORMATION_SELECTOR).get_text(strip=True) if soup.select_one(FORMATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe formation: {e}")
        try: data['match_duration_format'] = soup.select_one(MATCH_DURATION_SELECTOR).get_text(strip=True) if soup.select_one(MATCH_DURATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe duration format: {e}")
        try: data['substitutions_allowed'] = soup.select_one(SUBSTITUTIONS_SELECTOR).get_text(strip=True) if soup.select_one(SUBSTITUTIONS_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe substitutions: {e}")
        try: data['weather'] = soup.select_one(WEATHER_SELECTOR).get_text(strip=True) if soup.select_one(WEATHER_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe weather: {e}")
        # --- Yleisömäärä (VAHVISTETTU VALITSIN Kuva 10) ---
        try:
             audience_el = soup.select_one(ATTENDANCE_SELECTOR)
             audience_text = audience_el.get_text(strip=True) if audience_el else None
             if audience_text and audience_text.isdigit(): data['audience'] = int(audience_text)
        except Exception as e: logger.warning(f"Virhe yleisömäärä (uusi valitsin): {e}")

        # --- Palkinnot / Tähdet (Kuva 10) ---
        data['awards'] = []
        try:
             award_container = soup.select_one(AWARD_CONTAINER_SELECTOR)
             if award_container:
                  award_links = award_container.select(AWARD_LINK_SELECTOR)
                  for link in award_links:
                       player_name = link.get_text(strip=True)
                       player_href = link.get('href')
                       if player_name and player_href:
                            data['awards'].append({'player': player_name, 'link': player_href})
                            logger.debug(f"Löytyi palkittu pelaaja: {player_name}")
        except Exception as e: logger.warning(f"Virhe palkinnot: {e}")


        # --- Tilastot (ARVAUS) ---
        data['stats'] = {}
        try:
            stats_container = soup.select_one(STATS_CONTAINER_SELECTOR) # TARKISTA TÄMÄ
            if stats_container:
                 rows = stats_container.select(STAT_ROW_SELECTOR) # TARKISTA TÄMÄ
                 for row in rows:
                      name_el = row.select_one(STAT_NAME_SELECTOR) # TARKISTA
                      home_el = row.select_one(STAT_HOME_VALUE_SELECTOR) # TARKISTA
                      away_el = row.select_one(STAT_AWAY_VALUE_SELECTOR) # TARKISTA
                      if name_el and home_el and away_el:
                           stat_name = name_el.get_text(strip=True).lower().replace(" ", "_")
                           # Yritä muuttaa numeroiksi jos mahdollista
                           try: home_val = int(home_el.get_text(strip=True))
                           except ValueError: home_val = home_el.get_text(strip=True)
                           try: away_val = int(away_el.get_text(strip=True))
                           except ValueError: away_val = away_el.get_text(strip=True)
                           data['stats'][stat_name] = {'home': home_val, 'away': away_val}
        except Exception as e: logger.warning(f"Virhe tilastot: {e}")

        # --- Tapahtumat (Maalit, Kortit) ---
        try:
             home_events = self.extract_events(soup, 'A')
             away_events = self.extract_events(soup, 'B')
             data['goals_home'] = home_events['goals']
             data['goals_away'] = away_events['goals']
             data['yellow_cards_home'] = home_events['yellow_cards'] # TARKISTA NÄIDEN TOIMIVUUS
             data['yellow_cards_away'] = away_events['yellow_cards'] # TARKISTA NÄIDEN TOIMIVUUS
             data['red_cards_home'] = home_events['red_cards']
             data['red_cards_away'] = away_events['red_cards']
        except Exception as e:
             logger.error(f"Virhe tapahtumien purussa ID {match_id}: {e}")
             data.update({'goals_home': [], 'goals_away': [], 'yellow_cards_home': [], 'yellow_cards_away': [], 'red_cards_home': [], 'red_cards_away': []})


        logger.debug(f"Datan purku valmis ID:lle {match_id}")
        return data

    def process_match(self, match_id):
        """Prosessoi yksittäinen ottelu."""
        url = BASE_URL.format(match_id=match_id)
        logger.info(f"--- Käsittely alkaa: ID {match_id} ({url}) ---")
        scrape_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
        result_data = {'match_id': match_id, 'url': url, 'scrape_timestamp': scrape_timestamp, 'status': 'unknown'}

        try:
            html = self.fetch_page(url)
            if not html: result_data['status'] = 'page_load_failed'; return result_data

            self.save_debug_files(match_id, html, "FETCH_SUCCESS")
            soup = BeautifulSoup(html, 'html.parser')
            extracted_data = self.extract_data(soup, match_id)
            result_data.update(extracted_data)

            if result_data.get('match_id_from_page') is not None and result_data['match_id_from_page'] != match_id:
                 logger.warning(f"ID {match_id} eroaa sivulta löydetystä ID:stä {result_data['match_id_from_page']}!")
                 result_data.setdefault('status_details', []).append('id_mismatch') # Lisää listaan

            raw_status = result_data.get('match_status_raw', '').lower()
            if 'päättynyt' in raw_status: result_data['status'] = 'success_finished' if result_data.get('team_home') else 'success_finished_partial'
            elif 'ei alkanut' in raw_status: result_data['status'] = 'success_not_started'
            elif 'käynnissä' in raw_status or ':' in result_data.get('score',''): result_data['status'] = 'success_live'
            elif result_data.get('team_home'): result_data['status'] = 'success_data_found_unknown_state'
            elif result_data.get('page_title') and 'Tulospalvelu' in result_data.get('page_title'): result_data['status'] = 'success_partial_data'
            else: result_data['status'] = 'parsing_failed_no_data'

            # Tarkista onko oleellista dataa purettu
            if result_data['status'].startswith('success') and not result_data.get('team_home') and not result_data.get('score'):
                logger.warning(f"Vaikka status on '{result_data['status']}', oleellista dataa (joukkueet/tulos) puuttuu ID:llä {match_id}.")
                result_data.setdefault('status_details', []).append('missing_core_data')


            logger.info(f"Käsittely valmis: ID {match_id}. Tila: {result_data.get('status')}, Yleisö: {result_data.get('audience')}, Tulos: {result_data.get('score')}, Sää: {result_data.get('weather')}")
            return result_data

        except Exception as e:
            logger.exception(f"Kriittinen virhe ID {match_id}: {e}")
            result_data['status'] = 'critical_error_processing'; result_data['error_message'] = str(e); return result_data

    def run(self):
        """Suorita päälogiikka."""
        logger.info(f"Skraperi käynnistyy. Seuraava ID: {self.current_id + 1}, Max ID:t: {MAX_MATCHES}")
        processed_count = 0; success_count = 0; failed_count = 0
        start_time = time.time()

        try:
            while processed_count < MAX_MATCHES:
                if self.current_id < 0: self.current_id = 0
                next_id = self.current_id + 1
                logger.info(f"Käsitellään {processed_count + 1}/{MAX_MATCHES} : ID {next_id}")

                result = self.process_match(next_id)
                # Varmista että result on aina dict, vaikka virheitä tapahtuisi
                if not isinstance(result, dict):
                    logger.error(f"process_match palautti virheellisen tyypin ({type(result)}) ID:lle {next_id}. Ohitetaan.")
                    result = {'match_id': next_id, 'status': 'internal_error_invalid_result_type', 'error_message': 'process_match did not return a dict'}
                    failed_count += 1
                else:
                    self.match_data.append(result)
                    if result.get('status', '').startswith('success'): success_count += 1
                    else: failed_count += 1


                self.current_id = next_id
                processed_count += 1

                if processed_count % 5 == 0:
                     logger.info(f"Välitallennus {processed_count} ID:n jälkeen...")
                     self.save_data(); self.save_last_id()
                     logger.info(f"Tallennettu. Viimeisin ID: {self.current_id}")

                if processed_count < MAX_MATCHES: time.sleep(REQUEST_DELAY)

        except KeyboardInterrupt: logger.warning("Keskeytetty.")
        except Exception as e: logger.exception(f"Pääsilmukan virhe: {e}")
        finally:
            logger.info("Tallennetaan lopulliset tiedot..."); self.save_data(); self.save_last_id()
            duration = time.time() - start_time
            logger.info(f"--- Skrapaus valmis --- Kesto: {duration:.2f}s")
            logger.info(f"Yritti: {processed_count}, Onnistui ('success*'): {success_count}, Epäonnistui/Muu: {failed_count}")
            logger.info(f"Viimeisin ID: {self.current_id}, Data: {OUTPUT_FILE}, ID-tiedosto: {LAST_ID_FILE}")

if __name__ == '__main__':
    scraper = MatchDataScraper()
    scraper.run()
    logger.info("Skraperin suoritus päättyi.")
