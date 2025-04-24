#!/usr/bin/env python3
"""
Script to check database connections and query model counts
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables 
load_dotenv()

# Try loading from DiscordBot .env if it exists
discordbot_env = os.path.join(os.path.dirname(__file__), 'DiscordBot', '.env')
if os.path.exists(discordbot_env):
    load_dotenv(discordbot_env, override=True)
    print(f"Loaded environment from {discordbot_env}")

# Import db after loading env
from database import Database, init_database

def check_postgres_connection():
    """Check PostgreSQL connection and print counts from key tables"""
    try:
        # Initialize database
        init_database()
        
        # Print connection info
        db_type = os.getenv("DATABASE_TYPE", "")
        db_host = os.getenv("POSTGRES_HOST", "")
        db_port = os.getenv("POSTGRES_PORT", "")
        db_name = os.getenv("POSTGRES_DB", "")
        db_user = os.getenv("POSTGRES_USER", "")
        
        print(f"Database Type: {db_type}")
        print(f"Connection Info: {db_user}@{db_host}:{db_port}/{db_name}")
        
        # Check endpoints
        endpoint_query = "SELECT COUNT(*) FROM endpoints"
        endpoint_count = Database.fetch_one(endpoint_query)
        print(f"Endpoints Count: {endpoint_count[0] if endpoint_count else 0}")
        
        # Check verified endpoints
        verified_query = "SELECT COUNT(*) FROM endpoints WHERE verified = 1"
        verified_count = Database.fetch_one(verified_query)
        print(f"Verified Endpoints Count: {verified_count[0] if verified_count else 0}")
        
        # Check models
        models_query = "SELECT COUNT(*) FROM models"
        models_count = Database.fetch_one(models_query)
        print(f"Models Count: {models_count[0] if models_count else 0}")
        
        # Check specific models if any exist
        if models_count and models_count[0] > 0:
            # Check for deepseek models in database
            deepseek_query = """
                SELECT COUNT(*) 
                FROM models 
                WHERE LOWER(name) LIKE '%deepseek%'
            """
            deepseek_count = Database.fetch_one(deepseek_query)
            print(f"Deepseek Models Count: {deepseek_count[0] if deepseek_count else 0}")
            
            # List some example models
            model_sample_query = """
                SELECT id, name, parameter_size 
                FROM models 
                WHERE LOWER(name) LIKE '%deepseek%'
                LIMIT 5
            """
            model_samples = Database.fetch_all(model_sample_query)
            
            if model_samples and len(model_samples) > 0:
                print("\nSample Deepseek Models:")
                for row in model_samples:
                    model_id = row[0] if len(row) > 0 else "N/A"
                    model_name = row[1] if len(row) > 1 else "N/A"
                    param_size = row[2] if len(row) > 2 else "N/A"
                    print(f"  ID: {model_id}, Name: {model_name}, Params: {param_size}")
            else:
                print("\nNo deepseek models found in database.")
                
                # Check what model names exist
                print("\nChecking for other model types...")
                sample_models_query = """
                    SELECT name, COUNT(*) as count
                    FROM models
                    GROUP BY name
                    ORDER BY count DESC
                    LIMIT 10
                """
                sample_results = Database.fetch_all(sample_models_query)
                
                if sample_results and len(sample_results) > 0:
                    print("\nTop 10 Model Names:")
                    for row in sample_results:
                        model_name = row[0] if len(row) > 0 else "N/A"
                        count = row[1] if len(row) > 1 else 0
                        print(f"  Name: {model_name}, Count: {count}")
        
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        return False

if __name__ == "__main__":
    print("Checking database connection...")
    success = check_postgres_connection()
    
    if not success:
        print("\nAttempting to check database configuration...")
        try:
            # Print all relevant environment variables
            print(f"Current directory: {os.getcwd()}")
            print(f"DATABASE_TYPE: {os.getenv('DATABASE_TYPE', 'Not set')}")
            print(f"POSTGRES_HOST: {os.getenv('POSTGRES_HOST', 'Not set')}")
            print(f"POSTGRES_PORT: {os.getenv('POSTGRES_PORT', 'Not set')}")
            print(f"POSTGRES_DB: {os.getenv('POSTGRES_DB', 'Not set')}")
            print(f"POSTGRES_USER: {os.getenv('POSTGRES_USER', 'Not set')}")
            print(f"POSTGRES_PASSWORD: {'*****' if os.getenv('POSTGRES_PASSWORD') else 'Not set'}")
        except Exception as e:
            print(f"Error checking configuration: {e}")
    
    sys.exit(0 if success else 1) 