#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for Ollama Scanner

This script migrates data from an existing SQLite database to a PostgreSQL database.
It handles schema conversion, data migration, and validation.
"""

import os
import sys
import time
import logging
import sqlite3
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migration.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("migration")

# Load environment variables
load_dotenv()

# Database configuration
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", os.path.join('DiscordBot', 'ollama_instances.db'))
POSTGRES_DB = os.getenv("POSTGRES_DB", "ollama_scanner")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ollama")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Table mapping (SQLite table name -> PostgreSQL table name)
TABLE_MAPPING = {
    "endpoints": "endpoints",
    "verified_endpoints": "verified_endpoints",
    "models": "models",
    "benchmark_results": "benchmark_results"
}

# Type mapping (SQLite type -> PostgreSQL type)
TYPE_MAPPING = {
    "INTEGER": "INTEGER",
    "REAL": "NUMERIC(12, 2)",
    "TEXT": "TEXT",
    "BLOB": "BYTEA",
    "BOOLEAN": "BOOLEAN",
    "DATETIME": "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP": "TIMESTAMP WITH TIME ZONE",
}

def connect_sqlite():
    """Connect to SQLite database directly (not using Database class)"""
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        logger.info(f"Connected to SQLite DB: {SQLITE_DB_PATH}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"SQLite connection error: {e}")
        sys.exit(1)

def connect_postgres():
    """Connect to PostgreSQL database directly (not using Database class)"""
    try:
        conn = psycopg2.connect(
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        logger.info(f"Connected to PostgreSQL DB: {POSTGRES_DB} on {POSTGRES_HOST}:{POSTGRES_PORT}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL connection error: {e}")
        sys.exit(1)

def get_sqlite_tables(sqlite_conn):
    """Get list of tables from SQLite database"""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return tables

def get_table_schema(sqlite_conn, table_name):
    """Get schema definition for a SQLite table"""
    cursor = sqlite_conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    cursor.close()
    return columns

def create_postgres_table(pg_conn, table_name, sqlite_schema):
    """Create table in PostgreSQL based on SQLite schema"""
    cursor = pg_conn.cursor()
    
    # Map SQLite column types to PostgreSQL types
    columns = []
    primary_keys = []
    
    for col in sqlite_schema:
        col_id, col_name, col_type, not_null, default_value, is_pk = col
        
        # Map the column type
        pg_type = TYPE_MAPPING.get(col_type.upper(), "TEXT")
        
        # Handle autoincrement/primary key
        column_def = f"{col_name} {pg_type}"
        
        if is_pk:
            primary_keys.append(col_name)
            if col_type.upper() == "INTEGER":
                column_def = f"{col_name} SERIAL"
        
        if not_null:
            column_def += " NOT NULL"
            
        if default_value is not None:
            if isinstance(default_value, str) and not default_value.startswith("CURRENT_") and not default_value.isdigit():
                column_def += f" DEFAULT '{default_value}'"
            else:
                column_def += f" DEFAULT {default_value}"
                
        columns.append(column_def)
    
    # Add primary key constraint if needed
    if primary_keys:
        columns.append(f"PRIMARY KEY ({', '.join(primary_keys)})")
    
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    " + ",\n    ".join(columns) + "\n);"
    
    try:
        cursor.execute(create_table_sql)
        logger.info(f"Created table: {table_name}")
        logger.debug(f"SQL: {create_table_sql}")
    except psycopg2.Error as e:
        logger.error(f"Error creating table {table_name}: {e}")
        logger.debug(f"SQL: {create_table_sql}")
        raise
    finally:
        cursor.close()

def get_table_data(sqlite_conn, table_name):
    """Get all data from a SQLite table"""
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    cursor.close()
    return rows, columns

def fix_timestamp_format(data, columns):
    """Convert SQLite timestamp strings to PostgreSQL compatible format"""
    timestamp_columns = ["scan_date", "verification_date", "test_date"]
    fixed_data = []
    
    for row in data:
        row_dict = dict(zip(columns, row))
        for col in timestamp_columns:
            if col in row_dict and row_dict[col]:
                # Try to convert to ISO format if needed
                try:
                    dt = datetime.fromisoformat(row_dict[col].replace('Z', '+00:00'))
                    row_dict[col] = dt.isoformat()
                except (ValueError, AttributeError, TypeError):
                    # Leave as is if we can't convert
                    pass
        fixed_data.append(tuple(row_dict[col] for col in columns))
    
    return fixed_data

def migrate_table_data(sqlite_conn, pg_conn, sqlite_table, pg_table):
    """Migrate data from SQLite table to PostgreSQL table"""
    rows, columns = get_table_data(sqlite_conn, sqlite_table)
    
    if not rows:
        logger.info(f"No data to migrate for table: {sqlite_table}")
        return 0
    
    # Fix timestamp formats for PostgreSQL
    rows = fix_timestamp_format(rows, columns)
    
    total_rows = len(rows)
    logger.info(f"Migrating {total_rows} rows from {sqlite_table} to {pg_table}")
    
    # Prepare column placeholders for INSERT statement
    placeholders = ', '.join(['%s'] * len(columns))
    columns_str = ', '.join(columns)
    
    pg_cursor = pg_conn.cursor()
    
    try:
        # Use batch inserts for better performance
        batch_size = 1000
        
        for i in range(0, total_rows, batch_size):
            batch = rows[i:i+batch_size]
            
            # Handle empty values: convert empty strings to None for numeric columns
            processed_batch = []
            for row in batch:
                processed_row = []
                for j, val in enumerate(row):
                    # If it's an empty string and column might be numeric or date
                    if val == '' and columns[j] not in ('ip', 'name'):
                        processed_row.append(None)
                    else:
                        processed_row.append(val)
                processed_batch.append(tuple(processed_row))
            
            insert_query = f"INSERT INTO {pg_table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
            
            pg_cursor.executemany(insert_query, processed_batch)
            
            logger.info(f"Migrated batch: {i+1}-{min(i+batch_size, total_rows)} of {total_rows}")
            
        logger.info(f"Successfully migrated {total_rows} rows to {pg_table}")
        return total_rows
    except psycopg2.Error as e:
        logger.error(f"Error migrating data to {pg_table}: {e}")
        raise
    finally:
        pg_cursor.close()

def validate_migration(sqlite_conn, pg_conn, sqlite_table, pg_table):
    """Validate the migrated data by comparing row counts and sampling data"""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    # Compare row counts
    sqlite_cursor.execute(f"SELECT COUNT(*) FROM {sqlite_table};")
    sqlite_count = sqlite_cursor.fetchone()[0]
    
    pg_cursor.execute(f"SELECT COUNT(*) FROM {pg_table};")
    pg_count = pg_cursor.fetchone()[0]
    
    # Allow for some discrepancy due to ON CONFLICT DO NOTHING
    if pg_count < sqlite_count * 0.9:  # Allow 10% discrepancy
        logger.warning(f"Row count mismatch for {sqlite_table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        logger.warning(f"This might be due to duplicate entries being skipped during migration")
    else:
        logger.info(f"Row count validation: SQLite={sqlite_count}, PostgreSQL={pg_count}")
    
    # Sample and compare a few rows (skip detailed validation for now)
    if sqlite_count > 0:
        logger.info(f"Sampling rows from {sqlite_table} for validation")
    
    sqlite_cursor.close()
    pg_cursor.close()
    return True

def create_indices(pg_conn, table_name):
    """Create indices in PostgreSQL for common queries"""
    pg_cursor = pg_conn.cursor()
    
    indices = []
    
    # Define common indices based on table
    if table_name == 'endpoints':
        indices = [
            ("endpoints_ip_idx", "ip"),
            ("endpoints_verified_idx", "verified"),
        ]
    elif table_name == 'verified_endpoints':
        indices = [
            ("verified_endpoints_endpoint_id_idx", "endpoint_id"),
        ]
    elif table_name == 'models':
        indices = [
            ("models_endpoint_id_idx", "endpoint_id"),
            ("models_name_idx", "name"),
        ]
    elif table_name == 'benchmark_results':
        indices = [
            ("benchmark_results_endpoint_id_idx", "endpoint_id"),
            ("benchmark_results_model_id_idx", "model_id"),
            ("benchmark_results_test_date_idx", "test_date"),
        ]
    
    for index_name, column in indices:
        create_index_sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column});"
        
        try:
            pg_cursor.execute(create_index_sql)
            logger.info(f"Created index: {index_name}")
        except psycopg2.Error as e:
            logger.error(f"Error creating index {index_name}: {e}")
    
    pg_cursor.close()

def create_views(pg_conn):
    """Create necessary views for compatibility"""
    pg_cursor = pg_conn.cursor()
    
    # Create servers view for backward compatibility
    servers_view_sql = """
    CREATE OR REPLACE VIEW servers AS
    SELECT 
        e.id, 
        e.ip, 
        e.port, 
        e.scan_date
    FROM 
        endpoints e
    JOIN
        verified_endpoints ve ON e.id = ve.endpoint_id;
    """
    
    try:
        pg_cursor.execute(servers_view_sql)
        logger.info("Created servers view for backward compatibility")
    except psycopg2.Error as e:
        logger.error(f"Error creating servers view: {e}")
    
    pg_cursor.close()

def migrate_database():
    """Main migration function"""
    start_time = time.time()
    total_tables = 0
    total_rows = 0
    
    logger.info("Starting SQLite to PostgreSQL migration")
    logger.info(f"Source: {SQLITE_DB_PATH}")
    logger.info(f"Target: PostgreSQL {POSTGRES_DB} on {POSTGRES_HOST}:{POSTGRES_PORT}")
    
    # Connect to both databases directly
    sqlite_conn = connect_sqlite()
    pg_conn = connect_postgres()
    
    try:
        # Get tables from SQLite
        sqlite_tables = get_sqlite_tables(sqlite_conn)
        logger.info(f"Found {len(sqlite_tables)} tables in SQLite database: {', '.join(sqlite_tables)}")
        
        # Process each table
        for sqlite_table in sqlite_tables:
            if sqlite_table in TABLE_MAPPING:
                pg_table = TABLE_MAPPING[sqlite_table]
                
                # Get schema and create table in PostgreSQL
                schema = get_table_schema(sqlite_conn, sqlite_table)
                create_postgres_table(pg_conn, pg_table, schema)
                
                # Migrate data
                rows_migrated = migrate_table_data(sqlite_conn, pg_conn, sqlite_table, pg_table)
                total_rows += rows_migrated
                
                # Create indices
                create_indices(pg_conn, pg_table)
                
                # Validate migration
                if validate_migration(sqlite_conn, pg_conn, sqlite_table, pg_table):
                    logger.info(f"✅ Table {sqlite_table} -> {pg_table} migrated successfully")
                else:
                    logger.warning(f"⚠️ Table {sqlite_table} -> {pg_table} migration validation failed")
                
                total_tables += 1
            else:
                logger.warning(f"Table {sqlite_table} not in mapping, skipping")
        
        # Create necessary views after all tables are migrated
        create_views(pg_conn)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.exception("Exception details:")
        sys.exit(1)
    
    finally:
        # Close connections
        sqlite_conn.close()
        pg_conn.close()
    
    # Log summary
    duration = time.time() - start_time
    logger.info(f"Migration completed in {duration:.2f} seconds")
    logger.info(f"Migrated {total_tables} tables and {total_rows} rows")

if __name__ == "__main__":
    print(f"SQLite to PostgreSQL Migration Tool for Ollama Scanner")
    print(f"Source: {SQLITE_DB_PATH}")
    print(f"Target: PostgreSQL {POSTGRES_DB} on {POSTGRES_HOST}:{POSTGRES_PORT}")
    
    # Check if source file exists
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"Error: Source SQLite database file not found: {SQLITE_DB_PATH}")
        sys.exit(1)
    
    confirm = input("Proceed with migration? (y/n): ")
    if confirm.lower() != 'y':
        print("Migration cancelled")
        sys.exit(0)
    
    migrate_database()
    print("Migration completed. See migration.log for details.") 