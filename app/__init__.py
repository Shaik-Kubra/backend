from flask import Flask
from flask_cors import CORS
from .config import Config

def create_app():
    app = Flask(__name__)
    
    # Load Config
    app.config.from_object(Config)
    
    # Enable CORS (Crucial for React connection)
    CORS(app)
    
    # Register the routes blueprint
    from .routes import main
    app.register_blueprint(main)
    
    return app