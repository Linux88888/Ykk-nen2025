import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
# from sklearn.cluster import KMeans # Ei käytetä tässä versiossa, voi lisätä tarvittaessa
# from sklearn.preprocessing import StandardScaler # Ei käytetä tässä versiossa
# from sklearn.linear_model import LinearRegression # Ei käytetä tässä versiossa
# from sklearn.model_selection import train_test_split # Ei käytetä tässä versiossa
import datetime
# import calendar # datetime-objektit tarjoavat tarvittavat
import os
import warnings
import json # Voi olla tarpeen, jos tallennetaan JSONia, mutta ei datan lataukseen enää
from pathlib import Path # Käytetään Pathlibia tiedostopolkuihin

# Suppress warning messages
warnings.filterwarnings('ignore')

# Configuration
DEBUG = False
OUTPUT_DIR = "output"
PLOTS_DIR = os.path.join(OUTPUT_DIR, "plots")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
MODELS_DIR = os.path.join(OUTPUT_DIR, "models") # Vaikka malleja ei nyt luoda, kansio voi olla olemassa

# Create output directories
for directory in [OUTPUT_DIR, PLOTS_DIR, DATA_DIR, MODELS_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)

# Set visualization styles
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("viridis")

def debug_print(message):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"DEBUG: {message}")

def load_data(filepath="match_data.json"): # Oletusarvo tiedostonimelle
    """Load match data from JSON file"""
    try:
        path_obj = Path(filepath)
        if not path_obj.exists():
            print(f"Error: Data file not found at {filepath}")
            return None
        if path_obj.stat().st_size <= 2: # Tyhjä JSON "[]" on 2 tavua
            print(f"Warning: Data file at {filepath} is empty or too small. Returning None.")
            return None

        df = pd.read_json(filepath, orient='records', encoding='utf-8')
        if df.empty:
             debug_print(f"Data loaded from {filepath} is empty (no records).")
        else:
            debug_print(f"Data loaded successfully from {filepath}. Shape: {df.shape}")
        return df
    except ValueError as ve: 
        print(f"Error: Could not parse JSON from {filepath}. Error: {ve}")
        return None
    except Exception as e:
        print(f"Error loading data from {filepath}: {e}")
        return None

def preprocess_data(df):
    """Clean and preprocess the data from match_data.json"""
    if df is None or df.empty:
        print("Error: Input DataFrame is None or empty in preprocess_data.")
        return None
    processed_df = df.copy()

    # Nimeä sarakkeet vastaamaan odotuksia (jos tarpeen)
    # Oletetaan, että skraperi tuottaa jo 'score', 'team_home', 'team_away', 'audience', 'venue', 'match_datetime_raw', 'match_status_raw'
    # Jos nimet ovat eri, ne pitää mapata tässä
    rename_map = {
        'score': 'Tulos', 
        'team_home': 'Koti', 
        'team_away': 'Vieras',
        'audience': 'Yleisö', 
        'venue': 'Stadion', # Skraperin 'venue'
        'match_datetime_raw': 'PvmAikaRaw', # Skraperin 'match_datetime_raw'
        'match_status_raw': 'OttelunTilaRaaka', # Skraperin 'match_status_raw'
        'scrape_timestamp': 'HakuAikaleima' # Lisätty, jos skraperi tuottaa
        # Lisää muita mappauksia tarvittaessa
    }
    # Varmista, että sarakkeet, joita yritetään nimetä uudelleen, ovat olemassa
    existing_cols_to_rename = {k: v for k, v in rename_map.items() if k in processed_df.columns}
    processed_df.rename(columns=existing_cols_to_rename, inplace=True)


    # --- Maalien parsiminen ---
    processed_df['home_goals'] = pd.NA
    processed_df['away_goals'] = pd.NA
    if 'Tulos' in processed_df.columns:
        # Varmista, että 'Tulos' on merkkijono ennen split-operaatiota
        valid_scores = processed_df['Tulos'].notna() & processed_df['Tulos'].astype(str).str.contains('–') # Käytä pitkää viivaa
        score_parts = processed_df.loc[valid_scores, 'Tulos'].astype(str).str.split('–', n=1, expand=True)
        if not score_parts.empty:
            processed_df.loc[valid_scores, 'home_goals'] = pd.to_numeric(score_parts[0].str.strip(), errors='coerce')
            if score_parts.shape[1] > 1:
                 processed_df.loc[valid_scores, 'away_goals'] = pd.to_numeric(score_parts[1].str.strip(), errors='coerce')
    
    processed_df['home_goals'] = processed_df['home_goals'].astype('Int64')
    processed_df['away_goals'] = processed_df['away_goals'].astype('Int64')
    
    # --- Kokonaismaalit ---
    # Laske vain, jos molemmat maalimäärät ovat validia numeroita
    processed_df['total_goals'] = processed_df['home_goals'].add(processed_df['away_goals'], fill_value=pd.NA) # Jos toinen on NA, summa on NA
    processed_df['total_goals'] = processed_df['total_goals'].astype('Int64')


    # --- Ottelun tulos ---
    cond_home_win = (processed_df['home_goals'].notna() & 
                     processed_df['away_goals'].notna() & 
                     (processed_df['home_goals'] > processed_df['away_goals']))
    cond_away_win = (processed_df['home_goals'].notna() & 
                     processed_df['away_goals'].notna() & 
                     (processed_df['home_goals'] < processed_df['away_goals']))
    cond_draw = (processed_df['home_goals'].notna() & 
                 processed_df['away_goals'].notna() & 
                 (processed_df['home_goals'] == processed_df['away_goals']))
    conditions = [cond_home_win, cond_away_win, cond_draw]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None)
    
    # --- Päivämäärän ja ajan parsiminen ---
    # Oletetaan, että 'PvmAikaRaw' on muotoa "HH:MM | Päivä Viikonpäivä DD.MM." tai "DD.MM.YYYY" tai "HH:MM"
    processed_df['Pvm'] = pd.NaT # Alustetaan Pvm ja Aika erikseen, jos niitä tarvitaan myöhemmin
    processed_df['Aika'] = None

    if 'PvmAikaRaw' in processed_df.columns:
        # Yritä ensin splitata "|" merkillä
        split_dt = processed_df['PvmAikaRaw'].astype(str).str.split('|', n=1, expand=True)
        
        # Käsitellään tapaukset, joissa "|" löytyy
        if split_dt.shape[1] > 1:
            processed_df['Aika'] = split_dt[0].str.strip()
            # Poista viikonpäivä ja mahdollinen ylimääräinen piste DD.MM. jälkeen
            date_part_cleaned = split_dt[1].str.strip().str.replace(r'^[A-Za-zÄÖÅäöå]+\s+', '', regex=True)
            date_part_cleaned = date_part_cleaned.str.rstrip('.') # Poista piste lopusta esim. DD.MM. -> DD.MM
            processed_df['Pvm'] = date_part_cleaned
        else: # Ei "|" merkkiä, oletetaan että koko kenttä on joko aika tai pvm
            # Yritä tunnistaa, onko kyseessä aika vai päivämäärä
            time_like = processed_df['PvmAikaRaw'].astype(str).str.match(r'^\d{1,2}:\d{2}$')
            date_like = processed_df['PvmAikaRaw'].astype(str).str.contains(r'\d{1,2}\.\d{1,2}') # Laajempi ehto päivämäärille
            
            processed_df.loc[time_like == True, 'Aika'] = processed_df.loc[time_like == True, 'PvmAikaRaw']
            processed_df.loc[date_like == True, 'Pvm'] = processed_df.loc[date_like == True, 'PvmAikaRaw']

    # Muodosta 'match_datetime'
    processed_df['match_datetime'] = pd.NaT
    valid_pvm = processed_df['Pvm'].notna() & (processed_df['Pvm'].astype(str) != '')
    valid_aika = processed_df['Aika'].notna() & (processed_df['Aika'].astype(str) != '')
    
    if valid_pvm.any() or valid_aika.any(): # Jatketaan, jos jompikumpi on olemassa
        def parse_flexible_date(date_str):
            if pd.isna(date_str): return pd.NaT
            current_year = datetime.datetime.now().year
            for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m."): # Kokeile eri formaatteja
                try:
                    dt_obj = datetime.datetime.strptime(str(date_str).strip(), fmt)
                    if fmt == "%d.%m.": # Jos vain DD.MM., käytä kuluvaa vuotta
                        dt_obj = dt_obj.replace(year=current_year)
                    elif fmt == "%d.%m.%y": # Jos DD.MM.YY, korjaa vuosisata tarvittaessa
                         if dt_obj.year > current_year + 10 : # Esim. jos vuosi on 70 -> 1970
                              dt_obj = dt_obj.replace(year=dt_obj.year - 100)
                    return dt_obj
                except ValueError:
                    continue
            return pd.NaT

        # Muunna Pvm-sarake ensin datetime-objekteiksi
        temp_date_series = processed_df.loc[valid_pvm, 'Pvm'].apply(parse_flexible_date)

        # Yhdistä päivämäärä ja aika merkkijonoksi ja muunna datetimeksi
        # Käytä oletusaikaa (00:00), jos aika puuttuu mutta päivämäärä on
        default_time_str = "00:00"
        
        datetime_combined_str = temp_date_series.dt.strftime('%Y-%m-%d').fillna('') + \
                                ' ' + \
                                processed_df.loc[valid_aika, 'Aika'].fillna(default_time_str)
        
        datetime_combined_str = datetime_combined_str.str.strip()
        
        # Luo maski riveille, joissa on validi yhdistetty pvm-aika merkkijono
        # ja joissa alkuperäinen Pvm oli validi (tai Aika oli validi, jos Pvm puuttui mutta Aika antoi kontekstin)
        valid_combined_dt_str_mask = datetime_combined_str.ne('') & (valid_pvm | (processed_df['Pvm'].isna() & valid_aika))


        processed_df.loc[valid_combined_dt_str_mask, 'match_datetime'] = pd.to_datetime(
            datetime_combined_str.loc[valid_combined_dt_str_mask], 
            format='%Y-%m-%d %H:%M', 
            errors='coerce'
        )

    # Parsi päivämääräominaisuudet
    processed_df['date'] = processed_df['match_datetime'].dt.date
    processed_df['year'] = processed_df['match_datetime'].dt.year.astype('Int64')
    processed_df['month'] = processed_df['match_datetime'].dt.month.astype('Int64')
    processed_df['day'] = processed_df['match_datetime'].dt.day.astype('Int64')
    processed_df['weekday'] = processed_df['match_datetime'].dt.weekday.astype('Int64') # Maanantai=0, Sunnuntai=6
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['hour'] = processed_df['match_datetime'].dt.hour.astype('Int64')
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    
    # --- Yleisömäärä ---
    if 'Yleisö' in processed_df.columns:
        # Poista kaikki välilyönnit ja muunna numeroksi
        processed_df['attendance'] = processed_df['Yleisö'].astype(str).str.replace(r'\s+', '', regex=True)
        processed_df['attendance'] = pd.to_numeric(processed_df['attendance'], errors='coerce').astype('Int64')
    else:
        processed_df['attendance'] = pd.NA # Luo sarake, jos sitä ei ole

    # Varmista, että 'Koti', 'Vieras', 'Stadion' sarakkeet ovat olemassa myöhempiä analyysejä varten
    for col in ['Koti', 'Vieras', 'Stadion', 'OttelunTilaRaaka']:
        if col not in processed_df.columns:
            processed_df[col] = None # Tai pd.NA, riippuen odotetusta tyypistä

    # Poista rivit, joissa kriittistä dataa puuttuu (esim. sarjataulukkoa varten)
    # Tämä on jo vanhassa koodissa, mutta tarkistetaan subset
    # essential_for_table = ['Koti', 'Vieras', 'home_goals', 'away_goals', 'result']
    # processed_df.dropna(subset=essential_for_table, how='any', inplace=True)
    # HUOM: Vanha koodi pudotti lopussa. Pidetään se siellä, jotta analyysifunktiot saavat mahdollisimman paljon dataa.

    debug_print(f"Preprocessing finished. Shape: {processed_df.shape}")
    debug_print(f"Columns after preprocessing: {processed_df.columns.tolist()}")
    debug_print(f"Sample of match_datetime: {processed_df['match_datetime'].head().to_list()}")
    debug_print(f"Sample of home_goals: {processed_df['home_goals'].head().to_list()}")
    debug_print(f"Sample of result: {processed_df['result'].head().to_list()}")


    return processed_df

# --- ALKUPERÄISET ANALYYSIFUNKTIOT (calculate_league_table, analyze_attendance_patterns, jne.) ---
# --- OLETETAAN, ETTÄ NE TOIMIVAT, KUN `preprocess_data` TUOTTAA OIKEAT SARAKKEET ---
# --- Olen tehnyt pieniä tarkistuksia ja parannuksia niihin alla ---

def calculate_league_table(df):
    """Calculate league standings"""
    teams = {}
    # Filter only matches with valid results and teams for table calculation
    match_df = df[df['result'].notna() & 
                  df['Koti'].notna() & df['Koti'].ne('') &
                  df['Vieras'].notna() & df['Vieras'].ne('') &
                  df['home_goals'].notna() & 
                  df['away_goals'].notna()
                  ].copy()
    
    # Lisätään ehto, että ottelun pitää olla päättynyt, jos tieto on saatavilla
    if 'OttelunTilaRaaka' in match_df.columns:
        match_df = match_df[match_df['OttelunTilaRaaka'].astype(str).str.lower().str.contains('päättynyt')]

    if len(match_df) == 0:
        print("No valid (ended) match data found to calculate league table.")
        return None
        
    for _, match in match_df.iterrows():
        home_goals = int(match['home_goals']) # Varmistetaan int, vaikka pitäisi olla Int64
        away_goals = int(match['away_goals'])
        home_team = str(match['Koti']) # Varmistetaan str
        away_team = str(match['Vieras'])
        
        for team in [home_team, away_team]:
            if team not in teams:
                teams[team] = {
                    'played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                    'goals_for': 0, 'goals_against': 0, 'points': 0,
                    'clean_sheets': 0, 'failed_to_score': 0
                }
        teams[home_team]['played'] += 1
        teams[away_team]['played'] += 1
        teams[home_team]['goals_for'] += home_goals
        teams[home_team]['goals_against'] += away_goals
        teams[away_team]['goals_for'] += away_goals
        teams[away_team]['goals_against'] += home_goals
        
        if home_goals == 0:
            teams[home_team]['failed_to_score'] += 1
            if away_team in teams: teams[away_team]['clean_sheets'] += 1 # Varmista, että away_team on jo teams-dictissä
        if away_goals == 0:
            if home_team in teams: teams[home_team]['clean_sheets'] += 1 # Varmista
            teams[away_team]['failed_to_score'] += 1
            
        if match['result'] == 'home_win':
            teams[home_team]['wins'] += 1; teams[home_team]['points'] += 3
            teams[away_team]['losses'] += 1
        elif match['result'] == 'away_win':
            teams[away_team]['wins'] += 1; teams[away_team]['points'] += 3
            teams[home_team]['losses'] += 1
        elif match['result'] == 'draw': # Varmista, että result on 'draw'
            teams[home_team]['draws'] += 1; teams[home_team]['points'] += 1
            teams[away_team]['draws'] += 1; teams[away_team]['points'] += 1
            
    # PK-35 special handling (case-insensitive and partial match)
    pk35_name_part = "pk-35"
    for team_key in list(teams.keys()): # Käytä list(teams.keys()) jos muokkaat dictiä loopissa
        if isinstance(team_key, str) and pk35_name_part in team_key.lower():
            debug_print(f"Handling {team_key} with -2 point start")
            teams[team_key]['points'] -= 2
            break # Oletetaan, että vain yksi PK-35 joukkue
        
    if not teams:
         return None

    table_df = pd.DataFrame.from_dict(teams, orient='index') # Käytä from_dict paremmin
    table_df['team'] = table_df.index # Lisää team-sarake indeksistä

    for team_name_idx, stats_row in table_df.iterrows(): # Käytä iterrows varoen, mutta tässä ok pienelle table_df:lle
        played = stats_row['played']
        if played > 0:
            table_df.loc[team_name_idx, 'goal_difference'] = stats_row['goals_for'] - stats_row['goals_against']
            table_df.loc[team_name_idx, 'avg_goals_for'] = round(stats_row['goals_for'] / played, 2)
            table_df.loc[team_name_idx, 'avg_goals_against'] = round(stats_row['goals_against'] / played, 2)
            table_df.loc[team_name_idx, 'win_percentage'] = round((stats_row['wins'] / played) * 100, 1)
        else:
             table_df.loc[team_name_idx, 'goal_difference'] = 0
             table_df.loc[team_name_idx, 'avg_goals_for'] = 0.0
             table_df.loc[team_name_idx, 'avg_goals_against'] = 0.0
             table_df.loc[team_name_idx, 'win_percentage'] = 0.0
        
    sort_cols = ['points', 'goal_difference', 'goals_for']
    # Varmista, että lajittelusarakkeet ovat olemassa
    valid_sort_cols = [col for col in sort_cols if col in table_df.columns]
    if valid_sort_cols:
        table_df = table_df.sort_values(by=valid_sort_cols, ascending=[False] * len(valid_sort_cols))
    elif 'points' in table_df.columns: # Fallback
         table_df = table_df.sort_values(by='points', ascending=False)

    table_df.reset_index(drop=True, inplace=True)
    table_df['rank'] = table_df.index + 1

    ordered_cols = ['rank', 'team', 'played', 'wins', 'draws', 'losses', 'goals_for', 'goals_against', 'goal_difference', 'points']
    optional_cols = ['avg_goals_for', 'avg_goals_against', 'win_percentage', 'clean_sheets', 'failed_to_score']
    final_cols = ordered_cols + [col for col in optional_cols if col in table_df.columns]
    
    # Varmista, että kaikki final_cols ovat DataFrame:ssa ennen niiden valintaa
    final_cols = [col for col in final_cols if col in table_df.columns]

    return table_df[final_cols]


def analyze_attendance_patterns(df):
    if 'attendance' not in df.columns or df['attendance'].isnull().all():
        print("Attendance data ('Yleisö' / 'attendance' column) not found or all null.")
        return None
        
    # Varmista, että tarvittavat datetime-sarakkeet on luotu preprocess_data-funktiossa
    required_dt_cols = ['weekday_name', 'hour', 'month', 'month_name', 'Koti', 'Vieras']
    if not all(col in df.columns and df[col].notna().any() for col in required_dt_cols):
        missing_or_empty_dt = [col for col in required_dt_cols if col not in df.columns or not df[col].notna().any()]
        print(f"Missing or empty datetime-related columns for attendance analysis: {missing_or_empty_dt}")
        return None

    attendance_df = df[df['attendance'].notna() & 
                       df['weekday_name'].notna() & 
                       df['hour'].notna() &
                       df['month'].notna() & # Varmista, että month on myös olemassa
                       df['Koti'].notna() # Tarvitaan team_home_attendance
                       ].copy() # Tee kopio, jotta vältetään SettingWithCopyWarning

    if len(attendance_df) == 0:
        print("No valid attendance data found for pattern analysis after filtering.")
        return None
        
    day_attendance = attendance_df.groupby('weekday_name')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_attendance['weekday_name'] = pd.Categorical(day_attendance['weekday_name'], categories=day_order, ordered=True)
    day_attendance = day_attendance.sort_values('weekday_name').reset_index(drop=True)
    
    hour_attendance = attendance_df.groupby('hour')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    hour_attendance = hour_attendance.sort_values('hour').reset_index(drop=True)
    
    month_attendance = attendance_df.groupby(['month', 'month_name'])['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
    month_attendance = month_attendance.sort_values('month').reset_index(drop=True)
    
    team_home_attendance = None
    if 'Koti' in attendance_df.columns:
        team_home_attendance = attendance_df.groupby('Koti')['attendance'].agg(['mean', 'median', 'count', 'sum']).reset_index()
        team_home_attendance = team_home_attendance.rename(columns={'Koti': 'team'})
        team_home_attendance = team_home_attendance.sort_values('mean', ascending=False).reset_index(drop=True)
    
    top_matchups = None
    if 'Vieras' in attendance_df.columns and len(attendance_df) > 10:
        matchups = attendance_df.groupby(['Koti', 'Vieras'])['attendance'].mean().reset_index()
        matchups = matchups.sort_values('attendance', ascending=False)
        top_matchups = matchups.head(5).reset_index(drop=True)

    day_hour_data = None
    if len(attendance_df) > 15: 
        try:
            day_hour_data = pd.crosstab(
                index=attendance_df['weekday_name'], 
                columns=attendance_df['hour'], 
                values=attendance_df['attendance'], 
                aggfunc='mean'
            )
            day_hour_data = day_hour_data.reindex(day_order).fillna(0) 
        except Exception as e:
            print(f"Could not create day-hour heatmap data: {e}")
            day_hour_data = None

    return {
        'day_attendance': day_attendance,
        'hour_attendance': hour_attendance,
        'month_attendance': month_attendance,
        'team_attendance': team_home_attendance,
        'top_matchups': top_matchups,
        'day_hour_heatmap': day_hour_data
    }

def analyze_venue_performance(df):
    required_cols_venue = ['result', 'Koti', 'total_goals'] # Stadion on ehdollinen
    if not all(col in df.columns and df[col].notna().any() for col in required_cols_venue):
        missing_venue_cols = [col for col in required_cols_venue if col not in df.columns or not df[col].notna().any()]
        print(f"Missing columns for venue performance: {missing_venue_cols}")
        return None

    venue_df = df[df['result'].notna() & df['Koti'].notna() & df['total_goals'].notna()].copy()
    
    if len(venue_df) == 0:
        print("No valid data for venue performance analysis.")
        return None

    if 'Stadion' not in venue_df.columns or venue_df['Stadion'].isnull().all():
        debug_print("Using 'Koti' column as fallback for venue analysis, as 'Stadion' is missing or all null.")
        venue_df['Stadion'] = venue_df['Koti'] 
    else:
         venue_df['Stadion'] = venue_df['Stadion'].fillna(venue_df['Koti']) # Täytä puuttuvat Stadion-arvot Koti-joukkueella

    agg_dict = {
        'matches': ('result', 'count'),
        'home_wins': ('result', lambda x: (x == 'home_win').sum()),
        'away_wins': ('result', lambda x: (x == 'away_win').sum()),
        'draws': ('result', lambda x: (x == 'draw').sum()),
        'total_goals_sum': ('total_goals', 'sum'), # Nimeä selkeämmin
        'avg_goals_match': ('total_goals', 'mean'), # Nimeä selkeämmin
    }
    if 'attendance' in venue_df.columns and venue_df['attendance'].notna().any():
         agg_dict['avg_attendance'] = ('attendance', 'mean')
         agg_dict['total_attendance'] = ('attendance', 'sum')

    venues = venue_df.groupby('Stadion').agg(**agg_dict).reset_index()
    
    if venues.empty:
        print("No venues to analyze after grouping.")
        return None

    venues['home_win_percent'] = venues.apply(lambda row: round((row['home_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['draw_percent'] = venues.apply(lambda row: round((row['draws'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    venues['away_win_percent'] = venues.apply(lambda row: round((row['away_wins'] / row['matches']) * 100, 1) if row['matches'] > 0 else 0, axis=1)
    
    sort_key = 'avg_attendance' if 'avg_attendance' in venues.columns else 'avg_goals_match'
    if sort_key not in venues.columns: # Fallback if even avg_goals_match is missing
        sort_key = 'matches'
    
    return venues.sort_values(sort_key, ascending=False).reset_index(drop=True)


def analyze_team_performance_over_time(df):
    required_cols_perf = ['result', 'match_datetime', 'Koti', 'Vieras', 'home_goals', 'away_goals']
    if not all(col in df.columns and df[col].notna().any() for col in required_cols_perf):
        missing_perf_cols = [col for col in required_cols_perf if col not in df.columns or not df[col].notna().any()]
        print(f"Missing columns for team performance over time: {missing_perf_cols}")
        return None

    time_df = df[df['result'].notna() & 
                 df['match_datetime'].notna() & 
                 df['Koti'].notna() & 
                 df['Vieras'].notna() &
                 df['home_goals'].notna() & # Varmista, että maalit eivät ole NA
                 df['away_goals'].notna()
                 ].copy()
    
    if len(time_df) < 2: # Tarvitaan vähintään muutama peli per joukkue
        print("Not enough time-based data for temporal analysis (need at least 2 matches with datetime).")
        return None
        
    all_teams = pd.concat([time_df['Koti'], time_df['Vieras']]).astype(str).unique() # Varmista str ja uniikki
    
    team_results = []
    for team in all_teams:
        if not team or pd.isna(team): continue # Ohita tyhjät joukkuenimet

        team_matches = time_df[(time_df['Koti'] == team) | (time_df['Vieras'] == team)].sort_values('match_datetime')
        
        if len(team_matches) == 0: continue

        for _, match in team_matches.iterrows():
            is_home = match['Koti'] == team
            home_goals = int(match['home_goals']) # Varmista int
            away_goals = int(match['away_goals'])

            if is_home:
                points = 3 if match['result'] == 'home_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = home_goals; goals_against = away_goals
            else: 
                points = 3 if match['result'] == 'away_win' else (1 if match['result'] == 'draw' else 0)
                goals_for = away_goals; goals_against = home_goals
            
            team_results.append({
                'team': team, 'match_datetime': match['match_datetime'],
                'opponent': match['Vieras'] if is_home else match['Koti'],
                'is_home': is_home, 'points': points,
                'goals_for': goals_for, 'goals_against': goals_against,
                'goal_difference': goals_for - goals_against
            })
            
    if not team_results:
         print("No team results generated for temporal analysis.")
         return None

    team_perf_df = pd.DataFrame(team_results)
    team_perf_df = team_perf_df.sort_values(['team', 'match_datetime'])

    team_cumulative = team_perf_df.copy()
    team_cumulative['cumulative_points'] = team_cumulative.groupby('team')['points'].cumsum()
    team_cumulative['cumulative_goals_for'] = team_cumulative.groupby('team')['goals_for'].cumsum()
    team_cumulative['cumulative_goals_against'] = team_cumulative.groupby('team')['goals_against'].cumsum()
    team_cumulative['cumulative_goal_diff'] = team_cumulative['cumulative_goals_for'] - team_cumulative['cumulative_goals_against']
    team_cumulative['games_played'] = team_cumulative.groupby('team').cumcount() + 1
    
    N = 5
    # Lasketaan form_points (pisteet N viimeisestä pelistä)
    # groupby('team') ja sitten rolling.sum()
    # shift(1) käytetään, jotta formi perustuu *edellisiin* peleihin
    # reset_index on tarpeen, koska rolling palauttaa MultiIndexin groupbyn kanssa
    form_col_name = f'form_points_last_{N}'
    team_cumulative[form_col_name] = team_cumulative.groupby('team')['points']\
        .rolling(window=N, min_periods=1).sum().shift(1).reset_index(level=0, drop=True)
    
    # Täytä NaN-arvot (ensimmäisille N-1 pelille) nollalla tai sopivalla arvolla
    team_cumulative[form_col_name] = team_cumulative[form_col_name].fillna(0).astype(int)

    return team_cumulative.reset_index(drop=True)


def optimize_match_schedule(attendance_data):
    if attendance_data is None:
        print("Cannot optimize schedule without attendance analysis results.")
        return None
        
    # Tarkista, että avaimet ovat olemassa ja DataFrame:t eivät ole tyhjiä
    required_keys = ['day_attendance', 'hour_attendance', 'month_attendance']
    for key in required_keys:
        if key not in attendance_data or attendance_data[key] is None or attendance_data[key].empty:
            print(f"Attendance analysis results for '{key}' are missing or empty, cannot generate recommendations.")
            return None

    day_attendance = attendance_data['day_attendance'].sort_values('mean', ascending=False)
    best_days = day_attendance['weekday_name'].tolist()
    
    hour_attendance = attendance_data['hour_attendance'].sort_values('mean', ascending=False)
    best_hours = hour_attendance['hour'].tolist() # Nämä ovat numeroita
    
    month_attendance = attendance_data['month_attendance'] # Oletetaan, että tämä on DataFrame
    day_hour_matrix = attendance_data.get('day_hour_heatmap') # Käytä .get(), koska tämä voi puuttua
    
    recommendations = []
    
    if not best_days or not best_hours:
        print("Not enough data for best days/hours, cannot generate detailed recommendations.")
        # Voisit silti generoida kuukausi- tai matchup-pohjaisia suosituksia, jos dataa on
    else:
        for day in best_days[:3]:
            for hour_val in best_hours[:3]: # hour_val on numero
                day_mean = day_attendance[day_attendance['weekday_name'] == day]['mean'].iloc[0]
                hour_mean = hour_attendance[hour_attendance['hour'] == hour_val]['mean'].iloc[0]
                
                specific_value = 0.0 # Oletusarvo, jos heatmapista ei löydy
                if day_hour_matrix is not None and day in day_hour_matrix.index and hour_val in day_hour_matrix.columns:
                    val_from_matrix = day_hour_matrix.loc[day, hour_val]
                    if pd.notna(val_from_matrix): # Varmista, ettei ole NaN
                        specific_value = val_from_matrix
                
                priority_score = specific_value if specific_value > 0 else (day_mean + hour_mean) / 2
                
                overall_mean_attendance = attendance_data['day_attendance']['mean'].mean() 
                priority_cat = "Low"
                if priority_score > overall_mean_attendance * 1.2: priority_cat = "High"
                elif priority_score > overall_mean_attendance * 0.8: priority_cat = "Medium"
                     
                notes = [f"Day avg: {round(day_mean)}, Hour avg: {round(hour_mean)}"]
                if day in ['Saturday', 'Sunday']: notes.append("Weekend slot")
                if 16 <= hour_val <= 19: notes.append("Evening slot")
                if specific_value > 0: notes.append(f"Specific combo avg: {round(specific_value)}")

                recommendations.append({
                    'day': day, 'time': f"{int(hour_val):02d}:00", 
                    'priority': priority_cat,
                    'estimated_attendance_impact_score': round(priority_score),
                    'notes': "; ".join(notes)
                })
            
    if not month_attendance.empty:
        best_months_df = month_attendance.sort_values('mean', ascending=False)
        for _, month_row in best_months_df.head(2).iterrows():
            recommendations.append({
                'day': 'Any', 'time': 'Any', 'priority': 'Seasonal High',
                'estimated_attendance_impact_score': round(month_row['mean']),
                'notes': f"Consider key matches in {month_row['month_name']} (high avg attendance: {round(month_row['mean'])})"
            })
            
    top_matchups_df = attendance_data.get('top_matchups') # Käytä .get()
    if top_matchups_df is not None and not top_matchups_df.empty:
        for _, matchup in top_matchups_df.head(3).iterrows():
            recommendations.append({
                'day': best_days[0] if best_days else 'Saturday', 
                'time': f"{int(best_hours[0]):02d}:00" if best_hours else '18:00', 
                'priority': 'High (Matchup)',
                'estimated_attendance_impact_score': round(matchup['attendance']),
                'notes': f"Featured Match: {matchup['Koti']} vs {matchup['Vieras']} (avg: {round(matchup['attendance'])}). Prime slot."
            })
            
    if not recommendations:
         print("Could not generate any schedule recommendations based on available data.")
         return None

    recommendations_df = pd.DataFrame(recommendations)
    priority_order = ['High (Matchup)', 'High', 'Seasonal High', 'Medium', 'Low'] # Poistettu 'Seasonal Low'
    recommendations_df['priority'] = pd.Categorical(recommendations_df['priority'], categories=priority_order, ordered=True)
    recommendations_df = recommendations_df.sort_values(
        by=['priority', 'estimated_attendance_impact_score'], 
        ascending=[True, False]
        ).drop_duplicates(subset=['day', 'time', 'notes'], keep='first').reset_index(drop=True)

    return recommendations_df


def visualize_league_standings(league_table):
    if league_table is None or league_table.empty:
        print("No league table data available for visualization.")
        return
        
    Path(PLOTS_DIR).mkdir(parents=True, exist_ok=True) # Varmista kansion olemassaolo Pathlibillä
    
    try: # Matplotlib: Points Bar Chart
        plt.figure(figsize=(12, 8))
        # Varmista, että 'team' ja 'points' sarakkeet ovat olemassa
        if 'team' in league_table.columns and 'points' in league_table.columns:
            bars = plt.bar(league_table['team'], league_table['points'], color=sns.color_palette("viridis", len(league_table)))
            plt.title('Ykkösliiga Points Standings', fontsize=16)
            plt.xlabel('Team', fontsize=12); plt.ylabel('Points', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.5, f"{int(height)}", ha='center', va='bottom', fontsize=10)
            plt.tight_layout()
            plt.savefig(Path(PLOTS_DIR) / 'standings_points.png')
            debug_print("Points bar chart saved.")
        else:
            print("Skipping points bar chart: 'team' or 'points' column missing.")
        plt.close()
    except Exception as e: print(f"Error creating/saving points bar chart: {e}")

    try: # Plotly: Interactive Standings
        fig = go.Figure()
        if 'team' in league_table.columns and 'points' in league_table.columns:
            fig.add_trace(go.Bar(x=league_table['team'], y=league_table['points'], name='Points', marker_color='darkblue', text=league_table['points'], textposition='auto'))
        if 'goal_difference' in league_table.columns and 'team' in league_table.columns:
            fig.add_trace(go.Scatter(x=league_table['team'], y=league_table['goal_difference'], name='Goal Difference', mode='lines+markers', marker=dict(size=8, color='red'), yaxis='y2'))
        
        fig.update_layout(
            title='Ykkösliiga Standings with Goal Difference', xaxis_title='Team', yaxis=dict(title='Points'),
            yaxis2=dict(title='Goal Difference', overlaying='y', side='right', showgrid=False) if 'goal_difference' in league_table.columns else {},
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=600, xaxis={'categoryorder':'array', 'categoryarray': league_table['team'].tolist() if 'team' in league_table.columns else []}
        )
        fig.write_html(str(Path(PLOTS_DIR) / 'standings_interactive.html')) # Muunna Path-objekti merkkijonoksi
        debug_print("Interactive standings chart saved.")
    except Exception as e: print(f"Error creating/saving interactive standings chart: {e}")

    try: # Matplotlib: Stacked Bar Chart for W/D/L
        plt.figure(figsize=(14, 10))
        wdl_cols = ['wins', 'draws', 'losses']
        if all(col in league_table.columns for col in wdl_cols) and 'team' in league_table.columns:
            plt.bar(league_table['team'], league_table['wins'], 0.8, label='Wins', color='forestgreen')
            plt.bar(league_table['team'], league_table['draws'], 0.8, bottom=league_table['wins'], label='Draws', color='gold')
            plt.bar(league_table['team'], league_table['losses'], 0.8, bottom=league_table['wins'] + league_table['draws'], label='Losses', color='firebrick')
            plt.title('Match Results Breakdown by Team', fontsize=16)
            plt.xlabel('Team', fontsize=12); plt.ylabel('Number of Matches', fontsize=12)
            plt.xticks(rotation=45, ha='right'); plt.legend()
            if 'played' in league_table.columns and 'points' in league_table.columns:
                 for i, team_name in enumerate(league_table['team']): # Käytä team_name selkeyden vuoksi
                      total_played = league_table.loc[league_table['team'] == team_name, 'played'].iloc[0]
                      points_val = league_table.loc[league_table['team'] == team_name, 'points'].iloc[0]
                      plt.text(i, total_played + 0.5, f"P: {int(points_val)}", ha='center', va='bottom', fontweight='bold')
            plt.tight_layout()
            plt.savefig(Path(PLOTS_DIR) / 'team_results_breakdown.png')
            debug_print("Results breakdown chart saved.")
        else:
            print("Skipping results breakdown chart: Missing W/D/L or team columns.")
        plt.close()
    except Exception as e: print(f"Error creating/saving results breakdown chart: {e}")

    try: # Save League Table to CSV
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        csv_path = Path(DATA_DIR) / 'league_standings_calculated.csv' # Nimi yhdenmukainen toisen workflow'n kanssa
        league_table.to_csv(csv_path, index=False, encoding='utf-8-sig') # Lisää encoding
        print(f"League table saved to {csv_path}") # Käytä print, debug_print ei näy GH Actionsissa ilman DEBUG=True
    except Exception as e: print(f"Error saving league table to CSV: {e}")


# ===============================================
# Main execution block
# ===============================================
if __name__ == "__main__":
    # Oletetaan, että skraperi on ajettu ja match_data.json on projektin juuressa
    data_file = "match_data.json" 

    print(f"Starting analysis script at {datetime.datetime.now()}...")
    print(f"Attempting to load data from: {data_file}")

    match_data = load_data(data_file) # load_data lukee nyt JSONia

    if match_data is not None:
        print(f"Data loaded successfully. Rows: {len(match_data)}")
        
        processed_data = preprocess_data(match_data.copy()) # Käytä kopiota

        if processed_data is not None and not processed_data.empty:
            print(f"Data preprocessed successfully. Rows: {len(processed_data)}")

            league_table = calculate_league_table(processed_data.copy()) # Käytä kopiota
            if league_table is not None and not league_table.empty:
                 print("League table calculated.")
                 visualize_league_standings(league_table) # Tämä myös tallentaa CSV:n
            else:
                 print("Could not calculate league table or table is empty.")

            attendance_analysis = analyze_attendance_patterns(processed_data.copy())
            if attendance_analysis:
                print("Attendance patterns analyzed.")
                try:
                     # Tallenna keskeiset osat JSON-tiedostoon tai erillisiin CSV:hin
                     # Esimerkiksi:
                     if attendance_analysis.get('day_attendance') is not None:
                         attendance_analysis['day_attendance'].to_csv(Path(DATA_DIR) / 'attendance_by_day.csv', index=False, encoding='utf-8-sig')
                     if attendance_analysis.get('hour_attendance') is not None:
                         attendance_analysis['hour_attendance'].to_csv(Path(DATA_DIR) / 'attendance_by_hour.csv', index=False, encoding='utf-8-sig')
                     # ... ja niin edelleen muille osille
                     print(f"Attendance analysis summaries saved to {DATA_DIR}")
                except Exception as e: print(f"Error saving attendance summaries: {e}")

                schedule_recommendations = optimize_match_schedule(attendance_analysis)
                if schedule_recommendations is not None and not schedule_recommendations.empty:
                    try:
                         recommendations_path = Path(DATA_DIR) / 'schedule_recommendations.csv'
                         schedule_recommendations.to_csv(recommendations_path, index=False, encoding='utf-8-sig')
                         print(f"Schedule recommendations saved to {recommendations_path}")
                    except Exception as e: print(f"Error saving schedule recommendations: {e}")
                else: print("Could not generate schedule recommendations or they are empty.")
            else: print("Attendance pattern analysis skipped or failed.")

            venue_stats = analyze_venue_performance(processed_data.copy())
            if venue_stats is not None and not venue_stats.empty:
                try:
                     venue_path = Path(DATA_DIR) / 'venue_performance.csv'
                     venue_stats.to_csv(venue_path, index=False, encoding='utf-8-sig')
                     print(f"Venue performance analysis saved to {venue_path}")
                except Exception as e: print(f"Error saving venue performance analysis: {e}")
            else: print("Venue performance analysis skipped or failed or resulted in empty data.")

            team_perf_over_time = analyze_team_performance_over_time(processed_data.copy())
            if team_perf_over_time is not None and not team_perf_over_time.empty:
                try:
                     team_perf_path = Path(DATA_DIR) / 'team_performance_over_time.csv'
                     team_perf_over_time.to_csv(team_perf_path, index=False, encoding='utf-8-sig')
                     print(f"Team performance over time analysis saved to {team_perf_path}")
                except Exception as e: print(f"Error saving team performance over time analysis: {e}")
            else: print("Team performance over time analysis skipped or failed or resulted in empty data.")
            
            # Markdown-raportin generointi (otettu nykyisestä analyze_data.py:stä)
            # Oletetaan, että tarvittava generate_markdown_report-funktio on määritelty ylempänä
            # tai importattu. Tässä esimerkissä se pitäisi kopioida tähän tiedostoon.
            # Jätän sen nyt pois lyhyyden vuoksi, mutta se pitäisi integroida,
            # jos haluat sen mukaan tähän laajempaan skriptiin.
            # Esimerkiksi:
            # from markdown_generator import generate_markdown_report # Jos erillisessä tiedostossa
            # generate_markdown_report(processed_data.copy(), output_filename="PelatutOttelut.md")

            print(f"\nAnalysis script finished at {datetime.datetime.now()}.")

        else:
            print("Data preprocessing failed or resulted in empty data. Halting analysis.")
            # Voit luoda virhelokin tännekin
            with open(Path(OUTPUT_DIR) / "analysis_preprocessing_error.log", "w") as f:
                f.write(f"Preprocessing failed at {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    else:
        print(f"Data loading from '{data_file}' failed. Halting analysis.")
        with open(Path(OUTPUT_DIR) / "analysis_load_error.log", "w") as f:
            f.write(f"Failed to load data from {data_file} at {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
