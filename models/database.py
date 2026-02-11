"""
Database initialization and connection
"""
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy instance
db = SQLAlchemy()

def init_db(app):
    """
    Initialize database with Flask app

    Args:
        app: Flask application instance
    """
    db.init_app(app)

    with app.app_context():
        # Import models to register them
        from models import models

        # Create tables if they don't exist
        db.create_all()

        print("Database initialized successfully")

def get_db():
    """Get database instance"""
    return db
