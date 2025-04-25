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
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ollama_scanner.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

# Global verbosity flag - default to False
VERBOSE = False

# Global args reference
args = None

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
    
    # Force exit after a timeout in case threads are stuck
    def force_exit():
        print("[TIMEOUT] Forcing exit after cleanup timeout...")
        os._exit(1)
    
    # Set a timer to force exit if graceful shutdown takes too long
    timer = threading.Timer(10.0, force_exit)
    timer.daemon = True
    timer.start()
    
    print("[DONE] Scanner terminated by user.")

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
    global scanner_running, scanner_paused, args
    
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
        # Use a local variable for timeout calculation to avoid undefined args
        current_timeout = timeout
        if 'args' in globals() and args is not None and hasattr(args, 'timeout'):
            current_timeout = calculate_dynamic_timeout(timeout_flag=args.timeout)
            
        r = requests.get(url, timeout=current_timeout)
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
            root_response = requests.get(root_url, timeout=current_timeout)
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
    query = 'SELECT ip, port FROM endpoints WHERE id = %s'
    endpoint = Database.fetch_one(query, (endpointId,))
    
    if not endpoint:
        logger.error(f"No endpoint found with ID {endpointId}")
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
        # Use correct parameter placeholder for both PostgreSQL and SQLite
        # For both PostgreSQL and SQLite
        verify_query = 'SELECT verified FROM endpoints WHERE id = %s'
        current_verified = Database.fetch_one(verify_query, (endpointId,))
        
        # If preserve_verified is True and the endpoint is already verified, don't change its status
        if preserve_verified and current_verified and current_verified[0] == 1:
            print(f"Preserving verified status for endpoint {ip}:{port}")
            # Just update the verification date
            Database.execute('''
            UPDATE endpoints 
            SET verification_date = %s 
            WHERE id = %s
            ''', (now, endpointId))
        else:
            # Update endpoint as verified
            Database.execute('''
            UPDATE endpoints 
            SET verified = 1, verification_date = %s 
            WHERE id = %s
            ''', (now, endpointId))
            
        # Check if this endpoint is already in verified_endpoints
        verify_query = 'SELECT id FROM verified_endpoints WHERE endpoint_id = %s'
        verify_params = (endpointId,)
        verified_exists = Database.fetch_one(verify_query, verify_params) is not None
        
        if not verified_exists:
            # Add to verified_endpoints
            Database.execute('''
            INSERT INTO verified_endpoints (endpoint_id, verification_date)
            VALUES (%s, %s)
            ''', (endpointId, now))
        else:
            # Update verification date
            Database.execute('''
            UPDATE verified_endpoints 
            SET verification_date = %s 
            WHERE endpoint_id = %s
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
                model_exists_query = 'SELECT id FROM models WHERE endpoint_id = %s AND name = %s'
                model_exists = Database.fetch_one(model_exists_query, (endpointId, name)) is not None
                
                if model_exists:
                    # Update existing model
                    Database.execute('''
                    UPDATE models 
                    SET parameter_size = %s, quantization_level = %s, size_mb = %s
                    WHERE endpoint_id = %s AND name = %s
                    ''', (parameter_size, quantization_level, sizeMb, endpointId, name))
                else:
                    # Add new model
                    Database.execute('''
                    INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)
                    ''', (endpointId, name, parameter_size, quantization_level, sizeMb))
            
            print(f"Added/updated {len(model_data['models'])} models for endpoint {ip}:{port}")
        
        return True
    else:
        # If not valid, mark as not verified (verified = 0)
        Database.execute('''
        UPDATE endpoints 
        SET verified = 0
        WHERE id = %s
        ''', (endpointId,))
        
        # Also remove from verified_endpoints if it exists
        Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = %s', (endpointId,))
        
        print(f"Marked endpoint {ip}:{port} as not verified")
        return False

def isDuplicateServer(ip, port):
    """Check if a server already exists in the database"""
    result = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, port))
    return result is not None

def saveStuffToDb(ip, p, modelData, status="scanned", preserve_verified=True):
    """Save server and model data to database with duplicate checking"""
    # Use lock to ensure thread safety
    with db_lock:
        # Check if this server already exists
        is_duplicate = isDuplicateServer(ip, p)
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if is_duplicate:
            if preserve_verified:
                # Update existing endpoint with new scan date but preserve verified status
                Database.execute('''
                UPDATE endpoints 
                SET scan_date = %s
                WHERE ip = %s AND port = %s
                ''', (now, ip, p))
            else:
                # Update existing endpoint with new status and scan date
                verified_value = 1 if status == "verified" else 0
                Database.execute('''
                UPDATE endpoints 
                SET scan_date = %s, verified = %s 
                WHERE ip = %s AND port = %s
                ''', (now, verified_value, ip, p))
            
            # Get the endpoint ID
            endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, p))
                
            if endpoint_row:
                endpointId = endpoint_row[0]
            else:
                return
        else:
            # Insert new endpoint with specified status
            verified_value = 1 if status == "verified" else 0
            result = Database.execute('''
            INSERT INTO endpoints (ip, port, scan_date, verified) 
            VALUES (%s, %s, %s, %s)
            ''', (ip, p, now, verified_value))
            
            # Get the newly inserted ID
            endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, p))
            endpointId = endpoint_row[0] if endpoint_row else None
        
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
        logger.info(f"Found {len(dupes)} duplicate endpoint records")
        
        for dupe in dupes:
            ip, port, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logger.info(f"Keeping {ip}:{port} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM endpoints WHERE id = %s", (remove_id,))
    
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
        logger.info(f"Found {len(model_dupes)} duplicate model records")
        
        for dupe in model_dupes:
            endpoint_id, name, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logger.info(f"Keeping model {name} for endpoint {endpoint_id} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM models WHERE id = %s", (remove_id,))
    
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
        logger.info(f"Found {len(ve_dupes)} duplicate verified_endpoints records")
        
        for dupe in ve_dupes:
            endpoint_id, count, id_list = dupe
            ids = id_list.split(',')
            # Keep the first ID, remove others
            keep_id = ids[0]
            remove_ids = ids[1:]
            
            logger.info(f"Keeping verified_endpoint for endpoint {endpoint_id} with ID {keep_id}, removing IDs {','.join(remove_ids)}")
            
            for remove_id in remove_ids:
                Database.execute("DELETE FROM verified_endpoints WHERE id = %s", (remove_id,))

    print("Database cleanup complete!")

def process_server(result, total_count, current_index, stats, status="scanned", preserve_verified=True, args=None):
    """
    Process a single server result with multiple port checks
    
    Args:
        result (dict): Server result data
        total_count (int): Total count of servers to process
        current_index (int): Current index in the server list
        stats (dict): Statistics dictionary
        status (str): Status to assign to discovered endpoints
        preserve_verified (bool): Whether to preserve verified status for existing endpoints
        args: Command line arguments
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
        process_server(result, len(results), i, stats, status=args.status, preserve_verified=args.preserve_verified, args=args)
    
    # Show stats
    print("\nMasscan processing complete")
    print(f"Valid Ollama instances: {stats['valid']}")
    print(f"Invalid endpoints: {stats['invalid']}")
    print(f"Errors: {stats['errors']}")
    print(f"Duplicates: {stats['duplicates']}")
    
    return stats['valid']

def run_shodan(args, db_path):
    """Run Shodan search for Ollama instances"""
    if not shodan_available:
        print("Error: Shodan module not installed. Run 'pip install shodan' to enable Shodan searching.")
        return

    if not SHODAN_API_KEY:
        print("Error: Shodan API key not set. Please set SHODAN_API_KEY in your environment variables or .env file.")
        return
    
    # Check API key validity and credits first
    try:
        info = shodan_client.info()
        print(f"Shodan API plan: {info.get('plan', 'Unknown')}")
        print(f"Query credits available: {info.get('query_credits', 'Unknown')}")
        logger.info(f"Shodan API plan: {info.get('plan', 'Unknown')}, Credits: {info.get('query_credits', 'Unknown')}")
    except Exception as e:
        print(f"Error checking Shodan API: {e}")
        logger.error(f"Error checking Shodan API: {e}")
        return
    
    # List of search queries to try
    queries = [
        'product:Ollama',
        'http.title:"Ollama"',
        'http.html:"ollama is running"',
        'port:11434 http'
    ]
    
    all_results = []
    
    for query in queries:
        # Show what we're searching for
        print(f"\nSearching Shodan for: {query}")
        logger.info(f"Starting Shodan search for: {query}")
        
        # Get the results with robust error handling and retries
        max_retries = 3
        results = []
        
        for page in range(1, args.pages + 1):
            for attempt in range(max_retries):
                try:
                    print(f"Fetching page {page} for query '{query}'...")
                    page_results = shodan_client.search(query, page=page)
                    
                    # Validate response structure before proceeding
                    if not isinstance(page_results, dict) or 'matches' not in page_results:
                        logger.warning(f"Unexpected Shodan API response structure for query '{query}' page {page}")
                        break
                        
                    results.extend(page_results.get('matches', []))
                    print(f"Found {len(page_results.get('matches', []))} results on page {page}")
                    logger.info(f"Retrieved {len(page_results.get('matches', []))} results from page {page} for query '{query}'")
                    
                    # Add a small delay between pages to avoid rate limiting
                    time.sleep(1.5)
                    break  # Success, exit retry loop
                    
                except shodan.APIError as e:
                    logger.error(f"Shodan API error for query '{query}' page {page}: {e}")
                    print(f"Shodan API error: {e}")
                    
                    # If we're rate limited, wait longer before retrying
                    if 'rate limit' in str(e).lower():
                        wait_time = 10 * (attempt + 1)
                        print(f"Rate limited. Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        break  # Non-rate limit error, skip retries
                        
                except Exception as e:
                    logger.error(f"Shodan API error for query '{query}' page {page}: {e}")
                    print(f"Error: {e}")
                    
                    if attempt < max_retries - 1:
                        wait_time = 5 * (attempt + 1)
                        print(f"Unexpected error. Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        print(f"Failed after {max_retries} attempts. Moving to next page or query.")
            
            # Break out of pagination if we didn't get a full page of results
            if len(page_results.get('matches', [])) < 100:
                break
        
        all_results.extend(results)
        print(f"Found {len(results)} total results for query '{query}'")
    
    # Deduplicate results based on IP
    unique_ips = {}
    for result in all_results:
        ip = result.get('ip_str')
        if ip and ip not in unique_ips:
            unique_ips[ip] = result
    
    print(f"\nFound {len(unique_ips)} unique IP addresses across all queries")
    logger.info(f"Found {len(unique_ips)} unique IP addresses across all Shodan queries")
    
    # Apply limit if specified
    ip_list = list(unique_ips.values())
    if args.limit > 0 and len(ip_list) > args.limit:
        print(f"Limiting to {args.limit} IPs")
        ip_list = ip_list[:args.limit]
    
    # Verify the instances
    if ip_list:
        valid_count = verify_instances(ip_list, db_path, args.threads, args.status, args.preserve_verified)
        print(f"Verified {valid_count} Ollama instances")
        return valid_count
    else:
        print("No results found")
        return 0

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
                
        process_server(result, len(results), i, stats, status=args.status, preserve_verified=args.preserve_verified, args=args)
    
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
    """
    result = {
        'ip': ip,
        'port': 11434,
        'verified': False,
        'error': False,
        'reason': 'Not verified',
        'model_data': None
    }
    
    try:
        # Add debug logging
        logger.debug(f"Starting verification of {ip}:11434")
        
        # Check if this IP is a valid Ollama server
        is_valid, model_data = isOllamaServer(ip, 11434, timeout)
        
        if is_valid:
            logger.info(f"Found valid Ollama server at {ip}:11434")
            # Found a valid Ollama server
            result['verified'] = True
            result['reason'] = 'Valid Ollama server'
            result['model_data'] = model_data
            
            # Process database operations...
        else:
            logger.debug(f"No Ollama server found at {ip}:11434")
            # Not a valid Ollama server
            result['verified'] = False
            result['reason'] = 'Not an Ollama server'
            
            # Process database operations...
    
    except Exception as e:
        # Log the full exception
        logger.error(f"Error verifying {ip}: {str(e)}")
        if VERBOSE:
            import traceback
            logger.error(traceback.format_exc())
        result['error'] = True
        result['reason'] = f"Error: {str(e)}"
    
    # Log the final result before adding to the queue
    logger.debug(f"Verification result for {ip}: verified={result['verified']}, error={result['error']}, reason={result['reason']}")
    
    # Add to result queue if provided
    if result_queue is not None:
        try:
            result_queue.put(result)
            logger.debug(f"Added result for {ip} to queue")
        except Exception as e:
            logger.error(f"Error adding result for {ip} to queue: {str(e)}")
    
    return result

def save_model_to_db(endpoint_id, model):
    """Helper function to save a model to the database"""
    name = model.get("name", "Unknown")
    size = model.get("size", 0)
    size_mb = size / (1024 * 1024) if size else 0
    
    details = model.get("details", {})
    parameter_size = details.get("parameter_size", "Unknown")
    quantization_level = details.get("quantization_level", "Unknown")
    
    # Check if model already exists
    model_exists = Database.fetch_one(
        'SELECT id FROM models WHERE endpoint_id = %s AND name = %s',
        (endpoint_id, name)
    )
    
    if model_exists:
        # Update existing model
        Database.execute(
            '''UPDATE models 
            SET parameter_size = %s, quantization_level = %s, size_mb = %s 
            WHERE endpoint_id = %s AND name = %s''',
            (parameter_size, quantization_level, size_mb, endpoint_id, name)
        )
    else:
        # Insert new model
        Database.execute(
            '''INSERT INTO models 
            (endpoint_id, name, parameter_size, quantization_level, size_mb)
            VALUES (%s, %s, %s, %s, %s)''',
            (endpoint_id, name, parameter_size, quantization_level, size_mb)
        )

def add_server_to_db(ip, models_data, ps_data, db_path):
    """Add a server and its models to the database"""
    try:
        # Get current timestamp
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Find the endpoint ID in our database
        endpoint = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, 11434))
        if not endpoint:
            if VERBOSE:
                print(f"[ERROR] Endpoint {ip}:11434 not found in database, can't add models")
            return False
        
        endpoint_id = endpoint[0]
        
        # Update scan date and mark as verified
        Database.execute('UPDATE endpoints SET scan_date = %s, verified = 1, verification_date = %s WHERE id = %s', 
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
            model_query = 'SELECT id FROM models WHERE endpoint_id = %s AND name = %s'
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
                    SET parameter_size = %s, quantization_level = %s, size_mb = %s
                    WHERE endpoint_id = %s AND name = %s''',
                    (param_size, quant_level, size_mb, endpoint_id, name)
                )
            else:
                # Insert new model - ensure we're passing only scalar values
                Database.execute(
                    '''INSERT INTO models 
                    (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)''',
                    (endpoint_id, name, param_size, quant_level, size_mb)
                )
        
        return True
    except Exception as e:
        print(f"Error adding server to database: {e}")
        if VERBOSE:
            import traceback
            traceback.print_exc()
        return False

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
    # Get DB connection pool size from env or use default
    max_db_connections = int(os.getenv("DB_MAX_CONNECTIONS", "50"))
    
    # Reduce thread count if it exceeds max DB connections
    # Leave some connections for other operations
    safe_thread_count = max(1, min(num_threads, max_db_connections - 5))
    
    if safe_thread_count < num_threads:
        print(f"[WARN] Reducing thread count from {num_threads} to {safe_thread_count} to avoid DB connection pool exhaustion")
        num_threads = safe_thread_count
    
    print(f"[INFO] Verifying {len(ip_list)} potential Ollama instances using {num_threads} threads")
    
    # Process Shodan results properly to extract IPs
    processed_ips = []
    for result in ip_list:
        # If this is a Shodan result object, extract the IP
        if isinstance(result, dict) and 'ip_str' in result:
            processed_ips.append(result['ip_str'])
        # If this is already an IP string
        elif isinstance(result, str):
            processed_ips.append(result)
        else:
            logger.warning(f"Skipping unrecognized result format: {type(result)}")
    
    # Create a queue to store the results
    result_queue = Queue()
    
    # Add a detailed statistics tracker with thread safety
    stats = {
        'completed': 0,
        'total': len(processed_ips),
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'start_time': datetime.now(),
        'lock': threading.Lock()
    }
    
    # Create and start the worker threads
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit verification tasks for each IP
        futures = []
        for ip in processed_ips:
            if not scanner_running:
                break
                
            # Skip if we've hit the limit
            if args and args.limit > 0 and stats['completed'] >= args.limit:
                break
                
            future = executor.submit(
                verify_instance, 
                ip, 
                db_path, 
                timeout=args.timeout if args and hasattr(args, 'timeout') else 5,
                result_queue=result_queue,
                status=status,
                preserve_verified=preserve_verified
            )
            futures.append(future)
        
        # Progress monitoring loop
        try:
            while stats['completed'] < min(len(processed_ips), args.limit if args and args.limit > 0 else float('inf')) and scanner_running:
                # Process completed results from the queue
                try:
                    # Non-blocking queue check
                    while not result_queue.empty():
                        result = result_queue.get_nowait()
                        with stats['lock']:
                            stats['completed'] += 1
                            
                            # Debug the classification process
                            logger.debug(f"Processing queue item for {result.get('ip', 'unknown')}: " +
                                        f"verified={result.get('verified', False)}, " +
                                        f"error={result.get('error', False)}")
                            
                            if result.get('verified', False):
                                stats['valid'] += 1
                                logger.info(f"Valid Ollama instance: {result.get('ip', 'unknown')}")
                            elif result.get('error', False):
                                stats['errors'] += 1
                                logger.debug(f"Error verifying {result.get('ip', 'unknown')}: {result.get('reason', 'Unknown error')}")
                            else:
                                stats['invalid'] += 1
                                logger.debug(f"Invalid instance: {result.get('ip', 'unknown')}")
                except Exception as e:
                    # Just log any queue errors and continue
                    logger.error(f"Error processing result queue: {str(e)}")
                
                # Show progress
                elapsed = datetime.now() - stats['start_time']
                elapsed_seconds = elapsed.total_seconds()
                rate = stats['completed'] / elapsed_seconds if elapsed_seconds > 0 else 0
                
                # Calculate ETA
                remaining = stats['total'] - stats['completed']
                eta_seconds = remaining / rate if rate > 0 else 0
                eta = timedelta(seconds=int(eta_seconds))
                
                # Display progress
                print(f"\r[PROGRESS] Verification: {stats['completed']}/{stats['total']} ({stats['completed']/stats['total']*100:.1f}%)")
                print(f"[STATS] Valid: {stats['valid']}, Invalid: {stats['invalid']}, Errors: {stats['errors']}")
                print(f"[TIME] Elapsed: {str(elapsed).split('.')[0]}, ETA: {str(eta).split('.')[0]}")
                print(f"[RATE] {rate:.2f} endpoints/second")
                
                # Pause if needed
                while not scanner_paused.is_set() and scanner_running:
                    time.sleep(0.5)
                    print("\r[PAUSED] Scanner paused. Press Ctrl+C to resume...")
                
                # Exit if termination requested
                if not scanner_running:
                    print("\r[TERMINATING] Cleanup in progress...")
                    break
                
                # Sleep briefly to avoid CPU spinning
                time.sleep(1)
                
                # Clear terminal lines for next update (if supported)
                print("\033[4A\033[K\033[K\033[K\033[K", end='')
                
            # Final statistics 
            print(f"\n[COMPLETE] Verification finished")
            print(f"[STATS] Total: {stats['completed']}/{stats['total']}, Valid: {stats['valid']}, Invalid: {stats['invalid']}, Errors: {stats['errors']}")
            print(f"[TIME] Total time: {str(datetime.now() - stats['start_time']).split('.')[0]}")
            
            return stats['valid']
            
        except KeyboardInterrupt:
            print("\nVerification interrupted by user.")
            return stats['valid']
        finally:
            # Cancel any pending futures if we're terminating
            for future in futures:
                if not future.done():
                    future.cancel()

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
    """Show an interactive menu for the user to select options"""
    print("\n========== Ollama Scanner Menu ==========")
    
    while True:
        print("\nChoose a scan method or action:")
        print("1. Direct IP scan with masscan")
        print("2. Shodan search for Ollama instances")
        print("3. Censys search for Ollama instances")
        print("4. Reassign models for verified endpoints")
        print("5. Check specific endpoint status")
        print("6. Database cleanup")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ")
        
        # Handle choices...
        
        elif choice == '4':
            print("\n--- Reassign Models ---")
            print("This will re-check all verified endpoints for new models")
            
            # Get optional IP filter
            specific_ip = input("Enter specific IP to check (or leave empty for all): ").strip()
            
            if specific_ip:
                args.specific_ip = specific_ip
            else:
                args.specific_ip = None
                
            args.force = False
            args.method = "reassign"
            reassign_models(args, db_path)
            
            # Ask if user wants to return to menu
            continue_choice = input("\nReturn to main menu? (y/n): ")
            if continue_choice.lower() not in ['y', 'yes']:
                print("Exiting...")
                sys.exit(0)
        
        elif choice == '5':
            print("\n--- Check Endpoint Status ---")
            
            # Get IP to check
            check_ip = input("Enter IP address to check: ").strip()
            
            if not check_ip:
                print("Error: No IP specified")
                continue
                
            # Get optional port
            check_port = input("Enter port (default: 11434): ").strip()
            if check_port and check_port.isdigit():
                args.check_port = int(check_port)
            else:
                args.check_port = 11434
                
            args.check_ip = check_ip
            args.method = "check"
            check_endpoint(args, db_path)
            
            # Ask if user wants to return to menu
            continue_choice = input("\nReturn to main menu? (y/n): ")
            if continue_choice.lower() not in ['y', 'yes']:
                print("Exiting...")
                sys.exit(0)
        
        elif choice == '6':
            # Database cleanup code...

def main():
    """Main function"""
    global args, VERBOSE  # Make args global
    
    # Initialize database schema
    init_database()
    
    # Configure PostgreSQL connection pool size based on thread count
    if DATABASE_TYPE == "postgres":
        # Log current connection pool settings
        max_conn = os.getenv("DB_MAX_CONNECTIONS", "50")
        min_conn = os.getenv("DB_MIN_CONNECTIONS", "5")
        logger.info(f"PostgreSQL connection pool: min={min_conn}, max={max_conn}")
        
        # Recommend proper settings if threads are high
        default_threads = 50
        if int(max_conn) < default_threads:
            logger.warning(f"DB_MAX_CONNECTIONS ({max_conn}) is less than default thread count ({default_threads})")
            logger.warning("Consider increasing DB_MAX_CONNECTIONS or reducing --threads")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Ollama Scanner - Find Ollama instances using masscan, Shodan, or Censys")
    parser.add_argument("--method", choices=["masscan", "shodan", "censys", "menu", "reassign", "check"], default="menu", 
                      help="Method to use (default: menu)")
    
    # Existing arguments...
    
    # Add reassignment options
    parser.add_argument('--specific-ip', type=str, default=None,
                      help='Specific IP to reassign models for (default: all verified endpoints)')
    parser.add_argument('--force', action='store_true', default=False,
                      help='Skip confirmation prompts (default: False)')
    
    # Add endpoint checking options
    parser.add_argument('--check-ip', type=str, default=None,
                      help='IP address to check endpoint status')
    parser.add_argument('--check-port', type=int, default=11434,
                      help='Port for endpoint to check (default: 11434)')
    
    args = parser.parse_args()
    
    # Set global verbosity flag
    VERBOSE = args.verbose
    
    # Rest of the code...
    
    # Handle new methods
    if args.method == "reassign":
        reassign_models(args, db_path)
        return
    elif args.method == "check":
        check_endpoint(args, db_path)
        return
    
    # Run the scan for other methods
    if args.method == "masscan" and args.target_ips:
        run_scan(args, db_path, target_ips=args.target_ips)
    else:
        run_scan(args, db_path)
    
    print(f"[INFO] Scan completed. Use query_models.py to search the database for specific models.")

def reassign_models(args, db_path):
    """
    Re-verify all endpoints in database and update their model information
    
    This is useful when new models have been added to instances since the last scan
    """
    print("\n[INFO] Starting model reassignment for verified endpoints")
    
    # Query for all verified endpoints or specific IPs if provided
    if hasattr(args, 'specific_ip') and args.specific_ip:
        # Query for specific IP
        endpoints = Database.fetch_all(
            'SELECT id, ip, port FROM endpoints WHERE ip = %s AND verified = 1', 
            (args.specific_ip,)
        )
        print(f"[INFO] Found {len(endpoints)} verified endpoints with IP {args.specific_ip}")
    else:
        # Query for all verified endpoints
        endpoints = Database.fetch_all(
            'SELECT id, ip, port FROM endpoints WHERE verified = 1', 
            ()
        )
        print(f"[INFO] Found {len(endpoints)} verified endpoints in database")
    
    if not endpoints:
        print("[INFO] No verified endpoints found to reassign models")
        return 0
    
    # Ask for confirmation
    if not hasattr(args, 'force') or not args.force:
        confirm = input(f"Continue with model reassignment for {len(endpoints)} endpoints? (y/n): ")
        if confirm.lower() not in ['y', 'yes']:
            print("[INFO] Model reassignment cancelled")
            return 0
    
    # Set up stats
    stats = {
        'total': len(endpoints),
        'processed': 0,
        'updated': 0,
        'errors': 0,
        'unchanged': 0,
        'new_models': 0
    }
    
    print(f"\n[INFO] Processing {stats['total']} endpoints")
    
    # Process each endpoint
    for endpoint in endpoints:
        endpoint_id, ip, port = endpoint
        
        # Show progress
        stats['processed'] += 1
        if stats['processed'] % 10 == 0 or stats['processed'] == stats['total']:
            print(f"[PROGRESS] {stats['processed']}/{stats['total']} ({stats['processed']/stats['total']*100:.1f}%)")
        
        try:
            # Check if the endpoint is still valid
            is_valid, model_data = isOllamaServer(ip, port, timeout=10)
            
            if is_valid and model_data and "models" in model_data:
                # Get current models for this endpoint
                current_models = Database.fetch_all(
                    'SELECT name FROM models WHERE endpoint_id = %s',
                    (endpoint_id,)
                )
                current_model_names = [m[0] for m in current_models] if current_models else []
                
                # Update verification timestamp
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                Database.execute(
                    'UPDATE endpoints SET verification_date = %s WHERE id = %s',
                    (now, endpoint_id)
                )
                
                # Process each model
                for model in model_data["models"]:
                    name = model.get("name", "Unknown")
                    size = model.get("size", 0)
                    size_mb = size / (1024 * 1024) if size else 0
                    
                    details = model.get("details", {})
                    parameter_size = details.get("parameter_size", "Unknown")
                    quantization_level = details.get("quantization_level", "Unknown")
                    
                    # Check if model exists for this endpoint
                    if name in current_model_names:
                        # Update existing model
                        Database.execute(
                            '''UPDATE models 
                            SET parameter_size = %s, quantization_level = %s, size_mb = %s 
                            WHERE endpoint_id = %s AND name = %s''',
                            (parameter_size, quantization_level, size_mb, endpoint_id, name)
                        )
                        stats['updated'] += 1
                    else:
                        # Add new model
                        Database.execute(
                            '''INSERT INTO models 
                            (endpoint_id, name, parameter_size, quantization_level, size_mb)
                            VALUES (%s, %s, %s, %s, %s)''',
                            (endpoint_id, name, parameter_size, quantization_level, size_mb)
                        )
                        stats['new_models'] += 1
                        print(f"[NEW] Found new model '{name}' on {ip}:{port}")
            else:
                # Endpoint is no longer valid
                print(f"[INVALID] Endpoint {ip}:{port} is no longer valid, marking as unverified")
                Database.execute(
                    'UPDATE endpoints SET verified = 0 WHERE id = %s',
                    (endpoint_id,)
                )
                stats['errors'] += 1
                
        except Exception as e:
            print(f"[ERROR] Failed to process endpoint {ip}:{port}: {str(e)}")
            stats['errors'] += 1
    
    # Show final stats
    print("\n[COMPLETE] Model reassignment finished")
    print(f"[STATS] Total endpoints: {stats['total']}")
    print(f"[STATS] Processed: {stats['processed']}")
    print(f"[STATS] Updated models: {stats['updated']}")
    print(f"[STATS] New models found: {stats['new_models']}")
    print(f"[STATS] Errors: {stats['errors']}")
    
    return stats['new_models']

def check_endpoint(args, db_path):
    """
    Diagnostic function to check why an endpoint is marked as active or inactive
    """
    if not hasattr(args, 'check_ip') or not args.check_ip:
        print("[ERROR] No IP specified to check. Use --check-ip parameter.")
        return 1
        
    ip = args.check_ip
    port = args.check_port if hasattr(args, 'check_port') and args.check_port else 11434
    
    print(f"\n[DIAGNOSTIC] Checking endpoint {ip}:{port}")
    
    # First, check database status
    endpoint = Database.fetch_one(
        'SELECT id, verified, scan_date, verification_date FROM endpoints WHERE ip = %s AND port = %s',
        (ip, port)
    )
    
    if not endpoint:
        print(f"[INFO] Endpoint {ip}:{port} not found in database")
        
        # Try live check
        print(f"[INFO] Performing live check of {ip}:{port}")
        is_valid, model_data = isOllamaServer(ip, port, timeout=10)
        
        if is_valid:
            print(f"[RESULT] Endpoint {ip}:{port} is a valid Ollama server but not in database")
            if model_data and "models" in model_data:
                print(f"[MODELS] Found {len(model_data['models'])} models:")
                for model in model_data["models"]:
                    name = model.get("name", "Unknown")
                    size = model.get("size", 0)
                    size_mb = size / (1024 * 1024) if size else 0
                    print(f"  - {name} ({size_mb:.1f} MB)")
        else:
            print(f"[RESULT] Endpoint {ip}:{port} is not a valid Ollama server")
        
        return 0
    
    # Found in database
    endpoint_id, verified, scan_date, verification_date = endpoint
    
    print(f"[DB STATUS] Endpoint {ip}:{port} found in database (ID: {endpoint_id})")
    print(f"[DB STATUS] Verified: {'Yes' if verified == 1 else 'No'}")
    print(f"[DB STATUS] Last scan: {scan_date}")
    print(f"[DB STATUS] Last verification: {verification_date}")
    
    # Get models
    models = Database.fetch_all(
        'SELECT name, parameter_size, quantization_level, size_mb FROM models WHERE endpoint_id = %s',
        (endpoint_id,)
    )
    
    if models:
        print(f"[DB MODELS] Found {len(models)} models:")
        for model in models:
            name, parameter_size, quantization_level, size_mb = model
            print(f"  - {name} ({parameter_size}, {quantization_level}, {size_mb:.1f} MB)")
    else:
        print("[DB MODELS] No models found for this endpoint")
    
    # Perform live check
    print(f"\n[LIVE CHECK] Verifying {ip}:{port} is still active...")
    is_valid, model_data = isOllamaServer(ip, port, timeout=10)
    
    if is_valid:
        print(f"[LIVE STATUS] Endpoint {ip}:{port} is a valid Ollama server")
        
        if model_data and "models" in model_data:
            print(f"[LIVE MODELS] Found {len(model_data['models'])} models:")
            for model in model_data["models"]:
                name = model.get("name", "Unknown")
                size = model.get("size", 0)
                size_mb = size / (1024 * 1024) if size else 0
                print(f"  - {name} ({size_mb:.1f} MB)")
            
            # Compare with database
            db_model_names = [m[0] for m in models] if models else []
            live_model_names = [m.get("name", "Unknown") for m in model_data["models"]]
            
            # Models in database but not live
            removed_models = [m for m in db_model_names if m not in live_model_names]
            if removed_models:
                print(f"[DIFF] Models in database but not live: {', '.join(removed_models)}")
            
            # Models live but not in database
            new_models = [m for m in live_model_names if m not in db_model_names]
            if new_models:
                print(f"[DIFF] Models live but not in database: {', '.join(new_models)}")
                
            # No differences
            if not removed_models and not new_models:
                print("[DIFF] Database models match live models")
    else:
        print(f"[LIVE STATUS] Endpoint {ip}:{port} is NOT a valid Ollama server")
        print(f"[INCONSISTENCY] Database shows verified={verified} but endpoint is not valid")
        
        # Ask if user wants to update database
        if verified == 1:
            confirm = input("\nUpdate database to mark this endpoint as not verified? (y/n): ")
            if confirm.lower() in ['y', 'yes']:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                Database.execute(
                    'UPDATE endpoints SET verified = 0, scan_date = %s WHERE id = %s',
                    (now, endpoint_id)
                )
                print(f"[UPDATE] Marked endpoint {ip}:{port} as not verified")
    
    return 0

if __name__ == "__main__":
    main() 