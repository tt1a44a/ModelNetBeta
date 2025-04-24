#!/usr/bin/env python3
"""
Database Updates for LocalAI Support
Provides additional methods for handling LocalAI endpoints in the database
"""

import logging
import json
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from database import Database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("database_updates.log")
    ]
)
logger = logging.getLogger('database_updates')

class DatabaseUpdates:
    """Extended database functionality for LocalAI support"""
    
    # Valid API types
    VALID_API_TYPES = ['ollama', 'localai']
    
    # Valid capability types
    VALID_CAPABILITIES = ['chat', 'completion', 'embedding', 'vision', 'audio', 'function_calling']
    
    @staticmethod
    def get_endpoints_by_api_type(api_type: str) -> List[Dict[str, Any]]:
        """
        Get all endpoints of a specific API type (ollama or localai)
        
        Args:
            api_type: The API type to filter by ('ollama' or 'localai')
            
        Returns:
            List of endpoint dictionaries
        """
        try:
            if api_type not in DatabaseUpdates.VALID_API_TYPES:
                logger.warning(f"Invalid API type: {api_type}. Must be one of {DatabaseUpdates.VALID_API_TYPES}")
                return []
                
            query = """
                SELECT * FROM endpoints 
                WHERE api_type = %s
                ORDER BY last_check_date DESC
            """
            results = Database.fetch_all(query, (api_type,))
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error fetching endpoints by API type: {str(e)}")
            return []
    
    @staticmethod
    def update_endpoint_api_type(endpoint_id: int, api_type: str, api_version: Optional[str] = None) -> bool:
        """
        Update an endpoint's API type and version
        
        Args:
            endpoint_id: The ID of the endpoint to update
            api_type: The new API type ('ollama' or 'localai')
            api_version: Optional API version string
            
        Returns:
            bool indicating success
        """
        try:
            if api_type not in DatabaseUpdates.VALID_API_TYPES:
                logger.warning(f"Invalid API type: {api_type}. Must be one of {DatabaseUpdates.VALID_API_TYPES}")
                return False
                
            # Start a transaction
            with Database.transaction():
                query = """
                    UPDATE endpoints 
                    SET api_type = %s, api_version = %s, last_check_date = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                Database.execute(query, (api_type, api_version, endpoint_id))
                
                # Log the change in metadata
                Database.execute("""
                    INSERT INTO metadata (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                """, (f"endpoint_{endpoint_id}_api_type_change", 
                      json.dumps({"old_type": None, "new_type": api_type, "timestamp": time.time()}),
                      json.dumps({"old_type": None, "new_type": api_type, "timestamp": time.time()})))
                
            return True
        except Exception as e:
            logger.error(f"Error updating endpoint API type: {str(e)}")
            return False
    
    @staticmethod
    def get_endpoint_capabilities(endpoint_id: int) -> Dict[str, Any]:
        """
        Get the capabilities of an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            
        Returns:
            Dictionary of capabilities
        """
        try:
            query = """
                SELECT capabilities 
                FROM endpoints 
                WHERE id = %s
            """
            result = Database.fetch_one(query, (endpoint_id,))
            if result and result[0]:
                return result[0]
            return {}
        except Exception as e:
            logger.error(f"Error fetching endpoint capabilities: {str(e)}")
            return {}
    
    @staticmethod
    def update_endpoint_capabilities(endpoint_id: int, capabilities: Dict[str, Any]) -> bool:
        """
        Update an endpoint's capabilities
        
        Args:
            endpoint_id: The ID of the endpoint
            capabilities: Dictionary of capabilities to set
            
        Returns:
            bool indicating success
        """
        try:
            # Validate capabilities
            for cap in capabilities:
                if cap not in DatabaseUpdates.VALID_CAPABILITIES:
                    logger.warning(f"Unknown capability: {cap}. Valid capabilities are: {DatabaseUpdates.VALID_CAPABILITIES}")
            
            # Start a transaction
            with Database.transaction():
                query = """
                    UPDATE endpoints 
                    SET capabilities = %s, last_check_date = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                Database.execute(query, (capabilities, endpoint_id))
                
                # Log the change in metadata
                Database.execute("""
                    INSERT INTO metadata (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                """, (f"endpoint_{endpoint_id}_capabilities_change", 
                      json.dumps({"capabilities": capabilities, "timestamp": time.time()}),
                      json.dumps({"capabilities": capabilities, "timestamp": time.time()})))
                
            return True
        except Exception as e:
            logger.error(f"Error updating endpoint capabilities: {str(e)}")
            return False
    
    @staticmethod
    def get_endpoints_by_capability(capability: str) -> List[Dict[str, Any]]:
        """
        Get all endpoints that have a specific capability
        
        Args:
            capability: The capability to search for
            
        Returns:
            List of endpoint dictionaries
        """
        try:
            if capability not in DatabaseUpdates.VALID_CAPABILITIES:
                logger.warning(f"Invalid capability: {capability}. Must be one of {DatabaseUpdates.VALID_CAPABILITIES}")
                return []
                
            query = """
                SELECT * FROM endpoints 
                WHERE capabilities::jsonb ? %s
                ORDER BY last_check_date DESC
            """
            results = Database.fetch_all(query, (capability,))
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error fetching endpoints by capability: {str(e)}")
            return []
    
    @staticmethod
    def get_endpoints_requiring_auth() -> List[Dict[str, Any]]:
        """
        Get all endpoints that require authentication
        
        Returns:
            List of endpoint dictionaries
        """
        try:
            query = """
                SELECT * FROM endpoints 
                WHERE auth_required = true
                ORDER BY last_check_date DESC
            """
            results = Database.fetch_all(query)
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error fetching endpoints requiring auth: {str(e)}")
            return []
    
    @staticmethod
    def get_endpoint_stats() -> Dict[str, Any]:
        """
        Get statistics about endpoints grouped by API type
        
        Returns:
            Dictionary containing endpoint statistics
        """
        try:
            query = """
                SELECT 
                    api_type,
                    COUNT(*) as total,
                    COUNT(CASE WHEN is_active = true THEN 1 END) as active,
                    COUNT(CASE WHEN auth_required = true THEN 1 END) as auth_required,
                    COUNT(CASE WHEN is_honeypot = true THEN 1 END) as honeypots
                FROM endpoints
                GROUP BY api_type
            """
            results = Database.fetch_all(query)
            stats = {}
            for row in results:
                api_type = row['api_type'] or 'unknown'
                stats[api_type] = {
                    'total': row['total'],
                    'active': row['active'],
                    'auth_required': row['auth_required'],
                    'honeypots': row['honeypots']
                }
            return stats
        except Exception as e:
            logger.error(f"Error fetching endpoint stats: {str(e)}")
            return {}
            
    @staticmethod
    def create_endpoint(ip: str, port: int, api_type: str = 'ollama', 
                       api_version: Optional[str] = None, 
                       capabilities: Optional[Dict[str, Any]] = None,
                       auth_required: bool = False) -> Optional[int]:
        """
        Create a new endpoint in the database
        
        Args:
            ip: IP address of the endpoint
            port: Port number of the endpoint
            api_type: API type ('ollama' or 'localai')
            api_version: API version string
            capabilities: Dictionary of capabilities
            auth_required: Whether authentication is required
            
        Returns:
            ID of the created endpoint or None if creation failed
        """
        try:
            if api_type not in DatabaseUpdates.VALID_API_TYPES:
                logger.warning(f"Invalid API type: {api_type}. Must be one of {DatabaseUpdates.VALID_API_TYPES}")
                return None
                
            # Validate capabilities if provided
            if capabilities:
                for cap in capabilities:
                    if cap not in DatabaseUpdates.VALID_CAPABILITIES:
                        logger.warning(f"Unknown capability: {cap}. Valid capabilities are: {DatabaseUpdates.VALID_CAPABILITIES}")
            
            # Check if endpoint already exists
            query = """
                SELECT id FROM endpoints 
                WHERE ip = %s AND port = %s
            """
            existing = Database.fetch_one(query, (ip, port))
            if existing:
                logger.info(f"Endpoint {ip}:{port} already exists with ID {existing[0]}")
                return existing[0]
            
            # Create new endpoint
            with Database.transaction():
                query = """
                    INSERT INTO endpoints 
                    (ip, port, api_type, api_version, capabilities, auth_required, scan_date, last_check_date)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """
                result = Database.fetch_one(query, (ip, port, api_type, api_version, capabilities, auth_required))
                if result:
                    endpoint_id = result[0]
                    logger.info(f"Created new endpoint {ip}:{port} with ID {endpoint_id}")
                    return endpoint_id
                return None
        except Exception as e:
            logger.error(f"Error creating endpoint: {str(e)}")
            return None
            
    @staticmethod
    def update_endpoint_status(endpoint_id: int, is_active: bool, 
                              inactive_reason: Optional[str] = None,
                              is_honeypot: Optional[bool] = None,
                              honeypot_reason: Optional[str] = None) -> bool:
        """
        Update an endpoint's status (active/inactive, honeypot)
        
        Args:
            endpoint_id: The ID of the endpoint to update
            is_active: Whether the endpoint is active
            inactive_reason: Reason for inactivity if not active
            is_honeypot: Whether the endpoint is a honeypot
            honeypot_reason: Reason for honeypot classification
            
        Returns:
            bool indicating success
        """
        try:
            # Start a transaction
            with Database.transaction():
                # Build the query dynamically based on provided parameters
                query_parts = ["UPDATE endpoints SET last_check_date = CURRENT_TIMESTAMP"]
                params = []
                
                if is_active is not None:
                    query_parts.append("is_active = %s")
                    params.append(is_active)
                    
                if inactive_reason is not None:
                    query_parts.append("inactive_reason = %s")
                    params.append(inactive_reason)
                    
                if is_honeypot is not None:
                    query_parts.append("is_honeypot = %s")
                    params.append(is_honeypot)
                    
                if honeypot_reason is not None:
                    query_parts.append("honeypot_reason = %s")
                    params.append(honeypot_reason)
                
                query_parts.append("WHERE id = %s")
                params.append(endpoint_id)
                
                query = ", ".join(query_parts)
                Database.execute(query, tuple(params))
                
                # Log the change in metadata
                change_data = {
                    "timestamp": time.time(),
                    "is_active": is_active,
                    "inactive_reason": inactive_reason,
                    "is_honeypot": is_honeypot,
                    "honeypot_reason": honeypot_reason
                }
                
                Database.execute("""
                    INSERT INTO metadata (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                """, (f"endpoint_{endpoint_id}_status_change", 
                      json.dumps(change_data),
                      json.dumps(change_data)))
                
            return True
        except Exception as e:
            logger.error(f"Error updating endpoint status: {str(e)}")
            return False
            
    @staticmethod
    def get_endpoint_by_id(endpoint_id: int) -> Optional[Dict[str, Any]]:
        """
        Get an endpoint by its ID
        
        Args:
            endpoint_id: The ID of the endpoint
            
        Returns:
            Dictionary containing endpoint data or None if not found
        """
        try:
            query = """
                SELECT * FROM endpoints 
                WHERE id = %s
            """
            result = Database.fetch_one(query, (endpoint_id,))
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching endpoint by ID: {str(e)}")
            return None
            
    @staticmethod
    def get_endpoint_by_ip_port(ip: str, port: int) -> Optional[Dict[str, Any]]:
        """
        Get an endpoint by its IP and port
        
        Args:
            ip: IP address of the endpoint
            port: Port number of the endpoint
            
        Returns:
            Dictionary containing endpoint data or None if not found
        """
        try:
            query = """
                SELECT * FROM endpoints 
                WHERE ip = %s AND port = %s
            """
            result = Database.fetch_one(query, (ip, port))
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching endpoint by IP/port: {str(e)}")
            return None
            
    @staticmethod
    def delete_endpoint(endpoint_id: int) -> bool:
        """
        Delete an endpoint from the database
        
        Args:
            endpoint_id: The ID of the endpoint to delete
            
        Returns:
            bool indicating success
        """
        try:
            # Start a transaction
            with Database.transaction():
                # Log the deletion in metadata
                endpoint = DatabaseUpdates.get_endpoint_by_id(endpoint_id)
                if endpoint:
                    Database.execute("""
                        INSERT INTO metadata (key, value, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                    """, (f"endpoint_{endpoint_id}_deletion", 
                          json.dumps({"endpoint": endpoint, "timestamp": time.time()}),
                          json.dumps({"endpoint": endpoint, "timestamp": time.time()})))
                
                # Delete the endpoint (cascade will handle related records)
                query = """
                    DELETE FROM endpoints 
                    WHERE id = %s
                """
                Database.execute(query, (endpoint_id,))
                
            return True
        except Exception as e:
            logger.error(f"Error deleting endpoint: {str(e)}")
            return False
            
    @staticmethod
    def get_endpoint_models(endpoint_id: int) -> List[Dict[str, Any]]:
        """
        Get all models for an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            
        Returns:
            List of model dictionaries
        """
        try:
            query = """
                SELECT * FROM models 
                WHERE endpoint_id = %s
                ORDER BY name
            """
            results = Database.fetch_all(query, (endpoint_id,))
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error fetching endpoint models: {str(e)}")
            return []
            
    @staticmethod
    def add_model_to_endpoint(endpoint_id: int, name: str, 
                             parameter_size: Optional[str] = None,
                             quantization_level: Optional[str] = None,
                             size_mb: Optional[float] = None,
                             model_type: Optional[str] = None,
                             capabilities: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Add a model to an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            name: Name of the model
            parameter_size: Parameter size of the model
            quantization_level: Quantization level of the model
            size_mb: Size of the model in MB
            model_type: Type of the model
            capabilities: Capabilities of the model
            
        Returns:
            ID of the created model or None if creation failed
        """
        try:
            # Check if endpoint exists
            endpoint = DatabaseUpdates.get_endpoint_by_id(endpoint_id)
            if not endpoint:
                logger.warning(f"Endpoint with ID {endpoint_id} does not exist")
                return None
                
            # Check if model already exists for this endpoint
            query = """
                SELECT id FROM models 
                WHERE endpoint_id = %s AND name = %s
            """
            existing = Database.fetch_one(query, (endpoint_id, name))
            if existing:
                logger.info(f"Model {name} already exists for endpoint {endpoint_id} with ID {existing[0]}")
                return existing[0]
            
            # Add new model
            with Database.transaction():
                query = """
                    INSERT INTO models 
                    (endpoint_id, name, parameter_size, quantization_level, size_mb, model_type, capabilities)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """
                result = Database.fetch_one(query, (endpoint_id, name, parameter_size, 
                                                  quantization_level, size_mb, model_type, capabilities))
                if result:
                    model_id = result[0]
                    logger.info(f"Added model {name} to endpoint {endpoint_id} with ID {model_id}")
                    return model_id
                return None
        except Exception as e:
            logger.error(f"Error adding model to endpoint: {str(e)}")
            return None
            
    @staticmethod
    def get_endpoint_benchmarks(endpoint_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get benchmark results for an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            limit: Maximum number of results to return
            
        Returns:
            List of benchmark result dictionaries
        """
        try:
            query = """
                SELECT * FROM benchmark_results 
                WHERE endpoint_id = %s
                ORDER BY test_date DESC
                LIMIT %s
            """
            results = Database.fetch_all(query, (endpoint_id, limit))
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error fetching endpoint benchmarks: {str(e)}")
            return []
            
    @staticmethod
    def add_benchmark_result(endpoint_id: int, model_id: Optional[int], 
                            avg_response_time: float, tokens_per_second: float,
                            first_token_latency: Optional[float] = None,
                            throughput_tokens: Optional[float] = None,
                            throughput_time: Optional[float] = None,
                            context_500_tps: Optional[float] = None,
                            context_1000_tps: Optional[float] = None,
                            context_2000_tps: Optional[float] = None,
                            max_concurrent_requests: Optional[int] = None,
                            concurrency_success_rate: Optional[float] = None,
                            concurrency_avg_time: Optional[float] = None,
                            success_rate: Optional[float] = None) -> Optional[int]:
        """
        Add a benchmark result for an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            model_id: The ID of the model (optional)
            avg_response_time: Average response time
            tokens_per_second: Tokens per second
            first_token_latency: First token latency (optional)
            throughput_tokens: Throughput in tokens (optional)
            throughput_time: Throughput time (optional)
            context_500_tps: Context 500 tokens per second (optional)
            context_1000_tps: Context 1000 tokens per second (optional)
            context_2000_tps: Context 2000 tokens per second (optional)
            max_concurrent_requests: Maximum concurrent requests (optional)
            concurrency_success_rate: Concurrency success rate (optional)
            concurrency_avg_time: Concurrency average time (optional)
            success_rate: Success rate (optional)
            
        Returns:
            ID of the created benchmark result or None if creation failed
        """
        try:
            # Check if endpoint exists
            endpoint = DatabaseUpdates.get_endpoint_by_id(endpoint_id)
            if not endpoint:
                logger.warning(f"Endpoint with ID {endpoint_id} does not exist")
                return None
                
            # Check if model exists if model_id is provided
            if model_id:
                query = """
                    SELECT id FROM models 
                    WHERE id = %s
                """
                model = Database.fetch_one(query, (model_id,))
                if not model:
                    logger.warning(f"Model with ID {model_id} does not exist")
                    return None
            
            # Add new benchmark result
            with Database.transaction():
                query = """
                    INSERT INTO benchmark_results 
                    (endpoint_id, model_id, avg_response_time, tokens_per_second,
                     first_token_latency, throughput_tokens, throughput_time,
                     context_500_tps, context_1000_tps, context_2000_tps,
                     max_concurrent_requests, concurrency_success_rate,
                     concurrency_avg_time, success_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """
                result = Database.fetch_one(query, (endpoint_id, model_id, avg_response_time, tokens_per_second,
                                                  first_token_latency, throughput_tokens, throughput_time,
                                                  context_500_tps, context_1000_tps, context_2000_tps,
                                                  max_concurrent_requests, concurrency_success_rate,
                                                  concurrency_avg_time, success_rate))
                if result:
                    benchmark_id = result[0]
                    logger.info(f"Added benchmark result for endpoint {endpoint_id} with ID {benchmark_id}")
                    return benchmark_id
                return None
        except Exception as e:
            logger.error(f"Error adding benchmark result: {str(e)}")
            return None
            
    @staticmethod
    def get_endpoint_history(endpoint_id: int) -> Dict[str, Any]:
        """
        Get the history of changes for an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            
        Returns:
            Dictionary containing endpoint history
        """
        try:
            query = """
                SELECT key, value, updated_at FROM metadata
                WHERE key LIKE %s
                ORDER BY updated_at DESC
            """
            results = Database.fetch_all(query, (f"endpoint_{endpoint_id}_%",))
            
            history = {
                "api_type_changes": [],
                "capability_changes": [],
                "status_changes": [],
                "deletions": []
            }
            
            for row in results:
                key = row['key']
                value = json.loads(row['value'])
                updated_at = row['updated_at']
                
                if "api_type_change" in key:
                    history["api_type_changes"].append({
                        "timestamp": updated_at,
                        "data": value
                    })
                elif "capabilities_change" in key:
                    history["capability_changes"].append({
                        "timestamp": updated_at,
                        "data": value
                    })
                elif "status_change" in key:
                    history["status_changes"].append({
                        "timestamp": updated_at,
                        "data": value
                    })
                elif "deletion" in key:
                    history["deletions"].append({
                        "timestamp": updated_at,
                        "data": value
                    })
            
            return history
        except Exception as e:
            logger.error(f"Error fetching endpoint history: {str(e)}")
            return {}
            
    @staticmethod
    def search_endpoints(query: str, api_type: Optional[str] = None, 
                        active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Search for endpoints based on a query string
        
        Args:
            query: Search query (IP, port, or model name)
            api_type: Filter by API type (optional)
            active_only: Only return active endpoints
            
        Returns:
            List of endpoint dictionaries
        """
        try:
            # Build the query dynamically
            query_parts = ["SELECT DISTINCT e.* FROM endpoints e"]
            params = []
            
            # Join with models if searching by model name
            if query and not query.replace(".", "").isdigit():
                query_parts.append("LEFT JOIN models m ON e.id = m.endpoint_id")
                query_parts.append("WHERE (m.name ILIKE %s OR e.ip ILIKE %s)")
                params.extend([f"%{query}%", f"%{query}%"])
            elif query:
                query_parts.append("WHERE e.ip ILIKE %s")
                params.append(f"%{query}%")
            else:
                query_parts.append("WHERE 1=1")
            
            # Add API type filter
            if api_type:
                if api_type not in DatabaseUpdates.VALID_API_TYPES:
                    logger.warning(f"Invalid API type: {api_type}. Must be one of {DatabaseUpdates.VALID_API_TYPES}")
                    return []
                    
                query_parts.append("AND e.api_type = %s")
                params.append(api_type)
            
            # Add active filter
            if active_only:
                query_parts.append("AND e.is_active = true")
            
            # Add ordering
            query_parts.append("ORDER BY e.last_check_date DESC")
            
            # Execute the query
            query_str = " ".join(query_parts)
            results = Database.fetch_all(query_str, tuple(params))
            return [dict(row) for row in results] if results else []
        except Exception as e:
            logger.error(f"Error searching endpoints: {str(e)}")
            return []
            
    @staticmethod
    def get_endpoint_health(endpoint_id: int) -> Dict[str, Any]:
        """
        Get health information for an endpoint
        
        Args:
            endpoint_id: The ID of the endpoint
            
        Returns:
            Dictionary containing health information
        """
        try:
            endpoint = DatabaseUpdates.get_endpoint_by_id(endpoint_id)
            if not endpoint:
                return {"status": "unknown", "message": "Endpoint not found"}
                
            # Get the latest benchmark result
            benchmarks = DatabaseUpdates.get_endpoint_benchmarks(endpoint_id, limit=1)
            latest_benchmark = benchmarks[0] if benchmarks else None
            
            # Determine health status
            status = "unknown"
            message = ""
            
            if not endpoint.get('is_active', True):
                status = "inactive"
                message = endpoint.get('inactive_reason', 'Unknown reason')
            elif endpoint.get('is_honeypot', False):
                status = "honeypot"
                message = endpoint.get('honeypot_reason', 'Detected as honeypot')
            elif not endpoint.get('verified', 0):
                status = "unverified"
                message = "Endpoint not yet verified"
            elif latest_benchmark:
                # Check benchmark results
                success_rate = latest_benchmark.get('success_rate', 0)
                if success_rate < 0.5:
                    status = "degraded"
                    message = f"Low success rate: {success_rate:.2%}"
                else:
                    status = "healthy"
                    message = f"Success rate: {success_rate:.2%}"
            else:
                status = "verified"
                message = "No benchmark data available"
            
            return {
                "status": status,
                "message": message,
                "last_check": endpoint.get('last_check_date'),
                "api_type": endpoint.get('api_type', 'unknown'),
                "api_version": endpoint.get('api_version'),
                "capabilities": endpoint.get('capabilities', {}),
                "models_count": len(DatabaseUpdates.get_endpoint_models(endpoint_id)),
                "latest_benchmark": latest_benchmark
            }
        except Exception as e:
            logger.error(f"Error getting endpoint health: {str(e)}")
            return {"status": "error", "message": str(e)}
            
    @staticmethod
    def get_database_health() -> Dict[str, Any]:
        """
        Get health information for the database
        
        Returns:
            Dictionary containing database health information
        """
        try:
            # Get table sizes
            query = """
                SELECT 
                    relname as table_name,
                    n_live_tup as row_count,
                    n_dead_tup as dead_tuples,
                    last_vacuum,
                    last_autovacuum,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables
                WHERE relname IN ('endpoints', 'verified_endpoints', 'models', 'benchmark_results', 'metadata')
                ORDER BY n_live_tup DESC
            """
            table_stats = Database.fetch_all(query)
            
            # Get index sizes
            query = """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    idx_scan as index_scans,
                    idx_tup_read as tuples_read,
                    idx_tup_fetch as tuples_fetched
                FROM pg_stat_user_indexes
                WHERE tablename IN ('endpoints', 'verified_endpoints', 'models', 'benchmark_results')
                ORDER BY idx_scan DESC
            """
            index_stats = Database.fetch_all(query)
            
            # Get database size
            query = """
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
            """
            db_size = Database.fetch_one(query)
            
            # Get endpoint statistics
            endpoint_stats = DatabaseUpdates.get_endpoint_stats()
            
            return {
                "database_size": db_size[0] if db_size else "unknown",
                "table_statistics": [dict(row) for row in table_stats] if table_stats else [],
                "index_statistics": [dict(row) for row in index_stats] if index_stats else [],
                "endpoint_statistics": endpoint_stats,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Error getting database health: {str(e)}")
            return {"status": "error", "message": str(e)} 