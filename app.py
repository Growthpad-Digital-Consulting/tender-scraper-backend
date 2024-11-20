# Import necessary libraries
from flask import request, jsonify
from dotenv import load_dotenv
from flask_socketio import SocketIO
from flask_jwt_extended import jwt_required, JWTManager
import logging
import atexit
import os 

# Import custom modules and services
from app import create_app
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.utils.scraping_progress import run_scraping_with_progress

# Import scraping functions
from app.scrapers.scraper import scrape_tenders
from app.scrapers.ca_tenders import scrape_ca_tenders
from app.scrapers.undp_tenders import scrape_undp_tenders
from app.scrapers.reliefweb_tenders import fetch_reliefweb_tenders
from app.scrapers.scrape_jobinrwanda_tenders import scrape_jobinrwanda_tenders
from app.scrapers.scrape_treasury_ke_tenders import scrape_treasury_ke_tenders
from app.scrapers.website_scraper import scrape_tenders_from_websites

# Import blueprints for routing
from app.routes.keywords.keyword_routes import keyword_bp
from app.routes.terms.search_terms import search_terms_bp
from app.routes.upload.upload_routes import upload_bp

# Load environment variables from .env file
load_dotenv()

# Create Flask app and SocketIO instance
app, socketio = create_app()  # This initializes the app and socketio

# Configure logging for the application
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# JWT setup: Retrieve secret key from environment variables
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY') 
jwt = JWTManager(app)

# Start background scheduler for periodic tasks and register graceful shutdown
start_scheduler()
atexit.register(shutdown_scheduler)

# Register application blueprints to handle different routes
app.register_blueprint(keyword_bp)
app.register_blueprint(search_terms_bp)
app.register_blueprint(upload_bp)

# Run the Flask application with SocketIO support
if __name__ == '__main__':
    socketio.run(app, debug=True)  # Start the server with debug enabled