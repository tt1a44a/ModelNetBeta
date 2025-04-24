#!/usr/bin/env python3
"""
Ollama Scanner - tool to find Ollama instances using Shodan, Censys, and masscan
"""

import os
import sys
import time
import json
import requests
import argparse
import threading
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shodan
from queue import Queue

# Database abstraction
from database import Database, init_database

# Load environment variables from .env file if it exists
load_dotenv()

# PostgreSQL connection details for results display
PG_DB_NAME = os.getenv("POSTGRES_DB", "ollama_scanner")
PG_DB_USER = os.getenv("POSTGRES_USER", "ollama")
PG_DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# Global settings
# Define default settings for verbosity
DEFAULT_VERBOSE = False

# Shodan API key
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY", "")

# Censys API credentials
CENSYS_API_ID = os.getenv("CENSYS_API_ID", "")
CENSYS_API_SECRET = os.getenv("CENSYS_API_SECRET", "")

# Initialize Shodan client
shodan_client = None
if SHODAN_API_KEY:
    shodan_client = shodan.Shodan(SHODAN_API_KEY)

# Try to import Censys if available
try:
    from censys.search import CensysHosts
    censys_available = True
except ImportError:
    censys_available = False
    print("Warning: Censys module not installed. Run 'pip install censys' to enable Censys searching.")

# Connection settings
timeout = 5 
maxResults = 1000  

# Database lock for thread safety
db_lock = threading.Lock()

# Last scan time tracking
last_check_time = None

def makeDatabase():
    """Create or verify PostgreSQL database tables and schema"""
    try:
        # Initialize the database schema
        init_database()
        print(f"Database initialized successfully")
    except Exception as e:
        print(f"Database error: {e}")
        sys.exit(1)

def isOllamaServer(ip, p=11434):
    """Check if an IP/port combo is running Ollama by checking the API endpoint"""
    # First try the API endpoint which should be most reliable
    url = "http://" + ip + ":" + str(p) + "/api/tags"
    try:
        r = requests.get(url, timeout=timeout)
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
            root_response = requests.get(root_url, timeout=timeout)
            if "ollama is running" in root_response.text.lower():
                # Found the Ollama landing page, but we don't have model info
                return True, {"models": []}
        except:
            pass
            
        return False, None
    except:
        return False, None

def isDuplicateServer(ip, port):
    """Check if a server already exists in the database"""
    result = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, port))
    return result is not None

def saveStuffToDb(ip, p, modelData):
    """Save server and model data to database with duplicate checking"""
    # Use lock to ensure thread safety
    with db_lock:
        # Check if this server already exists
        is_duplicate = isDuplicateServer(ip, p)
        
        conn = Database()
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if is_duplicate:
            # Update existing server with new scan date
            conn.execute('''
            UPDATE endpoints SET scan_date = %s WHERE ip = %s AND port = %s
            ''', (now, ip, p))
            
            # Get the server ID
            server_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, p))
            if server_row:
                serverId = server_row[0]
            else:
                Database.close()
                return
        else:
            # Insert new server
            conn.execute('''
            INSERT INTO endpoints (ip, port, scan_date) 
            VALUES (%s, %s, %s)
            ''', (ip, p, now))
            
            # Get the new server ID
            serverId = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, p))[0]
        
        # Process models
        if modelData != None and "models" in modelData:
            for m in modelData["models"]:
                name = m.get("name", "Unknown")
                
                # Check if this model already exists on this server
                model_exists = Database.fetch_one(
                    'SELECT id FROM models WHERE endpoint_id = %s AND name = %s', 
                    (serverId, name)
                ) is not None
                
                size = m.get("size", 0)
                if size:
                    sizeMb = size / (1024 * 1024)
                else:
                    sizeMb = 0
                
                details = m.get("details", {})
                if "parameter_size" in details:
                    paramSize = details["parameter_size"]
                else:
                    paramSize = "Unknown"
                    
                if "quantization_level" in details:
                    quantLevel = details["quantization_level"]
                else:
                    quantLevel = "Unknown"
                
                if model_exists:
                    # Update existing model
                    conn.execute('''
                    UPDATE models 
                    SET parameter_size = %s, quantization_level = %s, size_mb = %s
                    WHERE endpoint_id = %s AND name = %s
                    ''', (paramSize, quantLevel, sizeMb, serverId, name))
                else:
                    # Insert new model
                    conn.execute('''
                    INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)
                    ''', (serverId, name, paramSize, quantLevel, sizeMb))
        
        Database.close()
        
        return is_duplicate

def removeDuplicates():
    """Remove duplicate entries from the database"""
    conn = Database()
    
    # Find duplicate endpoints
    dupes = Database.fetch_all("""
        SELECT ip, port, COUNT(*), string_agg(id::text, ',') as ids
        FROM endpoints
        GROUP BY ip, port
        HAVING COUNT(*) > 1
    """)
    
    # did we find any?
    if len(dupes) == 0:
        print("No duplicate endpoints found!")
    else:
        print("Found " + str(len(dupes)) + " duplicate endpoint entries - fixing now...")
        
        # go through each set of duplicates
        for dupe in dupes:
            ip, port, count, ids = dupe
            id_list = ids.split(',')
            # keep first one, remove others
            keep_id = id_list[0]  # keep this one
            remove_ids = id_list[1:]  # get rid of these
            
            print("  Will keep endpoint: " + ip + ":" + str(port) + " (ID " + keep_id + ")")
            print("  Will remove: " + str(len(remove_ids)) + " duplicates with same IP/port")
            
            # Update models to point to the ID we're keeping
            for remove_id in remove_ids:
                conn.execute("""
                    UPDATE models
                    SET endpoint_id = %s
                    WHERE endpoint_id = %s
                """, (keep_id, remove_id))
                
                # Update verified_endpoints to point to the ID we're keeping
                conn.execute("""
                    UPDATE verified_endpoints
                    SET endpoint_id = %s
                    WHERE endpoint_id = %s
                """, (keep_id, remove_id))
                
                # Now delete the duplicate endpoint
                Database.execute("DELETE FROM endpoints WHERE id = %s", (remove_id,))
    
    # Find duplicate models
    dupe_models = Database.fetch_all("""
        SELECT endpoint_id, name, COUNT(*), string_agg(id::text, ',') as ids
        FROM models
        GROUP BY endpoint_id, name
        HAVING COUNT(*) > 1
    """)
    
    # did we find any?
    if len(dupe_models) == 0:
        print("No duplicate models found!")
    else:
        print("Found " + str(len(dupe_models)) + " duplicate model entries - fixing now...")
        
        # go through each set of duplicates
        for dupe in dupe_models:
            endpoint_id, name, count, ids = dupe
            id_list = ids.split(',')
            # keep first one, remove others
            keep_id = id_list[0]  # keep this one
            remove_ids = id_list[1:]  # get rid of these
            
            # Get the endpoint IP and port for logging
            endpoint_info = Database.fetch_one("SELECT ip, port FROM endpoints WHERE id = %s", (endpoint_id,))
            if endpoint_info:
                ip, port = endpoint_info
                endpoint_str = f"{ip}:{port}"
            else:
                endpoint_str = f"ID {endpoint_id}"
            
            print(f"  Will keep model: {name} on {endpoint_str} (ID {keep_id})")
            print(f"  Will remove: {len(remove_ids)} duplicates")
            
            # Delete the duplicate models
            for remove_id in remove_ids:
                Database.execute("DELETE FROM models WHERE id = %s", (remove_id,))
    
    Database.close()

def process_server(result, total_count, current_index, stats):
    """Process a single server result with multiple port checks"""
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
            works, data = isOllamaServer(ip, test_port)
            if works == True:
                with stats['lock']:
                    stats['good'] += 1
                
                if data and "models" in data:
                    num_models = len(data["models"])
                else:
                    num_models = 0
                
                # Save to DB and check if it was a duplicate
                is_duplicate = saveStuffToDb(ip, test_port, data)
                
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
        if not found and 'promising_ip' in result and result['promising_ip']:
            print(f"Checking dynamic port ranges for {ip} as it seems promising...")
            
            for start_port, end_port in dynamic_port_ranges:
                for dynamic_port in range(start_port, end_port):
                    works, data = isOllamaServer(ip, dynamic_port)
                    if works == True:
                        with stats['lock']:
                            stats['good'] += 1
                        
                        if data and "models" in data:
                            num_models = len(data["models"])
                        else:
                            num_models = 0
                        
                        # Save to DB and check if it was a duplicate
                        is_duplicate = saveStuffToDb(ip, dynamic_port, data)
                        
                        with stats['lock']:
                            if is_duplicate:
                                stats['duplicates'] += 1
                                print(f"UPDATE! Ollama at {ip}:{dynamic_port} with {num_models} models (already in DB)")
                            else:
                                print(f"NEW! Found Ollama at {ip}:{dynamic_port} with {num_models} models")
                        
                        found = True
                        break  # exit the loop
                
                if found:
                    break  # exit the outer loop
        
        if found == False:
            print(f"No valid Ollama endpoints found at {ip}")
    
    except Exception as e:
        with stats['lock']:
            stats['bad'] += 1
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
        list: List of dictionaries with IP and port information
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
                    port = int(match.group(2))
                    
                    # Format like Shodan results for compatibility
                    result = {
                        'ip_str': ip,
                        'port': port
                    }
                    results.append(result)
                    
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
    
    pg = 1
    shodan_results = []
    
    while True:
        try:
            print("Fetching page " + str(pg) + "...")
            res = shodan_client.search('product:Ollama', page=pg, limit=maxResults)
            
            if len(res['matches']) == 0:
                print("No more results found.")
                break
                
            for match in res['matches']:
                shodan_results.append(match)
                
            print("Found " + str(len(res['matches'])) + " results on page " + str(pg))
            
            time.sleep(1)  # Don't overload shodan API
            
            pg = pg + 1
            
            if len(shodan_results) >= 1500 or pg > 20:  # Don't get more than 20 pages
                print("Reached limit of " + str(len(shodan_results)) + " results or max pages.")
                break
                
        except Exception as e:
            errText = str(e)
            if 'Invalid page' in errText or 'No more results' in errText:
                print("No more pages available.")
            else:
                print(f"Error during Shodan search: {str(e)}")
            break  # Continue with what we have
    
    print(f"Total potential Ollama instances found on Shodan: {len(shodan_results)}")
    return shodan_results

def verify_instance(ip, db_path, timeout=5, result_queue=None, verbose=None):
    """Verify if an IP address is running Ollama"""
    # Use the global VERBOSE if verbose parameter is not provided
    if verbose is None:
        verbose = DEFAULT_VERBOSE
        
    try:
        # First, add the endpoint to the database as unverified
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if endpoint exists
        endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, 11434))
        
        if endpoint_row:
            endpoint_id = endpoint_row[0]
            # Update scan date
            Database.execute('UPDATE endpoints SET scan_date = %s WHERE id = %s', (now, endpoint_id))
            if verbose:
                print(f"[VERBOSE] Updating existing endpoint {ip}:11434 (ID {endpoint_id})")
        else:
            # Insert as unverified
            Database.execute(
                'INSERT INTO endpoints (ip, port, scan_date, verified) VALUES (%s, %s, %s, 0)',
                (ip, 11434, now)
            )
            # Get the new ID
            endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, 11434))
            endpoint_id = endpoint_row[0]
            if verbose:
                print(f"[VERBOSE] Added new endpoint {ip}:11434 (ID {endpoint_id})")
        
        # Check /api/tags endpoint
        tags_url = f"http://{ip}:11434/api/tags"
        if verbose:
            print(f"[VERBOSE] Trying endpoint: {tags_url}")
        
        verification_start = datetime.now()
        tags_response = requests.get(tags_url, timeout=timeout)
        verification_time = (datetime.now() - verification_start).total_seconds()
        
        if tags_response.status_code == 200:
            try:
                tags_data = tags_response.json()
                
                # Check if models list exists and is not empty
                if "models" in tags_data and len(tags_data["models"]) > 0:
                    model_count = len(tags_data["models"])
                    
                    if verbose:
                        print(f"[VERBOSE] Valid response from {ip}:11434 with {model_count} models")
                        print(f"[VERBOSE] Response time: {verification_time:.3f}s")
                    
                    # Also check process list to see if ollama is detected as a process name
                    ps_url = f"http://{ip}:11434/api/ps"
                    ps_data = None
                    
                    try:
                        ps_response = requests.get(ps_url, timeout=timeout)
                        if ps_response.status_code == 200:
                            ps_data = ps_response.json()
                            if verbose and ps_data:
                                print(f"[VERBOSE] Process info successfully retrieved from {ip}:11434")
                        else:
                            if verbose:
                                print(f"[VERBOSE] Could not get process info from {ip}:11434 - status code {ps_response.status_code}")
                    except requests.RequestException as e:
                        if verbose:
                            print(f"[VERBOSE] Error retrieving process info from {ip}:11434: {str(e)}")
                    
                    # Mark the endpoint as verified
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Update endpoint as verified
                    Database.execute(
                        'UPDATE endpoints SET verified = 1, verification_date = %s WHERE id = %s',
                        (now, endpoint_id)
                    )
                    
                    # Check if the endpoint is already in verified_endpoints
                    verified_exists = Database.fetch_one('SELECT id FROM verified_endpoints WHERE endpoint_id = %s', (endpoint_id,)) is not None
                    
                    if not verified_exists:
                        # Add to verified_endpoints
                        Database.execute(
                            'INSERT INTO verified_endpoints (endpoint_id, verification_date) VALUES (%s, %s)',
                            (endpoint_id, now)
                        )
                        if verbose:
                            print(f"[VERBOSE] Added {ip}:11434 to verified_endpoints table")
                    else:
                        # Update verification date
                        Database.execute(
                            'UPDATE verified_endpoints SET verification_date = %s WHERE endpoint_id = %s',
                            (now, endpoint_id)
                        )
                        if verbose:
                            print(f"[VERBOSE] Updated existing verified endpoint {ip}:11434")
                    
                    # Add models to the database
                    if verbose:
                        print(f"[VERBOSE] Adding server {ip}:11434 to database with {model_count} models")
                    add_server_to_db(ip, tags_data["models"], ps_data, db_path)
                    
                    total_time = (datetime.now() - verification_start).total_seconds()
                    
                    if result_queue:
                        result = {
                            "ip": ip,
                            "port": 11434,
                            "verified": True,
                            "model_count": model_count,
                            "verification_time": verification_time,
                            "total_time": total_time
                        }
                        result_queue.put(result)
                    
                    return True, endpoint_id, model_count
                else:
                    # No models found, mark as invalid
                    if verbose:
                        print(f"[VERBOSE] No models found at {ip}:11434")
                    
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    Database.execute(
                        'UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s',
                        (now, endpoint_id)
                    )
                    
                    if result_queue:
                        result = {
                            "ip": ip,
                            "port": 11434,
                            "verified": False,
                            "reason": "No models found",
                            "verification_time": verification_time
                        }
                        result_queue.put(result)
                    
                    return False, endpoint_id, 0
            except ValueError as e:
                # JSON parsing error
                if verbose:
                    print(f"[VERBOSE] Error parsing JSON from {ip}:11434: {str(e)}")
                
                # Mark as invalid
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                Database.execute(
                    'UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s',
                    (now, endpoint_id)
                )
                
                if result_queue:
                    result = {
                        "ip": ip,
                        "port": 11434,
                        "verified": False,
                        "reason": "Invalid JSON response",
                        "verification_time": verification_time
                    }
                    result_queue.put(result)
                
                return False, endpoint_id, 0
        else:
            # Non-200 response code
            if verbose:
                print(f"[VERBOSE] Invalid response from {ip}:11434: status code {tags_response.status_code}")
            
            # Mark as invalid
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            Database.execute(
                'UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s',
                (now, endpoint_id)
            )
            
            if result_queue:
                result = {
                    "ip": ip,
                    "port": 11434,
                    "verified": False,
                    "reason": f"Invalid status code: {tags_response.status_code}",
                    "verification_time": verification_time
                }
                result_queue.put(result)
            
            return False, endpoint_id, 0
    
    except requests.Timeout:
        # Connection timeout
        if verbose:
            print(f"[VERBOSE] Connection timeout for {ip}:11434")
        
        # Mark as invalid if we got here
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        Database.execute('UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s', (now, endpoint_id))
        # Remove from verified_endpoints if it was there
        Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = %s', (endpoint_id,))
        
        if result_queue:
            result = {
                "ip": ip,
                "port": 11434,
                "verified": False,
                "reason": "Connection timeout",
                "verification_time": timeout
            }
            result_queue.put(result)
        
        return False, endpoint_id, 0
    
    except requests.RequestException as e:
        # Other request error
        if verbose:
            print(f"[VERBOSE] Request error for {ip}:11434: {str(e)}")
        
        # Mark as invalid if endpoint_id is defined
        if 'endpoint_id' in locals():
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            Database.execute('UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s', (now, endpoint_id))
            Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = %s', (endpoint_id,))
        
        if result_queue:
            result = {
                "ip": ip,
                "port": 11434,
                "verified": False,
                "reason": f"Request error: {str(e)}",
                "verification_time": 0
            }
            result_queue.put(result)
        
        return False, endpoint_id if 'endpoint_id' in locals() else None, 0
    
    except Exception as e:
        # Any other error
        if verbose:
            print(f"[VERBOSE] Unexpected error verifying {ip}:11434: {str(e)}")
        
        # Try to mark as invalid if endpoint_id is defined
        if 'endpoint_id' in locals():
            try:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                Database.execute('UPDATE endpoints SET verified = 2, verification_date = %s WHERE id = %s', (now, endpoint_id))
                Database.execute('DELETE FROM verified_endpoints WHERE endpoint_id = %s', (endpoint_id,))
            except Exception as db_error:
                if verbose:
                    print(f"[VERBOSE] Error updating database: {str(db_error)}")
        
        if result_queue:
            result = {
                "ip": ip,
                "port": 11434,
                "verified": False,
                "reason": f"Unexpected error: {str(e)}",
                "verification_time": 0
            }
            result_queue.put(result)
        
        return False, endpoint_id if 'endpoint_id' in locals() else None, 0

def add_server_to_db(ip, models_data, ps_data, db_path):
    """Add a server and its models to the database"""
    try:
        # Get current timestamp
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check if the endpoint already exists
        endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, 11434))
        
        if endpoint_row:
            # Endpoint exists, update scan date and mark as verified
            endpoint_id = endpoint_row[0]
            Database.execute('UPDATE endpoints SET scan_date = %s, verified = 1, verification_date = %s WHERE id = %s', 
                          (now, now, endpoint_id))
        else:
            # Insert new endpoint
            Database.execute(
                'INSERT INTO endpoints (ip, port, scan_date, verified, verification_date) VALUES (%s, %s, %s, 1, %s)',
                (ip, 11434, now, now)
            )
            # Get the new ID
            endpoint_row = Database.fetch_one('SELECT id FROM endpoints WHERE ip = %s AND port = %s', (ip, 11434))
            endpoint_id = endpoint_row[0]
        
        # Add to verified_endpoints table
        verified_exists = Database.fetch_one('SELECT id FROM verified_endpoints WHERE endpoint_id = %s', (endpoint_id,)) is not None
        
        if not verified_exists:
            Database.execute(
                'INSERT INTO verified_endpoints (endpoint_id, verification_date) VALUES (%s, %s)',
                (endpoint_id, now)
            )
        else:
            Database.execute(
                'UPDATE verified_endpoints SET verification_date = %s WHERE endpoint_id = %s',
                (now, endpoint_id)
            )
        
        # Process models
        for model in models_data:
            name = model.get("name", "Unknown")
            
            # Check if model exists for this endpoint
            model_exists = Database.fetch_one(
                'SELECT id FROM models WHERE endpoint_id = %s AND name = %s',
                (endpoint_id, name)
            ) is not None
            
            # Process model details
            size = model.get("size", 0)
            size_mb = size / (1024 * 1024) if size else 0
            
            details = model.get("details", {})
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
                # Insert new model
                Database.execute(
                    '''INSERT INTO models 
                    (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)''',
                    (endpoint_id, name, param_size, quant_level, size_mb)
                )
        
        return True
    except Exception as e:
        print(f"Error adding server to database: {e}")
        return False

def verify_instances(ip_list, num_threads=50, verbose=False):
    """Verify a list of IP addresses for Ollama instances"""
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
            if result and result.get('verified', False):
                stats['valid'] += 1
            else:
                # Either False or error
                if result and 'reason' in result and 'error' in result['reason'].lower():
                    stats['errors'] += 1
                else:
                    stats['invalid'] += 1
                
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
            if stats['completed'] % 10 == 0 or stats['completed'] == stats['total'] or verbose:
                print(f"\n[PROGRESS] Verification: {stats['completed']}/{stats['total']} ({percent:.1f}%)")
                print(f"[STATS] Valid: {stats['valid']}, Invalid: {stats['invalid']}, Errors: {stats['errors']}")
                print(f"[TIME] Elapsed: {str(elapsed).split('.')[0]}, ETA: {str(eta).split('.')[0]}")
                
                # Print rate information
                if elapsed_seconds > 0:
                    verify_rate = stats['completed'] / elapsed_seconds
                    print(f"[RATE] {verify_rate:.2f} endpoints/second")
    
    if verbose:
        print(f"[VERBOSE] Creating thread pool with {num_threads} workers")
    
    # Create a thread pool
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit the tasks
        verified_results = []
        futures = []
        
        for item in ip_list:
            # Extract IP from different formats (handle both string IPs and dict-formatted results)
            if isinstance(item, dict):
                ip = item.get('ip_str', '')
            else:
                ip = item
                
            if ip:
                # Submit task to thread pool
                future = executor.submit(verify_instance, ip, None, 5, result_queue, verbose)
                futures.append(future)
                
                # Set up callback for when verification completes
                def callback_factory(ip, future):
                    def callback(fut):
                        try:
                            result = fut.result()
                            if result and result[0]:  # If verification was successful
                                # result is (True, endpoint_id, model_count) for successful verifications
                                verified_results.append({
                                    'ip': ip,
                                    'port': 11434,
                                    'endpoint_id': result[1],
                                    'model_count': result[2]
                                })
                            update_progress(result_queue.get(timeout=1) if not result_queue.empty() else None)
                        except Exception as e:
                            if verbose:
                                print(f"[ERROR] Callback error for {ip}: {str(e)}")
                    return callback
                
                future.add_done_callback(callback_factory(ip, future))
        
        if verbose:
            print(f"[VERBOSE] All verification tasks submitted, waiting for completion")
        
        # Wait for all tasks to complete
        for future in futures:
            try:
                future.result()
            except Exception as e:
                if verbose:
                    print(f"[ERROR] Exception in verification thread: {str(e)}")
    
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
    
    return verified_results

def save_to_database(verified_results):
    """Save verified results to database"""
    if not verified_results:
        return
    
    print(f"Saving {len(verified_results)} verified instances to database...")
    
    for result in verified_results:
        ip = result.get('ip')
        port = result.get('port', 11434)
        endpoint_id = result.get('endpoint_id')
        
        if not ip or not endpoint_id:
            continue
        
        # Make sure the endpoint is marked as verified
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Update endpoint verification status
        Database.execute(
            'UPDATE endpoints SET verified = 1, verification_date = %s WHERE id = %s',
            (now, endpoint_id)
        )
        
        # Ensure entry exists in verified_endpoints
        verified_exists = Database.fetch_one(
            'SELECT id FROM verified_endpoints WHERE endpoint_id = %s',
            (endpoint_id,)
        ) is not None
        
        if not verified_exists:
            Database.execute(
                'INSERT INTO verified_endpoints (endpoint_id, verification_date) VALUES (%s, %s)',
                (endpoint_id, now)
            )
    
    print("Database update complete.")

def run_scan(scan_method='shodan', input_file=None, continuous=False, interval=3600, num_threads=1, verbose=False):
    """
    Run Ollama scanner to find instances
    
    Args:
        scan_method: Method to use for scanning ('shodan', 'censys', or 'masscan')
        input_file: File containing IP addresses to scan for masscan method
        continuous: Whether to run the scanner continuously
        interval: Time in seconds between scans when running continuously
        num_threads: Number of concurrent threads to use for scanning
        verbose: Enable verbose output
    """
    global last_check_time
    
    makeDatabase()
    
    # Run once or continuously
    while True:
        if scan_method in ["shodan", "censys", "masscan"]:
            print(f"Starting scan using {scan_method}...")
            if scan_method == "shodan":
                results = search_shodan()
            elif scan_method == "censys":
                results = search_censys()
            elif scan_method == "masscan":
                if not input_file:
                    print("Error: Input file required for masscan method")
                    exit(1)
                results = parse_masscan_results(input_file)
            
            if not results:
                print("No results found.")
            else:
                print(f"Found {len(results)} potential Ollama instances.")
                print("Verifying instances...")
                
                # Use a thread pool to verify instances concurrently
                verified_results = verify_instances(results, num_threads=num_threads, verbose=verbose)
                
                if verified_results:
                    print(f"Found {len(verified_results)} verified Ollama instances.")
                    save_to_database(verified_results)
                    last_check_time = time.time()
                else:
                    print("No verified Ollama instances found.")
        else:
            print(f"Invalid scan method: {scan_method}")
            exit(1)
        
        # Exit if not running continuously
        if not continuous:
            break
        
        # Sleep for the specified interval
        print(f"Sleeping for {interval} seconds...")
        time.sleep(interval)

def show_menu():
    """Display interactive menu for scanner options"""
    print("\n=========================================")
    print("       OLLAMA SCANNER MENU               ")
    print("=========================================")
    print("1. Scan using masscan results")
    print("2. Scan using Shodan API")
    print("3. Scan using Censys API")
    print("4. Prune duplicates from database")
    print("5. Exit")
    print("-----------------------------------------")
    
    choice = input("Enter your choice (1-5): ")
    
    if choice == '1':
        masscan_file = input("Enter path to masscan output file (res.txt): ") or "res.txt"
        if not os.path.exists(masscan_file):
            print(f"Error: File {masscan_file} does not exist")
            return
        
        num_threads = input("Enter number of threads (default 10): ") or "10"
        run_scan(scan_method='masscan', input_file=masscan_file, num_threads=int(num_threads))
        
    elif choice == '2':
        if not SHODAN_API_KEY:
            key = input("Shodan API key not found. Enter your Shodan API key: ")
            if key:
                os.environ["SHODAN_API_KEY"] = key
                global shodan_client
                shodan_client = shodan.Shodan(key)
            else:
                print("No API key provided. Cannot continue with Shodan scan.")
                return
                
        num_threads = input("Enter number of threads (default 10): ") or "10"
        run_scan(scan_method='shodan', num_threads=int(num_threads))
        
    elif choice == '3':
        if not censys_available:
            print("Censys module not installed. Run 'pip install censys' to enable Censys searching.")
            return
            
        if not CENSYS_API_ID or not CENSYS_API_SECRET:
            censys_id = input("Censys API ID not found. Enter your Censys API ID: ")
            censys_secret = input("Enter your Censys API Secret: ")
            
            if censys_id and censys_secret:
                os.environ["CENSYS_API_ID"] = censys_id
                os.environ["CENSYS_API_SECRET"] = censys_secret
            else:
                print("API credentials not provided. Cannot continue with Censys scan.")
                return
                
        num_threads = input("Enter number of threads (default 10): ") or "10"
        run_scan(scan_method='censys', num_threads=int(num_threads))
        
    elif choice == '4':
        removeDuplicates()
        
    elif choice == '5':
        print("Exiting...")
        sys.exit(0)
        
    else:
        print("Invalid choice, please try again")

if __name__ == "__main__":
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Tool to find Ollama instances using Shodan, Censys, and masscan')
    parser.add_argument('--continuous', '-c', action='store_true', help='Run scanner continuously')
    parser.add_argument('--interval', '-i', type=int, default=3600, 
                       help='Interval in seconds between scans when running continuously (default: 3600)')
    parser.add_argument('--prune', '-p', action='store_true', 
                       help='Prune duplicate entries from the database')
    parser.add_argument('--threads', '-t', type=int, default=10,
                       help='Number of concurrent threads to use for scanning (default: 10)')
    parser.add_argument('--method', '-m', choices=['masscan', 'shodan', 'censys', 'menu'], default='menu',
                       help='Scanning method to use (default: menu)')
    parser.add_argument('--input', '-f', type=str, default='res.txt',
                       help='Input file for masscan method (default: res.txt)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Use verbose directly from args
    verbose = args.verbose
    
    if args.prune:
        # Just prune the database
        print("Pruning duplicate entries from database...")
        makeDatabase()  # Ensure the database exists
        removeDuplicates()
    elif args.method == 'menu':
        # Show interactive menu
        show_menu()
    else:
        # Run the scan with specified method
        run_scan(
            scan_method=args.method,
            input_file=args.input if args.method == 'masscan' else None,
            continuous=args.continuous,
            interval=args.interval,
            num_threads=args.threads,
            verbose=verbose
        ) 