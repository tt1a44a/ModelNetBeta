#!/usr/bin/env python3
import sqlite3
import os

# Added by migration script
from database import Database, init_database

# Database configuration
# TODO: Replace SQLite-specific code: DB_FILE = "ollama_instances.db"

def update_schema():
    """Update the database schema to include benchmark-related columns"""
    # Check if database exists
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file {DB_FILE} not found!")
        return False
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Create benchmark_results table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER,
        model_id INTEGER,
        test_date TEXT NOT NULL,
        avg_response_time REAL,
        tokens_per_second REAL,
        first_token_latency REAL,
        throughput_tokens REAL,
        throughput_time REAL,
        context_500_tps REAL,
        context_1000_tps REAL,
        context_2000_tps REAL,
        max_concurrent_requests INTEGER,
        concurrency_success_rate REAL,
        concurrency_avg_time REAL,
        success_rate REAL,
        FOREIGN KEY (server_id) REFERENCES servers(id),
        FOREIGN KEY (model_id) REFERENCES models(id)
    )
    ''')
    
    # Check if we need to add missing columns
    Database.execute("PRAGMA table_info(benchmark_results)")
    existing_columns = [col[1] for col in Database.fetch_all(query, params)]
    
    # Check for throughput columns
    if 'throughput_tokens' not in existing_columns:
        print("Adding throughput_tokens column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN throughput_tokens REAL")
    
    if 'throughput_time' not in existing_columns:
        print("Adding throughput_time column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN throughput_time REAL")
    
    # Check for context handling columns
    if 'context_500_tps' not in existing_columns:
        print("Adding context_500_tps column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN context_500_tps REAL")
    
    if 'context_1000_tps' not in existing_columns:
        print("Adding context_1000_tps column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN context_1000_tps REAL")
    
    if 'context_2000_tps' not in existing_columns:
        print("Adding context_2000_tps column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN context_2000_tps REAL")
    
    # Check for concurrency columns
    if 'max_concurrent_requests' not in existing_columns:
        print("Adding max_concurrent_requests column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN max_concurrent_requests INTEGER")
    
    if 'concurrency_success_rate' not in existing_columns:
        print("Adding concurrency_success_rate column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN concurrency_success_rate REAL")
    
    if 'concurrency_avg_time' not in existing_columns:
        print("Adding concurrency_avg_time column...")
        Database.execute("ALTER TABLE benchmark_results ADD COLUMN concurrency_avg_time REAL")
    
    # Commit handled by Database methods
    conn.close()
    print("Schema update complete!")
    return True

if __name__ == "__main__":
    update_schema() 