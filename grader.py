import os
import requests
import re
from dotenv import load_dotenv
from app import app
from models import db, Pick
import ingest

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

# We look back 3 days just in case we missed a game yesterday
DAYS_LOOKBACK = 3

def get_scores(sport_key):
    """Fetch scores for completed games"""
    print(f"  Fetching scores for {sport_key}...")
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
    params = {
        "apiKey": ODDS_API_KEY,
        "daysFrom": DAYS_LOOKBACK,
        "dateFormat": "iso"
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"    [API ERROR] {response.text}")
            return []
        return response.json()
    except Exception as e:
        print(f"    [SYSTEM ERROR] {e}")
        return []

def find_game_result(pick, scores_data):
    """
    Finds the specific game in the API data that matches our Pick.
    Returns a dictionary with the final scores.
    """
    # Our DB stores matchup like: "Magic @ Celtics"
    # We need to match this to the API data
    
    for game in scores_data:
        if not game['completed']:
            continue
            
        home_team = game['home_team']
        away_team = game['away_team']
        
        # Check if this game object matches the teams in our pick
        # We check simply if the team name exists in the pick string
        if home_team in pick.matchup and away_team in pick.matchup:
            
            # Find the scores
            home_score = None
            away_score = None
            
            if game['scores']:
                for s in game['scores']:
                    if s['name'] == home_team: home_score = int(s['score'])
                    if s['name'] == away_team: away_score = int(s['score'])
            
            return {
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score
            }
    return None

def grade_pick(pick, result_data):
    """
    The Math Logic: Compares the Pick Selection vs Final Score
    """
    if result_data['home_score'] is None: return # Game might be cancelled

    selection = pick.selection # e.g., "Lakers -3.5" or "Over 220.5"
    h_score = result_data['home_score']
    a_score = result_data['away_score']
    
    home_won = h_score > a_score
    
    # -----------------------------
    # LOGIC 1: TOTALS (Over/Under)
    # -----------------------------
    if "Over" in selection or "Under" in selection:
        # Regex to find the number (e.g., 220.5)
        # Looks for digits, maybe a decimal, maybe digits after
        match = re.search(r"(\d+\.?\d*)", selection)
        if not match: return
        
        line = float(match.group(1))
        total_score = h_score + a_score
        
        if "Over" in selection:
            if total_score > line: return "WIN"
            elif total_score < line: return "LOSS"
            else: return "PUSH"
            
        elif "Under" in selection:
            if total_score < line: return "WIN"
            elif total_score > line: return "LOSS"
            else: return "PUSH"

    # -----------------------------
    # LOGIC 2: SPREADS (e.g. "Lakers -3.5")
    # -----------------------------
    # Check if there is a number in the string (positive or negative)
    match = re.search(r"([+-]?\d+\.?\d*)", selection)
    
    if match and ("+" in selection or "-" in selection):
        line = float(match.group(1))
        
        # Identify which team the bet is on
        # We assume the team name is the part of the string BEFORE the number
        team_name = selection.replace(str(line), "").strip()
        
        # Get that team's actual score
        if team_name in result_data['home_team']:
            my_score = h_score
            opp_score = a_score
        else:
            my_score = a_score
            opp_score = h_score
            
        # The Math: Add the spread to my score. If > opponent, I win.
        # Example: Bet "Lakers -5". Lakers score 100, Opp 90.
        # 100 + (-5) = 95. 95 > 90. Win.
        if (my_score + line) > opp_score: return "WIN"
        elif (my_score + line) < opp_score: return "LOSS"
        else: return "PUSH"

    # -----------------------------
    # LOGIC 3: MONEYLINE (e.g. "Lakers")
    # -----------------------------
    # If no numbers found, it's a Moneyline bet
    else:
        # If I bet Home and Home won
        if pick.selection in result_data['home_team'] and home_won:
            return "WIN"
        # If I bet Away and Away won (Home lost)
        elif pick.selection in result_data['away_team'] and not home_won:
            return "WIN"
        else:
            return "LOSS"
            
    return None # Could not grade

def run_grader():
    print("--- STARTING GRADER ---")
    
    with app.app_context():
        # Get all PENDING picks
        pending_picks = Pick.query.filter_by(result='PENDING').all()
        
        if not pending_picks:
            print("No pending picks to grade.")
            return

        # Optimization: Fetch scores once per sport
        # We use a set to know which sports we need
        active_sports= ingest.ACTIVE_SPORTS
        scores_cache = {}
        
        for sport in active_sports:
            scores_cache[sport] = get_scores(sport)

        print(f"Grading {len(pending_picks)} picks...")

        for pick in pending_picks:
            scores = scores_cache.get(pick.sport)
            if not scores: continue
            
            # Find the specific game result
            game_result = find_game_result(pick, scores)
            
            if game_result:
                # Determine Win/Loss
                outcome = grade_pick(pick, game_result)
                
                if outcome:
                    pick.result = outcome
                    db.session.add(pick) # Stage the update
                    print(f"  [GRADED] {pick.selection}: {outcome} (Score: {game_result['away_score']}-{game_result['home_score']})")
                else:
                    print(f"  [SKIP] Could not grade: {pick.selection}")
            else:
                # Game hasn't finished (or started) yet
                pass
        
        # Save all changes to DB
        db.session.commit()
    
    print("--- DONE ---")

if __name__ == "__main__":
    run_grader()