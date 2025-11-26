import os
import requests
import re
from dotenv import load_dotenv
from app import app
from models import db, Pick
from constants import ACTIVE_SPORTS 

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
DAYS_LOOKBACK = 3

# We create the reverse mapping locally for efficiency: {'NBA': 'basketball_nba', ...}
DB_TO_API_KEY = {v: k for k, v in ACTIVE_SPORTS.items()}

def get_scores(sport_key):
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
    # Get the two team names from your matchup string
    teams = [team.strip() for team in pick.matchup.replace(' @ ', ' vs ').split(' vs ')]
    
    for game in scores_data:
        if not game.get('completed'):
            continue
            
        home_team = game['home_team']
        away_team = game['away_team']
        
        # Check if BOTH teams in our pick are present in the API game object
        if all(team in home_team or team in away_team for team in teams):
            
            home_score, away_score = None, None
            
            # Find scores
            if game.get('scores'):
                for s in game['scores']:
                    if s['name'] == home_team: home_score = int(s['score'])
                    if s['name'] == away_team: away_score = int(s['score'])
            
            if home_score is not None and away_score is not None:
                return {
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score
                }
            
    return None

def grade_pick(pick, result_data):
    if result_data['home_score'] is None: return 
    
    selection = pick.selection
    h_score = result_data['home_score']
    a_score = result_data['away_score']
    
    # LOGIC 1: TOTALS
    if "Over" in selection or "Under" in selection:
        match = re.search(r"(\d+\.?\d*)", selection)
        if not match: return
        
        line = float(match.group(1))
        total_score = h_score + a_score
        
        if total_score == line: return "PUSH"
        if "Over" in selection: return "WIN" if total_score > line else "LOSS"
        if "Under" in selection: return "WIN" if total_score < line else "LOSS"

    # LOGIC 2: SPREADS
    # Matches strings like "Lakers -3.5" or "NY Giants +7"
    spread_match = re.search(r"([+-]?\d+\.?\d*)$", selection.strip())
    
    if spread_match:
        line = float(spread_match.group(1))
        
        # FIX: Remove the number to get the Team Name safely
        team_name = selection.replace(spread_match.group(1), "").strip()
        
        # Normalize for comparison
        team_name_norm = team_name.lower()
        home_team_norm = result_data['home_team'].lower()
        
        # Determine the scores
        if team_name_norm in home_team_norm:
            my_score = h_score
            opp_score = a_score
        else:
            my_score = a_score
            opp_score = h_score
            
        # The Math
        if (my_score + line) > opp_score: return "WIN"
        if (my_score + line) < opp_score: return "LOSS"
        return "PUSH"

    # LOGIC 3: MONEYLINE
    else:
        # Check for the third outcome: DRAW
        is_draw = h_score == a_score
        
        # 1. Check if the selection was explicitly for a DRAW
        if "draw" in pick.selection.lower():
            return "WIN" if is_draw else "LOSS"
        
        # 2. Check for a Team Win (Standard Logic)
        # This will ONLY run if the game was NOT a draw (or if the bet was explicitly NOT a draw)
        
        # The game must be resolved (not a draw) for a team bet to WIN/LOSS.
        if not is_draw:
            # We use string matching to be robust against "LA Lakers" vs "Lakers"
            picked_team = pick.selection.lower()
            home_team_name = result_data['home_team'].lower()
            away_team_name = result_data['away_team'].lower()
            
            home_won= h_score>a_score

            # Determine the outcome of the bet
            if picked_team in home_team_name:
                return "WIN" if home_won else "LOSS"
            elif picked_team in away_team_name:
                return "WIN" if not home_won else "LOSS"
            else:
                # If we couldn't match the team name to the score result data, skip the grade
                return None 
        
        # 3. If the pick was a TEAM but the game was a DRAW, the bet is a LOSS.
        else:
            return "LOSS"

    return None # Could not grade
        

def run_grader():
    print("--- STARTING GRADER ---")
    
    with app.app_context():
        pending_picks = Pick.query.filter_by(result='PENDING').all()
        
        if not pending_picks:
            print("No pending picks to grade.")
            return

        # 1. IDENTIFY NEEDED API KEYS based on current PENDING bets
        needed_api_keys = set()
        for pick in pending_picks:
            # Look up the API key using the friendly name from the DB (e.g., 'UCL')
            api_key = DB_TO_API_KEY.get(pick.sport) 
            if api_key:
                needed_api_keys.add(api_key)
            else:
                print(f"  [WARNING] Unknown sport in DB: '{pick.sport}'.")

        print(f"Fetching data for: {needed_api_keys}")
        
        # 2. FETCH SCORES
        scores_cache = {}
        for sport_key in needed_api_keys:
            scores_cache[sport_key] = get_scores(sport_key)

        print(f"Grading {len(pending_picks)} picks...")

        # 3. GRADE EACH PICK
        for pick in pending_picks:
            # Convert the friendly name back to the API key for the cache lookup
            api_sport_key = DB_TO_API_KEY.get(pick.sport)
            if not api_sport_key or api_sport_key not in scores_cache: 
                 # This happens if API returned no data for that sport key
                 continue
            
            scores = scores_cache.get(api_sport_key)
            
            game_result = find_game_result(pick, scores)
            
            if game_result:
                outcome = grade_pick(pick, game_result)
                
                if outcome and outcome != 'PUSH':
                    pick.result = outcome
                    db.session.add(pick) 
                    print(f"  [GRADED] {pick.selection}: {outcome} (Score: {game_result['away_score']}-{game_result['home_score']})")
                else:
                    print(f"  [SKIP/PUSH] {pick.selection}: {outcome or 'Game not complete'}")
            else:
                # This FAIL means the game result wasn't found in the API's completed list (still pending)
                print(f"  [FAIL] Could not match: '{pick.matchup}' in API data.")
            
        # 4. Save all changes to DB
        db.session.commit()
    
    print("--- DONE ---")

if __name__ == "__main__":
    run_grader()