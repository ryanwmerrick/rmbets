import os
from flask import Flask, render_template
from models import db, Pick
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo # Built-in Python library (No install needed)

from constants import CURRENT_MODEL, ACTIVE_SPORTS_NAMES, MARKET_NAMES
# Load the secrets BEFORE creating the app
load_dotenv()

app = Flask(__name__)

# LOGIC: Use the Cloud DB if available, otherwise local file
uri = os.getenv("DATABASE_URL")
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
    
app.config['SECRET_KEY'] = 'dev-key-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = uri or 'sqlite:///sports.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- CUSTOM FILTER: UTC to EST (Using ZoneInfo) ---
def format_est(value, format="%b %d @ %I:%M %p"):
    if value is None:
        return ""
    
    # Define timezones using the built-in library
    utc = ZoneInfo("UTC")
    est = ZoneInfo("America/New_York")
    
    # Check if the datetime is naive (has no timezone info)
    if value.tzinfo is None:
        # Assume it's UTC (because that's what datetime.utcnow() gives us)
        value = value.replace(tzinfo=utc)
    
    # Convert to EST
    local_dt = value.astimezone(est)
    local_dt = local_dt - timedelta(minutes=10) #adjusts back 10 min for national anthem
    return local_dt.strftime(format)

# Register the filter so Jinja can use it
app.jinja_env.filters['est_time'] = format_est

# Calculates total profit
def calculate_profit(picks):
    balance = 0
    bet_amount = 10 

    for p in picks:
        if p.result == 'LOSS':
            balance -= bet_amount
        elif p.result == 'WIN':
            try:
                odds = float(p.price)
                if odds > 0:
                    profit = bet_amount * (odds / 100)
                else:
                    profit = bet_amount * (100 / abs(odds))
                balance += profit
            except:
                pass
    return round(balance, 2)

@app.route('/')
def index():
    # Fetch all PENDING picks for the homepage
    picks = Pick.query.filter_by(result="PENDING").order_by(Pick.date.asc()).all()
    # Get today's date for display
    today_str = date.today().strftime("%m/%d/%y")
    return render_template('index.html', picks=picks, curr_Date=today_str)

@app.route('/stats')
def stats():
    # 1. Fetch all COMPLETED picks (Win or Loss)
    completed_picks = Pick.query.filter(Pick.result!="PENDING").order_by(Pick.date.desc()).all()
    
    # 2. Calculate Stats
    total_bets = len(completed_picks)
    wins = len([p for p in completed_picks if p.result == 'WIN'])
    losses = len([p for p in completed_picks if p.result == 'LOSS'])
    
    if total_bets > 0:
        win_rate = round((wins / total_bets) * 100, 1)
        loss_rate = round((losses / total_bets) * 100, 1)
    else:
        win_rate = 0
        loss_rate = 0
        
    # 3. Calculate Money
    total_profit = calculate_profit(completed_picks)

    return render_template("stats.html", 
                         picks=completed_picks, 
                         win_rate=win_rate, 
                         loss_rate=loss_rate, 
                         profit=total_profit)

@app.route('/about')
def about():
    # Pulling constants from ingest.py
    return render_template("about.html", 
                         curr_model=CURRENT_MODEL, 
                         curr_sports=ACTIVE_SPORTS_NAMES, 
                         curr_markets=MARKET_NAMES)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)