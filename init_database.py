#!/usr/bin/env python3
"""
Database Initialization Script for Scanner-Pruner-Bot Integration
Initializes the PostgreSQL database schema based on the refactor.md requirements
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("database_init.log")
    ]
)
logger = logging.getLogger('database_init')

# Load environment variables
load_dotenv()

def init_postgres_db():
    """Initialize the PostgreSQL database using psycopg2"""
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 package is required for PostgreSQL connectivity.")
        logger.error("Install it using: pip install psycopg2-binary")
        sys.exit(1)
    
    # Get connection parameters from environment variables
    db_name = os.getenv("POSTGRES_DB", "ollama_scanner")
    db_user = os.getenv("POSTGRES_USER", "ollama")
    db_password = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    
    # Load SQL schema from file
    schema_path = Path('schema/postgres_schema.sql')
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        sys.exit(1)
    
    schema_sql = schema_path.read_text()
    
    # Connect to database and execute schema
    try:
        # First connect to PostgreSQL to create the database if it doesn't exist
        conn = psycopg2.connect(
            dbname='postgres',
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Create database if it doesn't exist
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_name}'")
        if cursor.fetchone() is None:
            logger.info(f"Creating database {db_name}")
            cursor.execute(f"CREATE DATABASE {db_name}")
        
        conn.close()
        
        # Now connect to the target database and execute schema
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        logger.info(f"Executing schema for database {db_name}")
        cursor.execute(schema_sql)
        
        logger.info("Schema execution completed successfully")
        
        # Verify tables were created
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Tables in database: {', '.join(tables)}")
        
        conn.close()
        
        return True
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False

def main():
    """Main entry point for database initialization"""
    parser = argparse.ArgumentParser(description="Initialize database for Scanner-Pruner-Bot Integration")
    parser.add_argument('--force', action='store_true', help='Force reinitialization even if tables exist')
    args = parser.parse_args()
    
    # Ensure schema directory exists
    schema_dir = Path('schema')
    if not schema_dir.exists():
        logger.info(f"Creating schema directory: {schema_dir}")
        schema_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize database
    database_type = os.getenv("DATABASE_TYPE", "postgres").lower()
    
    if database_type == "postgres":
        logger.info("Initializing PostgreSQL database")
        if init_postgres_db():
            logger.info("PostgreSQL database initialization completed successfully")
        else:
            logger.error("PostgreSQL database initialization failed")
            sys.exit(1)
    else:
        logger.error(f"Unsupported database type: {database_type}")
        logger.error("Only PostgreSQL is supported for this implementation")
        sys.exit(1)

if __name__ == "__main__":
    main() 