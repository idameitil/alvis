#!/usr/bin/env python3
"""
Database setup script for Alvis

Usage:
    python setup_db.py
"""
import sys
import pymysql
from config import Config

def create_database():
    """Create the database if it doesn't exist"""
    print("Creating database...")

    try:
        print(Config.MYSQL_USER)
        print(Config.MYSQL_PASSWORD)
        # Connect to MySQL server (without specifying database)
        connection = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD
        )

        with connection.cursor() as cursor:
            # Create database
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {Config.MYSQL_DATABASE} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            print(f"✓ Database '{Config.MYSQL_DATABASE}' created/verified")

        connection.close()

    except pymysql.Error as e:
        print(f"✗ Error creating database: {e}")
        sys.exit(1)

def create_tables():
    """Create tables using SQLAlchemy"""
    print("\nCreating tables...")

    from flask import Flask
    from models.database import db

    # Create Flask app instance for setup
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize SQLAlchemy with app
    db.init_app(app)

    with app.app_context():
        # Import models to register them
        from models.models import Project, Alignment, ConservedPosition, Visualization

        # Create all tables
        db.create_all()
        print("✓ All tables created successfully")

def main():
    """Main setup function"""
    print("=" * 50)
    print("Alvis Database Setup")
    print("=" * 50)
    print()
    print("Database Configuration:")
    print(f"  Host: {Config.MYSQL_HOST}:{Config.MYSQL_PORT}")
    print(f"  User: {Config.MYSQL_USER}")
    print(f"  Database: {Config.MYSQL_DATABASE}")
    print()

    # Step 1: Create database
    create_database()

    # Step 2: Create tables
    create_tables()

    print()
    print("=" * 50)
    print("✓ Database setup completed successfully!")
    print("=" * 50)
    print()
    print("You can now run the application with:")
    print("  python app.py")
    print()

if __name__ == '__main__':
    main()
