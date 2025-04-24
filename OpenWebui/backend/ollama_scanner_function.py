#!/usr/bin/env python3
"""
Ollama Scanner Integration Function for OpenWebUI
-------------------------------------------------
This function integrates the Ollama Scanner capabilities into OpenWebUI,
allowing for discovery, search, and addition of Ollama endpoints.
"""

import os
import json
import time
import sqlite3
import requests
from datetime import datetime
import logging
from typing import Dict, List, Any, Tuple, Optional, Union

# Added by migration script
from database import Database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ollama_scanner_function")

# Constants
DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_MAX_RESULTS = 100  # max number of Shodan results to process
DATA_DIR = "/app/backend/data"  # OpenWebUI's persistent data directory
# TODO: Replace SQLite-specific code: DB_FILE = os.path.join(DATA_DIR, "ollama_scanner_results.db")


def setup_database() -> sqlite3.Connection:
    """
    Create or connect to the SQLite database for storing scan results.
    
    Returns:
        sqlite3.Connection: A connection to the SQLite database
    """
    try:
        # Create the data directory if it doesn't exist
        os.makedirs(DATA_DIR, exist_ok=True)
        
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Create servers table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            port INTEGER,
            scan_date TEXT,
            country_code TEXT,
            country_name TEXT,
            city TEXT,
            organization TEXT,
            asn TEXT,
            UNIQUE(ip, port)
        )
        ''')
        
        # Create models table
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
        logger.info(f"Database setup complete: {DB_FILE}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database setup error: {str(e)}")
        raise Exception(f"Failed to set up database: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during database setup: {str(e)}")
        raise


def check_ollama_endpoint(ip: str, port: int = 11434, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[Dict]]:
    """
    Check if the given IP has a valid Ollama instance with /api/tags endpoint.
    
    Args:
        ip (str): The IP address to check
        port (int): The port to check (default: 11434)
        timeout (int): Request timeout in seconds (default: 5)
    
    Returns:
        Tuple[bool, Optional[Dict]]: A tuple of (is_valid, model_data)
    """
    url = f"http://{ip}:{port}/api/tags"
    try:
        response = requests.get(url, timeout=calculate_dynamic_timeout(timeout_flag=args.timeout if "args" in locals() else None))
        if response.status_code == 200:
            try:
                data = response.json()
                if "models" in data and isinstance(data["models"], list):
                    return True, data
            except json.JSONDecodeError:
                pass
        return False, None
    except requests.RequestException:
        return False, None


def save_to_database(conn: sqlite3.Connection, server_info: Dict, model_data: Dict) -> int:
    """
    Save the server and model information to the database.
    
    Args:
        conn (sqlite3.Connection): Database connection
        server_info (Dict): Server information including IP and port
        model_data (Dict): Model data returned from the Ollama API
    
    Returns:
        int: The server ID of the inserted/updated server
    """
    try:
        cursor = # Using Database methods instead of cursor
        
        # Extract server information
        ip = server_info.get('ip_str')
        port = server_info.get('port', 11434)
        country_code = server_info.get('country_code', '')
        country_name = server_info.get('country_name', '')
        city = server_info.get('city', '')
        organization = server_info.get('org', '')
        asn = server_info.get('asn', '')
        
        # Insert or replace server information
        cursor.execute('''
        INSERT OR REPLACE INTO servers 
        (ip, port, scan_date, country_code, country_name, city, organization, asn) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ip, port, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
              country_code, country_name, city, organization, asn))
        
        # Get the server id
        server_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            "SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port)).fetchone()[0]
        
        # Insert model information
        if model_data and "models" in model_data:
            for model in model_data["models"]:
                model_name = model.get("name", "Unknown")
                model_size = model.get("size", 0)
                model_size_mb = model_size / (1024 * 1024) if model_size else 0
                
                details = model.get("details", {})
                param_size = details.get("parameter_size", "Unknown")
                quant_level = details.get("quantization_level", "Unknown")
                
                cursor.execute('''
                INSERT OR REPLACE INTO models 
                (server_id, name, parameter_size, quantization_level, size_mb)
                VALUES (?, ?, ?, ?, ?)
                ''', (server_id, model_name, param_size, quant_level, model_size_mb))
        
        # Commit handled by Database methods
        return server_id
    except sqlite3.Error as e:
        logger.error(f"Database error when saving data: {str(e)}")
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: conn.rollback()
        raise Exception(f"Failed to save data to database: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error when saving data: {str(e)}")
        # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: conn.rollback()
        raise


def perform_shodan_search(api_key: str, search_query: str = 'product:Ollama', 
                         max_results: int = DEFAULT_MAX_RESULTS) -> List[Dict]:
    """
    Perform a search on Shodan for Ollama instances.
    
    Args:
        api_key (str): Shodan API key
        search_query (str): Search query to use (default: 'product:Ollama')
        max_results (int): Maximum number of results to return (default: 100)
    
    Returns:
        List[Dict]: List of Shodan results matching the query
    """
    try:
        # Import Shodan here to avoid making it a hard dependency
        import shodan
        
        api 

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
= shodan.Shodan(api_key)
        
        page = 1
        total_results = []
        
        # Get results page by page
        while True:
            try:
                results = api.search(search_query, page=page, limit=min(100, max_results))
                
                if not results['matches']:
                    break
                    
                total_results.extend(results['matches'])
                logger.info(f"Found {len(results['matches'])} results on page {page}")
                
                # Shodan has a rate limit, so we need to wait between requests
                time.sleep(1)
                
                page += 1
                
                # If we've collected enough results or hit the maximum page limit (20), stop
                if len(total_results) >= max_results or page > 20:
                    break
                    
            except shodan.APIError as e:
                if 'Invalid page' in str(e) or 'No more results' in str(e):
                    break
                else:
                    raise
        
        logger.info(f"Total potential Ollama instances found: {len(total_results)}")
        return total_results
    
    except ImportError:
        logger.error("Shodan module not found. Please install it with 'pip install shodan'")
        raise Exception("Shodan module not found. Please install it with 'pip install shodan'")
    except shodan.APIError as e:
        logger.error(f"Shodan API error: {str(e)}")
        raise Exception(f"Shodan API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during Shodan search: {str(e)}")
        raise


def scan_ollama_instances(api_key: str, search_query: str = 'product:Ollama', 
                         max_results: int = DEFAULT_MAX_RESULTS, timeout: int = DEFAULT_TIMEOUT,
                         ports_to_try: List[int] = [11434, 8000, 8001]) -> Dict:
    """
    Main scanning function that initiates Ollama instance discovery.
    
    Args:
        api_key (str): Shodan API key
        search_query (str): Search query to use (default: 'product:Ollama')
        max_results (int): Maximum number of results to return (default: 100)
        timeout (int): Request timeout in seconds (default: 5)
        ports_to_try (List[int]): List of ports to try for each IP (default: [11434, 8000, 8001])
    
    Returns:
        Dict: Summary of scan results
    """
    try:
        # Setup database
        conn = setup_database()
        
        # Perform Shodan search
        try:
            results = perform_shodan_search(api_key, search_query, max_results)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "valid_count": 0,
                "total_count": 0
            }
        
        valid_count = 0
        error_count = 0
        valid_instances = []
        
        # Check each result
        for i, result in enumerate(results):
            ip = result['ip_str']
            default_port = result.get('port', 11434)
            
            # Progress indicator
            progress = (i + 1) / len(results) * 100
            logger.info(f"[{i+1}/{len(results)}] ({progress:.1f}%) Trying {ip}:{default_port}...")
            
            try:
                # Try different ports if the default doesn't work
                all_ports = [default_port] + [p for p in ports_to_try if p != default_port]
                
                server_valid = False
                for try_port in all_ports:
                    is_valid, model_data = check_ollama_endpoint(ip, try_port, timeout)
                    if is_valid:
                        valid_count += 1
                        models_count = len(model_data.get("models", [])) if model_data else 0
                        
                        # Save to database
                        server_id = save_to_database(conn, {
                            'ip_str': ip, 
                            'port': try_port,
                            'country_code': result.get('location', {}).get('country_code', ''),
                            'country_name': result.get('location', {}).get('country_name', ''),
                            'city': result.get('location', {}).get('city', ''),
                            'org': result.get('org', ''),
                            'asn': result.get('asn', '')
                        }, model_data)
                        
                        # Extract model names for the response
                        model_names = []
                        if model_data and "models" in model_data:
                            model_names = [model.get("name", "") for model in model_data.get("models", [])]
                        
                        valid_instances.append({
                            'server_id': server_id,
                            'ip': ip,
                            'port': try_port,
                            'model_count': models_count,
                            'models': model_names,
                            'country': result.get('location', {}).get('country_name', ''),
                            'city': result.get('location', {}).get('city', ''),
                            'org': result.get('org', '')
                        })
                        
                        logger.info(f"VALID! Found Ollama at {ip}:{try_port} with {models_count} models")
                        server_valid = True
                        break  # No need to try other ports
                    else:
                        logger.debug(f"INVALID - No Ollama found at {ip}:{try_port}")
                
                if not server_valid:
                    logger.info(f"No valid Ollama endpoints found at {ip}")
            
            except Exception as e:
                error_count += 1
                logger.error(f"ERROR scanning {ip}: {str(e)}")
            
            # Add a small delay to avoid overwhelming the API or servers
            time.sleep(0.5)
        
        # Close the database connection
        conn.close()
        
        return {
            "success": True,
            "valid_count": valid_count,
            "error_count": error_count,
            "total_count": len(results),
            "instances": valid_instances
        }
        
    except Exception as e:
        logger.error(f"Scan failed with error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "valid_count": 0,
            "total_count": 0
        }


def search_scanned_instances(search_params: Dict) -> Dict:
    """
    Search function to query the database of scanned instances.
    
    Args:
        search_params (Dict): Search parameters including:
            - model_name (str, optional): Filter by model name
            - parameter_size (str, optional): Filter by parameter size (e.g., "7B")
            - quantization (str, optional): Filter by quantization level
            - country (str, optional): Filter by country
            - limit (int, optional): Limit number of results (default: 100)
            - offset (int, optional): Offset for pagination (default: 0)
            - sort_by (str, optional): Field to sort by
            - sort_order (str, optional): "asc" or "desc" (default: "desc")
    
    Returns:
        Dict: Search results including servers and their models
    """
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Extract search parameters
        model_name = search_params.get('model_name', '')
        parameter_size = search_params.get('parameter_size', '')
        quantization = search_params.get('quantization', '')
        country = search_params.get('country', '')
        limit = int(search_params.get('limit', 100))
        offset = int(search_params.get('offset', 0))
        sort_by = search_params.get('sort_by', 'scan_date')
        sort_order = search_params.get('sort_order', 'desc').upper()
        
        # Validate sort order
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # Build query conditions
        conditions = []
        params = []
        
        if model_name:
            conditions.append("m.name LIKE ?")
            params.append(f"%{model_name}%")
        
        if parameter_size:
            conditions.append("m.parameter_size LIKE ?")
            params.append(f"%{parameter_size}%")
        
        if quantization:
            conditions.append("m.quantization_level LIKE ?")
            params.append(f"%{quantization}%")
        
        if country:
            conditions.append("s.country_name LIKE ?")
            params.append(f"%{country}%")
        
        # Build the WHERE clause
        where_clause = " AND ".join(conditions)
        if where_clause:
            where_clause = "WHERE " + where_clause
        
        # Validate sort_by field to prevent SQL injection
        valid_sort_fields = {
            'ip': 's.ip',
            'port': 's.port',
            'scan_date': 's.scan_date',
            'country': 's.country_name',
            'city': 's.city',
            'organization': 's.organization',
            'model_count': 'model_count',
            'model_name': 'm.name',
            'parameter_size': 'm.parameter_size',
            'quantization': 'm.quantization_level'
        }
        
        sort_field = valid_sort_fields.get(sort_by, 's.scan_date')
        
        # Query to get servers with their models
        query = f"""
        SELECT s.id, s.ip, s.port, s.scan_date, s.country_code, s.country_name, 
               s.city, s.organization, s.asn, COUNT(m.id) as model_count
        FROM servers s
        LEFT JOIN models m ON s.id = m.server_id
        {where_clause}
        GROUP BY s.id
        ORDER BY {sort_field} {sort_order}
        LIMIT ? OFFSET ?
        """
        
        params.extend([limit, offset])
        Database.execute(query, params)
        servers = Database.fetch_all(query, params)
        
        # Query to get total count for pagination
        count_query = f"""
        SELECT COUNT(DISTINCT s.id)
        FROM servers s
        LEFT JOIN models m ON s.id = m.server_id
        {where_clause}
        """
        
        count_params = params[:-2]  # Remove limit and offset
        Database.execute(count_query, count_params)
        total_count = Database.fetch_one(query, params)[0]
        
        # Format the results
        results = []
        for server in servers:
            server_id, ip, port, scan_date, country_code, country_name, city, org, asn, model_count = server
            
            # Get models for this server
            model_query = """
            SELECT name, parameter_size, quantization_level, size_mb
            FROM models
            WHERE server_id = ?
            """
            
            Database.execute(model_query, (server_id,))
            models = Database.fetch_all(query, params)
            
            formatted_models = []
            for model in models:
                name, params, quant, size = model
                formatted_models.append({
                    'name': name,
                    'parameter_size': params,
                    'quantization': quant,
                    'size_mb': size
                })
            
            results.append({
                'server_id': server_id,
                'ip': ip,
                'port': port,
                'scan_date': scan_date,
                'country_code': country_code,
                'country_name': country_name,
                'city': city,
                'organization': org,
                'asn': asn,
                'model_count': model_count,
                'models': formatted_models
            })
        
        conn.close()
        
        return {
            'success': True,
            'total': total_count,
            'offset': offset,
            'limit': limit,
            'results': results
        }
    
    except sqlite3.Error as e:
        logger.error(f"Database error during search: {str(e)}")
        return {
            'success': False,
            'error': f"Database error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def add_to_openwebui_endpoints(selected_instances: List[Dict], api_base_url: str, 
                              api_key: str) -> Dict:
    """
    Add selected Ollama instances to OpenWebUI's endpoint configuration.
    
    Args:
        selected_instances (List[Dict]): List of server information to add as endpoints
        api_base_url (str): The base URL of the OpenWebUI API (e.g., "http://192.168.0.9:3000")
        api_key (str): API key for OpenWebUI
    
    Returns:
        Dict: Status of the operation
    """
    try:
        added_count = 0
        errors = []
        
        # Make sure the API base URL doesn't end with a slash
        if api_base_url.endswith('/'):
            api_base_url = api_base_url[:-1]
        
        for instance in selected_instances:
            try:
                # Extract instance information
                ip = instance.get('ip')
                port = instance.get('port')
                
                if not ip or not port:
                    errors.append(f"Missing IP or port for instance: {instance}")
                    continue
                
                # Create a name based on location if available
                location_parts = []
                if instance.get('city'):
                    location_parts.append(instance['city'])
                if instance.get('country_name'):
                    location_parts.append(instance['country_name'])
                
                location = ', '.join(location_parts) if location_parts else 'Unknown'
                name = f"Ollama ({location}) - {ip}:{port}"
                
                # Create endpoint configuration
                endpoint_config = {
                    'name': name,
                    'base_url': f"http://{ip}:{port}",
                    'api_key': '',  # Ollama doesn't typically use API keys
                    'type': 'ollama',  # Specify this is an Ollama endpoint
                    'enabled': True,
                    'priority': 0  # Default priority
                }
                
                # Call OpenWebUI API to add the endpoint
                # The actual endpoint path might need to be adjusted based on OpenWebUI's API
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }
                
                response = requests.post(
                    f"{api_base_url}/api/admin/endpoints",
                    headers=headers,
                    json=endpoint_config,
                    timeout=calculate_dynamic_timeout(max_tokens=1000, timeout_flag=args.timeout if "args" in locals() else None))
                
                # Check if the request was successful
                if response.status_code in [200, 201]:
                    added_count += 1
                else:
                    try:
                        error_msg = response.json().get('error', f"Status code: {response.status_code}")
                    except:
                        error_msg = f"Status code: {response.status_code}"
                    
                    errors.append(f"Failed to add endpoint {ip}:{port} - {error_msg}")
            
            except Exception as e:
                errors.append(f"Error adding endpoint {instance.get('ip', 'unknown')}:{instance.get('port', 'unknown')} - {str(e)}")
        
        return {
            'success': True,
            'added_count': added_count,
            'error_count': len(errors),
            'errors': errors
        }
    
    except Exception as e:
        logger.error(f"Error adding endpoints: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'added_count': 0
        }


def get_available_countries() -> Dict:
    """
    Get a list of countries that have Ollama instances in the database.
    
    Returns:
        Dict: Dictionary with success status and list of countries
    """
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        query = """
        SELECT DISTINCT country_code, country_name
        FROM servers
        WHERE country_code != '' AND country_name != ''
        ORDER BY country_name
        """
        
        Database.execute(query)
        countries = Database.fetch_all(query, params)
        
        conn.close()
        
        formatted_countries = [
            {'code': code, 'name': name}
            for code, name in countries
        ]
        
        return {
            'success': True,
            'countries': formatted_countries
        }
    
    except sqlite3.Error as e:
        logger.error(f"Database error when getting countries: {str(e)}")
        return {
            'success': False,
            'error': f"Database error: {str(e)}",
            'countries': []
        }
    except Exception as e:
        logger.error(f"Error getting countries: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'countries': []
        }


def get_dashboard_stats() -> Dict:
    """
    Get statistics for the dashboard display.
    
    Returns:
        Dict: Statistics about scanned Ollama instances
    """
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Get server count
        Database.execute("SELECT COUNT(*) FROM servers")
        server_count = Database.fetch_one(query, params)[0]
        
        # Get most recent scan date
        Database.execute("SELECT MAX(scan_date) FROM servers")
        last_scan = Database.fetch_one(query, params)[0]
        
        # Get model count
        Database.execute("SELECT COUNT(*) FROM models")
        model_count = Database.fetch_one(query, params)[0]
        
        # Get unique model count
        Database.execute("SELECT COUNT(DISTINCT name) FROM models")
        unique_model_count = Database.fetch_one(query, params)[0]
        
        # Get country count
        Database.execute("SELECT COUNT(DISTINCT country_code) FROM servers WHERE country_code != ''")
        country_count = Database.fetch_one(query, params)[0]
        
        # Get top models
        cursor.execute("""
        SELECT name, COUNT(*) as count
        FROM models
        GROUP BY name
        ORDER BY count DESC
        LIMIT 5
        """)
        top_models = [{'name': name, 'count': count} for name, count in Database.fetch_all(query, params)]
        
        # Get top countries
        cursor.execute("""
        SELECT country_name, COUNT(*) as count
        FROM servers
        WHERE country_name != ''
        GROUP BY country_name
        ORDER BY count DESC
        LIMIT 5
        """)
        top_countries = [{'name': name, 'count': count} for name, count in Database.fetch_all(query, params)]
        
        conn.close()
        
        return {
            'success': True,
            'server_count': server_count,
            'model_count': model_count,
            'unique_model_count': unique_model_count,
            'country_count': country_count,
            'last_scan': last_scan,
            'top_models': top_models,
            'top_countries': top_countries
        }
    
    except sqlite3.Error as e:
        logger.error(f"Database error when getting stats: {str(e)}")
        return {
            'success': False,
            'error': f"Database error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# Define the function handler that will be registered with OpenWebUI
def handle_ollama_scanner(action, params):
    """
    Main handler for the Ollama Scanner function in OpenWebUI.
    This function dispatches to the appropriate handler based on the action.
    
    Args:
        action (str): The action to perform
        params (Dict): Parameters for the action
    
    Returns:
        Dict: The result of the action
    """
    try:
        if action == "scan":
            return scan_ollama_instances(
                api_key=params.get('api_key', ''),
                search_query=params.get('search_query', 'product:Ollama'),
                max_results=int(params.get('max_results', DEFAULT_MAX_RESULTS)),
                timeout=int(params.get('timeout', DEFAULT_TIMEOUT)),
                ports_to_try=params.get('ports_to_try', [11434, 8000, 8001])
            )
        
        elif action == "search":
            return search_scanned_instances(params)
        
        elif action == "add_endpoints":
            return add_to_openwebui_endpoints(
                selected_instances=params.get('instances', []),
                api_base_url=params.get('api_base_url', ''),
                api_key=params.get('api_key', '')
            )
        
        elif action == "get_countries":
            return get_available_countries()
        
        elif action == "get_stats":
            return get_dashboard_stats()
        
        else:
            return {
                'success': False,
                'error': f"Unknown action: {action}"
            }
    
    except Exception as e:
        logger.error(f"Error handling action '{action}': {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# For testing outside of OpenWebUI
if __name__ == "__main__":
    # Simple test of the database setup
    conn = setup_database()
    conn.close()
    print("Database setup successful!") 