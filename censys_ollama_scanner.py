#!/usr/bin/env python3
"""
Censys Ollama Scanner - Find Ollama instances using Censys API
"""

import os
import sys
import time
import json
import sqlite3
import requests
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from dotenv import load_dotenv
from queue import Queue

# Added by migration script
from database import Database, init_database

# Load environment variables from .env file if it exists
load_dotenv()

# Censys API credentials
CENSYS_API_ID = os.getenv("CENSYS_API_ID", "")
CENSYS_API_SECRET = os.getenv("CENSYS_API_SECRET", "")

# Database file
# TODO: Replace SQLite-specific code: database_file = 'ollama_instances.db'
timeout = 5 
max_results = 1000  

# Database lock for thread safety
db_lock = threading.Lock()

def make_database():
    """Create the SQLite database and tables if they don't exist"""
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        port INTEGER,
        scan_date TEXT,
        UNIQUE(ip, port)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER,
        name TEXT,
        parameter_size TEXT,
        quantization_level TEXT,
        size_mb REAL,
        FOREIGN KEY (server_id) REFERENCES servers (id),
        UNIQUE(server_id, name)
    )
    ''')
    
    # Commit handled by Database methods
    conn.close()

def check_ollama_endpoint(ip, port, timeout=5):
    """
    Check if the given IP and port has a valid Ollama instance
    
    Args:
        ip: IP address to check
        port: Port to check
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (is_valid, models_list)
    """
    try:
        # Try to get the list of models
        url = f"http://{ip}:{port}/api/tags"
        response = requests.get(url, timeout=timeout)
        
        if response.status_code == 200:
            try:
                data = response.json()
                models = data.get("models", [])
                
                if models:
                    return True, models
                else:
                    return True, []  # Valid Ollama instance but no models
            except:
                return False, []
        else:
            return False, []
    except:
        return False, []

def save_server_to_db(ip, port):
    """
    Save a server to the database
    
    Args:
        ip: IP address
        port: Port number
        
    Returns:
        Server ID if successful, None if failed
    """
    try:
        with db_lock:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Check if server already exists
            Database.execute("SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
            existing = Database.fetch_one(query, params)
            
            if existing:
                server_id = existing[0]
            else:
                # Insert new server
                cursor.execute(
                    "INSERT INTO servers (ip, port, scan_date) VALUES (?, ?, ?)",
                    (ip, port, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
                server_id = cursor.lastrowid
            
            # Commit handled by Database methods
            conn.close()
            return server_id
    except Exception as e:
        print(f"Error saving server to database: {str(e)}")
        return None

def save_models_to_db(server_id, models):
    """
    Save models to the database
    
    Args:
        server_id: ID of the server in the database
        models: List of model dictionaries
    """
    if not models:
        return
    
    try:
        with db_lock:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            for model in models:
                name = model.get("name", "")
                parameter_size = model.get("parameter_size", "")
                quantization_level = model.get("quantization_level", "")
                size_mb = model.get("size_mb", 0)
                
                # Check if model already exists for this server
                cursor.execute(
                    "SELECT id FROM models WHERE server_id = ? AND name = ?",
                    (server_id, name)
                )
                existing = Database.fetch_one(query, params)
                
                if not existing:
                    # Insert new model
                    cursor.execute(
                        """
                        INSERT INTO models 
                        (server_id, name, parameter_size, quantization_level, size_mb) 
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (server_id, name, parameter_size, quantization_level, size_mb)
                    )
            
            # Commit handled by Database methods
            conn.close()
    except Exception as e:
        print(f"Error saving models to database: {str(e)}")

def search_censys():
    """Search Censys for potential Ollama instances"""
    try:
        # Import Censys here to avoid making it a hard dependency
        from censys.search import CensysHosts
        
        if not CENSYS_API_ID or not CENSYS_API_SECRET:
            print("Censys API credentials not configured. Please set CENSYS_API_ID and CENSYS_API_SECRET environment variables.")
            return []
        
        # Initialize the Censys client
        h = CensysHosts(api_id=CENSYS_API_ID, api_secret=CENSYS_API_SECRET)
        
        print("Searching Censys for Ollama instances...")
        
        # Search for potential Ollama instances
        # These queries target typical HTTP signatures that might be associated with Ollama
        queries = [
            # Search for Ollama landing page text
            "services.http.response.body: \"ollama is running\"",
            # Search for typical Ollama HTTP response
            "services.http.response.body: ollama",
            # Default Ollama port 
            "services.port: 11434",
            # Ollama API endpoint
            "services.http.response.body: /api/tags",
            # Search for typical API response structure
            "services.http.response.body: models AND services.http.response.body: array"
        ]
        
        all_results = []
        
        for query in queries:
            try:
                print(f"Executing Censys query: {query}")
                
                # Execute the query and get up to 1000 results
                query_results = list(h.search(query, per_page=100, pages=10))
                
                print(f"Found {len(query_results)} results for query: {query}")
                
                # Add the results to our master list
                all_results.extend(query_results)
                
                # Sleep to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"Error with Censys query '{query}': {str(e)}")
        
        # Clean and deduplicate results
        clean_results = []
        seen_ips = set()
        
        for result in all_results:
            ip = result.get("ip")
            
            # Skip duplicates
            if ip in seen_ips:
                continue
                
            seen_ips.add(ip)
            
            # Format as Shodan-like result for compatibility
            formatted_result = {
                'ip_str': ip
            }
            
            # Initialize a set of potential ports to check
            potential_ports = set()
            
            # First, try to find the port through service analysis
            # Prioritize port 11434 if available
            for service in result.get("services", []):
                port = service.get("port")
                if port:
                    potential_ports.add(port)
                    
                    # Look for "ollama is running" text in HTTP responses
                    http_data = service.get("http", {})
                    response_body = http_data.get("response", {}).get("body", "")
                    
                    if "ollama is running" in response_body.lower():
                        # Found Ollama landing page on this port, prioritize it
                        formatted_result['port'] = port
                        break
            
            # If we haven't assigned a port yet but found the default Ollama port, use it
            if 'port' not in formatted_result and 11434 in potential_ports:
                formatted_result['port'] = 11434
            
            # If we still don't have a port but have other options, use the first one
            # We'll try all potential ports later during the full scan
            if 'port' not in formatted_result and potential_ports:
                formatted_result['port'] = next(iter(potential_ports))
                
            # Add any additional potential ports to check
            if potential_ports:
                formatted_result['additional_ports'] = list(potential_ports)
            
            clean_results.append(formatted_result)
        
        print(f"After deduplication, found {len(clean_results)} unique IPs from Censys")
        return clean_results
        
    except ImportError:
        print("Censys module not installed. Please install it with 'pip install censys'")
        return []
    except Exception as e:
        print(f"Error during Censys search: {str(e)}")
        return []

def scan_server(result, stats):
    """
    Scan a single server for Ollama instances
    
    Args:
        result: Server result from Censys
        stats: Statistics dictionary with thread-safe counter
    """
    ip = result['ip_str']
    port = result.get('port', 11434)  # Default to 11434 if not specified
    additional_ports = result.get('additional_ports', [])
    
    # Try the primary port first
    is_valid, models = check_ollama_endpoint(ip, port, timeout)
    
    if is_valid:
        print(f"Found Ollama instance at {ip}:{port}")
        
        # Save to database
        server_id = save_server_to_db(ip, port)
        if server_id and models:
            save_models_to_db(server_id, models)
        
        with stats['lock']:
            stats['good'] += 1
        
        # Print model information
        if models:
            print(f"  Models available: {len(models)}")
            for model in models:
                name = model.get("name", "Unknown")
                print(f"    - {name}")
        else:
            print("  No models found")
        
        return
    
    # If primary port failed, try additional ports
    for alt_port in additional_ports:
        if alt_port == port:  # Skip if we already tried this port
            continue
            
        is_valid, models = check_ollama_endpoint(ip, alt_port, timeout)
        
        if is_valid:
            print(f"Found Ollama instance at {ip}:{alt_port}")
            
            # Save to database
            server_id = save_server_to_db(ip, alt_port)
            if server_id and models:
                save_models_to_db(server_id, models)
            
            with stats['lock']:
                stats['good'] += 1
            
            # Print model information
            if models:
                print(f"  Models available: {len(models)}")
                for model in models:
                    name = model.get("name", "Unknown")
                    print(f"    - {name}")
            else:
                print("  No models found")
            
            return
    
    # If we get here, no valid Ollama instance was found
    with stats['lock']:
        stats['bad'] += 1
    print(f"No valid Ollama instance found at {ip}")

def run_scan(num_threads=10):
    """
    Run Ollama scanner to find instances using Censys
    
    Args:
        num_threads: Number of concurrent threads to use for scanning
    """
    print("----------------------------------------")
    print("  Censys Ollama Scanner - Find AI Models!  ")
    print("----------------------------------------")
    print("Started at " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print(f"Using {num_threads} threads for scanning")
    
    make_database()
    
    # Get Censys results
    results = search_censys()
    
    if not results:
        print("No potential Ollama instances found. Exiting.")
        return
    
    print(f"Total potential Ollama instances found: {len(results)}")
    
    # Statistics with thread safety
    stats = {
        'good': 0,
        'bad': 0,
        'lock': threading.Lock()
    }
    
    # Use thread pool to scan servers in parallel
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit tasks for all results
        futures = [executor.submit(scan_server, result, stats) for result in results]
        
        # Wait for all tasks to complete
        for future in futures:
            future.result()
    
    # Print summary
    print("\n----------------------------------------")
    print("  Scan Complete!  ")
    print("----------------------------------------")
    print(f"Total servers scanned: {len(results)}")
    print(f"Valid Ollama instances found: {stats['good']}")
    print(f"Invalid or unreachable servers: {stats['bad']}")
    print("----------------------------------------")

def main():
    
    # Initialize database schema
    init_database()"""Main entry point"""
    parser = argparse.ArgumentParser(description="Censys Ollama Scanner")
    parser.add_argument("--threads", type=int, default=10, help="Number of threads to use for scanning")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds")
    parser.add_argument("--max-results", type=int, default=1000, help="Maximum number of results to process")
    
    args = parser.parse_args()
    
    # Update global variables from command line arguments
    global timeout, max_results
    timeout = args.timeout
    max_results = args.max_results
    
    run_scan(args.threads)

if __name__ == "__main__":
    main() 