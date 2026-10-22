"""All tunable settings for v2 in one place.

Changing a threshold or prompt means bumping that strategy's version below, so
old and new bets are never mixed in the results.
"""

# The Odds API sport key -> our league label
LEAGUES = {
    "basketball_nba": "NBA",
    "icehockey_nhl": "NHL",
    "americanfootball_nfl": "NFL",
}

# ESPN public API path per league (injuries, scoreboard)
ESPN_PATHS = {
    "NBA": "basketball/nba",
    "NHL": "hockey/nhl",
    "NFL": "football/nfl",
}

# Pinnacle is the sharp reference line. Up to 10 books in one request cost the
# same as one region, so keep this list at 10 or fewer.
SHARP_BOOK = "pinnacle"
US_BOOKS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "williamhill_us",  # Caesars
    "espnbet",
    "betrivers",
    "fanatics",
    "bovada",
    "betonlineag",
]

MORNING_MARKETS = ["h2h", "spreads", "totals"]
EVENING_MARKETS = ["h2h"]

# How far ahead the morning job looks for games (hours from run time)
LOOKAHEAD_HOURS = 20

# A consensus fair line needs at least this many books quoting both sides
MIN_CONSENSUS_BOOKS = 3

STRATEGY_VERSIONS = {
    "market_ev": "2.0",
    "ai_analyst": "2.0",
    "baseline_fav": "2.0",
    "baseline_random": "2.0",
}

MARKET_EV_MIN = 0.025       # bet when EV vs fair line >= 2.5%
AI_EV_MIN = 0.03            # ai_analyst bets when EV >= 3%
AI_MAX_SHIFT = 0.05         # AI may move the market probability by at most 5 points

# Tried in order; the free tier often returns 503 "high demand" on one model
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
GEMINI_SECONDS_BETWEEN_CALLS = 7   # stay under free-tier requests-per-minute
GEMINI_TIMEOUT_SECONDS = 60
GEMINI_MAX_ROUNDS = 3              # rounds through the model list per game
AI_TIME_BUDGET_SECONDS = 35 * 60   # stop calling the AI after this; other strategies still run

# Bets on games that never complete within this many days are voided
VOID_AFTER_DAYS = 4
