from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Pick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.now)
    
    game_time = db.Column(db.DateTime)
    
    # Game Context
    sport = db.Column(db.String(50))
    matchup = db.Column(db.String(100))
    
    # The Bet
    market_type = db.Column(db.String(50))
    selection = db.Column(db.String(50))
    price = db.Column(db.String(20))  
    
    # Analysis
    confidence_score = db.Column(db.String(20))
    value_edge = db.Column(db.Float)
    rationale = db.Column(db.Text)
    
    model= db.Column(db.String(20))
    version= db.Column(db.String(20))
    result = db.Column(db.String(20), default="PENDING")

    def __repr__(self):
        return f'<Pick {self.matchup} -> {self.selection}>'