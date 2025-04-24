#!/usr/bin/env python3
"""
Sync Endpoints to Servers

This script synchronizes data between the endpoints table (used by scanner) 
and the servers table (used by pruner and discord bot).
"""

import os
import logging
import sys
from datetime import datetime

# Added by migration script
from database import Database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_sync.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Log database type being used
db_type = os.environ.get('DATABASE_TYPE', 'postgres').lower()
logger.info(f"Using database type: {db_type}")

# Check if PostgreSQL is configured properly
if db_type == 'postgres':
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    pg_port = os.environ.get('POSTGRES_PORT', '5432')
    pg_db = os.environ.get('POSTGRES_DB', 'ollama_scanner')
    pg_user = os.environ.get('POSTGRES_USER', 'ollama')
    logger.info(f"PostgreSQL configuration: {pg_user}@{pg_host}:{pg_port}/{pg_db}")

def sync_endpoints_to_servers():
    """
    Synchronize data from endpoints table to servers table
    """
    conn = Database()
    
    logger.info("Starting synchronization...")
    
    try:
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        # 1. Get all endpoints that are verified (verified=1)
        query = """
            SELECT e.id, e.ip, e.port, e.scan_date
            FROM endpoints e
            WHERE e.verified = 1
        """
        verified_endpoints = Database.fetch_all(query)
        
        if not verified_endpoints:
            logger.warning("No verified endpoints found to sync")
        else:
            logger.info(f"Found {len(verified_endpoints)} verified endpoints to sync")
            
            # 2. Add each verified endpoint to the servers table if it doesn't exist
            servers_added = 0
            for endpoint_id, ip, port, scan_date in verified_endpoints:
                # Check if server already exists
                check_query = """
                    SELECT id FROM servers 
                    WHERE ip = %s AND port = %s
                """
                existing_server = Database.fetch_one(check_query, (ip, port))
                
                if existing_server:
                    # Server already exists, update scan_date
                    Database.execute("""
                        UPDATE servers 
                        SET scan_date = %s
                        WHERE ip = %s AND port = %s
                    """, (scan_date, ip, port))
                    logger.debug(f"Updated existing server: {ip}:{port}")
                else:
                    # Add new server
                    Database.execute("""
                        INSERT INTO servers (ip, port, scan_date)
                        VALUES (%s, %s, %s)
                    """, (ip, port, scan_date))
                    servers_added += 1
            
            logger.info(f"Added {servers_added} new servers")
            
        # 3. Get all endpoints that are NOT verified (verified=0)
        unverified_query = """
            SELECT e.id, e.ip, e.port, e.scan_date
            FROM endpoints e
            WHERE e.verified = 0
        """
        unverified_endpoints = Database.fetch_all(unverified_query)
        
        if unverified_endpoints:
            logger.info(f"Found {len(unverified_endpoints)} unverified endpoints")
            
            # Add unverified endpoints to servers as well for the pruner to check them
            servers_added = 0
            for endpoint_id, ip, port, scan_date in unverified_endpoints:
                # Check if server already exists
                check_query = """
                    SELECT id FROM servers 
                    WHERE ip = %s AND port = %s
                """
                existing_server = Database.fetch_one(check_query, (ip, port))
                
                if not existing_server:
                    # Add new server
                    Database.execute("""
                        INSERT INTO servers (ip, port, scan_date)
                        VALUES (%s, %s, %s)
                    """, (ip, port, scan_date))
                    servers_added += 1
            
            logger.info(f"Added {servers_added} unverified servers")
        
        # 4. Sync server data back to endpoints when pruner marks them as invalid
        # In PostgreSQL, the servers view doesn't have a status column
        # We need to look directly at the endpoints table for invalidation
        invalid_query = """
            SELECT e.id, e.ip, e.port, e.verified 
            FROM endpoints e 
            WHERE e.verified = 2
            AND EXISTS (
                SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = e.id
            )
        """
        
        invalid_servers = Database.fetch_all(invalid_query)
        if invalid_servers:
            logger.info(f"Found {len(invalid_servers)} servers marked as invalid that need endpoint sync")
            
            for server_id, ip, port, verified in invalid_servers:
                # Update the corresponding endpoint as invalid (verified=2)
                Database.execute("""
                    UPDATE endpoints
                    SET verified = 2, verification_date = NOW()
                    WHERE ip = %s AND port = %s
                """, (ip, port))
                
                # Delete from verified_endpoints if exists
                Database.execute("""
                    DELETE FROM verified_endpoints 
                    WHERE endpoint_id IN (
                        SELECT id FROM endpoints WHERE ip = %s AND port = %s
                    )
                """, (ip, port))
            
            logger.info(f"Updated {len(invalid_servers)} endpoints to invalid state")
        
        # 5. Update metadata with sync timestamp
        Database.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('last_sync', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Commit transaction
        # Commit handled by Database methods
        logger.info("Synchronization completed successfully")
        
    except Exception as e:
        # Database class handles rollback
        logger.error(f"Synchronization failed: {str(e)}")
        raise
    finally:
        conn.close()

def update_stats():
    """Update database statistics in metadata table"""
    conn = Database()
    
    try:
        # Count servers (verified endpoints)
        server_count_query = """
            SELECT COUNT(*) FROM endpoints e
            WHERE EXISTS (
                SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = e.id
            )
        """
        server_count = Database.fetch_one(server_count_query)[0]
        
        # Count models
        model_count_query = "SELECT COUNT(*) FROM models"
        model_count = Database.fetch_one(model_count_query)[0]
        
        # Count verified servers (endpoints with verified=1)
        verified_count_query = "SELECT COUNT(*) FROM endpoints WHERE verified = 1"
        verified_count = Database.fetch_one(verified_count_query)[0]
        
        # Update metadata
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        Database.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('server_count', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (str(server_count), str(server_count)))
        
        Database.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('model_count', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (str(model_count), str(model_count)))
        
        Database.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES ('verified_server_count', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (str(verified_count), str(verified_count)))
        
        # Commit handled by Database methods
        logger.info(f"Updated stats: {server_count} servers, {model_count} models, {verified_count} verified")
        
    except Exception as e:
        logger.error(f"Failed to update stats: {str(e)}")
    finally:
        conn.close()

def main():
    """Main entry point"""
    # Initialize database schema
    init_database()
    
    logger.info("Starting database sync...")
    
    # Sync endpoints to servers
    sync_endpoints_to_servers()
    
    # Update statistics
    update_stats()
    
    logger.info("Database sync completed")

if __name__ == "__main__":
    main() 