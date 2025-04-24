#!/usr/bin/env python3
"""
Unified Discord Bot Commands

This module contains unified command implementations that consolidate
multiple similar commands into a single command with a type parameter.
"""

import discord
from discord import app_commands
import sqlite3
import logging
import json
import asyncio
import aiohttp
from datetime import datetime
import os
from typing import Optional, List, Dict, Any, Union, Tuple

# Added by migration script
from database import Database, init_database

def setup_additional_tables(db_file):
    """
    Set up additional database tables for chat history and user model selection
    
    Args:
        db_file: Path to the SQLite database
    """
    try:
        conn = Database()
        # Using Database methods instead of cursor
        
        # Create table for storing selected models per user
        Database.execute('''
        CREATE TABLE IF NOT EXISTS user_selected_models (
            user_id TEXT PRIMARY KEY,
            model_id INTEGER,
            selection_date TEXT,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        ''')
        
        # Create table for storing chat history - using SERIAL for PostgreSQL compatibility
        Database.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            model_id INTEGER,
            prompt TEXT,
            system_prompt TEXT,
            response TEXT,
            temperature REAL,
            max_tokens INTEGER,
            timestamp TEXT,
            eval_count INTEGER,
            eval_duration REAL,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        ''')
        
        # Create index on user_id for faster lookups
        Database.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history (user_id)')
        Database.execute('CREATE INDEX IF NOT EXISTS idx_chat_history_model_id ON chat_history (model_id)')
        
        # Commit handled by Database methods
        conn.close()
        logging.info("Additional database tables initialized")
    except Exception as e:
        logging.error(f"Database error while setting up additional tables: {e}")

# This function will be registered in discord_bot.py
def register_unified_commands(bot, DB_FILE, safe_defer, safe_followup, session, check_server_connectivity, logger, sync_models_with_server, get_servers):
    """
    Register unified commands that combine multiple similar commands
    
    Args:
        bot: The Discord bot instance
        DB_FILE: Path to the SQLite database
        safe_defer: Function to safely defer interactions
        safe_followup: Function to safely follow up on interactions
        session: aiohttp ClientSession
        check_server_connectivity: Function to check server connectivity
        logger: Logger instance
        sync_models_with_server: Function to sync models with server
        get_servers: Function to get servers
    """
    
    # Initialize additional database tables for chat and model selection
    setup_additional_tables(DB_FILE)
    
    # Helper function to get a user's selected model
    async def get_user_selected_model(user_id):
        """Get the currently selected model for a user"""
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Get the selected model for this user
            query = '''
                SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                FROM user_selected_models usm
                JOIN models m ON usm.model_id = m.id
                JOIN servers s ON m.endpoint_id = s.id
                WHERE usm.user_id = ?
            '''
            
            result = Database.fetch_one(query, (str(user_id),))
            conn.close()
            
            return result  # Returns None if no model is selected
        except Exception as e:
            logger.error(f"Error getting user selected model: {e}")
            return None
    
    # Helper function to save a model selection for a user
    async def save_user_model_selection(user_id, model_id):
        """Save a model selection for a user"""
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Save the selected model for this user
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query = '''
                INSERT OR REPLACE INTO user_selected_models (user_id, model_id, selection_date)
                VALUES (?, ?, ?)
            '''
            Database.execute(query, (str(user_id), model_id, now))
            
            # Commit handled by Database methods
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving user model selection: {e}")
            return False
    
    # Helper function to save chat history
    async def save_chat_history(user_id, model_id, prompt, system_prompt, response, temperature, max_tokens, eval_count, eval_duration):
        """Save a chat interaction to history"""
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Save the chat history
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query = '''
                INSERT INTO chat_history 
                (user_id, model_id, prompt, system_prompt, response, temperature, max_tokens, timestamp, eval_count, eval_duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            Database.execute(query, (
                str(user_id), model_id, prompt, system_prompt, response, 
                temperature, max_tokens, now, eval_count, eval_duration
            ))
            
            # Commit handled by Database methods
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving chat history: {e}")
            return False

    @bot.tree.command(name="unified_search", description="Unified search command for models and servers")
    @app_commands.describe(
        search_type="Type of search to perform",
        query="Search term",
        sort_by="Field to sort results by",
        descending="Sort in descending order (true) or ascending order (false)",
        limit="Maximum number of results to return",
        show_endpoints="Show all endpoints for each model"
    )
    @app_commands.choices(search_type=[
        app_commands.Choice(name="Model Name", value="name"),
        app_commands.Choice(name="Parameter Size", value="params"),
        app_commands.Choice(name="All Models", value="all"),
        app_commands.Choice(name="Models with Servers", value="with_servers")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Parameters", value="params"),
        app_commands.Choice(name="Quantization", value="quant"),
        app_commands.Choice(name="Count", value="count")
    ])
    async def unified_search(
        interaction,
        search_type: str,
        query: str = "",
        sort_by: str = None,
        descending: bool = True,
        limit: int = 25,
        show_endpoints: bool = False
    ):
        """
        Unified search command that combines several search commands
        
        Args:
            interaction: Discord interaction
            search_type: Type of search (name, params, all, with_servers)
            query: Search term (if applicable)
            sort_by: Field to sort results by
            descending: Sort in descending order (true) or ascending order (false)
            limit: Maximum number of results to return
            show_endpoints: Show all endpoints for each model
        """
        if not await safe_defer(interaction):
            return
            
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Default sorting - by server count in descending order
            orderby = "server_count DESC"
            
            # Apply sorting options if provided
            if sort_by:
                if sort_by == "name":
                    if descending:
                        orderby = "name DESC"
                    else:
                        orderby = "name ASC"
                elif sort_by == "params":
                    if descending:
                        orderby = """
                        CASE 
                            WHEN parameter_size LIKE '%B' THEN 
                                CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                            ELSE 0
                        END DESC"""
                    else:
                        orderby = """
                        CASE 
                            WHEN parameter_size LIKE '%B' THEN 
                                CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                            ELSE 0
                        END ASC"""
                elif sort_by == "quant":
                    if descending:
                        orderby = "quantization_level DESC"
                    else:
                        orderby = "quantization_level ASC"
                elif sort_by == "count":
                    if descending:
                        orderby = "server_count DESC"
                    else:
                        orderby = "server_count ASC"
                elif sort_by == "size":
                    if descending:
                        orderby = "size_mb DESC"
                    else:
                        orderby = "size_mb ASC"
                        
            # Determine search type and construct query
            if search_type == "name" and query:
                # Search by model name
                search = "%" + query + "%"
                query_sql = f"""
                    SELECT 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        COUNT(DISTINCT m.endpoint_id) as server_count
                    FROM models m
                    WHERE m.name LIKE ?
                    GROUP BY m.name, m.parameter_size, m.quantization_level
                    ORDER BY {orderby}
                    LIMIT ?
                """
                Database.execute(query_sql, (search, limit))
                title = f"Models containing '{query}'"
                
            elif search_type == "params" and query:
                # Search by parameter size
                search = "%" + query + "%"
                query_sql = f"""
                    SELECT 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        COUNT(DISTINCT m.endpoint_id) as server_count
                    FROM models m
                    WHERE m.parameter_size LIKE ?
                    GROUP BY m.name, m.parameter_size, m.quantization_level
                    ORDER BY {orderby}
                    LIMIT ?
                """
                Database.execute(query_sql, (search, limit))
                title = f"Models with parameter size '{query}'"
                
            elif search_type == "all":
                # List all models
                query_sql = f"""
                    SELECT 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        COUNT(DISTINCT m.endpoint_id) as server_count
                    FROM models m
                    GROUP BY m.name, m.parameter_size, m.quantization_level
                    ORDER BY {orderby}
                    LIMIT ?
                """
                Database.execute(query_sql, (limit,))
                title = "All models"
                
            elif search_type == "with_servers":
                # List models with their servers
                query_sql = f"""
                    SELECT 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        COUNT(DISTINCT m.endpoint_id) as server_count
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    GROUP BY m.name, m.parameter_size, m.quantization_level
                    ORDER BY {orderby}
                    LIMIT ?
                """
                Database.execute(query_sql, (limit,))
                title = "Models with their servers"
                
            else:
                await safe_followup(interaction, f"Invalid search type: {search_type}")
                conn.close()
                return
                
            results = Database.fetch_all(query, params)
            
            if not results:
                if query:
                    await safe_followup(interaction, f"No models found matching the criteria: '{query}'")
                else:
                    await safe_followup(interaction, "No models found.")
                conn.close()
                return
                
            # Format the results
            message = f"**{title}**\nFound {len(results)} unique models\n\n"
            message += "Model Name | Parameters | Quantization | Count | Endpoints\n"
            message += "-" * 90 + "\n"
            
            for model in results:
                name, params, quant, count = model
                
                # Get servers for this model if showing endpoints
                if show_endpoints:
                    if search_type == "name" and query:
                        Database.execute("""
                            SELECT m.id, s.ip, s.port
                            FROM models m
                            JOIN servers s ON m.endpoint_id = s.id
                            WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                        """, (name, params, quant))
                    elif search_type == "params" and query:
                        Database.execute("""
                            SELECT m.id, s.ip, s.port
                            FROM models m
                            JOIN servers s ON m.endpoint_id = s.id
                            WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                        """, (name, params, quant))
                    elif search_type == "all" or search_type == "with_servers":
                        Database.execute("""
                            SELECT m.id, s.ip, s.port
                            FROM models m
                            JOIN servers s ON m.endpoint_id = s.id
                            WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                        """, (name, params, quant))
                    
                    servers = Database.fetch_all(query, params)
                else:
                    servers = []
                
                # Trim long model names
                display_name = name
                if len(display_name) > 20:
                    display_name = name[:17] + "..."
                    
                # Add this model to the message with header info
                message += f"{display_name} | {params or 'N/A'} | {quant or 'N/A'} | {count} | "
                
                # Add endpoint information if requested
                if show_endpoints and servers:
                    # Check if endpoint list is too long
                    if len(servers) > 10:
                        # List the first 5 servers
                        servers_text = "\n  • " + "\n  • ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers[:5]])
                        message += f"{servers_text}\n  • ... and {len(servers) - 5} more endpoints\n"
                    else:
                        # List all servers with bullet points for better readability
                        servers_text = "\n  • " + "\n  • ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers])
                        message += f"{servers_text}\n"
                else:
                    message += "Use 'show_endpoints=True' to see all endpoints\n"
                
            # Check if message is too long and truncate if needed
            if len(message) > 1900:
                # Truncate and indicate there's more
                message = message[:1850] + "\n... (additional content truncated) ..."
                
            # Send the response
            await safe_followup(interaction, message)
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in unified_search: {str(e)}")
            await safe_followup(interaction, f"Error searching models: {str(e)}")

    @bot.tree.command(name="server", description="Unified server management command")
    @app_commands.describe(
        action="Action to perform",
        ip="Server IP address",
        port="Server port",
        sort_by="Field to sort results by",
        descending="Sort in descending order (true) or ascending order (false)",
        limit="Maximum number of results to return"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Servers", value="list"),
        app_commands.Choice(name="Check Server Models", value="check"),
        app_commands.Choice(name="Sync Server Models", value="sync"),
        app_commands.Choice(name="Server Details", value="info"),
        app_commands.Choice(name="Verify All Servers", value="verify"),
        app_commands.Choice(name="Purge Unreachable Servers", value="purge")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="ID", value="id"),
        app_commands.Choice(name="IP", value="ip"),
        app_commands.Choice(name="Scan Date", value="date"),
        app_commands.Choice(name="Model Count", value="count")
    ])
    async def unified_server(
        interaction,
        action: str,
        ip: str = None,
        port: int = None,
        sort_by: str = None,
        descending: bool = True,
        limit: int = 25
    ):
        """
        Unified server management command that combines server-related commands
        
        Args:
            interaction: Discord interaction
            action: Server action to perform
            ip: Server IP (if needed)
            port: Server port (if needed)
            sort_by: Field to sort by
            descending: Sort in descending order
            limit: Maximum number of results
        """
        if not await safe_defer(interaction):
            return
            
        try:
            # LIST ALL SERVERS
            if action == "list":
                servers = get_servers()
                
                if not servers:
                    await safe_followup(interaction, "No servers found in the database.")
                    return
                
                message = "**Ollama Servers:**\n\n"
                
                for server in servers:
                    server_id, ip, port, scan_date, model_count = server
                    scan_date = scan_date or "Never"
                    
                    message += f"**Server ID: {server_id}**\n"
                    message += f"- Address: {ip}:{port}\n"
                    message += f"- Last Scan: {scan_date}\n"
                    message += f"- Models: {model_count}\n\n"
                
                # Send as a single message, truncating if necessary
                if len(message) > 1900:
                    message = message[:1897] + "..."
                    
                await safe_followup(interaction, message)
                return
            
            # CHECK SERVER MODELS
            elif action == "check":
                if not ip or not port:
                    await safe_followup(interaction, "Please provide both IP and port for the 'check' action.")
                    return
                
                # Call the API to get the list of available models on the server
                try:
                    async with session.get(f"http://{ip}:{port}/api/tags", timeout=10) as response:
                        if response.status != 200:
                            response_text = await response.text()
                            await safe_followup(interaction, f"Error: Failed to retrieve models from server {ip}:{port}: {response_text}")
                            return
                        
                        # Parse the response
                        result = await response.json()
                        models = result.get("models", [])
                except asyncio.TimeoutError:
                    await safe_followup(interaction, f"Connection timed out when attempting to reach {ip}:{port}")
                    return
                except Exception as e:
                    await safe_followup(interaction, f"Error connecting to server: {str(e)}")
                    return
                
                if not models:
                    await safe_followup(interaction, f"No models found on server {ip}:{port}.")
                    return
                
                # Create a single consolidated message
                details = f"**Found {len(models)} models on {ip}:{port}**\n\n"
                
                # Limit to a reasonable number to avoid message length issues
                MAX_MODELS_TO_SHOW = 15
                models_to_show = models[:MAX_MODELS_TO_SHOW]
                
                # Process each model
                for i, model in enumerate(models_to_show):
                    name = model.get("name", "Unknown")
                    model_size = model.get("size", 0) / (1024 * 1024)  # Convert to MB
                    modified_at = model.get("modified_at", "Unknown")
                    
                    details += f"**{i+1}. {name}**\n"
                    details += f"- Size: {model_size:.2f} MB\n"
                    details += f"- Modified: {modified_at}\n"
                    
                    # Get parameter info if available
                    if "details" in model:
                        details += f"- Format: {model['details'].get('format', 'Unknown')}\n"
                        details += f"- Family: {model['details'].get('family', 'Unknown')}\n"
                        details += f"- Parameter Size: {model['details'].get('parameter_size', 'Unknown')}\n"
                        details += f"- Quantization: {model['details'].get('quantization_level', 'Unknown')}\n"
                    
                    details += "\n"  # Add line break between models
                
                # If there are more models, mention how many weren't shown
                if len(models) > MAX_MODELS_TO_SHOW:
                    details += f"(Additional {len(models) - MAX_MODELS_TO_SHOW} models not displayed)"
                
                # Cap message length if needed
                if len(details) > 1900:
                    details = details[:1897] + "..."
                    
                await safe_followup(interaction, details)
                return
                
            # SYNC SERVER MODELS
            elif action == "sync":
                if not ip or not port:
                    await safe_followup(interaction, "Please provide both IP and port for the 'sync' action.")
                    return
                
                # Clean the IP to remove any trailing/leading colons
                clean_ip = ip.strip(":")
                
                await safe_followup(interaction, f"Synchronizing database with models on {clean_ip}:{port}...")
                
                try:
                    # Call the sync function
                    added, updated, removed = sync_models_with_server(clean_ip, port)
                    
                    # Create a structured report
                    message = f"Database synchronization with {clean_ip}:{port} complete:\n"
                    message += f"Added {len(added)} new models\n"
                    message += f"Updated {len(updated)} existing models\n"
                    message += f"Removed {len(removed)} models no longer on server"
                    
                    # If there are specific models to report, add them
                    if added:
                        message += "\n\nAdded models: " + ", ".join(added[:10])
                        if len(added) > 10:
                            message += f" and {len(added) - 10} additional models"
                    
                    if updated:
                        message += "\n\nUpdated models: " + ", ".join(updated[:10])
                        if len(updated) > 10:
                            message += f" and {len(updated) - 10} additional models"
                    
                    if removed:
                        message += "\n\nRemoved models: " + ", ".join(removed[:10])
                        if len(removed) > 10:
                            message += f" and {len(removed) - 10} additional models"
                    
                    await safe_followup(interaction, message)
                except Exception as e:
                    await safe_followup(interaction, f"Error during synchronization: {str(e)}")
                    logger.error(f"Error in sync_server: {str(e)}")
                return
                
            # SERVER INFO
            elif action == "info":
                if not ip:
                    await safe_followup(interaction, "Please provide at least an IP address for the 'info' action.")
                    return
                
                conn = Database()
                # Using Database methods instead of cursor
                
                # Default port if not provided
                if not port:
                    port_condition = ""
                    port_value = None
                else:
                    port_condition = "AND port = ?"
                    port_value = port
                
                # Query for server info
                if port_value:
                    Database.execute("""
                        SELECT id, ip, port, scan_date 
                        FROM servers 
                        WHERE ip LIKE ? AND port = ?
                        ORDER BY scan_date DESC
                    """, (f"%{ip}%", port_value))
                else:
                    Database.execute("""
                        SELECT id, ip, port, scan_date 
                        FROM servers 
                        WHERE ip LIKE ?
                        ORDER BY scan_date DESC
                    """, (f"%{ip}%",))
                
                servers = Database.fetch_all(query, params)
                
                if not servers:
                    await safe_followup(interaction, f"No servers found matching IP: {ip}" + (f" and port: {port}" if port else ""))
                    conn.close()
                    return
                
                # Prepare detailed info for each matching server
                message = f"**Server Information for {ip}" + (f":{port}" if port else "") + "**\n\n"
                
                for server in servers:
                    server_id, server_ip, server_port, scan_date = server
                    
                    # Get model count
                    Database.execute("SELECT COUNT(*) FROM models WHERE endpoint_id = ?", (server_id,))
                    model_count = Database.fetch_one(query, params)[0]
                    
                    # Get model details
                    Database.execute("""
                        SELECT name, parameter_size, quantization_level, size_mb
                        FROM models
                        WHERE endpoint_id = ?
                        ORDER BY name
                        LIMIT 20
                    """, (server_id,))
                    
                    models = Database.fetch_all(query, params)
                    
                    # Add server details
                    message += f"**Server ID: {server_id}**\n"
                    message += f"- Address: {server_ip}:{server_port}\n"
                    message += f"- Last Scan: {scan_date or 'Never'}\n"
                    message += f"- Models: {model_count}\n\n"
                    
                    if models:
                        message += "**Available Models:**\n"
                        for model in models:
                            name, params, quant, size = model
                            model_info = f"- {name}"
                            if params:
                                model_info += f" ({params}"
                                if quant:
                                    model_info += f", {quant}"
                                model_info += ")"
                            message += model_info + "\n"
                        
                        if model_count > 20:
                            message += f"(and {model_count - 20} more models...)\n"
                        
                        message += "\n"
                
                # Check if message is too long and truncate if needed
                if len(message) > 1900:
                    message = message[:1850] + "\n... (additional content truncated) ..."
                
                await safe_followup(interaction, message)
                conn.close()
                return
                
            # VERIFY ALL SERVERS
            elif action == "verify":
                await safe_followup(interaction, "Starting verification of all servers... This may take a while.")
                
                # Get all servers
                conn = Database()
                # Using Database methods instead of cursor
                Database.execute("SELECT id, ip, port, scan_date FROM servers ORDER BY scan_date DESC")
                servers = Database.fetch_all(query, params)
                conn.close()
                
                if not servers:
                    await safe_followup(interaction, "No servers found in the database.")
                    return
                
                # Check each server's connectivity
                total = len(servers)
                reachable = 0
                unreachable = []
                
                # Process in batches to avoid timeouts
                BATCH_SIZE = 10
                for i in range(0, total, BATCH_SIZE):
                    batch = servers[i:i+BATCH_SIZE]
                    
                    for server_id, ip, port, scan_date in batch:
                        is_reachable, error = await check_server_connectivity(ip, port)
                        if is_reachable:
                            reachable += 1
                        else:
                            unreachable.append((server_id, ip, port, error))
                    
                    # Provide progress updates
                    if (i + BATCH_SIZE) % 50 == 0 or (i + BATCH_SIZE) >= total:
                        prog_message = f"Progress: {min(i + BATCH_SIZE, total)}/{total} servers checked. {reachable} reachable, {len(unreachable)} unreachable."
                        await safe_followup(interaction, prog_message)
                
                # Final report
                if unreachable:
                    # Generate a list of unreachable servers
                    unreachable_list = ""
                    for _, ip, port, error in unreachable[:20]:  # Limit to 20 servers in the message
                        unreachable_list += f"- {ip}:{port} - {error}\n"
                    
                    if len(unreachable) > 20:
                        unreachable_list += f"... and {len(unreachable) - 20} more servers\n"
                    
                    result_message = f"**Verification complete**\n\n"
                    result_message += f"Total servers: {total}\n"
                    result_message += f"Reachable: {reachable}\n"
                    result_message += f"Unreachable: {len(unreachable)}\n\n"
                    result_message += "**Unreachable Servers:**\n"
                    result_message += unreachable_list
                    result_message += "\nUse `/server action:purge` to remove unreachable servers and their models."
                    
                    # Truncate if needed
                    if len(result_message) > 1900:
                        result_message = result_message[:1850] + "\n... (list truncated) ..."
                    
                    await safe_followup(interaction, result_message)
                else:
                    await safe_followup(interaction, f"All {total} servers are reachable!")
                
                return
                
            # PURGE UNREACHABLE SERVERS
            elif action == "purge":
                await safe_followup(interaction, "Scanning for unreachable servers... This may take a while.")
                
                # Get all servers
                conn = Database()
                # Using Database methods instead of cursor
                Database.execute("SELECT id, ip, port FROM servers")
                servers = Database.fetch_all(query, params)
                
                if not servers:
                    await safe_followup(interaction, "No servers found in the database.")
                    conn.close()
                    return
                
                # Check each server and remove unreachable ones
                total = len(servers)
                unreachable = []
                removed = 0
                
                # Process in batches
                BATCH_SIZE = 10
                for i in range(0, total, BATCH_SIZE):
                    batch = servers[i:i+BATCH_SIZE]
                    batch_unreachable = []
                    
                    for server_id, ip, port in batch:
                        is_reachable, error = await check_server_connectivity(ip, port)
                        if not is_reachable:
                            batch_unreachable.append((server_id, ip, port, error))
                    
                    # Remove unreachable servers
                    for server_id, ip, port, error in batch_unreachable:
                        Database.execute("DELETE FROM models WHERE endpoint_id = ?", (server_id,))
                        Database.execute("DELETE FROM servers WHERE id = ?", (server_id,))
                        removed += 1
                        unreachable.append((ip, port, error))
                    
                    # Commit handled by Database methods
                    
                    # Provide progress updates
                    if (i + BATCH_SIZE) % 50 == 0 or (i + BATCH_SIZE) >= total:
                        prog_message = f"Progress: {min(i + BATCH_SIZE, total)}/{total} servers checked. {removed} unreachable servers removed."
                        await safe_followup(interaction, prog_message)
                
                conn.close()
                
                # Final report
                if unreachable:
                    unreachable_list = ""
                    for ip, port, error in unreachable[:20]:  # Limit to 20 servers in the message
                        unreachable_list += f"- {ip}:{port} - {error}\n"
                    
                    if len(unreachable) > 20:
                        unreachable_list += f"... and {len(unreachable) - 20} more servers\n"
                    
                    result_message = f"**Purge complete**\n\n"
                    result_message += f"Total servers checked: {total}\n"
                    result_message += f"Unreachable servers removed: {removed}\n\n"
                    result_message += "**Removed Servers:**\n"
                    result_message += unreachable_list
                    
                    # Truncate if needed
                    if len(result_message) > 1900:
                        result_message = result_message[:1850] + "\n... (list truncated) ..."
                    
                    await safe_followup(interaction, result_message)
                else:
                    await safe_followup(interaction, f"All {total} servers are reachable! No servers were removed.")
                
                return
            
            else:
                await safe_followup(interaction, f"Invalid action: {action}")
                
        except Exception as e:
            logger.error(f"Error in unified_server: {str(e)}")
            await safe_followup(interaction, f"Error processing server command: {str(e)}")

    @bot.tree.command(name="admin", description="Unified admin command for maintenance tasks")
    @app_commands.describe(
        action="Admin action to perform",
        scope="Scope of the command (e.g., global or guild)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Refresh Commands", value="refresh"),
        app_commands.Choice(name="Sync to Guild", value="guild_sync"),
        app_commands.Choice(name="Full Refresh", value="full_refresh"),
        app_commands.Choice(name="Clean Database", value="cleanup"),
        app_commands.Choice(name="Update All Models", value="update_models")
    ])
    @app_commands.choices(scope=[
        app_commands.Choice(name="Global", value="global"),
        app_commands.Choice(name="Current Guild", value="guild")
    ])
    async def unified_admin(
        interaction,
        action: str,
        scope: str = "guild"
    ):
        """
        Unified admin command for bot maintenance tasks
        
        Args:
            interaction: Discord interaction
            action: Admin action to perform
            scope: Scope of the command
        """
        # Check if user has admin rights
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator privileges to use admin commands.", ephemeral=True)
            return
            
        if not await safe_defer(interaction):
            return
            
        try:
            # Define a placeholder for additional implementations
            await safe_followup(interaction, f"Admin command {action} with scope {scope} is being processed...")
            
            # Actual implementation would go here, calling the appropriate admin functions
            message = f"Admin command '{action}' with scope '{scope}' completed."
            await safe_followup(interaction, message)
            
        except Exception as e:
            logger.error(f"Error in unified_admin: {str(e)}")
            await safe_followup(interaction, f"Error processing admin command: {str(e)}")

    @bot.tree.command(name="model", description="Unified model management command")
    @app_commands.describe(
        action="Action to perform",
        model_id="Model ID for select/delete actions",
        ip="Server IP for add action",
        port="Server port for add action",
        model_name="Model name for add action",
        info="Additional model info for add action",
        search_term="Search term for list action",
        param_size="Parameter size filter (e.g. 7B, 13B)",
        quant_level="Quantization level filter (e.g. Q4_0, Q5_K_M)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Models", value="list"),
        app_commands.Choice(name="Select Model", value="select"),
        app_commands.Choice(name="Add Model", value="add"),
        app_commands.Choice(name="Delete Model", value="delete"),
        app_commands.Choice(name="Current Default", value="current"),
        app_commands.Choice(name="Search Models", value="search")
    ])
    async def unified_model(
        interaction,
        action: str,
        model_id: int = None,
        ip: str = None,
        port: int = None,
        model_name: str = None,
        info: str = None,
        search_term: str = None,
        param_size: str = None,
        quant_level: str = None
    ):
        """
        Unified model management command
        
        Args:
            interaction: Discord interaction
            action: Action to perform (list, select, add, delete, current, search)
            model_id: Model ID for select/delete actions
            ip: Server IP for add action
            port: Server port for add action
            model_name: Model name for add/search actions
            info: Additional model info for add action
            search_term: Search term for search action
            param_size: Parameter size filter (e.g. 7B, 13B)
            quant_level: Quantization level filter (e.g. Q4_0, Q5_K_M)
        """
        if not await safe_defer(interaction):
            return
            
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            if action == "list":
                # Build a query that counts how many servers each model is on
                Database.execute("""
                    SELECT 
                        m.id, 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        COUNT(DISTINCT m.endpoint_id) as server_count
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    GROUP BY m.name, m.parameter_size, m.quantization_level
                    ORDER BY server_count DESC, m.name ASC
                    LIMIT 25
                """)
                
                results = Database.fetch_all(query, params)
                
                if not results:
                    await safe_followup(interaction, "No models found in the database.")
                    conn.close()
                    return
                
                message = "**All Models**\n\n"
                message += "ID | Model Name | Params | Quantization | Server Count\n"
                message += "-" * 70 + "\n"
                
                for result in results:
                    model_id, name, param_size, quant_level, server_count = result
                    message += f"`{model_id}` | {name} | {param_size} | {quant_level} | {server_count}\n"
                
                message += "\nUse `/model select <model_id>` to select a model as your default."
                
                await safe_followup(interaction, message)
                
            elif action == "select":
                if not model_id:
                    await safe_followup(interaction, "Please provide a model ID to select.")
                    conn.close()
                    return
                
                # Verify the model ID exists
                Database.execute("""
                    SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    WHERE m.id = ?
                """, (model_id,))
                
                result = Database.fetch_one(query, params)
                
                if not result:
                    await safe_followup(interaction, f"Model with ID {model_id} not found.")
                    conn.close()
                    return
                
                model_id, name, param_size, quant_level, ip, port = result
                
                # Check server connectivity
                is_reachable, error = await check_server_connectivity(ip, port)
                if not is_reachable:
                    await safe_followup(interaction, f"Model server ({ip}:{port}) is not reachable: {error}. Please select a different model.")
                    conn.close()
                    return
                
                # Save the user's model selection
                await save_user_model_selection(interaction.user.id, model_id)
                
                # Format model description
                model_desc = f"{name}"
                if param_size:
                    model_desc += f" ({param_size}"
                    if quant_level:
                        model_desc += f", {quant_level}"
                    model_desc += ")"
                
                await safe_followup(interaction, f"✅ Selected **{model_desc}** as your default model. Use `/chat` to interact with it.")
            
            elif action == "add":
                # Implementation for adding a model
                if not ip or not port or not model_name:
                    await safe_followup(interaction, "Please provide IP, port, and model name.")
                    conn.close()
                    return
                
                # Check if the server exists
                Database.execute("SELECT id FROM servers WHERE ip = ? AND port = ?", (ip, port))
                server_result = Database.fetch_one(query, params)
                
                if not server_result:
                    # Add the server
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    Database.execute(
                        "INSERT INTO servers (ip, port, scan_date) VALUES (?, ?, ?)",
                        (ip, port, now)
                    )
                    server_id = Database.lastrowid
                else:
                    server_id = server_result[0]
                
                # Parse model info if provided
                try:
                    model_info = json.loads(info) if info else {}
                except json.JSONDecodeError:
                    model_info = {}
                
                # Set defaults for model metadata
                param_size = model_info.get("parameter_size", "Unknown")
                quant_level = model_info.get("quantization_level", "Unknown")
                size_mb = model_info.get("size_mb", 0)
                
                # Check if model already exists
                Database.execute(
                    "SELECT id FROM models WHERE endpoint_id = ? AND name = ?",
                    (server_id, model_name)
                )
                model_result = Database.fetch_one(query, params)
                
                if model_result:
                    # Update existing model
                    Database.execute(
                        """UPDATE models 
                        SET parameter_size = ?, quantization_level = ?, size_mb = ?
                        WHERE endpoint_id = ? AND name = ?""",
                        (param_size, quant_level, size_mb, server_id, model_name)
                    )
                    model_id = model_result[0]
                    message = f"Updated model **{model_name}** on server {ip}:{port}"
                else:
                    # Add new model
                    Database.execute(
                        """INSERT INTO models 
                        (endpoint_id, name, parameter_size, quantization_level, size_mb)
                        VALUES (?, ?, ?, ?, ?)""",
                        (server_id, model_name, param_size, quant_level, size_mb)
                    )
                    model_id = Database.lastrowid
                    message = f"Added model **{model_name}** to server {ip}:{port}"
                
                # Commit handled by Database methods
                await safe_followup(interaction, message)
            
            elif action == "delete":
                if not model_id:
                    await safe_followup(interaction, "Please provide a model ID to delete.")
                    conn.close()
                    return
                
                # Check if model exists
                Database.execute(
                    """SELECT m.id, m.name, s.ip, s.port
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    WHERE m.id = ?""",
                    (model_id,)
                )
                
                model_result = Database.fetch_one(query, params)
                
                if not model_result:
                    await safe_followup(interaction, f"Model with ID {model_id} not found.")
                    conn.close()
                    return
                
                model_id, name, ip, port = model_result
                
                # Delete the model
                Database.execute("DELETE FROM models WHERE id = ?", (model_id,))
                
                # Also delete from user_selected_models if it was someone's default
                Database.execute("DELETE FROM user_selected_models WHERE model_id = ?", (model_id,))
                
                # Commit handled by Database methods
                
                await safe_followup(interaction, f"✅ Deleted model **{name}** from server {ip}:{port}")
            
            elif action == "current":
                # Get the user's currently selected model
                selected_model = await get_user_selected_model(interaction.user.id)
                
                if not selected_model:
                    await safe_followup(interaction, "You don't have a default model selected. Use `/model select <model_id>` to select one.")
                    conn.close()
                    return
                
                model_id, name, param_size, quant_level, ip, port = selected_model
                
                # Check server connectivity
                is_reachable, error = await check_server_connectivity(ip, port)
                
                # Format model description
                model_desc = f"{name}"
                if param_size:
                    model_desc += f" ({param_size}"
                    if quant_level:
                        model_desc += f", {quant_level}"
                    model_desc += ")"
                
                status = "✅ Available" if is_reachable else f"❌ Unavailable: {error}"
                
                message = f"**Your Default Model**\n\n"
                message += f"Model: **{model_desc}**\n"
                message += f"ID: `{model_id}`\n"
                message += f"Server: {ip}:{port}\n"
                message += f"Status: {status}\n\n"
                
                if not is_reachable:
                    message += "This model is currently unavailable. Use `/model select <model_id>` to select a different model."
                else:
                    message += "Use `/chat <prompt>` to interact with this model."
                
                await safe_followup(interaction, message)
                
            elif action == "search":
                if not search_term and not param_size and not quant_level:
                    await safe_followup(interaction, "Please provide at least one search criteria (search_term, param_size, or quant_level).")
                    conn.close()
                    return
                
                # Build search query
                query_parts = []
                query_params = []
                
                if search_term:
                    query_parts.append("m.name LIKE ?")
                    query_params.append(f"%{search_term}%")
                
                if param_size:
                    query_parts.append("m.parameter_size LIKE ?")
                    query_params.append(f"%{param_size}%")
                    
                if quant_level:
                    query_parts.append("m.quantization_level LIKE ?")
                    query_params.append(f"%{quant_level}%")
                
                query = f"""
                    SELECT 
                        m.id, 
                        m.name, 
                        m.parameter_size, 
                        m.quantization_level, 
                        s.ip, 
                        s.port,
                        s.scan_date
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    WHERE {" AND ".join(query_parts)}
                    ORDER BY s.scan_date DESC
                    LIMIT 25
                """
                
                Database.execute(query, query_params)
                results = Database.fetch_all(query, params)
                
                if not results:
                    filters = []
                    if search_term:
                        filters.append(f"name:'{search_term}'")
                    if param_size:
                        filters.append(f"params:'{param_size}'")
                    if quant_level:
                        filters.append(f"quant:'{quant_level}'")
                        
                    filter_text = ", ".join(filters)
                    await safe_followup(interaction, f"No models found matching the criteria: {filter_text}")
                    conn.close()
                    return
                
                message = "**Search Results**\n\n"
                message += "ID | Model Name | Params | Quantization | Server\n"
                message += "-" * 70 + "\n"
                
                for result in results:
                    model_id, name, param_size, quant_level, ip, port, scan_date = result
                    message += f"`{model_id}` | {name} | {param_size} | {quant_level} | {ip}:{port}\n"
                
                message += "\nUse `/model select <model_id>` to select a model as your default."
                
                await safe_followup(interaction, message)
            
            else:
                await safe_followup(interaction, f"Unknown action: {action}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in unified_model: {str(e)}")
            await safe_followup(interaction, f"Error: {str(e)}")

    @bot.tree.command(name="chat", description="Chat with your selected model")
    @app_commands.describe(
        prompt="Your message to the model",
        system_prompt="Optional system prompt to set context",
        temperature="Controls randomness (0.0 to 1.0)",
        max_tokens="Maximum number of tokens in response",
        model_id="Optional: Specific model ID to use instead of your default model",
        verbose="Show the equivalent curl command"
    )
    async def chat(
        interaction,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        model_id: int = None,
        verbose: bool = False
    ):
        """
        Chat with your selected model or a specified model
        
        Args:
            interaction: Discord interaction
            prompt: Your message to the model
            system_prompt: Optional system prompt to set context
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum number of tokens in response
            model_id: Optional specific model ID to use instead of default
            verbose: Show the equivalent curl command
        """
        if not await safe_defer(interaction):
            return
        
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Determine which model to use
            if model_id:
                # Use the specified model
                Database.execute("""
                    SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    WHERE m.id = ?
                """, (model_id,))
                
                model = Database.fetch_one(query, params)
                
                if not model:
                    await safe_followup(interaction, f"❌ Model with ID {model_id} not found.")
                    conn.close()
                    return
                    
                selected_by = "specified"
            else:
                # Use the user's default model
                model = await get_user_selected_model(interaction.user.id)
                
                if not model:
                    await safe_followup(interaction, "❌ You don't have a default model selected. Use `/model select <model_id>` to select one, or specify a model_id with this command.")
                    conn.close()
                    return
                    
                selected_by = "default"
            
            conn.close()
            
            model_id, name, param_size, quant_level, ip, port = model
            
            # Check server connectivity
            is_reachable, error = await check_server_connectivity(ip, port)
            if not is_reachable:
                await safe_followup(interaction, f"❌ Model server ({ip}:{port}) is not reachable: {error}. Please select a different model.")
                return
            
            # Build model description
            model_desc = f"{name}"
            if param_size:
                model_desc += f" ({param_size}"
                if quant_level:
                    model_desc += f", {quant_level}"
                model_desc += ")"
                
            selection_msg = "Your default" if selected_by == "default" else "Specified"
            await safe_followup(interaction, f"**Using {selection_msg} Model: {model_desc}**\nSending prompt to {ip}:{port}...")
            
            # Build the request data
            request_data = {
                "model": name,
                "prompt": prompt,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # Add system prompt if provided
            if system_prompt:
                request_data["system"] = system_prompt
            
            # Calculate dynamic timeout based on prompt length, model size and max tokens
            prompt_length = len(prompt)
            base_timeout = 180  # Base timeout in seconds (3 minutes)
            
            # Factor in prompt length (longer prompts need more time)
            prompt_factor = 1.0 + (prompt_length / 1000)  # Add 1 second per 1000 chars
            
            # Factor in model complexity based on parameter size
            param_factor = 1.0
            if param_size:
                # Extract number from strings like "7B", "13B", etc.
                try:
                    if "B" in param_size:
                        size_num = float(param_size.replace("B", "").strip())
                        param_factor = 1.0 + (size_num / 10)  # Larger models get more time
                except ValueError:
                    # If we can't parse it, use default factor
                    param_factor = 1.5
            
            # Factor in max_tokens (more tokens = more generation time)
            token_factor = max(1.0, max_tokens / 1000)
            
            # Calculate final timeout (minimum 180s, maximum 900s)
            dynamic_timeout = min(900, max(180, base_timeout * prompt_factor * param_factor * token_factor))
            
            logger.info(f"Dynamic timeout for {name}: {dynamic_timeout:.1f}s (prompt: {prompt_length} chars, model: {param_size}, max_tokens: {max_tokens})")
            
            await safe_followup(interaction, f"**Using {selection_msg} Model: {model_desc}**\nSending prompt to {ip}:{port}...\nTimeout set to {int(dynamic_timeout)} seconds based on prompt length and model size.")
            
            try:
                # Use aiohttp for async operation
                start_time = datetime.now()
                
                async with session.post(
                    f"http://{ip}:{port}/api/generate", 
                    json=request_data, 
                    timeout=dynamic_timeout  # Use dynamic timeout
                ) as response:
                    if response.status == 200:
                        raw_response_text = await response.text()
                        result = json.loads(raw_response_text)
                        response_text = result.get("response", "No response received.")
                        
                        # Get stats if available
                        eval_count = result.get("eval_count", 0)
                        eval_duration = result.get("eval_duration", 0)
                        
                        # Save to chat history
                        await save_chat_history(
                            interaction.user.id, 
                            model_id, 
                            prompt, 
                            system_prompt, 
                            response_text, 
                            temperature, 
                            max_tokens, 
                            eval_count, 
                            eval_duration / 1000000 if eval_duration else 0
                        )
                        
                        # Add some stats to the response
                        stats = f"\n\n---\nTokens: {eval_count} | Time: {eval_duration/1000000:.2f}s"
                        if eval_duration > 0 and eval_count > 0:
                            tokens_per_second = eval_count / (eval_duration / 1000000000)
                            stats += f" | Throughput: {tokens_per_second:.2f} tokens/sec"
                        
                        response_text += stats
                        
                        # If verbose mode is enabled, show the raw API response
                        if verbose:
                            # Calculate total request time
                            end_time = datetime.now()
                            total_time = (end_time - start_time).total_seconds()
                            
                            # Build verbose output
                            verbose_output = f"**API Request/Response Details:**\n\n"
                            verbose_output += f"**Request URL:** `http://{ip}:{port}/api/generate`\n\n"
                            verbose_output += f"**Request Body:**\n```json\n{json.dumps(request_data, indent=2)}\n```\n\n"
                            verbose_output += f"**Response Status:** {response.status} {response.reason}\n\n"
                            verbose_output += f"**Response Headers:**\n```\n"
                            for header, value in response.headers.items():
                                verbose_output += f"{header}: {value}\n"
                            verbose_output += "```\n\n"
                            verbose_output += f"**Raw Response:**\n```json\n{json.dumps(json.loads(raw_response_text), indent=2)}\n```\n\n"
                            verbose_output += f"**Total Time:** {total_time:.2f} seconds\n"
                            
                            # Send verbose output first
                            await safe_followup(interaction, verbose_output)
                        
                        # Format the response with bold header but keep the model's output as is
                        formatted_response = f"**Response from {name}:**\n{response_text}"
                            
                        await safe_followup(interaction, formatted_response)
                    else:
                        response_text = await response.text()
                        
                        # If verbose mode is enabled, show more details about the error
                        if verbose:
                            error_output = f"**API Error Details:**\n\n"
                            error_output += f"**Request URL:** `http://{ip}:{port}/api/generate`\n\n"
                            error_output += f"**Request Body:**\n```json\n{json.dumps(request_data, indent=2)}\n```\n\n"
                            error_output += f"**Response Status:** {response.status} {response.reason}\n\n"
                            error_output += f"**Response Headers:**\n```\n"
                            for header, value in response.headers.items():
                                error_output += f"{header}: {value}\n"
                            error_output += "```\n\n"
                            error_output += f"**Error Response:**\n```\n{response_text}\n```\n"
                            
                            await safe_followup(interaction, error_output)
                        else:
                            await safe_followup(interaction, f"Error: {response.status} - {response_text}")
            except asyncio.TimeoutError:
                await safe_followup(interaction, f"Request timed out after {int(dynamic_timeout)} seconds. The model may be taking too long to respond.")
            except aiohttp.ClientError as e:
                logger.error(f"Connection error in chat: {str(e)}")
                await safe_followup(interaction, f"Request failed: {str(e)}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                await safe_followup(interaction, f"Error parsing response from the model: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            await safe_followup(interaction, f"Error: {str(e)}")

    @bot.tree.command(name="quickprompt", description="Search, select and interact with a model in one command")
    @app_commands.describe(
        action="Action to perform",
        prompt="Your prompt/message to send to the model",
        model_name="Model name to search for",
        server_name="Server name to search for (optional)",
        system_prompt="Optional system prompt to set context",
        temperature="Controls randomness (0.0 to 1.0)",
        max_tokens="Maximum number of tokens in response"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="interact", value="interact"),
        app_commands.Choice(name="history", value="history"),
        app_commands.Choice(name="search", value="search"),
        app_commands.Choice(name="continue", value="continue"),
        app_commands.Choice(name="image", value="image"),
        app_commands.Choice(name="advanced", value="advanced")
    ])
    async def unified_chat_command(
        interaction,
        action: str,
        prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        server_name: Optional[str] = None,
        system_prompt: Optional[str] = "",
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 1000
    ):
        """
        Search, select and interact with a model in one command
        
        Args:
            interaction: Discord interaction
            action: Action to perform (interact, history, search, etc.)
            prompt: Your prompt/message to send to the model
            model_name: Model name to search for
            server_name: Server name to search for
            system_prompt: System prompt to set context
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum number of tokens in response
        """
        await safe_defer(interaction)
        
        try:
            if action == "interact":
                # Simple chat interaction with a model
                if not model_name:
                    await safe_followup(interaction, "Please provide a model name to interact with.")
                    return
                
                if not prompt:
                    await safe_followup(interaction, "Please provide a prompt for the model.")
                    return
                
                # Find models matching the name
                conn = Database()
                
                query = """
                    SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                    FROM models m
                    JOIN servers s ON m.endpoint_id = s.id
                    WHERE LOWER(m.name) LIKE %s 
                    ORDER BY m.parameter_size DESC
                    LIMIT 1
                """
                
                model = Database.fetch_one(query, (f"%{model_name.lower()}%",))
                conn.close()
                
                if not model:
                    await safe_followup(interaction, f"No models found matching '{model_name}'")
                    return
                
                model_id, name, param_size, quant, ip, port = model
                
                # Call to model using Ollama API
                url = f"http://{ip}:{port}/api/generate"
                
                request_data = {
                    "model": name,
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                }
                
                response_text = ""
                start_time = datetime.now()
                
                try:
                    async with session.post(url, json=request_data) as response:
                        if response.status == 200:
                            response_data = await response.json()
                            response_text = response_data.get("response", "")
                            eval_count = response_data.get("eval_count", 0)
                            eval_duration = (response_data.get("eval_duration", 0) or 0) / 1000000000  # Convert nanoseconds to seconds
                        else:
                            await safe_followup(interaction, f"Error: API returned status {response.status}")
                            return
                except Exception as e:
                    logger.error(f"Error interacting with model API: {str(e)}")
                    await safe_followup(interaction, f"Error interacting with model: {str(e)}")
                    return
                
                duration = (datetime.now() - start_time).total_seconds()
                
                # Save chat history
                await save_chat_history(str(interaction.user.id), model_id, prompt, system_prompt, 
                                      response_text, temperature, max_tokens, eval_count, eval_duration)
                
                # Format and send the response
                embed = discord.Embed(
                    title=f"Chat with {name}",
                    description=f"**Your prompt:**\n{prompt[:1000]}...",
                    color=0x3498db
                )
                
                # Add system prompt if provided
                if system_prompt:
                    embed.add_field(name="System Prompt", value=system_prompt[:1024], inline=False)
                
                # Add the model's response, chunking if necessary
                response_chunks = [response_text[i:i+1024] for i in range(0, len(response_text), 1024)]
                for i, chunk in enumerate(response_chunks[:10]):  # Limit to 10 chunks to stay within embed limits
                    field_name = "Response" if i == 0 else "Response (continued)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
                
                # Add metadata
                embed.add_field(
                    name="Model Info", 
                    value=f"Name: {name}\nSize: {param_size}\nQuantization: {quant}", 
                    inline=True
                )
                
                embed.add_field(
                    name="Generation Stats", 
                    value=f"Temperature: {temperature}\nMax Tokens: {max_tokens}\nEval Count: {eval_count}\nTime: {eval_duration:.2f}s", 
                    inline=True
                )
                
                embed.set_footer(text=f"Requested by {interaction.user.name} • Use /chat for more advanced options")
                
                await safe_followup(interaction, "", file=None, ephemeral=False)
                await interaction.channel.send(embed=embed)
            
            elif action == "search":
                # Implement other actions
                await safe_followup(interaction, "Search functionality not implemented yet.")
                
            else:
                await safe_followup(interaction, f"Action '{action}' not implemented yet.")
                
        except Exception as e:
            logger.error(f"Error in unified_chat_command: {str(e)}")
            await safe_followup(interaction, f"Error: {str(e)}")

    @bot.tree.command(name="help", description="Show help information for commands")
    async def help_command(interaction):
        """Show help information for commands"""
        if not await safe_defer(interaction):
            return
            
        try:
            help_text = """
**Ollama Scanner Discord Bot Help**

The following commands are available:

**/unified_search** - Search for models with various filters
• **search_type**: Choose from "Model Name", "Parameter Size", "All Models", or "Models with Servers"
• **query**: Search term (required for name and param searches)
• **sort_by**: Sort results by Name, Parameters, Quantization, or Count
• **descending**: Sort in descending (true) or ascending (false) order
• **limit**: Maximum number of results to return
• **show_endpoints**: Whether to show server endpoints for each model

**/server** - Unified server management command
• **action**: Choose from "List All Servers", "Check Server Models", "Sync Server Models", "Server Details", "Verify All Servers", or "Purge Unreachable Servers"
• **ip**: Server IP address (required for some actions)
• **port**: Server port (required for some actions)
• **sort_by**: Sort results by ID, IP, Scan Date, or Model Count

**/admin** - Administrative commands (admin only)
• **action**: Choose from "Refresh Commands", "Sync to Guild", "Full Refresh", "Clean Database", "Update All Models"
• **scope**: Choose between "Global" and "Current Guild"

**/model** - Model management command
• **action**: Choose from "List All Models", "Select Model", "Add Model", "Delete Model", "Current Default", "Search Models"
• **model_id**: Model ID for select/delete actions
• **search_term**: Search term for searching models by name
• **param_size**: Parameter size filter (e.g. 7B, 13B)
• **quant_level**: Quantization level filter (e.g. Q4_0, Q5_K_M)

**/chat** - Chat with your selected model
• **prompt**: Your message to the model
• **system_prompt**: Optional system prompt to set context
• **temperature**: Controls randomness (0.0 to 1.0)
• **max_tokens**: Maximum number of tokens in response
• **model_id**: Optional specific model ID to use instead of your default

**/quickprompt** - Search, select and interact with a model in one command
• **search_term**: Part of the model name to search for
• **prompt**: Your message to send to the model
• **system_prompt**: Optional system prompt to set context
• **temperature**: Controls randomness (0.0 to 1.0)
• **max_tokens**: Maximum number of tokens in response
• **param_size**: Optional parameter size filter (e.g. 7B, 13B)
• **quant_level**: Optional quantization level filter (e.g. Q4_0, Q5_K_M)
• **save_as_default**: Whether to save this model as your default

**/history** - View your chat history
• **limit**: Maximum number of chat entries to display (default: 5)
• **model_id**: Filter history by a specific model ID
• **search_term**: Search for specific text in your chat history

**/ping** - Check if the bot is responding

**/resync** - Force a resync of all slash commands
• **scope**: Sync scope: 'guild' for current server only, 'global' for all servers

**COMMAND USAGE TIPS:**
• For quick use, try `/quickprompt` to search, select, and chat with a model in one command
• Set a default model with `/model select <model_id>` or use `/quickprompt` with `save_as_default: true`
• Once you have a default model set, simply use `/chat <prompt>` for subsequent interactions
• Use `/history` to view your previous conversations

For any questions or issues, please contact the bot administrator.
"""
            await safe_followup(interaction, help_text)
        except Exception as e:
            logger.error(f"Error in help_command: {str(e)}")
            await safe_followup(interaction, f"Error displaying help: {str(e)}")

    @bot.tree.command(name="history", description="View your chat history")
    @app_commands.describe(
        limit="Maximum number of chat entries to display",
        model_id="Filter history by a specific model ID",
        search_term="Search for specific text in your chat history"
    )
    async def chat_history(
        interaction,
        limit: int = 5,
        model_id: int = None,
        search_term: str = None
    ):
        """
        View your chat history
        
        Args:
            interaction: Discord interaction
            limit: Maximum number of chat entries to display
            model_id: Filter history by a specific model ID
            search_term: Search for specific text in your chat history
        """
        if not await safe_defer(interaction):
            return
        
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
            # Build query based on filters
            query_parts = ["ch.user_id = %s"]
            query_params = [str(interaction.user.id)]
            
            if model_id:
                query_parts.append("ch.model_id = %s")
                query_params.append(model_id)
                
            if search_term:
                query_parts.append("(ch.prompt LIKE %s OR ch.response LIKE %s)")
                search = f"%{search_term}%"
                query_params.extend([search, search])
                
            # Cap the limit to a reasonable number
            if limit > 20:
                limit = 20
                
            # Build the final query
            query = f"""
                SELECT 
                    ch.id,
                    ch.model_id,
                    m.name,
                    ch.prompt,
                    ch.response,
                    ch.system_prompt,
                    ch.temperature,
                    ch.max_tokens,
                    ch.timestamp,
                    ch.eval_count,
                    ch.eval_duration
                FROM chat_history ch
                JOIN models m ON ch.model_id = m.id
                WHERE {" AND ".join(query_parts)}
                ORDER BY ch.timestamp DESC
                LIMIT %s
            """
            query_params.append(limit)
            
            results = Database.fetch_all(query, query_params)
            conn.close()
            
            if not results:
                filters = []
                if model_id:
                    filters.append(f"model_id:{model_id}")
                if search_term:
                    filters.append(f"text:'{search_term}'")
                    
                filter_text = " with " + ", ".join(filters) if filters else ""
                await safe_followup(interaction, f"No chat history found{filter_text}.")
                return
                
            # Format the results
            message = f"**Your Chat History** (showing {len(results)} of {limit} requested)\n\n"
            
            for result in results:
                chat_id, model_id, model_name, prompt, response, system_prompt, temp, max_tokens, timestamp, eval_count, eval_duration = result
                
                # Truncate long prompts and responses for display
                prompt_display = prompt[:100] + "..." if len(prompt) > 100 else prompt
                response_display = response[:200] + "..." if len(response) > 200 else response
                
                message += f"**ID: {chat_id} | {timestamp}**\n"
                message += f"**Model**: {model_name}\n"
                message += f"**Prompt**: {prompt_display}\n"
                message += f"**Response**: {response_display}\n"
                
                if system_prompt:
                    system_display = system_prompt[:50] + "..." if len(system_prompt) > 50 else system_prompt
                    message += f"**System**: {system_display}\n"
                    
                message += f"**Stats**: Temperature={temp}, Tokens={eval_count}, Time={eval_duration:.2f}s\n\n"
                message += "----------\n\n"
                
            await safe_followup(interaction, message)
            
        except Exception as e:
            logger.error(f"Error in chat_history: {str(e)}")
            await safe_followup(interaction, f"Error retrieving chat history: {str(e)}")

    @bot.tree.command(name="resync", description="Force a resync of all slash commands")
    @app_commands.describe(
        scope="Sync scope: 'guild' for current server only, 'global' for all servers"
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="Current Guild", value="guild"),
        app_commands.Choice(name="Global", value="global")
    ])
    async def resync_commands(
        interaction,
        scope: str = "guild"
    ):
        """
        Force a resync of all slash commands
        
        Args:
            interaction: Discord interaction
            scope: Scope of the sync (guild or global)
        """
        # Check if user has admin rights
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator privileges to use this command.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        
        try:
            if scope == "guild":
                # Sync to current guild
                await bot.tree.sync(guild=interaction.guild)
                await interaction.followup.send(f"Successfully resynced commands to this guild.", ephemeral=True)
            else:
                # Global sync
                await bot.tree.sync()
                await interaction.followup.send(f"Successfully resynced commands globally. This may take up to an hour to propagate to all servers.", ephemeral=True)
                
            logger.info(f"Commands resynced by {interaction.user.name} with scope: {scope}")
            
        except Exception as e:
            logger.error(f"Error in resync_commands: {str(e)}")
            await interaction.followup.send(f"Error resyncing commands: {str(e)}", ephemeral=True)

def setup(bot):
    """Setup function to add the cog to the bot.
    
    Args:
        bot: The Discord bot instance
    """
    # These parameters would be passed from discord_bot.py when loading the cog
    # TODO: Replace SQLite-specific code: DB_FILE = os.getenv("DB_FILE", "ollama_models.db")
    session = bot.session if hasattr(bot, "session") else None
    logger = logging.getLogger("discord_bot")
    
    # Return the commands for registration
    return [
        unified_search,
        unified_server,
        unified_admin,
        unified_model,
        chat,
        quickprompt,
        chat_history,
        help_command,
        resync_commands
    ]

if __name__ == "__main__":
    # This file is meant to be imported, not run directly
    print("This file should be imported from discord_bot.py")