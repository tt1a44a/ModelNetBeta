from typing import Dict, List, Optional, Any, Union, Tuple
from pydantic import BaseModel, Field
import requests
import json
import sqlite3
import os
import datetime
import logging
import socket
import ipaddress
import re
import shodan
import threading
import time
import base64
from concurrent.futures import ThreadPoolExecutor

# Added by migration script
from database import Database, init_database

class Tools:
    """
    Ollama Scanner Tool for OpenWebUI
    
    Discover, analyze, and connect to Ollama instances across the internet or local networks.
    This tool combines all functionality from the original Ollama Scanner project.
    """
    
    class Valves(BaseModel):
        """Configuration valves for the Ollama Scanner tool."""
        # API Keys
        SHODAN_API_KEY: str = Field(
            default="",
            description="Shodan API key for scanning Ollama instances"
        )
        
        # Search Configuration
        MAX_RESULTS: int = Field(
            default=100,
            description="Maximum number of results to return from a scan"
        )
        DEFAULT_SEARCH_QUERY: str = Field(
            default="product:Ollama port:11434",
            description="Default Shodan search query"
        )
        CHECK_AVAILABILITY: bool = Field(
            default=True,
            description="Check if instances are actually available"
        )
        SCAN_TIMEOUT: int = Field(
            default=10,
            description="Timeout in seconds for scan requests"
        )
        
        # Network Scanning
        ENABLE_LOCAL_NETWORK_SCAN: bool = Field(
            default=False,
            description="Enable scanning of local networks (potentially dangerous)"
        )
        LOCAL_SCAN_THREADS: int = Field(
            default=50,
            description="Number of threads to use for local network scanning"
        )
        LOCAL_SCAN_TIMEOUT: float = Field(
            default=0.5,
            description="Timeout in seconds for local network scan connections"
        )
        
        # Database and Storage
        DB_PATH: str = Field(
            # TODO: Replace SQLite-specific code: default="/app/backend/data/ollama_scanner.db",
            description="Path to the SQLite database file"
        )
        OPENWEBUI_DB_PATH: str = Field(
            # TODO: Replace SQLite-specific code: default="/app/backend/data/database.db",
            description="Path to the OpenWebUI SQLite database"
        )
        
        # OpenWebUI Integration
        AUTO_ADD_TO_OPENWEBUI: bool = Field(
            default=False,
            description="Automatically add discovered instances to OpenWebUI"
        )
        MAX_AUTO_ADD: int = Field(
            default=5,
            description="Maximum number of instances to automatically add"
        )
        ENDPOINT_WEIGHT: int = Field(
            default=1,
            description="Weight assigned to added endpoints"
        )
        DEFAULT_CONTEXT_SIZE: int = Field(
            default=8192,
            description="Default context size for added endpoints"
        )
        
        # Security Features
        ENABLE_SECURITY_CHECKS: bool = Field(
            default=True,
            description="Enable security vulnerability checks on instances"
        )
        ENABLE_BENCHMARKING: bool = Field(
            default=False,
            description="Enable benchmarking of discovered instances (sends test prompts)"
        )

    def __init__(self):
        self.valves = self.Valves()
        self._setup_logging()
        self._setup_database()
    
    def _setup_logging(self):
        """Set up logging for the Ollama Scanner tool."""
        self.logger = logging.getLogger("ollama_scanner")
        self.logger.setLevel(logging.INFO)
        
        # Create handler if not already set up
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _setup_database(self):
        """Set up the SQLite database for storing Ollama instances."""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.valves.DB_PATH)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # Connect to database and create tables if they don't exist
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Create instances table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ollama_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                country TEXT,
                city TEXT,
                organization TEXT,
                version TEXT,
                available BOOLEAN,
                has_auth BOOLEAN DEFAULT 0,
                is_vulnerable BOOLEAN DEFAULT 0,
                response_time FLOAT,
                last_check TIMESTAMP,
                added_to_openwebui BOOLEAN DEFAULT 0,
                UNIQUE(ip, port)
            )
            ''')
            
            # Create models table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ollama_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                model_name TEXT,
                model_family TEXT,
                size_mb REAL,
                parameter_size TEXT,
                quantization TEXT,
                last_check TIMESTAMP,
                FOREIGN KEY (instance_id) REFERENCES ollama_instances(id),
                UNIQUE(instance_id, model_name)
            )
            ''')
            
            # Create benchmark table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER,
                model_name TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                response_time FLOAT,
                tokens_per_second FLOAT,
                benchmark_date TIMESTAMP,
                FOREIGN KEY (instance_id) REFERENCES ollama_instances(id)
            )
            ''')
            
            # Commit handled by Database methods
            conn.close()
            self.logger.info("Database setup complete")
        except Exception as e:
            self.logger.error(f"Error setting up database: {str(e)}")
            # Re-raise critical database setup errors as this is essential
            raise RuntimeError(f"Failed to set up database: {str(e)}")
    
    # ----- SHODAN SCANNING METHODS -----
    
    def scan_ollama_instances(
        self, 
        limit: Optional[int] = None, 
        country: Optional[str] = None,
        custom_query: Optional[str] = None,
        check_availability: Optional[bool] = None,
        save_to_db: bool = True,
        auto_add_to_openwebui: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Scan for publicly accessible Ollama instances using Shodan.
        
        Args:
            limit: Maximum number of instances to return
            country: Filter results by country code (e.g., 'US', 'DE')
            custom_query: Custom Shodan search query (overrides default)
            check_availability: Whether to check if instances are actually responding
            save_to_db: Whether to save results to the database
            auto_add_to_openwebui: Whether to automatically add discovered instances to OpenWebUI
            
        Returns:
            Dictionary with scan results
        """
        # Input validation
        if limit is not None and limit <= 0:
            return {
                "success": False,
                "error": "Limit must be a positive integer"
            }

        if country is not None and not isinstance(country, str):
            return {
                "success": False,
                "error": "Country must be a string (e.g., 'US', 'DE')"
            }
            
        # Use provided values or fall back to valve defaults
        limit = limit if limit is not None else self.valves.MAX_RESULTS
        check_availability = check_availability if check_availability is not None else self.valves.CHECK_AVAILABILITY
        auto_add = auto_add_to_openwebui if auto_add_to_openwebui is not None else self.valves.AUTO_ADD_TO_OPENWEBUI
        
        if not self.valves.SHODAN_API_KEY:
            return {
                "success": False,
                "error": "Shodan API key not configured. Please set your API key in the tool configuration."
            }
        
        # Build the Shodan query
        if custom_query:
            query = custom_query
        else:
            query = self.valves.DEFAULT_SEARCH_QUERY
            if country:
                query += f" country:{country}"
        
        try:
            self.logger.info(f"Scanning for Ollama instances with query: {query}, limit: {limit}")
            
            # Initialize Shodan API client
            api = shodan.Shodan(self.valves.SHODAN_API_KEY)
            
            # Search for Ollama instances
            search_results = api.search(query, limit=limit)
            
            if "matches" not in search_results:
                self.logger.error(f"No matches found in Shodan response")
                return {
                    "success": False,
                    "error": "No results found"
                }
            
            # Process results
            instances = []
            for result in search_results["matches"]:
                instance = {
                    "ip": result.get("ip_str"),
                    "port": result.get("port", 11434),
                    "country": result.get("location", {}).get("country_name", "Unknown"),
                    "city": result.get("location", {}).get("city", "Unknown"),
                    "organization": result.get("org", "Unknown"),
                    "last_update": result.get("timestamp", "Unknown"),
                    "available": False,
                    "version": "Unknown",
                    "has_auth": False,
                    "is_vulnerable": True,  # Assume vulnerable until proven otherwise
                    "response_time": None
                }
                
                # Check if the instance is actually available
                if check_availability:
                    availability_info = self._check_instance_availability(
                        instance["ip"], 
                        instance["port"]
                    )
                    
                    instance.update(availability_info)
                
                instances.append(instance)
                
                # Save to database if requested
                if save_to_db:
                    self._save_instance_to_db(instance)
            
            # Automatically add to OpenWebUI if configured
            auto_add_info = self._handle_auto_add(auto_add, instances)
            
            result_data = {
                "success": True,
                "total": search_results.get("total", 0),
                "returned": len(instances),
                "instances": instances,
                "auto_add_info": auto_add_info
            }
            
            self.logger.info(f"Scan complete. Found {len(instances)} instances.")
            return result_data
            
        except shodan.APIError as e:
            self.logger.error(f"Shodan API error: {str(e)}")
            return {
                "success": False,
                "error": f"Shodan API error: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error scanning for Ollama instances: {str(e)}")
            return {
                "success": False,
                "error": f"Error scanning for Ollama instances: {str(e)}"
            }
    
    def _check_instance_availability(self, ip: str, port: int) -> Dict[str, Any]:
        """Check if an Ollama instance is available and get its version."""
        result = {
            "available": False,
            "version": "Unknown",
            "has_auth": False,
            "is_vulnerable": True,
            "response_time": None
        }
        
        try:
            start_time = time.time()
            response = requests.get(
                f"http://{ip}:{port}/api/version",
                timeout=self.valves.SCAN_TIMEOUT
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result["available"] = True
                result["version"] = response.json().get("version", "Unknown")
                result["response_time"] = response_time
                
                # Check for authentication
                auth_check = self._check_instance_auth(ip, port)
                result["has_auth"] = auth_check["has_auth"]
                result["is_vulnerable"] = not auth_check["has_auth"]
            
            return result
        except Exception as e:
            self.logger.debug(f"Instance {ip}:{port} not available: {str(e)}")
            return result
    
    def _check_instance_auth(self, ip: str, port: int) -> Dict[str, bool]:
        """Check if an Ollama instance requires authentication."""
        try:
            # Try to list models without authentication
            response = requests.get(
                f"http://{ip}:{port}/api/tags",
                timeout=self.valves.SCAN_TIMEOUT
            )
            
            # If we get a 401, it requires authentication
            if response.status_code == 401:
                return {"has_auth": True}
            
            # If we get a 200, it doesn't require authentication
            if response.status_code == 200:
                return {"has_auth": False}
            
            # Otherwise, we're not sure
            return {"has_auth": False}
        except Exception:
            # If there's an error, we can't determine auth status
            return {"has_auth": False}
    
    # ----- LOCAL NETWORK SCANNING -----
    
    def scan_local_network(
        self, 
        network_range: str, 
        port: int = 11434,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """
        Scan a local network range for Ollama instances.
        
        Args:
            network_range: Network range in CIDR notation (e.g., '192.168.1.0/24')
            port: Port to scan (default: 11434)
            save_to_db: Whether to save results to the database
            
        Returns:
            Dictionary with scan results
        """
        if not self.valves.ENABLE_LOCAL_NETWORK_SCAN:
            return {
                "success": False,
                "error": "Local network scanning is disabled. Enable it in the tool configuration."
            }
        
        # Validate port number
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return {
                "success": False,
                "error": "Invalid port number. Must be between 1 and 65535."
            }
        
        try:
            # Validate network range
            try:
                network = ipaddress.ip_network(network_range, strict=False)
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"Invalid network range: {str(e)}"
                }
            
            # Safety checks for sensitive networks
            if network.is_global and not network.is_private:
                # This is a public internet range
                host_count = network.num_addresses
                if host_count > 1024:
                    return {
                        "success": False,
                        "error": f"Network range too large ({host_count} addresses). For safety, limit scans to smaller ranges (max 1024 hosts)."
                    }
            
            # Check for reserved or special-use networks
            reserved_networks = [
                ipaddress.ip_network("10.0.0.0/8"),  # Private network
                ipaddress.ip_network("172.16.0.0/12"),  # Private network
                ipaddress.ip_network("192.168.0.0/16"),  # Private network
                ipaddress.ip_network("127.0.0.0/8"),  # Loopback
                ipaddress.ip_network("169.254.0.0/16"),  # Link-local
                ipaddress.ip_network("224.0.0.0/4"),  # Multicast
                ipaddress.ip_network("240.0.0.0/4"),  # Reserved
            ]
            
            network_type = "Public Internet"
            for reserved in reserved_networks:
                if network.subnet_of(reserved):
                    if reserved == ipaddress.ip_network("127.0.0.0/8"):
                        network_type = "Loopback"
                    elif reserved in [ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16")]:
                        network_type = "Private Network"
                    else:
                        network_type = "Special-Use Network"
                    break
            
            self.logger.info(f"Scanning {network_type} range {network_range} for Ollama instances on port {port}")
            
            # Prepare scanning
            instances = []
            scan_count = 0
            
            # Cap the number of hosts to scan for safety
            host_count = min(network.num_addresses, 4096)  # Hard cap
            hosts_to_scan = list(network.hosts())[:host_count]
            
            # Use ThreadPoolExecutor for parallel scanning
            max_workers = min(self.valves.LOCAL_SCAN_THREADS, 100)  # Cap max workers for safety
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit scanning tasks
                future_to_ip = {
                    executor.submit(self._check_local_instance, str(ip), port): str(ip)
                    for ip in hosts_to_scan
                }
                
                # Process results as they complete
                for future in future_to_ip:
                    ip = future_to_ip[future]
                    scan_count += 1
                    
                    try:
                        result = future.result()
                        if result["available"]:
                            instances.append(result)
                            
                            # Save to database if requested
                            if save_to_db:
                                self._save_instance_to_db(result)
                    except Exception as e:
                        self.logger.debug(f"Error scanning {ip}: {str(e)}")
            
            self.logger.info(f"Local network scan complete. Scanned {scan_count} IPs, found {len(instances)} instances.")
            
            return {
                "success": True,
                "scanned": scan_count,
                "found": len(instances),
                "instances": instances,
                "network_type": network_type
            }
            
        except Exception as e:
            self.logger.error(f"Error scanning local network: {str(e)}")
            return {
                "success": False,
                "error": f"Error scanning local network: {str(e)}"
            }
    
    def _check_local_instance(self, ip: str, port: int) -> Dict[str, Any]:
        """Check if an IP address has an Ollama instance running."""
        result = {
            "ip": ip,
            "port": port,
            "available": False,
            "version": "Unknown",
            "country": "Local",
            "city": "Local",
            "organization": "Local Network",
            "has_auth": False,
            "is_vulnerable": True,
            "response_time": None,
            "last_update": datetime.datetime.now().isoformat()
        }
        
        try:
            # First check if the port is open
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.valves.LOCAL_SCAN_TIMEOUT)
            
            if sock.connect_ex((ip, port)) == 0:
                # Port is open, check if it's Ollama
                availability_info = self._check_instance_availability(ip, port)
                result.update(availability_info)
            
            sock.close()
            return result
        except Exception:
            return result
    
    # ----- INSTANCE MANAGEMENT METHODS -----
    
    def _save_instance_to_db(self, instance: Dict[str, Any]) -> bool:
        """Save an Ollama instance to the database."""
        conn = None
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            cursor.execute(
                '''
                INSERT OR REPLACE INTO ollama_instances 
                (ip, port, country, city, organization, version, available, has_auth, is_vulnerable, response_time, last_check)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    instance["ip"],
                    instance["port"],
                    instance.get("country", "Unknown"),
                    instance.get("city", "Unknown"),
                    instance.get("organization", "Unknown"),
                    instance.get("version", "Unknown"),
                    1 if instance.get("available", False) else 0,
                    1 if instance.get("has_auth", False) else 0,
                    1 if instance.get("is_vulnerable", True) else 0,
                    instance.get("response_time"),
                    datetime.datetime.now().isoformat()
                )
            )
            
            # Commit handled by Database methods
            return True
        except sqlite3.Error as e:
            self.logger.error(f"SQLite error saving instance to database: {str(e)}")
            if conn:
                # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: conn.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Error saving instance to database: {str(e)}")
            if conn:
                # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_available_models(self, ip: str, port: int = 11434, save_to_db: bool = True) -> Dict[str, Any]:
        """
        Get available models from a specific Ollama instance.
        
        Args:
            ip: IP address of the Ollama instance
            port: Port of the Ollama instance (default: 11434)
            save_to_db: Whether to save results to the database
            
        Returns:
            Dictionary with available models
        """
        # Input validation
        if not ip or not isinstance(ip, str):
            return {
                "success": False,
                "error": "Invalid IP address"
            }
            
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return {
                "success": False,
                "error": "Invalid port number. Must be between 1 and 65535."
            }
            
        try:
            self.logger.info(f"Getting models from {ip}:{port}")
            
            # Use a timeout to prevent hanging
            response = requests.get(
                f"http://{ip}:{port}/api/tags",
                timeout=self.valves.SCAN_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                
                # Edge case: Check if models array is None or missing
                if models is None:
                    models = []
                
                # Enhance model information
                enhanced_models = [self._enhance_model_info(model) for model in models]
                
                # Save to database if requested
                if save_to_db and enhanced_models:
                    self._save_models_to_db(ip, port, enhanced_models)
                
                return {
                    "success": True,
                    "count": len(enhanced_models),
                    "models": enhanced_models
                }
            elif response.status_code == 401:
                self.logger.warning(f"Authentication required for {ip}:{port}")
                return {
                    "success": False,
                    "error": "Authentication required",
                    "requires_auth": True
                }
            else:
                self.logger.error(f"Error getting models: Status code {response.status_code}")
                return {
                    "success": False,
                    "error": f"Error getting models: Status code {response.status_code}"
                }
        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout connecting to {ip}:{port}")
            return {
                "success": False,
                "error": f"Timeout connecting to {ip}:{port}"
            }
        except requests.exceptions.ConnectionError:
            self.logger.error(f"Connection error to {ip}:{port}")
            return {
                "success": False,
                "error": f"Unable to connect to {ip}:{port}"
            }
        except Exception as e:
            self.logger.error(f"Error getting models: {str(e)}")
            return {
                "success": False,
                "error": f"Error getting models: {str(e)}"
            }
    
    def _enhance_model_info(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance model information with additional details."""
        enhanced = model.copy()
        
        # Extract model family (e.g., llama, mistral)
        model_name = model.get("name", "").lower()
        if "llama" in model_name:
            enhanced["model_family"] = "llama"
        elif "mistral" in model_name:
            enhanced["model_family"] = "mistral"
        elif "phi" in model_name:
            enhanced["model_family"] = "phi"
        elif "gemma" in model_name:
            enhanced["model_family"] = "gemma"
        elif "yi" in model_name:
            enhanced["model_family"] = "yi"
        elif "qwen" in model_name:
            enhanced["model_family"] = "qwen"
        else:
            enhanced["model_family"] = "unknown"
        
        # Extract parameter size (e.g., 7b, 13b)
        param_match = re.search(r'(\d+b)', model_name)
        if param_match:
            enhanced["parameter_size"] = param_match.group(1)
        else:
            enhanced["parameter_size"] = "unknown"
        
        # Extract quantization (e.g., q4_0, q8_0)
        quant_match = re.search(r'q\d+_\d+', model_name)
        if quant_match:
            enhanced["quantization"] = quant_match.group(0)
        else:
            enhanced["quantization"] = "none"
        
        # Convert size to MB
        if "size" in model:
            enhanced["size_mb"] = model["size"] / (1024 * 1024)
        else:
            enhanced["size_mb"] = 0
            
        return enhanced
    
    def _save_models_to_db(self, ip: str, port: int, models: List[Dict[str, Any]]) -> bool:
        """Save models to the database."""
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Get instance ID
            cursor.execute(
                "SELECT id FROM ollama_instances WHERE ip = ? AND port = ?",
                (ip, port)
            )
            result = Database.fetch_one(query, params)
            
            if not result:
                self.logger.warning(f"Instance {ip}:{port} not found in database")
                return False
            
            instance_id = result[0]
            
            # Save models
            for model in models:
                cursor.execute(
                    '''
                    INSERT OR REPLACE INTO ollama_models 
                    (instance_id, model_name, model_family, size_mb, parameter_size, quantization, last_check)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        instance_id,
                        model.get("name", "Unknown"),
                        model.get("model_family", "unknown"),
                        model.get("size_mb", 0),
                        model.get("parameter_size", "unknown"),
                        model.get("quantization", "none"),
                        datetime.datetime.now().isoformat()
                    )
                )
            
            # Commit handled by Database methods
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"Error saving models to database: {str(e)}")
            return False
    
    def list_instances_from_db(
        self, 
        limit: int = 100, 
        available_only: bool = True,
        vulnerable_only: bool = False,
        country: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List Ollama instances from the database.
        
        Args:
            limit: Maximum number of instances to return
            available_only: Whether to only return available instances
            vulnerable_only: Whether to only return vulnerable instances
            country: Filter by country
            
        Returns:
            Dictionary with instances
        """
        try:
            conn = Database()
            conn.row_factory = sqlite3.Row
            cursor = # Using Database methods instead of cursor
            
            query = "SELECT * FROM ollama_instances WHERE 1=1"
            params = []
            
            if available_only:
                query += " AND available = 1"
            
            if vulnerable_only:
                query += " AND is_vulnerable = 1"
                
            if country:
                query += " AND country = ?"
                params.append(country)
                
            query += " ORDER BY last_check DESC LIMIT ?"
            params.append(limit)
            
            Database.execute(query, params)
            rows = Database.fetch_all(query, params)
            
            instances = []
            for row in rows:
                instance = dict(row)
                
                # Convert boolean fields from integers
                instance["available"] = bool(instance["available"])
                instance["has_auth"] = bool(instance["has_auth"])
                instance["is_vulnerable"] = bool(instance["is_vulnerable"])
                instance["added_to_openwebui"] = bool(instance["added_to_openwebui"])
                
                instances.append(instance)
            
            conn.close()
            
            return {
                "success": True,
                "count": len(instances),
                "instances": instances
            }
        except Exception as e:
            self.logger.error(f"Error listing instances from database: {str(e)}")
            return {
                "success": False,
                "error": f"Error listing instances from database: {str(e)}"
            }
    
    def get_instance_details(self, ip: str, port: int = 11434, with_models: bool = True) -> Dict[str, Any]:
        """
        Get detailed information about a specific instance.
        
        Args:
            ip: IP address of the instance
            port: Port of the instance
            with_models: Whether to include model information
            
        Returns:
            Dictionary with instance details
        """
        try:
            conn = Database()
            conn.row_factory = sqlite3.Row
            cursor = # Using Database methods instead of cursor
            
            # Get instance details
            cursor.execute(
                "SELECT * FROM ollama_instances WHERE ip = ? AND port = ?",
                (ip, port)
            )
            instance_row = Database.fetch_one(query, params)
            
            if not instance_row:
                return {
                    "success": False,
                    "error": f"Instance {ip}:{port} not found in database"
                }
            
            instance = dict(instance_row)
            
            # Convert boolean fields from integers
            instance["available"] = bool(instance["available"])
            instance["has_auth"] = bool(instance["has_auth"])
            instance["is_vulnerable"] = bool(instance["is_vulnerable"])
            instance["added_to_openwebui"] = bool(instance["added_to_openwebui"])
            
            # Get models if requested
            if with_models:
                cursor.execute(
                    "SELECT * FROM ollama_models WHERE instance_id = ? ORDER BY model_name",
                    (instance["id"],)
                )
                model_rows = Database.fetch_all(query, params)
                
                models = [dict(row) for row in model_rows]
                instance["models"] = models
            
            conn.close()
            
            return {
                "success": True,
                "instance": instance
            }
        except Exception as e:
            self.logger.error(f"Error getting instance details: {str(e)}")
            return {
                "success": False,
                "error": f"Error getting instance details: {str(e)}"
            }
    
    # ----- OPENWEBUI INTEGRATION METHODS -----
    
    def _handle_auto_add(self, auto_add: bool, instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle auto-adding instances to OpenWebUI if configured."""
        if not auto_add or not instances:
            return {
                "auto_add_enabled": auto_add
            }
        
        # Filter available instances
        available_instances = [i for i in instances if i.get("available", False)]
        if not available_instances:
            return {
                "auto_add_enabled": True,
                "auto_add_result": "No available instances found to add"
            }
        
        # Add up to the configured maximum
        add_result = self.add_multiple_to_openwebui(
            instances=available_instances[:self.valves.MAX_AUTO_ADD]
        )
        
        return {
            "auto_add_enabled": True,
            "auto_add_result": add_result
        }
    
    def add_to_openwebui(self, ip: str, port: int = 11434, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Add an Ollama instance as an endpoint in OpenWebUI.
        
        Args:
            ip: IP address of the Ollama instance
            port: Port of the Ollama instance (default: 11434)
            name: Name for the endpoint (default: "Ollama {ip}")
            
        Returns:
            Dictionary with result of the operation
        """
        if not name:
            name = f"Ollama {ip}"
        
        try:
            # First, check if the instance is available
            availability_check = requests.get(
                f"http://{ip}:{port}/api/version",
                timeout=self.valves.SCAN_TIMEOUT
            )
            
            if availability_check.status_code != 200:
                return {
                    "success": False,
                    "error": f"Instance {ip}:{port} is not available"
                }
            
            # Connect to OpenWebUI's database
            openwebui_db_path = self.valves.OPENWEBUI_DB_PATH
            if not os.path.exists(openwebui_db_path):
                return {
                    "success": False,
                    "error": f"OpenWebUI database not found at {openwebui_db_path}"
                }
            
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Check if endpoints table exists
            Database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_endpoint'")
            if not Database.fetch_one(query, params):
                conn.close()
                return {
                    "success": False,
                    "error": "OpenWebUI database does not have the expected schema"
                }
            
            # Add endpoint to database
            cursor.execute(
                '''
                INSERT OR REPLACE INTO llm_endpoint
                (name, url, api_key, type, weight, context_size, models, default_endpoint, creation_date, update_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    name,
                    f"http://{ip}:{port}",
                    "",  # No API key for Ollama
                    "ollama",
                    self.valves.ENDPOINT_WEIGHT,
                    self.valves.DEFAULT_CONTEXT_SIZE,
                    "[]",  # Empty models list
                    0,  # Not default
                    datetime.datetime.now().isoformat(),
                    datetime.datetime.now().isoformat()
                )
            )
            
            # Mark as added in our database
            ollama_conn = Database()
            ollama_cursor = ollama_# Using Database methods instead of cursor
            
            # Check if the instance exists in our database
            ollama_cursor.execute(
                "SELECT id FROM ollama_instances WHERE ip = ? AND port = ?",
                (ip, port)
            )
            instance_row = ollama_Database.fetch_one(query, params)
            
            if instance_row:
                # Update the existing instance
                ollama_cursor.execute(
                    "UPDATE ollama_instances SET added_to_openwebui = 1 WHERE ip = ? AND port = ?",
                    (ip, port)
                )
            else:
                # Insert a new instance record
                ollama_cursor.execute(
                    '''
                    INSERT INTO ollama_instances 
                    (ip, port, country, city, organization, version, available, has_auth, is_vulnerable, last_check, added_to_openwebui)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        ip, 
                        port, 
                        "Unknown", 
                        "Unknown", 
                        "Unknown", 
                        "Unknown", 
                        1,  # Available
                        0,  # No auth
                        1,  # Vulnerable
                        datetime.datetime.now().isoformat(), 
                        1   # Added to OpenWebUI
                    )
                )
            
            # Commit handled by Database methods
            ollama_# Commit handled by Database methods
            conn.close()
            ollama_conn.close()
            
            self.logger.info(f"Added endpoint {name} ({ip}:{port}) to OpenWebUI")
            
            return {
                "success": True,
                "message": f"Successfully added {ip}:{port} as '{name}' to OpenWebUI endpoints"
            }
        except Exception as e:
            self.logger.error(f"Error adding endpoint to OpenWebUI: {str(e)}")
            return {
                "success": False,
                "error": f"Error adding endpoint to OpenWebUI: {str(e)}"
            }
    
    def add_multiple_to_openwebui(
        self, 
        limit: Optional[int] = None, 
        available_only: bool = True,
        instances: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Add multiple Ollama instances to OpenWebUI.
        
        Args:
            limit: Maximum number of instances to add
            available_only: Whether to only add available instances
            instances: List of instances to add (if not provided, fetched from database)
            
        Returns:
            Dictionary with result of the operation
        """
        try:
            # Use the provided limit or default
            limit = limit if limit is not None else self.valves.MAX_AUTO_ADD
            
            # If instances not provided, get from database
            if instances is None:
                db_result = self.list_instances_from_db(limit=limit, available_only=available_only)
                
                if not db_result["success"]:
                    return db_result
                
                if len(db_result["instances"]) == 0:
                    return {
                        "success": False,
                        "error": "No instances found in database"
                    }
                
                instances = db_result["instances"]
            
            # Add each instance to OpenWebUI
            added = []
            failed = []
            
            for instance in instances[:limit]:
                # Skip if already added (when using DB instances)
                if instance.get("added_to_openwebui", 0) == 1:
                    continue
                
                # Get instance IP and port
                ip = instance.get("ip")
                port = instance.get("port", 11434)
                
                if not ip:
                    failed.append({
                        "error": "Instance missing IP address"
                    })
                    continue
                
                # Generate a name based on country or organization if available
                name_parts = []
                if instance.get("country") and instance["country"] != "Unknown":
                    name_parts.append(instance["country"])
                if instance.get("city") and instance["city"] != "Unknown":
                    name_parts.append(instance["city"])
                if instance.get("organization") and instance["organization"] != "Unknown":
                    name_parts.append(instance["organization"].split()[0])  # First word only
                
                if name_parts:
                    name = f"Ollama {' '.join(name_parts)} {ip}"
                else:
                    name = f"Ollama {ip}"
                
                result = self.add_to_openwebui(ip=ip, port=port, name=name)
                
                if result["success"]:
                    added.append({
                        "ip": ip,
                        "port": port,
                        "name": name
                    })
                else:
                    failed.append({
                        "ip": ip,
                        "port": port,
                        "error": result.get("error", "Unknown error")
                    })
            
            return {
                "success": True,
                "added_count": len(added),
                "failed_count": len(failed),
                "added": added,
                "failed": failed
            }
        except Exception as e:
            self.logger.error(f"Error adding multiple endpoints to OpenWebUI: {str(e)}")
            return {
                "success": False,
                "error": f"Error adding multiple endpoints to OpenWebUI: {str(e)}"
            }
    
    # ----- SECURITY ANALYSIS METHODS -----
    
    def check_instance_security(self, ip: str, port: int = 11434) -> Dict[str, Any]:
        """
        Perform security checks on an Ollama instance.
        
        Args:
            ip: IP address of the instance
            port: Port of the instance
            
        Returns:
            Dictionary with security assessment
        """
        if not self.valves.ENABLE_SECURITY_CHECKS:
            return {
                "success": False,
                "error": "Security checks are disabled. Enable them in the tool configuration."
            }
        
        # Input validation
        if not ip or not isinstance(ip, str):
            return {
                "success": False,
                "error": "Invalid IP address"
            }
            
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return {
                "success": False,
                "error": "Invalid port number. Must be between 1 and 65535."
            }
        
        try:
            self.logger.info(f"Performing security checks on {ip}:{port}")
            
            security_checks = {
                "publicly_accessible": True,  # We assume it's public if we can access it
                "authentication_enabled": False,
                "version": "Unknown",
                "vulnerabilities": []
            }
            
            # Check if the instance is available
            try:
                version_response = requests.get(
                    f"http://{ip}:{port}/api/version",
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                if version_response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Instance {ip}:{port} is not available"
                    }
                
                security_checks["version"] = version_response.json().get("version", "Unknown")
            except requests.exceptions.RequestException as e:
                return {
                    "success": False,
                    "error": f"Error connecting to instance: {str(e)}"
                }
            
            # Check for authentication
            auth_check = self._check_instance_auth(ip, port)
            security_checks["authentication_enabled"] = auth_check["has_auth"]
            
            # If no authentication, this is a vulnerability
            if not auth_check["has_auth"]:
                security_checks["vulnerabilities"].append({
                    "name": "No Authentication",
                    "severity": "HIGH",
                    "description": "The Ollama instance does not require authentication. Anyone can access and use the models, potentially leading to abuse or unexpected costs."
                })
            
            # Check for remote code execution vulnerabilities
            rce_check = self._check_rce_vulnerability(ip, port)
            if rce_check["vulnerable"]:
                security_checks["vulnerabilities"].append({
                    "name": "Potential Remote Code Execution",
                    "severity": "CRITICAL",
                    "description": f"The Ollama instance may be vulnerable to remote code execution: {rce_check.get('details', 'Unknown issues detected')}."
                })
            
            # Check for model access control
            models_check = self._check_model_access_control(ip, port)
            if models_check["vulnerable"]:
                security_checks["vulnerabilities"].append({
                    "name": "Unrestricted Model Access",
                    "severity": "MEDIUM",
                    "description": f"The Ollama instance allows unrestricted access to models: {models_check.get('details', 'No details available')}."
                })
            
            # Check for rate limiting
            rate_limit_check = self._check_rate_limiting(ip, port)
            if rate_limit_check["vulnerable"]:
                security_checks["vulnerabilities"].append({
                    "name": "No Rate Limiting",
                    "severity": "MEDIUM",
                    "description": "The Ollama instance does not appear to implement rate limiting, potentially allowing resource exhaustion attacks."
                })
            
            # Additional check: Assess TLS/HTTPS
            if not ip.startswith("127.") and not ip.startswith("192.168.") and not ip.startswith("10."):
                # Only relevant for non-local instances
                tls_check = self._check_tls_support(ip, port)
                if tls_check["vulnerable"]:
                    security_checks["vulnerabilities"].append({
                        "name": "Unencrypted Communication",
                        "severity": "HIGH",
                        "description": "The Ollama instance does not use TLS/HTTPS encryption, potentially exposing sensitive data."
                    })
                    
            # Update security score based on number and severity of vulnerabilities
            security_score = 100  # Start with perfect score
            severity_weights = {"LOW": 5, "MEDIUM": 15, "HIGH": 25, "CRITICAL": 40}
            
            for vuln in security_checks["vulnerabilities"]:
                severity = vuln.get("severity", "MEDIUM")
                security_score -= severity_weights.get(severity, 10)
            
            security_score = max(0, security_score)  # Ensure non-negative
            security_checks["security_score"] = security_score
            
            # Determine overall risk level
            if security_score >= 90:
                security_checks["risk_level"] = "LOW"
            elif security_score >= 70:
                security_checks["risk_level"] = "MEDIUM"
            elif security_score >= 40:
                security_checks["risk_level"] = "HIGH"
            else:
                security_checks["risk_level"] = "CRITICAL"
            
            # Update the instance in the database with security info
            self._update_instance_security(ip, port, {
                "has_auth": security_checks["authentication_enabled"],
                "is_vulnerable": len(security_checks["vulnerabilities"]) > 0
            })
            
            return {
                "success": True,
                "security_assessment": security_checks
            }
        except Exception as e:
            self.logger.error(f"Error checking instance security: {str(e)}")
            return {
                "success": False,
                "error": f"Error checking instance security: {str(e)}"
            }
            
    def _check_rce_vulnerability(self, ip: str, port: int) -> Dict[str, Any]:
        """Check if an Ollama instance is vulnerable to remote code execution."""
        try:
            # Non-exploitative security check that doesn't attempt dangerous commands
            # We specifically avoid attempting to exploit any potential vulnerabilities
            
            # Instead, check if the model allows accessing system-level prompts
            # by attempting a harmless model listing action
            vulnerable = False
            details = []
            
            # Check 1: Test if the echo model is available (indicates basic functionality)
            test_prompt_1 = {
                "model": "echo",  # Safe model that just echoes input
                "prompt": "security-check",
                "stream": False
            }
            
            try:
                response = requests.post(
                    f"http://{ip}:{port}/api/generate",
                    json=test_prompt_1,
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                if response.status_code == 200:
                    details.append("Instance accepts and runs the echo model")
            except Exception:
                pass
            
            # Check 2: See if instance has file-related capabilities
            # A more comprehensive security assessment would examine whether
            # the instance allows file operations, but we don't attempt this directly
            
            # Instead, check API info to infer capabilities
            try:
                api_info_response = requests.get(
                    f"http://{ip}:{port}/api/tags",
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                if api_info_response.status_code == 200:
                    data = api_info_response.json()
                    models = data.get("models", [])
                    
                    # Look for models that might have embedding or fine-tuning capabilities
                    # as these sometimes require more system access
                    for model in models:
                        model_name = model.get("name", "").lower()
                        if "llava" in model_name or "clip" in model_name or "embedding" in model_name:
                            details.append(f"Instance has multimodal or embedding model: {model_name}")
                            break
            except Exception:
                pass
            
            # Check 3: Check API configuration
            try:
                version_response = requests.get(
                    f"http://{ip}:{port}/api/version",
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                if version_response.status_code == 200:
                    version_data = version_response.json()
                    version = version_data.get("version", "unknown")
                    
                    # Check for known vulnerable Ollama versions
                    # This would need to be updated with security bulletins
                    if version in ["0.0.1", "0.0.2", "0.0.3"]:  # Example vulnerable versions
                        details.append(f"Instance is running potentially vulnerable version: {version}")
                        vulnerable = True
            except Exception:
                pass
                
            # Overall vulnerability assessment
            # In a real security scanner, we'd have more specific checks
            # For this tool, we consider any open instance without auth as potentially vulnerable
            if not details:
                return {"vulnerable": False}
                
            return {
                "vulnerable": vulnerable,
                "details": "; ".join(details)
            }
        except Exception as e:
            self.logger.debug(f"Error checking RCE vulnerability: {str(e)}")
            return {"vulnerable": False}
    
    def _check_model_access_control(self, ip: str, port: int) -> Dict[str, Any]:
        """Check if an Ollama instance has model access control."""
        try:
            # Get list of models to check for access control
            response = requests.get(
                f"http://{ip}:{port}/api/tags",
                timeout=self.valves.SCAN_TIMEOUT
            )
            
            if response.status_code != 200:
                # If we can't list models, instance might have some access controls
                return {"vulnerable": False}
            
            # Count models to determine if it's a public server
            data = response.json()
            models = data.get("models", [])
            model_count = len(models)
            
            # Check for interesting models that may be unintentionally exposed
            sensitive_models = []
            for model in models:
                name = model.get("name", "").lower()
                # Look for models that might be proprietary, fine-tuned, or expensive to run
                if any(term in name for term in ["gpt4", "claude", "private", "custom", "fine-tuned", "confidential"]):
                    sensitive_models.append(name)
            
            # Perform additional checks
            details = []
            if model_count > 10:
                details.append(f"Instance has {model_count} models accessible")
            if sensitive_models:
                details.append(f"Instance exposes potentially sensitive models: {', '.join(sensitive_models)}")
            
            if details:
                return {
                    "vulnerable": True,
                    "details": "; ".join(details)
                }
            
            # If there are no issues detected, still report as vulnerable but with less concern
            return {
                "vulnerable": True,
                "details": "Instance allows unrestricted model listing and access"
            }
        except Exception as e:
            self.logger.debug(f"Error checking model access control: {str(e)}")
            return {"vulnerable": False}
            
    def _check_rate_limiting(self, ip: str, port: int) -> Dict[str, bool]:
        """Check if an Ollama instance implements rate limiting."""
        try:
            # Send a few quick requests to check for rate limiting
            # This is a minimal check that won't cause harm
            
            # Use a very simple model and prompt to minimize resource usage
            test_prompt = {
                "model": "echo",  # Use echo model if available
                "prompt": "test",
                "stream": False
            }
            
            # Try 3 rapid requests to see if any are rate limited
            for _ in range(3):
                response = requests.post(
                    f"http://{ip}:{port}/api/generate",
                    json=test_prompt,
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                # Look for rate limiting headers or status codes
                if response.status_code == 429:  # Too Many Requests
                    return {"vulnerable": False}
                    
                # Check for rate limiting headers
                if any(header.lower() in response.headers for header in ["x-ratelimit-limit", "x-ratelimit-remaining", "retry-after"]):
                    return {"vulnerable": False}
                    
                # Short pause to avoid overloading the server
                time.sleep(0.5)
            
            # If no rate limiting was detected, consider it potentially vulnerable
            return {"vulnerable": True}
        except Exception:
            # If we can't complete the check, assume not vulnerable
            return {"vulnerable": False}
    
    def _check_tls_support(self, ip: str, port: int) -> Dict[str, bool]:
        """Check if an Ollama instance supports TLS/HTTPS."""
        try:
            # Try to connect using HTTPS
            response = requests.get(
                f"https://{ip}:{port}/api/version",
                timeout=self.valves.SCAN_TIMEOUT,
                verify=False  # Don't verify cert as it might be self-signed
            )
            
            # If we get any response, TLS is supported
            if response.status_code in [200, 401, 403]:
                return {"vulnerable": False}
            
            # Check for redirect to HTTPS
            http_response = requests.get(
                f"http://{ip}:{port}/api/version",
                timeout=self.valves.SCAN_TIMEOUT,
                allow_redirects=False
            )
            
            if http_response.status_code in [301, 302, 307, 308]:
                location = http_response.headers.get("Location", "")
                if location.startswith("https://"):
                    return {"vulnerable": False}
            
            # If we reach here, no TLS support was detected
            return {"vulnerable": True}
        except Exception:
            # If we can't check HTTPS, assume it's vulnerable (unencrypted)
            return {"vulnerable": True}
    
    def _update_instance_security(self, ip: str, port: int, security_info: Dict[str, Any]) -> bool:
        """Update security information for an instance in the database."""
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Check if instance exists
            cursor.execute(
                "SELECT id FROM ollama_instances WHERE ip = ? AND port = ?",
                (ip, port)
            )
            instance_row = Database.fetch_one(query, params)
            
            if not instance_row:
                conn.close()
                return False
            
            # Update security information
            cursor.execute(
                '''
                UPDATE ollama_instances SET
                has_auth = ?,
                is_vulnerable = ?
                WHERE ip = ? AND port = ?
                ''',
                (
                    1 if security_info.get("has_auth", False) else 0,
                    1 if security_info.get("is_vulnerable", True) else 0,
                    ip,
                    port
                )
            )
            
            # Commit handled by Database methods
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"Error updating instance security: {str(e)}")
            return False
    
    # ----- BENCHMARKING METHODS -----
    
    def benchmark_instance(
        self, 
        ip: str, 
        port: int = 11434, 
        model: str = "llama2", 
        prompt: str = "Explain how transformer models work in one paragraph."
    ) -> Dict[str, Any]:
        """
        Benchmark an Ollama instance for performance.
        
        Args:
            ip: IP address of the instance
            port: Port of the instance
            model: Model to use for benchmarking
            prompt: Test prompt to use
            
        Returns:
            Dictionary with benchmark results
        """
        if not self.valves.ENABLE_BENCHMARKING:
            return {
                "success": False,
                "error": "Benchmarking is disabled. Enable it in the tool configuration."
            }
        
        # Input validation
        if not ip or not isinstance(ip, str):
            return {
                "success": False,
                "error": "Invalid IP address"
            }
            
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return {
                "success": False,
                "error": "Invalid port number. Must be between 1 and 65535."
            }
            
        if not model or not isinstance(model, str):
            return {
                "success": False,
                "error": "Invalid model name"
            }
            
        # Validate prompt length to ensure we don't send something massive
        if not prompt or not isinstance(prompt, str) or len(prompt) > 5000:
            return {
                "success": False,
                "error": "Invalid prompt (must be a string under 5000 characters)"
            }
        
        try:
            self.logger.info(f"Benchmarking instance {ip}:{port} with model {model}")
            
            # First check if the model exists on the server
            try:
                models_response = requests.get(
                    f"http://{ip}:{port}/api/tags",
                    timeout=self.valves.SCAN_TIMEOUT
                )
                
                if models_response.status_code == 200:
                    model_data = models_response.json()
                    available_models = [m.get("name") for m in model_data.get("models", [])]
                    
                    # Check if our model exists
                    model_exists = False
                    for available in available_models:
                        if model.lower() == available.lower() or model.lower() in available.lower():
                            model_exists = True
                            model = available  # Use the exact model name from the server
                            break
                    
                    if not model_exists and available_models:
                        # Fall back to first available model if our requested one doesn't exist
                        self.logger.warning(f"Model {model} not found, falling back to {available_models[0]}")
                        model = available_models[0]
            except Exception as e:
                self.logger.warning(f"Could not check for model availability: {str(e)}")
            
            # Prepare the benchmark request
            benchmark_data = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 100  # Limit token generation for benchmarking
                }
            }
            
            # Measure performance
            start_time = time.time()
            
            response = requests.post(
                f"http://{ip}:{port}/api/generate",
                json=benchmark_data,
                timeout=60  # Longer timeout for benchmarking
            )
            
            end_time = time.time()
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Error benchmarking instance: Status code {response.status_code}, Response: {response.text[:200]}"
                }
            
            # Calculate metrics
            response_time = end_time - start_time
            
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "Invalid JSON response from server"
                }
            
            # Extract token counts if available
            prompt_tokens = response_data.get("prompt_eval_count", 0)
            completion_tokens = response_data.get("eval_count", 0)
            total_tokens = prompt_tokens + completion_tokens
            
            # Calculate tokens per second
            tokens_per_second = total_tokens / response_time if response_time > 0 else 0
            
            # Validate generated text
            generated_text = response_data.get("response", "")
            if not generated_text:
                self.logger.warning(f"No text generated in benchmark for {ip}:{port}")
            
            # Save benchmark results to database
            benchmark_result = {
                "ip": ip,
                "port": port,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "response_time": response_time,
                "tokens_per_second": tokens_per_second,
                "benchmark_date": datetime.datetime.now().isoformat(),
                "response_sample": generated_text[:100] if generated_text else ""
            }
            
            self._save_benchmark_result(ip, port, model, benchmark_result)
            
            return {
                "success": True,
                "benchmark": benchmark_result
            }
        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout benchmarking instance {ip}:{port}")
            return {
                "success": False,
                "error": f"Timeout benchmarking instance. The server may be overloaded or the model is too large."
            }
        except requests.exceptions.ConnectionError:
            self.logger.error(f"Connection error benchmarking instance {ip}:{port}")
            return {
                "success": False,
                "error": "Connection error. The server may be unavailable."
            }
        except Exception as e:
            self.logger.error(f"Error benchmarking instance: {str(e)}")
            return {
                "success": False,
                "error": f"Error benchmarking instance: {str(e)}"
            }
    
    def _save_benchmark_result(
        self, 
        ip: str, 
        port: int, 
        model: str, 
        benchmark: Dict[str, Any]
    ) -> bool:
        """Save benchmark results to the database."""
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Get instance ID
            cursor.execute(
                "SELECT id FROM ollama_instances WHERE ip = ? AND port = ?",
                (ip, port)
            )
            instance_row = Database.fetch_one(query, params)
            
            if not instance_row:
                conn.close()
                return False
            
            instance_id = instance_row[0]
            
            # Save benchmark results
            cursor.execute(
                '''
                INSERT INTO benchmark_results
                (instance_id, model_name, prompt_tokens, completion_tokens, total_tokens, 
                response_time, tokens_per_second, benchmark_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    instance_id,
                    model,
                    benchmark.get("prompt_tokens", 0),
                    benchmark.get("completion_tokens", 0),
                    benchmark.get("total_tokens", 0),
                    benchmark.get("response_time", 0),
                    benchmark.get("tokens_per_second", 0),
                    benchmark.get("benchmark_date", datetime.datetime.now().isoformat())
                )
            )
            
            # Commit handled by Database methods
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"Error saving benchmark results: {str(e)}")
            return False
    
    # ----- UTILITY METHODS -----
    
    def export_database(self, format: str = "json", include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Export the database to a specific format.
        
        Args:
            format: Export format (json, csv)
            include_sensitive: Whether to include potentially sensitive data like IP addresses
            
        Returns:
            Dictionary with export data
        """
        try:
            conn = Database()
            conn.row_factory = sqlite3.Row
            cursor = # Using Database methods instead of cursor
            
            # Check if the database has content
            Database.execute("SELECT COUNT(*) FROM ollama_instances")
            instance_count = Database.fetch_one(query, params)[0]
            
            if instance_count == 0:
                return {
                    "success": False,
                    "error": "Database is empty. Nothing to export."
                }
            
            # Get all instances
            Database.execute("SELECT * FROM ollama_instances")
            instance_rows = Database.fetch_all(query, params)
            instances = [dict(row) for row in instance_rows]
            
            # Get all models
            Database.execute("SELECT * FROM ollama_models")
            model_rows = Database.fetch_all(query, params)
            models = [dict(row) for row in model_rows]
            
            # Get all benchmark results
            Database.execute("SELECT * FROM benchmark_results")
            benchmark_rows = Database.fetch_all(query, params)
            benchmarks = [dict(row) for row in benchmark_rows]
            
            conn.close()
            
            # Sanitize sensitive information if requested
            if not include_sensitive:
                # Remove IP addresses and other sensitive data
                for instance in instances:
                    if "ip" in instance:
                        # Obscure the IP address by showing only the first octet
                        ip_parts = instance["ip"].split(".")
                        if len(ip_parts) == 4:  # IPv4
                            instance["ip"] = f"{ip_parts[0]}.***.***"
                        else:
                            instance["ip"] = "obscured"
            
            # Format data according to requested format
            export_data = {
                "instances": instances,
                "models": models,
                "benchmarks": benchmarks,
                "export_date": datetime.datetime.now().isoformat(),
                "statistics": {
                    "instance_count": len(instances),
                    "model_count": len(models),
                    "benchmark_count": len(benchmarks)
                }
            }
            
            if format.lower() == "json":
                # Check if the data is too large
                try:
                    json_str = json.dumps(export_data)
                    export_size_mb = len(json_str) / (1024 * 1024)
                    
                    if export_size_mb > 50:  # If more than 50MB
                        self.logger.warning(f"Large export: {export_size_mb:.2f}MB")
                        # Truncate the data for safety
                        export_data["instances"] = export_data["instances"][:100]
                        export_data["models"] = export_data["models"][:100]
                        export_data["benchmarks"] = export_data["benchmarks"][:100]
                        export_data["warning"] = "Data was truncated due to large size"
                except Exception as e:
                    self.logger.error(f"Error checking export size: {str(e)}")
                
                return {
                    "success": True,
                    "format": "json",
                    "data": export_data
                }
            elif format.lower() == "csv":
                # Convert to CSV format
                try:
                    csv_data = {
                        "instances": self._dict_list_to_csv(instances),
                        "models": self._dict_list_to_csv(models),
                        "benchmarks": self._dict_list_to_csv(benchmarks)
                    }
                    return {
                        "success": True,
                        "format": "csv",
                        "data": csv_data
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Error converting to CSV: {str(e)}"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Unsupported export format: {format}. Supported formats: json, csv"
                }
        except sqlite3.Error as e:
            self.logger.error(f"SQLite error exporting database: {str(e)}")
            return {
                "success": False,
                "error": f"Database error: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error exporting database: {str(e)}")
            return {
                "success": False,
                "error": f"Error exporting database: {str(e)}"
            }
    
    def _dict_list_to_csv(self, dict_list: List[Dict[str, Any]]) -> str:
        """Convert a list of dictionaries to CSV format."""
        if not dict_list:
            return ""
        
        # Get headers from the first dictionary
        headers = list(dict_list[0].keys())
        
        # Build CSV string
        csv_lines = [",".join(headers)]
        
        for item in dict_list:
            values = []
            for header in headers:
                # Convert value to string and escape commas
                value = str(item.get(header, ""))
                
                # Remove newlines, as they break CSV format
                value = value.replace("\n", " ").replace("\r", "")
                
                # Escape quotes and commas
                if "," in value or '"' in value:
                    value = value.replace('"', '""')
                    value = f'"{value}"'
                
                values.append(value)
            
            csv_lines.append(",".join(values))
        
        return "\n".join(csv_lines)
    
    def clear_database(self) -> Dict[str, bool]:
        """Clear all data from the database."""
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Clear tables
            Database.execute("DELETE FROM benchmark_results")
            Database.execute("DELETE FROM ollama_models")
            Database.execute("DELETE FROM ollama_instances")
            
            # Reset auto-increment counters
            Database.execute("DELETE FROM sqlite_sequence WHERE name IN ('benchmark_results', 'ollama_models', 'ollama_instances')")
            
            # Commit handled by Database methods
            conn.close()
            
            self.logger.info("Database cleared successfully")
            
            return {
                "success": True,
                "message": "Database cleared successfully"
            }
        except Exception as e:
            self.logger.error(f"Error clearing database: {str(e)}")
            return {
                "success": False,
                "error": f"Error clearing database: {str(e)}"
            }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database."""
        try:
            conn = Database()
            cursor = # Using Database methods instead of cursor
            
            # Get count of instances
            Database.execute("SELECT COUNT(*) FROM ollama_instances")
            instance_count = Database.fetch_one(query, params)[0]
            
            # Get count of available instances
            Database.execute("SELECT COUNT(*) FROM ollama_instances WHERE available = 1")
            available_count = Database.fetch_one(query, params)[0]
            
            # Get count of vulnerable instances
            Database.execute("SELECT COUNT(*) FROM ollama_instances WHERE is_vulnerable = 1")
            vulnerable_count = Database.fetch_one(query, params)[0]
            
            # Get count of instances added to OpenWebUI
            Database.execute("SELECT COUNT(*) FROM ollama_instances WHERE added_to_openwebui = 1")
            added_count = Database.fetch_one(query, params)[0]
            
            # Get count of models
            Database.execute("SELECT COUNT(*) FROM ollama_models")
            model_count = Database.fetch_one(query, params)[0]
            
            # Get count of benchmarks
            Database.execute("SELECT COUNT(*) FROM benchmark_results")
            benchmark_count = Database.fetch_one(query, params)[0]
            
            # Get country distribution
            Database.execute("SELECT country, COUNT(*) FROM ollama_instances GROUP BY country ORDER BY COUNT(*) DESC")
            country_distribution = {row[0]: row[1] for row in Database.fetch_all(query, params)}
            
            # Get model family distribution
            Database.execute("SELECT model_family, COUNT(*) FROM ollama_models GROUP BY model_family ORDER BY COUNT(*) DESC")
            model_family_distribution = {row[0]: row[1] for row in Database.fetch_all(query, params)}
            
            conn.close()
            
            return {
                "success": True,
                "instance_count": instance_count,
                "available_count": available_count,
                "vulnerable_count": vulnerable_count,
                "added_to_openwebui_count": added_count,
                "model_count": model_count,
                "benchmark_count": benchmark_count,
                "country_distribution": country_distribution,
                "model_family_distribution": model_family_distribution,
                "last_updated": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error getting database stats: {str(e)}")
            return {
                "success": False,
                "error": f"Error getting database stats: {str(e)}"
            }
            
    # ----- CONFIGURATION MANAGEMENT -----
    
    def set_configuration(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the tool's configuration (valves) from a dictionary.
        
        Args:
            config_dict: Dictionary containing configuration values
            
        Returns:
            Dictionary with update result
        """
        try:
            updated_keys = []
            invalid_keys = []
            
            # Check which keys are valid for our configuration
            valid_keys = set(self.valves.dict().keys())
            
            for config_key, config_value in config_dict.items():
                if config_key.upper() in valid_keys:
                    # Use uppercase for consistency
                    upper_key = config_key.upper()
                    
                    # Type checking before assignment
                    current_value = getattr(self.valves, upper_key)
                    # Use Python's built-in type function but don't assign to a variable named 'type'
                    current_type = type(current_value)
                    
                    # Special case for str vs NoneType
                    if current_value is None:
                        # If current value is None, we'll accept any type
                        setattr(self.valves, upper_key, config_value)
                        updated_keys.append(upper_key)
                    elif current_type is bool and isinstance(config_value, (bool, int)):
                        # Convert int to bool for boolean fields
                        setattr(self.valves, upper_key, bool(config_value))
                        updated_keys.append(upper_key)
                    elif isinstance(config_value, current_type):
                        # Same type, direct assignment
                        setattr(self.valves, upper_key, config_value)
                        updated_keys.append(upper_key)
                    else:
                        # Type mismatch
                        # Use type() but don't store in a variable named 'type'
                        invalid_keys.append(f"{config_key} (expected {current_type.__name__}, got {type(config_value).__name__})")
                else:
                    invalid_keys.append(config_key)
            
            if updated_keys:
                self.logger.info(f"Updated configuration values: {', '.join(updated_keys)}")
                
                # Re-initialize components if necessary
                if any(key in ["DB_PATH", "OPENWEBUI_DB_PATH"] for key in updated_keys):
                    self._setup_database()
            
            result = {
                "success": len(updated_keys) > 0,
                "updated_keys": updated_keys,
                "invalid_keys": invalid_keys,
                "current_config": self.get_configuration()["config"]
            }
            
            return result
        except Exception as e:
            self.logger.error(f"Error updating configuration: {str(e)}")
            return {
                "success": False,
                "error": f"Error updating configuration: {str(e)}"
            }
    
    def get_configuration(self) -> Dict[str, Any]:
        """
        Get the current configuration (valves).
        
        Returns:
            Dictionary with current configuration
        """
        try:
            # Convert pydantic model to dict
            config = self.valves.dict()
            
            # Add some additional metadata
            config["_last_updated"] = datetime.datetime.now().isoformat()
            
            return {
                "success": True,
                "config": config
            }
        except Exception as e:
            self.logger.error(f"Error getting configuration: {str(e)}")
            return {
                "success": False,
                "error": f"Error getting configuration: {str(e)}"
            }
    
    def save_configuration(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Save the current configuration to a file.
        
        Args:
            file_path: Path to save the configuration file (JSON)
            
        Returns:
            Dictionary with save result
        """
        if not file_path:
            # Use a default path based on the database path
            db_dir = os.path.dirname(self.valves.DB_PATH)
            file_path = os.path.join(db_dir, "ollama_scanner_config.json")
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Get current configuration
            config = self.valves.dict()
            
            # Add metadata
            config["_saved_at"] = datetime.datetime.now().isoformat()
            config["_version"] = "2.0.0"  # Configuration format version
            
            # Write to file
            with open(file_path, "w") as f:
                json.dump(config, f, indent=2)
            
            self.logger.info(f"Configuration saved to {file_path}")
            
            return {
                "success": True,
                "file_path": file_path
            }
        except Exception as e:
            self.logger.error(f"Error saving configuration: {str(e)}")
            return {
                "success": False,
                "error": f"Error saving configuration: {str(e)}"
            }
    
    def load_configuration(self, file_path: str) -> Dict[str, Any]:
        """
        Load configuration from a file.
        
        Args:
            file_path: Path to the configuration file (JSON)
            
        Returns:
            Dictionary with load result
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"Configuration file not found: {file_path}"
                }
            
            # Read configuration from file
            with open(file_path, "r") as f:
                config = json.load(f)
            
            # Remove metadata fields
            for key in list(config.keys()):
                if key.startswith("_"):
                    del config[key]
            
            # Update configuration
            result = self.set_configuration(config)
            result["loaded_from"] = file_path
            
            self.logger.info(f"Configuration loaded from {file_path}")
            
            return result
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in configuration file: {file_path}")
            return {
                "success": False,
                "error": "Invalid JSON in configuration file"
            }
        except Exception as e:
            self.logger.error(f"Error loading configuration: {str(e)}")
            return {
                "success": False,
                "error": f"Error loading configuration: {str(e)}"
            }