#!/usr/bin/env python3
"""
Query tool for searching the Ollama Scanner database
"""

import os
import sys
import argparse
from database import Database, init_database

def checkDB():
    """Check if database has data"""
    try:
        # how many servers do we have?
        count = Database.fetch_one("SELECT COUNT(*) FROM servers")[0]
        
        if count == 0:
            print("No data found in the database.")
            print("Run ollama_scanner.py first to collect data.")
            return False
        
        print(f"Database contains {count} servers.")
        return True
    except Exception as e:
        print(f"Error checking database: {e}")
        return False

def listServers():
    """List all servers in the database"""
    try:
        servers = Database.fetch_all("SELECT * FROM servers ORDER BY scan_date DESC")
        
        if not servers:
            print("No servers found in database.")
            return
        
        print(f"\nFound {len(servers)} servers:")
        print("-" * 80)
        print(f"{'ID':<5} {'IP':<15} {'Port':<6} {'Status':<12} {'Scan Date':<20}")
        print("-" * 80)
        
        for server in servers:
            print(f"{server[0]:<5} {server[1]:<15} {server[2]:<6} {server[3]:<12} {str(server[4]):<20}")
            
    except Exception as e:
        print(f"Error listing servers: {e}")

def listModels():
    """List all models in the database"""
    try:
        models = Database.fetch_all("SELECT * FROM models ORDER BY name")
        
        if not models:
            print("No models found in database.")
            return
        
        print(f"\nFound {len(models)} models:")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<30} {'Server ID':<10} {'Params':<10}")
        print("-" * 80)
        
        for model in models:
            print(f"{model[0]:<5} {model[1]:<30} {model[2]:<10} {model[3] or 'N/A':<10}")
            
    except Exception as e:
        print(f"Error listing models: {e}")

def searchModels(search_term):
    """Search for models by name"""
    try:
        query = "SELECT * FROM models WHERE name ILIKE %s ORDER BY name"
        models = Database.fetch_all(query, (f"%{search_term}%",))
        
        if not models:
            print(f"No models found matching '{search_term}'.")
            return
        
        print(f"\nFound {len(models)} models matching '{search_term}':")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<30} {'Server ID':<10} {'Params':<10}")
        print("-" * 80)
        
        for model in models:
            print(f"{model[0]:<5} {model[1]:<30} {model[2]:<10} {model[3] or 'N/A':<10}")
            
    except Exception as e:
        print(f"Error searching models: {e}")

def main():
    parser = argparse.ArgumentParser(description='Query Ollama Scanner database')
    parser.add_argument('command', choices=['servers', 'models', 'search'], 
                       help='Command to execute')
    parser.add_argument('search_term', nargs='?', 
                       help='Search term for search command')
    
    args = parser.parse_args()
    
    # Initialize database
    init_database()
    
    if args.command == 'servers':
        if checkDB():
            listServers()
    elif args.command == 'models':
        if checkDB():
            listModels()
    elif args.command == 'search':
        if not args.search_term:
            print("Error: search command requires a search term")
            return
        if checkDB():
            searchModels(args.search_term)

if __name__ == "__main__":
    main()
