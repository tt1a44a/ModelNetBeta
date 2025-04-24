#!/usr/bin/env python3
"""
Script to directly check PostgreSQL models table
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment variables 
load_dotenv()

# Try loading from DiscordBot .env if it exists
discordbot_env = os.path.join(os.path.dirname(__file__), 'DiscordBot', '.env')
if os.path.exists(discordbot_env):
    load_dotenv(discordbot_env, override=True)
    print(f"Loaded environment from {discordbot_env}")

def check_postgres_models():
    """Connect directly to PostgreSQL and check models table"""
    try:
        # Get connection parameters from environment
        dbname = os.getenv("POSTGRES_DB", "ollama_scanner")
        user = os.getenv("POSTGRES_USER", "ollama")
        password = os.getenv("POSTGRES_PASSWORD", "ollama_scanner_password")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5433")
        
        # Connect to PostgreSQL
        print(f"Connecting to PostgreSQL: {user}@{host}:{port}/{dbname}")
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        
        # Create cursor
        cursor = conn.cursor()
        
        # Get table names to verify structure
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = cursor.fetchall()
        print("\nDatabase tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Get column names for models table
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='models'")
        columns = cursor.fetchall()
        print("\nModels table columns:")
        for column in columns:
            print(f"  - {column[0]}")
        
        # Count models
        cursor.execute("SELECT COUNT(*) FROM models")
        count = cursor.fetchone()[0]
        print(f"\nTotal models count: {count}")
        
        # Check for deepseek models
        cursor.execute("SELECT COUNT(*) FROM models WHERE name ILIKE '%deepseek%'")
        deepseek_count = cursor.fetchone()[0]
        print(f"Deepseek models count: {deepseek_count}")
        
        # Get sample of model names
        cursor.execute("""
            SELECT name, COUNT(*) as count
            FROM models
            GROUP BY name
            ORDER BY count DESC
            LIMIT 10
        """)
        model_counts = cursor.fetchall()
        print("\nTop 10 models by count:")
        for model, count in model_counts:
            print(f"  - {model}: {count}")
        
        # Get parameter sizes
        cursor.execute("""
            SELECT parameter_size, COUNT(*) as count
            FROM models
            WHERE parameter_size IS NOT NULL
            GROUP BY parameter_size
            ORDER BY count DESC
            LIMIT 10
        """)
        param_sizes = cursor.fetchall()
        print("\nPopular parameter sizes:")
        for size, count in param_sizes:
            print(f"  - {size}: {count}")
        
        # Check deepseek models with specific parameter sizes
        if deepseek_count > 0:
            cursor.execute("""
                SELECT name, parameter_size, quantization_level, COUNT(*) as count
                FROM models
                WHERE name ILIKE '%deepseek%'
                GROUP BY name, parameter_size, quantization_level
                ORDER BY count DESC
            """)
            deepseek_models = cursor.fetchall()
            print("\nDeepseek models by parameter size:")
            for name, size, quant, count in deepseek_models:
                print(f"  - {name} | Size: {size or 'Unknown'} | Quant: {quant or 'Unknown'} | Count: {count}")
                
        # Check join to endpoints table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = 1
        """)
        verified_models = cursor.fetchone()[0]
        print(f"\nModels with verified endpoints: {verified_models}")
        
        # Close connection
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        return False

if __name__ == "__main__":
    print("Checking PostgreSQL models table...")
    success = check_postgres_models()
    sys.exit(0 if success else 1) 