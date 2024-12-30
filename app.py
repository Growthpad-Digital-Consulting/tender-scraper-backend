from flask import request, jsonify
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
import logging
import atexit
import os
from datetime import timedelta

from app import create_app, socketio
from app.services.scheduler import start_scheduler, shutdown_scheduler

load_dotenv()

# Create Flask app
app = create_app()  # This initializes the app

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# JWT setup
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=60)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=14)

# Initialize JWT with the app instance
jwt = JWTManager(app)

# Start scheduler
start_scheduler()
atexit.register(shutdown_scheduler)

# Register blueprints
from app.routes.keywords.keyword_routes import keyword_bp
from app.routes.terms.search_terms import search_terms_bp
from app.routes.upload.upload_routes import upload_bp
from app.routes.terms.directory_keywords import directory_keywords_bp
from app.routes.terms.base_keywords import base_keywords_bp
from app.routes.countries.countries import countries_bp
from app.routes.closing_keywords.closing_keywords import closing_keywords_bp
from app.routes.scraping_log.scraping_log import scraping_log_bp

app.register_blueprint(keyword_bp)
app.register_blueprint(search_terms_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(directory_keywords_bp)
app.register_blueprint(base_keywords_bp)
app.register_blueprint(countries_bp)
app.register_blueprint(closing_keywords_bp)
app.register_blueprint(scraping_log_bp)

# Only run this block if executed directly
if __name__ == '__main__':
    socketio.run(app, debug=True)