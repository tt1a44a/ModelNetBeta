#!/usr/bin/env python3
"""
Add the endpoint_verifications table to track response history for honeypot detection
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

# Import database functions
from database import Database, init_database, DATABASE_TYPE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("db_schema_update.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

def create_endpoint_verifications_table():
    """Create the endpoint_verifications table for tracking response history"""
    
    logger.info("Creating endpoint_verifications table if it doesn't exist...")
    
    try:
        if DATABASE_TYPE == "postgres":
            # PostgreSQL version
            Database.execute("""
                CREATE TABLE IF NOT EXISTS endpoint_verifications (
                    id SERIAL PRIMARY KEY,
                    endpoint_id INTEGER REFERENCES endpoints(id),
                    verification_date TIMESTAMP DEFAULT NOW(),
                    response_sample TEXT,
                    detected_models JSONB,
                    is_honeypot BOOLEAN DEFAULT FALSE,
                    response_metrics JSONB,
                    UNIQUE (endpoint_id, verification_date)
                )
            """)
            
            # Add indexes for better query performance
            Database.execute("""
                CREATE INDEX IF NOT EXISTS endpoint_verifications_endpoint_id_idx 
                ON endpoint_verifications (endpoint_id)
            """)
            
            Database.execute("""
                CREATE INDEX IF NOT EXISTS endpoint_verifications_date_idx 
                ON endpoint_verifications (verification_date)
            """)
            
            logger.info("PostgreSQL endpoint_verifications table created successfully")
            
        else:
            # SQLite version
            Database.execute("""
                CREATE TABLE IF NOT EXISTS endpoint_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint_id INTEGER REFERENCES endpoints(id),
                    verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response_sample TEXT,
                    detected_models TEXT,
                    is_honeypot INTEGER DEFAULT 0,
                    response_metrics TEXT,
                    UNIQUE (endpoint_id, verification_date)
                )
            """)
            
            # Add indexes for better query performance
            Database.execute("""
                CREATE INDEX IF NOT EXISTS endpoint_verifications_endpoint_id_idx 
                ON endpoint_verifications (endpoint_id)
            """)
            
            Database.execute("""
                CREATE INDEX IF NOT EXISTS endpoint_verifications_date_idx 
                ON endpoint_verifications (verification_date)
            """)
            
            logger.info("SQLite endpoint_verifications table created successfully")
        
        return True
    except Exception as e:
        logger.error(f"Error creating endpoint_verifications table: {e}")
        return False

def update_schema_version():
    """Update schema version in metadata"""
    
    try:
        # Get current timestamp
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if schema_version exists
        if DATABASE_TYPE == "postgres":
            version_record = Database.fetch_one("SELECT value FROM metadata WHERE key = 'schema_version'")
            
            if version_record:
                current_version = int(version_record[0])
                new_version = current_version + 1
                
                # Update schema version
                Database.execute(
                    "UPDATE metadata SET value = %s, updated_at = %s WHERE key = 'schema_version'",
                    (str(new_version), now)
                )
            else:
                # Insert new schema version
                Database.execute(
                    "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s)",
                    ('schema_version', '1', now)
                )
                new_version = 1
                
            # Add schema update record
            Database.execute(
                "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s)",
                (f'schema_update_{new_version}', 'Added endpoint_verifications table', now)
            )
            
            logger.info(f"Schema version updated to {new_version}")
            
        else:
            # SQLite doesn't have UPSERT, so we need to check if the key exists
            version_record = Database.fetch_one("SELECT value FROM metadata WHERE key = 'schema_version'")
            
            if version_record:
                current_version = int(version_record[0])
                new_version = current_version + 1
                
                # Update schema version
                Database.execute(
                    "UPDATE metadata SET value = ?, updated_at = ? WHERE key = 'schema_version'",
                    (str(new_version), now)
                )
            else:
                # Insert new schema version
                Database.execute(
                    "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                    ('schema_version', '1', now)
                )
                new_version = 1
                
            # Add schema update record
            Database.execute(
                "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                (f'schema_update_{new_version}', 'Added endpoint_verifications table', now)
            )
            
            logger.info(f"Schema version updated to {new_version}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating schema version: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Add endpoint_verifications table to the database")
    parser.add_argument('--dry-run', action='store_true', help="Show SQL commands without executing them")
    parser.add_argument('--verbose', '-v', action='store_true', help="Enable verbose logging")
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    if args.dry_run:
        logger.info("DRY RUN: Would create endpoint_verifications table and update schema version")
        return
    
    # Create the table
    if create_endpoint_verifications_table():
        # Update schema version
        update_schema_version()
        logger.info("Database schema update completed successfully")
    else:
        logger.error("Failed to update database schema")
        sys.exit(1)

if __name__ == "__main__":
    main() 