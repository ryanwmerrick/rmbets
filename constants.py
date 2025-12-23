# Preparing Research (15 RPM)
RESEARCH_MODEL = "gemini-2.5-flash" 

# The "Boss": High reasoning, very low rate limit (2 RPM)
DECISION_MODEL = "gemini-2.5-pro"

# High reasoning, very low rate limit (2 RPM)
CURRENT_VERSION = "v1.1"

#REMEMBER:
# - Each active sport costs 3 API tokens to find the odds (if there are games on that day)
# - Each sport takes 2 API calls to grade the pick the next day (if there were games for that sport)

ACTIVE_SPORTS = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "soccer_epl": "EPL",
    "soccer_uefa_champs_league": "UEFA Champions League"
}

# What days each sport has games

SPORT_DAYS = {
    "basketball_nba": [0, 1, 2, 3, 4, 5, 6], # Daily
    "icehockey_nhl": [0, 1, 2, 3, 4, 5, 6], # Daily
    "americanfootball_nfl": [0, 3, 4, 5, 6], # Mon, Thu, Sat, Sun (Skip Tue/Wed/Fri)
    "soccer_epl": [0, 1, 2, 4, 5, 6], # Mon, Tue, Wed, Fri, Sat, Sun
    "soccer_uefa_champs_league": [1, 2, 3], # Tue, Wed, Thu
}

REGIONS = "us"
MARKETS = "h2h,spreads,totals"

MARKET_NAMES = ["ML", "Spreads", "Totals"]
