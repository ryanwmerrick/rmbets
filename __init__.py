# The "Factory" (Sets up the app)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize the database extension
db = SQLAlchemy()

def create_app():
    # Create the Flask instance
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'dev-key-123' # Security key
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sports.db' # The DB file
    
    # Link the DB to the app
    db.init_app(app)

    # Import and register the routes from Step 1
    from .routes import main
    app.register_blueprint(main)

    return app