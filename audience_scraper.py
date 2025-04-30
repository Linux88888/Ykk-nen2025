import os
import re
import time
import json
import logging
import datetime
from pathlib import Path
# Poistettu 'Counter', koska sitä ei käytetty aktiivisesti laajemmassa datan keruussa
# from collections import Counter

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
    level=logging.INFO,  # Muutettu INFO-tasolle oletuksena, DEBUG antaa paljon enemmän tulostetta
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("match_scraper.log"), # Logitiedoston nimi muutettu
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Asetukset
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
# START_ID voi olla hyödyllinen, jos halutaan aloittaa tietystä pisteestä ilman last_id-tiedostoa
# START_ID = 3748452
MAX_MATCHES = 100  # Kuinka monta ID:tä käsitellään per ajo
REQUEST_DELAY = 2  # Sekuntia sivujen välillä
CACHE_DIR = "scrape_cache" # Välimuistin nimi muutettu
OUTPUT_FILE = "match_data.json" # Tulostiedoston nimi muutettu
LAST_ID_FILE = "last_match_id.txt" # Viimeisen ID:n tiedoston nimi muutettu

# Alusta hakemistot
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class MatchDataScraper:
    def __init__(self):
        self.current_id = self.load_last_id()
        self.match_data = self.load_data() # Muuttujan nimi muutettu

    def setup_driver_local(self):
        """Alusta Selenium WebDriver ja palauta instanssi"""
        chrome_options = Options()
        # Headless on oletus CI/CD-ympäristöissä
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            # Service-objekti piilottaa webdriverin lokitiedot
            service = Service(ChromeDriverManager().install(), log_output=os.devnull)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(45)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            # Yritetään yksinkertaisempaa fallbackina (harvoin tarpeen ChromDriverManagerin kanssa)
            try:
                logger.info("Yritetään yksinkertaisempaa driverin alustusta...")
                # Poistetaan service tästä, jos se aiheutti ongelman
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(45)
                return driver
            except Exception as e2:
                 logger.critical(f"Driverin alustus epäonnistui täysin: {e2}")
                 raise # Heitetään poikkeus, koska ilman driveria ei voi jatkaa

    def load_last_id(self):
        """Lataa viimeisin käsitelty ID"""
        start_id_default = 1 # Oletusarvo, jos tiedostoa ei ole ja START_ID:tä ei ole määritelty
        try:
            if os.path.exists(LAST_ID_FILE):
                with open(LAST_ID_FILE, 'r') as f:
                    last_id = int(f.read().strip())
                    logger.info(f"Ladatty viimeisin ID: {last_id} tiedostosta {LAST_ID_FILE}")
                    # Varmistetaan, ettei ID ole negatiivinen
                    return max(0, last_id)
            # Jos START_ID on määritelty globaalisti, käytä sitä lähtökohtana
            # Huom: globaalin muuttujan käyttö funktiossa vaatii 'global START_ID' tai sen välittämistä parametrina.
            # Pidetään tämä yksinkertaisena ja aloitetaan 0:sta tai START_ID-1:stä jos se on asetettu ylempänä.
            # Tässä esimerkissä aloitetaan 0:sta, jos tiedostoa ei ole.
            logger.info(f"Ei löytynyt {LAST_ID_FILE}-tiedostoa, aloitetaan ID:stä {start_id_default -1 } (seuraava on {start_id_default}).")
            return start_id_default - 1 # Palautetaan edellinen ID, jotta seuraava käsitelty on start_id_default
        except ValueError:
             logger.error(f"Virheellinen arvo tiedostossa {LAST_ID_FILE}. Aloitetaan ID:stä {start_id_default - 1}.")
             return start_id_default - 1
        except Exception as e:
            logger.error(f"Virhe ladattaessa viimeisintä ID:tä tiedostosta {LAST_ID_FILE}: {str(e)}")
            return start_id_default - 1

    def save_last_id(self):
        """Tallenna nykyinen (viimeksi käsitelty) ID"""
        try:
            with open(LAST_ID_FILE, 'w') as f:
                f.write(str(self.current_id))
            # Poistettu logitus täältä, koska se tulee run-metodin lopusta
        except Exception as e:
            logger.error(f"Virhe tallennettaessa ID:tä tiedostoon {LAST_ID_FILE}: {str(e)}")

    def load_data(self):
        """Lataa olemassa oleva data JSON-tiedostosta"""
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    # Käytetään listaa oletuksena, jos tiedosto on tyhjä tai virheellinen
                    try:
                        data = json.load(f)
                        # Varmistetaan, että data on lista
                        if isinstance(data, list):
                             logger.info(f"Ladatty {len(data)} tietuetta tiedostosta {OUTPUT_FILE}")
                             return data
                        else:
                             logger.warning(f"Tiedoston {OUTPUT_FILE} sisältö ei ollut lista. Aloitetaan tyhjästä listasta.")
                             return []
                    except json.JSONDecodeError:
                         logger.error(f"Virhe ladattaessa JSON-dataa tiedostosta {OUTPUT_FILE}. Tiedosto saattaa olla korruptoitunut. Aloitetaan tyhjästä listasta.")
                         return []
            logger.info(f"Ei löytynyt {OUTPUT_FILE}-tiedostoa, aloitetaan tyhjästä listasta.")
            return []
        except Exception as e:
            logger.error(f"Yleinen virhe ladattaessa dataa tiedostosta {OUTPUT_FILE}: {str(e)}")
            return [] # Palautetaan tyhjä lista virhetilanteessa

    def save_data(self):
        """Tallenna kerätty data JSON-muodossa"""
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.match_data, f, ensure_ascii=False, indent=2)
            # Poistettu logitus täältä, koska se tulee run-metodin lopusta
        except Exception as e:
            logger.error(f"Virhe tallennettaessa dataa tiedostoon {OUTPUT_FILE}: {str(e)}")

    def fetch_page(self, url):
        """Hae sivu Seleniumilla, mukaan lukien uudelleenyritykset"""
        driver = None
        last_exception = None
        for attempt in range(1, 4):
            try:
                logger.debug(f"fetch_page yritys {attempt}/3 URL: {url}")
                driver = self.setup_driver_local()
                if not driver:
                    logger.error(f"Driverin alustus epäonnistui yrityksellä {attempt}, ei voida jatkaa.")
                    # Ei heitetä poikkeusta heti, yritetään uudelleen jos mahdollista
                    if attempt < 3:
                         time.sleep(5 + attempt * 2) # Pidennä odotusta epäonnistuneiden yritysten jälkeen
                         continue
                    else:
                         # Jos kaikki yritykset epäonnistuivat driverin alustuksessa
                         raise WebDriverException("Driverin alustus epäonnistui kaikilla yrityksillä.")

                driver.get(url)
                logger.debug(f"Sivu {url} avattu yrityksellä {attempt}")

                # --- ODOTUSSTRATEGIA ---
                # Odotetaan, että jokin keskeinen elementti latautuu.
                # TÄMÄ ON ARVAUS - TARKISTA OIKEA ELEMENTTI SELAINKEHITTÄJÄN TYÖKALUILLA!
                # Esimerkiksi elementti, joka sisältää joukkueiden nimet tai ottelun tilan.
                wait_element_selector = "div.match-header" # TAI "div.stats-container" TAI jokin muu luotettava
                try:
                    logger.debug(f"Odotetaan elementtiä '{wait_element_selector}' enintään 30 sekuntia...")
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_element_selector))
                    )
                    logger.debug("Odotettu elementti löytyi.")
                except TimeoutException:
                    # Jos odotuselementtiä ei löydy, sivu ei ehkä latautunut oikein tai se puuttuu.
                    # Yritetään silti jatkaa, mutta logitetaan varoitus.
                    logger.warning(f"Odotettu elementti '{wait_element_selector}' ei löytynyt annetussa ajassa sivulla {url}.")
                    # Otetaan kuvakaappaus debuggausta varten (valinnainen, mutta hyödyllinen)
                    # try:
                    #     screenshot_path = os.path.join(CACHE_DIR, f"{url.split('/')[-2]}_timeout_screenshot.png")
                    #     driver.save_screenshot(screenshot_path)
                    #     logger.info(f"Tallennnettu kuvakaappaus: {screenshot_path}")
                    # except Exception as ss_err:
                    #     logger.error(f"Kuvakaappauksen tallennus epäonnistui: {ss_err}")


                # Pieni lisäodotus ja skrollaus varmuuden vuoksi (dynaaminen sisältö)
                time.sleep(3)
                logger.debug("Skrollataan sivun alaosaan...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)

                page_source = driver.page_source
                logger.debug(f"Sivun lähdekoodi haettu (pituus: {len(page_source)} merkkiä)")

                # Tarkista edelleen sivun pituus (hyvä heuristiikka virhesivuille)
                if len(page_source) < 2000:
                     logger.warning(f"Sivu {url} vaikuttaa lyhyeltä (koko: {len(page_source)}), mahdollinen virhe tai tyhjä sivu.")
                     # Tallenna debug-tiedostot lyhyestä sivusta
                     self.save_debug_files(url.split('/')[-2], page_source, "LYHYT_SIVU")
                     # Älä yritä uudelleen turhaan, jos sivu on lyhyt, se todennäköisesti pysyy sellaisena.
                     # Voit päättää palauttaa None tai tyhjän merkkijonon. None on selkeämpi virheen merkki.
                     return None # Indikoi, että sivun sisältöä ei saatu kunnolla

                logger.info(f"Sivun {url} haku onnistui yrityksellä {attempt}")
                return page_source # Palauta onnistuneesti haettu sisältö

            except TimeoutException as e:
                logger.warning(f"TimeoutException yrityksellä {attempt}/3 haettaessa {url}: {e}")
                last_exception = e
            except WebDriverException as e:
                 logger.error(f"WebDriverException yrityksellä {attempt}/3 haettaessa {url}: {e}")
                 last_exception = e
                 # Jos virhe on yhteysvirhe, odotus voi auttaa
            except Exception as e:
                logger.error(f"Yleinen virhe sivun haussa yrityksellä {attempt}/3 ({url}): {type(e).__name__} - {str(e)}")
                last_exception = e
            finally:
                if driver:
                    logger.debug(f"Suljetaan driver yrityksen {attempt} jälkeen.")
                    driver.quit()
                # Odota ennen seuraavaa yritystä (jos sellainen tulee)
                if attempt < 3:
                    wait_time = REQUEST_DELAY + attempt * 2 # Lisää odotusaikaa epäonnistuneiden jälkeen
                    logger.debug(f"Odotetaan {wait_time} sekuntia ennen seuraavaa yritystä...")
                    time.sleep(wait_time)

        logger.error(f"Sivun {url} haku epäonnistui kaikkien 3 yrityksen jälkeen. Viimeisin virhe: {last_exception}")
        return None # Palauta None, jos kaikki yritykset epäonnistuivat

    def save_debug_files(self, match_id, html_content, context_text):
        """Tallenna HTML ja kontekstiteksti debuggausta varten"""
        try:
            match_id_str = str(match_id)
            # Luo alihakemisto ID:lle cache-hakemistoon
            debug_dir = os.path.join(CACHE_DIR, match_id_str)
            Path(debug_dir).mkdir(parents=True, exist_ok=True)

            # HTML-tiedosto
            html_filename = f"{match_id_str}_{context_text}_debug.html"
            html_path = os.path.join(debug_dir, html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(str(html_content))
            logger.debug(f"Tallennettu debug HTML: {html_path}")

        except Exception as e:
            logger.error(f"Debug-tiedostojen tallennus epäonnistui (ID: {match_id_str}, Context: {context_text}): {str(e)}")

    def extract_data(self, soup, match_id):
        """
        Etsi ja pura keskeiset tiedot ottelusivulta.
        Tämä funktio on esimerkki ja vaatii todennäköisesti säätöä
        kohdesivuston rakenteen perusteella.
        """
        data = {'match_id': match_id}
        logger.debug(f"Aloitetaan datan purku ID:lle {match_id}")

        try:
            # --- Yleiset tiedot (Esimerkkejä, vaatii tarkistusta) ---
            # Sivun otsikko
            title_tag = soup.find('title')
            data['page_title'] = title_tag.get_text(strip=True) if title_tag else None

            # Joukkueet (etsi elementit, jotka sisältävät joukkueiden nimet)
            # Tässä oletetaan, että ne ovat esim. span-tageissa tietyllä luokalla
            teams = soup.select('div.match-header .team-name') # TARKISTA OIKEAT LUOKAT
            if len(teams) >= 2:
                data['team_home'] = teams[0].get_text(strip=True)
                data['team_away'] = teams[1].get_text(strip=True)
            else:
                 data['team_home'] = None
                 data['team_away'] = None
                 logger.warning(f"Ei löytynyt odotettua määrää joukkueiden nimiä ID:lle {match_id}")

            # Tulos (jos pelattu)
            score_element = soup.select_one('div.match-header .score') # TARKISTA OIKEA LUOKKA
            data['score'] = score_element.get_text(strip=True) if score_element else None

            # Ottelun päivämäärä ja aika
            # Nämä ovat usein yhdessä tai erillisissä elementeissä
            datetime_element = soup.select_one('.match-datetime') # TARKISTA OIKEA LUOKKA
            data['match_datetime_raw'] = datetime_element.get_text(" ", strip=True) if datetime_element else None
            # Tässä voisi yrittää jäsentää päivämäärän ja ajan erikseen, jos tarpeen

            # Pelipaikka
            venue_element = soup.select_one('.match-venue') # TARKISTA OIKEA LUOKKA
            data['venue'] = venue_element.get_text(strip=True) if venue_element else None

            # --- Yleisömäärä (Käytetään aiempia strategioita, mutta palautetaan None jos ei löydy) ---
            audience = None
            # Strategia 1: Teksti "Yleisö" + numero
            try:
                audience_labels = soup.find_all(string=re.compile(r'yleisö', re.IGNORECASE))
                for label in audience_labels:
                    parent = label.find_parent()
                    if parent:
                        combined_text = parent.get_text(" ", strip=True)
                        match = re.search(r'yleisö\D*(\d+)', combined_text, re.IGNORECASE)
                        if match:
                            audience = int(match.group(1))
                            logger.debug(f"Yleisömäärä löytyi (Strategia 1a): {audience}")
                            break # Lopeta etsintä, kun löytyi

                        # Etsi seuraavista sisaruksista
                        if not audience:
                             next_sibling = parent.find_next_sibling()
                             while next_sibling:
                                 sibling_text = next_sibling.get_text(strip=True)
                                 if sibling_text.isdigit():
                                     audience = int(sibling_text)
                                     logger.debug(f"Yleisömäärä löytyi (Strategia 1b): {audience}")
                                     break
                                 next_sibling = next_sibling.find_next_sibling()
                             if audience: break # Lopeta ulompi silmukka
            except Exception as e:
                logger.warning(f"Virhe yleisömäärän etsinnässä (Strategia 1): {e}")

            # Strategia 2: Tilastoblokit (jos strategia 1 ei tuottanut tulosta)
            if audience is None:
                try:
                    stat_blocks = soup.select('.statistic-item, .stat-block, .match-stat') # TARKISTA LUOKAT
                    for block in stat_blocks:
                        block_text = block.get_text(" ", strip=True)
                        if re.search(r'yleisö', block_text, re.IGNORECASE):
                            match = re.search(r'\b(\d{1,5})\b', block_text) # Etsi 1-5 numeroinen luku sanarajojen sisällä
                            if match:
                                potential_audience = int(match.group(1))
                                # Lisää tarkistus: onko numero uskottava? (Esim. ei vuosiluku)
                                # Tämä raja voi olla liian tiukka, säädä tarvittaessa
                                if 0 <= potential_audience < 100000:
                                    audience = potential_audience
                                    logger.debug(f"Yleisömäärä löytyi (Strategia 2): {audience}")
                                    break
                                else:
                                     logger.debug(f"Hylättiin potentiaalinen yleisömäärä {potential_audience} (epäuskottava).")
                except Exception as e:
                    logger.warning(f"Virhe yleisömäärän etsinnässä (Strategia 2): {e}")

            # Lisää muita strategioita tarvittaessa (esim. taulukot)

            data['audience'] = audience # Tallennetaan None, jos ei löytynyt

            # --- Muut Tilastot (Esimerkki: Pura kaikki taulukot) ---
            # Tämä voi tuottaa paljon dataa, harkitse tarpeen mukaan
            data['tables'] = []
            try:
                 tables = soup.find_all('table')
                 for table in tables:
                      table_data = []
                      headers = [th.get_text(strip=True) for th in table.find_all('th')]
                      rows = table.find_all('tr')
                      for row in rows:
                           cells = [td.get_text(strip=True) for td in row.find_all('td')]
                           if cells: # Älä lisää tyhjiä rivejä (voi olla otsikkorivejä ilman td:tä)
                                table_data.append(dict(zip(headers, cells)) if headers and len(headers) == len(cells) else cells)
                      if table_data: # Lisää vain jos taulukossa oli dataa
                           data['tables'].append(table_data)
                 logger.debug(f"Löytyi ja purettiin {len(data['tables'])} taulukkoa.")
            except Exception as e:
                 logger.warning(f"Virhe taulukoiden purkamisessa: {e}")


            # --- Koko sivun teksti (Viimeinen keino, jos strukturoitu data puuttuu) ---
            # data['full_text'] = soup.get_text(separator='\n', strip=True) # POISTA KOMMENTTI TARVITTAESSA

            logger.debug(f"Datan purku valmis ID:lle {match_id}")
            return data # Palauta kerätty data

        except Exception as e:
            logger.error(f"Kriittinen virhe datan purkamisessa ID:lle {match_id}: {str(e)}")
            # Palauta perustiedot ja virheilmoitus
            return {
                'match_id': match_id,
                'status': 'parsing_error',
                'error_message': str(e),
                'page_title': data.get('page_title'), # Yritä säilyttää edes otsikko
                'audience': None # Varmista, että audience on None virhetilanteessa
            }

    def process_match(self, match_id):
        """Prosessoi yksittäinen ottelu: hae sivu ja pura data"""
        url = BASE_URL.format(match_id=match_id)
        logger.info(f"--- Aloitetaan ottelun {match_id} käsittely ({url}) ---")
        scrape_timestamp = datetime.datetime.now().isoformat() # Aikaleima haun aloitukselle

        try:
            html = self.fetch_page(url)
            if not html:
                logger.error(f"HTML-sisällön haku epäonnistui ID:lle {match_id}")
                # Palauta perustiedot ja virhetila
                return {
                    'match_id': match_id,
                    'url': url,
                    'scrape_timestamp': scrape_timestamp,
                    'status': 'page_load_failed',
                    'audience': None # Lisätään varmuuden vuoksi
                }

            soup = BeautifulSoup(html, 'html.parser')

            # Tallenna debug-tiedostot (HTML) onnistuneesta hausta
            self.save_debug_files(match_id, html, "FETCH_SUCCESS")

            # Pura data sivulta
            extracted_data = self.extract_data(soup, match_id)

            # Lisää/päivitä perustiedot palautettavaan dataan
            extracted_data['url'] = url
            extracted_data['scrape_timestamp'] = scrape_timestamp
            # Määritä status lopullisen datan perusteella (jos extract_data ei jo asettanut virhettä)
            if 'status' not in extracted_data:
                 # Oletetaan onnistuneeksi, jos dataa löytyi edes vähän (esim. otsikko)
                 if extracted_data.get('page_title'):
                      # Tarkista onko tuleva ottelu (esim. ei tulosta, päivämäärä tulevaisuudessa)
                      # Tähän voisi lisätä logiikkaa päivämäärän tarkistamiseksi, jos se saadaan purettua luotettavasti
                      is_future_match = not extracted_data.get('score') and extracted_data.get('match_datetime_raw') # Hyvin karkea arvio
                      if is_future_match:
                           extracted_data['status'] = 'success_future_match'
                      else:
                           extracted_data['status'] = 'success'
                 else:
                      # Jos edes otsikkoa ei löytynyt, merkitään epäonnistuneeksi
                      extracted_data['status'] = 'parsing_failed_no_title'


            # Varmista, että audience on olemassa avaimena (arvo voi olla None)
            if 'audience' not in extracted_data:
                 extracted_data['audience'] = None


            logger.info(f"Ottelun {match_id} käsittely valmis. Tila: {extracted_data.get('status')}, Yleisö: {extracted_data.get('audience')}")
            return extracted_data

        except Exception as e:
            # Tämä kerää odottamattomat virheet itse process_match-funktiossa
            logger.exception(f"Kriittinen virhe käsiteltäessä ottelua {match_id}: {str(e)}")
            return {
                'match_id': match_id,
                'url': url,
                'scrape_timestamp': scrape_timestamp,
                'status': 'critical_error_processing',
                'error_message': str(e),
                'audience': None
            }

    def run(self):
        """Suorita päälogiikka: iteroi ID:t, prosessoi ja tallenna"""
        logger.info(f"Käynnistetään skraperi. Aloitus ID (seuraava): {self.current_id + 1}, Maksimi ID:t tällä ajolla: {MAX_MATCHES}")
        processed_count = 0
        success_count = 0 # Lasketaan onnistuneet haut (status alkaa 'success')
        failed_count = 0 # Lasketaan epäonnistuneet (ei 'success')
        start_time = time.time()

        try:
            while processed_count < MAX_MATCHES:
                # Tarkistetaan negatiiviset ID:t varmuuden vuoksi
                if self.current_id < 0:
                     logger.warning("current_id on negatiivinen, asetetaan 0:ksi.")
                     self.current_id = 0

                next_id_to_process = self.current_id + 1
                logger.info(f"Käsitellään {processed_count + 1}/{MAX_MATCHES} : ID {next_id_to_process}")

                result_data = self.process_match(next_id_to_process)

                # Lisää tulos listaan
                self.match_data.append(result_data)

                # Päivitä laskurit tuloksen statuksen perusteella
                if result_data.get('status', '').startswith('success'):
                    success_count += 1
                else:
                    failed_count += 1
                    # Voit lisätä logiikkaa kriittisiin virheisiin reagointiin, esim. pysäytys
                    # if result_data.get('status') == 'critical_error_processing':
                    #    logger.critical("Kriittinen virhe prosessoinnissa, pysäytetään ajo.")
                    #    break

                # Päivitä viimeksi käsitellyn ID:n numero vasta onnistuneen prosessoinnin jälkeen
                self.current_id = next_id_to_process
                processed_count += 1


                # Tallenna data ja viimeisin ID säännöllisesti (esim. joka 10. ID)
                if processed_count % 10 == 0:
                     logger.info(f"Välitallennus {processed_count} ID:n jälkeen...")
                     self.save_data()
                     self.save_last_id()
                     logger.info(f"Tiedot tallennettu. Viimeisin käsitelty ID: {self.current_id}")


                # Odota ennen seuraavan ID:n käsittelyä (paitsi viimeisen jälkeen)
                if processed_count < MAX_MATCHES:
                     # Käytä pientä satunnaisuutta viiveessä, jos haluat näyttää vähemmän botilta
                     # import random
                     # wait_time = REQUEST_DELAY + random.uniform(0, 1)
                     wait_time = REQUEST_DELAY
                     logger.debug(f"Odotetaan {wait_time:.2f} sekuntia...")
                     time.sleep(wait_time)

        except KeyboardInterrupt:
             logger.warning("Käyttäjä keskeytti ajon (KeyboardInterrupt).")
        except Exception as e:
            # Kerää odottamattomat virheet pääsilmukasta
            logger.exception(f"Pääsilmukan odottamaton virhe: {str(e)}")
        finally:
            # Tallenna aina lopuksi, riippumatta siitä, miten silmukka päättyi
            logger.info("Tallennetaan lopulliset tiedot...")
            self.save_data()
            # Tallenna viimeisin onnistuneesti KÄSITELTY ID
            self.save_last_id()

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"--- Skrapausajo valmis ---")
            logger.info(f"Kesto: {duration:.2f} sekuntia")
            logger.info(f"Käsiteltyjä ID:itä yritti: {processed_count}")
            logger.info(f"Onnistuneita hakuja (status 'success*'): {success_count}")
            logger.info(f"Epäonnistuneita/muita tiloja: {failed_count}")
            logger.info(f"Viimeisin käsitelty ID: {self.current_id}") # Tämä on nyt viimeisin onnistunut
            logger.info(f"Data tallennettu tiedostoon: {OUTPUT_FILE}")
            logger.info(f"Viimeisin ID tallennettu tiedostoon: {LAST_ID_FILE}")


if __name__ == '__main__':
    scraper = MatchDataScraper()
    scraper.run()
    logger.info("Skraperin suoritus päättyi.")
