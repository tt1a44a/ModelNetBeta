#!/usr/bin/env python3
"""
Update Ollama Models

This script connects to all Ollama instances in the database and updates
the list of available models for each instance.

Usage:
  python update_ollama_models.py                    # Update all servers
  python update_ollama_models.py --debug IP:PORT    # Debug a specific endpoint
"""

import sqlite3
import os
import sys
import time
import json
import requests
import argparse
import re
from concurrent.futures import ThreadPoolExecutor
import logging
from datetime import datetime

# Import the sync_models_with_server function from ollama_models.py
from ollama_models import DB_FILE

# Added by migration script
from database import Database, init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update_models.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_all_servers():
    """
    Get all servers from the database
    """
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

def get_server_models(server_id):
    """
    Get all models for a specific server from the database
    
    Args:
        server_id: The ID of the server
        
    Returns:
        list: List of model dictionaries
    """
    conn = Database()
    conn.row_factory = sqlite3.Row
    cursor = # Using Database methods instead of cursor
    
    cursor.execute('''
        SELECT id, name, parameter_size, quantization_level, size_mb
        FROM models
        WHERE server_id = ?
    ''', (server_id,))
    
    models = [dict(row) for row in Database.fetch_all(query, params)]
    conn.close()
    
    return models

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

def check_endpoint_validity(ip, port):
    """
    Check if an endpoint gives valid responses before updating models
    
    Args:
        ip: The IP address of the server
        port: The port number
        
    Returns:
        bool: True if the endpoint returns valid responses, False otherwise
    """
    try:
        # Clean IP and create base URL
        clean_ip = ip.strip(":")
        base_url = f"http://{clean_ip}:{port}"
        
        # First get available models
        tags_url = f"{base_url}/api/tags"
        response = requests.get(tags_url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to get models from {ip}:{port}: {response.status_code}")
            return False
            
        models_data = response.json()
        available_models = models_data.get("models", [])
        
        if not available_models:
            logger.error(f"No models found on {ip}:{port}")
            return False
            
        # Test first model with a simple prompt
        model_name = available_models[0].get("name", "")
        if not model_name:
            logger.error(f"No valid model name found on {ip}:{port}")
            return False
            
        # Test with a simple prompt
        generate_url = f"{base_url}/api/generate"
        prompt = "Hello, please respond with a simple test message."
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "max_tokens": 50  # Limit token count for faster test
        }
        
        generate_response = requests.post(generate_url, json=payload, timeout=20)
        
        if generate_response.status_code != 200:
            logger.error(f"Failed to generate response from {ip}:{port}: {generate_response.status_code}")
            return False
        
        # Check if response is valid
        response_data = generate_response.json()
        response_text = response_data.get("response", "")
        
        is_valid = is_valid_response(response_text)
        
        if not is_valid:
            logger.warning(f"Endpoint {ip}:{port} returns nonsensical responses: {response_text[:100]}")
        else:
            logger.info(f"Endpoint {ip}:{port} returns valid responses")
            
        return is_valid
        
    except Exception as e:
        logger.error(f"Error checking endpoint validity for {ip}:{port}: {str(e)}")
        return False

def fetch_models_from_api(ip, port):
    """
    Fetch models from the Ollama API
    
    Args:
        ip: The IP address of the server
        port: The port number
        
    Returns:
        list: List of model dictionaries from the API
    """
    try:
        # Ensure IP and port format is correct by removing any extra colons
        clean_ip = ip.strip(":")
        url = f"http://{clean_ip}:{port}/api/tags"
        
        logger.info(f"Fetching models from {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            api_response = response.json()
            logger.info(f"API Response: {json.dumps(api_response, indent=2)}")
            return api_response.get("models", [])
        else:
            logger.error(f"Failed to get models: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Exception fetching models: {str(e)}")
        return []

def debug_endpoint(ip, port, model_name=None):
    """
    Debug an Ollama endpoint by testing models and showing raw responses
    
    Args:
        ip: The IP address of the server
        port: The port number
        model_name: Optional specific model to test
    """
    clean_ip = ip.strip(":")
    
    # First, get available models
    try:
        url = f"http://{clean_ip}:{port}/api/tags"
        logger.info(f"Fetching models from {url}")
        
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to get models: {response.status_code} - {response.text}")
            return
        
        models_data = response.json()
        available_models = models_data.get("models", [])
        
        if not available_models:
            logger.error(f"No models found on {ip}:{port}")
            return
        
        logger.info(f"Found {len(available_models)} models on {ip}:{port}")
        
        # If no specific model requested, use the first one from the list
        if not model_name:
            model_name = available_models[0].get("name")
            logger.info(f"Using first available model: {model_name}")
        
        # Test the API with a simple prompt
        logger.info(f"Testing model {model_name} on {ip}:{port}")
        
        generate_url = f"http://{clean_ip}:{port}/api/generate"
        prompt = "Hello, can you please respond with a simple test message?"
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }
        
        logger.info(f"Sending request: {json.dumps(payload)}")
        
        generate_response = requests.post(generate_url, json=payload, timeout=30)
        
        logger.info(f"Response status: {generate_response.status_code}")
        logger.info(f"Response headers: {generate_response.headers}")
        
        # Try to parse as JSON
        try:
            json_response = generate_response.json()
            logger.info(f"JSON Response: {json.dumps(json_response, indent=2)}")
            
            # Check if response is valid
            response_text = json_response.get("response", "")
            is_valid = is_valid_response(response_text)
            logger.info(f"Response validity check: {is_valid}")
            
        except json.JSONDecodeError:
            # Not JSON, log as text
            logger.info(f"Text Response: {generate_response.text}")
        
        # Check if we got a streaming response despite requesting non-streaming
        if 'transfer-encoding' in generate_response.headers and generate_response.headers['transfer-encoding'] == 'chunked':
            logger.warning("Received a streaming response despite requesting non-streaming")
        
        # Try a streaming request to compare
        logger.info("Testing with streaming enabled...")
        
        payload["stream"] = True
        
        with requests.post(generate_url, json=payload, timeout=30, stream=True) as stream_response:
            logger.info(f"Streaming response status: {stream_response.status_code}")
            
            for chunk in stream_response.iter_lines():
                if chunk:
                    logger.info(f"Chunk: {chunk.decode('utf-8')}")
    
    except Exception as e:
        logger.error(f"Error debugging endpoint {ip}:{port}: {str(e)}")

def update_models_in_db(server_id, ip, port, api_models):
    """
    Update models in the database based on API response
    
    Args:
        server_id: The ID of the server
        ip: The IP address
        port: The port number
        api_models: Models from the API
        
    Returns:
        tuple: Lists of (added, updated, deleted) model names
    """
    # Lists to track changes
    added_models = []
    updated_models = []
    deleted_models = []
    
    try:
        # Get existing models from database
        db_models = get_server_models(server_id)
        logger.info(f"Current DB models for {ip}:{port}: {json.dumps(db_models, indent=2)}")
        
        # Create dictionary of existing models for easier lookup
        db_models_dict = {model["name"]: model for model in db_models}
        
        # Connect to database for updates
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Process models from API
        for model in api_models:
            name = model.get("name", "")
            if not name:
                continue  # Skip models without a name
            
            # Extract model details
            model_size_mb = model.get("size", 0) / (1024 * 1024)  # Convert to MB
            
            parameter_size = ""
            quantization_level = ""
            
            # Get detailed info if available
            if "details" in model:
                parameter_size = model["details"].get("parameter_size", "")
                quantization_level = model["details"].get("quantization_level", "")
            
            logger.info(f"API Model: {name}, Size: {model_size_mb} MB, Params: {parameter_size}, Quant: {quantization_level}")
            
            # Check if model exists in database
            if name in db_models_dict:
                # Get existing model
                existing = db_models_dict[name]
                logger.info(f"Existing model: {name}, Size: {existing['size_mb']} MB, Params: {existing['parameter_size']}, Quant: {existing['quantization_level']}")
                
                # Update model if details have changed
                if (existing["parameter_size"] != parameter_size or 
                    existing["quantization_level"] != quantization_level or 
                    abs(existing["size_mb"] - model_size_mb) > 0.1):  # Allow small size differences
                    
                    logger.info(f"Updating model {name} - API: {parameter_size}/{quantization_level}/{model_size_mb} DB: {existing['parameter_size']}/{existing['quantization_level']}/{existing['size_mb']}")
                    
                    cursor.execute("""
                        UPDATE models SET 
                        parameter_size = ?, 
                        quantization_level = ?, 
                        size_mb = ? 
                        WHERE id = ?
                    """, (parameter_size, quantization_level, model_size_mb, existing["id"]))
                    updated_models.append(name)
                else:
                    logger.info(f"No changes for model {name}")
                
                # Remove from db_models_dict to track which are no longer on server
                del db_models_dict[name]
            else:
                # Add new model
                logger.info(f"Adding new model: {name}, Size: {model_size_mb} MB, Params: {parameter_size}, Quant: {quantization_level}")
                try:
                    cursor.execute("""
                        INSERT INTO models (server_id, name, parameter_size, quantization_level, size_mb)
                        VALUES (?, ?, ?, ?, ?)
                    """, (server_id, name, parameter_size, quantization_level, model_size_mb))
                    added_models.append(name)
                except sqlite3.IntegrityError:
                    # Handle potential race condition if the model was added in parallel
                    logger.warning(f"Model {name} already exists in the database. Skipping.")
        
        # Delete models that are no longer on the server
        for name, model_info in db_models_dict.items():
            logger.info(f"Removing model no longer on server: {name}")
            Database.execute("DELETE FROM models WHERE id = ?", (model_info["id"],))
            deleted_models.append(name)
        
        # Update server scan date
        Database.execute("UPDATE servers SET scan_date = datetime('now') WHERE id = ?", (server_id,))
        
        # Commit handled by Database methods
        conn.close()
        
    except Exception as e:
        logger.error(f"Error updating models in database: {str(e)}")
        raise
    
    return (added_models, updated_models, deleted_models)

def update_server_models(server):
    """
    Update models for a single server
    
    Args:
        server: A tuple of (id, ip, port, scan_date)
        
    Returns:
        dict: Results of the update operation
    """
    server_id, ip, port, scan_date = server
    logger.info(f"===== Updating models for server {ip}:{port} =====")
    
    try:
        # First check if endpoint gives valid responses
        if not check_endpoint_validity(ip, port):
            logger.warning(f"Skipping endpoint {ip}:{port} due to invalid responses")
            return {
                "server_id": server_id,
                "ip": ip,
                "port": port,
                "success": False,
                "added": [],
                "updated": [],
                "deleted": [],
                "error": "Endpoint returns nonsensical responses"
            }
        
        # Fetch models from API
        api_models = fetch_models_from_api(ip, port)
        
        if not api_models:
            logger.warning(f"No models found for server {ip}:{port}")
            return {
                "server_id": server_id,
                "ip": ip,
                "port": port,
                "success": False,
                "added": [],
                "updated": [],
                "deleted": [],
                "error": "No models found from API"
            }
        
        logger.info(f"Found {len(api_models)} models on server {ip}:{port}")
        
        # Update models in database
        added, updated, deleted = update_models_in_db(server_id, ip, port, api_models)
        
        result = {
            "server_id": server_id,
            "ip": ip,
            "port": port,
            "success": True,
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "error": None
        }
        
        logger.info(f"Server {ip}:{port} - Added: {len(added)}, Updated: {len(updated)}, Deleted: {len(deleted)}")
        return result
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error updating models for {ip}:{port}: {error_msg}")
        
        return {
            "server_id": server_id,
            "ip": ip,
            "port": port,
            "success": False,
            "added": [],
            "updated": [],
            "deleted": [],
            "error": error_msg
        }

def main():
    
    # Initialize database schema
    init_database()# Set up argument parser
    parser = argparse.ArgumentParser(description='Update Ollama models from remote instances')
    parser.add_argument('--debug', metavar='IP:PORT', help='Debug a specific endpoint')
    parser.add_argument('--model', help='Specific model to test (for debug mode)')
    parser.add_argument('--skip-validity-check', action='store_true', help='Skip endpoint validity checks')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of servers to update')
    args = parser.parse_args()
    
    # If debug mode is requested
    if args.debug:
        try:
            # Parse IP:PORT format
            parts = args.debug.split(':')
            if len(parts) != 2:
                logger.error("Invalid format. Use --debug IP:PORT")
                return
                
            ip = parts[0]
            port = int(parts[1])
            logger.info(f"Debug mode: Testing endpoint {ip}:{port}")
            
            debug_endpoint(ip, port, args.model)
            return
        except Exception as e:
            logger.error(f"Error in debug mode: {str(e)}")
            return
    
    # Normal update mode
    start_time = datetime.now()
    logger.info(f"Starting model update at {start_time}")
    
    # Get all servers from the database
    servers = get_all_servers()
    logger.info(f"Found {len(servers)} servers in the database")
    
    if not servers:
        logger.warning("No servers found in the database.")
        return
    
    # Apply limit if specified
    if args.limit is not None:
        servers = servers[:args.limit]
        logger.info(f"Limited to first {args.limit} servers")
    
    # Track results
    results = {
        "total_servers": len(servers),
        "successful": 0,
        "failed": 0,
        "skipped_invalid": 0,
        "total_added": 0,
        "total_updated": 0,
        "total_deleted": 0,
        "servers": []
    }
    
    # Use ThreadPoolExecutor to update servers in parallel
    # Reduced worker count for more detailed logging
    with ThreadPoolExecutor(max_workers=5) as executor:
        server_results = list(executor.map(update_server_models, servers))
    
    # Process results
    for result in server_results:
        results["servers"].append(result)
        
        if result["success"]:
            results["successful"] += 1
            results["total_added"] += len(result["added"])
            results["total_updated"] += len(result["updated"])
            results["total_deleted"] += len(result["deleted"])
        else:
            results["failed"] += 1
            if result.get("error") == "Endpoint returns nonsensical responses":
                results["skipped_invalid"] += 1
    
    # Print summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"Model update completed in {duration:.2f} seconds")
    logger.info(f"Summary: {results['successful']} successful, {results['failed']} failed")
    logger.info(f"Skipped due to invalid responses: {results['skipped_invalid']}")
    logger.info(f"Models: {results['total_added']} added, {results['total_updated']} updated, {results['total_deleted']} deleted")
    
    return results

if __name__ == "__main__":
    main() 