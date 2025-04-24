#!/usr/bin/env python3
"""
Simple script to check the database schema
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if psycopg2 is installed
try:
    import psycopg2
except ImportError:
    print("psycopg2 package is required for PostgreSQL connectivity.")
    print("Install it using: pip install psycopg2-binary")
    sys.exit(1)

# Get database connection parameters
DB_NAME = os.getenv("POSTGRES_DB", "ollama_scanner")
DB_USER = os.getenv("POSTGRES_USER", "ollama")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

print(f"Connecting to PostgreSQL database: {DB_NAME} on {DB_HOST}:{DB_PORT}")
try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = [row[0] for row in cursor.fetchall()]
    print("\nTables in database:")
    for table in tables:
        print(f"- {table}")
    
    # Check columns in servers table
    if 'servers' in tables:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'servers'")
        columns = [row[0] for row in cursor.fetchall()]
        print("\nColumns in servers table:")
        for column in columns:
            print(f"- {column}")
    else:
        print("\nServers table not found!")
    
    # Check columns in models table
    if 'models' in tables:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'models'")
        columns = [row[0] for row in cursor.fetchall()]
        print("\nColumns in models table:")
        for column in columns:
            print(f"- {column}")
    else:
        print("\nModels table not found!")
    
    # Check if the metadata table exists
    if 'metadata' in tables:
        cursor.execute("SELECT key, value FROM metadata LIMIT 10")
        metadata = cursor.fetchall()
        print("\nSample metadata entries:")
        for key, value in metadata:
            print(f"- {key}: {value}")
    else:
        print("\nMetadata table not found!")
    
    conn.close()
    print("\nDatabase connection closed.")
except psycopg2.Error as e:
    print(f"PostgreSQL error: {e}")
    sys.exit(1) 