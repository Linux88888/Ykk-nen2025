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
