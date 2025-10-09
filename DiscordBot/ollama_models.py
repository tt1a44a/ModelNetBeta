#!/usr/bin/env python3
"""
Database handling for Ollama models.
Ollama Models Database Management.
"""

import sqlite3
import json
import os
import requests
import time
from datetime import datetime

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

# Define database file location (used only for SQLite)
DB_FILE = "ollama_instances.db"

def setup_database():
    """
    Set up the database tables if they don't exist
    """
    conn = Database()
    
    # Create servers table
    Database.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            port INTEGER,
            scan_date TEXT,
            UNIQUE(ip, port)
        )
    ''')
    
    # Create models table
    Database.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint_id INTEGER,
            name TEXT,
            parameter_size TEXT,
            quantization_level TEXT,
            size_mb REAL,
            FOREIGN KEY (endpoint_id) REFERENCES servers (id),
            UNIQUE(endpoint_id, name)
        )
    ''')
    
    # Commit handled by Database methods
    conn.close()

def get_models():
    """
    Get all models from the database
    """
    conn = Database()
    
    query = '''
        SELECT m.id, s.ip, s.port, m.name, m.parameter_size, m.quantization_level, m.size_mb
        FROM models m
        JOIN endpoints s ON m.endpoint_id = s.id
    '''
    models = Database.fetch_all(query)
    conn.close()
    return models

def get_model_by_id(model_id):
    """
    Get a specific model by ID
    """
    conn = Database()
    
    query = '''
        SELECT m.id, s.ip, s.port, m.name, m.parameter_size, m.quantization_level, m.size_mb
        FROM models m
        JOIN endpoints s ON m.endpoint_id = s.id
        WHERE m.id = ?
    '''
    model = Database.fetch_one(query, (model_id,))
    conn.close()
    return model

def check_model_exists(model_id):
    """
    Check if a model with the given ID exists in the database
    Returns True if the model exists, False otherwise
    """
    conn = Database()
    
    query = "SELECT COUNT(*) FROM models WHERE id = ?"
    count = Database.fetch_one(query, (model_id,))[0]
    conn.close()
    return count > 0

def add_model(ip, port, name, info="{}"):
    """
    Add a new model to the database
    """
    # Parse the info to get parameter_size, quantization_level, and size_mb
    if isinstance(info, str):
        try:
            info_dict = json.loads(info)
        except:
            info_dict = {}
    else:
        info_dict = info
    
    parameter_size = info_dict.get('parameter_size', '')
    quantization_level = info_dict.get('quantization_level', '')
    size_mb = info_dict.get('size_mb', 0.0)
    
    conn = Database()
    
    # First check if the server exists
    query = "SELECT id FROM servers WHERE ip = ? AND port = ?"
    server = Database.fetch_one(query, (ip, port))
    
    if server:
        server_id = server[0]
    else:
        # Add the server if it doesn't exist
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = Database.execute("INSERT INTO servers (ip, port, scan_date) VALUES (?, ?, ?)", 
                          (ip, port, now))
        
        # Get the server ID based on database type
        if DATABASE_TYPE == "postgres":
            # For PostgreSQL, we need to query the ID after insertion
            server_row = Database.fetch_one("SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
            server_id = server_row[0] if server_row else None
        else:
            # For SQLite, we can use lastrowid
            server_id = result.lastrowid
    
    # Then add the model
    query = """
        INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
        VALUES (?, ?, ?, ?, ?)
    """
    result = Database.execute(query, (server_id, name, parameter_size, quantization_level, size_mb))
    
    # Get the model ID based on database type
    if DATABASE_TYPE == "postgres":
        # For PostgreSQL, we need to query the ID after insertion
        model_row = Database.fetch_one("SELECT id FROM models WHERE endpoint_id = ? AND name = ?", (server_id, name))
        model_id = model_row[0] if model_row else None
    else:
        # For SQLite, we can use lastrowid
        model_id = result.lastrowid
    
    # Commit handled by Database methods
    conn.close()
    return model_id

def delete_model(model_id):
    """
    Delete a model from the database
    """
    conn = Database()
    
    # Get the server_id for this model
    query = "SELECT endpoint_id FROM models WHERE id = ?"
    result = Database.fetch_one(query, (model_id,))
    
    if result:
        server_id = result[0]
        
        # Delete the model
        Database.execute("DELETE FROM models WHERE id = ?", (model_id,))
        
        # Check if there are any other models for this server
        query = "SELECT COUNT(*) FROM models WHERE endpoint_id = ?"
        count = Database.fetch_one(query, (server_id,))[0]
        
        # If no other models, delete the server too
        if count == 0:
            Database.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    
    # Commit handled by Database methods
    conn.close()

def sync_models_with_server(ip, port):
    """
    Synchronize the database with the models actually available on the Ollama server
    
    Returns:
        tuple: (added_models, updated_models, deleted_models) lists of model names
    """
    # Lists to track changes
    added_models = []
    updated_models = []
    deleted_models = []
    conn = None
    
    try:
        # Get models from the server with retries
        for retry in range(3):  # Try up to 3 times
            try:
                # Ensure IP and port format is correct by removing any extra colons
                clean_ip = ip.strip(":")
                url = f"http://{clean_ip}:{port}/api/tags"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    server_models = response.json().get("models", [])
                    break
                elif retry < 2:  # Don't sleep after the last attempt
                    time.sleep(2 ** retry)  # Exponential backoff: 1, 2, 4 seconds
                else:
                    raise Exception(f"Failed to get models from server: {response.status_code} - {response.text}")
            except requests.RequestException as e:
                if retry < 2:  # Don't sleep after the last attempt
                    time.sleep(2 ** retry)  # Exponential backoff
                else:
                    raise Exception(f"Connection error: {str(e)}")
        else:
            # This runs if the for loop completes without a break
            raise Exception("Failed to connect to server after multiple retries")
        
        # Get server_id or create if it doesn't exist
        conn = Database()
        if os.getenv("DEBUG_SQL"):
            conn.set_trace_callback(lambda query: print(f"SQL: {query}"))
        
        # Check if server exists in the servers view
        server_result = None
        endpoint_id = None
        
        if DATABASE_TYPE == "postgres":
            # For PostgreSQL, first check if the endpoint exists
            endpoint_query = "SELECT id FROM endpoints WHERE ip = %s AND port = %s"
            endpoint_result = Database.fetch_one(endpoint_query, (ip, port))
            
            if endpoint_result:
                endpoint_id = endpoint_result[0]
                # Now check if it's in the verified_endpoints table (which would make it visible in servers view)
                verified_query = "SELECT endpoint_id FROM verified_endpoints WHERE endpoint_id = %s"
                verified_result = Database.fetch_one(verified_query, (endpoint_id,))
                
                if verified_result:
                    # If it's in verified_endpoints, it's in the servers view
                    server_result = [endpoint_id]
            
            if not endpoint_id:
                # Endpoint doesn't exist at all, need to create it
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                result = Database.execute(
                    "INSERT INTO endpoints (ip, port, scan_date, verified) VALUES (%s, %s, %s, 1)",
                    (ip, port, now)
                )
                
                # Get the new endpoint ID
                endpoint_row = Database.fetch_one("SELECT id FROM endpoints WHERE ip = %s AND port = %s", (ip, port))
                endpoint_id = endpoint_row[0] if endpoint_row else None
                
                # Add to verified_endpoints to make it visible in servers view
                if endpoint_id:
                    Database.execute(
                        "INSERT INTO verified_endpoints (endpoint_id, verification_date) VALUES (%s, %s)",
                        (endpoint_id, now)
                    )
                    server_result = [endpoint_id]
            elif not server_result:
                # Endpoint exists but is not verified, update it and add to verified_endpoints
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                Database.execute(
                    "UPDATE endpoints SET verified = 1, verification_date = %s WHERE id = %s",
                    (now, endpoint_id)
                )
                
                # Add to verified_endpoints
                Database.execute(
                    "INSERT INTO verified_endpoints (endpoint_id, verification_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (endpoint_id, now)
                )
                server_result = [endpoint_id]
        else:
            # For SQLite, just check the servers view
            server_result = Database.fetch_one("SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
            
            if not server_result:
                # For SQLite, the original approach works fine
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                result = Database.execute("INSERT INTO servers (ip, port, scan_date) VALUES (?, ?, ?)", 
                              (ip, port, now))
                
                # For SQLite, we can use lastrowid
                server_id = result.lastrowid
        
        server_id = server_result[0] if server_result else None
        
        # Get existing models for this server
        existing_models_query = "SELECT id, name, parameter_size, quantization_level, size_mb FROM models WHERE endpoint_id = ?"
        existing_models = Database.fetch_all(existing_models_query, (server_id,))
        
        # Create a dictionary for easier lookup
        db_models = {row[1]: {"id": row[0], "parameter_size": row[2], 
                            "quantization_level": row[3], "size_mb": row[4]} 
                    for row in existing_models}
        
        # Process models from server
        for model in server_models:
            name = model.get("name", "")
            if not name:
                continue  # Skip models without a name
            
            # Extract model details
            model_size = model.get("size", 0)
            # Ensure we're working with float type
            if isinstance(model_size, (int, float, str)):
                model_size = float(model_size)
            else:
                # Handle potential decimal type or other types
                model_size = float(str(model_size))
                
            model_size_mb = model_size / (1024 * 1024)  # Convert to MB
            
            parameter_size = ""
            quantization_level = ""
            
            # Get detailed info if available
            if "details" in model:
                parameter_size = model["details"].get("parameter_size", "")
                quantization_level = model["details"].get("quantization_level", "")
            
            # Check if model exists in database
            if name in db_models:
                # Update model if details have changed
                existing = db_models[name]
                
                # Convert both values to float before comparison to avoid type errors
                existing_size = float(existing["size_mb"]) if existing["size_mb"] is not None else 0.0
                new_size = float(model_size_mb)
                
                if (existing["parameter_size"] != parameter_size or 
                    existing["quantization_level"] != quantization_level or 
                    abs(existing_size - new_size) > 0.1):  # Allow small size differences
                    
                    Database.execute("""
                        UPDATE models SET 
                        parameter_size = ?, 
                        quantization_level = ?, 
                        size_mb = ? 
                        WHERE id = ?
                    """, (parameter_size, quantization_level, model_size_mb, existing["id"]))
                    updated_models.append(name)
                
                # Remove from db_models to track which are no longer on server
                del db_models[name]
            else:
                # Add new model
                try:
                    Database.execute("""
                        INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                        VALUES (?, ?, ?, ?, ?)
                    """, (server_id, name, parameter_size, quantization_level, model_size_mb))
                    added_models.append(name)
                except sqlite3.IntegrityError:
                    # Handle potential race condition if the model was added in parallel
                    print(f"Model {name} already exists in the database. Skipping.")
        
        # Delete models that are no longer on the server
        for name, model_info in db_models.items():
            Database.execute("DELETE FROM models WHERE id = ?", (model_info["id"],))
            deleted_models.append(name)
        
        # Update scan_date in endpoints table directly (instead of servers view)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if DATABASE_TYPE == "postgres":
            # For PostgreSQL, update the underlying table, not the view
            Database.execute("UPDATE endpoints SET scan_date = %s WHERE id = %s", (now, server_id))
        else:
            # For SQLite, the original approach works fine
            Database.execute("UPDATE servers SET scan_date = ? WHERE id = ?", (now, server_id))
        
    except Exception as e:
        print(f"Error syncing models: {str(e)}")
        # In our Database abstraction, we don't need to manually rollback
        # as each operation is committed automatically
        raise
    finally:
        if conn:
            conn.close()
    
    return (added_models, updated_models, deleted_models)

def get_servers():
    """
    Get all servers from the database
    """
    conn = Database()
    
    query = '''
        SELECT s.id, s.ip, s.port, s.scan_date, COUNT(m.id) as model_count
        FROM servers s
        LEFT JOIN models m ON s.id = m.endpoint_id
        GROUP BY s.id, s.ip, s.port, s.scan_date
        ORDER BY s.scan_date DESC
    '''
    servers = Database.fetch_all(query)
    conn.close()
    return servers

if __name__ == "__main__":
    setup_database()
