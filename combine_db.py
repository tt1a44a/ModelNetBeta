#!/usr/bin/env python3
#
# c0mbine_db.py - hacker script 2 merge 0llama & LiteLLM databases
#

import os
import sqlite3
import sys
from datetime import datetime

# Added by migration script
from database import Database, init_database

def check_db_exists(db_path):
    """Check if database exists"""
    if not os.path.exists(db_path):
        print(f"[!] ERR0R: {db_path} not found!")
        print(f"[*] Run scanners first to create database files")
        return False
    return True

def setup_combined_db():
    """Create combined database structure"""
    # TODO: Replace SQLite-specific code: print(f"[+] Creating new combined database: ai_endpoints.db")
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Drop tables if they exist
    Database.execute('DROP TABLE IF EXISTS servers')
    Database.execute('DROP TABLE IF EXISTS models')
    
    # Create server table
    cursor.execute('''
    CREATE TABLE servers (
        id INTEGER PRIMARY KEY,
        ip TEXT,
        port INTEGER,
        last_seen TEXT,
        type TEXT,
        version TEXT,
        country_code TEXT,
        country_name TEXT,
        city TEXT,
        organization TEXT,
        asn TEXT,
        model_count INTEGER
    )
    ''')
    
    # Create models table
    cursor.execute('''
    CREATE TABLE models (
        id INTEGER PRIMARY KEY,
        server_id INTEGER,
        model_name TEXT,
        provider TEXT,
        parameters TEXT,
        quantization TEXT,
        last_seen TEXT,
        FOREIGN KEY (server_id) REFERENCES servers (id)
    )
    ''')
    
    # Commit handled by Database methods
    conn.close()
    return True

def import_ollama_data():
    """Import data from Ollama database"""
    # TODO: Replace SQLite-specific code: if not check_db_exists('ollama.db'):
        return False
    
    print(f"[+] Importing Ollama data...")
    ollama_conn = Database()
    combined_conn = Database()
    
    ollama_cursor = ollama_# Using Database methods instead of cursor
    combined_cursor = combined_# Using Database methods instead of cursor
    
    # Import servers
    ollama_cursor.execute('''
    SELECT ip, port, last_seen, version, country_code, country_name, 
           city, organization, asn, model_count 
    FROM servers
    ''')
    servers = ollama_Database.fetch_all(query, params)
    
    for server in servers:
        combined_cursor.execute('''
        INSERT INTO servers 
        (ip, port, last_seen, type, version, country_code, country_name, 
         city, organization, asn, model_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (server[0], server[1], server[2], 'ollama', server[3], 
              server[4], server[5], server[6], server[7], server[8], server[9]))
        
        # Get the server ID we just inserted
        server_id = combined_cursor.lastrowid
        
        # Get models for this server
        ollama_cursor.execute('''
        SELECT model_name, parameters, quantization, last_seen 
        FROM models 
        WHERE server_ip = ? AND server_port = ?
        ''', (server[0], server[1]))
        
        models = ollama_Database.fetch_all(query, params)
        for model in models:
            combined_cursor.execute('''
            INSERT INTO models 
            (server_id, model_name, provider, parameters, quantization, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (server_id, model[0], 'ollama', model[1], model[2], model[3]))
    
    combined_# Commit handled by Database methods
    ollama_conn.close()
    combined_conn.close()
    
    print(f"[+] Imported {len(servers)} Ollama servers with their models")
    return True

def import_litellm_data():
    """Import data from LiteLLM database"""
    # TODO: Replace SQLite-specific code: if not check_db_exists('litellm.db'):
        return False
    
    print(f"[+] Importing LiteLLM data...")
    litellm_conn = Database()
    combined_conn = Database()
    
    litellm_cursor = litellm_# Using Database methods instead of cursor
    combined_cursor = combined_# Using Database methods instead of cursor
    
    # Import servers
    litellm_cursor.execute('''
    SELECT ip, port, last_seen, version, country_code, country_name, 
           city, organization, asn, model_count 
    FROM servers
    ''')
    servers = litellm_Database.fetch_all(query, params)
    
    for server in servers:
        combined_cursor.execute('''
        INSERT INTO servers 
        (ip, port, last_seen, type, version, country_code, country_name, 
         city, organization, asn, model_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (server[0], server[1], server[2], 'litellm', server[3], 
              server[4], server[5], server[6], server[7], server[8], server[9]))
        
        # Get the server ID we just inserted
        server_id = combined_cursor.lastrowid
        
        # Get models for this server
        litellm_cursor.execute('''
        SELECT model_name, provider, parameters, quantization, last_seen 
        FROM models 
        WHERE server_ip = ? AND server_port = ?
        ''', (server[0], server[1]))
        
        models = litellm_Database.fetch_all(query, params)
        for model in models:
            combined_cursor.execute('''
            INSERT INTO models 
            (server_id, model_name, provider, parameters, quantization, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (server_id, model[0], model[1], model[2], model[3], model[4]))
    
    combined_# Commit handled by Database methods
    litellm_conn.close()
    combined_conn.close()
    
    print(f"[+] Imported {len(servers)} LiteLLM servers with their models")
    return True

def show_stats():
    """Show statistics about combined database"""
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Get server count by type
    Database.execute('SELECT type, COUNT(*) FROM servers GROUP BY type')
    server_counts = Database.fetch_all(query, params)
    
    # Get total model count
    Database.execute('SELECT COUNT(*) FROM models')
    model_count = Database.fetch_one(query, params)[0]
    
    # Get model count by provider
    Database.execute('SELECT provider, COUNT(*) FROM models GROUP BY provider')
    provider_counts = Database.fetch_all(query, params)
    
    print("\n" + "="*40)
    print("      C0MBINED DATABASE STAT1STICS")
    print("="*40)
    
    print(f"\n[+] Server Stats:")
    for server_type, count in server_counts:
        print(f"    - {server_type.upper()}: {count} servers")
    
    print(f"\n[+] Model Stats:")
    print(f"    - Total models: {model_count}")
    for provider, count in provider_counts:
        print(f"    - {provider.upper()}: {count} models")
    
    print("\n" + "="*40)
    
    conn.close()

def main():
    
    # Initialize database schema
    init_database()print("\n" + "="*50)
    print("  MERG1NG 0LLAMA & LITELLM DATABAS3S - H4CK MODE")
    print("="*50 + "\n")
    
    # Create new combined database
    if not setup_combined_db():
        print("[!] Failed to create combined database")
        return
    
    # Import Ollama data
    import_ollama_data()
    
    # Import LiteLLM data
    import_litellm_data()
    
    # Show stats
    show_stats()
    
    # TODO: Replace SQLite-specific code: print(f"\n[+] Process c0mplete! Combined db saved to ai_endpoints.db")
    print(f"[+] Use query_combined.py to interact with it\n")

if __name__ == "__main__":
    main() 