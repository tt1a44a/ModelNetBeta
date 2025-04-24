#!/usr/bin/env python3
"""
Database Migration Script for Scanner-Pruner-Bot Integration
Migrates data from the existing schema to the new schema defined in refactor.md
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
        logging.FileHandler("migration.log")
    ]
)
logger = logging.getLogger('migration')

# Load environment variables
load_dotenv()

def migrate_to_new_schema():
    """
    Migrates data from the existing schema to the new schema.
    Handles both SQLite to PostgreSQL and old PostgreSQL to new PostgreSQL migrations.
    """
    database_type = os.getenv("DATABASE_TYPE", "postgres").lower()
    
    # Different migration paths based on source database
    if database_type == "sqlite":
        return migrate_from_sqlite()
    elif database_type == "postgres":
        return migrate_from_old_postgres()
    else:
        logger.error(f"Unsupported database type: {database_type}")
        return False

def migrate_from_sqlite():
    """Migrate data from SQLite to the new PostgreSQL schema"""
    try:
        import sqlite3
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError as e:
        logger.error(f"Missing required package: {e}")
        logger.error("Install dependencies using: pip install psycopg2-binary")
        return False
    
    sqlite_path = os.getenv("SQLITE_DB_PATH", "ollama_instances.db")
    if not Path(sqlite_path).exists():
        logger.error(f"SQLite database not found: {sqlite_path}")
        return False
    
    # PostgreSQL connection parameters
    pg_db = os.getenv("POSTGRES_DB", "ollama_scanner")
    pg_user = os.getenv("POSTGRES_USER", "ollama")
    pg_password = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    
    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(
            dbname=pg_db,
            user=pg_user,
            password=pg_password,
            host=pg_host,
            port=pg_port
        )
        pg_cursor = pg_conn.cursor()
        
        # Begin transaction
        pg_conn.autocommit = False
        
        # 1. Migrate endpoints to servers
        logger.info("Migrating endpoints to servers table")
        sqlite_cursor.execute("""
            SELECT id, ip, port, scan_date, verified, verification_date 
            FROM endpoints
        """)
        
        endpoints = []
        id_mapping = {}  # To map old IDs to new IDs
        
        for row in sqlite_cursor.fetchall():
            # Convert verified (0/1) to status ('scanned'/'verified')
            status = 'verified' if row['verified'] == 1 else 'scanned'
            endpoints.append((
                row['ip'],
                row['port'],
                status,
                row['scan_date'],
                row['verification_date'] if row['verified'] == 1 else None
            ))
            id_mapping[row['id']] = None  # Placeholder for new ID
        
        # Insert into servers table and get new IDs
        for i, (ip, port, status, scan_date, verified_date) in enumerate(endpoints):
            pg_cursor.execute("""
                INSERT INTO servers (ip, port, status, scan_date, verified_date)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ip, port) DO UPDATE 
                SET status = EXCLUDED.status,
                    scan_date = EXCLUDED.scan_date,
                    verified_date = EXCLUDED.verified_date
                RETURNING id
            """, (ip, port, status, scan_date, verified_date))
            
            new_id = pg_cursor.fetchone()[0]
            old_id = list(id_mapping.keys())[i]
            id_mapping[old_id] = new_id
        
        # 2. Migrate models
        logger.info("Migrating models table")
        sqlite_cursor.execute("""
            SELECT id, endpoint_id, name, parameter_size, quantization_level, size_mb 
            FROM models
        """)
        
        models_data = []
        for row in sqlite_cursor.fetchall():
            if row['endpoint_id'] in id_mapping:
                models_data.append((
                    row['name'],
                    id_mapping[row['endpoint_id']],  # Use new server_id
                    row['parameter_size'],
                    row['quantization_level'],
                    int(row['size_mb'] * 1024 * 1024) if row['size_mb'] else None  # Convert MB to bytes
                ))
        
        # Use execute_values for batch insert
        execute_values(pg_cursor, """
            INSERT INTO models (name, server_id, params, quant, size)
            VALUES %s
            ON CONFLICT (name, server_id) DO UPDATE 
            SET params = EXCLUDED.params,
                quant = EXCLUDED.quant,
                size = EXCLUDED.size
        """, models_data)
        
        # 3. Commit the transaction
        pg_conn.commit()
        
        # 4. Update metadata counts
        pg_cursor.execute("SELECT COUNT(*) FROM servers WHERE status = 'scanned'")
        scanned_count = pg_cursor.fetchone()[0]
        
        pg_cursor.execute("SELECT COUNT(*) FROM servers WHERE status = 'verified'")
        verified_count = pg_cursor.fetchone()[0]
        
        pg_cursor.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES 
                ('scanned_count', %s, NOW()),
                ('verified_count', %s, NOW()),
                ('failed_count', '0', NOW()),
                ('migration_date', NOW()::text, NOW())
            ON CONFLICT (key) DO UPDATE 
            SET value = EXCLUDED.value,
                updated_at = NOW()
        """, (str(scanned_count), str(verified_count)))
        
        pg_conn.commit()
        
        logger.info(f"Migration completed: {len(endpoints)} servers and {len(models_data)} models migrated")
        return True
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        if 'pg_conn' in locals():
            pg_conn.rollback()
        return False
    finally:
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        if 'pg_conn' in locals():
            pg_conn.close()

def migrate_from_old_postgres():
    """Migrate data from old PostgreSQL schema to the new schema"""
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        logger.error("psycopg2 package is required for PostgreSQL connectivity.")
        logger.error("Install it using: pip install psycopg2-binary")
        return False
    
    # PostgreSQL connection parameters
    pg_db = os.getenv("POSTGRES_DB", "ollama_scanner")
    pg_user = os.getenv("POSTGRES_USER", "ollama")
    pg_password = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            dbname=pg_db,
            user=pg_user,
            password=pg_password,
            host=pg_host,
            port=pg_port
        )
        cursor = conn.cursor()
        
        # Begin transaction
        conn.autocommit = False
        
        # Check if old schema exists
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'endpoints'
        """)
        
        if cursor.fetchone() is None:
            logger.warning("Old schema not found. No migration needed.")
            return True
            
        # Check if new schema exists
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'servers'
        """)
        
        if cursor.fetchone() is None:
            logger.error("New schema not found. Run init_database.py first.")
            return False
        
        # 1. Migrate endpoints to servers
        logger.info("Migrating endpoints to servers table")
        cursor.execute("""
            INSERT INTO servers (ip, port, status, scan_date, verified_date)
            SELECT 
                e.ip, 
                e.port, 
                CASE WHEN e.verified = 1 THEN 'verified' ELSE 'scanned' END as status,
                e.scan_date,
                e.verification_date
            FROM endpoints e
            ON CONFLICT (ip, port) DO UPDATE 
            SET status = EXCLUDED.status,
                scan_date = EXCLUDED.scan_date,
                verified_date = EXCLUDED.verified_date
            RETURNING id, ip, port
        """)
        
        # Get the mapping of IP:port to new server IDs
        server_mapping = {}
        for row in cursor.fetchall():
            server_mapping[f"{row[1]}:{row[2]}"] = row[0]
        
        # 2. Migrate models
        logger.info("Migrating models table")
        cursor.execute("""
            INSERT INTO models (name, server_id, params, quant, size)
            SELECT 
                m.name, 
                s.id, 
                m.parameter_size, 
                m.quantization_level, 
                CASE WHEN m.size_mb IS NOT NULL THEN (m.size_mb * 1024 * 1024)::bigint ELSE NULL END
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            JOIN servers s ON s.ip = e.ip AND s.port = e.port
            ON CONFLICT (name, server_id) DO UPDATE 
            SET params = EXCLUDED.params,
                quant = EXCLUDED.quant,
                size = EXCLUDED.size
        """)
        
        # 3. Update metadata counts
        cursor.execute("SELECT COUNT(*) FROM servers WHERE status = 'scanned'")
        scanned_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM servers WHERE status = 'verified'")
        verified_count = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO metadata (key, value, updated_at)
            VALUES 
                ('scanned_count', %s, NOW()),
                ('verified_count', %s, NOW()),
                ('failed_count', '0', NOW()),
                ('migration_date', NOW()::text, NOW())
            ON CONFLICT (key) DO UPDATE 
            SET value = EXCLUDED.value,
                updated_at = NOW()
        """, (str(scanned_count), str(verified_count)))
        
        # 4. Commit the transaction
        conn.commit()
        
        logger.info(f"Migration completed: {len(server_mapping)} servers migrated")
        return True
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main entry point for database migration"""
    parser = argparse.ArgumentParser(description="Migrate database to new schema for Scanner-Pruner-Bot Integration")
    parser.add_argument('--force', action='store_true', help='Force migration even if target tables exist')
    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without making changes')
    args = parser.parse_args()
    
    # Execute migration
    logger.info("Starting database migration")
    
    if args.dry_run:
        logger.info("Dry run mode: no changes will be made")
        # TODO: Implement dry run functionality
        logger.info("Dry run completed")
        return
    
    if migrate_to_new_schema():
        logger.info("Migration completed successfully")
    else:
        logger.error("Migration failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 