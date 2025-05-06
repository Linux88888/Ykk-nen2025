import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
# from sklearn.cluster import KMeans # Ei käytössä, voidaan poistaa jos ei tarvita
# from sklearn.preprocessing import StandardScaler # Ei käytössä
# from sklearn.linear_model import LinearRegression # Ei käytössä
# from sklearn.model_selection import train_test_split # Ei käytössä
import datetime
# import calendar # Ei suoraan käytössä, datetime hoitaa vastaavat
import os
import warnings
import json 
import re # Lisätty re-moduuli
from datetime import timedelta

# Suppress warning messages
warnings.filterwarnings('ignore')

# Configuration
DEBUG = False # Aseta Trueksi saadaksesi enemmän debug-tulostetta
OUTPUT_DIR = "output"
PLOTS_DIR = os.path.join(OUTPUT_DIR, "plots")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
# MODELS_DIR = os.path.join(OUTPUT_DIR, "models") # Ei käytössä, voidaan poistaa

# Create output directories
for directory in [OUTPUT_DIR, PLOTS_DIR, DATA_DIR]: # Poistettu MODELS_DIR
    os.makedirs(directory, exist_ok=True)

# Set visualization styles
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("viridis")

def debug_print(message):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"DEBUG: {message}")

def load_data(filepath):
    """Load match data from JSON file"""
    try:
        # Varmistetaan, että tiedosto on olemassa ennen lukua
        if not os.path.exists(filepath):
            print(f"Error: Data file not found at {filepath}")
            return None
        if os.path.getsize(filepath) == 0: # Tarkistetaan onko tiedosto tyhjä
            print(f"Warning: Data file at {filepath} is empty. Returning None.")
            return None

        df = pd.read_json(filepath, orient='records', encoding='utf-8') # Lisätty encoding
        if df.empty:
             debug_print(f"Data loaded from {filepath} is empty (no records). This might be expected if no data was scraped or all scraped data was filtered out.")
        else:
            debug_print(f"Data loaded successfully from {filepath}. Shape: {df.shape}")
        return df
    except FileNotFoundError: # Tämä on jo tarkistettu, mutta pidetään varalta
        print(f"Error: Data file not found at {filepath}")
        return None
    except ValueError as ve: 
        print(f"Error: Could not parse JSON from {filepath}. It might be malformed or not a list of records. Error: {ve}")
        # Yritä lukea tiedoston sisältö debuggausta varten
        try:
            with open(filepath, 'r', encoding='utf-8') as f_err:
                debug_print(f"Content of malformed JSON file ({filepath}):\n{f_err.read(500)}...") # Lue vain alku
        except Exception as read_err:
            debug_print(f"Could not read content of malformed file {filepath}: {read_err}")
        return None
    except Exception as e:
        print(f"Error loading data from {filepath}: {e}")
        return None

def preprocess_data(df):
    """Clean and preprocess the data"""
    if df is None or df.empty:
        print("Error: Input DataFrame is None or empty in preprocess_data.")
        return None
    processed_df = df.copy()

    # Poista rivit, joissa match_id on NaN (jos sellaisia jostain syystä ilmenee)
    if 'match_id' in processed_df.columns:
        original_row_count = len(processed_df)
        processed_df.dropna(subset=['match_id'], inplace=True)
        if len(processed_df) < original_row_count:
            debug_print(f"Removed {original_row_count - len(processed_df)} rows with missing match_id.")
    
    # Varmista, että match_id on integer-tyyppinen
    if 'match_id' in processed_df.columns:
        processed_df['match_id'] = pd.to_numeric(processed_df['match_id'], errors='coerce').astype('Int64')


    # Sarakkeiden uudelleennimeäminen
    rename_map = {
        'score': 'Tulos',
        'team_home': 'Koti',
        'team_away': 'Vieras',
        'audience': 'Yleisö',
        'venue': 'Stadion',
        'match_datetime_raw': 'PvmAikaRaw',
        'match_status_raw': 'OttelunTilaRaaka',
        'scrape_timestamp': 'HakuAikaleima'
        # Lisää muita tarvittaessa
    }
    # Uudelleennimeä vain olemassa olevat sarakkeet
    processed_df.rename(columns={k: v for k, v in rename_map.items() if k in processed_df.columns}, inplace=True)
    debug_print(f"Columns after renaming: {processed_df.columns.tolist()}")

    # Pvm ja Aika -sarakkeiden alustus
    processed_df['Pvm'] = pd.NaT # Käytä NaT (Not a Time) oletuksena päivämäärille
    processed_df['Aika'] = None

    if 'PvmAikaRaw' in processed_df.columns:
        # Erotellaan aika ja päivämäärä, jos PvmAikaRaw sisältää '|'
        # Oletetaan formaatti "HH:MM | Viikonpäivä DD.MM." tai "HH:MM | Viikonpäivä DD.MM.YYYY"
        # Tai "HH:MM | DD.MM.YYYY"
        temp_dt_series = processed_df['PvmAikaRaw'].astype(str).str.split('|', n=1, expand=True)
        
        if not temp_dt_series.empty:
            processed_df['Aika'] = temp_dt_series[0].str.strip()
            if temp_dt_series.shape[1] > 1: # Jos myös päivämääräosa löytyi
                # Yritä poimia päivämäärä DD.MM.YYYY tai DD.MM.YY tai DD.MM.
                # Poista ensin mahdollinen viikonpäivä
                date_part_cleaned = temp_dt_series[1].str.strip().str.replace(r'^[A-Za-zÄÖÅäöå]+\s+', '', regex=True)
                # Poista piste lopusta, jos se on siellä yksinään
                date_part_cleaned = date_part_cleaned.str.rstrip('.')
                processed_df['Pvm'] = date_part_cleaned
        else: # Jos '|' ei löytynyt, yritä arvata onko kyseessä aika vai pvm
             time_like = processed_df['PvmAikaRaw'].str.match(r'^\d{1,2}:\d{2}$')
             date_like = processed_df['PvmAikaRaw'].str.contains(r'\d{1,2}\.\d{1,2}')
             if time_like is not None: processed_df.loc[time_like, 'Aika'] = processed_df.loc[time_like, 'PvmAikaRaw']
             if date_like is not None: processed_df.loc[date_like, 'Pvm'] = processed_df.loc[date_like, 'PvmAikaRaw']
        
        debug_print(f"Aika parsing from PvmAikaRaw: {processed_df['Aika'].notna().sum()} valid entries.")
        debug_print(f"Pvm parsing from PvmAikaRaw: {processed_df['Pvm'].notna().sum()} valid entries.")


    # Maalien purku tuloksesta
    processed_df['home_goals'] = pd.NA # Käytä pandasin NA-arvoa numeerisille puuttuville
    processed_df['away_goals'] = pd.NA
    if 'Tulos' in processed_df.columns:
        # Pura vain jos Tulos ei ole NaN ja sisältää viivan
        valid_scores = processed_df['Tulos'].notna() & processed_df['Tulos'].astype(str).str.contains('–')
        score_parts = processed_df.loc[valid_scores, 'Tulos'].astype(str).str.split('–', n=1, expand=True)
        if not score_parts.empty:
            processed_df.loc[valid_scores, 'home_goals'] = pd.to_numeric(score_parts[0].str.strip(), errors='coerce')
            if score_parts.shape[1] > 1:
                 processed_df.loc[valid_scores, 'away_goals'] = pd.to_numeric(score_parts[1].str.strip(), errors='coerce')
    
    processed_df['home_goals'] = processed_df['home_goals'].astype('Int64') # Käytä Int64, joka tukee NA:ta
    processed_df['away_goals'] = processed_df['away_goals'].astype('Int64')
    debug_print(f"Home goals parsed: {processed_df['home_goals'].notna().sum()} valid entries.")
    debug_print(f"Away goals parsed: {processed_df['away_goals'].notna().sum()} valid entries.")

    # Kokonaismaalit
    processed_df['total_goals'] = processed_df['home_goals'].fillna(0) + processed_df['away_goals'].fillna(0)
    # Jos jompikumpi maaleista oli alunperin NA, total_goals pitäisi myös olla NA
    processed_df.loc[processed_df['home_goals'].isna() | processed_df['away_goals'].isna(), 'total_goals'] = pd.NA
    processed_df['total_goals'] = processed_df['total_goals'].astype('Int64')


    # Ottelun tulos (koti, vieras, tasapeli)
    conditions = [
        (processed_df['home_goals'] > processed_df['away_goals']),
        (processed_df['home_goals'] < processed_df['away_goals']),
        (processed_df['home_goals'] == processed_df['away_goals']) & (processed_df['home_goals'].notna()) # Varmista että maalit ei ole NA
    ]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None) # None jos maaleja ei ole tai ne ovat NA

    # Luo match_datetime yhdistämällä Pvm ja Aika
    processed_df['match_datetime'] = pd.NaT
    # Yhdistä vain jos sekä Pvm että Aika ovat validit merkkijonot
    valid_pvm = processed_df['Pvm'].notna() & (processed_df['Pvm'] != '')
    valid_aika = processed_df['Aika'].notna() & (processed_df['Aika'] != '')
    
    if valid_pvm.any() and valid_aika.any():
        # Yritä muuttaa Pvm saraketta datetimeksi, olettaen formaatin DD.MM.YYYY tai DD.MM.YY tai DD.MM.
        # Lisätään oletusvuosi, jos se puuttuu ja se on DD.MM. muotoa
        def parse_flexible_date(date_str):
            if pd.isna(date_str): return pd.NaT
            # Kokeile yleisimpiä formaatteja
            for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m."): # Lisätty piste loppuun
                try:
                    dt_obj = datetime.datetime.strptime(str(date_str).strip(), fmt)
                    # Jos vuosi on pelkkä DD.MM. -> lisää kuluva vuosi
                    if fmt == "%d.%m.":
                        dt_obj = dt_obj.replace(year=datetime.datetime.now().year)
                    return dt_obj
                except ValueError:
                    continue
            return pd.NaT # Palauta NaT jos mikään formaatti ei täsmää

        temp_date_series = processed_df.loc[valid_pvm, 'Pvm'].apply(parse_flexible_date)
        
        # Yhdistä päivämäärä ja aika
        # Varmista, että yhdistettävät sarakkeet ovat oikeaa tyyppiä
        datetime_combined_str = temp_date_series.dt.strftime('%Y-%m-%d').fillna('') + ' ' + processed_df.loc[valid_aika, 'Aika'].fillna('')
        datetime_combined_str = datetime_combined_str.str.strip() # Poista ylimääräiset välilyönnit

        # Muunna yhdistetty merkkijono datetime-objektiksi
        # Olettaa, että Aika on HH:MM
        processed_df.loc[valid_pvm & valid_aika, 'match_datetime'] = pd.to_datetime(
            datetime_combined_str.loc[valid_pvm & valid_aika], 
            format='%Y-%m-%d %H:%M', errors='coerce' # errors='coerce' muuttaa virheelliset NaT:ksi
        )
        debug_print(f"Match_datetime created for {processed_df['match_datetime'].notna().sum()} entries.")


    # Pura päivämäärä- ja aikaosia match_datetime-sarakkeesta
    processed_df['date'] = processed_df['match_datetime'].dt.date
    processed_df['year'] = processed_df['match_datetime'].dt.year.astype('Int64')
    processed_df['month'] = processed_df['match_datetime'].dt.month.astype('Int64')
    processed_df['day'] = processed_df['match_datetime'].dt.day.astype('Int64')
    processed_df['weekday'] = processed_df['match_datetime'].dt.weekday.astype('Int64') # Ma=0, Su=6
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['hour'] = processed_df['match_datetime'].dt.hour.astype('Int64')
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    
    # Yleisömäärä
    if 'Yleisö' in processed_df.columns:
        processed_df['attendance'] = pd.to_numeric(processed_df['Yleisö'], errors='coerce').astype('Int64')
    else:
        debug_print("Warning: 'Yleisö' column not found for attendance processing.")
        processed_df['attendance'] = pd.NA # Luo sarake Int64 NA-arvoilla

    # Poista rivit, joissa kriittistä dataa puuttuu analyysia varten
    # Esim. jos tulosta, koti/vierasjoukkuetta tai päivämäärää ei ole, rivi voi olla hyödytön
    essential_cols_for_dropna = ['Koti', 'Vieras', 'home_goals', 'away_goals', 'result', 'match_datetime']
    # Tarkista, mitkä näistä sarakkeista todella ovat olemassa ennen dropna-kutsua
    cols_to_check_for_dropna = [col for col in essential_cols_for_dropna if col in processed_df.columns]
    
    if cols_to_check_for_dropna:
        original_rows = len(processed_df)
        # Poista rivit vain jos KAIKKI subsetin sarakkeet ovat NA/None/NaN
        # Tämä on lempeämpi kuin any='any', joka poistaisi jos yksikin on NA
        processed_df.dropna(subset=cols_to_check_for_dropna, how='all', inplace=True)
        # Tai jos halutaan tiukempi: poista jos yksikin näistä puuttuu
        # processed_df.dropna(subset=cols_to_check_for_dropna, how='any', inplace=True)
        debug_print(f"Rows before dropna on essentials: {original_rows}, after: {len(processed_df)}")
    else:
        debug_print("No essential columns found for dropna check, or all are missing. Skipping dropna.")


    # Lisää tarkistus, että 'OttelunTilaRaaka' on 'päättynyt' niille riveille, joita käytetään sarjataulukossa
    # Tämä on tärkeää, jotta keskeneräisiä pelejä ei lasketa mukaan.
    if 'OttelunTilaRaaka' in processed_df.columns:
        ended_matches_mask = processed_df['OttelunTilaRaaka'].astype(str).str.lower().str.contains('päättynyt')
        # Jos halutaan, voidaan suodattaa pois ei-päättyneet ottelut tässä vaiheessa
        # processed_df = processed_df[ended_matches_mask | processed_df['OttelunTilaRaaka'].isna()] # Pidä myös ne, joissa tilaa ei tiedetä
        # debug_print(f"Rows after filtering for 'päättynyt' status (or unknown): {len(processed_df)}")
    else:
        debug_print("Warning: 'OttelunTilaRaaka' column not found. Cannot filter by match status.")

    return processed_df

def calculate_league_table(df):
    """Calculate league standings"""
    # Varmista, että df ei ole None ja sisältää tarvittavat sarakkeet
    required_cols = ['Koti', 'Vieras', 'home_goals', 'away_goals', 'result']
    if df is None or not all(col in df.columns for col in required_cols):
        print(f"Error: Missing one or more required columns for league table: {required_cols}")
        return None

    # Suodata vain ottelut, joissa on validi tulos ja joukkueet
    # Ja varmista, että maalit ovat numeroita (Int64 tukee NA:ta)
    match_df = df[
        df['result'].notna() &
        df['Koti'].notna() & df['Koti'].ne('') & # Varmista, ettei ole tyhjä merkkijono
        df['Vieras'].notna() & df['Vieras'].ne('') &
        df['home_goals'].notna() & 
        df['away_goals'].notna()
    ].copy() # Käytä kopiota, jotta alkuperäinen df ei muutu

    # Lisätään suodatus 'OttelunTilaRaaka' perusteella, jos sarake on olemassa
    # Lasketaan mukaan vain päättyneet ottelut
    if 'OttelunTilaRaaka' in match_df.columns:
        initial_rows = len(match_df)
        match_df = match_df[match_df['OttelunTilaRaaka'].astype(str).str.lower().str.contains('päättynyt')]
        debug_print(f"League table calculation: Filtered by 'päättynyt' status. Rows before: {initial_rows}, after: {len(match_df)}")
    else:
        debug_print("Warning: 'OttelunTilaRaaka' not in DataFrame for league table. All matches with results will be included.")


    if len(match_df) == 0:
        print("No valid (ended) match data found to calculate league table.")
        return pd.DataFrame() # Palauta tyhjä DataFrame

    teams_stats = {} # Käytetään sanakirjaa joukkueiden tilastojen keräämiseen

    for _, match in match_df.iterrows():
        home_team_name = match['Koti']
        away_team_name = match['Vieras']
        # Maalit pitäisi olla jo Int64, mutta varmistetaan int-muunnos laskentaa varten
        # (NA-arvot on jo suodatettu pois ylempänä)
        h_goals = int(match['home_goals'])
        a_goals = int(match['away_goals'])

        # Alusta joukkueen tiedot, jos niitä ei vielä ole
        for team_name_iter in [home_team_name, away_team_name]:
            if team_name_iter not in teams_stats:
                teams_stats[team_name_iter] = {
                    'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                    'goals_for': 0, 'goals_against': 0, 'points': 0,
                    'clean_sheets': 0, 'failed_to_score': 0
                }
        
        # Päivitä pelatut, maalit
        teams_stats[home_team_name]['played'] += 1
        teams_stats[away_team_name]['played'] += 1
        teams_stats[home_team_name]['goals_for'] += h_goals
        teams_stats[home_team_name]['goals_against'] += a_goals
        teams_stats[away_team_name]['goals_for'] += a_goals
        teams_stats[away_team_name]['goals_against'] += h_goals

        # Nollapelit ja ei maalia -tilastot
        if h_goals == 0: teams_stats[home_team_name]['failed_to_score'] += 1
        if a_goals == 0: teams_stats[away_team_name]['failed_to_score'] += 1
        if h_goals == 0 and teams_stats.get(away_team_name): teams_stats[away_team_name]['clean_sheets'] += 1
        if a_goals == 0 and teams_stats.get(home_team_name): teams_stats[home_team_name]['clean_sheets'] += 1
            
        # Pisteet ja voitot/tasapelit/häviöt
        if match['result'] == 'home_win':
            teams_stats[home_team_name]['wins'] += 1
            teams_stats[home_team_name]['points'] += 3
            teams_stats[away_team_name]['losses'] += 1
        elif match['result'] == 'away_win':
            teams_stats[away_team_name]['wins'] += 1
            teams_stats[away_team_name]['points'] += 3
            teams_stats[home_team_name]['losses'] += 1
        elif match['result'] == 'draw': # Varmistetaan, että kyseessä on tasapeli
            teams_stats[home_team_name]['draws'] += 1
            teams_stats[home_team_name]['points'] += 1
            teams_stats[away_team_name]['draws'] += 1
            teams_stats[away_team_name]['points'] += 1
    
    # Mahdollinen pistevähennys (esim. PK-35)
    # Tämä pitäisi tehdä konfiguroitavammaksi, jos tarvitaan useammille joukkueille
    pk35_normalized_name = "pk-35" # Normalisoitu nimi vertailuun
    for team_name_key in list(teams_stats.keys()): # Käytä listaa, jotta voidaan muokata dictiä iteroinnin aikana
        if isinstance(team_name_key, str) and pk35_normalized_name in team_name_key.lower():
            debug_print(f"Applying -2 points deduction for team containing '{pk35_normalized_name}': {team_name_key}")
            teams_stats[team_name_key]['points'] -= 2
            break # Oletetaan, että vain yksi PK-35

    if not teams_stats:
         return pd.DataFrame() # Palauta tyhjä DataFrame, jos yhtään joukkuetta ei käsitelty

    # Muunna sanakirja DataFrameksi
    table_df = pd.DataFrame.from_dict(teams_stats, orient='index')
    table_df['team'] = table_df.index # Lisää joukkueen nimi sarakkeeksi

    # Laske lisätilastot
    table_df['goal_difference'] = table_df['goals_for'] - table_df['goals_against']
    # Vältä DivisionByZero, jos played = 0
    table_df['avg_goals_for'] = table_df.apply(lambda row: round(row['goals_for'] / row['played'], 2) if row['played'] > 0 else 0, axis=1)
    table_df['avg_goals_against'] = table_df.apply(lambda row: round(row['goals_against'] / row['played'], 2) if row['played'] > 0 else 0, axis=1)
    table_df['win_percentage'] = table_df.apply(lambda row: round((row['wins'] / row['played']) * 100, 1) if row['played'] > 0 else 0, axis=1)
    
    # Järjestä sarjataulukko
    sort_order = ['points', 'goal_difference', 'goals_for'] # Pääasialliset lajittelukriteerit
    # Varmista, että kaikki lajittelusarakkeet ovat olemassa
    valid_sort_order = [col for col in sort_order if col in table_df.columns]
    if valid_sort_order:
        table_df = table_df.sort_values(by=valid_sort_order, ascending=[False, False, False])
    else: # Fallback, jos pääasiallisia ei ole (epätodennäköistä)
        table_df = table_df.sort_values(by=['team'], ascending=True) 
        print("Warning: Could not sort league table by primary criteria. Sorted by team name.")

    table_df.reset_index(drop=True, inplace=True)
    table_df['rank'] = table_df.index + 1 # Lisää sijoitusnumero

    # Määritä lopulliset sarakkeet ja niiden järjestys
    final_columns = [
        'rank', 'team', 'played', 'wins', 'draws', 'losses', 
        'goals_for', 'goals_against', 'goal_difference', 'points',
        'avg_goals_for', 'avg_goals_against', 'win_percentage',
        'clean_sheets', 'failed_to_score'
    ]
    # Ota mukaan vain ne sarakkeet, jotka ovat todella olemassa DataFrame:ssa
    existing_final_columns = [col for col in final_columns if col in table_df.columns]
    
    return table_df[existing_final_columns]


def analyze_attendance_patterns(df):
    """Analyze attendance patterns to identify optimal scheduling"""
    if df is None or 'attendance' not in df.columns or df['attendance'].isnull().all():
        print("Attendance data ('attendance' column) not found or all null. Skipping attendance analysis.")
        return None
        
    # Varmista, että tarvittavat aika-sarakkeet ovat olemassa
    required_time_cols = ['weekday_name', 'hour', 'month', 'month_name', 'Koti']
    if not all(col in df.columns for col in required_time_cols):
        print(f"Missing one or more required time/team columns for attendance analysis: {required_time_cols}. Skipping.")
        return None

    # Ota kopio ja poista rivit, joissa tarvittava data puuttuu
    attendance_df = df[
        df['attendance'].notna() & 
        df['weekday_name'].notna() & 
        df['hour'].notna() &
        df['month'].notna() &
        df['month_name'].notna() &
        df['Koti'].notna() # Tarvitaan joukkuekohtaiseen analyysiin
    ].copy()
    
    if len(attendance_df) < 5: # Tarvitaan riittävästi dataa mielekkääseen analyysiin
        print(f"Not enough valid attendance data points (found {len(attendance_df)}, need at least 5) for pattern analysis.")
        return None
    
    # Viikonpäivittäinen analyysi
    day_attendance = attendance_df.groupby('weekday_name')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_attendance['weekday_name'] = pd.Categorical(day_attendance['weekday_name'], categories=day_order, ordered=True)
    day_attendance = day_attendance.sort_values('weekday_name')
    
    # Tuntikohtainen analyysi
    hour_attendance = attendance_df.groupby('hour')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    hour_attendance = hour_attendance.sort_values('hour') # Järjestä tunnin mukaan
    
    # Kuukausittainen analyysi
    month_attendance = attendance_df.groupby(['month', 'month_name'])['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    month_attendance = month_attendance.sort_values('month') # Järjestä kuukauden numeron mukaan
    
    # Joukkuekohtainen kotipelien yleisömäärä
    team_home_attendance = attendance_df.groupby('Koti')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    team_home_attendance = team_home_attendance.rename(columns={'Koti': 'team'})
    team_home_attendance = team_home_attendance.sort_values('mean', ascending=False)

    # Suosituimmat otteluparit (jos myös Vieras-sarake löytyy)
    top_matchups = None
    if 'Vieras' in attendance_df.columns and attendance_df['Vieras'].notna().any():
        if len(attendance_df) > 10: # Tarvitaan hieman enemmän dataa tähän
            matchups = attendance_df.groupby(['Koti', 'Vieras'])['attendance'].mean().reset_index()
            top_matchups = matchups.sort_values('attendance', ascending=False).head(10) # Näytä top 10
    else:
        debug_print("Warning: 'Vieras' column not found for top_matchups attendance analysis.")

    # Viikonpäivä-tunti heatmap data
    day_hour_heatmap_data = None
    if len(attendance_df) > 15: # Tarvitaan riittävästi dataa heatmapiin
        try:
            day_hour_heatmap_data = pd.crosstab(
                index=attendance_df['weekday_name'], 
                columns=attendance_df['hour'], 
                values=attendance_df['attendance'], 
                aggfunc='mean'
            )
            day_hour_heatmap_data = day_hour_heatmap_data.reindex(day_order).fillna(0) # Järjestä ja täytä puuttuvat nollilla
        except Exception as e:
            print(f"Could not create day-hour heatmap data for attendance: {e}")
            day_hour_heatmap_data = None

    return {
        'day_attendance': day_attendance,
        'hour_attendance': hour_attendance,
        'month_attendance': month_attendance,
        'team_attendance': team_home_attendance,
        'top_matchups': top_matchups,
        'day_hour_heatmap': day_hour_heatmap_data
    }

# Muut analyysifunktiot (analyze_venue_performance, analyze_team_performance_over_time, optimize_match_schedule)
# ja visualisointifunktiot (visualize_league_standings) voivat pysyä pääosin ennallaan,
# kunhan varmistetaan, että ne käsittelevät oikein mahdolliset puuttuvat sarakkeet tai datan.
# Esimerkiksi, jos 'Stadion'-sarake puuttuu, venue_performance ei voi toimia odotetusti.

# PÄÄLOHKO (Main execution block)
if __name__ == "__main__":
    data_file = "match_data.json"
    print(f"Starting analysis using data file: {data_file}")

    match_data_df = load_data(data_file)

    if match_data_df is not None and not match_data_df.empty:
        print(f"Data loaded successfully. Rows: {len(match_data_df)}, Columns: {len(match_data_df.columns)}")
        
        processed_data_df = preprocess_data(match_data_df.copy()) 

        if processed_data_df is not None and not processed_data_df.empty:
            print(f"Data preprocessed successfully. Rows after preprocessing: {len(processed_data_df)}")

            # Sarjataulukko
            league_table_df = calculate_league_table(processed_data_df.copy())
            if league_table_df is not None and not league_table_df.empty:
                 print("League table calculated.")
                 # visualize_league_standings(league_table_df.copy()) # Visualisointi voidaan kutsua tarvittaessa
                 # print(f"League table visualizations saved to {PLOTS_DIR}")
                 try:
                     league_table_df.to_csv(os.path.join(DATA_DIR, 'league_standings_calculated.csv'), index=False, encoding='utf-8-sig') # Lisätty encoding
                     print(f"League table data saved to {os.path.join(DATA_DIR, 'league_standings_calculated.csv')}")
                 except Exception as e:
                     print(f"Error saving league_standings_calculated.csv: {e}")
            else:
                 print("Could not calculate league table or table is empty.")

            # Yleisöanalyysi
            attendance_analysis_results = analyze_attendance_patterns(processed_data_df.copy())
            if attendance_analysis_results:
                print("Attendance patterns analyzed.")
                try:
                     if attendance_analysis_results.get('day_attendance') is not None:
                         attendance_analysis_results['day_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_day.csv'), index=False, encoding='utf-8-sig')
                     if attendance_analysis_results.get('hour_attendance') is not None:
                         attendance_analysis_results['hour_attendance'].to_csv(os.path.join(DATA_DIR, 'attendance_by_hour.csv'), index=False, encoding='utf-8-sig')
                     # Lisää muiden attendance-tulosten tallennus tarvittaessa
                     print(f"Attendance analysis summaries saved to {DATA_DIR}")
                except Exception as e: print(f"Error saving attendance summaries: {e}")
            else: 
                print("Attendance pattern analysis skipped, failed, or produced no results.")

            # Muut analyysit voidaan lisätä tänne vastaavalla tavalla
            # venue_stats = analyze_venue_performance(processed_data_df.copy())
            # team_perf_over_time = analyze_team_performance_over_time(processed_data_df.copy())
            # schedule_recommendations = optimize_match_schedule(attendance_analysis_results)


            print("\nAnalysis script finished.")
        else:
            print("Data preprocessing failed or resulted in empty data. Halting further analysis.")
    else:
        print(f"Data loading from {data_file} failed or file is empty. Halting analysis.")
        try:
            with open(os.path.join(OUTPUT_DIR, "analysis_error.log"), "w", encoding='utf-8') as f:
                f.write(f"Failed to load or process data from {data_file} at {datetime.datetime.utcnow().isoformat()}Z. Input data was None or empty.")
        except Exception as e_log:
            print(f"Failed to write analysis_error.log: {e_log}")
