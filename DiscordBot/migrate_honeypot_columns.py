#!/usr/bin/env python3
"""
Add honeypot and inactive endpoint tracking columns to the Ollama Scanner database
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("database_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add project root to system path if not running from project directory
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Import database module
try:
    from database import Database, init_database, DATABASE_TYPE
except ImportError:
    logger.error("Failed to import database module. Make sure you're running this script from the project root.")
    sys.exit(1)

def migrate_database(dry_run=False):
    """Add honeypot and inactive endpoint tracking columns to endpoints table"""
    try:
        logger.info("Starting database migration for honeypot and inactive endpoint tracking")
        
        # Initialize the database connection
        init_database()
        
        # Check if honeypot column already exists
        if DATABASE_TYPE == "postgres":
            column_exists = Database.fetch_one("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'endpoints' AND column_name = 'is_honeypot'
                )
            """)[0]
        else:
            # SQLite
            pragma_result = Database.fetch_all("PRAGMA table_info(endpoints)")
            column_exists = any(row[1] == 'is_honeypot' for row in pragma_result)
        
        if column_exists:
            logger.info("Honeypot column already exists, skipping migration")
            return True
            
        # Add honeypot and inactive endpoint columns to endpoints table
        if dry_run:
            logger.info("[DRY RUN] Would add honeypot and inactive endpoint columns to endpoints table")
            return True
            
        logger.info("Adding honeypot and inactive endpoint columns to endpoints table")
        
        if DATABASE_TYPE == "postgres":
            # Add honeypot tracking
            Database.execute("ALTER TABLE endpoints ADD COLUMN is_honeypot BOOLEAN DEFAULT FALSE")
            Database.execute("ALTER TABLE endpoints ADD COLUMN honeypot_reason TEXT")
            
            # Add inactive endpoint tracking
            Database.execute("ALTER TABLE endpoints ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
            Database.execute("ALTER TABLE endpoints ADD COLUMN inactive_reason TEXT")
            Database.execute("ALTER TABLE endpoints ADD COLUMN last_check_date TIMESTAMP WITH TIME ZONE")
            
            # Add indexes for performance
            logger.info("Creating indexes for new columns")
            Database.execute("CREATE INDEX idx_endpoints_honeypot ON endpoints(is_honeypot)")
            Database.execute("CREATE INDEX idx_endpoints_active ON endpoints(is_active)")
            Database.execute("CREATE INDEX idx_endpoints_verified_honeypot ON endpoints(verified, is_honeypot)")
            Database.execute("CREATE INDEX idx_endpoints_verified_active ON endpoints(verified, is_active)")
            
        else:
            # SQLite doesn't support adding multiple columns in one statement
            Database.execute("ALTER TABLE endpoints ADD COLUMN is_honeypot INTEGER DEFAULT 0")
            Database.execute("ALTER TABLE endpoints ADD COLUMN honeypot_reason TEXT")
            Database.execute("ALTER TABLE endpoints ADD COLUMN is_active INTEGER DEFAULT 1")
            Database.execute("ALTER TABLE endpoints ADD COLUMN inactive_reason TEXT")
            Database.execute("ALTER TABLE endpoints ADD COLUMN last_check_date TEXT")
            
            # SQLite doesn't support CREATE INDEX IF NOT EXISTS
            try:
                Database.execute("CREATE INDEX idx_endpoints_honeypot ON endpoints(is_honeypot)")
            except Exception:
                logger.info("Index idx_endpoints_honeypot already exists")
                
            try:
                Database.execute("CREATE INDEX idx_endpoints_active ON endpoints(is_active)")
            except Exception:
                logger.info("Index idx_endpoints_active already exists")
                
            try:
                Database.execute("CREATE INDEX idx_endpoints_verified_honeypot ON endpoints(verified, is_honeypot)")
            except Exception:
                logger.info("Index idx_endpoints_verified_honeypot already exists")
                
            try:
                Database.execute("CREATE INDEX idx_endpoints_verified_active ON endpoints(verified, is_active)")
            except Exception:
                logger.info("Index idx_endpoints_verified_active already exists")
        
        # Update metadata to track migration
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if DATABASE_TYPE == "postgres":
            Database.execute(
                "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s",
                ('honeypot_columns_added', 'true', now, 'true', now)
            )
        else:
            # SQLite doesn't have ON CONFLICT UPDATE
            existing = Database.fetch_one("SELECT value FROM metadata WHERE key = ?", ('honeypot_columns_added',))
            if existing:
                Database.execute(
                    "UPDATE metadata SET value = ?, updated_at = ? WHERE key = ?",
                    ('true', now, 'honeypot_columns_added')
                )
            else:
                Database.execute(
                    "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                    ('honeypot_columns_added', 'true', now)
                )
        
        # Update schema version
        if DATABASE_TYPE == "postgres":
            Database.execute(
                "INSERT INTO schema_version (version) VALUES ('1.1.0-honeypot')"
            )
        else:
            Database.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                ('1.1.0-honeypot',)
            )
            
        logger.info("Database migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during database migration: {e}")
        return False

def main():
    """Main entry point for the migration script"""
    
    parser = argparse.ArgumentParser(description="Migrate database to add honeypot and inactive endpoint tracking")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be executed without making changes")
    parser.add_argument("--verbose", action="store_true", help="Show additional debug information")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")
    
    if args.dry_run:
        logger.info("Running in dry-run mode (no changes will be made)")
    
    success = migrate_database(dry_run=args.dry_run)
    
    if success:
        print("\n✅ Migration completed successfully!")
        if args.dry_run:
            print("  (No changes were made due to --dry-run flag)")
        sys.exit(0)
    else:
        print("\n❌ Migration failed! Check the logs for details.")
        print("   Log file: database_migration.log")
        sys.exit(1)

if __name__ == "__main__":
    main() 