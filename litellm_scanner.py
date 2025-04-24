#!/usr/bin/env python3
"""
LiteLLM Proxy Scanner - h4x0r t00l 2 f1nd LiteLLM proxy endpoints
Scans for open LiteLLM proxy instances and catalogs their available models
"""

import os
import sys
import sqlite3
import requests
import json
import time
import re
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv

# Added by migration script
from database import Database, init_database

# Load environment variables
load_dotenv()

# Constants
# TODO: Replace SQLite-specific code: DB_FILE = 'litellm_endpoints.db'  # Separate DB for now, will merge later
TIMEOUT = 5  # seconds
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
OUTPUT_FILE = 'litellm_instances.txt'  # File to output discovered endpoints
MAX_RESULTS = 100  # Results per page from Shodan

# Use the Shodan API key from environment or from ollama_scanner.py
SHODAN_API_KEY = os.getenv('SHODAN_API_KEY')
if not SHODAN_API_KEY:
    # Fallback to the key in ollama_scanner.py if available
    try:
        with open('/home/adam/Documents/Code/Ollama_Scanner/ollama_scanner.py', 'r') as f:
            content = f.read()
            key_match = re.search(r'SHODAN_API_KEY\s*=\s*["\']([^"\']+)["\']', content)
            if key_match:
                SHODAN_API_KEY = key_match.group(1)
    except:
        # If we can't read the file or find the key, we'll handle this later
        pass

def init_database():
    """Initialize the database with necessary tables"""
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Create servers table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY,
            hostname TEXT,
            port INTEGER,
            url TEXT,
            is_secure INTEGER,
            scan_date TEXT
        )
        ''')
        
        # Create models table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY,
            server_id INTEGER,
            model_name TEXT,
            provider TEXT,
            parameter_size TEXT,
            api_base TEXT,
            model_id TEXT,
            FOREIGN KEY (server_id) REFERENCES servers (id)
        )
        ''')
        
        # Commit handled by Database methods
        conn.close()
        print("D4tabase initialized!")
        return True
    except sqlite3.Error as e:
        print(f"DATAB4SE ERR0R: {e}")
        return False

def check_litellm_endpoint(url, verbose=False):
    """Check if a given URL is a LiteLLM proxy endpoint
    
    Args:
        url (str): The URL to check
        verbose (bool): Whether to print verbose output
        
    Returns:
        tuple: (is_litellm, model_data, error_message)
    """
    headers = {'User-Agent': USER_AGENT}
    
    if verbose:
        print(f"PR0BING: {url}")
    
    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"  # Default to HTTPS
    
    # Try both with and without trailing slash
    normalized_url = url.rstrip('/')
    
    # Store any error message
    error_msg = None
    
    try:
        # Try the model info endpoint (main indicator)
        info_url = f"{normalized_url}/v1/model/info"
        info_response = requests.get(info_url, headers=headers, timeout=TIMEOUT, verify=False)
        
        if info_response.status_code == 200:
            try:
                data = info_response.json()
                if 'data' in data and isinstance(data['data'], list):
                    if verbose:
                        print(f"SUCC3SS! Valid LiteLLM proxy at {url}")
                    return True, data, None
            except json.JSONDecodeError:
                error_msg = "Invalid JSON response from /v1/model/info"
        
        # If info endpoint didn't work, try the models endpoint
        models_url = f"{normalized_url}/v1/models"
        models_response = requests.get(models_url, headers=headers, timeout=TIMEOUT, verify=False)
        
        if models_response.status_code == 200:
            try:
                data = models_response.json()
                if 'data' in data and isinstance(data['data'], list):
                    # Convert to expected format
                    model_info_data = {"data": []}
                    for model in data.get('data', []):
                        if isinstance(model, dict) and 'id' in model:
                            model_info_data["data"].append({
                                "model_name": model.get('id', ''),
                                "litellm_params": {
                                    "model": model.get('id', ''),
                                    "api_base": normalized_url
                                }
                            })
                    if verbose:
                        print(f"SUCC3SS! Valid LiteLLM proxy at {url} (via /models)")
                    return True, model_info_data, None
            except json.JSONDecodeError:
                error_msg = "Invalid JSON response from /v1/models"
        
        # If we got 401/403, it's probably a LiteLLM proxy but requires auth
        if info_response.status_code in (401, 403) or models_response.status_code in (401, 403):
            error_msg = "Authentication required"
            if verbose:
                print(f"AUTH REQUIRED: {url}")
            return False, None, error_msg
        
        # Try the health endpoint as a last resort
        health_url = f"{normalized_url}/health"
        health_response = requests.get(health_url, headers=headers, timeout=TIMEOUT, verify=False)
        
        if health_response.status_code == 200:
            try:
                health_data = health_response.json()
                # If has expected health structure, it's probably LiteLLM
                if isinstance(health_data, dict) and ('status' in health_data or 'healthcheck' in health_data):
                    # Return an empty data structure
                    if verbose:
                        print(f"PARTIAL MATCH! LiteLLM health endpoint found at {url}")
                    return True, {"data": []}, None
            except json.JSONDecodeError:
                pass
        
        if error_msg is None:
            error_msg = f"Not a LiteLLM API (status: info={info_response.status_code}, models={models_response.status_code})"
        
        if verbose:
            print(f"N0T FOUND: {url} - {error_msg}")
        
        return False, None, error_msg
        
    except requests.exceptions.Timeout:
        if verbose:
            print(f"TIMEOUT: {url}")
        return False, None, "Connection timeout"
    except requests.exceptions.SSLError as e:
        if verbose:
            print(f"SSL ERR0R: {url} - {e}")
        # Try HTTP if HTTPS failed
        if url.startswith("https://"):
            http_url = url.replace("https://", "http://")
            if verbose:
                print(f"Retrying with HTTP: {http_url}")
            return check_litellm_endpoint(http_url, verbose)
        return False, None, f"SSL Error: {str(e)}"
    except requests.exceptions.ConnectionError:
        if verbose:
            print(f"C0NNECTION ERR0R: {url}")
        # Try HTTP if HTTPS failed
        if url.startswith("https://"):
            http_url = url.replace("https://", "http://")
            if verbose:
                print(f"Retrying with HTTP: {http_url}")
            return check_litellm_endpoint(http_url, verbose)
        return False, None, "Connection refused"
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"REQUEST ERR0R: {url} - {e}")
        return False, None, f"Request failed: {str(e)}"

def parse_model_info(model_data):
    """Parse model data from LiteLLM API response"""
    models = []
    
    if not model_data or 'data' not in model_data:
        return models
    
    for model in model_data['data']:
        if not isinstance(model, dict):
            continue
            
        model_name = model.get('model_name', '')
        if not model_name and 'litellm_params' in model and 'model' in model['litellm_params']:
            model_name = model['litellm_params']['model']
        
        # Skip if no model name found
        if not model_name:
            continue
            
        # Get litellm params
        litellm_params = model.get('litellm_params', {})
        api_base = litellm_params.get('api_base', '')
        
        # Get provider from model name or API base
        provider = "unknown"
        if "openai" in model_name.lower() or "gpt" in model_name.lower():
            provider = "openai"
        elif "anthropic" in model_name.lower() or "claude" in model_name.lower():
            provider = "anthropic"
        elif "llama" in model_name.lower():
            provider = "meta"
        elif "mistral" in model_name.lower():
            provider = "mistral"
        
        # Try to extract parameter size from model name
        parameter_size = "unknown"
        param_pattern = r'(?:^|\D)(\d+\.?\d*)B'  # Match numbers followed by 'B' (e.g., 7B, 13B)
        param_match = re.search(param_pattern, model_name, re.IGNORECASE)
        if param_match:
            parameter_size = f"{param_match.group(1)}B"
        
        # Get model ID if available
        model_id = model.get('model_info', {}).get('id', '')
        
        models.append({
            'model_name': model_name,
            'provider': provider,
            'parameter_size': parameter_size,
            'api_base': api_base,
            'model_id': model_id
        })
    
    return models

def save_endpoint(url, model_data, verbose=False):
    """Save LiteLLM endpoint and models to database and output file
    
    Returns:
        int: server_id or -1 if failed
    """
    try:
        # Parse the URL
        parsed_url = urlparse(url)
        hostname = parsed_url.netloc.split(':')[0] if ':' in parsed_url.netloc else parsed_url.netloc
        port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
        is_secure = 1 if parsed_url.scheme == 'https' else 0
        
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Check if this endpoint already exists
        cursor.execute(
            "SELECT id FROM servers WHERE hostname = ? AND port = ?", 
            (hostname, port)
        )
        existing = Database.fetch_one(query, params)
        
        if existing:
            server_id = existing[0]
            # Update scan date
            cursor.execute(
                "UPDATE servers SET scan_date = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), server_id)
            )
            # Delete old models
            Database.execute("DELETE FROM models WHERE server_id = ?", (server_id,))
            if verbose:
                print(f"Updating existing endpoint: {url}")
        else:
            # Insert new server
            cursor.execute(
                "INSERT INTO servers (hostname, port, url, is_secure, scan_date) VALUES (?, ?, ?, ?, ?)",
                (hostname, port, url, is_secure, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            server_id = cursor.lastrowid
            if verbose:
                print(f"Added new endpoint: {url}")
        
        # Parse and save models
        models = parse_model_info(model_data)
        
        model_count = 0
        for model in models:
            cursor.execute(
                """
                INSERT INTO models 
                (server_id, model_name, provider, parameter_size, api_base, model_id) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    server_id, 
                    model['model_name'], 
                    model['provider'],
                    model['parameter_size'],
                    model['api_base'],
                    model['model_id']
                )
            )
            model_count += 1
        
        # Commit handled by Database methods
        conn.close()
        
        # Also save to text file
        with open(OUTPUT_FILE, 'a') as f:
            f.write(f"====== LITELLM ENDP0INT ======\n")
            f.write(f"URL: {url}\n")
            f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Models Found: {model_count}\n")
            
            for model in models:
                f.write(f"  - {model['model_name']} ({model['provider']}, {model['parameter_size']})\n")
                if model['api_base']:
                    f.write(f"    API Base: {model['api_base']}\n")
            
            f.write("\n")
        
        if verbose:
            print(f"SAVED: {url} with {model_count} models to database and {OUTPUT_FILE}")
        
        return server_id
        
    except sqlite3.Error as e:
        print(f"DATAB4SE ERR0R while saving {url}: {e}")
        return -1

def scan_from_shodan(api_key=None, verbose=False, test_mode=False):
    """Scan for LiteLLM proxy endpoints using Shodan API with pagination (similar to ollama_scanner)"""
    api_key = api_key or SHODAN_API_KEY
    
    if not api_key:
        print("ERR0R: Shodan API key not found. Fix ur .env file, n00b.")
        return []
    
    try:
        import shodan
    except ImportError:
        print("ERR0R: Shodan module not installed. Run 'pip install shodan' first!")
        return []
    
    print("----------------------------------------")
    print("  LiteLLM Scanner - Find AI Proxies!  ")
    print("----------------------------------------")
    print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"H4cking int0 sh0dan to find LiteLLM proxies...")
    
    api = shodan.Shodan(api_key)
    
    # Search queries to find potential LiteLLM endpoints
    search_queries = [
        'title:"LiteLLM"',
        'http.component:"fastapi" title:"LiteLLM"',
        'http.component:"fastapi" "v1/model/info"',
        'http.component:"fastapi" "litellm"',
        '"OpenAI" "v1/chat/completions" -nginx -apache',
        '"text-embedding" "v1/embeddings" -nginx -apache',
        'title:"API" "/v1/models" -nginx -apache'
    ]
    
    # When in test mode, only use the first query and limit results
    if test_mode:
        print("RUNNING IN TEST MODE - Limited results")
        search_queries = search_queries[:1]  # Only use the first query
        max_results_per_query = 5  # Limit results in test mode
        max_pages = 1  # Only check one page in test mode
    else:
        max_results_per_query = 500
        max_pages = 10
    
    endpoints_found = []
    total_valid_count = 0
    total_error_count = 0
    query_count = 0
    
    for query in search_queries:
        query_count += 1
        print(f"[*] Running Shodan search {query_count}/{len(search_queries)}: {query}")
        
        page = 1
        total_results = []
        
        # Get results page by page
        while True:
            try:
                print(f"Fetching page {page}...")
                results = api.search(query, page=page, limit=MAX_RESULTS)
                
                if not results['matches']:
                    print("No more results found.")
                    break
                
                total_results.extend(results['matches'])
                print(f"Found {len(results['matches'])} results on page {page}")
                
                # Shodan has a rate limit, so we need to wait between requests
                time.sleep(1)
                
                page += 1
                
                # If we've collected enough results or hit the maximum page limit, stop
                if len(total_results) >= max_results_per_query or page > max_pages:
                    print(f"Reached limit of {len(total_results)} results or max pages.")
                    break
                
            except shodan.APIError as e:
                if 'Invalid page' in str(e) or 'No more results' in str(e):
                    print("No more pages available.")
                    break
                else:
                    print(f"[-] Sh0dan API err0r: {e}")
                    break
        
        print(f"Total potential LiteLLM endpoints found: {len(total_results)}")
        
        valid_count = 0
        error_count = 0
        
        # Check each result
        for i, result in enumerate(total_results):
            ip = result['ip_str']
            port = result.get('port', 80)
            
            # Show progress
            progress = (i + 1) / len(total_results) * 100
            print(f"[{i+1}/{len(total_results)}] ({progress:.1f}%) Trying {ip}:{port}...")
            
            # Check both HTTP and HTTPS
            protocols = ['https', 'http']
            
            server_valid = False
            for protocol in protocols:
                url = f"{protocol}://{ip}:{port}"
                
                # Skip if we already checked this endpoint
                if url in endpoints_found:
                    continue
                
                try:
                    is_litellm, model_data, error = check_litellm_endpoint(url, verbose)
                    
                    if is_litellm:
                        valid_count += 1
                        total_valid_count += 1
                        models = parse_model_info(model_data)
                        models_count = len(models)
                        
                        print(f"PWNED! Valid LiteLLM proxy at {url} with {models_count} models")
                        for model in models:
                            print(f"  - {model['model_name']} ({model['provider']})")
                        
                        save_endpoint(url, model_data)
                        endpoints_found.append(url)
                        server_valid = True
                        break  # No need to try other protocols
                    elif verbose:
                        print(f"Not a LiteLLM endpoint: {url} - {error}")
                
                except Exception as e:
                    error_count += 1
                    total_error_count += 1
                    print(f"ERROR scanning {url}: {str(e)}")
            
            if not server_valid and verbose:
                print(f"No valid LiteLLM endpoints found at {ip}:{port}")
            
            # Add a small delay to avoid overwhelming servers
            time.sleep(0.5)
        
        print(f"Results for query {query_count}/{len(search_queries)}:")
        print(f"- Endpoints checked: {len(total_results)}")
        print(f"- Valid LiteLLM proxies: {valid_count}")
        print(f"- Errors during scanning: {error_count}")
        print("---")
        
        # If in test mode, only process one query
        if test_mode and query_count >= 1:
            print("TEST MODE: Stopping after first query")
            break
    
    print(f"\nScan finished. Overall results:")
    print(f"- Total servers checked: {len(total_results) * query_count}")
    print(f"- Valid LiteLLM proxies found: {total_valid_count}")
    print(f"- Errors during scanning: {total_error_count}")
    print(f"Results saved to database: {DB_FILE}")
    print(f"Results also saved to text file: {OUTPUT_FILE}")
    print("All done!")
    
    return endpoints_found

def scan_from_file(file_path, verbose=False):
    """Scan LiteLLM proxies from a file of URLs"""
    if not os.path.exists(file_path):
        print(f"ERR0R: File {file_path} not found!")
        return []
    
    print(f"[*] Scanning LiteLLM proxies from {file_path}...")
    
    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    endpoints_found = []
    valid_count = 0
    error_count = 0
    
    print(f"Total URLs to check: {len(urls)}")
    
    for i, url in enumerate(urls):
        # Show progress
        progress = (i + 1) / len(urls) * 100
        print(f"[{i+1}/{len(urls)}] ({progress:.1f}%) Trying {url}...")
        
        try:
            is_litellm, model_data, error = check_litellm_endpoint(url, verbose)
            
            if is_litellm:
                valid_count += 1
                models = parse_model_info(model_data)
                models_count = len(models)
                
                print(f"PWNED! Valid LiteLLM proxy at {url} with {models_count} models")
                for model in models:
                    print(f"  - {model['model_name']} ({model['provider']})")
                
                save_endpoint(url, model_data)
                endpoints_found.append(url)
            elif verbose:
                print(f"Not a LiteLLM endpoint: {url} - {error}")
        
        except Exception as e:
            error_count += 1
            print(f"ERROR scanning {url}: {str(e)}")
        
        # Avoid rate limiting
        time.sleep(0.5)
    
    print(f"\nScan finished. Results:")
    print(f"- Total URLs checked: {len(urls)}")
    print(f"- Valid LiteLLM proxies: {valid_count}")
    print(f"- Errors during scanning: {error_count}")
    print(f"Results saved to database: {DB_FILE}")
    print(f"Results also saved to text file: {OUTPUT_FILE}")
    
    return endpoints_found

def scan_single_url(url, verbose=True):
    """Scan a single URL for LiteLLM proxy"""
    print(f"[*] Scanning URL: {url}")
    
    try:
        is_litellm, model_data, error = check_litellm_endpoint(url, verbose)
        
        if is_litellm:
            print(f"[+] PWNED! Valid LiteLLM proxy at {url}")
            models = parse_model_info(model_data)
            print(f"    Found {len(models)} models")
            for model in models:
                print(f"    - {model['model_name']} ({model['provider']})")
            
            save_endpoint(url, model_data)
            return True
        else:
            print(f"[-] Not a LiteLLM endpoint: {url} - {error}")
            return False
    except Exception as e:
        print(f"ERROR scanning {url}: {str(e)}")
        return False

def list_endpoints():
    """List all endpoints in the database"""
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        cursor.execute("""
            SELECT s.id, s.hostname, s.port, s.url, s.is_secure, s.scan_date, COUNT(m.id) as model_count
            FROM servers s
            LEFT JOIN models m ON s.id = m.server_id
            GROUP BY s.id
            ORDER BY s.scan_date DESC
        """)
        
        servers = Database.fetch_all(query, params)
        
        print("\n==== LiteLLM Endpoints ====")
        print(f"Total endpoints: {len(servers)}")
        print(f"{'URL':<40} {'Scan Date':<20} {'Models':<10}")
        print("-" * 70)
        
        for server in servers:
            server_id, hostname, port, url, is_secure, scan_date, model_count = server
            print(f"{url:<40} {scan_date:<20} {model_count:<10}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"DATAB4SE ERR0R: {e}")

def list_models():
    """List all models in the database"""
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        cursor.execute("""
            SELECT m.model_name, m.provider, m.parameter_size, COUNT(*) as endpoint_count
            FROM models m
            GROUP BY m.model_name, m.provider, m.parameter_size
            ORDER BY endpoint_count DESC
        """)
        
        models = Database.fetch_all(query, params)
        
        print("\n==== LiteLLM Models ====")
        print(f"Total unique models: {len(models)}")
        print(f"{'Model Name':<40} {'Provider':<15} {'Parameters':<10} {'Endpoints':<10}")
        print("-" * 75)
        
        for model in models:
            model_name, provider, parameter_size, endpoint_count = model
            print(f"{model_name:<40} {provider:<15} {parameter_size:<10} {endpoint_count:<10}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"DATAB4SE ERR0R: {e}")

def main():
    """Main function"""
    # Initialize the database
    if not init_database():
        return
    
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="LiteLLM Proxy Scanner - f1nd unpr0tected AI pr0xy endpoints")
    
    parser.add_argument('-s', '--shodan', action='store_true', 
                        help='Scan for LiteLLM proxies using Shodan')
    parser.add_argument('-f', '--file', type=str, 
                        help='Scan LiteLLM proxies from a file of URLs')
    parser.add_argument('-u', '--url', type=str, 
                        help='Check a single URL for LiteLLM proxy')
    parser.add_argument('-l', '--list', action='store_true',
                        help='List all endpoints in the database')
    parser.add_argument('-m', '--models', action='store_true',
                        help='List all models in the database')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print verbose output')
    parser.add_argument('-k', '--key', type=str,
                        help='Shodan API key (if not in .env file)')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Test mode - limit Shodan queries and results')
    
    args = parser.parse_args()
    
    # Disable warnings for insecure requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Print banner
    print("██╗     ██╗████████╗███████╗██╗     ██╗     ███╗   ███╗")
    print("██║     ██║╚══██╔══╝██╔════╝██║     ██║     ████╗ ████║")
    print("██║     ██║   ██║   █████╗  ██║     ██║     ██╔████╔██║")
    print("██║     ██║   ██║   ██╔══╝  ██║     ██║     ██║╚██╔╝██║")
    print("███████╗██║   ██║   ███████╗███████╗███████╗██║ ╚═╝ ██║")
    print("╚══════╝╚═╝   ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝     ╚═╝")
    print("       ╔═╗╔═╗╔═╗╔╗╔╔╗╔╔═╗╦═╗  ╦  ╦╔╦╗╔═╗╦╔═╗         ")
    print("       ╚═╗║  ╠═╣║║║║║║║╣ ╠╦╝  ║  ║ ║ ║╣ ║║╣          ")
    print("       ╚═╝╚═╝╩ ╩╝╚╝╝╚╝╚═╝╩╚═  ╩═╝╩ ╩ ╚═╝╩╚═╝         ")
    print("\n        f1nd unpr0tected AI pr0xy endpoints\n")
    
    if args.list:
        list_endpoints()
    elif args.models:
        list_models()
    elif args.shodan:
        scan_from_shodan(args.key, args.verbose, args.test)
    elif args.file:
        scan_from_file(args.file, args.verbose)
    elif args.url:
        scan_single_url(args.url, args.verbose)
    else:
        parser.print_help()
        
if __name__ == "__main__":
    main() 