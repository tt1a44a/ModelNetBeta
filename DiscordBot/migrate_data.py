#!/usr/bin/env python3
"""
Data Migration Script: SQLite to PostgreSQL
This script migrates data from the SQLite database to PostgreSQL.
"""

import os
import sys
import time
import json
import sqlite3
import logging
import argparse
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Added by migration script
from database import Database, init_database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migrate_data.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("data_migration")

# Load environment variables
load_dotenv()

# SQLite database paths
# TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "ollama_instances.db")

# PostgreSQL connection parameters
DB_NAME = os.getenv("POSTGRES_DB", "ollama_scanner")
DB_USER = os.getenv("POSTGRES_USER", "ollama")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# Migration statistics
stats = {
    "endpoints": {
        "total": 0,
        "migrated": 0,
        "errors": 0
    },
    "verified_endpoints": {
        "total": 0,
        "migrated": 0,
        "errors": 0
    },
    "models": {
        "total": 0,
        "migrated": 0,
        "errors": 0
    },
    "benchmark_results": {
        "total": 0,
        "migrated": 0,
        "errors": 0
    },
    "start_time": None,
    "end_time": None
}

def connect_sqlite():
    """Connect to the SQLite database"""
    try:
        sqlite_conn = Database()
        sqlite_conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        logger.info(f"Connected to SQLite database: {SQLITE_DB_PATH}")
        return sqlite_conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to SQLite database: {e}")
        sys.exit(1)

def connect_postgres():
    """Connect to the PostgreSQL database"""
    try:
        pg_conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        logger.info(f"Connected to PostgreSQL database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
        return pg_conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        sys.exit(1)

def get_sqlite_tables(sqlite_conn):
    """Get a list of tables from the SQLite database"""
    cursor = sqlite_# Using Database methods instead of cursor
    Database.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in Database.fetch_all(query, params)]
    return tables

def check_sqlite_schema(sqlite_conn):
    """Check the SQLite schema to determine migration strategy"""
    tables = get_sqlite_tables(sqlite_conn)
    logger.info(f"Found tables in SQLite: {', '.join(tables)}")
    
    # Check for specific tables
    required_tables = ['servers', 'models']
    for table in required_tables:
        if table not in tables:
            logger.error(f"Required table '{table}' not found in SQLite database")
            sys.exit(1)
    
    # Check table structure for servers (endpoints)
    cursor = sqlite_# Using Database methods instead of cursor
    # TODO: Replace SQLite-specific code: Database.execute("PRAGMA table_info(servers)")
    columns = [row['name'] for row in Database.fetch_all(query, params)]
    logger.info(f"Columns in servers table: {', '.join(columns)}")
    
    # Check if using old schema (pre-migration to endpoints)
    if 'endpoints' not in tables:
        logger.info("Using older schema (servers only, no endpoints table)")
        return "old_schema"
    else:
        logger.info("Using newer schema with endpoints table")
        return "new_schema"

def migrate_endpoints(sqlite_conn, pg_conn, schema_type="new_schema"):
    """Migrate endpoints from SQLite to PostgreSQL"""
    logger.info("Starting migration of endpoints...")
    
    # Get total count for statistics
    sqlite_cursor = sqlite_# Using Database methods instead of cursor
    pg_cursor = pg_# Using Database methods instead of cursor
    
    try:
        # Different approach based on schema type
        if schema_type == "old_schema":
            sqlite_Database.execute("SELECT COUNT(*) FROM servers")
            stats["endpoints"]["total"] = sqlite_Database.fetch_one(query, params)[0]
            
            # Fetch servers from SQLite
            sqlite_cursor.execute("""
                SELECT id, ip, port, scan_date
                FROM servers
            """)
        else:
            sqlite_Database.execute("SELECT COUNT(*) FROM endpoints")
            stats["endpoints"]["total"] = sqlite_Database.fetch_one(query, params)[0]
            
            # Fetch endpoints from SQLite
            sqlite_cursor.execute("""
                SELECT id, ip, port, scan_date, verified, verification_date
                FROM endpoints
            """)
            
        rows = sqlite_Database.fetch_all(query, params)
        
        # Create a mapping of old IDs to new IDs
        id_mapping = {}
        
        # Prepare data for PostgreSQL - handle both schema types
        for row in rows:
            try:
                if schema_type == "old_schema":
                    old_id, ip, port, scan_date = row['id'], row['ip'], row['port'], row['scan_date']
                    # All servers are verified in old schema
                    verified = 1
                    verification_date = scan_date
                else:
                    old_id = row['id']
                    ip = row['ip']
                    port = row['port']
                    scan_date = row['scan_date']
                    verified = row['verified']
                    verification_date = row['verification_date']
                
                # Insert into PostgreSQL
                pg_cursor.execute("""
                    INSERT INTO endpoints (ip, port, scan_date, verified, verification_date)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (ip, port, scan_date, verified, verification_date))
                
                new_id = pg_Database.fetch_one(query, params)[0]
                id_mapping[old_id] = new_id
                stats["endpoints"]["migrated"] += 1
                
                # For servers in old schema or verified endpoints in new schema,
                # add to verified_endpoints table
                if schema_type == "old_schema" or verified == 1:
                    pg_cursor.execute("""
                        INSERT INTO verified_endpoints (endpoint_id, verification_date)
                        VALUES (%s, %s)
                        ON CONFLICT (endpoint_id) DO NOTHING
                    """, (new_id, verification_date))
                    stats["verified_endpoints"]["migrated"] += 1
                
            except Exception as e:
                stats["endpoints"]["errors"] += 1
                logger.error(f"Error migrating endpoint {row['id']}: {str(e)}")
        
        pg_# Commit handled by Database methods
        logger.info(f"Successfully migrated {stats['endpoints']['migrated']} endpoints")
        return id_mapping
        
    except Exception as e:
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pg_conn.rollback()
        logger.error(f"Error during endpoint migration: {str(e)}")
        return {}

def migrate_models(sqlite_conn, pg_conn, id_mapping, schema_type="new_schema"):
    """Migrate models from SQLite to PostgreSQL"""
    logger.info("Starting migration of models...")
    
    # Get total count for statistics
    sqlite_cursor = sqlite_# Using Database methods instead of cursor
    pg_cursor = pg_# Using Database methods instead of cursor
    
    try:
        sqlite_Database.execute("SELECT COUNT(*) FROM models")
        stats["models"]["total"] = sqlite_Database.fetch_one(query, params)[0]
        
        # Different query based on schema
        if schema_type == "old_schema":
            sqlite_cursor.execute("""
                SELECT id, server_id as endpoint_id, name, parameter_size, quantization_level, size_mb
                FROM models
            """)
        else:
            sqlite_cursor.execute("""
                SELECT id, endpoint_id, name, parameter_size, quantization_level, size_mb
                FROM models
            """)
            
        rows = sqlite_Database.fetch_all(query, params)
        
        # Prepare batch insert
        models_data = []
        model_id_mapping = {}
        
        for row in rows:
            try:
                old_id = row['id']
                old_endpoint_id = row['endpoint_id']
                
                # Skip if the endpoint doesn't exist in the mapping
                if old_endpoint_id not in id_mapping:
                    logger.warning(f"Skipping model {old_id}: endpoint {old_endpoint_id} not found in mapping")
                    continue
                
                new_endpoint_id = id_mapping[old_endpoint_id]
                
                # Insert into PostgreSQL
                pg_cursor.execute("""
                    INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    new_endpoint_id,
                    row['name'],
                    row['parameter_size'],
                    row['quantization_level'],
                    row['size_mb']
                ))
                
                new_id = pg_Database.fetch_one(query, params)[0]
                model_id_mapping[old_id] = new_id
                stats["models"]["migrated"] += 1
                
            except Exception as e:
                stats["models"]["errors"] += 1
                logger.error(f"Error migrating model {row['id']}: {str(e)}")
        
        pg_# Commit handled by Database methods
        logger.info(f"Successfully migrated {stats['models']['migrated']} models")
        return model_id_mapping
        
    except Exception as e:
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pg_conn.rollback()
        logger.error(f"Error during model migration: {str(e)}")
        return {}

def migrate_benchmark_results(sqlite_conn, pg_conn, endpoint_mapping, model_mapping):
    """Migrate benchmark_results from SQLite to PostgreSQL"""
    logger.info("Starting migration of benchmark results...")
    
    # Get total count for statistics
    sqlite_cursor = sqlite_# Using Database methods instead of cursor
    pg_cursor = pg_# Using Database methods instead of cursor
    
    # Check if benchmark_results table exists
    sqlite_Database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='benchmark_results'")
    if not sqlite_Database.fetch_one(query, params):
        logger.info("benchmark_results table does not exist in SQLite database. Skipping.")
        return
    
    try:
        sqlite_Database.execute("SELECT COUNT(*) FROM benchmark_results")
        stats["benchmark_results"]["total"] = sqlite_Database.fetch_one(query, params)[0]
        
        # Fetch benchmark results
        sqlite_cursor.execute("""
            SELECT id, server_id, model_id, test_date, avg_response_time, tokens_per_second,
                   first_token_latency, throughput_tokens, throughput_time,
                   context_500_tps, context_1000_tps, context_2000_tps,
                   max_concurrent_requests, concurrency_success_rate, concurrency_avg_time, success_rate
            FROM benchmark_results
        """)
        
        rows = sqlite_Database.fetch_all(query, params)
        for row in rows:
            try:
                old_server_id = row['server_id']
                old_model_id = row['model_id']
                
                # Skip if server not in mapping
                if old_server_id not in endpoint_mapping:
                    logger.warning(f"Skipping benchmark result: server {old_server_id} not found in mapping")
                    continue
                
                new_endpoint_id = endpoint_mapping[old_server_id]
                
                # Model ID can be NULL
                new_model_id = None
                if old_model_id is not None and old_model_id in model_mapping:
                    new_model_id = model_mapping[old_model_id]
                
                # Insert into PostgreSQL
                pg_cursor.execute("""
                    INSERT INTO benchmark_results (
                        endpoint_id, model_id, test_date, avg_response_time, tokens_per_second,
                        first_token_latency, throughput_tokens, throughput_time,
                        context_500_tps, context_1000_tps, context_2000_tps,
                        max_concurrent_requests, concurrency_success_rate, concurrency_avg_time, success_rate
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    new_endpoint_id, new_model_id, row['test_date'], row['avg_response_time'], row['tokens_per_second'],
                    row['first_token_latency'], row['throughput_tokens'], row['throughput_time'],
                    row['context_500_tps'], row['context_1000_tps'], row['context_2000_tps'],
                    row['max_concurrent_requests'], row['concurrency_success_rate'], 
                    row['concurrency_avg_time'], row['success_rate']
                ))
                
                stats["benchmark_results"]["migrated"] += 1
                
            except Exception as e:
                stats["benchmark_results"]["errors"] += 1
                logger.error(f"Error migrating benchmark result {row['id']}: {str(e)}")
        
        pg_# Commit handled by Database methods
        logger.info(f"Successfully migrated {stats['benchmark_results']['migrated']} benchmark results")
        
    except Exception as e:
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pg_conn.rollback()
        logger.error(f"Error during benchmark result migration: {str(e)}")

def save_migration_stats():
    """Save migration statistics to a JSON file"""
    stats["end_time"] = datetime.now().isoformat()
    
    # Calculate elapsed time
    if stats["start_time"]:
        start = datetime.fromisoformat(stats["start_time"])
        end = datetime.fromisoformat(stats["end_time"])
        elapsed = end - start
        stats["elapsed_seconds"] = elapsed.total_seconds()
        stats["elapsed_formatted"] = str(elapsed)
    
    # Calculate success rates
    for table in ["endpoints", "verified_endpoints", "models", "benchmark_results"]:
        if stats[table]["total"] > 0:
            stats[table]["success_rate"] = stats[table]["migrated"] / stats[table]["total"] * 100
    
    # Save to file
    with open("migration_results.json", "w") as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Migration statistics saved to migration_results.json")

def verify_migration(sqlite_conn, pg_conn):
    """Verify the migration by comparing counts"""
    logger.info("Verifying migration...")
    
    sqlite_cursor = sqlite_# Using Database methods instead of cursor
    pg_cursor = pg_# Using Database methods instead of cursor
    
    verification = {}
    
    # Check endpoints count
    sqlite_Database.execute("SELECT COUNT(*) FROM endpoints")
    sqlite_count = sqlite_Database.fetch_one(query, params)[0]
    pg_Database.execute("SELECT COUNT(*) FROM endpoints")
    pg_count = pg_Database.fetch_one(query, params)[0]
    verification["endpoints"] = {
        "sqlite_count": sqlite_count,
        "postgres_count": pg_count,
        "match": sqlite_count == pg_count
    }
    
    # Check models count
    sqlite_Database.execute("SELECT COUNT(*) FROM models")
    sqlite_count = sqlite_Database.fetch_one(query, params)[0]
    pg_Database.execute("SELECT COUNT(*) FROM models")
    pg_count = pg_Database.fetch_one(query, params)[0]
    verification["models"] = {
        "sqlite_count": sqlite_count,
        "postgres_count": pg_count,
        "match": sqlite_count == pg_count
    }
    
    # Check benchmark_results count if table exists
    sqlite_Database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='benchmark_results'")
    if sqlite_Database.fetch_one(query, params):
        sqlite_Database.execute("SELECT COUNT(*) FROM benchmark_results")
        sqlite_count = sqlite_Database.fetch_one(query, params)[0]
        pg_Database.execute("SELECT COUNT(*) FROM benchmark_results")
        pg_count = pg_Database.fetch_one(query, params)[0]
        verification["benchmark_results"] = {
            "sqlite_count": sqlite_count,
            "postgres_count": pg_count,
            "match": sqlite_count == pg_count
        }
    
    # Log verification results
    for table, data in verification.items():
        if data["match"]:
            logger.info(f"✅ {table}: {data['sqlite_count']} records in SQLite, {data['postgres_count']} in PostgreSQL")
        else:
            logger.warning(f"❌ {table}: {data['sqlite_count']} records in SQLite, {data['postgres_count']} in PostgreSQL")
    
    return verification

def main():
    
    # Initialize database schema
    init_database()# Parse command line arguments
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite-db", help="Path to SQLite database", default=SQLITE_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes to PostgreSQL")
    parser.add_argument("--verify", action="store_true", help="Verify migration after completion")
    args = parser.parse_args()
    
    # Update SQLite path if provided
    global SQLITE_DB_PATH
    SQLITE_DB_PATH = args.sqlite_db
    
    # Record start time
    stats["start_time"] = datetime.now().isoformat()
    logger.info(f"Starting migration from SQLite ({SQLITE_DB_PATH}) to PostgreSQL ({DB_NAME})")
    
    if args.dry_run:
        logger.info("DRY RUN MODE: No changes will be committed to PostgreSQL")
    
    # Connect to databases
    sqlite_conn = connect_sqlite()
    pg_conn = connect_postgres()
    
    try:
        # Check SQLite schema and determine migration strategy
        schema_type = check_sqlite_schema(sqlite_conn)
        logger.info(f"Using migration strategy for {schema_type}")
        
        # Migrate data
        endpoint_mapping = migrate_endpoints(sqlite_conn, pg_conn, schema_type)
        model_mapping = migrate_models(sqlite_conn, pg_conn, endpoint_mapping, schema_type)
        migrate_benchmark_results(sqlite_conn, pg_conn, endpoint_mapping, model_mapping)
        
        # Save migration statistics
        save_migration_stats()
        
        # Verify migration if requested
        if args.verify:
            verification = verify_migration(sqlite_conn, pg_conn)
            
        # Rollback if dry run
        if args.dry_run:
            # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pg_conn.rollback()
            logger.info("DRY RUN: All changes have been rolled back")
        else:
            # Final commit
            pg_# Commit handled by Database methods
            logger.info("Migration completed successfully!")
        
    except Exception as e:
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pg_conn.rollback()
        logger.error(f"Migration failed: {str(e)}")
    finally:
        # Close connections
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    main() 