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

# --- Loggausasetukset ja Globaalit muuttujat (ennallaan) ---
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
REQUEST_DELAY = 2.5
CACHE_DIR = "scrape_cache"
OUTPUT_FILE = "match_data_single_test.json" # Eri tiedosto testille
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# --- MatchDataScraper -luokka ---
class MatchDataScraper:
    def __init__(self):
        pass

    def setup_driver_local(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new"); chrome_options.add_argument("--no-sandbox"); chrome_options.add_argument("--disable-dev-shm-usage"); chrome_options.add_argument("--disable-gpu"); chrome_options.add_argument("--window-size=1920,1080"); chrome_options.add_argument("--lang=fi-FI"); chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"); chrome_options.add_argument("--disable-blink-features=AutomationControlled"); chrome_options.add_experimental_option('excludeSwitches', ['enable-automation']); chrome_options.add_experimental_option('useAutomationExtension', False); chrome_options.add_experimental_option('prefs', {'intl.accept_languages': 'fi,fi_FI'})
        try:
            service = Service(ChromeDriverManager().install(), log_output=os.devnull); driver = webdriver.Chrome(service=service, options=chrome_options); driver.set_page_load_timeout(60); driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"); return driver
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            try: logger.info("Yritetään yksinkertaisempaa driverin alustusta..."); driver = webdriver.Chrome(options=chrome_options); driver.set_page_load_timeout(60); return driver
            except Exception as e2: logger.critical(f"Driverin alustus epäonnistui täysin: {e2}"); raise

    def fetch_page(self, url):
        driver = None; last_exception = None; wait_element_selector = "div#matchstatus"
        for attempt in range(1, 4):
            try:
                logger.debug(f"fetch_page yritys {attempt}/3 URL: {url}"); driver = self.setup_driver_local();
                if not driver: raise WebDriverException("Driverin alustus epäonnistui.")
                driver.get(url); logger.debug(f"Sivu {url} avattu yrityksellä {attempt}")
                try: logger.debug(f"Odotetaan elementtiä '{wait_element_selector}' enintään 45 sekuntia..."); WebDriverWait(driver, 45).until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_element_selector))); logger.debug(f"Odotettu elementti '{wait_element_selector}' löytyi.")
                except TimeoutException:
                    page_title = driver.title; logger.warning(f"Elementti '{wait_element_selector}' ei löytynyt ajoissa sivulla {url} (Otsikko: {page_title}). Yritetään jatkaa."); screenshot_path = os.path.join(CACHE_DIR, f"{url.split('/')[-2]}_timeout_err.png");
                    try: driver.save_screenshot(screenshot_path); logger.info(f"Kuvakaappaus tallennettu: {screenshot_path}")
                    except Exception as ss_err: logger.error(f"Kuvakaappauksen tallennus epäonnistui: {ss_err}")
                time.sleep(4); logger.debug("Skrollataan sivun alaosaan..."); driver.execute_script("window.scrollTo(0, document.body.scrollHeight);"); time.sleep(2)
                page_source = driver.page_source; logger.debug(f"Sivun lähdekoodi haettu (pituus: {len(page_source)} merkkiä)")
                if len(page_source) < 20000: logger.warning(f"Sivu {url} vaikuttaa lyhyeltä (koko: {len(page_source)}), mahdollinen virhe tai data puuttuu."); self.save_debug_files(url.split('/')[-2], page_source, "LYHYT_SIVU"); return None
                logger.info(f"Sivun {url} haku onnistui yrityksellä {attempt}"); return page_source
            except (TimeoutException, WebDriverException, NoSuchElementException) as e: logger.warning(f"{type(e).__name__} yrityksellä {attempt}/3 haettaessa {url}: {e}"); last_exception = e
            except Exception as e: logger.error(f"Yleinen virhe sivun haussa yrityksellä {attempt}/3 ({url}): {type(e).__name__} - {str(e)}"); last_exception = e
            finally:
                if driver: logger.debug(f"Suljetaan driver yrityksen {attempt} jälkeen."); driver.quit()
                if attempt < 3: wait_time = REQUEST_DELAY + attempt * 3; logger.debug(f"Odotetaan {wait_time}s ennen seuraavaa yritystä..."); time.sleep(wait_time)
        logger.error(f"Sivun {url} haku epäonnistui {attempt} yrityksen jälkeen. Viimeisin virhe: {last_exception}"); return None

    def save_debug_files(self, match_id, html_content, context_text):
        try:
            match_id_str = str(match_id); debug_dir = os.path.join(CACHE_DIR, match_id_str); Path(debug_dir).mkdir(parents=True, exist_ok=True); html_path = os.path.join(debug_dir, f"{match_id_str}_{context_text}_debug.html"); html_to_write = str(html_content) if html_content else ""
            with open(html_path, 'w', encoding='utf-8') as f: f.write(html_to_write)
            logger.debug(f"Tallennettu debug HTML: {html_path}")
        except Exception as e: logger.error(f"Debug HTML -tiedoston tallennus epäonnistui (ID: {match_id_str}): {e}")

    def extract_events(self, soup, team_id_suffix):
        events = {'goals': [], 'yellow_cards': [], 'red_cards': []}; scorers_container_selector = f"div#scorers_{team_id_suffix} div.football.scorernames"; scorers_container = soup.select_one(scorers_container_selector)
        if scorers_container:
            scorer_spans = scorers_container.find_all('span', recursive=False)
            for scorer_span in scorer_spans:
                 scorer_link = scorer_span.find('a', class_='scorer')
                 if scorer_link: player_name = scorer_link.get_text(strip=True); player_href = scorer_link.get('href'); time_node = scorer_link.next_sibling; goal_times_str = time_node.strip() if time_node and isinstance(time_node, NavigableString) else None
                 if player_name and goal_times_str: goal_times = re.findall(r"(\d+'?)", goal_times_str); [events['goals'].append({'player': player_name, 'time': time_val.replace("'", "") + "'", 'link': player_href}) for time_val in goal_times]; logger.debug(f"Löytyi maali (ylälista, {team_id_suffix}): {player_name} {goal_times}")
        red_card_selector = f"div.redcard_{team_id_suffix} span"; red_card_spans = soup.select(red_card_selector)
        for span in red_card_spans: text_content = span.get_text(strip=True); match = re.match(r"(.+)\s+(\d+'?)", text_content);
        if match: player_name = match.group(1).strip(); time_str = match.group(2).replace("'", "") + "'"; events['red_cards'].append({'player': player_name, 'time': time_str}); logger.debug(f"Löytyi punainen kortti ({team_id_suffix}): {player_name} {time_str}")
        yellow_card_selector = f"div.yellowcard_{team_id_suffix} span"; yellow_card_spans = soup.select(yellow_card_selector)
        if not yellow_card_spans: logger.debug(f"Ei löytynyt yksittäisiä keltaisia kortteja valitsimella '{yellow_card_selector}' ({team_id_suffix})")
        for span in yellow_card_spans: text_content = span.get_text(strip=True); match = re.match(r"(.+)\s+(\d+'?)", text_content);
        if match: player_name = match.group(1).strip(); time_str = match.group(2).replace("'", "") + "'"; events['yellow_cards'].append({'player': player_name, 'time': time_str}); logger.debug(f"Löytyi (mahdollisesti) keltainen kortti ({team_id_suffix}): {player_name} {time_str}")
        return events

    def extract_data(self, soup, match_id):
        data = {'match_id': match_id, 'match_id_from_page': None}; logger.debug(f"Aloitetaan datan purku ID:lle {match_id}"); HOME_TEAM_SELECTOR = "a#team_A span.teamname"; AWAY_TEAM_SELECTOR = "a#team_B span.teamname"; SCORE_SELECTOR = "span.info_result"; HALF_TIME_SCORE_SELECTOR = "div.widget-match__score-halftime"; STATUS_SELECTOR = "div#matchstatus span"; INFO_BLOCK_SELECTOR = "div#timeandvenue"; MATCH_DATE_ID_SELECTOR = "span.matchdate"; MATCH_VENUE_TIME_SELECTOR = "span.matchvenue"; FORMATION_SELECTOR = "span.infosnippet.players"; MATCH_DURATION_SELECTOR = "span.infosnippet.matchtim"; SUBSTITUTIONS_SELECTOR = "span.infosnippet.substitutions"; WEATHER_SELECTOR = "span.infosnippet.weather"; ATTENDANCE_SELECTOR = "span.infosnippet.attendance"; AWARD_CONTAINER_SELECTOR = "div.infosnippetaward"; AWARD_PLAYER_DIV_SELECTOR = "div[style*='text-align: left']"; AWARD_LINK_SELECTOR = "a[href*='/person/']"; AWARD_SPAN_SELECTOR = "span.award"; AWARD_STAR_CONTAINER_SELECTOR = "div[style*='float: right']"; AWARD_STAR_ICON_SELECTOR = "i.fa-star"; STATS_WRAPPER_SELECTOR = "div.slimstatwrapper"; STATS_NAME_SELECTOR = "span.tT"; STATS_HOME_VALUE_SELECTOR = "span.tA"; STATS_AWAY_VALUE_SELECTOR = "span.tB"; GOAL_ASSIST_HEADING_SELECTOR = "h2"; GOAL_ASSIST_ROW_SELECTOR = "div.row"; GOAL_ASSIST_COL_SELECTOR = "div.col"; GOAL_ASSIST_TEAM_NAME_SELECTOR = "h3"; GOAL_ASSIST_TABLE_SELECTOR = "table"; GOAL_ASSIST_TABLE_BODY_SELECTOR = "tbody"; GOAL_ASSIST_TABLE_ROW_SELECTOR = "tr"; GOAL_ASSIST_JERSEY_SELECTOR = "td:nth-of-type(1)"; GOAL_ASSIST_PLAYER_SELECTOR = "td:nth-of-type(2) a"; GOAL_ASSIST_CONTRIB_SELECTOR = "td:nth-of-type(3)";
        try: data['page_title'] = soup.find('title').get_text(strip=True) if soup.find('title') else None
        except Exception as e: logger.warning(f"Virhe otsikko: {e}"); data['page_title'] = None
        try: data['team_home'] = soup.select_one(HOME_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(HOME_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe kotijoukkue: {e}"); data['team_home'] = None
        try: data['team_away'] = soup.select_one(AWAY_TEAM_SELECTOR).get_text(strip=True) if soup.select_one(AWAY_TEAM_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe vierasjoukkue: {e}"); data['team_away'] = None
        try: score_el = soup.select_one(SCORE_SELECTOR); score_text = score_el.get_text(strip=True).replace(" ", "") if score_el else None; data['score'] = score_text if score_text and '–' in score_text else None
        except Exception as e: logger.warning(f"Virhe tulos: {e}"); data['score'] = None
        try: ht_el = soup.select_one(HALF_TIME_SCORE_SELECTOR); ht_text = ht_el.get_text(strip=True).replace("(", "").replace(")", "").replace(" ", "") if ht_el else ""; data['score_halftime'] = ht_text if ht_text else None
        except Exception as e: logger.warning(f"Virhe puoliaikatulos: {e}"); data['score_halftime'] = None
        try: status_element = soup.select_one(STATUS_SELECTOR); data['match_status_raw'] = status_element.get_text(strip=True) if status_element else None
        except Exception as e: logger.warning(f"Virhe ottelun tila: {e}"); data['match_status_raw'] = None
        data['match_datetime_raw'] = None; data['venue'] = None;
        try:
            info_block = soup.select_one(INFO_BLOCK_SELECTOR)
            if info_block:
                match_date_el = info_block.select_one(MATCH_DATE_ID_SELECTOR)
                if match_date_el: id_match = re.search(r'Ottelu\s+(\d+)', match_date_el.get_text()); data['match_id_from_page'] = int(id_match.group(1)) if id_match else None
                match_venue_el = info_block.select_one(MATCH_VENUE_TIME_SELECTOR)
                if match_venue_el: time_date_match = re.search(r'(\d{1,2}:\d{2})\s*\|\s*([a-zA-Z]{1,3}\s+\d{1,2}\.\d{1,2}\.?)', match_venue_el.get_text(separator='|', strip=True)); data['match_datetime_raw'] = f"{time_date_match.group(1)} | {time_date_match.group(2)}" if time_date_match else None; venue_link = match_venue_el.find('a');
                if venue_link: venue_text_before = venue_link.previous_sibling; venue_parts = [venue_text_before.strip() if venue_text_before and isinstance(venue_text_before, NavigableString) else None, venue_link.get_text(strip=True)]; data['venue'] = ', '.join(filter(None, venue_parts))
                else: full_venue_text = match_venue_el.get_text(strip=True); data['venue'] = full_venue_text.replace(data['match_datetime_raw'].split('|')[0].strip(), '').replace(data['match_datetime_raw'].split('|')[1].strip(), '').replace('|','').strip(',').strip() if data['match_datetime_raw'] else full_venue_text
        except Exception as e: logger.warning(f"Virhe info block: {e}")
        data['formation'] = None; data['match_duration_format'] = None; data['substitutions_allowed'] = None; data['weather'] = None; data['audience'] = None;
        try: data['formation'] = soup.select_one(FORMATION_SELECTOR).get_text(strip=True) if soup.select_one(FORMATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe formation: {e}")
        try: data['match_duration_format'] = soup.select_one(MATCH_DURATION_SELECTOR).get_text(strip=True) if soup.select_one(MATCH_DURATION_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe duration format: {e}")
        try: data['substitutions_allowed'] = soup.select_one(SUBSTITUTIONS_SELECTOR).get_text(strip=True) if soup.select_one(SUBSTITUTIONS_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe substitutions: {e}")
        try: data['weather'] = soup.select_one(WEATHER_SELECTOR).get_text(strip=True) if soup.select_one(WEATHER_SELECTOR) else None
        except Exception as e: logger.warning(f"Virhe weather: {e}")
        try: audience_el = soup.select_one(ATTENDANCE_SELECTOR); audience_text = audience_el.get_text(strip=True) if audience_el else None; data['audience'] = int(audience_text) if audience_text and audience_text.isdigit() else None
        except Exception as e: logger.warning(f"Virhe yleisömäärä: {e}")
        data['awards'] = []
        try:
             award_container = soup.select_one(AWARD_CONTAINER_SELECTOR)
             if award_container:
                  player_divs = award_container.select(AWARD_PLAYER_DIV_SELECTOR)
                  for player_div in player_divs:
                    link = player_div.select_one(AWARD_LINK_SELECTOR)
                    if link: player_href = link.get('href'); player_name = None; award_span = link.select_one(AWARD_SPAN_SELECTOR); player_name = award_span.next_sibling.strip() if award_span and award_span.next_sibling and isinstance(award_span.next_sibling, NavigableString) else None; name_parts = [text.strip() for text in link.find_all(string=True, recursive=False) if text.strip()]; player_name = player_name or (" ".join(name_parts) if name_parts else None); star_count = 0; star_container = link.select_one(AWARD_STAR_CONTAINER_SELECTOR); star_count = len(star_container.select(AWARD_STAR_ICON_SELECTOR)) if star_container else 0
                    if player_name and player_href: data['awards'].append({'player': player_name, 'link': player_href, 'stars': star_count}); logger.debug(f"Löytyi palkittu: {player_name} ({star_count}*)")
                    else: logger.warning(f"Ei saatu purettua palkitun nimeä/linkkiä: {link.prettify()}")
        except Exception as e: logger.warning(f"Virhe palkinnot: {e}")
        data['stats'] = {}
        try:
            stat_wrappers = soup.select(STATS_WRAPPER_SELECTOR); logger.debug(f"Löytyi {len(stat_wrappers)} tilasto-wrapperia.")
            for wrapper in stat_wrappers:
                name_el = wrapper.select_one(STATS_NAME_SELECTOR); home_el = wrapper.select_one(STATS_HOME_VALUE_SELECTOR); away_el = wrapper.select_one(STATS_AWAY_VALUE_SELECTOR)
                if name_el and home_el and away_el:
                    stat_name_raw = name_el.get_text(strip=True); stat_name_clean = re.sub(r'[()]', '', stat_name_raw.lower().replace(" ", "_").replace("ä", "a").replace("ö", "o")); home_val_raw = home_el.get_text(strip=True); away_val_raw = away_el.get_text(strip=True)
                    try: home_val = int(home_val_raw)
                    except ValueError: home_val = home_val_raw
                    try: away_val = int(away_val_raw)
                    except ValueError: away_val = away_val_raw
                    data['stats'][stat_name_clean] = {'home': home_val, 'away': away_val}; logger.debug(f"Tilasto: '{stat_name_clean}' Koti: {home_val}, Vieras: {away_val}")
                else: # KORJATTU SISENNYS TÄSSÄ
                    logger.warning(f"Ei voitu purkaa tilastoa tästä wrapperista (puuttuvia elementtejä): {wrapper.prettify()}")
        except Exception as e: logger.error(f"Virhe tilastojen purussa: {e}")
        data['events_from_list'] = {};
        try: home_events = self.extract_events(soup, 'A'); away_events = self.extract_events(soup, 'B'); data['events_from_list']['home'] = home_events; data['events_from_list']['away'] = away_events
        except Exception as e: logger.error(f"Virhe tapahtumien (ylälista/kortit) purussa ID {match_id}: {e}"); data['events_from_list'] = {'home': {}, 'away': {}}

        # --- Maalit ja Syötöt - Taulukko (KORJATTU SISENNYS) ---
        data['goal_assist_details'] = {'home': [], 'away': []}
        try:
            heading = soup.find(GOAL_ASSIST_HEADING_SELECTOR, string=re.compile(r'Maalit\s+ja\s+syötöt'))
            if heading:
                logger.debug("Löytyi 'Maalit ja syötöt' -otsikko."); parent_row = heading.find_next_sibling(GOAL_ASSIST_ROW_SELECTOR)
                if parent_row:
                    cols = parent_row.select(GOAL_ASSIST_COL_SELECTOR); logger.debug(f"Löytyi {len(cols)} saraketta maali/syöttö-datalle.")
                    for col in cols:
                        team_name_h3 = col.select_one(GOAL_ASSIST_TEAM_NAME_SELECTOR); team_name = team_name_h3.get_text(strip=True) if team_name_h3 else None; team_key = None
                        if team_name and data['team_home'] and team_name in data['team_home']: team_key = 'home'
                        elif team_name and data['team_away'] and team_name in data['team_away']: team_key = 'away'
                        else: logger.warning(f"Ei tunnistettu joukkuetta '{team_name}' maali/syöttö-taulukosta."); continue
                        logger.debug(f"Käsitellään maali/syöttö-taulukkoa joukkueelle: {team_name} ({team_key})"); table = col.select_one(GOAL_ASSIST_TABLE_SELECTOR)
                        if table:
                            tbody = table.select_one(GOAL_ASSIST_TABLE_BODY_SELECTOR)
                            if tbody:
                                rows = tbody.select(GOAL_ASSIST_TABLE_ROW_SELECTOR); logger.debug(f"Löytyi {len(rows)} pelaajariviä taulukosta ({team_key}).")
                                for row in rows:
                                    jersey_el = row.select_one(GOAL_ASSIST_JERSEY_SELECTOR); player_link_el = row.select_one(GOAL_ASSIST_PLAYER_SELECTOR); contrib_el = row.select_one(GOAL_ASSIST_CONTRIB_SELECTOR)
                                    # Tarkista, löytyivätkö kaikki tarvittavat elementit riviltä
                                    if jersey_el and player_link_el and contrib_el:
                                        jersey = jersey_el.get_text(strip=True); player_name = player_link_el.get_text(strip=True); player_link = player_link_el.get('href'); contrib_str = contrib_el.get_text(strip=True); goals, assists, total = None, None, None; contrib_match = re.match(r'(\d+)\+(\d+)=(\d+)', contrib_str)
                                        if contrib_match:
                                            try: goals = int(contrib_match.group(1)); assists = int(contrib_match.group(2)); total = int(contrib_match.group(3))
                                            except ValueError: logger.warning(f"Virhe muunnettaessa G+A numeroiksi: {contrib_str}")
                                        player_data = {'jersey': jersey, 'player': player_name, 'link': player_link, 'contribution_raw': contrib_str, 'goals': goals, 'assists': assists, 'total_points': total}; data['goal_assist_details'][team_key].append(player_data); logger.debug(f"Lisätty G+A data ({team_key}): {player_name} ({contrib_str})")
                                    else: # KORJATTU SISENNYS TÄSSÄ
                                        logger.warning(f"Ei voitu purkaa kaikkia tietoja maali/syöttö-riviltä: {row.prettify()}")
                            else: logger.warning(f"Ei löytynyt tbody-elementtiä maali/syöttö-taulukosta ({team_key}).")
                        else: logger.warning(f"Ei löytynyt table-elementtiä maali/syöttö-sarakkeesta ({team_key}).")
                else: logger.warning("Ei löytynyt rivielementtiä 'Maalit ja syötöt' -otsikon jälkeen.")
            else: logger.debug("Ei löytynyt 'Maalit ja syötöt' -otsikkoa.")
        except Exception as e: logger.error(f"Virhe maali/syöttö-taulukon purussa: {e}")
        logger.debug(f"Datan purku valmis ID:lle {match_id}")
        return data

    def process_match(self, match_id):
        url = BASE_URL.format(match_id=match_id); logger.info(f"--- Käsittely alkaa: ID {match_id} ({url}) ---"); scrape_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'); result_data = {'match_id': match_id, 'url': url, 'scrape_timestamp': scrape_timestamp, 'status': 'unknown', 'status_details': []}
        try:
            html = self.fetch_page(url)
            if not html: result_data['status'] = 'page_load_failed'; result_data['status_details'].append('HTML content was empty after fetch attempts.'); return result_data
            self.save_debug_files(match_id, html, "FETCH_SUCCESS")
            soup = BeautifulSoup(html, 'html.parser')
            extracted_data = self.extract_data(soup, match_id); result_data.update(extracted_data)
            if result_data.get('match_id_from_page') is not None and result_data['match_id_from_page'] != match_id: logger.warning(f"ID {match_id} eroaa sivulta löydetystä ID:stä {result_data['match_id_from_page']}!"); result_data['status_details'].append(f"id_mismatch_on_page_{result_data['match_id_from_page']}")
            raw_status_value = result_data.get('match_status_raw'); raw_status = raw_status_value.lower() if isinstance(raw_status_value, str) else ''
            score_value = result_data.get('score') or ''

            if 'päättynyt' in raw_status: result_data['status'] = 'success_finished' if result_data.get('team_home') else 'success_finished_partial'
            elif 'ei alkanut' in raw_status: result_data['status'] = 'success_not_started'
            elif 'käynnissä' in raw_status or ('–' in score_value and ':' not in score_value): result_data['status'] = 'success_live'
            elif result_data.get('team_home'): result_data['status'] = 'success_data_found_unknown_state'
            elif result_data.get('page_title') and 'Tulospalvelu' in result_data.get('page_title'): result_data['status'] = 'success_partial_data'
            else: result_data['status'] = 'parsing_failed_no_data'; result_data['status_details'].append('No meaningful data extracted.')

            if result_data['status'].startswith('success') and not result_data.get('team_home') and not result_data.get('score') and not result_data.get('stats'): logger.warning(f"Vaikka status on '{result_data['status']}', oleellista dataa (joukkueet/tulos/tilastot) puuttuu ID:llä {match_id}."); result_data['status_details'].append('missing_core_data')
            logger.info(f"Käsittely valmis: ID {match_id}. Tila: {result_data.get('status')}, Yleisö: {result_data.get('audience')}, Tulos: {result_data.get('score')}, Tilastoja: {len(result_data.get('stats',{}))}, G+A: {len(result_data.get('goal_assist_details',{}).get('home',[]))}/{len(result_data.get('goal_assist_details',{}).get('away',[]))}")
            return result_data
        except Exception as e: logger.exception(f"Kriittinen virhe käsiteltäessä ID {match_id}: {e}"); result_data['status'] = 'critical_error_processing'; result_data['error_message'] = str(e); result_data['status_details'].append('Exception during processing.'); return result_data

# --- Muokattu pääsuoritus vain yhdelle ID:lle ---
if __name__ == '__main__':
    target_match_id = 3748451
    logger.info(f"Aloitetaan yksittäisen ID:n {target_match_id} testiajo...")
    start_time = time.time()
    scraper = MatchDataScraper()
    result = None
    try:
        result = scraper.process_match(target_match_id)
    except Exception as e:
        logger.exception(f"Odottamaton virhe process_match-kutsussa ID:lle {target_match_id}: {e}")
        result = {'match_id': target_match_id, 'url': BASE_URL.format(match_id=target_match_id), 'scrape_timestamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'), 'status': 'critical_error_main_execution', 'error_message': str(e), 'status_details': ['Exception during main execution block.']}

    logger.info("--- Yksittäisen ajon tulos ---")
    # Varmista, että result on sanakirja ennen json.dumps-kutsua
    if isinstance(result, dict):
        logger.info(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        logger.error(f"Tulos ei ollut sanakirja, vaan tyyppiä {type(result)}. Tulos: {result}")


    try:
        # Tallenna vain jos result on sanakirja
        data_to_save = [result] if isinstance(result, dict) else []
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        logger.info(f"Testiajon tulos tallennettu tiedostoon: {OUTPUT_FILE}")
    except Exception as e:
        logger.error(f"Virhe tallennettaessa testitulosta tiedostoon {OUTPUT_FILE}: {e}")

    duration = time.time() - start_time
    logger.info(f"--- Testiajo valmis --- Kesto: {duration:.2f}s")
    logger.info("Skriptin suoritus päättyi (yksittäinen ajo).")
