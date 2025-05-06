import pandas as pd
import numpy as np
# import matplotlib.pyplot as plt # Kommentoitu pois, jos ei aktiivisesti käytetä plotteja tässä skriptissä
# import seaborn as sns # Kommentoitu pois
# import plotly.express as px # Kommentoitu pois
# import plotly.graph_objects as go # Kommentoitu pois
# from plotly.subplots import make_subplots # Kommentoitu pois
import datetime
import os
import warnings
import json
import re
from pathlib import Path # Lisätty Path-kirjasto

# Suppress warning messages
warnings.filterwarnings('ignore')

# Configuration
DEBUG = False 
OUTPUT_DIR = "output"
PLOTS_DIR = os.path.join(OUTPUT_DIR, "plots") # Vaikka plottaus on kommentoitu, kansio voi olla olemassa
DATA_DIR = os.path.join(OUTPUT_DIR, "data")

# Create output directories
for directory in [OUTPUT_DIR, PLOTS_DIR, DATA_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True) # Käytä Pathlibia

# plt.style.use('seaborn-v0_8-whitegrid') # Kommentoitu pois
# sns.set_palette("viridis") # Kommentoitu pois

def debug_print(message):
    if DEBUG:
        print(f"DEBUG: {message}")

def load_data(filepath="match_data.json"): # Oletusarvo tiedostonimelle
    try:
        if not Path(filepath).exists():
            print(f"Error: Data file not found at {filepath}")
            return None
        if Path(filepath).stat().st_size <= 2: # Tyhjä JSON "[]" on 2 tavua
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
    if df is None or df.empty:
        print("Error: Input DataFrame is None or empty in preprocess_data.")
        return None
    processed_df = df.copy()

    if 'match_id' in processed_df.columns:
        original_row_count = len(processed_df)
        processed_df.dropna(subset=['match_id'], inplace=True)
        if len(processed_df) < original_row_count:
            debug_print(f"Removed {original_row_count - len(processed_df)} rows with missing match_id.")
        processed_df['match_id'] = pd.to_numeric(processed_df['match_id'], errors='coerce').astype('Int64')

    rename_map = {
        'score': 'Tulos', 'team_home': 'Koti', 'team_away': 'Vieras',
        'audience': 'Yleisö', 'venue': 'Stadion', 
        'match_datetime_raw': 'PvmAikaRaw', 'match_status_raw': 'OttelunTilaRaaka',
        'scrape_timestamp': 'HakuAikaleima'
    }
    processed_df.rename(columns={k: v for k, v in rename_map.items() if k in processed_df.columns}, inplace=True)
    
    processed_df['Pvm'] = pd.NaT
    processed_df['Aika'] = None

    if 'PvmAikaRaw' in processed_df.columns:
        temp_dt_series = processed_df['PvmAikaRaw'].astype(str).str.split('|', n=1, expand=True)
        if not temp_dt_series.empty:
            processed_df['Aika'] = temp_dt_series[0].str.strip()
            if temp_dt_series.shape[1] > 1:
                date_part_cleaned = temp_dt_series[1].str.strip().str.replace(r'^[A-Za-zÄÖÅäöå]+\s+', '', regex=True)
                date_part_cleaned = date_part_cleaned.str.rstrip('.')
                processed_df['Pvm'] = date_part_cleaned
        else:
             time_like = processed_df['PvmAikaRaw'].str.match(r'^\d{1,2}:\d{2}$')
             date_like = processed_df['PvmAikaRaw'].str.contains(r'\d{1,2}\.\d{1,2}')
             if time_like is not None: processed_df.loc[time_like, 'Aika'] = processed_df.loc[time_like, 'PvmAikaRaw']
             if date_like is not None: processed_df.loc[date_like, 'Pvm'] = processed_df.loc[date_like, 'PvmAikaRaw']

    processed_df['home_goals'] = pd.NA
    processed_df['away_goals'] = pd.NA
    if 'Tulos' in processed_df.columns:
        valid_scores = processed_df['Tulos'].notna() & processed_df['Tulos'].astype(str).str.contains('–')
        score_parts = processed_df.loc[valid_scores, 'Tulos'].astype(str).str.split('–', n=1, expand=True)
        if not score_parts.empty:
            processed_df.loc[valid_scores, 'home_goals'] = pd.to_numeric(score_parts[0].str.strip(), errors='coerce')
            if score_parts.shape[1] > 1:
                 processed_df.loc[valid_scores, 'away_goals'] = pd.to_numeric(score_parts[1].str.strip(), errors='coerce')
    
    processed_df['home_goals'] = processed_df['home_goals'].astype('Int64')
    processed_df['away_goals'] = processed_df['away_goals'].astype('Int64')

    processed_df['total_goals'] = processed_df['home_goals'].fillna(0) + processed_df['away_goals'].fillna(0)
    processed_df.loc[processed_df['home_goals'].isna() | processed_df['away_goals'].isna(), 'total_goals'] = pd.NA
    processed_df['total_goals'] = processed_df['total_goals'].astype('Int64')

    conditions = [
        (processed_df['home_goals'] > processed_df['away_goals']),
        (processed_df['home_goals'] < processed_df['away_goals']),
        (processed_df['home_goals'] == processed_df['away_goals']) & (processed_df['home_goals'].notna())
    ]
    choices = ['home_win', 'away_win', 'draw']
    processed_df['result'] = np.select(conditions, choices, default=None)

    processed_df['match_datetime'] = pd.NaT
    valid_pvm = processed_df['Pvm'].notna() & (processed_df['Pvm'] != '')
    valid_aika = processed_df['Aika'].notna() & (processed_df['Aika'] != '')
    
    if valid_pvm.any() and valid_aika.any():
        def parse_flexible_date(date_str):
            if pd.isna(date_str): return pd.NaT
            for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m."):
                try:
                    dt_obj = datetime.datetime.strptime(str(date_str).strip(), fmt)
                    if fmt == "%d.%m.":
                        dt_obj = dt_obj.replace(year=datetime.datetime.now().year)
                    return dt_obj
                except ValueError: continue
            return pd.NaT

        temp_date_series = processed_df.loc[valid_pvm, 'Pvm'].apply(parse_flexible_date)
        datetime_combined_str = temp_date_series.dt.strftime('%Y-%m-%d').fillna('') + ' ' + processed_df.loc[valid_aika, 'Aika'].fillna('')
        datetime_combined_str = datetime_combined_str.str.strip()
        processed_df.loc[valid_pvm & valid_aika, 'match_datetime'] = pd.to_datetime(
            datetime_combined_str.loc[valid_pvm & valid_aika], format='%Y-%m-%d %H:%M', errors='coerce'
        )

    processed_df['date'] = processed_df['match_datetime'].dt.date
    for col in ['year', 'month', 'day', 'weekday', 'hour']:
        processed_df[col] = getattr(processed_df['match_datetime'].dt, col).astype('Int64')
    processed_df['weekday_name'] = processed_df['match_datetime'].dt.day_name()
    processed_df['month_name'] = processed_df['match_datetime'].dt.month_name()
    
    if 'Yleisö' in processed_df.columns:
        processed_df['attendance'] = pd.to_numeric(processed_df['Yleisö'], errors='coerce').astype('Int64')
    else:
        processed_df['attendance'] = pd.NA 

    essential_cols = ['Koti', 'Vieras', 'home_goals', 'away_goals', 'result', 'match_datetime']
    cols_to_check = [col for col in essential_cols if col in processed_df.columns]
    if cols_to_check:
        processed_df.dropna(subset=cols_to_check, how='all', inplace=True)

    return processed_df

def calculate_league_table(df):
    required_cols = ['Koti', 'Vieras', 'home_goals', 'away_goals', 'result']
    if df is None or not all(col in df.columns for col in required_cols):
        print(f"Error: Missing required columns for league table. Found: {df.columns if df is not None else 'None'}")
        return pd.DataFrame()

    match_df = df[
        df['result'].notna() &
        df['Koti'].notna() & df['Koti'].ne('') & 
        df['Vieras'].notna() & df['Vieras'].ne('') &
        df['home_goals'].notna() & 
        df['away_goals'].notna()
    ].copy()

    if 'OttelunTilaRaaka' in match_df.columns:
        match_df = match_df[match_df['OttelunTilaRaaka'].astype(str).str.lower().str.contains('päättynyt')]
    
    if len(match_df) == 0:
        print("No valid (ended) match data for league table.")
        return pd.DataFrame()

    teams_stats = {}
    for _, match in match_df.iterrows():
        home_team, away_team = match['Koti'], match['Vieras']
        h_goals, a_goals = int(match['home_goals']), int(match['away_goals'])
        for team in [home_team, away_team]:
            if team not in teams_stats:
                teams_stats[team] = {'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'goals_for': 0, 'goals_against': 0, 'points': 0, 'clean_sheets': 0, 'failed_to_score': 0}
        
        teams_stats[home_team]['played'] += 1; teams_stats[away_team]['played'] += 1
        teams_stats[home_team]['goals_for'] += h_goals; teams_stats[home_team]['goals_against'] += a_goals
        teams_stats[away_team]['goals_for'] += a_goals; teams_stats[away_team]['goals_against'] += h_goals

        if h_goals == 0: teams_stats[home_team]['failed_to_score'] += 1
        if a_goals == 0: teams_stats[away_team]['failed_to_score'] += 1
        if h_goals == 0 and away_team in teams_stats: teams_stats[away_team]['clean_sheets'] += 1
        if a_goals == 0 and home_team in teams_stats: teams_stats[home_team]['clean_sheets'] += 1
            
        if match['result'] == 'home_win':
            teams_stats[home_team]['wins'] += 1; teams_stats[home_team]['points'] += 3; teams_stats[away_team]['losses'] += 1
        elif match['result'] == 'away_win':
            teams_stats[away_team]['wins'] += 1; teams_stats[away_team]['points'] += 3; teams_stats[home_team]['losses'] += 1
        elif match['result'] == 'draw':
            teams_stats[home_team]['draws'] += 1; teams_stats[home_team]['points'] += 1
            teams_stats[away_team]['draws'] += 1; teams_stats[away_team]['points'] += 1
    
    pk35_name_part = "pk-35" 
    for team_key in list(teams_stats.keys()):
        if isinstance(team_key, str) and pk35_name_part in team_key.lower():
            teams_stats[team_key]['points'] -= 2; break
            
    if not teams_stats: return pd.DataFrame()
    table_df = pd.DataFrame.from_dict(teams_stats, orient='index'); table_df['team'] = table_df.index
    table_df['goal_difference'] = table_df['goals_for'] - table_df['goals_against']
    for col in ['avg_goals_for', 'avg_goals_against', 'win_percentage']: table_df[col] = 0.0 # Alustus
    
    if 'played' in table_df.columns and table_df['played'].sum() > 0: # Varmista, että played-sarake on olemassa
        table_df['avg_goals_for'] = table_df.apply(lambda r: round(r['goals_for'] / r['played'], 2) if r['played'] > 0 else 0, axis=1)
        table_df['avg_goals_against'] = table_df.apply(lambda r: round(r['goals_against'] / r['played'], 2) if r['played'] > 0 else 0, axis=1)
        table_df['win_percentage'] = table_df.apply(lambda r: round((r['wins'] / r['played']) * 100, 1) if r['played'] > 0 else 0, axis=1)

    sort_cols = ['points', 'goal_difference', 'goals_for']
    valid_sort_cols = [c for c in sort_cols if c in table_df.columns]
    if valid_sort_cols: table_df = table_df.sort_values(by=valid_sort_cols, ascending=[False]*len(valid_sort_cols))
    
    table_df.reset_index(drop=True, inplace=True); table_df['rank'] = table_df.index + 1
    
    ordered_cols = ['rank', 'team', 'played', 'wins', 'draws', 'losses', 'goals_for', 'goals_against', 'goal_difference', 'points', 'avg_goals_for', 'avg_goals_against', 'win_percentage', 'clean_sheets', 'failed_to_score']
    final_cols = [c for c in ordered_cols if c in table_df.columns]
    return table_df[final_cols]

def generate_markdown_report(df, output_filename="PelatutOttelut.md", max_rows=75):
    if df is None or df.empty:
        print("Cannot generate Markdown report: DataFrame is empty or None.")
        # Varmistetaan, että tyhjäkin raportti luodaan, jotta workflow ei kaadu tiedoston puutteeseen
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(f"# Pelatut Ottelut (Ykkösliiga)\n\nPäivitetty: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
            f.write("Ei pelattuja otteluita datassa (status: success_finished ja tarvittavat tiedot löytyvät).\n")
        print(f"::set-output name=md_file_path::{output_filename}") # Ilmoita tiedostonimi silti
        return

    # Käytetään df:ää suoraan, olettaen että se on jo esikäsitelty
    # Suodata vain onnistuneesti haetut ja päättyneet ottelut
    report_df = df[
        df['OttelunTilaRaaka'].astype(str).str.lower().str.contains('päättynyt') &
        df['status'].astype(str).str.lower().eq('success_finished') & # Varmistetaan myös skraperin status
        df['Koti'].notna() &
        df['Vieras'].notna() &
        df['Tulos'].notna()
    ].copy()

    # Järjestä ensisijaisesti scrape_timestampin mukaan (uusin ensin), sitten match_id
    if 'HakuAikaleima' in report_df.columns:
        report_df['HakuAikaleima'] = pd.to_datetime(report_df['HakuAikaleima'], errors='coerce')
        sort_key_1 = report_df['HakuAikaleima'].fillna(pd.Timestamp.min)
    else:
        sort_key_1 = pd.Timestamp.min # Jos saraketta ei ole, käytä oletusta

    if 'match_id' in report_df.columns:
        sort_key_2 = report_df['match_id'].fillna(0)
    else:
        sort_key_2 = 0
        
    report_df = report_df.sort_values(by=['HakuAikaleima', 'match_id'], ascending=[False, False], key=lambda x: sort_key_1 if x.name == 'HakuAikaleima' else sort_key_2)
    
    limited_matches_list = report_df.head(max_rows).to_dict(orient='records')

    utc_now = datetime.datetime.now(datetime.timezone.utc)
    markdown_content = f"# Pelatut Ottelut (Ykkösliiga)\n\nPäivitetty: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"

    if not limited_matches_list:
        markdown_content += "Ei pelattuja otteluita datassa (status: success_finished ja tarvittavat tiedot löytyvät).\n"
    else:
        header = "| Pvm | Aika | Kotijoukkue | Tulos | Vierasjoukkue | Yleisö | Paikka | Sää | Ottelu ID |\n"
        separator = "|:----|:-----|:------------|:------|:--------------|:-------|:-------|:----|:----------|\n"
        markdown_content += header + separator
        stats_sections = ""

        for match_dict in limited_matches_list: # Käytä listaa sanakirjoja
            raw_dt = match_dict.get('PvmAikaRaw', '') # Käytä jo prosessoituja nimiä
            date_part, time_part = 'N/A', 'N/A'
            if isinstance(raw_dt, str) and '|' in raw_dt:
                parts = raw_dt.split('|', 1); time_part = parts[0].strip(); date_part = parts[1].strip().replace('.', '. ').rstrip('. ') 
            elif isinstance(raw_dt, str): 
                if ':' in raw_dt: time_part = raw_dt.strip()
                else: date_part = raw_dt.strip().replace('.', '. ').rstrip('. ')

            venue = match_dict.get('Stadion', 'N/A') or 'N/A'
            weather = match_dict.get('weather', 'N/A') or 'N/A' # Olettaen, että 'weather' on skrapattu kenttä
            audience = match_dict.get('Yleisö', 'N/A')
            audience_str = str(int(audience)) if pd.notna(audience) and isinstance(audience, (int, float)) else 'N/A'

            match_id_display = match_dict.get('match_id_from_page') or match_dict.get('match_id', 'N/A')
            home_team = match_dict.get('Koti', 'N/A')
            away_team = match_dict.get('Vieras', 'N/A')
            score = match_dict.get('Tulos', 'N/A')

            table_row = f"| {str(date_part)} | {str(time_part)} | {str(home_team)} | {str(score)} | {str(away_team)} | {audience_str} | {str(venue)} | {str(weather)} | {str(match_id_display)} |\n"
            markdown_content += table_row

            stats_data = match_dict.get('stats', {}) # Olettaen, että 'stats' on sanakirja JSON:ssa
            if isinstance(stats_data, dict) and stats_data: # Varmista, että on sanakirja eikä tyhjä
                stats_sections += f"\n## Tilastot: {home_team} vs {away_team} ({date_part} - ID: {match_id_display})\n\n"
                stats_sections += "| Tilasto                 | Koti | Vieras |\n" 
                stats_sections += "|:------------------------|:-----|:-------|\n"
                
                stat_definitions = {
                    'maalintekoyritykset': 'Maalintekoyritykset', 'maalintekoyritykset_maalia_kohti': 'Yritykset maalia kohti',
                    'ohi_maalin': 'Ohi maalin', 'blokki': 'Blokatut yritykset', 'kulmapotkut': 'Kulmapotkut',
                    'paitsiot': 'Paitsiot', 'virheet': 'Virheet', 'keltaiset_kortit': 'Keltaiset kortit',
                    'punaiset_kortit': 'Punaiset kortit', 'pallonhallinta': 'Pallonhallinta (%)',
                    'hyokkaykset': 'Hyökkäykset', 'vaaralliset_hyokkaykset': 'Vaaralliset hyökkäykset',
                }
                for key_clean, display_name in stat_definitions.items():
                    if key_clean in stats_data: 
                        values = stats_data[key_clean]
                        home_val = values.get('home', 'N/A'); away_val = values.get('away', 'N/A')
                        stats_sections += f"| {display_name:<23} | {str(home_val):<4} | {str(away_val):<6} |\n"
                for key, values in sorted(stats_data.items()):
                    if key not in stat_definitions:
                        stat_name = key.replace('_', ' ').capitalize()
                        home_val = values.get('home', 'N/A'); away_val = values.get('away', 'N/A')
                        stats_sections += f"| {stat_name:<23} | {str(home_val):<4} | {str(away_val):<6} |\n"
                stats_sections += "\n" 
            else:
                stats_sections += f"\n## Tilastot: {home_team} vs {away_team} ({date_part} - ID: {match_id_display})\n\n*Ei tilastotietoja saatavilla.*\n\n" 
        markdown_content += "\n---\n" + stats_sections

    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"Markdown report generated successfully: {output_filename}")
        print(f"::set-output name=md_file_path::{output_filename}") # Ilmoita tiedostonimi workflow'lle
    except Exception as e:
        print(f"Error writing Markdown file {output_filename}: {e}")
        print(f"::set-output name=md_file_path::") # Tyhjä, jos virhe

if __name__ == "__main__":
    print(f"Starting analysis script at {datetime.datetime.now()}...")
    match_data_df = load_data()

    if match_data_df is not None and not match_data_df.empty:
        print(f"Data loaded. Rows: {len(match_data_df)}")
        processed_df = preprocess_data(match_data_df.copy()) 

        if processed_df is not None and not processed_df.empty:
            print(f"Data preprocessed. Rows: {len(processed_df)}")

            league_table = calculate_league_table(processed_df.copy())
            if league_table is not None and not league_table.empty:
                 print("League table calculated.")
                 try:
                     league_table_path = Path(DATA_DIR) / 'league_standings_calculated.csv'
                     league_table.to_csv(league_table_path, index=False, encoding='utf-8-sig')
                     print(f"League table saved to {league_table_path}")
                 except Exception as e: print(f"Error saving league_standings_calculated.csv: {e}")
            else: print("Could not calculate league table or table is empty.")
            
            # Generoidaan Markdown-raportti tässä
            print("Generating Markdown report (PelatutOttelut.md)...")
            # Oletetaan, että 'status' on jo sarakkeena processed_df:ssä skraperin jäljiltä
            # Jos ei, se pitää lisätä tai hakea toisella tavalla
            if 'status' not in processed_df.columns and 'OttelunTilaRaaka' in processed_df.columns:
                # Yksinkertainen status-määritys raportointia varten, jos skraperin status puuttuu
                processed_df['status'] = processed_df['OttelunTilaRaaka'].apply(
                    lambda x: 'success_finished' if isinstance(x, str) and 'päättynyt' in x.lower() else 'unknown'
                )


            generate_markdown_report(processed_df.copy(), output_filename="PelatutOttelut.md")
            # ::set-output on jo generate_markdown_report-funktion sisällä

            # Muut aiemmat analyysit (esim. attendance) voidaan lisätä takaisin tarvittaessa
            # attendance_analysis = analyze_attendance_patterns(processed_df.copy()) ...

            print(f"\nAnalysis script finished at {datetime.datetime.now()}.")
        else:
            print("Data preprocessing failed or resulted in empty data.")
    else:
        print(f"Data loading failed or file is empty. Halting analysis.")
        # Luodaan tyhjä raportti, jotta commit-vaihe ei epäonnistu tiedoston puutteeseen
        generate_markdown_report(pd.DataFrame(), output_filename="PelatutOttelut.md")

