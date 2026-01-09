import os
import requests
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from app import app
from models import db, Pick
from constants import RESEARCH_MODEL, DECISION_MODEL, CURRENT_VERSION, ACTIVE_SPORTS, SPORT_DAYS, REGIONS, MARKETS

load_dotenv()

# CONFIGURATION
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================
# 1. PYDANTIC SCHEMAS
# ==========================================

class QualitativeAnalysis(BaseModel):
    matchup: str
    impact_factors: List[str]
    public_sentiment: str = Field(description="Which side does the general public likely favor?")
    sharp_sentiment: str = Field(description="Which side would professional bettors likely favor?") 

class QuantitativeAnalysis(BaseModel):
    matchup: str
    projected_winner: str
    projected_spread: float
    projected_total: float
    confidence_score: int

class RecommendedBet(BaseModel):
    bet_type: str      # "Moneyline", "Spread", "Total"
    selection: str     # e.g., "Lakers -3.5"
    odds: str          # e.g., "-110"
    units_staked: int  # 1, 2, or 3
    value_edge: float  # e.g., 0.045
    rationale: str
    confidence_score: str # "High", "Medium", "Low"

class GameAnalysis(BaseModel):
    matchup: str
    bets: List[RecommendedBet]


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

def get_game_odds(sport_key):
    print(f"  Fetching odds for {sport_key}...")
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    
    eastern = ZoneInfo("America/New_York")
    now_est = datetime.now(eastern)
    start_est = now_est.replace(hour=11, minute=0, second=0, microsecond=0)
    end_est = now_est.replace(hour=23, minute=59, second=59, microsecond=0)
    start_utc = start_est.astimezone(ZoneInfo("UTC"))
    end_utc = end_est.astimezone(ZoneInfo("UTC"))
    start_iso = start_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_iso = end_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": "american",
        "commenceTimeFrom": start_iso,
        "commenceTimeTo": end_iso
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"[API ERROR]: {response.text}")
            return []
        return response.json()
    except Exception as e:
        print(f"[SYSTEM ERROR]: {e}")
        return []

def format_american_odds(price):
    try:
        if float(price) > 0:
            return f"+{price}"
        return str(price)
    except:
        return str(price)

def format_game_data(game):
    home = game['home_team']
    away = game['away_team']
    
    raw_time = game['commence_time']
    game_dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
    
    bookie = next((b for b in game['bookmakers'] if b['key'] in ['draftkings', 'fanduel', 'mgm']), game['bookmakers'][0] if game['bookmakers'] else None)
    if not bookie: return None

    lines = []
    
    for market in bookie['markets']:
        if market['key'] == 'h2h':
            p1 = format_american_odds(market['outcomes'][0]['price'])
            p2 = format_american_odds(market['outcomes'][1]['price'])
            lines.append(f"Moneyline: {market['outcomes'][0]['name']} ({p1}) vs {market['outcomes'][1]['name']} ({p2})")
            
        elif market['key'] == 'spreads':
            p = format_american_odds(market['outcomes'][0]['price'])
            lines.append(f"Spread: {market['outcomes'][0]['name']} {market['outcomes'][0]['point']} ({p})")
            
        elif market['key'] == 'totals':
            p = format_american_odds(market['outcomes'][0]['price'])
            point = market['outcomes'][0]['point']
            if point > 0: point_str = f"+{point}"
            else: point_str = str(point)
            lines.append(f"Total: {market['outcomes'][0]['name']} {market['outcomes'][0]['point']} ({p})")
    
    return {
        "id": game['id'],
        "sport": game['sport_title'],
        "matchup": f"{away} @ {home}",
        "game_time": game_dt,
        "lines_summary": " | ".join(lines)
    }

# ==========================================
# 3. THE 3-AGENT PIPELINE (v1.5 Sharp Follower)
# ==========================================

def run_game_analysis(game_obj):
    matchup = game_obj['matchup']
    lines = game_obj['lines_summary']
    print(f"\nANALYZING: {matchup}")

    # --- AGENT A: QUALITATIVE ---
    prompt_a = f"""
    ROLE: Expert Sports Handicapper & Sharp Money Analyst.
    TASK: Analyze the "Sharp vs. Public" dynamic for: {matchup} ({game_obj['sport']}).
    
    FOCUS:
    1. Identify who the "Public" (casual bettor) is likely backing based on big names/recent TV performance.
    2. Identify who the "Sharps" (pros) would likely back based on value, buy-low spots, or injuries.
    3. List critical injuries/rest factors.
    
    OUTPUT SCHEMA (JSON):
    - impact_factors (list)
    - public_sentiment (string): e.g. "Heavy on Lakers"
    - sharp_sentiment (string): e.g. "Contrarian value on Pistons"
    """
    
    res_a = client.models.generate_content(
        model=RESEARCH_MODEL,
        contents=prompt_a,
        config=types.GenerateContentConfig(response_mime_type='application/json', response_schema=QualitativeAnalysis)
    )
    
    # LIST FIX
    raw_a = json.loads(res_a.text)
    while isinstance(raw_a, list):
        raw_a = raw_a[0] if raw_a else {}
    qual_data = raw_a
    time.sleep(2)

    # --- AGENT B: QUANTITATIVE ---
    prompt_b = f"""
    ROLE: Quantitative Sports Modeler.
    TASK: Create a projection for: {matchup}.
    lines: {lines}
    
    STRATEGY: 
    - Weigh LAST 10 GAMES more heavily.
    - Be realistic with Total Points (regress to mean).
    - If a team is on a B2B (Back-to-Back), penalize their score by 5%.
    
    OUTPUT:
    1. Who wins and by how much? (Projected Spread)
    2. Total points scored? (Projected Total)
    """
    res_b = client.models.generate_content(
        model=RESEARCH_MODEL,
        contents=prompt_b,
        config=types.GenerateContentConfig(response_mime_type='application/json', response_schema=QuantitativeAnalysis)
    )
    
    # LIST FIX
    raw_b = json.loads(res_b.text)
    while isinstance(raw_b, list):
        raw_b = raw_b[0] if raw_b else {}
    quant_data = raw_b
    time.sleep(2)

    # --- AGENT C: DECISION ---
    # Safe getters
    impact_factors = qual_data.get('impact_factors', []) if isinstance(qual_data, dict) else []
    public_bias = qual_data.get('public_sentiment', 'Unknown') if isinstance(qual_data, dict) else 'Unknown'
    sharp_bias = qual_data.get('sharp_sentiment', 'Unknown') if isinstance(qual_data, dict) else 'Unknown'
    
    proj_winner = quant_data.get('projected_winner', 'Unknown') if isinstance(quant_data, dict) else 'Unknown'
    proj_spread = quant_data.get('projected_spread', 0) if isinstance(quant_data, dict) else 0
    proj_total = quant_data.get('projected_total', 0) if isinstance(quant_data, dict) else 0

    final_context = f"""
    MATCHUP: {matchup}
    MARKET LINES: {lines}
    
    SENTIMENT: Public likes: {public_bias}. Sharps likely: {sharp_bias}.
    FACTORS: {json.dumps(impact_factors)}
    MATH PROJECTION: {proj_winner} by {proj_spread} pts. Total: {proj_total}.
    """
    
    prompt_c = f"""
    ROLE: Lead Handicapper.
    CONTEXT: {final_context}
    
    TASK: Identify bets where the MATH aligns with the SHARP sentiment.
    
    STRATEGY (The "Sharp Follower" Method):
    1. FADE THE PUBLIC: Be skeptical if the Math backs a very popular public favorite. 
    2. FOLLOW THE SHARPS: If 'Sharp Sentiment' matches the 'Math Projection', this is a HIGH CONFIDENCE bet.
    3. IGNORE NOISE: If Sharp sentiment and Math disagree, PASS.
    
    THRESHOLDS:
    - Spread Edge > 1.5 points.
    - Total Edge > 2.0 points.
    
    CRITICAL FORMATTING:
    - 'value_edge' must be a decimal (e.g. 0.05 for 5%). 
    - If calculated edge is > 0.40 (40%), assume hallucination and PASS.
    
    OUTPUT:
    - Return a JSON object containing a list of 'bets'.
    """
    
    res_c = client.models.generate_content(
        model=DECISION_MODEL,
        contents=prompt_c,
        config=types.GenerateContentConfig(response_mime_type='application/json', response_schema=GameAnalysis)
    )
    
    # LIST FIX
    raw_c = json.loads(res_c.text)
    while isinstance(raw_c, list):
        raw_c = raw_c[0] if raw_c else {}
    decision = raw_c
    
    return decision

# ==========================================
# 4. MAIN RUNNER
# ==========================================

def run_ingest():
    print("--- Starting Analysis Pipeline (v1.5 Sharp Follower) ---")
    
    today_dow = datetime.today().weekday()
    day_name = datetime.today().strftime('%A')
    print(f"Today is {day_name} (Day {today_dow})")

    all_potential_bets = []
    
    for sport_key in ACTIVE_SPORTS:
        allowed_days = SPORT_DAYS.get(sport_key)
        if allowed_days and today_dow not in allowed_days:
            print(f"[SKIP] {ACTIVE_SPORTS[sport_key]} does not play on {day_name}s.")
            continue

        raw_games = get_game_odds(sport_key)
        if not raw_games: continue

        print(f"Found {len(raw_games)} games for {sport_key}. Analyzing all...")

        for game in raw_games:
            formatted_game = format_game_data(game)
            if not formatted_game: continue
            
            try:
                decision = run_game_analysis(formatted_game)
                
                if isinstance(decision, dict) and decision.get('bets'):
                    for bet in decision['bets']:
                        bet_record = {
                            "sport": formatted_game['sport'],
                            "matchup": formatted_game['matchup'],
                            "game_time": formatted_game['game_time'],
                            "market_type": bet['bet_type'],
                            "selection": bet['selection'],
                            "odds": bet['odds'],
                            "confidence_score": bet['confidence_score'],
                            "value_edge": bet['value_edge'],
                            "rationale": bet['rationale']
                        }
                        all_potential_bets.append(bet_record)
                        print(f"  -> BET FOUND: {bet['selection']} ({bet['confidence_score']})")
                else:
                    print(f"  -> [PASS] {decision.get('reason_for_pass', 'No edge')}")

                print("  [Waiting 10s...]")
                time.sleep(10)
                
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(60)
            
    # --- SAVE TO DB ---
    print(f"\n--- Saving {len(all_potential_bets)} bets ---")
    
    if all_potential_bets:
        with app.app_context():
            db.create_all()
            for bet in all_potential_bets:
                new_pick = Pick(
                    sport=bet['sport'], #type: ignore
                    matchup=bet['matchup'], #type: ignore
                    game_time=bet['game_time'], #type: ignore
                    market_type=bet['market_type'], #type: ignore
                    selection=bet['selection'], #type: ignore
                    odds=bet['odds'], #type: ignore
                    confidence_score=bet['confidence_score'], #type: ignore
                    value_edge=bet['value_edge'], #type: ignore
                    model= DECISION_MODEL, #type: ignore
                    version= CURRENT_VERSION, #type: ignore
                    rationale=bet['rationale'] #type: ignore
                )
                db.session.add(new_pick)
            db.session.commit()
    
    print("--- DONE ---\n")

if __name__ == "__main__":
    run_ingest()