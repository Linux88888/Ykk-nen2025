import json
import pandas as pd
from datetime import datetime
import re
import io # Tarvitaan suomalaisille päiville

INPUT_JSON = "match_data.json"
OUTPUT_MD = "AnalyysiRaportti.md"

def parse_score(score_str):
    """Muuttaa 'X–Y' -merkkijonon (int, int) tupleksi."""
    if score_str and isinstance(score_str, str) and '–' in score_str:
        try:
            parts = score_str.split('–')
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return None, None
    return None, None

def get_points(home_goals, away_goals):
    """Laskee pisteet kotijoukkueen näkökulmasta."""
    if home_goals is None or away_goals is None:
        return None, None # Ei voida laskea pisteitä
    if home_goals > away_goals:
        return 3, 0 # Kotivoitto
    elif home_goals == away_goals:
        return 1, 1 # Tasapeli
    else:
        return 0, 3 # Vierasvoitto

def parse_datetime(datetime_str):
    """Yrittää parsia 'HH:MM | Pä DD.MM.' tai 'HH:MM | Pä DD.MM.YYYY'."""
    if not datetime_str or '|' not in datetime_str:
        return None, None, None # Palauta None kaikille jos ei voida parsia

    try:
        time_part_str, date_part_str = [part.strip() for part in datetime_str.split('|')]

        # Yritä parsia kellonaika
        try:
            time_obj = datetime.strptime(time_part_str, "%H:%M").time()
        except ValueError:
            time_obj = None # Kellonaika tuntematon

        # Parsi päivämäärä (käsittele vuosi ja suomalaiset päivänimet)
        # Poista mahdollinen piste lopusta
        date_part_str = date_part_str.rstrip('.')

        # Suomesta englanniksi mapitus viikonpäille (jos tarvitaan myöhemmin)
        day_map_fi_to_en = {
            'ma': 'Monday', 'ti': 'Tuesday', 'ke': 'Wednesday',
            'to': 'Thursday', 'pe': 'Friday', 'la': 'Saturday', 'su': 'Sunday'
        }
        # Poista päivän nimi ja ylimääräiset välilyönnit
        date_only_str = re.sub(r'^[a-zA-ZäöåÄÖÅ]+\s*', '', date_part_str).strip()
        weekday_fi = re.match(r'^([a-zA-ZäöåÄÖÅ]+)', date_part_str)
        weekday_fi_str = weekday_fi.group(1).lower() if weekday_fi else None
        weekday_en_str = day_map_fi_to_en.get(weekday_fi_str) if weekday_fi_str else None


        # Oleta kuluva vuosi, jos vuotta ei ole annettu
        year = datetime.now().year
        date_obj = None

        # Yritä formaattia DD.MM.YYYY
        try:
            date_obj = datetime.strptime(date_only_str, "%d.%m.%Y").date()
        except ValueError:
            # Yritä formaattia DD.MM. (lisää kuluva vuosi)
            try:
                date_obj = datetime.strptime(f"{date_only_str}.{year}", "%d.%m.%Y").date()
            except ValueError:
                 date_obj = None # Päivämäärä tuntematon

        return date_obj, time_obj, weekday_en_str # Palauta parsittu date, time ja englanninkielinen viikonpäivä

    except Exception:
        return None, None, None # Yleinen virhe parsinnassa

def format_float(value, precision=1):
    """Muotoilee liukuluvun merkkijonoksi tietyllä tarkkuudella, käsittelee None."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.{precision}f}"

def main():
    # --- Datan lataus ---
    try:
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Virhe ladattaessa tai jäsennettäessä {INPUT_JSON}: {e}")
        all_data = []

    # Suodata vain onnistuneesti haetut ja päättyneet ottelut
    valid_matches = [
        match for match in all_data
        if isinstance(match, dict) and \
           match.get('status') == 'success_finished' and \
           match.get('team_home') and \
           match.get('team_away') and \
           match.get('score')
    ]

    if not valid_matches:
        print("Ei validia otteludataa analysoitavaksi.")
        # Luo tyhjä raportti
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write(f"# Ykkösliiga Data-analyysi\n\nPäivitetty: {datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}\n\nEi dataa saatavilla.\n")
        return

    # --- Datan esikäsittely ja muunnos DataFrameksi ---
    processed_data = []
    for match in valid_matches:
        match_id = match.get('match_id_from_page') or match.get('match_id')
        home_goals, away_goals = parse_score(match.get('score'))
        home_points, away_points = get_points(home_goals, away_goals)
        date_obj, time_obj, weekday = parse_datetime(match.get('match_datetime_raw'))
        month = date_obj.strftime('%Y-%m') if date_obj else None # Kuukausi muodossa YYYY-MM

        data_row = {
            'MatchID': match_id,
            'Date': date_obj,
            'Time': time_obj.strftime('%H:%M') if time_obj else None,
            'Weekday': weekday,
            'Month': month,
            'HomeTeam': match.get('team_home'),
            'AwayTeam': match.get('team_away'),
            'HomeGoals': home_goals,
            'AwayGoals': away_goals,
            'TotalGoals': home_goals + away_goals if home_goals is not None and away_goals is not None else None,
            'HomePoints': home_points,
            'AwayPoints': away_points,
            'Audience': match.get('audience'),
            'Venue': match.get('venue'),
            'Weather': match.get('weather', 'N/A').strip() # Puhdista säädata
        }

        # Lisää keskeiset tilastot omiin sarakkeisiin (jos löytyvät)
        stats = match.get('stats', {})
        data_row['HomeShotsOnTarget'] = stats.get('laukaukset_maali_kohti', {}).get('home')
        data_row['AwayShotsOnTarget'] = stats.get('laukaukset_maali_kohti', {}).get('away')
        data_row['HomeCorners'] = stats.get('kulmapotkut', {}).get('home')
        data_row['AwayCorners'] = stats.get('kulmapotkut', {}).get('away')
        data_row['HomeFouls'] = stats.get('rikkeet', {}).get('home')
        data_row['AwayFouls'] = stats.get('rikkeet', {}).get('away')
        data_row['HomeYellowCards'] = stats.get('varoitukset', {}).get('home')
        data_row['AwayYellowCards'] = stats.get('varoitukset', {}).get('away')
        data_row['HomeRedCards'] = stats.get('kentaltapoistot', {}).get('home')
        data_row['AwayRedCards'] = stats.get('kentaltapoistot', {}).get('away')

        processed_data.append(data_row)

    df = pd.DataFrame(processed_data)
    # Muunna numerot oikeisiin tyyppeihin, virheet NaN:ksi
    numeric_cols = ['HomeGoals', 'AwayGoals', 'TotalGoals', 'HomePoints', 'AwayPoints', 'Audience',
                    'HomeShotsOnTarget', 'AwayShotsOnTarget', 'HomeCorners', 'AwayCorners',
                    'HomeFouls', 'AwayFouls', 'HomeYellowCards', 'AwayYellowCards',
                    'HomeRedCards', 'AwayRedCards']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- Analyysit ---

    # 1. Yleiskatsaus
    total_matches = len(df)
    avg_audience = df['Audience'].mean()
    total_goals = df['TotalGoals'].sum()
    avg_goals_per_match = df['TotalGoals'].mean()

    # 2. Kuukausittainen analyysi
    monthly_analysis = df.groupby('Month').agg(
        Otteluita=('MatchID', 'count'),
        Keskiyleisö=('Audience', 'mean'),
        MaalejaKeskim=('TotalGoals', 'mean')
    ).reset_index().sort_values('Month')

    # 3. Sarjataulukko
    league_table = {}
    teams = pd.concat([df['HomeTeam'], df['AwayTeam']]).unique()
    for team in teams:
        league_table[team] =
