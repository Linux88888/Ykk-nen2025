
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
    level=logging.DEBUG,  # Käytä DEBUG-tasoa nähdäksesi enemmän tietoa
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audience_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Asetukset
BASE_URL = "https://tulospalvelu.palloliitto.fi/match/{match_id}/stats"
START_ID = 3748452  # Voit muuttaa tätä tarvittaessa
MAX_MATCHES = 100  # Kuinka monta ID:tä käsitellään per ajo
REQUEST_DELAY = 2  # Sekuntia sivujen välillä
CACHE_DIR = "audience_cache"
OUTPUT_FILE = "audience_data.json"
LAST_ID_FILE = "last_audience_id.txt"

# Alusta hakemistot
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class AudienceScraper:
    def __init__(self):
        # self.driver poistettu - driveria hallitaan nyt fetch_page:ssa
        self.current_id = self.load_last_id()
        self.audience_data = self.load_data()

    # UUSI: Apufunktio driverin alustamiseen paikallisesti fetch_page:ssa
    def setup_driver_local(self):
        """Alusta Selenium WebDriver ja palauta instanssi"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        # Lisää argumentti, joka voi auttaa piilottamaan automaation joiltakin sivustoilta
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            # Käytä Service-objektia piilottaaksesi webdriverin lokit konsolista
            service = Service(ChromeDriverManager().install(), log_output=os.devnull)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(45) # Nostettu timeout-aikaa hieman
            # Lisäyritys piilottaa automaatio
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"Selaimen alustus epäonnistui: {str(e)}")
            # Kokeile yksinkertaisempaa alustusta fallbackina
            try:
                logger.info("Yritetään yksinkertaisempaa driverin alustusta...")
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(45)
                return driver
            except Exception as e2:
                 logger.critical(f"Driverin alustus epäonnistui täysin: {e2}")
                 raise

    def load_last_id(self):
        """Lataa viimeisin käsitelty ID"""
        try:
            if os.path.exists(LAST_ID_FILE):
                with open(LAST_ID_FILE, 'r') as f:
                    last_id = int(f.read().strip())
                    logger.info(f"Ladatty viimeisin ID: {last_id}")
                    return last_id
            logger.info(f"Ei löytynyt last_audience_id.txt-tiedostoa, aloitetaan ID:stä {START_ID - 1}")
            return START_ID - 1
        except Exception as e:
            logger.error(f"Virhe ladattaessa viimeisintä ID:tä tiedostosta {LAST_ID_FILE}: {str(e)}")
            return START_ID - 1

    def save_last_id(self):
        """Tallenna nykyinen ID"""
        try:
            with open(LAST_ID_FILE, 'w') as f:
                f.write(str(self.current_id))
            logger.info(f"Tallennettu viimeisin ID: {self.current_id} tiedostoon {LAST_ID_FILE}")
        except Exception as e:
            logger.error(f"Virhe tallennettaessa ID:tä tiedostoon {LAST_ID_FILE}: {str(e)}")

    def load_data(self):
        """Lataa olemassa oleva data"""
        try:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Ladatty {len(data)} tietuetta tiedostosta {OUTPUT_FILE}")
                    return data
            logger.info(f"Ei löytynyt {OUTPUT_FILE}-tiedostoa, aloitetaan tyhjästä listasta.")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Virhe ladattaessa JSON-dataa tiedostosta {OUTPUT_FILE}: {str(e)}. Aloitetaan tyhjästä listasta.")
            return []
        except Exception as e:
            logger.error(f"Yleinen virhe ladattaessa dataa tiedostosta {OUTPUT_FILE}: {str(e)}")
            return []

    def save_data(self):
        """Tallenna data JSON-muodossa"""
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.audience_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Tallennettu {len(self.audience_data)} tietuetta tiedostoon {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"Virhe tallennettaessa dataa tiedostoon {OUTPUT_FILE}: {str(e)}")

    # MUOKATTU: fetch_page käyttää nyt paikallista driveria ja robustimpaa logiikkaa
    def fetch_page(self, url):
        """Hae sivu Seleniumilla (parannettu driverin hallinta ja odotus)"""
        driver = None # Käytä paikallista muuttujaa driverille tässä funktiossa
        for attempt in range(1, 4): # Yritä 3 kertaa
            try:
                logger.debug(f"fetch_page yritys {attempt}/3 URL: {url}")
                # Alusta driver JOKAISELLA yrityksellä
                driver = self.setup_driver_local()
                if not driver: # Jos alustus epäonnistui setup_driver_local:ssa
                    logger.error("Driverin alustus epäonnistui setup_driver_localissa, ei voida jatkaa tätä yritystä.")
                    if attempt < 3:
                         time.sleep(5) # Odota ennen seuraavaa yritystä
                         continue
                    else:
                         return None # Kaikki yritykset epäonnistuivat

                driver.get(url)
                logger.debug(f"Sivu {url} avattu yrityksellä {attempt}")

                # --- ODOTUSSTRATEGIA ---
                # Kokeile ensin staattista odotusta. Jos tämä ei toimi luotettavasti,
                # voit kokeilla WebDriverWait odottamaan jotain muuta elementtiä,
                # jonka tiedät varmasti latautuvan sivulle. Esim:
                # WebDriverWait(driver, 30).until(
                #     EC.presence_of_element_located((By.CSS_SELECTOR, '.match-details-container')) # Tarkista oikea luokka selaimella!
                # )
                logger.debug(f"Odotetaan staattisesti 10 sekuntia sivun latautumista...")
                time.sleep(10)

                # Vieritä alas varmistaaksesi, että kaikki (lazy-loaded) sisältö latautuu
                logger.debug("Skrollataan sivun alaosaan...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3) # Anna hieman aikaa skrollauksen jälkeisille latauksille

                page_source = driver.page_source
                logger.debug(f"Sivun lähdekoodi haettu (pituus: {len(page_source)} merkkiä)")

                # Tarkista sivun pituus - hyvin lyhyt sivu voi olla virhesivu
                if len(page_source) < 2000: # Voit säätää tätä rajaa tarvittaessa
                     logger.warning(f"Sivu {url} vaikuttaa lyhyeltä (koko: {len(page_source)}), mahdollinen virhe. Yritetään uudelleen...")
                     if attempt < 3: # Jos ei viimeinen yritys
                         # Ei tarvita ylimääräistä odotusta tässä, koska finally-lohko hoitaa sen
                         continue # Siirry seuraavaan yritykseen (finally suoritetaan ensin)
                     else:
                         logger.error("Sivu jäi lyhyeksi viimeiselläkin yrityksellä.")
                         # Tallenna lyhyt sivu debuggausta varten
                         self.save_debug_files(url.split('/')[-2], page_source, "LYHYT_SIVU")
                         return None

                # Jos kaikki meni hyvin tähän asti, palauta sivun lähdekoodi
                logger.info(f"Sivun {url} haku onnistui yrityksellä {attempt}")
                return page_source

            except TimeoutException:
                logger.warning(f"TimeoutException yrityksellä {attempt}/3 haettaessa {url}")
            except WebDriverException as e:
                 logger.error(f"WebDriverException yrityksellä {attempt}/3 haettaessa {url}: {str(e)}")
                 # Jos virhe on "net::ERR_CONNECTION_REFUSED" tms., odotus ja uudelleenyritys voi auttaa
            except Exception as e:
                logger.error(f"Yleinen virhe sivun haussa yrityksellä {attempt}/3 ({url}): {type(e).__name__} - {str(e)}")
            finally:
                # Sulje driver JOKAISEN yrityksen jälkeen, onnistui tai ei
                if driver:
                    logger.debug(f"Suljetaan driver yrityksen {attempt} jälkeen.")
                    driver.quit()
                # Pieni tauko ennen seuraavaa yritystä (jos on) tai seuraavaa ID:tä
                if attempt < 3:
                    logger.debug(f"Odotetaan {REQUEST_DELAY + attempt} sekuntia ennen seuraavaa yritystä...")
                    time.sleep(REQUEST_DELAY + attempt) # Lisää odotusaikaa epäonnistuneiden yritysten jälkeen


        logger.error(f"Sivun {url} haku epäonnistui kaikkien 3 yrityksen jälkeen")
        return None

    def save_debug_files(self, match_id, html, text):
        """Tallenna debug-tiedostot"""
        try:
            # Varmista, että match_id on merkkijono
            match_id_str = str(match_id)
            # HTML
            html_filename = f"{match_id_str}_page_debug.html"
            html_path = os.path.join(CACHE_DIR, html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(str(html)) # Varmistetaan että kirjoitetaan merkkijono
            logger.debug(f"Tallennettu debug HTML: {html_path}")

            # Teksti
            text_filename = f"{match_id_str}_text_debug.txt"
            text_path = os.path.join(CACHE_DIR, text_filename)
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(str(text)) # Varmistetaan että kirjoitetaan merkkijono
            logger.debug(f"Tallennettu debug teksti: {text_path}")

        except Exception as e:
            logger.error(f"Debug-tiedostojen tallennus epäonnistui (ID: {match_id_str}): {str(e)}")

    def extract_audience(self, soup, match_id):
        """Etsi yleisömäärä sivulta käyttäen useita strategioita"""
        logger.debug(f"Aloitetaan yleisömäärän etsintä ID:lle {match_id}")

        # --- Strategia 1: Etsi elementti, jossa on teksti "Yleisö" ja sen jälkeen numero ---
        try:
            # Etsi kaikki elementit, joiden teksti sisältää "Yleisö" (case-insensitive)
            audience_labels = soup.find_all(string=re.compile(r'yleisö', re.IGNORECASE))
            logger.debug(f"Löytyi {len(audience_labels)} elementtiä tekstillä 'yleisö'")
            for label in audience_labels:
                # Etsi seuraava sibling tai parentin seuraava sibling, joka sisältää numeron
                potential_value_element = None
                # Kokeile ensin parentin tasolla, jos label on esim. <span> tagissa
                parent = label.find_parent()
                if parent:
                    # Etsi numerollinen teksti parentista tai sen jälkeisistä siblingeista
                    combined_text = parent.get_text(" ", strip=True)
                    match = re.search(r'yleisö\D*(\d+)', combined_text, re.IGNORECASE)
                    if match:
                        audience = int(match.group(1))
                        logger.info(f"Strategia 1 (Parent text): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                        return audience

                    # Jos ei löytynyt parentista, etsi seuraavista siblingeista
                    next_sibling = parent.find_next_sibling()
                    while next_sibling:
                        sibling_text = next_sibling.get_text(strip=True)
                        if sibling_text.isdigit():
                            audience = int(sibling_text)
                            logger.info(f"Strategia 1 (Next Sibling): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                            return audience
                        # Kokeile myös jos numero on osa tekstiä siblingissa
                        match_in_sibling = re.search(r'^(\d+)$', sibling_text)
                        if match_in_sibling:
                           audience = int(match_in_sibling.group(1))
                           logger.info(f"Strategia 1 (Next Sibling Text): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                           return audience
                        next_sibling = next_sibling.find_next_sibling()

        except Exception as e:
            logger.warning(f"Virhe Strategiassa 1 (Yleisö-teksti): {str(e)}")

        # --- Strategia 2: Etsi tilasto-blokkeja (yleinen tapa esittää dataa) ---
        try:
            # Nämä luokat ovat yleisiä tilastosivuilla, tarkista oikeat luokat selaimella!
            stat_blocks = soup.select('.statistic-item, .stat-block, .match-stat')
            logger.debug(f"Löytyi {len(stat_blocks)} potentiaalista tilastoblokkia (Strategia 2)")
            for block in stat_blocks:
                block_text = block.get_text(" ", strip=True)
                # Etsi "Yleisö" ja numero samasta blokista
                if re.search(r'yleisö', block_text, re.IGNORECASE):
                    match = re.search(r'(\d+)', block_text) # Etsi mikä tahansa numero blokista
                    if match:
                        audience = int(match.group(1))
                        # Lisätarkistus: onko numero uskottava yleisömäärä?
                        if 50 < audience < 50000: # Estää esim. vuosilukujen poimimisen
                           logger.info(f"Strategia 2 (Stat Block): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                           return audience
                        else:
                           logger.debug(f"Hylättiin Strategia 2 löydös {audience}, ei uskottava yleisömäärä.")
        except Exception as e:
             logger.warning(f"Virhe Strategiassa 2 (Tilastoblokit): {str(e)}")

        # --- Strategia 3: Etsi taulukoista ---
        try:
            tables = soup.find_all('table')
            logger.debug(f"Löytyi {len(tables)} taulukkoa (Strategia 3)")
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        # Etsi solu, joka sisältää "Yleisö"
                        for i, cell in enumerate(cells):
                            cell_text = cell.get_text(" ", strip=True)
                            if re.search(r'yleisö', cell_text, re.IGNORECASE):
                                # Yritä löytää numero samasta solusta tai seuraavasta solusta
                                match_in_cell = re.search(r'(\d+)', cell_text)
                                if match_in_cell:
                                    audience = int(match_in_cell.group(1))
                                    logger.info(f"Strategia 3 (Table - Same Cell): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                                    return audience
                                elif i + 1 < len(cells):
                                    next_cell_text = cells[i+1].get_text(strip=True)
                                    if next_cell_text.isdigit():
                                        audience = int(next_cell_text)
                                        logger.info(f"Strategia 3 (Table - Next Cell): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                                        return audience
                                break # Siirry seuraavaan riviin, jos Yleisö-label löytyi tästä rivistä
        except Exception as e:
            logger.warning(f"Virhe Strategiassa 3 (Taulukot): {str(e)}")

        # --- Strategia 4: Etsi numeroita koko tekstisisällöstä (Viimeinen keino) ---
        # Tämä on epätarkin, käytä varoen
        try:
            full_text = soup.get_text(" ", strip=True)
            # Etsi 3-5 numeroisia lukuja, jotka esiintyvät "yleisö"-sanan läheisyydessä
            potential_matches = re.findall(r'yleisö\D{0,20}(\d{3,5})|(\d{3,5})\D{0,20}yleisö', full_text, re.IGNORECASE)
            logger.debug(f"Löytyi {len(potential_matches)} potentiaalista osumaa Strategialla 4")
            if potential_matches:
                 for match_tuple in potential_matches:
                      # re.findall palauttaa tupleja, jos ryhmiä käytetään | kanssa
                      num_str = next((s for s in match_tuple if s), None) # Ota ensimmäinen ei-tyhjä numero
                      if num_str:
                           audience = int(num_str)
                           # Varmistus: Onko luku järkevä?
                           if 100 < audience < 30000: # Tiukempi raja tälle strategialle
                                logger.info(f"Strategia 4 (Text Proximity): Löydetty yleisömäärä {audience} ID:lle {match_id}")
                                return audience
                           else:
                                logger.debug(f"Hylättiin Strategia 4 löydös {audience}, ei uskottava yleisömäärä.")

        except Exception as e:
            logger.warning(f"Virhe Strategiassa 4 (Tekstihaku): {str(e)}")


        logger.warning(f"Ei löytynyt yleisömäärää ID:lle {match_id} millään strategialla.")
        return None


    def process_match(self, match_id):
        """Prosessoi yksittäinen ottelu"""
        url = BASE_URL.format(match_id=match_id)
        logger.info(f"--- Aloitetaan ottelun {match_id} käsittely ({url}) ---")

        try:
            html = self.fetch_page(url)
            if not html:
                logger.error(f"HTML-sisällön haku epäonnistui ID:lle {match_id}")
                return {'status': 'page_load_failed', 'audience': None}

            soup = BeautifulSoup(html, 'html.parser')
            text_content = soup.get_text(separator='\n', strip=True)

            # Tallenna debug-tiedostot AINA, jotta voidaan tutkia miksi yleisömäärää ei löydy
            self.save_debug_files(match_id, html, text_content)

            # Tarkista validius (tätä voi keventää, jos sivut ovat usein valideja mutta data puuttuu)
            # if not self.is_valid_page(soup):
            #     logger.warning(f"Sivu {match_id} ei vaikuta validilta ottelusivulta.")
            #     return {'status': 'invalid_page', 'audience': None}

            # Etsi yleisömäärä käyttäen parannettuja strategioita
            audience = self.extract_audience(soup, match_id)

            status = 'success' if audience is not None else 'no_audience_found'
            logger.info(f"Ottelun {match_id} käsittely valmis. Tila: {status}, Yleisö: {audience}")
            return {
                'status': status,
                'audience': audience
            }

        except Exception as e:
            logger.exception(f"Kriittinen virhe käsiteltäessä ottelua {match_id}: {str(e)}")
            return {'status': 'critical_error', 'audience': None}

    def is_valid_page(self, soup):
        """Tarkista onko sivu validi ottelusivu (KEVENNETTY TARKISTUS)"""
        # Riittääkö, että sivulla on jokin tilastoihin viittaava elementti?
        # Voit laajentaa tätä tarvittaessa.
        has_stats_keyword = soup.find(string=re.compile(r'tilastot|statistics', re.I))
        has_table = soup.find('table')
        # logger.debug(f"is_valid_page check: has_stats_keyword={bool(has_stats_keyword)}, has_table={bool(has_table)}")
        # Palautetaan True, jos edes jokin viittaa dataan, koska pääfokus on yleisömäärässä
        return bool(has_stats_keyword or has_table)


    def run(self):
        """Suorita päälogiikka"""
        logger.info(f"Käynnistetään skraper. Aloitus ID: {self.current_id + 1}, Maksimi ID:t tällä ajolla: {MAX_MATCHES}")
        processed_count = 0
        found_count = 0
        failed_count = 0
        start_time = time.time()

        try:
            # Driverin alustusta ei enää tarvita tässä
            # self.setup_driver() poistettu

            while processed_count < MAX_MATCHES:
                self.current_id += 1
                logger.info(f"Käsitellään {processed_count + 1}/{MAX_MATCHES} : ID {self.current_id}")
                result = self.process_match(self.current_id)

                # Tallenna tulos aina, vaikka yleisöä ei löytyisikään
                entry = {
                    'match_id': self.current_id,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'url': BASE_URL.format(match_id=self.current_id),
                    'status': result['status'],
                    'audience': result['audience'] # On None jos ei löytynyt
                }
                self.audience_data.append(entry)

                processed_count += 1
                if result['status'] == 'success':
                    found_count += 1
                elif result['status'] in ['page_load_failed', 'critical_error', 'invalid_page']:
                    failed_count +=1
                    # Voit päättää, haluatko pysähtyä kriittisiin virheisiin vai jatkaa
                    # Esimerkiksi:
                    # if result['status'] == 'critical_error':
                    #    logger.error("Kriittinen virhe havaittu, pysäytetään ajo.")
                    #    break

                # Tallenna data ja ID säännöllisesti (esim. joka 10. ottelu)
                if processed_count % 10 == 0:
                     logger.info(f"Välitallennus {processed_count} ottelun jälkeen...")
                     self.save_data()
                     self.save_last_id()

                # Odota ennen seuraavan ID:n käsittelyä (paitsi viimeisen jälkeen)
                if processed_count < MAX_MATCHES:
                     time.sleep(REQUEST_DELAY)

        except KeyboardInterrupt:
             logger.warning("Käyttäjä keskeytti ajon (KeyboardInterrupt).")
        except Exception as e:
            logger.exception(f"Päälogiikan odottamaton virhe: {str(e)}")
        finally:
            # Driverin sulkua ei enää tarvita tässä
            # if self.driver: self.driver.quit() poistettu

            # Tallenna aina lopuksi
            logger.info("Tallennetaan lopulliset tiedot...")
            self.save_data()
            # Tallenna viimeisin KÄSITELTY ID, vaikka se olisi epäonnistunut
            self.save_last_id()

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"--- Skrapausajo valmis ---")
            logger.info(f"Kesto: {duration:.2f} sekuntia")
            logger.info(f"Käsiteltyjä ID:itä yhteensä: {processed_count}")
            logger.info(f"Yleisömääriä löytyi: {found_count}")
            logger.info(f"Epäonnistuneita hakuja/virheitä: {failed_count}")
            logger.info(f"Viimeisin käsitelty ID: {self.current_id}")
            logger.info(f"Data tallennettu tiedostoon: {OUTPUT_FILE}")
            logger.info(f"Viimeisin ID tallennettu tiedostoon: {LAST_ID_FILE}")


if __name__ == '__main__':
    scraper = AudienceScraper()
    scraper.run()
    logger.info("Skraperin suoritus päättyi.")