def fetch_match_data(match_id):
    """Hae yksittäisen ottelun data ja tallenna kaikki teksti"""
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
    
    # Tallenna kaikki teksti
    text_content = soup.get_text(separator='\n', strip=True)
    debug_text_path = os.path.join(CACHE_DIR, f'match_{match_id}_text.txt')
    with open(debug_text_path, 'w', encoding='utf-8') as f:
        f.write(text_content)
    
    # Tallenna raaka HTML
    debug_html_path = os.path.join(CACHE_DIR, f'match_{match_id}_raw.html')
    with open(debug_html_path, 'w', encoding='utf-8') as f:
        f.write(str(soup.prettify()))
    
    return soup

def extract_audience_number(soup):
    """Etsi yleisömäärä ja kirjaa kaikki löydetyt tiedot"""
    # Kirjaa koko tekstisisältö
    full_text = soup.get_text(separator=' ', strip=True)
    logger.debug(f"Koko sivun teksti: {full_text[:500]}...")  # Kirjaa ensimmäiset 500 merkkiä
    
    # Alkuperäinen logiikka + lisätty kaikkien numeroiden tallennus
    numbers_found = re.findall(r'\b\d+\b', full_text)
    logger.debug(f"Kaikki löydetyt numerot: {numbers_found}")
    
    # Lisätään uusi debug-strategia
    audience_numbers = []
    
    # Strategia 1-4 pysyvät ennallaan...
    
    # Uusi strategia 5: Tallenna kaikki löydetyt numerot
    valid_numbers = [int(n) for n in numbers_found if 100 <= int(n) <= 50000]
    if valid_numbers:
        counts = Counter(valid_numbers)
        most_common = counts.most_common(3)
        logger.debug(f"Yleisimmät numerot: {most_common}")
        audience_numbers.extend([num for num, count in most_common])
    
    # Valitse paras arvio
    if audience_numbers:
        return max(audience_numbers)
    
    logger.warning("Yleisömäärää ei löytynyt, tallennetaan kaikki data")
    return None

def paivita_yleisodata():
    """Päivitä data ja tallenna kaikki yritykset"""
    logger.info("Aloitetaan yleisömäärien haku")
    
    viimeisin_id = hae_viimeisin_id()
    nykyinen_id = viimeisin_id + 1
    yleisodata = lataa_data()
    max_otteluita = 100
    
    for _ in range(max_otteluita):
        logger.info(f"Käsitellään ID: {nykyinen_id}")
        
        # Hae data ja tallenna kaikki tiedot
        match_data = fetch_match_data(nykyinen_id)
        
        if not match_data:
            # Tallennetaan myös virheet
            yleisodata.append({
                'ottelu_id': nykyinen_id,
                'status': 'ei_sivua',
                'hakuhetki': datetime.datetime.now().isoformat()
            })
            nykyinen_id += 1
            continue
        
        if not is_valid_stats_page(match_data):
            yleisodata.append({
                'ottelu_id': nykyinen_id,
                'status': 'virheellinen_sivu',
                'hakuhetki': datetime.datetime.now().isoformat()
            })
            nykyinen_id += 1
            continue
        
        yleisomaara = extract_audience_number(match_data)
        
        # Tallennetaan kaikki saatavilla oleva data
        otteludata = {
            'ottelu_id': nykyinen_id,
            'yleisomaara': yleisomaara,
            'hakuhetki': datetime.datetime.now().isoformat(),
            'url': BASE_URL.format(match_id=nykyinen_id),
            'status': 'onnistui' if yleisomaara else 'epäonnistui'
        }
        
        yleisodata.append(otteludata)
        tallenna_viimeisin_id(nykyinen_id)
        nykyinen_id += 1
        
        time.sleep(2)
    
    tallenna_data(yleisodata)
    logger.info(f"Tallennettiin {len(yleisodata)} ottelua")

# Muuta loggauksen taso debug-tilaan
logging.basicConfig(
    level=logging.DEBUG,  # Muutettu INFO -> DEBUG
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audience_scraper.log"),
        logging.StreamHandler()
    ]
)
