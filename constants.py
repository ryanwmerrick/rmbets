# SHARED CONFIGURATION

CURRENT_MODEL = "gemini-2.0-flash" 

CURRENT_VERSION = "v1.0"


#REMEMBER:
# - Each active sport costs 3 API tokens to find the odds (if there are games on that day)
# - 
ACTIVE_SPORTS = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "soccer_epl": "EPL",
    "soccer_uefa_champs_league": "UEFA Champions League"
}

REGIONS = "us"
MARKETS = "h2h,spreads,totals"

MARKET_NAMES = ["ML", "Spreads", "Totals"]
