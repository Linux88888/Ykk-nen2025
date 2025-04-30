import json
import pandas as pd
from datetime import datetime
import re
import io  # Tarvitaan suomalaisille päiville
import os  # Lisätty tiedostopolkujen käsittelyyn
import sys  # Lisätty virhehallintaan

INPUT_JSON = "match_data.json"
OUTPUT_MD = "AnalyysiRaportti.md"

# Lisätty debug-tulostus funktio
def debug_print(message):
    print(f"DEBUG: {message}")

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
        return None, None  # Ei voida laskea pisteitä
    if home_goals > away_goals:
        return 3, 0  # Kotivoitto
    elif home_goals == away_goals:
        return 1, 1  # Tasapeli
    else:
        return 0, 3  # Vierasvoitto

def parse_datetime(datetime_str):
    """Yrittää parsia 'HH:MM | Pä DD.MM.' tai 'HH:MM | Pä DD.MM.YYYY'."""
    if not datetime_str or '|' not in datetime_str:
        return None, None, None  # Palauta None kaikille jos ei voida parsia

    try:
        time_part_str, date_part_str = [part.strip() for part in datetime_str.split('|')]

        # Yritä parsia kellonaika
        try:
            time_obj = datetime.strptime(time_part_str, "%H:%M").time()
        except ValueError:
            time_obj = None  # Kellonaika tuntematon

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
                date_obj = None  # Päivämäärä tuntematon

        return date_obj, time_obj, weekday_en_str  # Palauta parsittu date, time ja englanninkielinen viikonpäivä

    except Exception as e:
        debug_print(f"Virhe parsittaessa päivämäärää '{datetime_str}': {str(e)}")
        return None, None, None  # Yleinen virhe parsinnassa

def format_float(value, precision=1):
    """Muotoilee liukuluvun merkkijonoksi tietyllä tarkkuudella, käsittelee None."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.{precision}f}"

def main():
    debug_print(f"Skripti käynnistyi. Työhakemisto: {os.getcwd()}")
    debug_print(f"Etsitään tiedostoa: {INPUT_JSON}")
    
    # --- Datan lataus ---
    try:
        if not os.path.exists(INPUT_JSON):
            debug_print(f"Tiedostoa {INPUT_JSON} ei löytynyt!")
            # Listaa työhakemiston tiedostot debuggausta varten
            debug_print(f"Hakemiston sisältö: {os.listdir('.')}")
            raise FileNotFoundError(f"Tiedostoa {INPUT_JSON} ei löytynyt työhakemistosta.")
            
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            debug_print(f"Tiedosto {INPUT_JSON} avattu onnistuneesti.")
            all_data = json.load(f)
            debug_print(f"JSON ladattu. Rivejä: {len(all_data)}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        debug_print(f"Virhe ladattaessa tai jäsennettäessä {INPUT_JSON}: {str(e)}")
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
    debug_print(f"Valideja otteluita suodatuksen jälkeen: {len(valid_matches)}")

    if not valid_matches:
        debug_print("Ei validia otteludataa analysoitavaksi.")
        # Luo tyhjä raportti
        try:
            with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
                f.write(f"# Ykkösliiga Data-analyysi\n\nPäivitetty: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nEi dataa saatavilla.\n")
                debug_print(f"Tyhjä raportti tallennettu tiedostoon {OUTPUT_MD}")
        except Exception as e:
            debug_print(f"Virhe tyhjän raportin tallennuksessa: {str(e)}")
        return

    # --- Datan esikäsittely ja muunnos DataFrameksi ---
    processed_data = []
    for match in valid_matches:
        match_id = match.get('match_id_from_page') or match.get('match_id')
        home_goals, away_goals = parse_score(match.get('score'))
        home_points, away_points = get_points(home_goals, away_goals)
        date_obj, time_obj, weekday = parse_datetime(match.get('match_datetime_raw'))
        month = date_obj.strftime('%Y-%m') if date_obj else None  # Kuukausi muodossa YYYY-MM

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
            'Weather': match.get('weather', 'N/A').strip()  # Puhdista säädata
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

    debug_print(f"Käsiteltyjä ottelurivejä: {len(processed_data)}")
    df = pd.DataFrame(processed_data)
    
    # Muunna numerot oikeisiin tyyppeihin, virheet NaN:ksi
    numeric_cols = ['HomeGoals', 'AwayGoals', 'TotalGoals', 'HomePoints', 'AwayPoints', 'Audience',
                   'HomeShotsOnTarget', 'AwayShotsOnTarget', 'HomeCorners', 'AwayCorners',
                   'HomeFouls', 'AwayFouls', 'HomeYellowCards', 'AwayYellowCards',
                   'HomeRedCards', 'AwayRedCards']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    debug_print(f"DataFrame luotu. Rivejä: {len(df)}, sarakkeita: {len(df.columns)}")
    
    # --- Analyysit ---

    # 1. Yleiskatsaus
    total_matches = len(df)
    avg_audience = df['Audience'].mean()
    total_goals = df['TotalGoals'].sum()
    avg_goals_per_match = df['TotalGoals'].mean()

    debug_print("Yleiskatsausanalyysit valmiit.")

    # 2. Kuukausittainen analyysi
    try:
        monthly_analysis = df.groupby('Month').agg(
            Otteluita=('MatchID', 'count'),
            Keskiyleisö=('Audience', 'mean'),
            MaalejaKeskim=('TotalGoals', 'mean')
        ).reset_index().sort_values('Month')
        debug_print(f"Kuukausianalyysi valmis. Kuukausia: {len(monthly_analysis)}")
    except Exception as e:
        debug_print(f"Virhe kuukausianalyysissä: {str(e)}")
        monthly_analysis = pd.DataFrame(columns=['Month', 'Otteluita', 'Keskiyleisö', 'MaalejaKeskim'])

    # 3. Sarjataulukko
    try:
        league_table = {}
        teams = pd.concat([df['HomeTeam'], df['AwayTeam']]).unique()
        debug_print(f"Sarjataulukon koostaminen. Joukkueita: {len(teams)}")
        
        for team in teams:
            # Etsi kaikki ottelut, joissa tämä joukkue on ollut mukana
            home_matches = df[df['HomeTeam'] == team]
            away_matches = df[df['AwayTeam'] == team]
            
            # Laske pisteet, maalit, jne.
            points = home_matches['HomePoints'].sum() + away_matches['AwayPoints'].sum()
            goals_for = home_matches['HomeGoals'].sum() + away_matches['AwayGoals'].sum()
            goals_against = home_matches['AwayGoals'].sum() + away_matches['HomeGoals'].sum()
            
            league_table[team] = {
                'Ottelut': len(home_matches) + len(away_matches),
                'Pisteet': points,
                'Tehdyt Maalit': goals_for,
                'Päästetyt Maalit': goals_against,
                'Maaliero': goals_for - goals_against
            }

        # Muunna sarjataulukko DataFrame-muotoon ja järjestä
        league_df = pd.DataFrame.from_dict(league_table, orient='index')
        league_df = league_df.sort_values(['Pisteet', 'Maaliero'], ascending=[False, False])
        debug_print("Sarjataulukko valmis.")
        
    except Exception as e:
        debug_print(f"Virhe sarjataulukon koostamisessa: {str(e)}")
        league_df = pd.DataFrame(columns=['Ottelut', 'Pisteet', 'Tehdyt Maalit', 'Päästetyt Maalit', 'Maaliero'])

    # --- Raportin kirjoitus tiedostoon ---
    try:
        debug_print(f"Aloitetaan raportin kirjoitus tiedostoon {OUTPUT_MD}")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write(f"# Ykkösliiga Data-analyysi\n\n")
            f.write(f"Päivitetty: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 1. Yleiskatsaus
            f.write("## Yleiskatsaus\n\n")
            f.write(f"- Otteluita yhteensä: {total_matches}\n")
            f.write(f"- Keskimääräinen yleisömäärä: {format_float(avg_audience)} katsojaa\n")
            f.write(f"- Maaleja yhteensä: {int(total_goals) if not pd.isna(total_goals) else 'N/A'}\n")
            f.write(f"- Maaleja per ottelu: {format_float(avg_goals_per_match)}\n\n")
            
            # 2. Kuukausittainen analyysi
            f.write("## Kuukausittainen analyysi\n\n")
            f.write("| Kuukausi | Otteluita | Keskiyleisö | Maaleja/ottelu |\n")
            f.write("|----------|-----------|-------------|---------------|\n")
            for _, row in monthly_analysis.iterrows():
                f.write(f"| {row['Month']} | {int(row['Otteluita'])} | {format_float(row['Keskiyleisö'])} | {format_float(row['MaalejaKeskim'])} |\n")
            f.write("\n")
            
            # 3. Sarjataulukko
            f.write("## Sarjataulukko\n\n")
            f.write("| Joukkue | Ottelut | Pisteet | Tehdyt Maalit | Päästetyt Maalit | Maaliero |\n")
            f.write("|---------|---------|---------|---------------|-----------------|----------|\n")
            for team, row in league_df.iterrows():
                # Käytä format_float-funktiota varmistamaan, että kaikki arvot ovat valideja
                f.write(f"| {team} | {int(row['Ottelut'])} | {int(row['Pisteet'])} | ")
                f.write(f"{int(row['Tehdyt Maalit'])} | {int(row['Päästetyt Maalit'])} | ")
                f.write(f"{int(row['Maaliero'])} |\n")
                
        debug_print(f"Raportti kirjoitettu onnistuneesti tiedostoon {OUTPUT_MD}")
        # Tarkista, että tiedosto on todella olemassa ja sisältää dataa
        if os.path.exists(OUTPUT_MD):
            file_size = os.path.getsize(OUTPUT_MD)
            debug_print(f"Tiedosto {OUTPUT_MD} on olemassa. Koko: {file_size} tavua.")
        else:
            debug_print(f"VIRHE: Tiedostoa {OUTPUT_MD} ei luotu onnistuneesti!")
            
    except Exception as e:
        debug_print(f"KRIITTINEN VIRHE raportin kirjoituksessa: {str(e)}")
        # Yritä kirjoittaa virheilmoitus yksinkertaisella tavalla
        try:
            with open("virhe_raportti.txt", 'w', encoding='utf-8') as f:
                f.write(f"Virhe AnalyysiRaportti.md -tiedoston luonnissa: {str(e)}\n")
                f.write(f"Aikaleima: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            print("Ei voitu kirjoittaa edes virheilmoitusta tiedostoon!")

# Varmista, että main() suoritetaan kun skripti ajetaan
if __name__ == "__main__":
    try:
        debug_print("Skriptin suoritus alkaa")
        main()
        debug_print("Skripti suoritettu onnistuneesti")
    except Exception as e:
        debug_print(f"Odottamaton virhe pääskriptissä: {str(e)}")
        sys.exit(1)  # Poistutaan virheellä
