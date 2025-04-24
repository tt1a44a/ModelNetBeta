#!/usr/bin/env python3
"""
Ollama Scanner - tool to find Ollama instances using Shodan, Censys, and masscan
"""

import os
import sys
import time
import json
import sqlite3
import requests
import argparse
import threading
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue
import signal
from threading import Event

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

# Global verbosity flag - default to False
VERBOSE = False

# Try to import optional dependencies
try:
    from dotenv import load_dotenv
    # Load environment variables from .env file if it exists
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv module not installed. Environment variables from .env file will not be loaded.")
    # Define a dummy function to avoid errors
    def load_dotenv():
        pass

# Shodan API key
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "")

# Censys API credentials
CENSYS_API_ID = os.getenv("CENSYS_API_ID", "")
CENSYS_API_SECRET = os.getenv("CENSYS_API_SECRET", "")

# Initialize Shodan client
shodan_client = None
shodan_available = False
try:
    import shodan
    if SHODAN_API_KEY:
        shodan_client = shodan.Shodan(SHODAN_API_KEY)
        shodan_available = True
except ImportError:
    print("Warning: Shodan module not installed. Run 'pip install shodan' to enable Shodan searching.")

# Try to import Censys if available
try:
    from censys.search import CensysHosts
    censys_available = True
except ImportError:
    censys_available = False
    print("Warning: Censys module not installed. Run 'pip install censys' to enable Censys searching.")
    # Define a dummy CensysHosts class to avoid NameError when referenced
    class CensysHosts:
        def __init__(self, *args, **kwargs):
            raise ImportError("Censys module not installed")

# Define database_file for SQLite only
database_file = os.path.join('DiscordBot', 'ollama_instances.db')

timeout = 5 
maxResults = 1000  

# Database lock for thread safety
db_lock = threading.Lock()

# Global state control variables
scanner_running = True  # Controls if scanner should continue running
scanner_paused = Event()  # Event to pause/resume scanner
scanner_paused.set()  # Initially not paused (set = not paused, clear = paused)

def setup_signal_handlers():
    """Set up handlers for keyboard signals"""
    # Handle Ctrl+C (SIGINT) for pause/resume
    signal.signal(signal.SIGINT, handle_pause_resume)
    
    # Attempt to handle Ctrl+X for termination using SIGQUIT or other available signals
    # SIGQUIT is often Ctrl+\ but we can instruct the user to use it
    signal.signal(signal.SIGQUIT, handle_termination)
    
    print("Keyboard controls enabled:")
    print("  • Press Ctrl+C to pause/resume scanning")
    print("  • Press Ctrl+\\ (Ctrl+Backslash) to terminate the program")
    print("  • While paused, press Ctrl+C again to resume or Ctrl+\\ to exit")

def handle_pause_resume(signum, frame):
    """Handle SIGINT (Ctrl+C) to pause or resume scanning"""
    global scanner_paused
    
    if scanner_paused.is_set():
        # Scanner is running, pause it
        print("\n[PAUSED] Scanning paused. Press Ctrl+C to resume or Ctrl+\\ to exit.")
        scanner_paused.clear()  # Pause the scanner
    else:
        # Scanner is paused, resume it
        print("\n[RESUMED] Scanning resumed.")
        scanner_paused.set()  # Resume the scanner

def handle_termination(signum, frame):
    """Handle SIGQUIT (Ctrl+\\) to terminate the program gracefully"""
    global scanner_running
    
    print("\n[TERMINATING] Gracefully shutting down. Please wait...")
    scanner_running = False
    scanner_paused.set()  # Make sure we're not stuck in pause state
    
    # Optional cleanup operations can be done here
    print("[CLEANUP] Saving current state and closing connections...")
    
    # Exit with proper code
    # Using sys.exit within signal handlers can cause issues, so we exit later
    print("[DONE] Scanner terminated by user.")
    sys.exit(0)

def makeDatabase():
    """Initialize the database schema"""
    # Check if database path is overridden by command line argument
    global database_file
    
    # Get the database path from environment variable if set
    if 'DB_OVERRIDE_PATH' in os.environ and DATABASE_TYPE == "sqlite":
        database_file = os.environ['DB_OVERRIDE_PATH']
        print(f"Using database path from environment: {database_file}")
    
    # For SQLite, ensure the directory exists
    if DATABASE_TYPE == "sqlite":
        db_dir = os.path.dirname(database_file)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                print(f"Created directory: {db_dir}")
            except OSError as e:
                print(f"Error creating directory {db_dir}: {e}")
    
    # Initialize the database schema using the init_database function
    try:
        init_database()
        print(f"Database initialized successfully: {DATABASE_TYPE}")
    except Exception as e:
        print(f"Database initialization error: {e}")
        sys.exit(1)

def isOllamaServer(ip, p=11434, timeout=timeout):
    """Check if an IP/port combo is running Ollama by checking the API endpoint"""
    global scanner_running, scanner_paused
    
    # Check if we should terminate
    if not scanner_running:
        return False, None
        
    # Check if paused
    while not scanner_paused.is_set() and scanner_running:
        time.sleep(0.5)
    
    # Check again after potential pause
    if not scanner_running:
        return False, None
    
    # First try the API endpoint which should be most reliable
    url = "http://" + ip + ":" + str(p) + "/api/tags"
    try:
        r = requests.get(url, timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None))
        if r.status_code == 200:
            try:
                d = r.json()
                if "models" in d and type(d["models"]) == list:
                    return True, d
            except:
                pass
                
        # If API check fails, try checking for the "ollama is running" text on root endpoint
        # This is shown on Ollama's default landing page
        root_url = "http://" + ip + ":" + str(p) + "/"
        try:
            root_response = requests.get(root_url, timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None))
            if "ollama is running" in root_response.text.lower():
                # Found the Ollama landing page, but we don't have model info
                return True, {"models": []}
        except:
            pass
            
        return False, None
    except requests.exceptions.Timeout:
        if VERBOSE:
            print(f"[VERBOSE] Connection timeout ({timeout}s) for {ip}:{p}")
        return False, None
    except requests.exceptions.ConnectionError:
        if VERBOSE:
            print(f"[VERBOSE] Connection error for {ip}:{p}")
        return False, None
    except Exception as e:
        if VERBOSE:
            print(f"[VERBOSE] Error checking {ip}:{p}: {str(e)}")
        return False, None

def verifyEndpoint(endpointId, is_valid=None, preserve_verified=True):
    """Verify an endpoint and update its status in the database"""
    # Using Database methods directly - they manage connections internally
    
    # Get the endpoint information
    if DATABASE_TYPE == "postgres":
        query = 'SELECT ip, port FROM endpoints WHERE id = ?'
    else:
        query = 'SELECT ip, port FROM endpoints WHERE id = ?'
        
    endpoint = Database.fetch_one(query, (endpointId,))
    
    if not endpoint:
        print(f"Error: No endpoint found with ID {endpointId}")
        return False
    
    ip, port = endpoint
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # If is_valid is not provided, check if this is a valid Ollama server
    if is_valid is None:
        is_valid, model_data = isOllamaServer(ip, port)
    else:
        # Use the provided is_valid value and get model data
        _, model_data = isOllamaServer(ip, port)
    
    if is_valid:
        if DATABASE_TYPE == "postgres":
            # For PostgreSQL with the actual schema
            # First, check if this endpoint is already verified
            verify_query = 'SELECT verified FROM endpoints WHERE id = ?'
            current_verified = Database.fetch_one(verify_query, (endpointId,))
            
            # If preserve_verified is True and the endpoint is already verified, don't change its status
            if preserve_verified and current_verified and current_verified[0] == 1:
                print(f"Preserving verified status for endpoint {ip}:{port}")
                # Just update the verification date
                Database.execute('''
                UPDATE endpoints 
                SET verification_date = ? 
                WHERE id = ?
                ''', (now, endpointId))
            else:
                # Update endpoint as verified
                Database.execute('''
                UPDATE endpoints 
                SET verified = 1, verification_date = ? 
                WHERE id = ?
                ''', (now, endpointId))
                
            # Check if this endpoint is already in verified_endpoints
            verify_query = 'SELECT id FROM verified_endpoints WHERE endpoint_id = ?'
            verify_params = (endpointId,)
            verified_exists = Database.fetch_one(verify_query, verify_params) is not None
            
            if not verified_exists:
                # Add to verified_endpoints
                Database.execute('''
                INSERT INTO verified_endpoints (endpoint_id, verification_date)
                VALUES (?, ?)
                ''', (endpointId, now))
            else:
                # Update verification date
                Database.execute('''
                UPDATE verified_endpoints 
                SET verification_date = ? 
                WHERE endpoint_id = ?
                ''', (now, endpointId))
        else:
            # For SQLite, check if this endpoint is already verified
            verify_query = 'SELECT verified FROM endpoints WHERE id = ?'
            current_status = Database.fetch_one(verify_query, (endpointId,))
            
            # If preserve_verified is True and the endpoint is already verified, don't change its status
            if preserve_verified and current_status and current_status[0] == 1:
                print(f"Preserving verified status for endpoint {ip}:{port}")
                # Just update the verification date
                Database.execute('''
                UPDATE endpoints 
                SET verification_date = ? 
                WHERE id = ?
                ''', (now, endpointId))
            else:
                # Update endpoint as verified
                Database.execute('''
                UPDATE endpoints 
                SET verified = 1, verification_date = ? 
                WHERE id = ?
                ''', (now, endpointId))
                
                # Check if this endpoint is already in verified_endpoints
                verify_query = 'SELECT id FROM verified_endpoints WHERE endpoint_id = ?'
                verify_params = (endpointId,)
                verified_exists = Database.fetch_one(verify_query, verify_params) is not None
                
                if not verified_exists:
                    # Add to verified_endpoints
                    Database.execute('''
                    INSERT INTO verified_endpoints (endpoint_id, verification_date)
                    VALUES (?, ?)
                    ''', (endpointId, now))
                else:
                    # Update verification date
                    Database.execute('''
                    UPDATE verified_endpoints 
                    SET verification_date = ? 
                    WHERE endpoint_id = ?
                    ''', (now, endpointId))
        
        # Now add the models if they were found
        if model_data and "models" in model_data:
            for model in model_data["models"]:
                # Extract model information
                name = model.get("name", "Unknown")
                size = model.get("size", 0)
                sizeMb = size / (1024 * 1024) if size else 0
                
                details = model.get("details", {})
                parameter_size = details.get("parameter_size", "Unknown")
                quantization_level = details.get("quantization_level", "Unknown")
                
                # Check if the model already exists for this endpoint
                model_exists_query = 'SELECT id FROM models WHERE endpoint_id = ? AND name = ?'
                model_exists = Database.fetch_one(model_exists_query, (endpointId, name)) is not None
                
                if model_exists:
                    # Update existing model
                    Database.execute('''
                    UPDATE models 
                    SET parameter_size = ?, quantization_level = ?, size_mb = ?
                    WHERE endpoint_id = ? AND name = ?
                    ''', (parameter_size, quantization_level, sizeMb, endpointId, name))
                else:
                    # Add new model
                    Database.execute('''
                    INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (endpointId, name, parameter_size, quantization_level, sizeMb))
            
            print(f"Added/updated {len(model_data['models'])} models for endpoint {ip}:{port}")
        
        return True
    else:
        # If not valid, mark as not verified (verified = 0)
        if DATABASE_TYPE == "postgres":
            # For PostgreSQL with the actual schema, set verified = 0
            Database.execute('''
            UPDATE endpoints 
            SET verified = 0
            WHERE id = ?
            ''', (endpointId,))
            
            # Also remove from verified_endpoints if it exists
            Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = ?', (endpointId,))
        else:
            # For SQLite, set verified = 0
            Database.execute('''
            UPDATE endpoints 
            SET verified = 0
            WHERE id = ?
            ''', (endpointId,))
            
            # Also remove from verified_endpoints if it exists
            Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = ?', (endpointId,))
        
        print(f"Marked endpoint {ip}:{port} as not verified")
        return False

def isDuplicateServer(ip, port):
    """Check if a server already exists in the database"""
    if DATABASE_TYPE == "postgres":
        result = Database.fetch_one('SELECT id FROM servers WHERE ip = ? AND port = ?', (ip, port))
    else:
        result = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, port))
    return result is not None

def saveStuffToDb(ip, p, modelData, status="scanned", preserve_verified=True):
    """
    Save server and model data to database with duplicate checking
    
    Args:
        ip (str): IP address of the server
        p (int): Port number
        modelData (dict): Model data from the server
        status (str): Status to assign to new endpoints (default: 'scanned')
        preserve_verified (bool): Whether to preserve verified status for existing endpoints
    """
    # Use lock to ensure thread safety
    with db_lock:
        # Check if this server already exists
        is_duplicate = isDuplicateServer(ip, p)
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if is_duplicate:
            if preserve_verified:
                # Update existing endpoint with new scan date but preserve verified status
                if DATABASE_TYPE == "postgres":
                    # For PostgreSQL with the actual schema, preserve 'verified' integer field
                    Database.execute('''
                    UPDATE endpoints 
                    SET scan_date = ?
                    WHERE ip = ? AND port = ?
                    ''', (now, ip, p))
                else:
                    # For SQLite, preserve verified=1
                    Database.execute('''
                    UPDATE endpoints 
                    SET scan_date = ?,
                        verified = CASE WHEN verified = 1 THEN verified ELSE ? END
                    WHERE ip = ? AND port = ?
                    ''', (now, 1 if status == "verified" else 0, ip, p))
            else:
                # Update existing endpoint with new status and scan date
                if DATABASE_TYPE == "postgres":
                    # For PostgreSQL with the actual schema, update verified field based on status
                    verified_value = 1 if status == "verified" else 0
                    Database.execute('''
                    UPDATE endpoints 
                    SET scan_date = ?, verified = ? 
                    WHERE ip = ? AND port = ?
                    ''', (now, verified_value, ip, p))
                else:
                    # For SQLite, convert status to verified field
                    verified = 1 if status == "verified" else 0
                    Database.execute('''
                    UPDATE endpoints 
                    SET scan_date = ?, verified = ? 
                    WHERE ip = ? AND port = ?
                    ''', (now, verified, ip, p))
            
            # Get the endpoint ID
            if DATABASE_TYPE == "postgres":
                endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, p))
            else:
                endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, p))
                
            if endpoint_row:
                endpointId = endpoint_row[0]
            else:
                return
        else:
            # Insert new endpoint with specified status
            if DATABASE_TYPE == "postgres":
                # For PostgreSQL with the actual schema, use verified field
                verified_value = 1 if status == "verified" else 0
                result = Database.execute('''
                INSERT INTO endpoints (ip, port, scan_date, verified) 
                VALUES (?, ?, ?, ?)
                ''', (ip, p, now, verified_value))
                
                # Get the newly inserted ID
                endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, p))
                endpointId = endpoint_row[0] if endpoint_row else None
            else:
                # For SQLite, convert status to verified field
                verified = 1 if status == "verified" else 0
                result = Database.execute('''
                INSERT INTO endpoints (ip, port, scan_date, verified) 
                VALUES (?, ?, ?, ?)
                ''', (ip, p, now, verified))
                
                # SQLite can use cursor.lastrowid
                endpointId = result.lastrowid
        
        # Save models - this will be done in the verification step now
        # We're not adding models for unverified endpoints
        
        return is_duplicate

def removeDuplicates():
    """Remove duplicate endpoints from the database"""
    # Find duplicate IPs/ports with different IDs
    if DATABASE_TYPE == "postgres":
        dupes = Database.fetch_all("""
            SELECT ip, port, COUNT(*), STRING_AGG(id::text, ',') as ids
            FROM endpoints
            GROUP BY ip, port
            HAVING COUNT(*) > 1
        """)
    else:  # SQLite
        dupes = Database.fetch_all("""
            SELECT ip, port, COUNT(*), GROUP_CONCAT(id) as ids
            FROM endpoints
            GROUP BY ip, port
            HAVING COUNT(*) > 1
        """)
    
    if dupes:
        logging.info(f"Found {len(dupes)} duplicate endpoint records")
        
        for dupe in dupes:
            ip, port, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logging.info(f"Keeping {ip}:{port} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM endpoints WHERE id = ?", (remove_id,))
    
    # Find duplicate models (same endpoint_id/name with different IDs)
    if DATABASE_TYPE == "postgres":
        model_dupes = Database.fetch_all("""
            SELECT endpoint_id, name, COUNT(*), STRING_AGG(id::text, ',') as ids
            FROM models
            GROUP BY endpoint_id, name
            HAVING COUNT(*) > 1
        """)
    else:  # SQLite
        model_dupes = Database.fetch_all("""
            SELECT endpoint_id, name, COUNT(*), GROUP_CONCAT(id) as ids
            FROM models
            GROUP BY endpoint_id, name
            HAVING COUNT(*) > 1
        """)
    
    if model_dupes:
        logging.info(f"Found {len(model_dupes)} duplicate model records")
        
        for dupe in model_dupes:
            endpoint_id, name, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logging.info(f"Keeping model {name} for endpoint {endpoint_id} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM models WHERE id = ?", (remove_id,))
    
    # Find duplicate verified_endpoints (same endpoint_id with different IDs)
    if DATABASE_TYPE == "postgres":
        ve_dupes = Database.fetch_all("""
            SELECT endpoint_id, COUNT(*), STRING_AGG(id::text, ',') as ids
            FROM verified_endpoints
            GROUP BY endpoint_id
            HAVING COUNT(*) > 1
        """)
    else:  # SQLite
        ve_dupes = Database.fetch_all("""
            SELECT endpoint_id, COUNT(*), GROUP_CONCAT(id) as ids
            FROM verified_endpoints
            GROUP BY endpoint_id
            HAVING COUNT(*) > 1
        """)
    
    if ve_dupes:
        logging.info(f"Found {len(ve_dupes)} duplicate verified_endpoints records")
        
        for dupe in ve_dupes:
            endpoint_id, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logging.info(f"Keeping verified_endpoint for endpoint {endpoint_id} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM verified_endpoints WHERE id = ?", (remove_id,))

    print("Database cleanup complete!")

def process_server(result, total_count, current_index, stats, status="scanned", preserve_verified=True):
    """
    Process a single server result with multiple port checks
    
    Args:
        result (dict): Server result data
        total_count (int): Total count of servers to process
        current_index (int): Current index in the server list
        stats (dict): Statistics dictionary
        status (str): Status to assign to discovered endpoints
        preserve_verified (bool): Whether to preserve verified status for existing endpoints
    """
    ip = result['ip_str']
    
    if 'port' in result:
        port = result['port']
    else:
        port = 11434  # default Ollama port
    
    percent_done = (current_index + 1) / total_count * 100
    print(f"[{current_index+1}/{total_count}] ({round(percent_done, 1)}%) Trying {ip}:{port}...")
    
    try:
        # Construct a list of ports to check
        # Start with the detected port, then additional ports from result, then common ports
        ports_to_check = [port]
        
        # Add additional ports from the search results if available
        if 'additional_ports' in result:
            for additional_port in result['additional_ports']:
                if additional_port not in ports_to_check:
                    ports_to_check.append(additional_port)
        
        # Add common Ollama ports if not already in the list
        common_ports = [11434, 8000, 8001, 11435, 11436, 3000, 8080, 8888]
        for common_port in common_ports:
            if common_port not in ports_to_check:
                ports_to_check.append(common_port)
        
        # Check for dynamically assigned ports in common ranges (keep this reasonable)
        # UPnP often uses ports in these ranges
        dynamic_port_ranges = [
            (49152, 49252),  # Common UPnP high port range (checking 100 ports)
            (1024, 1124)     # Lower privileged ports (checking 100 ports)
        ]
        
        # Check for Ollama on all ports in our list
        found = False
        for test_port in ports_to_check:
            # Check for termination
            if not scanner_running:
                print(f"Scanner termination requested, stopping scan of {ip}")
                break
                
            # Check if scanner is paused and wait if it is
            while not scanner_paused.is_set() and scanner_running:
                time.sleep(0.5)  # Sleep briefly while paused
                
            if not scanner_running:  # Check again after potential pause
                print(f"Scanner termination requested, stopping scan of {ip}")
                break
            
            # First, add or update the endpoint in the database
            # This adds it with the specified status
            is_duplicate = saveStuffToDb(ip, test_port, None, status=status, preserve_verified=preserve_verified)
            
            # Now verify if this is a valid Ollama server
            works, data = isOllamaServer(ip, test_port)
            if works == True:
                with stats['lock']:
                    stats['valid'] += 1
                
                # Get the endpoint ID from the database
                if DATABASE_TYPE == "postgres":
                    endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, test_port))
                else:
                    endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, test_port))
                
                if endpoint_row:
                    endpoint_id = endpoint_row[0]
                    # Mark the endpoint as verified and add model data
                    verified = verifyEndpoint(endpoint_id, works, preserve_verified)
                    
                    if verified:
                        # Count the models
                        if data and "models" in data:
                            num_models = len(data["models"])
                        else:
                            num_models = 0
                        
                        with stats['lock']:
                            if is_duplicate:
                                stats['duplicates'] += 1
                                print(f"UPDATE! Ollama at {ip}:{test_port} with {num_models} models (already in DB)")
                            else:
                                print(f"NEW! Found Ollama at {ip}:{test_port} with {num_models} models")
                        
                        found = True
                        break  # exit the loop once we find a working Ollama instance
                
            else:
                print(f"INVALID - No Ollama found at {ip}:{test_port}")
        
        # If we haven't found Ollama yet and the IP is promising, check the dynamic port ranges
        # This is a more intensive scan, so we only do it for IPs that matched other criteria
        if not found and 'promising_ip' in result and result['promising_ip'] and not args.no_dynamic_ports:
            print(f"Checking dynamic port ranges for {ip} as it seems promising...")
            
            # Record start time to enforce global timeout for dynamic port scanning
            dynamic_scan_start = time.time()
            dynamic_port_timeout = args.dynamic_port_timeout
            dynamic_port_limit = args.dynamic_port_limit
            ports_scanned = 0
            
            # Reduce the number of ports in each range based on the limit
            for start_port, end_port in dynamic_port_ranges:
                # Check for termination
                if not scanner_running:
                    print(f"Scanner termination requested, stopping scan of {ip}")
                    break
                    
                # Check if scanner is paused and wait if it is
                while not scanner_paused.is_set() and scanner_running:
                    time.sleep(0.5)  # Sleep briefly while paused
                    
                if not scanner_running:  # Check again after potential pause
                    print(f"Scanner termination requested, stopping scan of {ip}")
                    break
                
                # Calculate how many ports to check (limited by dynamic_port_limit)
                original_range = end_port - start_port
                skip_factor = max(1, original_range // dynamic_port_limit)
                
                print(f"Scanning ~{min(dynamic_port_limit, original_range)} ports in range {start_port}-{end_port} (sampling every {skip_factor} ports)")
                
                # Scan a subset of ports in this range, with a fixed interval
                for dynamic_port in range(start_port, end_port, skip_factor):
                    # Check if we've exceeded the global timeout for dynamic port scanning
                    if time.time() - dynamic_scan_start > dynamic_port_timeout:
                        print(f"Dynamic port scan timeout ({dynamic_port_timeout}s) reached for {ip}, stopping scan")
                        break
                    
                    # Check for termination
                    if not scanner_running:
                        print(f"Scanner termination requested, stopping scan of {ip}")
                        break
                        
                    # Check if scanner is paused and wait if it is
                    while not scanner_paused.is_set() and scanner_running:
                        time.sleep(0.5)  # Sleep briefly while paused
                        
                    if not scanner_running:  # Check again after potential pause
                        print(f"Scanner termination requested, stopping scan of {ip}")
                        break
                        
                    ports_scanned += 1
                    
                    if VERBOSE:
                        print(f"[VERBOSE] Checking port {dynamic_port} ({ports_scanned} total scanned)")
                    
                    # First add the endpoint as unverified
                    is_duplicate = saveStuffToDb(ip, dynamic_port, None, status=status, preserve_verified=preserve_verified)
                    
                    try:
                        # Use a shorter timeout for dynamic port scanning
                        works, data = isOllamaServer(ip, dynamic_port, timeout=min(3, timeout))
                        if works == True:
                            with stats['lock']:
                                stats['valid'] += 1
                            
                            # Get the endpoint ID
                            if DATABASE_TYPE == "postgres":
                                endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, dynamic_port))
                            else:
                                endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, dynamic_port))
                            
                            if endpoint_row:
                                endpoint_id = endpoint_row[0]
                                # Mark as verified and add model data
                                verified = verifyEndpoint(endpoint_id, works, preserve_verified)
                                
                                if verified:
                                    # Count the models
                                    if data and "models" in data:
                                        num_models = len(data["models"])
                                    else:
                                        num_models = 0
                                    
                                    with stats['lock']:
                                        if is_duplicate:
                                            stats['duplicates'] += 1
                                            print(f"UPDATE! Ollama at {ip}:{dynamic_port} with {num_models} models (already in DB)")
                                        else:
                                            print(f"NEW! Found Ollama at {ip}:{dynamic_port} with {num_models} models")
                                    
                                    found = True
                                    break  # exit the loop
                            
                    except Exception as e:
                        if VERBOSE:
                            print(f"[VERBOSE] Error checking {ip}:{dynamic_port}: {str(e)}")
                        continue  # Continue with next port on error
                
                # If we've found an Ollama instance or hit the timeout, exit all loops
                if found or (time.time() - dynamic_scan_start > dynamic_port_timeout):
                    break
            
            # Log how long the dynamic scan took if we performed one
            if ports_scanned > 0:
                dynamic_scan_duration = time.time() - dynamic_scan_start
                print(f"Dynamic port scan for {ip} checked {ports_scanned} ports in {dynamic_scan_duration:.1f}s")
        elif 'promising_ip' in result and result['promising_ip'] and args.no_dynamic_ports:
            print(f"Skipping dynamic port scan for {ip} (--no-dynamic-ports enabled)")
    
    except Exception as e:
        with stats['lock']:
            stats['errors'] += 1
        print(f"ERROR scanning {ip}: {str(e)}")

def search_censys():
    """Search Censys for potential Ollama instances"""
    if not censys_available:
        print("Censys module not installed. Skipping Censys search.")
        return []
    
    if not CENSYS_API_ID or not CENSYS_API_SECRET:
        print("Censys API credentials not configured. Skipping Censys search.")
        return []
    
    try:
        # Initialize the Censys client
        h = CensysHosts(api_id=CENSYS_API_ID, api_secret=CENSYS_API_SECRET)
        
        print("Searching Censys for Ollama instances...")
        
        # Search for potential Ollama instances
        # These queries target typical HTTP signatures that might be associated with Ollama
        # We'll try multiple queries to increase our chance of finding instances
        
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
        
    except Exception as e:
        print(f"Error during Censys search: {str(e)}")
        return []

def parse_masscan_results(file_path, default_port=11434):
    """
    Parse masscan output file in grepable format
    
    Args:
        file_path: Path to masscan output file in grepable format (-oG)
        default_port: Default port to use if not specified
        
    Returns:
        list: List of IP addresses (strings)
    """
    results = []
    line_pattern = re.compile(r'Host:\s+(\d+\.\d+\.\d+\.\d+)[^\d]+Ports:\s+(\d+)/open')
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Skip comment lines and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Match the line against the pattern
                match = line_pattern.search(line)
                if match:
                    ip = match.group(1)
                    # Just store the IP address, as verify_instance expects only IPs
                    results.append(ip)
                    
        print(f"Parsed {len(results)} potential Ollama instances from masscan output")
        return results
        
    except Exception as e:
        print(f"Error parsing masscan output: {str(e)}")
        return []

def search_shodan():
    """Search Shodan for potential Ollama instances"""
    if not shodan_client:
        print("Shodan API key not configured. Skipping Shodan search.")
        return []
    
    print("Looking for Ollama instances on Shodan...")
    print("Searching Shodan...")
    
    # Define search queries to find all possible Ollama instances
    search_queries = [
        'product:Ollama', 
        'port:11434'
    ]
    
    shodan_results = []
    
    for query in search_queries:
        print(f"Searching Shodan for: '{query}'")
        pg = 1
        
        while True:
            try:
                print(f"Fetching page {pg} for query '{query}'...")
                res = shodan_client.search(query, page=pg, limit=maxResults)
                
                # Validate response structure
                if not isinstance(res, dict):
                    print(f"Warning: Unexpected response type from Shodan for query '{query}' page {pg}")
                    break
                    
                if 'matches' not in res:
                    print(f"Warning: No 'matches' field in Shodan response for query '{query}' page {pg}")
                    break
                    
                matches = res.get('matches', [])
                if not matches:
                    print(f"No more results found for query '{query}'.")
                    break
                
                # Process each match with validation
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                        
                    # Ensure required fields exist
                    ip_str = match.get('ip_str')
                    if not ip_str:
                        continue
                        
                    # Check if this result is already in our list (by IP)
                    if not any(r.get('ip_str') == ip_str for r in shodan_results):
                        # Add additional fields that might be useful
                        processed_match = {
                            'ip_str': ip_str,
                            'port': match.get('port', 11434),  # Default to common Ollama port
                            'promising_ip': True,  # Mark all Shodan results as promising
                            'additional_ports': []  # Initialize empty list for additional ports
                        }
                        
                        # Extract additional ports if available
                        if 'ports' in match:
                            try:
                                processed_match['additional_ports'] = [
                                    p for p in match['ports'] 
                                    if isinstance(p, int) and p != processed_match['port']
                                ]
                            except Exception:
                                pass
                        
                        shodan_results.append(processed_match)
                
                print(f"Found {len(matches)} results on page {pg} for query '{query}' (Total unique: {len(shodan_results)})")
                
                # Check if we've reached the total results
                total = res.get('total', 0)
                if pg * maxResults >= total:
                    print(f"Reached end of results for query '{query}'.")
                    break
                
                time.sleep(1)  # Don't overload shodan API
                
                pg = pg + 1
                
                if pg > 20:  # Don't get more than 20 pages per query
                    print(f"Reached maximum page limit (20) for query '{query}'.")
                    break
                    
            except shodan.APIError as e:
                print(f"Shodan API error for query '{query}' page {pg}: {str(e)}")
                break
            except json.JSONDecodeError as e:
                print(f"JSON parsing error for query '{query}' page {pg}: {str(e)}")
                # Try to continue with next page despite the error
                pg = pg + 1
                continue
            except Exception as e:
                print(f"Error during Shodan search for query '{query}' page {pg}: {str(e)}")
                break  # Continue with what we have
    
    print(f"Total unique potential Ollama instances found on Shodan: {len(shodan_results)}")
    
    if len(shodan_results) > 1500:
        print(f"Limiting results to 1500 (out of {len(shodan_results)} found)")
        shodan_results = shodan_results[:1500]
        
    return shodan_results

def run_masscan(args, target_ips=None, port=11434, rate=10000, db_path=None):
    """Run masscan to find Ollama instances or process an existing masscan output file"""
    # Set global database file
    global database_file
    database_file = db_path
    
    # Check if masscan is installed
    if not args.input and subprocess.run(['which', 'masscan'], capture_output=True).returncode != 0:
        print("Error: masscan command not found. Please install masscan.")
        return -1
    
    # Generate output file
    input_file = None
    
    if args.input:
        # Use provided input file
        if not os.path.exists(args.input):
            print(f"Error: Input file {args.input} does not exist")
            return -1
        
        print(f"Using existing masscan results file: {args.input}")
        input_file = args.input
    else:
        # Run masscan
        # Check if target_ips list is provided
        if not target_ips:
            print("Error: No target IP ranges specified for masscan")
            return -1
        
        # Create masscan command
        cmd = [
            'masscan',
            '-p', str(port),
            '--rate', str(rate),
            '-oG', 'res.txt'
        ]
        
        # Add all target IPs to the command
        for ip_range in target_ips:
            cmd.append(ip_range)
        
        # Check if running as root
        if os.geteuid() != 0:
            # Not running as root, warn the user
            print("Warning: masscan requires root privileges")
            print("Please run the following command with sudo:")
            print(' '.join(cmd))
            return -1
        else:
            # Already running as root, proceed with scan
            try:
                if VERBOSE:
                    print("[VERBOSE] Executing masscan, this may take some time...")
                subprocess.run(cmd, check=True)
                print("[SUCCESS] Masscan completed successfully")
                input_file = "res.txt"
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Error running masscan: {e}")
                return 0
            except FileNotFoundError:
                print("[ERROR] masscan command not found. Please install masscan.")
                return 0
    
    # Process masscan results
    if not input_file:
        print("Error: No input file specified")
        return 0
    
    # Parse the masscan results
    ip_list = parse_masscan_results(input_file, port)
    
    if not ip_list:
        print("No potential Ollama instances found in masscan results")
        return 0
    
    print(f"Found {len(ip_list)} potential Ollama instances in masscan results")
    
    # Apply limit if specified
    if args.limit > 0 and len(ip_list) > args.limit:
        print(f"Limiting results to {args.limit} (out of {len(ip_list)})")
        ip_list = ip_list[:args.limit]
    
    # Convert IPs to format expected by process_server
    results = []
    for ip in ip_list:
        results.append({
            'ip_str': ip,
            'port': port
        })
    
    # Set up statistics
    stats = {
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'duplicates': 0,
        'lock': threading.Lock()
    }
    
    # Process each result
    for i, result in enumerate(results):
        process_server(result, len(results), i, stats, status=args.status, preserve_verified=args.preserve_verified)
    
    # Show stats
    print("\nMasscan processing complete")
    print(f"Valid Ollama instances: {stats['valid']}")
    print(f"Invalid endpoints: {stats['invalid']}")
    print(f"Errors: {stats['errors']}")
    print(f"Duplicates: {stats['duplicates']}")
    
    return stats['valid']

def run_shodan(args, db_path):
    """Run Shodan search for Ollama instances"""
    # Set global database file
    global database_file
    database_file = db_path
    
    # Get search results from Shodan
    results = search_shodan()
    
    if not results:
        print("No results found from Shodan search")
        return 0
    
    # Set up statistics
    stats = {
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'duplicates': 0,
        'lock': threading.Lock()
    }
    
    # Process results
    print(f"Processing {len(results)} results from Shodan search")
    
    # Apply limit if specified
    if args.limit > 0 and len(results) > args.limit:
        print(f"Limiting results to {args.limit} (out of {len(results)})")
        results = results[:args.limit]
    
    # Process each result
    for i, result in enumerate(results):
        if not scanner_running:
            print("Scanner termination requested, stopping processing")
            break
                
        # Check if scanner is paused and wait if it is
        while not scanner_paused.is_set() and scanner_running:
            time.sleep(0.5)  # Sleep briefly while paused
                
        if not scanner_running:  # Check again after potential pause
            print("Scanner termination requested, stopping processing")
            break
                
        process_server(result, len(results), i, stats, status=args.status, preserve_verified=args.preserve_verified)
    
    # Show stats
    print("\nShodan search complete")
    print(f"Valid Ollama instances: {stats['valid']}")
    print(f"Invalid endpoints: {stats['invalid']}")
    print(f"Errors: {stats['errors']}")
    print(f"Duplicates: {stats['duplicates']}")
    
    return stats['valid']

def run_censys(args, db_path):
    """Run Censys search for Ollama instances"""
    # Set global database file
    global database_file
    database_file = db_path
    
    # Check if Censys is installed
    if not censys_available:
        print("Censys module not installed. Install with: pip install censys")
        return 0
    
    # Check Censys API key
    censys_api_key = os.environ.get("CENSYS_API_KEY")
    if not censys_api_key:
        print("CENSYS_API_KEY not set in environment")
        return 0
    
    # Get search results from Censys
    results = search_censys()
    
    if not results:
        print("No results found from Censys search")
        return 0
    
    # Set up statistics
    stats = {
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'duplicates': 0,
        'lock': threading.Lock()
    }
    
    # Process results
    print(f"Processing {len(results)} results from Censys search")
    
    # Apply limit if specified
    if args.limit > 0 and len(results) > args.limit:
        print(f"Limiting results to {args.limit} (out of {len(results)})")
        results = results[:args.limit]
    
    # Process each result
    for i, result in enumerate(results):
        if not scanner_running:
            print("Scanner termination requested, stopping processing")
            break
                
        # Check if scanner is paused and wait if it is
        while not scanner_paused.is_set() and scanner_running:
            time.sleep(0.5)  # Sleep briefly while paused
                
        if not scanner_running:  # Check again after potential pause
            print("Scanner termination requested, stopping processing")
            break
                
        process_server(result, len(results), i, stats, status=args.status, preserve_verified=args.preserve_verified)
    
    # Show stats
    print("\nCensys search complete")
    print(f"Valid Ollama instances: {stats['valid']}")
    print(f"Invalid endpoints: {stats['invalid']}")
    print(f"Errors: {stats['errors']}")
    print(f"Duplicates: {stats['duplicates']}")
    
    return stats['valid']

def verify_instance(ip, db_path, timeout=5, result_queue=None, status="scanned", preserve_verified=True):
    """
    Verify if an IP is a valid Ollama instance and collect model info
    
    Args:
        ip (str): IP address to verify
        db_path (str): Path to SQLite database
        timeout (int): Request timeout in seconds
        result_queue (Queue): Optional queue to put results into (for multiprocessing)
        status (str): Status to assign to verified instances (default: 'scanned')
        preserve_verified (bool): Whether to preserve verified status for existing endpoints
    
    Returns:
        dict: Result info including verification status and model data if successful
    """
    
    global database_file
    
    # Set up temporary database file for multiprocessing if needed
    if db_path:
        database_file = db_path
        
    try:
        # Initialize result dictionary
        result = {
            'ip': ip,
            'port': 11434,
            'verified': False,
            'reason': 'Not verified',
            'model_data': None
        }
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if endpoint already exists and get its status
        if DATABASE_TYPE == "postgres":
            endpoint_row = Database.fetch_one('SELECT id, status FROM servers WHERE ip = ? AND port = ?', (ip, 11434))
        else:
            endpoint_row = Database.fetch_one('SELECT id, verified FROM endpoints WHERE ip = ? AND port = ?', (ip, 11434))
        
        if endpoint_row:
            endpoint_id = endpoint_row[0]
            if DATABASE_TYPE == "postgres":
                current_status = endpoint_row[1] if len(endpoint_row) > 1 else None
                
                if preserve_verified and current_status == 'verified':
                    # Update scan date but preserve verified status
                    Database.execute('UPDATE servers SET scan_date = ? WHERE id = ?', (now, endpoint_id))
                    
                    if VERBOSE:
                        print(f"[VERBOSE] Updating existing verified endpoint {ip}:11434 (ID {endpoint_id})")
                else:
                    # Update scan date and status
                    Database.execute('UPDATE servers SET scan_date = ?, status = ? WHERE id = ?', 
                                 (now, status, endpoint_id))
                    
                    if VERBOSE:
                        print(f"[VERBOSE] Updating existing endpoint {ip}:11434 (ID {endpoint_id}) with status '{status}'")
            else:
                # For SQLite
                current_verified = endpoint_row[1] if len(endpoint_row) > 1 else 0
                
                if preserve_verified and current_verified == 1:
                    # Update scan date but preserve verified status
                    Database.execute('UPDATE endpoints SET scan_date = ? WHERE id = ?', (now, endpoint_id))
                    
                    if VERBOSE:
                        print(f"[VERBOSE] Updating existing verified endpoint {ip}:11434 (ID {endpoint_id})")
                else:
                    # Update scan date and verified status based on input status
                    verified = 1 if status == "verified" else 0
                    Database.execute('UPDATE endpoints SET scan_date = ?, verified = ? WHERE id = ?', 
                                 (now, verified, endpoint_id))
                    
                    if VERBOSE:
                        print(f"[VERBOSE] Updating existing endpoint {ip}:11434 (ID {endpoint_id}) with status '{status}'")
        else:
            # Insert with specified status
            if DATABASE_TYPE == "postgres":
                # For PostgreSQL, use status field
                result_db = Database.execute(
                    'INSERT INTO servers (ip, port, scan_date, status) VALUES (?, ?, ?, ?)',
                    (ip, 11434, now, status)
                )
                
                # Get the newly inserted ID for PostgreSQL
                endpoint_row = Database.fetch_one('SELECT id FROM servers WHERE ip = ? AND port = ?', (ip, 11434))
                endpoint_id = endpoint_row[0] if endpoint_row else None
            else:
                # For SQLite, convert status to verified field
                verified = 1 if status == "verified" else 0
                result_db = Database.execute(
                    'INSERT INTO endpoints (ip, port, scan_date, verified) VALUES (?, ?, ?, ?)',
                    (ip, 11434, now, verified)
                )
                
                # SQLite can use cursor.lastrowid
                endpoint_id = result_db.lastrowid
                
            if VERBOSE:
                print(f"[VERBOSE] Added new endpoint {ip}:11434 (ID {endpoint_id}) with status '{status}'")
                
        # Check /api/tags endpoint
        tags_url = f"http://{ip}:11434/api/tags"
        if VERBOSE:
            print(f"[VERBOSE] Trying endpoint: {tags_url}")
        
        verification_start = datetime.now()
        tags_response = requests.get(tags_url, timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None))
        verification_time = (datetime.now() - verification_start).total_seconds()
        
        if tags_response.status_code == 200:
            try:
                tags_data = tags_response.json()
                
                # Get model details
                model_data = {
                    "models": []
                }
                
                # Extract model information
                for model in tags_data.get("models", []):
                    model_data["models"].append(model)
                
                result["verified"] = True
                result["reason"] = "Ollama API verified"
                result["verification_time"] = verification_time
                result["model_data"] = model_data
                result["model_count"] = len(model_data["models"])
                
                # Process system info if available
                if tags_response.headers.get('Server'):
                    result["server"] = tags_response.headers.get('Server')
                
                # Mark the endpoint as verified
                if endpoint_id:
                    # Use the verifyEndpoint function which handles both database types
                    verifyEndpoint(endpoint_id, True, preserve_verified)
                    
                if VERBOSE:
                    print(f"[VERBOSE] Verified Ollama API at {ip}:11434 in {verification_time:.2f}s with {len(model_data['models'])} models")
                    if len(model_data["models"]) > 0:
                        for model in model_data["models"]:
                            print(f"[VERBOSE]   - {model.get('name', 'Unknown')}")
                
            except json.JSONDecodeError:
                result["reason"] = "Invalid JSON response"
                if VERBOSE:
                    print(f"[VERBOSE] Invalid JSON from {ip}:11434")
        else:
            result["reason"] = f"HTTP {tags_response.status_code}"
            if VERBOSE:
                print(f"[VERBOSE] HTTP error {tags_response.status_code} from {ip}:11434")
    
    except requests.exceptions.Timeout:
        result = {
            'ip': ip,
            'port': 11434,
            'verified': False,
            'reason': f"Connection timeout (>{timeout}s)"
        }
        if VERBOSE:
            print(f"[VERBOSE] Connection timeout for {ip}:11434")
    
    except requests.exceptions.ConnectionError:
        result = {
            'ip': ip,
            'port': 11434,
            'verified': False,
            'reason': "Connection refused"
        }
        if VERBOSE:
            print(f"[VERBOSE] Connection refused for {ip}:11434")
    
    except Exception as e:
        result = {
            'ip': ip,
            'port': 11434,
            'verified': False,
            'reason': str(e)
        }
        if VERBOSE:
            print(f"[VERBOSE] Error verifying {ip}:11434: {str(e)}")
    
    # Put result in queue if provided (for multiprocessing)
    if result_queue:
        result_queue.put(result)
    
    return result

def add_server_to_db(ip, models_data, ps_data, db_path):
    """Add a server and its models to the database"""
    try:
        # Get current timestamp
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Find the endpoint ID in our database
        endpoint = Database.fetch_one('SELECT id FROM endpoints WHERE ip = ? AND port = ?', (ip, 11434))
        if not endpoint:
            if VERBOSE:
                print(f"[ERROR] Endpoint {ip}:11434 not found in database, can't add models")
            return False
        
        endpoint_id = endpoint[0]
        
        # Update scan date and mark as verified
        Database.execute('UPDATE endpoints SET scan_date = ?, verified = 1, verification_date = ? WHERE id = ?', 
                      (now, now, endpoint_id))
        
        # Process models
        for model in models_data:
            # Ensure we're working with a valid model object
            if not isinstance(model, dict):
                if VERBOSE:
                    print(f"[WARNING] Invalid model data type: {type(model)}, skipping")
                continue
                
            # Extract model properties safely
            name = model.get("name", "Unknown")
            
            # Check if model exists for this endpoint
            model_query = 'SELECT id FROM models WHERE endpoint_id = ? AND name = ?'
            model_params = (endpoint_id, name)
            model_exists = Database.fetch_one(model_query, model_params) is not None
            
            # Process model details
            size = model.get("size", 0)
            size_mb = size / (1024 * 1024) if size else 0
            
            # Safely extract nested values
            details = model.get("details", {})
            if not isinstance(details, dict):
                details = {}
                
            param_size = details.get("parameter_size", "Unknown")
            quant_level = details.get("quantization_level", "Unknown")
            
            if model_exists:
                # Update existing model
                Database.execute(
                    '''UPDATE models 
                    SET parameter_size = ?, quantization_level = ?, size_mb = ?
                    WHERE endpoint_id = ? AND name = ?''',
                    (param_size, quant_level, size_mb, endpoint_id, name)
                )
            else:
                # Insert new model - ensure we're passing only scalar values
                Database.execute(
                    '''INSERT INTO models 
                    (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (?, ?, ?, ?, ?)''',
                    (endpoint_id, name, param_size, quant_level, size_mb)
                )
        
        return True
    except Exception as e:
        print(f"Error adding server to database: {e}")
        if VERBOSE:
            import traceback
            traceback

# Dynamic timeout calculation function
def calculate_dynamic_timeout(model_name="", prompt="", max_tokens=1000, timeout_flag=None):
    """
    Calculate a dynamic timeout based on model size, prompt length, and max tokens.
    
    Args:
        model_name (str): Name of the model, used to estimate size (e.g., "deepseek-r1:70b")
        prompt (str): The prompt text, longer prompts need more time
        max_tokens (int): Maximum tokens to generate, more tokens need more time
        timeout_flag (int, optional): If provided, overrides the calculated timeout.
                                     Use 0 for no timeout (None or inf).
    
    Returns:
        float or None: Timeout in seconds, or None for no timeout
    """
    # If timeout_flag is explicitly set to 0, return None for no timeout
    if timeout_flag == 0:
        return None
    
    # If timeout_flag is provided and not 0, use that value
    if timeout_flag is not None:
        return float(timeout_flag)
    
    # Base timeout value
    base_timeout = 180  # 3 minutes
    
    # Factor in model size
    param_factor = 1.0
    model_name_lower = model_name.lower()
    
    # Extract parameter size from model name (e.g., "13b" from "deepseek-r1:13b")
    size_match = re.search(r'(\d+)b', model_name_lower)
    if size_match:
        try:
            size_num = float(size_match.group(1))
            # Special handling for very large models (50B+)
            if size_num >= 50:
                param_factor = 2.5 + (size_num / 20)  # Much more time for 70B models
            else:
                param_factor = 1.0 + (size_num / 10)  # Standard scaling for smaller models
        except ValueError:
            # If we can't parse it, use default factor
            pass
    elif "70b" in model_name_lower:
        param_factor = 6.0  # Special case for 70B models
    elif "14b" in model_name_lower or "13b" in model_name_lower:
        param_factor = 2.4  # Special case for 13-14B models
    elif "7b" in model_name_lower or "8b" in model_name_lower:
        param_factor = 1.7  # Special case for 7-8B models
    
    # Factor in prompt length
    prompt_length = len(prompt) if prompt else 0
    prompt_factor = 1.0 + (prompt_length / 1000)  # Add factor for each 1000 chars
    
    # Factor in max_tokens
    max_tokens = max(1, max_tokens)  # Ensure positive value
    token_factor = max(1.0, max_tokens / 1000)  # Add factor for each 1000 tokens
    
    # Calculate final timeout with minimum and maximum bounds
    final_timeout = max(60, min(1800, base_timeout * param_factor * prompt_factor * token_factor))
    
    return final_timeout
.print_exc()
        return False

def verify_instances(ip_list, db_path, num_threads=50, status="scanned", preserve_verified=True):
    """
    Verify a list of IP addresses for Ollama instances
    
    Args:
        ip_list (list): List of IP addresses to verify
        db_path (str): Path to database file (for SQLite)
        num_threads (int): Number of concurrent verification threads
        status (str): Status to assign to endpoints (default: 'scanned')
        preserve_verified (bool): Whether to preserve verified status for existing endpoints
    """
    print(f"[INFO] Verifying {len(ip_list)} potential Ollama instances using {num_threads} threads")
    
    # Create a queue to store the results
    result_queue = Queue()
    
    # Add a detailed statistics tracker with thread safety
    stats = {
        'completed': 0,
        'total': len(ip_list),
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'start_time': datetime.now(),
        'lock': threading.Lock()
    }
    
    # Create a callback function to update progress
    def update_progress(result):
        with stats['lock']:
            stats['completed'] += 1
            
            # Track result types
            if result == True:
                stats['valid'] += 1
            elif result == False:
                stats['invalid'] += 1
            else:  # None or exception
                stats['errors'] += 1
                
            percent = (stats['completed'] / stats['total']) * 100
            
            # Calculate elapsed and estimated time
            elapsed = datetime.now() - stats['start_time']
            elapsed_seconds = elapsed.total_seconds()
            
            if stats['completed'] > 0:
                per_item_seconds = elapsed_seconds / stats['completed']
                remaining_items = stats['total'] - stats['completed']
                eta_seconds = remaining_items * per_item_seconds
                eta = timedelta(seconds=int(eta_seconds))
            else:
                eta = timedelta(seconds=0)
            
            # Print progress update with more details
            if stats['completed'] % 10 == 0 or stats['completed'] == stats['total'] or VERBOSE:
                print(f"\n[PROGRESS] Verification: {stats['completed']}/{stats['total']} ({percent:.1f}%)")
                print(f"[STATS] Valid: {stats['valid']}, Invalid: {stats['invalid']}, Errors: {stats['errors']}")
                print(f"[TIME] Elapsed: {str(elapsed).split('.')[0]}, ETA: {str(eta).split('.')[0]}")
                
                # Print rate information
                if elapsed_seconds > 0:
                    verify_rate = stats['completed'] / elapsed_seconds
                    print(f"[RATE] {verify_rate:.2f} endpoints/second")
    
    if VERBOSE:
        print(f"[VERBOSE] Creating thread pool with {num_threads} workers")
    
    # Create a thread pool
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit the tasks
        futures = []
        for ip in ip_list:
            # Ensure ip is a string (handle both string IPs and dict-formatted results)
            ip_addr = ip if isinstance(ip, str) else ip.get('ip_str', '')
            if ip_addr:
                future = executor.submit(verify_instance, ip_addr, db_path, 5, result_queue, status=status, preserve_verified=preserve_verified)
                future.add_done_callback(lambda f: update_progress(f.result() if not f.exception() else None))
                futures.append(future)
        
        if VERBOSE:
            print(f"[VERBOSE] All verification tasks submitted, waiting for completion")
        
        # Wait for all tasks to complete
        for future in futures:
            try:
                future.result()
            except Exception as e:
                if VERBOSE:
                    print(f"[ERROR] Exception in verification thread: {str(e)}")
    
    # Get the results
    valid_count = stats['valid']
    
    # Calculate total time
    total_time = datetime.now() - stats['start_time']
    total_seconds = total_time.total_seconds()
    
    # Print final statistics summary
    print(f"\n[VERIFICATION SUMMARY]")
    print(f"Total endpoints checked: {stats['total']}")
    print(f"Valid Ollama instances: {stats['valid']} ({(stats['valid']/stats['total']*100):.1f}%)")
    print(f"Invalid endpoints: {stats['invalid']} ({(stats['invalid']/stats['total']*100):.1f}%)")
    print(f"Connection errors: {stats['errors']} ({(stats['errors']/stats['total']*100):.1f}%)")
    print(f"Total time: {str(total_time).split('.')[0]}")
    
    if total_seconds > 0:
        verify_rate = stats['total'] / total_seconds
        print(f"Average verification rate: {verify_rate:.2f} endpoints/second")
    
    return valid_count

def run_scan(args, db_path, target_ips=None):
    """Run scan based on specified method"""
    if VERBOSE:
        print(f"[VERBOSE] Starting scan with method: {args.method}")
        print(f"[VERBOSE] Status: {args.status}")
        print(f"[VERBOSE] Preserve verified: {args.preserve_verified}")
        if args.limit > 0:
            print(f"[VERBOSE] Limit: {args.limit}")
        print(f"[VERBOSE] Dynamic port scan: {'disabled' if args.no_dynamic_ports else 'enabled'}")
        if not args.no_dynamic_ports:
            print(f"[VERBOSE] Dynamic port limit: {args.dynamic_port_limit}")
            print(f"[VERBOSE] Dynamic port timeout: {args.dynamic_port_timeout}s")
    
    if args.method == "menu":
        # Show interactive menu
        if VERBOSE:
            print("[VERBOSE] Showing interactive menu")
        show_menu(args, db_path)
    elif args.method == "masscan":
        # Run masscan
        if VERBOSE:
            print("[VERBOSE] Running masscan")
        run_masscan(args, target_ips, args.port, args.rate, db_path)
    elif args.method == "shodan":
        # Run Shodan search
        if VERBOSE:
            print("[VERBOSE] Running Shodan search")
        run_shodan(args, db_path)
    elif args.method == "censys":
        # Run Censys search
        if VERBOSE:
            print("[VERBOSE] Running Censys search")
        run_censys(args, db_path)
    else:
        print(f"Unknown method: {args.method}")
        sys.exit(1)
    
    # Remove duplicates
    removeDuplicates()
    
    print("Scan completed")

def show_menu(args, db_path):
    """Display interactive menu for scanner options"""
    while True:
        print("\n=========================================")
        print("       OLLAMA SCANNER MENU               ")
        print("=========================================")
        print("1. Run masscan on ALL IPs (0.0.0.0/0)")
        print("2. Scan using masscan results file")
        print("3. Scan using Shodan API")
        print("4. Scan using Censys API")
        print("5. Prune duplicates from database")
        print("6. Exit")
        print("-----------------------------------------")
        
        choice = input("Enter your choice (1-6): ")
        
        if choice == '1':
            print("\n--- Direct Masscan Configuration for Full Internet Scan ---")
            print("This will run masscan to find Ollama instances on port 11434 across the entire internet")
            print("NOTE: masscan requires root privileges. You may need to run with sudo.")
            print("Target range: 0.0.0.0/0 (ALL IPv4 addresses)")
            
            # Set fixed values for a full internet scan
            target_ips = ["0.0.0.0/0"]  # Scan the entire internet
            port = 11434  # Default Ollama port
            scan_rate = 10000  # Set a reasonable rate to avoid network issues
            num_threads = 25  # Fixed 25 worker threads for verification
            
            print(f"\nSCAN CONFIGURATION:")
            print(f"- Target range: 0.0.0.0/0 (ENTIRE INTERNET)")
            print(f"- Port: {port}")
            print(f"- Scan rate: {scan_rate} pps")
            print(f"- Verification threads: {num_threads}")
            print(f"- Database: {db_path}")
            print("\nWARNING: Scanning without proper authorization may be illegal.")
            print("Only scan networks you own or have explicit permission to scan.")
            print("Scanning the entire internet may violate laws in many countries.")
            print("This can result in legal consequences including criminal charges.")
            
            confirm = input("\nAre you ABSOLUTELY SURE you want to continue with this scan? (y/n): ")
            
            if confirm.lower() == 'y' or confirm.lower() == 'yes':
                # Update args with the new values
                args.threads = num_threads
                args.port = port
                args.rate = scan_rate
                args.method = "masscan"  # Important: change method to avoid returning to menu
                
                # Run the scan
                result = run_scan(args, db_path, target_ips=target_ips)
                
                # If the scan was attempted, ask if user wants to return to menu
                print("\nScan operation completed.")
                continue_choice = input("Return to main menu? (y/n): ")
                if continue_choice.lower() not in ['y', 'yes']:
                    print("Exiting...")
                    sys.exit(0)
            else:
                print("Scan cancelled.")
        
        elif choice == '2':
            print("\n--- Masscan Results File Import ---")
            print("This will parse a masscan results file in grepable format (-oG)")
            print("Example line format: \"Host: 192.168.1.1 () Ports: 11434/open/tcp////\"")
            
            masscan_file = input("Enter path to masscan output file: ")
            if not masscan_file:
                print("Error: File path is required")
                continue
            if not os.path.exists(masscan_file):
                print(f"Error: File {masscan_file} does not exist")
                continue
            
            num_threads = input("Enter number of verification threads (default 50): ") or "50"
            
            print(f"\nIMPORT CONFIGURATION:")
            print(f"- Input file: {masscan_file}")
            print(f"- Verification threads: {num_threads}")
            print(f"- Database: {db_path}")
            
            confirm = input("\nContinue with import? (y/n): ")
            
            if confirm.lower() == 'y' or confirm.lower() == 'yes':
                # Update args
                args.input = masscan_file
                args.threads = int(num_threads)
                args.method = "masscan"  # Change method to avoid returning to menu
                # In this case we're using the input file, not target_ips
                run_scan(args, db_path)
                
                # Ask if user wants to return to menu
                continue_choice = input("\nReturn to main menu? (y/n): ")
                if continue_choice.lower() not in ['y', 'yes']:
                    print("Exiting...")
                    sys.exit(0)
            else:
                print("Import cancelled.")
            
        elif choice == '3':
            print("\n--- Shodan API Search ---")
            print("This will search Shodan for Ollama instances")
            
            if not SHODAN_API_KEY:
                key = input("Shodan API key not found. Enter your Shodan API key: ")
                if key:
                    os.environ["SHODAN_API_KEY"] = key
                    global shodan_client
                    shodan_client = shodan.Shodan(key)
                else:
                    print("No API key provided. Cannot continue with Shodan scan.")
                    continue
            
            num_threads = input("Enter number of verification threads (default 50): ") or "50"
            
            print(f"\nSHODAN SEARCH CONFIGURATION:")
            print(f"- API Key: {'*' * (len(SHODAN_API_KEY) - 4) + SHODAN_API_KEY[-4:] if SHODAN_API_KEY else 'None'}")
            print(f"- Verification threads: {num_threads}")
            print(f"- Database: {db_path}")
            
            confirm = input("\nContinue with Shodan search? (y/n): ")
            
            if confirm.lower() == 'y' or confirm.lower() == 'yes':
                # Update args
                args.threads = int(num_threads)
                args.method = "shodan"  # Change method to avoid returning to menu
                run_scan(args, db_path)
                
                # Ask if user wants to return to menu
                continue_choice = input("\nReturn to main menu? (y/n): ")
                if continue_choice.lower() not in ['y', 'yes']:
                    print("Exiting...")
                    sys.exit(0)
            else:
                print("Shodan search cancelled.")
            
        elif choice == '4':
            print("\n--- Censys API Search ---")
            print("This will search Censys for Ollama instances")
            
            if not censys_available:
                print("Censys module not installed. Run 'pip install censys' to enable Censys searching.")
                continue
                
            if not CENSYS_API_ID or not CENSYS_API_SECRET:
                censys_id = input("Censys API ID not found. Enter your Censys API ID: ")
                censys_secret = input("Enter your Censys API Secret: ")
                
                if censys_id and censys_secret:
                    os.environ["CENSYS_API_ID"] = censys_id
                    os.environ["CENSYS_API_SECRET"] = censys_secret
                else:
                    print("API credentials not provided. Cannot continue with Censys scan.")
                    continue
            
            num_threads = input("Enter number of verification threads (default 50): ") or "50"
            
            print(f"\nCENSYS SEARCH CONFIGURATION:")
            print(f"- API ID: {'*' * (len(CENSYS_API_ID) - 4) + CENSYS_API_ID[-4:] if CENSYS_API_ID else 'None'}")
            print(f"- API Secret: {'*' * (len(CENSYS_API_SECRET) - 4) + CENSYS_API_SECRET[-4:] if CENSYS_API_SECRET else 'None'}")
            print(f"- Verification threads: {num_threads}")
            print(f"- Database: {db_path}")
            
            confirm = input("\nContinue with Censys search? (y/n): ")
            
            if confirm.lower() == 'y' or confirm.lower() == 'yes':
                # Update args
                args.threads = int(num_threads)
                args.method = "censys"  # Change method to avoid returning to menu
                run_scan(args, db_path)
                
                # Ask if user wants to return to menu
                continue_choice = input("\nReturn to main menu? (y/n): ")
                if continue_choice.lower() not in ['y', 'yes']:
                    print("Exiting...")
                    sys.exit(0)
            else:
                print("Censys search cancelled.")
            
        elif choice == '5':
            print("\n--- Database Cleanup ---")
            print(f"This will remove duplicate entries from database: {db_path}")
            
            confirm = input("\nContinue with database cleanup? (y/n): ")
            
            if confirm.lower() == 'y' or confirm.lower() == 'yes':
                removeDuplicates()
                
                # Ask if user wants to return to menu
                continue_choice = input("\nReturn to main menu? (y/n): ")
                if continue_choice.lower() not in ['y', 'yes']:
                    print("Exiting...")
                    sys.exit(0)
            else:
                print("Cleanup cancelled.")
            
        elif choice == '6':
            print("Exiting...")
            sys.exit(0)
            
        else:
            print("Invalid choice, please try again")

def main():
    """Main function"""
    # Initialize database schema
    init_database()
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Ollama Scanner - Find Ollama instances using masscan, Shodan, or Censys")
    parser.add_argument("--method", choices=["masscan", "shodan", "censys", "menu"], default="menu", help="Method to use for scanning")
    parser.add_argument("--threads", type=int, default=50, help="Number of threads to use for concurrent verification")
    parser.add_argument("--pages", type=int, default=2, help="Number of pages to fetch from Censys (100 results per page)")
    
    # masscan specific options
    parser.add_argument("--target", dest="target_ips", nargs="+", help="Target IP range(s) for direct masscan scanning (e.g. 192.168.1.0/24)")
    parser.add_argument("--input", help="Input file with masscan results (grepable format)")
    parser.add_argument("--port", type=int, default=11434, help="Port to scan for Ollama instances (default: 11434)")
    parser.add_argument("--rate", type=int, default=10000, help="Masscan rate in packets per second (default: 10000)")
    parser.add_argument("--continuous", action="store_true", default=False,
                        help="Run scanner continuously (default: False)")
    
    # database options
    parser.add_argument("--db", default=None, help="Database file path (default: use predefined path)")
    parser.add_argument("--timeout", type=int, default=5, help="Connection timeout in seconds (default: 5)")
    
    # verbosity options
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output with detailed information about the scanning process")
    
    parser.add_argument('--status', type=str, default='scanned',
                        help="Status to assign to verified instances (default: 'scanned')")
    parser.add_argument('--preserve-verified', action='store_true', default=True,
                        help="Preserve existing verified instances in database (default: True)")
    parser.add_argument('--no-preserve-verified', dest='preserve_verified', action='store_false',
                        help="Do not preserve existing verified instances in database")
    parser.add_argument('--limit', type=int, default=0, 
                        help="Limit the number of IPs to process (default: 0 = no limit)")
    parser.add_argument('--no-dynamic-ports', action='store_true', default=False,
                        help="Skip scanning dynamic port ranges which can be slow (default: False)")
    parser.add_argument('--dynamic-port-limit', type=int, default=20,
                        help="Maximum number of ports to check in each dynamic port range (default: 20)")
    parser.add_argument('--dynamic-port-timeout', type=int, default=60,
                        help="Maximum seconds to spend scanning dynamic ports per IP (default: 60)")
    
    args = 
    # Add timeout flag - 0 means no timeout
    parser.add_argument('--timeout', '-t', type=int, default=None,
                      help='Timeout in seconds for API requests. Use 0 for no timeout.')
parser.parse_args()
    
    # Set global verbosity flag
    global VERBOSE
    VERBOSE = args.verbose
    
    if VERBOSE:
        print("[VERBOSE] Verbose mode enabled - you will see detailed information about the scanning process")
    
    # Validate masscan options
    if args.method == "masscan" and not args.input and not args.target_ips:
        parser.error("masscan method requires either --input FILE or --target IP_RANGE")
    
    # Set database path if provided
    global database_file
    if args.db:
        os.environ['DB_OVERRIDE_PATH'] = args.db
        if VERBOSE:
            print(f"[VERBOSE] Database path set to: {args.db}")
    
    # Create the database if it doesn't exist
    if DATABASE_TYPE == "postgres":
        # For PostgreSQL, just set the db_path to empty since it's not used for file path
        db_path = ""
    else:  
        # For SQLite, use the file path
        db_path = args.db if args.db else database_file
        
    if VERBOSE:
        print(f"[VERBOSE] Using database: {DATABASE_TYPE}")
        if DATABASE_TYPE == "sqlite":
            print(f"[VERBOSE] Database file: {db_path}")
        print("[VERBOSE] Creating database if it doesn't exist")
    
    makeDatabase()
    
    # Set up signal handlers for keyboard controls
    setup_signal_handlers()
    
    # Run the scan
    if args.method == "masscan" and args.target_ips:
        run_scan(args, db_path, target_ips=args.target_ips)
    else:
        run_scan(args, db_path)
    
    print(f"[INFO] Scan completed. Use query_models.py to search the database for specific models.")

if __name__ == "__main__":
    main() 