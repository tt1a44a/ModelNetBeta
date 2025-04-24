#!/usr/bin/env python3
"""
Ollama Scanner Filter Function for OpenWebUI
-------------------------------------------
This function integrates the Ollama Scanner into OpenWebUI
using the Filter Function architecture.
"""

import os
import json
import time
import sqlite3
import requests
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional, Union, Callable, Awaitable
from pydantic import BaseModel, Field

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ollama_scanner_filter")

# Constants
DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_MAX_RESULTS = 100  # max number of Shodan results to process
DATA_DIR = "/app/backend/data"  # OpenWebUI's persistent data directory
# We no longer need DB_FILE as we're using the Database abstraction class

class Filter:
    """
    Ollama Scanner Filter Function for OpenWebUI.
    
    This filter provides capabilities to:
    1. Discover Ollama instances using Shodan
    2. Search and filter discovered instances
    3. Add discovered instances as endpoints in OpenWebUI
    """
    
    class Valves(BaseModel):
        """
        System configurable values (admin settings)
        """
        SHODAN_API_KEY: str = Field(
            default="",
            description="Shodan API key for scanning Ollama instances"
        )
        MAX_RESULTS: int = Field(
            default=100,
            description="Maximum number of results to return from a scan"
        )
        SEARCH_QUERY: str = Field(
            default="product:Ollama",
            description="Default Shodan search query"
        )
        REQUEST_TIMEOUT: int = Field(
            default=5,
            description="Timeout in seconds for requests to Ollama instances"
        )
    
    class UserValves(BaseModel):
        """
        User configurable values (per-user settings)
        """
        enable_scanner: bool = Field(
            default=True,
            description="Enable Ollama Scanner features"
        )
        default_country_filter: str = Field(
            default="",
            description="Default country code filter for searching instances"
        )
        auto_add_endpoints: bool = Field(
            default=False,
            description="Automatically add discovered endpoints"
        )
    
    def __init__(self):
        """Initialize the filter"""
        self.valves = self.Valves()
        # Setup database
        self.setup_database()
    
    def setup_database(self) -> None:
        """Setup the database tables."""
        try:
            conn = Database()
            
            # Use appropriate SQL syntax based on database type
            if DATABASE_TYPE == "postgres":
                # PostgreSQL schema
                Database.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    id SERIAL PRIMARY KEY,
                    ip TEXT,
                    port INTEGER,
                    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    country_code TEXT,
                    country_name TEXT,
                    city TEXT,
                    organization TEXT,
                    asn TEXT,
                    UNIQUE(ip, port)
                );
                
                CREATE TABLE IF NOT EXISTS models (
                    id SERIAL PRIMARY KEY,
                    server_id INTEGER,
                    name TEXT,
                    parameter_size TEXT,
                    quantization_level TEXT,
                    size_mb REAL,
                    FOREIGN KEY (server_id) REFERENCES servers (id) ON DELETE CASCADE,
                    UNIQUE(server_id, name)
                );
                ''')
            else:
                # SQLite schema
                Database.execute('''
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
                );
                
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER,
                    name TEXT,
                    parameter_size TEXT,
                    quantization_level TEXT,
                    size_mb REAL,
                    FOREIGN KEY (server_id) REFERENCES servers (id),
                    UNIQUE(server_id, name)
                );
                ''')
            
            # Commit handled by Database methods
            conn.close()
            logger.info(f"Database setup complete. Type: {DATABASE_TYPE}")
        except sqlite3.Error as e:
            logger.error(f"Database setup error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during database setup: {str(e)}")
    
    def check_ollama_endpoint(self, ip: str, port: int = 11434, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[Dict]]:
        """Check if the given IP has a valid Ollama instance with /api/tags endpoint."""
        url = f"http://{ip}:{port}/api/tags"
        try:
            response = requests.get(url, timeout=timeout)
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
    
    def save_to_database(self, server_info: Dict, model_data: Dict) -> int:
        """Save the server and model information to the database."""
        try:
            conn = Database()
            
            # Extract server information
            ip = server_info.get('ip_str')
            port = server_info.get('port', 11434)
            country_code = server_info.get('country_code', '')
            country_name = server_info.get('country_name', '')
            city = server_info.get('city', '')
            organization = server_info.get('org', '')
            asn = server_info.get('asn', '')
            scan_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # First check if the server already exists to get its ID
            existing_server = Database.fetch_one(
                "SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
            
            if existing_server:
                server_id = existing_server[0]
                # Update existing record
                Database.execute('''
                UPDATE servers 
                SET scan_date = ?, country_code = ?, country_name = ?, city = ?, 
                    organization = ?, asn = ?
                WHERE id = ?
                ''', (scan_date, country_code, country_name, city, organization, asn, server_id))
            else:
                # Insert new record
                Database.execute('''
                INSERT INTO servers 
                (ip, port, scan_date, country_code, country_name, city, organization, asn) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ip, port, scan_date, country_code, country_name, city, organization, asn))
                
                # Get the server id
                server_row = Database.fetch_one(
                    "SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
                server_id = server_row[0] if server_row else None
            
            # Insert model information
            if model_data and "models" in model_data and server_id:
                for model in model_data["models"]:
                    model_name = model.get("name", "Unknown")
                    model_size = model.get("size", 0)
                    model_size_mb = model_size / (1024 * 1024) if model_size else 0
                    
                    details = model.get("details", {})
                    param_size = details.get("parameter_size", "Unknown")
                    quant_level = details.get("quantization_level", "Unknown")
                    
                    # Check if model already exists
                    existing_model = Database.fetch_one(
                        "SELECT id FROM models WHERE server_id = ? AND name = ?", 
                        (server_id, model_name))
                    
                    if existing_model:
                        # Update existing model
                        Database.execute('''
                        UPDATE models
                        SET parameter_size = ?, quantization_level = ?, size_mb = ?
                        WHERE server_id = ? AND name = ?
                        ''', (param_size, quant_level, model_size_mb, server_id, model_name))
                    else:
                        # Insert new model
                        Database.execute('''
                        INSERT INTO models 
                        (server_id, name, parameter_size, quantization_level, size_mb)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (server_id, model_name, param_size, quant_level, model_size_mb))
            
            # Commit handled by Database methods
            conn.close()
            return server_id
        except sqlite3.Error as e:
            logger.error(f"Database error when saving data: {str(e)}")
            conn.close()
            raise Exception(f"Failed to save data to database: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error when saving data: {str(e)}")
            if 'conn' in locals() and conn:
                conn.close()
            raise
    
    def perform_shodan_search(self, api_key: str, search_query: str = 'product:Ollama', 
                             max_results: int = DEFAULT_MAX_RESULTS) -> List[Dict]:
        """Perform a search on Shodan for Ollama instances."""
        try:
            # Import Shodan here to avoid making it a hard dependency
            import shodan
            
            api = shodan.Shodan(api_key)
            
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
    
    def scan_ollama_instances(self, api_key: str, search_query: str = 'product:Ollama', 
                             max_results: int = DEFAULT_MAX_RESULTS, timeout: int = DEFAULT_TIMEOUT,
                             ports_to_try: List[int] = [11434, 8000, 8001]) -> Dict:
        """Main scanning function that initiates Ollama instance discovery."""
        try:
            if not api_key:
                return {"success": False, "error": "Shodan API key is required"}
            
            # Get results from Shodan
            try:
                results = self.perform_shodan_search(api_key, search_query, max_results)
            except Exception as e:
                return {"success": False, "error": str(e)}
            
            if not results:
                return {"success": True, "message": "No Ollama instances found", "count": 0, "instances": []}
            
            # Connect to database
            conn = Database()
            
            # Initialize counters
            valid_count = 0
            total_models = 0
            instances_info = []
            
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
                        is_valid, model_data = self.check_ollama_endpoint(ip, try_port, timeout)
                        if is_valid:
                            valid_count += 1
                            models_count = len(model_data.get("models", [])) if model_data else 0
                            
                            # Save to database
                            server_id = self.save_to_database({
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
                                total_models += len(model_names)
                            
                            # Add to instances info
                            instances_info.append({
                                "id": server_id,
                                "ip": ip,
                                "port": try_port,
                                "country": result.get('location', {}).get('country_name', 'Unknown'),
                                "city": result.get('location', {}).get('city', 'Unknown'),
                                "organization": result.get('org', 'Unknown'),
                                "models_count": models_count,
                                "models": model_names
                            })
                            
                            # We found a valid server, no need to try other ports
                            server_valid = True
                            break
                    
                except Exception as e:
                    logger.error(f"Error checking {ip}:{default_port}: {str(e)}")
                    continue
            
            conn.close()
            
            return {
                "success": True,
                "count": valid_count,
                "models_count": total_models,
                "instances": instances_info
            }
            
        except Exception as e:
            logger.error(f"Error during scan: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def search_scanned_instances(self, search_params: Dict) -> Dict:
        """Search for scanned instances based on the provided parameters."""
        try:
            # Extract search parameters
            model_name = search_params.get('model_name', '')
            parameter_size = search_params.get('parameter_size', '')
            quantization = search_params.get('quantization', '')
            country = search_params.get('country', '')
            limit = int(search_params.get('limit', 100))
            offset = int(search_params.get('offset', 0))
            sort_by = search_params.get('sort_by', 'scan_date')
            sort_order = search_params.get('sort_order', 'desc')
            
            # Validate sort order
            if sort_order.lower() not in ['asc', 'desc']:
                sort_order = 'desc'
            
            # Connect to database
            conn = Database()
            
            # Base query
            query = """
            SELECT s.id, s.ip, s.port, s.scan_date, s.country_code, s.country_name, 
                   s.city, s.organization, s.asn
            FROM servers s
            """
            
            # Conditions and parameters
            conditions = []
            params = []
            
            # Model name filter (requires join)
            if model_name:
                query = """
                SELECT s.id, s.ip, s.port, s.scan_date, s.country_code, s.country_name, 
                       s.city, s.organization, s.asn
                FROM servers s
                JOIN models m ON s.id = m.server_id
                """
                conditions.append("m.name LIKE ?")
                params.append(f"%{model_name}%")
            
            # Parameter size filter (requires join if not already joined)
            if parameter_size:
                if 'JOIN models' not in query:
                    query = """
                    SELECT s.id, s.ip, s.port, s.scan_date, s.country_code, s.country_name, 
                           s.city, s.organization, s.asn
                    FROM servers s
                    JOIN models m ON s.id = m.server_id
                    """
                conditions.append("m.parameter_size LIKE ?")
                params.append(f"%{parameter_size}%")
            
            # Quantization filter (requires join if not already joined)
            if quantization:
                if 'JOIN models' not in query:
                    query = """
                    SELECT s.id, s.ip, s.port, s.scan_date, s.country_code, s.country_name, 
                           s.city, s.organization, s.asn
                    FROM servers s
                    JOIN models m ON s.id = m.server_id
                    """
                conditions.append("m.quantization_level LIKE ?")
                params.append(f"%{quantization}%")
            
            # Country filter
            if country:
                conditions.append("(s.country_code LIKE ? OR s.country_name LIKE ?)")
                params.append(f"%{country}%")
                params.append(f"%{country}%")
            
            # Add WHERE clause if there are conditions
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            # Add GROUP BY to avoid duplicates when joining with models
            if 'JOIN models' in query:
                query += " GROUP BY s.id"
            
            # Add ORDER BY clause
            valid_sort_fields = {
                'scan_date': 's.scan_date', 
                'country': 's.country_name',
                'ip': 's.ip',
                'port': 's.port',
                'organization': 's.organization'
            }
            
            sort_field = valid_sort_fields.get(sort_by, 's.scan_date')
            query += f" ORDER BY {sort_field} {sort_order}"
            
            # Add LIMIT and OFFSET
            query += " LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset)
            
            # Execute query
            servers = Database.fetch_all(query, params)
            
            # Count total results (without limit/offset)
            count_query = query.split("ORDER BY")[0]
            if "GROUP BY" in count_query:
                count_query = count_query.split("GROUP BY")[0] + " GROUP BY s.id"
            count_query = f"SELECT COUNT(*) FROM ({count_query}) as count_query"
            count_params = params[:-2]  # Remove limit and offset params
            
            count_result = Database.fetch_one(count_query, count_params)
            total_count = count_result[0] if count_result else 0
            
            # Prepare results
            results = []
            for server in servers:
                # Convert server row to dictionary
                if isinstance(server, dict):
                    server_dict = server
                else:
                    # Create dictionary from tuple
                    server_dict = {}
                    keys = ['id', 'ip', 'port', 'scan_date', 'country_code', 'country_name', 
                            'city', 'organization', 'asn']
                    for i, key in enumerate(keys):
                        server_dict[key] = server[i] if i < len(server) else None
                
                # Get server ID
                server_id = server_dict.get('id')
                if server_id:
                    # Get models for this server
                    models_query = """
                    SELECT name, parameter_size, quantization_level, size_mb
                    FROM models
                    WHERE server_id = ?
                    """
                    models = Database.fetch_all(models_query, (server_id,))
                    
                    # Process model data
                    model_list = []
                    for model in models:
                        if isinstance(model, dict):
                            model_dict = model
                        else:
                            # Create dictionary from tuple
                            model_dict = {}
                            keys = ['name', 'parameter_size', 'quantization_level', 'size_mb']
                            for i, key in enumerate(keys):
                                model_dict[key] = model[i] if i < len(model) else None
                        
                        model_list.append(model_dict)
                    
                    server_dict['models'] = model_list
                    server_dict['models_count'] = len(model_list)
                else:
                    server_dict['models'] = []
                    server_dict['models_count'] = 0
                
                results.append(server_dict)
            
            conn.close()
            
            return {
                "success": True,
                "total": total_count,
                "count": len(results),
                "offset": offset,
                "limit": limit,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error searching instances: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def add_to_openwebui_endpoints(self, selected_instances: List[Dict], api_base_url: str, 
                                  api_key: str) -> Dict:
        """Add selected Ollama instances to OpenWebUI's endpoint configuration."""
        try:
            added_count = 0
            errors = []
            
            # Make sure the API base URL doesn't end with a slash
            if api_base_url.endswith('/'):
                api_base_url = api_base_url[:-1]
            
            for instance in selected_instances:
                try:
                    ip = instance.get('ip')
                    port = instance.get('port', 11434)
                    
                    if not ip:
                        errors.append("Missing IP address in instance data")
                        continue
                    
                    # Create a friendly name
                    name = instance.get('name', f"Ollama ({ip}:{port})")
                    
                    # Prepare the endpoint data
                    endpoint_data = {
                        "id": f"ollama-{ip.replace('.', '-')}-{port}",
                        "name": name,
                        "type": "ollama",
                        "ollama": {
                            "url": f"http://{ip}:{port}/api"
                        },
                        "context_length": 8192,
                        "weight": 1.0,
                        "active": True
                    }
                    
                    # Send the request to add the endpoint
                    headers = {
                        "Content-Type": "application/json",
                        "X-API-Key": api_key
                    }
                    
                    url = f"{api_base_url}/api/endpoints"
                    response = requests.post(url, json=endpoint_data, headers=headers)
                    
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
    
    def get_available_countries(self) -> Dict:
        """Get the list of available countries in the database."""
        try:
            conn = Database()
            
            query = """
            SELECT DISTINCT country_code, country_name
            FROM servers
            WHERE country_code != ''
            ORDER BY country_name
            """
            
            countries = Database.fetch_all(query)
            
            # Make sure we can access the results properly regardless of the database type
            result = []
            for country in countries:
                # Convert the row to a dictionary if it's not already
                if not isinstance(country, dict):
                    country_dict = {}
                    for i, key in enumerate(['country_code', 'country_name']):
                        country_dict[key] = country[i] if i < len(country) else None
                else:
                    country_dict = country
                
                result.append({
                    "code": country_dict.get("country_code", ""),
                    "name": country_dict.get("country_name", "")
                })
            
            conn.close()
            
            return {
                "success": True,
                "countries": result
            }
            
        except Exception as e:
            logger.error(f"Error retrieving countries: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_dashboard_stats(self) -> Dict:
        """Get statistics for the dashboard."""
        try:
            conn = Database()
            
            # Get total instances
            instances_query = "SELECT COUNT(*) as count FROM servers"
            instances_result = Database.fetch_one(instances_query)
            
            # Handle result based on whether it's a dict or tuple
            if isinstance(instances_result, dict):
                instances_count = instances_result.get("count", 0)
            else:
                instances_count = instances_result[0] if instances_result else 0
            
            # Get total models
            models_query = "SELECT COUNT(*) as count FROM models"
            models_result = Database.fetch_one(models_query)
            
            # Handle result based on whether it's a dict or tuple
            if isinstance(models_result, dict):
                models_count = models_result.get("count", 0)
            else:
                models_count = models_result[0] if models_result else 0
            
            # Get country distribution
            countries_query = """
            SELECT country_name, COUNT(*) as count
            FROM servers
            WHERE country_name != ''
            GROUP BY country_name
            ORDER BY count DESC
            LIMIT 10
            """
            countries_results = Database.fetch_all(countries_query)
            
            # Process countries results
            countries = []
            for row in countries_results:
                if isinstance(row, dict):
                    countries.append({
                        "name": row.get("country_name", "Unknown"),
                        "count": row.get("count", 0)
                    })
                else:
                    countries.append({
                        "name": row[0] if len(row) > 0 else "Unknown", 
                        "count": row[1] if len(row) > 1 else 0
                    })
            
            # Get popular models
            models_query = """
            SELECT name, COUNT(*) as count
            FROM models
            GROUP BY name
            ORDER BY count DESC
            LIMIT 10
            """
            popular_models_results = Database.fetch_all(models_query)
            
            # Process models results
            popular_models = []
            for row in popular_models_results:
                if isinstance(row, dict):
                    popular_models.append({
                        "name": row.get("name", "Unknown"),
                        "count": row.get("count", 0)
                    })
                else:
                    popular_models.append({
                        "name": row[0] if len(row) > 0 else "Unknown", 
                        "count": row[1] if len(row) > 1 else 0
                    })
            
            # Get recent scans
            scans_query = """
            SELECT scan_date, COUNT(*) as count
            FROM servers
            GROUP BY scan_date
            ORDER BY scan_date DESC
            LIMIT 10
            """
            recent_scans_results = Database.fetch_all(scans_query)
            
            # Process scans results
            recent_scans = []
            for row in recent_scans_results:
                if isinstance(row, dict):
                    recent_scans.append({
                        "date": row.get("scan_date", "Unknown"),
                        "count": row.get("count", 0)
                    })
                else:
                    recent_scans.append({
                        "date": row[0] if len(row) > 0 else "Unknown", 
                        "count": row[1] if len(row) > 1 else 0
                    })
            
            conn.close()
            
            return {
                "success": True,
                "instances_count": instances_count,
                "models_count": models_count,
                "countries": countries,
                "popular_models": popular_models,
                "recent_scans": recent_scans
            }
            
        except Exception as e:
            logger.error(f"Error retrieving dashboard stats: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def inlet(
        self,
        query: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process the input message before it goes to the LLM.
        This is where we can add context about Ollama Scanner features.
        
        Args:
            query: The user's input message
            __event_emitter__: An event emitter function for streaming responses
            __user__: User information including valves
            
        Returns:
            str: The processed input message
        """
        # Check if Ollama Scanner related query
        scanner_keywords = [
            "ollama scanner", "find ollama", "discover ollama", 
            "search for ollama", "scan for ollama"
        ]
        
        # Get the user valves if available
        user_valves = None
        if __user__ and "valves" in __user__:
            user_valves = __user__["valves"]
        
        # Only modify the query if the scanner is enabled for this user
        is_enabled = user_valves.enable_scanner if user_valves else True
        
        if is_enabled and any(keyword in query.lower() for keyword in scanner_keywords):
            # Add context about Ollama Scanner to the user's query
            return (
                f"{query}\n\n"
                "Note: You can use the Ollama Scanner feature to discover and connect to Ollama instances. "
                "Go to Admin Panel > Ollama Scanner to use this feature. "
                "The scanner requires a Shodan API key to search for instances."
            )
        
        return query
    
    async def stream(
        self,
        chunk: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process each chunk of the LLM's response as it's generated.
        We simply pass through the chunks unchanged.
        
        Args:
            chunk: A chunk of the model's response
            __event_emitter__: An event emitter function
            __user__: User information
            
        Returns:
            str: The processed chunk
        """
        return chunk
    
    async def outlet(
        self,
        response: str,
        __event_emitter__: Callable[[dict], Awaitable[None]],
        __user__: Optional[dict] = None
    ) -> str:
        """
        Process the complete LLM response after it's been generated.
        
        Args:
            response: The complete response from the LLM
            __event_emitter__: An event emitter function
            __user__: User information
            
        Returns:
            str: The processed response
        """
        # Check if we need to process the response
        scanner_related = any(term in response.lower() for term in [
            "ollama scanner", "scan ollama", "discover ollama", "ollama instances"
        ])
        
        # Get the user valves if available
        user_valves = None
        if __user__ and "valves" in __user__:
            user_valves = __user__["valves"]
        
        # Only modify the response if the scanner is enabled for this user
        is_enabled = user_valves.enable_scanner if user_valves else True
        
        if is_enabled and scanner_related:
            # Add a note about accessing the scanner UI
            footer = (
                "\n\n---\n"
                "**Ollama Scanner Note**: To use the Ollama Scanner, visit the Admin Panel and navigate to "
                "the Ollama Scanner section. You'll need a Shodan API key to scan for instances."
            )
            return response + footer
        
        return response 