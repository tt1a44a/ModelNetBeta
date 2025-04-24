#!/usr/bin/env python3
#
# create_mock_db.py - creates m0ck databases for testing c0mbine_db.py
#

import os
import sqlite3
from datetime import datetime, timedelta
import random

# Added by migration script
from database import Database, init_database

def create_mock_ollama_db():
    """Create a mock Ollama database with test data"""
    print("[+] Creating mock Ollama database...")
    
    # Remove existing db if it exists
    # TODO: Replace SQLite-specific code: if os.path.exists('ollama.db'):
        # TODO: Replace SQLite-specific code: os.remove('ollama.db')
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Create servers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY,
        ip TEXT,
        port INTEGER,
        last_seen TEXT,
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
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY,
        server_ip TEXT,
        server_port INTEGER,
        model_name TEXT,
        parameters TEXT,
        quantization TEXT,
        size_mb INTEGER,
        last_seen TEXT
    )
    ''')
    
    # Sample data for servers
    servers = [
        ('192.168.1.1', 11434, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.1.18', 'US', 'United States', 'New York', 'Digital Ocean', 'AS14061', 3),
        ('192.168.1.2', 11434, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.1.17', 'DE', 'Germany', 'Berlin', 'Hetzner', 'AS24940', 2),
        ('192.168.1.3', 11434, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.1.16', 'FR', 'France', 'Paris', 'OVH', 'AS16276', 4),
        ('192.168.1.4', 11434, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.1.18', 'JP', 'Japan', 'Tokyo', 'Linode', 'AS63949', 1),
        ('192.168.1.5', 11434, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.1.18', 'CA', 'Canada', 'Toronto', 'AWS', 'AS16509', 2)
    ]
    
    for server in servers:
        cursor.execute('''
        INSERT INTO servers 
        (ip, port, last_seen, version, country_code, country_name, city, organization, asn, model_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', server)
    
    # Sample data for models
    models = [
        ('192.168.1.1', 11434, 'llama2', '7B', 'Q4_K_M', 3900, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.1', 11434, 'mistral', '7B', 'Q4_0', 4200, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.1', 11434, 'codellama', '13B', 'Q5_K_M', 7800, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.2', 11434, 'llama2', '13B', 'Q4_K_M', 7600, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.2', 11434, 'mistral', '7B', 'Q5_K_M', 4500, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.3', 11434, 'llama2', '70B', 'Q4_0', 35000, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.3', 11434, 'mistral', '7B', 'Q8_0', 6700, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.3', 11434, 'codellama', '7B', 'Q4_K_M', 3800, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.3', 11434, 'vicuna', '13B', 'Q5_K_M', 7800, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.4', 11434, 'mistral', '7B', 'Q4_K_M', 4100, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.5', 11434, 'llama2', '7B', 'Q4_K_M', 3900, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('192.168.1.5', 11434, 'llama2', '13B', 'Q6_K', 9500, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ]
    
    for model in models:
        cursor.execute('''
        INSERT INTO models 
        (server_ip, server_port, model_name, parameters, quantization, size_mb, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', model)
    
    # Commit handled by Database methods
    conn.close()
    print(f"[+] Created mock Ollama database with {len(servers)} servers and {len(models)} models")

def create_mock_litellm_db():
    """Create a mock LiteLLM database with test data"""
    print("[+] Creating mock LiteLLM database...")
    
    # Remove existing db if it exists
    # TODO: Replace SQLite-specific code: if os.path.exists('litellm.db'):
        # TODO: Replace SQLite-specific code: os.remove('litellm.db')
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Create servers table - matching the format in combine_db.py
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY,
        ip TEXT,
        port INTEGER,
        last_seen TEXT,
        version TEXT,
        country_code TEXT,
        country_name TEXT,
        city TEXT,
        organization TEXT,
        asn TEXT,
        model_count INTEGER
    )
    ''')
    
    # Create models table - matching the format in combine_db.py
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY,
        server_ip TEXT,
        server_port INTEGER,
        model_name TEXT,
        provider TEXT,
        parameters TEXT,
        quantization TEXT,
        last_seen TEXT
    )
    ''')
    
    # Sample data for servers
    servers = [
        ('10.0.0.1', 4000, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.6.2', 'US', 'United States', 'Seattle', 'AWS', 'AS16509', 3),
        ('10.0.0.2', 4000, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.6.1', 'UK', 'United Kingdom', 'London', 'Azure', 'AS8075', 4),
        ('10.0.0.3', 4000, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.6.0', 'SG', 'Singapore', 'Singapore', 'GCP', 'AS15169', 2),
        ('10.0.0.4', 4000, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '0.6.2', 'BR', 'Brazil', 'Sao Paulo', 'Linode', 'AS63949', 1)
    ]
    
    for server in servers:
        cursor.execute('''
        INSERT INTO servers 
        (ip, port, last_seen, version, country_code, country_name, city, organization, asn, model_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', server)
    
    # Sample data for models
    models = [
        ('10.0.0.1', 4000, 'gpt-3.5-turbo', 'openai', '6B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.1', 4000, 'gpt-4', 'openai', '175B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.1', 4000, 'text-embedding-ada-002', 'openai', '1B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.2', 4000, 'claude-2', 'anthropic', '100B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.2', 4000, 'llama-2-13b-chat', 'meta', '13B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.2', 4000, 'llama-2-70b-chat', 'meta', '70B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.2', 4000, 'mistral-7b-instruct', 'mistral', '7B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.3', 4000, 'gpt-4', 'openai', '175B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.3', 4000, 'claude-instant-1', 'anthropic', '30B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        ('10.0.0.4', 4000, 'mistral-7b-instruct', 'mistral', '7B', 'None', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ]
    
    for model in models:
        cursor.execute('''
        INSERT INTO models 
        (server_ip, server_port, model_name, provider, parameters, quantization, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', model)
    
    # Commit handled by Database methods
    conn.close()
    print(f"[+] Created mock LiteLLM database with {len(servers)} servers and {len(models)} models")

def main():
    
    # Initialize database schema
    init_database()"""Main function"""
    print("\n===== CREATING M0CK DATABASES FOR TESTING =====\n")
    
    create_mock_ollama_db()
    create_mock_litellm_db()
    
    print("\n[+] B0th databases cr34ted successfully!")
    print("[+] Run combine_db.py to test database merging")

if __name__ == "__main__":
    main() 