#!/usr/bin/env python3
"""
Cleanup script for honeypot detection issues.
This script ensures no honeypots are marked as verified in PostgreSQL.
"""

import sys
import os
import logging
import time
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Configure paths
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # Go up one level to the project root
sys.path.insert(0, parent_dir)

# Load environment variables
load_dotenv(os.path.join(parent_dir, '.env'))

# Configure logging
log_dir = os.environ.get('LOG_DIR', os.path.join(parent_dir, 'logs'))
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

log_file = os.environ.get('HONEYPOT_LOG_FILE', os.path.join(log_dir, 'honeypot_cleanup.log'))

# Create handlers
file_handler = logging.FileHandler(log_file)
console_handler = logging.StreamHandler()

# Create formatters and add it to handlers
log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

# Get the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# PostgreSQL connection details
PG_DB_NAME = os.environ.get("POSTGRES_DB", "ollama_scanner")
PG_DB_USER = os.environ.get("POSTGRES_USER", "ollama")
PG_DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "ollama_scanner_password")
PG_DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
PG_DB_PORT = os.environ.get("POSTGRES_PORT", "5432")

def get_pg_connection():
    """Get a PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            dbname=PG_DB_NAME,
            user=PG_DB_USER,
            password=PG_DB_PASSWORD,
            host=PG_DB_HOST,
            port=PG_DB_PORT
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL: {e}")
        raise

def get_database_status():
    """Get the current state of the database regarding honeypots and verification."""
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Get counts of different endpoint types
        status = {}
        
        # Total honeypots
        cursor.execute("SELECT COUNT(*) FROM endpoints WHERE is_honeypot = TRUE")
        status['total_honeypots'] = cursor.fetchone()[0]
        
        # Verified non-honeypots
        cursor.execute("SELECT COUNT(*) FROM endpoints WHERE verified = 1 AND is_honeypot = FALSE")
        status['verified_non_honeypots'] = cursor.fetchone()[0]
        
        # Incorrectly verified honeypots (should be 0)
        cursor.execute("SELECT COUNT(*) FROM endpoints WHERE verified = 1 AND is_honeypot = TRUE")
        status['verified_honeypots'] = cursor.fetchone()[0]
        
        # Count in verified_endpoints table
        cursor.execute("SELECT COUNT(*) FROM verified_endpoints")
        status['verified_endpoints_table'] = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return status
    except Exception as e:
        logger.error(f"Error getting database status: {e}")
        return None

def cleanup_honeypots():
    """
    Ensure no honeypots are marked as verified in the PostgreSQL database.
    This function:
    1. Sets verified = 0 for all honeypots
    2. Removes honeypots from the verified_endpoints table
    
    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    start_time = time.time()
    
    try:
        # Get initial status
        before_status = get_database_status()
        if before_status is None:
            logger.error("Could not get database status")
            return False
            
        logger.info("Database status before cleanup:")
        logger.info(f"  - Total honeypots: {before_status['total_honeypots']}")
        logger.info(f"  - Verified non-honeypots: {before_status['verified_non_honeypots']}")
        logger.info(f"  - Verified honeypots (should be 0): {before_status['verified_honeypots']}")
        logger.info(f"  - Entries in verified_endpoints table: {before_status['verified_endpoints_table']}")
        
        # Check if we need to do any cleanup
        if before_status['verified_honeypots'] == 0:
            logger.info("No verified honeypots found, continuing with other checks...")
        
        # Execute the cleanup directly with PostgreSQL
        conn = get_pg_connection()
        conn.autocommit = False  # Use a transaction
        cursor = conn.cursor()
        
        try:
            # 1. Ensure no honeypots are marked as verified
            logger.info("Updating honeypot verification status")
            cursor.execute("UPDATE endpoints SET verified = 0 WHERE is_honeypot = TRUE")
            logger.info(f"Updated {cursor.rowcount} honeypot endpoints")
            
            # 2. Remove any honeypots from verified_endpoints table
            logger.info("Removing honeypots from verified_endpoints table")
            cursor.execute("""
                DELETE FROM verified_endpoints 
                WHERE endpoint_id IN (SELECT id FROM endpoints WHERE is_honeypot = TRUE)
            """)
            logger.info(f"Removed {cursor.rowcount} entries from verified_endpoints")
            
            # Commit the transaction
            conn.commit()
            logger.info("Transaction committed successfully")
            
        except Exception as e:
            # Rollback on error
            conn.rollback()
            logger.error(f"Error during cleanup: {e}")
            cursor.close()
            conn.close()
            return False
        
        # Get status after cleanup
        after_status = get_database_status()
        if after_status is None:
            logger.error("Could not get database status after cleanup")
            return False
            
        logger.info("Database status after cleanup:")
        logger.info(f"  - Total honeypots: {after_status['total_honeypots']}")
        logger.info(f"  - Verified non-honeypots: {after_status['verified_non_honeypots']}")
        logger.info(f"  - Verified honeypots (should be 0): {after_status['verified_honeypots']}")
        logger.info(f"  - Entries in verified_endpoints table: {after_status['verified_endpoints_table']}")
        
        # Check for inconsistencies
        inconsistencies = []
        if after_status['verified_honeypots'] > 0:
            inconsistencies.append(f"Found {after_status['verified_honeypots']} honeypots still marked as verified")
        
        # Find honeypots that are still in the verified_endpoints table
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ve.endpoint_id, e.ip, e.port
                FROM verified_endpoints ve
                JOIN endpoints e ON ve.endpoint_id = e.id
                WHERE e.is_honeypot = TRUE
                LIMIT 100
            """)
            
            honeypots_in_verified = cursor.fetchall()
            
            if honeypots_in_verified:
                inconsistencies.append(f"Found {len(honeypots_in_verified)} honeypots still in verified_endpoints table")
                for endpoint in honeypots_in_verified:
                    logger.error(f"Honeypot in verified_endpoints: ID {endpoint[0]} ({endpoint[1]}:{endpoint[2]})")
            else:
                logger.info("No honeypots found in verified_endpoints table")
                
            cursor.close()
            
        except Exception as e:
            logger.error(f"Error checking for honeypots in verified_endpoints: {e}")
            inconsistencies.append(f"Error during verification: {e}")
        
        # Close the connection
        conn.close()
        
        if inconsistencies:
            logger.error("Cleanup completed but inconsistencies were found:")
            for issue in inconsistencies:
                logger.error(f"  - {issue}")
            return False
        else:
            logger.info("Cleanup completed successfully, no inconsistencies found")
            return True
            
    except Exception as e:
        logger.error(f"Error during honeypot cleanup: {e}")
        return False

def main():
    """Main entry point for the cleanup script."""
    logger.info("Starting honeypot cleanup process (PostgreSQL version)")
    
    # Set start time for overall process
    start_time = time.time()
    
    # Perform cleanup
    try:
        success = cleanup_honeypots()
        
        elapsed_time = time.time() - start_time
        logger.info(f"Cleanup process took {elapsed_time:.2f} seconds")
        
        if success:
            logger.info("Honeypot cleanup completed successfully")
            return 0
        else:
            logger.error("Honeypot cleanup completed with errors")
            return 1
    except Exception as e:
        logger.error(f"Unexpected error during cleanup: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 