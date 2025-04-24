#!/usr/bin/env python3
"""
Migrate Valid Ollama Endpoints

This script tests endpoints in the database and copies only valid ones to a new database,
preserving all metadata (parameters, quantization levels, etc.). This allows for safe pruning
while maintaining access to valid endpoints.
"""

import sqlite3
import requests
import json
import argparse
import logging
import sys
import re
import time
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from tqdm import tqdm

# Added by migration script
from database import Database, init_database

# Default database paths
# TODO: Replace SQLite-specific code: DEFAULT_DB_FILE = "ollama.db"
try:
    # Try to import from ollama_models.py if it exists
    from ollama_models import DB_FILE
except ImportError:
    # If import fails, use the default
    DB_FILE = DEFAULT_DB_FILE
    logging.warning(f"Could not import DB_FILE from ollama_models, using default: {DEFAULT_DB_FILE}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migrate_endpoints.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Maximum number of retries for API requests
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds between retries

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

def is_valid_response(text):
    """
    Check if a response is valid (not nonsensical)
    
    Args:
        text: The response text to check
        
    Returns:
        bool: True if the response seems valid, False otherwise
    """
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

def check_endpoint(server):
    """
    Check if an endpoint is responsive and returns valid responses
    
    Args:
        server: A tuple of (id, ip, port, scan_date)
        
    Returns:
        dict: Result with status information
    """
    server_id, ip, port, scan_date = server
    
    result = {
        "server_id": server_id,
        "ip": ip,
        "port": port,
        "scan_date": scan_date,
        "status": "failed", 
        "valid": False,
        "reason": "Unknown error",
        "is_honeypot": False
    }
    
    try:
        # Clean IP and create base URL
        clean_ip = ip.strip(":")
        base_url = f"http://{clean_ip}:{port}"
        
        # 1. First check if the /api/tags endpoint is responding
        models_data = None
        try:
            tags_url = f"{base_url}/api/tags"
            response = make_request_with_retry('get', tags_url, timeout=15)
            
            if response.status_code != 200:
                result["reason"] = f"Failed to get models: HTTP {response.status_code}"
                return result
                
            models_data = response.json()
            available_models = models_data.get("models", [])
            
            if not available_models:
                result["reason"] = "No models available"
                return result
                
        except requests.RequestException as e:
            result["reason"] = f"Connection error: {str(e)}"
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
        
        # Test with a simple prompt
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
            
            if generate_response.status_code != 200:
                result["reason"] = f"Failed to generate response: HTTP {generate_response.status_code}"
                return result
            
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
                    result["valid"] = False
                    result["reason"] = honeypot_reason
                    result["is_honeypot"] = True
                    return result
            except Exception as e:
                logger.warning(f"Error in honeypot detection for {ip}:{port}: {str(e)}")
                # Continue with the validation - don't mark as honeypot if detection fails
            
            # 3. Additional check: Test system_prompt parameter
            # Many fake implementations don't properly handle this parameter
            try:
                system_prompt_payload = {
                    "model": smallest_model,
                    "prompt": "What's the capital of France?",
                    "system": "You are a geography expert. Keep responses very short.",
                    "stream": False,
                    "max_tokens": 50
                }
                system_response = make_request_with_retry('post', generate_url, json=system_prompt_payload, timeout=25)
                
                if system_response.status_code == 200:
                    system_data = system_response.json()
                    system_text = system_data.get("response", "")
                    
                    # Fake implementations often ignore the system prompt, giving longer responses
                    # or responding in a way that doesn't match the requested behavior
                    words = system_text.split()
                    if len(words) > 25:  # If response is very long despite asking for short response
                        result["is_honeypot"] = True
                        result["valid"] = False
                        result["reason"] = "Likely honeypot: Doesn't respect system prompt parameter"
                        return result
            except Exception as e:
                # Fix: Log the exception but don't cause the check to fail
                logger.warning(f"Error in system prompt check for {ip}:{port}: {str(e)}")
                # If this additional check fails, we'll still trust our previous assessments
                pass
            
            # If we've made it here, the endpoint is good
            result["status"] = "success"
            result["valid"] = True
            result["reason"] = "Valid endpoint"
            
            return result
            
        except requests.RequestException as e:
            result["reason"] = f"Generate API error: {str(e)}"
            return result
            
    except Exception as e:
        result["reason"] = f"Error checking endpoint: {str(e)}"
        return result

def get_all_servers(db_file):
    """
    Get all servers from the database
    
    Args:
        db_file: Path to the SQLite database
        
    Returns:
        list: List of server tuples
    """
    try:
        conn = Database()
        cursor = # Using Database methods instead of cursor
        cursor.execute('''
            SELECT id, ip, port, scan_date
            FROM servers
            ORDER BY scan_date DESC
        ''')
        servers = Database.fetch_all(query, params)
        conn.close()
        return servers
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        print(f"Error: Could not access database {db_file}. Make sure the path is correct.")
        sys.exit(1)

def create_new_db(source_db, target_db):
    """
    Create a new database with the same schema as the source database
    
    Args:
        source_db: Path to the source database
        target_db: Path to the target database
        
    Returns:
        bool: Success status
    """
    # First make a backup of target_db if it exists
    if os.path.exists(target_db):
        backup_path = f"{target_db}.bak.{int(time.time())}"
        shutil.copy2(target_db, backup_path)
        logger.info(f"Created backup of existing target database at {backup_path}")
    
    try:
        # Connect to the source database
        source_conn = Database()
        source_cursor = source_# Using Database methods instead of cursor
        
        # Get the schema from the source database
        source_Database.execute("SELECT sql FROM sqlite_master WHERE type='table'")
        table_schemas = source_Database.fetch_all(query, params)
        
        # Create a new database
        if os.path.exists(target_db):
            os.remove(target_db)
            
        target_conn = Database()
        target_cursor = target_# Using Database methods instead of cursor
        
        # Create the tables in the new database
        for schema in table_schemas:
            if schema[0] and "sqlite_" not in schema[0]:
                target_Database.execute(schema[0])
        
        # Commit changes and close connections
        target_# Commit handled by Database methods
        target_conn.close()
        source_conn.close()
        
        logger.info(f"Created new database {target_db} with schema from {source_db}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating new database: {str(e)}")
        return False

def copy_server_and_models(source_db, target_db, server_id):
    """
    Copy a server and its models from the source database to the target database
    
    Args:
        source_db: Path to the source database
        target_db: Path to the target database
        server_id: ID of the server to copy
        
    Returns:
        bool: Success status
    """
    try:
        # Connect to the source database
        source_conn = Database()
        source_cursor = source_# Using Database methods instead of cursor
        
        # Connect to the target database
        target_conn = Database()
        target_cursor = target_# Using Database methods instead of cursor
        
        # Get the server from the source database
        source_cursor.execute('''
            SELECT id, ip, port, scan_date
            FROM servers
            WHERE id = ?
        ''', (server_id,))
        server = source_Database.fetch_one(query, params)
        
        if not server:
            logger.warning(f"Server {server_id} not found in source database")
            source_conn.close()
            target_conn.close()
            return False
        
        # Insert the server into the target database
        target_cursor.execute('''
            INSERT OR REPLACE INTO servers (id, ip, port, scan_date)
            VALUES (?, ?, ?, ?)
        ''', server)
        
        # Get all models for the server from the source database
        source_cursor.execute('''
            SELECT id, server_id, name, parameter_size, quantization_level, size_mb
            FROM models
            WHERE server_id = ?
        ''', (server_id,))
        models = source_Database.fetch_all(query, params)
        
        # Insert the models into the target database
        for model in models:
            target_cursor.execute('''
                INSERT OR REPLACE INTO models (id, server_id, name, parameter_size, quantization_level, size_mb)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', model)
        
        # Commit changes and close connections
        target_# Commit handled by Database methods
        target_conn.close()
        source_conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Error copying server {server_id}: {str(e)}")
        return False

def migrate_endpoints(source_db, target_db, results):
    """
    Migrate valid endpoints from source database to target database
    
    Args:
        source_db: Path to the source database
        target_db: Path to the target database
        results: List of check results
        
    Returns:
        int: Number of migrated endpoints
    """
    # Create a new database with the same schema as the source database
    if not create_new_db(source_db, target_db):
        logger.error(f"Failed to create new database {target_db}")
        return 0
    
    # Filter valid endpoints
    valid_endpoints = [r for r in results if r["valid"]]
    
    # Copy each valid endpoint and its models to the target database
    migrated_count = 0
    
    # Add a progress bar for migration
    print("\nMigrating valid endpoints to new database...")
    for endpoint in tqdm(valid_endpoints, desc="Migrating endpoints", unit="endpoint"):
        if copy_server_and_models(source_db, target_db, endpoint["server_id"]):
            migrated_count += 1
    
    return migrated_count

def process_server(server):
    """Process a single server for ThreadPoolExecutor with progress reporting"""
    result = check_endpoint(server)
    return result

def main():
    
    # Initialize database schema
    init_database()# Parse command line arguments
    parser = argparse.ArgumentParser(description='Migrate valid Ollama endpoints to a new database')
    parser.add_argument('--source-db', default=DB_FILE, help='Source database file')
    # TODO: Replace SQLite-specific code: parser.add_argument('--target-db', default="valid-endpoints.db", help='Target database file')
    parser.add_argument('--limit', type=int, default=None, help='Limit the number of servers to check')
    parser.add_argument('--workers', type=int, default=10, help='Number of concurrent workers')
    parser.add_argument('--replace', action='store_true', help='Replace the source database with the target database after migration')
    parser.add_argument('--min-endpoints', type=int, default=50, help='Minimum number of valid endpoints required for replacing the source database')
    args = parser.parse_args()
    
    # Start time for tracking duration
    start_time = datetime.now()
    logger.info(f"Starting migration process at {start_time}")
    print(f"Starting migration process at {start_time}")
    
    # Get all servers from the source database
    try:
        servers = get_all_servers(args.source_db)
    except Exception as e:
        print(f"Failed to access database {args.source_db}: {str(e)}")
        return
    
    if not servers:
        logger.warning(f"No servers found in the source database {args.source_db}")
        print(f"No servers found in the source database {args.source_db}")
        return
    
    logger.info(f"Found {len(servers)} servers in the source database")
    print(f"Found {len(servers)} servers in the source database")
    
    # Apply limit if specified
    if args.limit:
        servers = servers[:args.limit]
        logger.info(f"Limited to checking first {args.limit} servers")
        print(f"Limited to checking first {args.limit} servers")
    
    # Check endpoints in parallel with progress bar
    results = []
    print("\nChecking endpoints...\n")
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Create a progress bar that will update as tasks complete
        futures = {executor.submit(process_server, server): server for server in servers}
        
        for future in tqdm(
            concurrent.futures.as_completed(futures), 
            total=len(servers),
            desc="Testing endpoints",
            unit="endpoint"
        ):
            result = future.result()
            results.append(result)
            # Update the progress bar description with current success rate
            valid_so_far = len([r for r in results if r["valid"]])
            tqdm.write(f"Valid: {valid_so_far}/{len(results)} ({valid_so_far/len(results)*100:.1f}%)")
    
    # Count valid and invalid endpoints
    valid_endpoints = [r for r in results if r["valid"]]
    honeypot_count = len([r for r in results if r.get("is_honeypot", False)])
    
    logger.info(f"Found {len(valid_endpoints)} valid endpoints out of {len(results)} checked")
    print(f"\nFound {len(valid_endpoints)} valid endpoints out of {len(results)} checked ({len(valid_endpoints)/len(results)*100:.1f}%)")
    logger.info(f"Found {honeypot_count} honeypots")
    print(f"Found {honeypot_count} honeypots")
    
    # Migrate valid endpoints to the target database
    migrated_count = migrate_endpoints(args.source_db, args.target_db, results)
    logger.info(f"Migrated {migrated_count} valid endpoints to {args.target_db}")
    print(f"Migrated {migrated_count} valid endpoints to {args.target_db}")
    
    # Replace the source database with the target database if requested
    if args.replace:
        if migrated_count < args.min_endpoints:
            logger.warning(f"Not replacing source database: only {migrated_count} valid endpoints found, minimum required is {args.min_endpoints}")
            print(f"\nWARNING: Not replacing source database - only {migrated_count} valid endpoints found")
            print(f"Minimum required is {args.min_endpoints}. Use --min-endpoints to change this threshold.")
        else:
            try:
                # Create a backup of the source database
                backup_path = f"{args.source_db}.bak.{int(time.time())}"
                shutil.copy2(args.source_db, backup_path)
                logger.info(f"Created backup of source database at {backup_path}")
                print(f"Created backup of source database at {backup_path}")
                
                # Replace the source database with the target database
                shutil.copy2(args.target_db, args.source_db)
                logger.info(f"Replaced source database {args.source_db} with target database {args.target_db}")
                print(f"Replaced source database {args.source_db} with target database {args.target_db}")
            except Exception as e:
                logger.error(f"Error replacing source database: {str(e)}")
                print(f"Error replacing source database: {str(e)}")
    
    # Output summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"Migration completed in {duration:.2f} seconds")
    print(f"\nMigration completed in {duration:.2f} seconds")
    logger.info(f"Source database: {args.source_db}")
    logger.info(f"Target database: {args.target_db}")
    logger.info(f"Valid endpoints: {len(valid_endpoints)} out of {len(results)} checked")
    
    # Save results to JSON file
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "total_checked": len(results),
        "valid_endpoints": len(valid_endpoints),
        "honeypots_detected": honeypot_count,
        "migrated_count": migrated_count,
        "source_db": args.source_db,
        "target_db": args.target_db,
        "duration_seconds": duration,
        "endpoints": [
            {
                "server_id": r["server_id"],
                "ip": r["ip"],
                "port": r["port"],
                "valid": r["valid"],
                "reason": r["reason"],
                "is_honeypot": r.get("is_honeypot", False)
            }
            for r in results
        ]
    }
    
    with open('migration_results.json', 'w') as f:
        json.dump(output_data, f, indent=2)
        
    logger.info(f"Results saved to migration_results.json")
    
    # Print a final summary message
    print(f"Source database: {args.source_db}")
    print(f"Target database: {args.target_db}")
    print(f"Valid endpoints: {len(valid_endpoints)} out of {len(results)} checked ({len(valid_endpoints)/len(results)*100:.1f}%)")
    if args.replace and migrated_count >= args.min_endpoints:
        print(f"Successfully replaced source database with clean database")
    print(f"Detailed results saved to migration_results.json")

if __name__ == "__main__":
    import concurrent.futures
    main() 