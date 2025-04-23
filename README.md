# Ykkönen 2025 Season Prediction

This repository contains prediction models and analysis for the Finnish Ykkönen (second tier) football league for the 2025 season.

## Current Status

Last updated: **April 23, 2025 11:16:04 UTC** by [Linux88888a](https://github.com/Linux88888a)

The 2025 Ykkönen season has just begun with some teams having played their first matches. The early leaders are Jippo and TPS, both with 3 points from their opening matches.

## Key League Information

- **Competition Format**: 10 teams, double round-robin (18 rounds total)
- **Points Deduction**: PK-35 starts the season with a 2-point deduction per License Committee decision
- **Promotion**: 1st place directly promoted to Veikkausliiga, 2nd place enters promotion playoff
- **Relegation**: 9th and 10th places relegated to Kakkonen (third tier)

## Current Standings (April 23, 2025)

| Pos | Team | MP | W | D | L | GF | GA | GD | Pts |
|-----|------|----|----|----|----|----|----|----|----|
| 1 | Jippo | 1 | 1 | 0 | 0 | 2 | 0 | 2 | 3 |
| 2 | TPS | 1 | 1 | 0 | 0 | 4 | 3 | 1 | 3 |
| 3 | EIF | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | KäPa | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | FC Lahti | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | JäPS | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 7 | HJK Klubi 04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | SJK Akatemia | 1 | 0 | 0 | 1 | 3 | 4 | -1 | 0 |
| 9 | SalPa | 1 | 0 | 0 | 1 | 0 | 2 | -2 | 0 |
| 10 | PK-35 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | -2 |

## Teams for 2025 Season

1. **Jippo** - Based in Joensuu, strong start to the season with a 2-0 win over SalPa
2. **TPS** - Traditional powerhouse from Turku, won 4-3 against SJK Akatemia showing attacking quality
3. **EIF** - From Ekenäs (Tammisaari), yet to play their first match
4. **KäPa** - Helsinki-based club with solid grassroots development
5. **FC Lahti** - Recently relegated from Veikkausliiga, bringing top-tier experience
6. **PK-35** - Helsinki club, starting with a 2-point deduction due to License Committee decision
7. **JäPS** - From Järvenpää, north of Helsinki
8. **HJK Klubi 04** - Development team of Finnish giants HJK
9. **SJK Akatemia** - Academy team of SJK from Seinäjoki, lost 4-3 to TPS showing offensive capabilities
10. **SalPa** - From Salo, lost 2-0 to Jippo in their opening match

## Repository Contents

- **ykkonen_prediction_2025.py**: Python script that generates predictions
- **ykkonen_2025_current.csv**: Current league standings (as of April 23, 2025)
- **ykkonen_2025_prediction.csv**: End-of-season prediction
- **ykkonen_2025_odds.csv**: Promotion and relegation probabilities
- **ykkonen_2025_upcoming.csv**: Upcoming fixture predictions
- **ykkonen_2025_schedule.csv**: Complete schedule for all 18 rounds

## Prediction Model

The prediction uses a statistical model that considers:

- Actual results from the early matches of the 2025 season
- PK-35's 2-point deduction
- Team strength ratings based on squad quality and historical performance
- Home advantage factors
- Form/momentum indicators
- Poisson distribution for realistic score modeling

## How to Use

1. Run the prediction script:
```bash
python ykkonen_prediction_2025.py