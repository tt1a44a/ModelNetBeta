#!/usr/bin/env python3
"""
Prune Bad Ollama Endpoints

This script removes Ollama instances from the database that return nonsensical
responses or fail to respond. It also detects and filters out honeypots and fake
Ollama implementations.
"""

import requests
import json
import argparse
import logging
import sys
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import threading

# Added by migration script
from database import Database, init_database, get_db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('prune_endpoints.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Log database configuration
db_type = os.environ.get('DATABASE_TYPE', 'postgres').lower()
if db_type == 'postgres':
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    pg_port = os.environ.get('POSTGRES_PORT', '5432')
    pg_db = os.environ.get('POSTGRES_DB', 'ollama_scanner')
    pg_user = os.environ.get('POSTGRES_USER', 'ollama')
    logger.info(f"Using PostgreSQL: {pg_user}@{pg_host}:{pg_port}/{pg_db}")
else:
    logger.warning("Non-PostgreSQL database type detected. This script now requires PostgreSQL.")

# Maximum number of retries for API requests
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds between retries

def get_all_servers():
    """
    Get all servers from the database - checks both servers view and endpoints table
    to ensure we find all potential endpoints to verify
    """
    logger.info("Getting servers from database...")
    
    # Ensure database connection is properly initialized
    Database.ensure_pool_initialized()
    
    # First try using the servers view (which contains already verified endpoints)
    servers_query = '''
        SELECT id, ip, port, scan_date
        FROM servers
        ORDER BY scan_date DESC
    '''
    servers = Database.fetch_all(servers_query)
    
    if servers:
        logger.info(f"Found {len(servers)} servers in the servers view")
        return servers
    
    # If no servers found in the view, look directly in the endpoints table
    logger.info("No servers found in servers view, checking endpoints table...")
    endpoints_query = '''
        SELECT id, ip, port, scan_date
        FROM endpoints
        WHERE verified = 0 OR verified = 1  -- Include both unverified (0) and verified (1) endpoints
        ORDER BY scan_date DESC
    '''
    endpoints = Database.fetch_all(endpoints_query)
    
    if endpoints:
        logger.info(f"Found {len(endpoints)} endpoints in the endpoints table")
        return endpoints
    
    # If still no results, log a warning
    logger.warning("No endpoints found in the database at all. Scanner may not have run yet.")
    return []

def is_valid_response(text):
    """
    Check if a response is valid (not nonsensical)
    
    Args:
        text: The response text to check
        
    Returns:
        bool: True if the response seems valid, False otherwise
    """
    # Check if response is mostly random characters
    # Valid responses should have proper words and sentences
    
    # Count words that look like English words
    word_pattern = re.compile(r'\b[a-zA-Z]{2,}\b')
    words = word_pattern.findall(text)
    
    # Count total space-separated tokens
    tokens = text.split()
    
    if not tokens:
        return False
    
    # If we have a good ratio of English-looking words, it's probably valid
    word_ratio = len(words) / len(tokens) if tokens else 0
    
    # Check for common English words that should appear in normal responses
    common_words = ['the', 'a', 'and', 'is', 'to', 'in', 'it', 'you', 'that', 'of']
    has_common_words = any(word.lower() in text.lower() for word in common_words)
    
    # If the text is very short, it might be valid even without common words
    if len(text) < 20:
        return word_ratio > 0.5
    
    # Longer text should have common words and a good word ratio
    return word_ratio > 0.5 and has_common_words

def is_honeypot(models_data, generate_response=None):
    """
    Detect if an endpoint is likely a honeypot or fake Ollama implementation
    
    Args:
        models_data: JSON response from /api/tags
        generate_response: Optional JSON response from /api/generate
        
    Returns:
        tuple: (is_honeypot, reason) - Boolean indicating if it's a honeypot and why
    """
    # 1. Check for fake-ollama signatures
    ## These are based on the repo at https://github.com/spoonnotfound/fake-ollama
    if models_data and "models" in models_data:
        # Check if all models are DeepSeek models (fake-ollama pattern)
        all_models = models_data.get("models", [])
        if all_models:
            deepseek_count = 0
            for model in all_models:
                model_name = model.get("name", "").lower()
                if "deepseek" in model_name or "r1" in model_name:
                    deepseek_count += 1
            
            # If all or most models are DeepSeek, it may be a honeypot
            if deepseek_count > 0 and deepseek_count >= len(all_models) * 0.8:
                return True, "Most/all models are DeepSeek variants (likely fake-ollama honeypot)"
    
    # 2. Check suspicious response patterns
    if generate_response:
        # Check for unnaturally fast response times (common in honeypots)
        eval_duration = generate_response.get("eval_duration", 0)
        eval_count = generate_response.get("eval_count", 0)
        
        # If we have a suspiciously high tokens/second rate, it might be a honeypot
        if eval_duration > 0 and eval_count > 0:
            tokens_per_second = eval_count / (eval_duration / 1000000000)
            # Real LLMs typically don't exceed certain token generation speeds
            # An absurdly high tokens/second might indicate a fake response
            if tokens_per_second > 1000:  # Most consumer GPUs can't do 1000+ tokens/sec
                return True, f"Suspiciously fast token generation: {tokens_per_second:.2f} tokens/sec"
    
    # 3. Check consistency of model metadata
    if models_data and "models" in models_data:
        models = models_data.get("models", [])
        
        # Check for unusual file sizes or duplicated file sizes
        if len(models) > 1:
            file_sizes = [model.get("size", 0) for model in models]
            unique_sizes = set(file_sizes)
            
            # If there are multiple models but they all have identical file sizes,
            # it's suspicious (real models have different sizes)
            if len(unique_sizes) == 1 and len(models) > 3:
                return True, "All models have identical file sizes (suspicious)"
    
    return False, ""

def make_request_with_retry(method, url, **kwargs):
    """
    Make an HTTP request with retry logic
    
    Args:
        method: HTTP method ('get' or 'post')
        url: URL to request
        **kwargs: Additional arguments for requests
        
    Returns:
        Response object or None on failure
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt} for {url}")
                time.sleep(RETRY_DELAY)
                
            if method.lower() == 'get':
                response = requests.get(url, **kwargs)
            elif method.lower() == 'post':
                response = requests.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            return response
            
        except requests.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt+1}/{MAX_RETRIES+1}): {str(e)}")
            if attempt == MAX_RETRIES:
                raise

def check_endpoint(server):
    """
    Check if an endpoint is responsive and returns valid responses
    
    Args:
        server: A tuple of (id, ip, port, scan_date)
        
    Returns:
        dict: Result with status information
    """
    server_id, ip, port, scan_date = server
    logger.info(f"Checking endpoint {ip}:{port}")
    
    # Initialize timing metrics
    start_time = datetime.now()
    
    result = {
        "server_id": server_id,
        "ip": ip,
        "port": port,
        "status": "failed", 
        "should_remove": True,  # Default to removing if we can't verify it's good
        "reason": "Unknown error",
        "is_honeypot": False,
        "verification_time": 0  # Will be updated at the end
    }
    
    try:
        # Clean IP and create base URL
        clean_ip = ip.strip(":")
        base_url = f"http://{clean_ip}:{port}"
        
        # 1. First check if the /api/tags endpoint is responding
        tags_start_time = datetime.now()
        models_data = None
        try:
            tags_url = f"{base_url}/api/tags"
            response = make_request_with_retry('get', tags_url, timeout=15)
            
            tags_time = (datetime.now() - tags_start_time).total_seconds()
            
            if response.status_code != 200:
                result["reason"] = f"Failed to get models: HTTP {response.status_code} (after {tags_time:.2f}s)"
                return result
                
            models_data = response.json()
            available_models = models_data.get("models", [])
            
            logger.info(f"Tags request succeeded in {tags_time:.2f}s - Found {len(available_models)} models")
            
            if not available_models:
                result["reason"] = "No models available"
                return result
                
        except requests.RequestException as e:
            tags_time = (datetime.now() - tags_start_time).total_seconds()
            result["reason"] = f"Connection error: {str(e)} (after {tags_time:.2f}s)"
            return result
        
        # 2. Find the smallest model to test with (to minimize timeouts)
        smallest_model = None
        smallest_size = float('inf')
        
        # First try to find the smallest model by file size
        for model in available_models:
            if 'size' in model and model['size'] > 0:
                if model['size'] < smallest_size:
                    smallest_size = model['size']
                    smallest_model = model.get('name')
        
        # If size-based selection failed, try naming patterns for small models
        if not smallest_model:
            for model in available_models:
                name = model.get('name', '').lower()
                if any(term in name for term in ['tiny', 'small', 'mini', '7b', '3b', '1b', '1.5b', '135m']):
                    smallest_model = model.get('name')
                    break
        
        # If all else fails, use the first model
        if not smallest_model and available_models:
            smallest_model = available_models[0].get('name')
        
        if not smallest_model:
            result["reason"] = "No valid model name found"
            return result
        
        logger.info(f"Selected model for testing: {smallest_model}")
        
        # Test with a simple prompt
        generate_start_time = datetime.now()
        generate_url = f"{base_url}/api/generate"
        prompt = "Hello, please respond with a simple sentence."
        
        payload = {
            "model": smallest_model,
            "prompt": prompt,
            "stream": False,
            "max_tokens": 50
        }
        
        try:
            # Increased timeout for the generate request
            generate_response = make_request_with_retry('post', generate_url, json=payload, timeout=30)
            
            generate_time = (datetime.now() - generate_start_time).total_seconds()
            
            if generate_response.status_code != 200:
                result["reason"] = f"Failed to generate response: HTTP {generate_response.status_code} (after {generate_time:.2f}s)"
                return result
            
            logger.info(f"Generate request succeeded in {generate_time:.2f}s")
            
            # Check if response is valid
            response_data = generate_response.json()
            response_text = response_data.get("response", "")
            
            is_valid = is_valid_response(response_text)
            
            if not is_valid:
                result["reason"] = f"Nonsensical response: {response_text[:50]}..."
                return result
            
            # Check if it's a honeypot - Fix: Use a try/except to catch any errors
            try:
                is_honeypot_result, honeypot_reason = is_honeypot(models_data, response_data)
                if is_honeypot_result:
                    result["status"] = "honeypot"
                    result["should_remove"] = True
                    result["reason"] = honeypot_reason
                    result["is_honeypot"] = True
                    logger.warning(f"Honeypot detected at {ip}:{port} - {honeypot_reason}")
                    return result
            except Exception as e:
                logger.warning(f"Error in honeypot detection for {ip}:{port}: {str(e)}")
                # Continue with the validation - don't mark as honeypot if detection fails
            
            # 3. Additional check: Test system_prompt parameter
            # Many fake implementations don't properly handle this parameter
            system_start_time = datetime.now()
            try:
                system_prompt_payload = {
                    "model": smallest_model,
                    "prompt": "What's the capital of France?",
                    "system": "You are a geography expert. Keep responses very short.",
                    "stream": False,
                    "max_tokens": 50
                }
                system_response = make_request_with_retry('post', generate_url, json=system_prompt_payload, timeout=25)
                
                system_time = (datetime.now() - system_start_time).total_seconds()
                logger.info(f"System prompt check completed in {system_time:.2f}s")
                
                if system_response.status_code == 200:
                    system_data = system_response.json()
                    system_text = system_data.get("response", "")
                    
                    # Fake implementations often ignore the system prompt, giving longer responses
                    # or responding in a way that doesn't match the requested behavior
                    words = system_text.split()
                    if len(words) > 25:  # If response is very long despite asking for short response
                        result["is_honeypot"] = True
                        result["should_remove"] = True
                        result["reason"] = "Likely honeypot: Doesn't respect system prompt parameter"
                        return result
            except Exception as e:
                # Fix: Log the exception but don't cause the check to fail
                logger.warning(f"Error in system prompt check for {ip}:{port}: {str(e)}")
                # If this additional check fails, we'll still trust our previous assessments
                pass
            
            # If we've made it here, the endpoint is good
            result["status"] = "success"
            result["should_remove"] = False
            result["reason"] = "Valid endpoint"
            
            # Calculate total verification time
            total_time = (datetime.now() - start_time).total_seconds()
            result["verification_time"] = total_time
            
            logger.info(f"✅ Endpoint {ip}:{port} is valid (verified in {total_time:.2f}s) with response: {response_text[:50]}...")
            return result
            
        except requests.RequestException as e:
            generate_time = (datetime.now() - generate_start_time).total_seconds()
            result["reason"] = f"Generate API error: {str(e)} (after {generate_time:.2f}s)"
            return result
            
    except Exception as e:
        # Calculate total time even for errors
        total_time = (datetime.now() - start_time).total_seconds()
        result["verification_time"] = total_time
        result["reason"] = f"Error checking endpoint: {str(e)} (after {total_time:.2f}s)"
        return result

def remove_server(server_id):
    """
    Mark a server as invalid in the database
    
    Args:
        server_id: The ID of the server/endpoint to mark as invalid
        
    Returns:
        bool: Success status
    """
    try:
        # Ensure database connection is properly initialized
        Database.ensure_pool_initialized()
        
        # For PostgreSQL schema, we need to:
        # 1. Mark the endpoint as invalid (verified=2) in the endpoints table
        # 2. Remove it from the verified_endpoints table if it exists
        
        # Update the endpoint status to invalid (2)
        Database.execute(
            "UPDATE endpoints SET verified = 2, verification_date = NOW() WHERE id = %s", 
            (server_id,)
        )
        
        # Remove from verified_endpoints if it exists
        Database.execute(
            "DELETE FROM verified_endpoints WHERE endpoint_id = %s", 
            (server_id,)
        )
        
        # Get the IP and port for logging
        endpoint_info = Database.fetch_one(
            "SELECT ip, port FROM endpoints WHERE id = %s",
            (server_id,)
        )
        
        if endpoint_info:
            ip, port = endpoint_info
            logger.info(f"Marked endpoint {ip}:{port} (ID: {server_id}) as invalid")
        else:
            logger.warning(f"Endpoint with ID {server_id} not found when trying to mark as invalid")
        
        return True
        
    except Exception as e:
        logger.error(f"Error marking server {server_id} as invalid: {str(e)}")
        return False

def mark_endpoint_as_verified(server_id):
    """
    Mark an endpoint as verified in the database
    
    Args:
        server_id: The ID of the server/endpoint to mark as verified
        
    Returns:
        bool: Success status
    """
    try:
        # Ensure database connection is properly initialized
        Database.ensure_pool_initialized()
        
        # For PostgreSQL schema:
        # 1. Mark the endpoint as verified (verified=1) in the endpoints table
        # 2. Add it to the verified_endpoints table if it doesn't exist
        
        # First update the endpoint status
        Database.execute(
            "UPDATE endpoints SET verified = 1, verification_date = NOW() WHERE id = %s", 
            (server_id,)
        )
        
        # Then add to verified_endpoints if not already there
        Database.execute("""
            INSERT INTO verified_endpoints (endpoint_id, verification_date) 
            VALUES (%s, NOW())
            ON CONFLICT (endpoint_id) DO UPDATE SET verification_date = NOW()
        """, (server_id,))
        
        # Get the IP and port for logging
        endpoint_info = Database.fetch_one(
            "SELECT ip, port FROM endpoints WHERE id = %s",
            (server_id,)
        )
        
        if endpoint_info:
            ip, port = endpoint_info
            logger.info(f"Marked endpoint {ip}:{port} (ID: {server_id}) as verified")
        else:
            logger.warning(f"Endpoint with ID {server_id} not found when trying to mark as verified")
        
        return True
        
    except Exception as e:
        logger.error(f"Error marking server {server_id} as verified: {str(e)}")
        return False

def main():
    
    # Initialize database schema
    init_database()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Prune bad Ollama endpoints from the database')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of endpoints to process in each batch')
    parser.add_argument('--threads', type=int, default=5, help='Number of concurrent threads for checking endpoints')
    parser.add_argument('--no-remove', action='store_true', help='Don\'t actually remove bad endpoints, just report them')
    parser.add_argument('--verify-only', action='store_true', help='Only verify and mark verified endpoints, don\'t remove bad ones')
    args = parser.parse_args()
    
    try:
        # Get all servers from the database
        logger.info("Starting pruner script")
        servers = get_all_servers()
        
        if not servers:
            logger.warning("No servers found in the database. Exiting.")
            return
            
        logger.info(f"Found {len(servers)} total endpoints to check")
        
        # Process in batches to avoid overwhelming the database
        batch_size = min(args.batch_size, len(servers))
        num_batches = (len(servers) + batch_size - 1) // batch_size
        logger.info(f"Processing in {num_batches} batches of up to {batch_size} endpoints each")
        
        # Track statistics
        stats = {
            "total": len(servers),
            "checked": 0,
            "removed": 0,
            "verified": 0,
            "honeypots": 0,
            "errors": 0
        }
        
        # Process each batch
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(servers))
            batch = servers[start_idx:end_idx]
            
            logger.info(f"Starting batch {batch_num+1}/{num_batches} with {len(batch)} endpoints")
            
            # Check endpoints in parallel
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                # Submit all tasks and store futures
                future_to_server = {executor.submit(check_endpoint, server): server for server in batch}
                
                # Define a callback for when each task completes
                def process_result(future):
                    try:
                        result = future.result()
                        if result:
                            server_id = result.get("server_id")
                            ip = result.get("ip")
                            port = result.get("port")
                            status = result.get("status")
                            should_remove = result.get("should_remove", False)
                            reason = result.get("reason", "Unknown")
                            is_honeypot = result.get("is_honeypot", False)
                            
                            with stats_lock:
                                stats["checked"] += 1
                                if is_honeypot:
                                    stats["honeypots"] += 1
                                
                                # Progress reporting
                                if stats["checked"] % 10 == 0:
                                    logger.info(f"[PROGRESS] Checked {stats['checked']}/{stats['total']} endpoints")
                                    logger.info(f"  - Removed: {stats['removed']}, Verified: {stats['verified']}, Honeypots: {stats['honeypots']}, Errors: {stats['errors']}")
                            
                            # Log the result
                            if status == "ok":
                                logger.info(f"Endpoint {ip}:{port} (ID: {server_id}) is valid")
                                
                                try:
                                    # Mark as verified in the database
                                    mark_endpoint_as_verified(server_id)
                                    with stats_lock:
                                        stats["verified"] += 1
                                except Exception as e:
                                    logger.error(f"Error marking server {server_id} as verified: {str(e)}")
                            else:
                                if is_honeypot:
                                    reason_str = f"HONEYPOT: {reason}"
                                else:
                                    reason_str = reason
                                    
                                logger.warning(f"Endpoint {ip}:{port} (ID: {server_id}) is bad: {reason_str}")
                                
                                # Remove if needed and not in verify-only mode
                                if should_remove and not args.verify_only and not args.no_remove:
                                    try:
                                        remove_server(server_id)
                                        with stats_lock:
                                            stats["removed"] += 1
                                        logger.info(f"Removed endpoint {ip}:{port} (ID: {server_id})")
                                    except Exception as e:
                                        logger.error(f"Error removing server {server_id}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing result: {str(e)}")
                        with stats_lock:
                            stats["errors"] += 1
                
                # Use a lock for thread-safe stats updates
                stats_lock = threading.Lock()
                
                # Process results as they complete
                for future in future_to_server:
                    future.add_done_callback(process_result)
                
                # Wait for all futures to complete
                for future in future_to_server:
                    try:
                        future.result()
                    except Exception as e:
                        server = future_to_server[future]
                        logger.error(f"Unhandled error checking server {server[0]} ({server[1]}:{server[2]}): {str(e)}")
                        with stats_lock:
                            stats["errors"] += 1
            
            # Sleep briefly between batches to allow database resources to be released
            if batch_num < num_batches - 1:
                logger.info(f"Completed batch {batch_num+1}/{num_batches}, waiting 2 seconds before next batch")
                time.sleep(2)
        
        # Print final statistics
        logger.info("=" * 50)
        logger.info("PRUNING COMPLETE")
        logger.info("=" * 50)
        logger.info(f"Total endpoints: {stats['total']}")
        logger.info(f"Endpoints checked: {stats['checked']}")
        logger.info(f"Valid endpoints: {stats['verified']}")
        logger.info(f"Endpoints removed: {stats['removed']}")
        logger.info(f"Honeypots identified: {stats['honeypots']}")
        logger.info(f"Errors encountered: {stats['errors']}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Error in pruner script: {str(e)}")
    finally:
        # Ensure database connections are closed properly
        try:
            Database.close()
            logger.info("Database connections closed properly")
        except Exception as e:
            logger.error(f"Error closing database connections: {str(e)}")

if __name__ == "__main__":
    main() 