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
# FLASK IMPORTS
from app import app
from models import db, Pick

from constants import RESEARCH_MODEL, DECISION_MODEL, CURRENT_VERSION, ACTIVE_SPORTS, SPORT_DAYS, REGIONS, MARKETS
load_dotenv()

# CONFIGURATION
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================
# 1. NEW PYDANTIC SCHEMAS (LIST SUPPORT)
# ==========================================

class QualitativeAnalysis(BaseModel):
    matchup: str
    impact_factors: List[str] 
    model_breakers: bool
    team_a_motivation: int = Field(ge=1, le=10)
    team_b_motivation: int = Field(ge=1, le=10)

class QuantitativeAnalysis(BaseModel):
    matchup: str
    projected_winner: str
    projected_spread: float
    projected_total: float
    confidence_score: int
    home_score_range: dict 
    away_score_range: dict
    implied_spread: float 
    confidence_score: int

class RecommendedBet(BaseModel):
    bet_type: str      # "Moneyline", "Spread", "Total"
    selection: str     # e.g., "Lakers -3.5"
    odds: str          # e.g., "-110"
    units_staked: int  # 1, 2, or 3
    value_edge: float  # e.g., 0.045
    rationale: str
    confidence_score: str # "High", "Medium", "Low"

# The AI returns this Wrapper, which contains a LIST of bets
class GameAnalysis(BaseModel):
    matchup: str
    bets: List[RecommendedBet]
    reason_for_pass: Optional[str] = None 


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

#Gets the game odds from The Odds API
def get_game_odds(sport_key):
    print(f"  Fetching odds for {sport_key}...")
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    
    #PARAMETERS
    # time parameter 
    eastern = ZoneInfo("America/New_York")
    now_est = datetime.now(eastern)
    # 11:00 AM EST to 11:59PM EST (initialize in EST, convert to UTC, convert to ISO)
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

# Formats the AI output
def format_game_data(game):
    home = game['home_team']
    away = game['away_team']
    
    #get game time
    raw_time = game['commence_time']
    # Remove the 'Z' and parse
    game_dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
    
    # Gets all the bookies
    bookie = next((b for b in game['bookmakers'] if b['key'] in ['draftkings', 'fanduel', 'mgm']), game['bookmakers'][0] if game['bookmakers'] else None)
    if not bookie: return None

    # Gets the lines from all the bookies (well-formatted)
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
            if point > 0:
                point_str = f"+{point}"
            else:
                point_str = str(point)
            lines.append(f"Total: {market['outcomes'][0]['name']} {market['outcomes'][0]['point']} ({p})")
    
    return {
        "id": game['id'],
        "sport": game['sport_title'],
        "matchup": f"{away} @ {home}",
        "game_time": game_dt,
        "lines_summary": " | ".join(lines)
    }

# ==========================================
# 3. THE 3-AGENT PIPELINE
# ==========================================

def run_game_analysis(game_obj):
    matchup = game_obj['matchup']
    lines = game_obj['lines_summary']
    print(f"\nANALYZING: {matchup}")

    # AGENT A: Context
    prompt_a = f"""
    ROLE: Expert Sports Journalist & Insider.
    TASK: Analyze qualitative factors for: {matchup} ({game_obj['sport']}).
    
    CRITICAL: Identify "Model Breakers" - events so significant that historical stats (last 5 games) become irrelevant (e.g., Starting QB out, team played double OT last night).
    
    FACTORS:
    1. Injuries (Key starters only)
    2. Schedule/Rest (Travel fatigue, back-to-backs)
    3. Motivation (Revenge game, must-win, tanking)
    4. Public Sentiment (Is the line moving on hype?)

    OUTPUT SCHEMA (JSON):
    - impact_factors (list of strings)
    - model_breakers (boolean): True if major lineup/rest changes make historical data unreliable.
    - team_a_motivation (1-10 scale)
    - team_b_motivation (1-10 scale)
    """
    
    res_a = client.models.generate_content(
        model=RESEARCH_MODEL,
        contents=prompt_a,
        config=types.GenerateContentConfig(
            response_mime_type='application/json', 
            response_schema=QualitativeAnalysis
        )
    )
    qual_data = json.loads(res_a.text) 
    time.sleep(2)

    # AGENT B: Math
    prompt_b = f"""
    ROLE: Professional Sports Better (Quantitative).
    TASK: Create a probabilistic scoring projection for: {matchup}.
    MARKET LINES: {lines}
    
    METHODOLOGY:
    1. Base calculation on Season Averages.
    2. Apply weighted adjustment for Last 5 Games (2x weight).
    3. PENALIZE variance: If a team is inconsistent, widen the range.
    4. If a Key Player is OUT (check lines), adjust manually.
    
    OUTPUT REQUIREMENTS:
    - Provide a "Median" projection (your true predicted score).
    - Provide a "Floor" and "Ceiling" (10th/90th percentile outcomes).
    - implied_spread = (Home Median - Away Median).
    
    OUTPUT SCHEMA (JSON):
    - projected_winner (str)
    - home_score_range {{ "floor": int, "median": int, "ceiling": int }}
    - away_score_range {{ "floor": int, "median": int, "ceiling": int }}
    - projected_total_median (int)
    - implied_spread (float)
    - projected_spread (float)
    - projected_total (float)
    - confidence_score (int 1-10)
    """

    res_b = client.models.generate_content(
        model=RESEARCH_MODEL,
        contents=prompt_b,
        config=types.GenerateContentConfig(
            response_mime_type='application/json', 
            response_schema=QuantitativeAnalysis
        )
    )
    quant_data = json.loads(res_b.text) 
    time.sleep(2)

    # AGENT C: The Sharp
    final_context = f"""
    MATCHUP: {matchup}
    MARKET LINES: {lines}
    
    REPORT A (Qualitative):
    - Model Breakers Present: {qual_data.get('model_breakers')}
    - Factors: {json.dumps(qual_data.get('impact_factors'))}
    - Motivation Gap: {abs(qual_data.get('team_a_motivation', 5) - qual_data.get('team_b_motivation', 5))}
    
    REPORT B (Quantitative):
    - Projected Spread: {quant_data.get('implied_spread')}
    - Projected Total: {quant_data.get('projected_total')}
    - Home Range: {quant_data.get('home_score_range')}
    - Away Range: {quant_data.get('away_score_range')}
    """
    
    prompt_c = f"""
    ROLE: Lead Handicapper & Risk Manager.
    CONTEXT: {final_context}
    
    TASK: Identify positive expected value (+EV) bets.
    
    EVALUATION CRITERIA:
    1. MINIMUM EDGE (The "Actionable" Zone):
       - Spread: Market must differ by >= 1.5 points from Projection.
       - Total: Market must differ by >= 2.5 points from Projection.
       - If edge is smaller than this, PASS.
    
    2. CONSENSUS:
       - If Agent A (Qual) and Agent B (Quant) disagree on direction, PASS.
       - If Agent A flags "Model Breakers", Increase Minimum Edge requirements by 50%.

    3. CONFIDENCE SCORING:
       - High Confidence: Edge > 3.0 pts AND Line is outside Agent B's Floor/Ceiling.
       - Medium Confidence: Edge > 2.0 pts.
       - Low Confidence: Edge > 1.5 pts (A "Lean").
    
    4. SANITY CHECK:
       - If calculated edge > 25% (huge outlier), assume hallucination and PASS.
    
    OUTPUT:
    Return a list of 'bets'. If no bets meet criteria, return empty list.
    """
    
    res_c = client.models.generate_content(
        model=DECISION_MODEL,
        contents=prompt_c,
        config=types.GenerateContentConfig(
            response_mime_type='application/json', 
            response_schema=GameAnalysis
        )
    )
    
    return json.loads(res_c.text) #type: ignore

# ==========================================
# 4. MAIN RUNNER
# ==========================================


def run_ingest():
    print("--- Starting Analysis Pipeline ---")
    
    today_dow = datetime.today().weekday()
    day_name = datetime.today().strftime('%A')
    print(f"Today is {day_name} (Day {today_dow})")

    all_potential_bets = []
    
    # --- STEP 1: DO ALL THE HEAVY LIFTING (NO DB CONNECTION YET) ---
    # We do NOT use 'with app.app_context()' here.
    # We just run the python logic.
    
    for sport_key in ACTIVE_SPORTS:
        # Credit Saving Check
        allowed_days = SPORT_DAYS.get(sport_key)
        if allowed_days and today_dow not in allowed_days:
            print(f"[SKIP] {ACTIVE_SPORTS[sport_key]} does not play on {day_name}s.")
            continue

        raw_games = get_game_odds(sport_key)
        
        if not raw_games:
            print(f"No games found for {sport_key}.")
            continue

        print(f"Found {len(raw_games)} games for {sport_key}. Analyzing all...")

        for game in raw_games:
            formatted_game = format_game_data(game)
            if not formatted_game: continue
            
            try:
                decision = run_game_analysis(formatted_game)
                
                if decision.get('bets'):
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
                        print(f"  -> Found potential bet: {bet['selection']} (Edge: {bet['value_edge']:.2%})")
                else:
                    print(f"  -> [PASS] No value found.")
    
                print("  [Waiting 30 for Pro Model Rate Limit...]")
                time.sleep(30)
                
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(60)
            
    # --- STEP 2: FILTER RESULTS ---
    print(f"\n--- Analysis Complete. Found {len(all_potential_bets)} total opportunities. ---")
    print("--- Filtering for Top 9 Best Bets ---")
    
    high_confidence_bets = [
            bet for bet in all_potential_bets 
            if bet.get('confidence_score') in ['Medium', 'High']
    ]
    
    sorted_bets = sorted(
        high_confidence_bets, 
        key=lambda x: x.get('value_edge', 0), 
        reverse=True
    )
    top_9_bets = sorted_bets[:9]
    
    # --- STEP 3: OPEN DB CONNECTION AND SAVE QUICKLY ---
    # We only open the connection NOW, when we are ready to write.
    print("--- Saving to Database ---")
    
    with app.app_context():
        db.create_all() # Ensure tables exist
        
        for bet in top_9_bets:
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
            print(f"[SAVED TO DB] {bet['selection']} (Edge: {bet['value_edge']:.2%})")

        # This commit happens immediately after opening, so no timeout!
        db.session.commit()
        
    print("--- DONE ---\n")

if __name__ == "__main__":
    run_ingest()