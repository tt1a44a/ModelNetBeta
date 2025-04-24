"""
This file contains commands that need to be synced with Discord.
Import this file in discord_bot.py to ensure all commands are properly registered.
"""

import discord
from discord import app_commands
import sqlite3
import asyncio
import aiohttp
import logging
import random
from datetime import datetime

# Added by migration script
from database import Database, init_database

# This function will be called by discord_bot.py to register the commands
def register_additional_commands(bot, DB_FILE, safe_defer, safe_followup, session, check_server_connectivity, logger):
    @bot.tree.command(name="quickprompt", description="Search, select and interact with a model in one command")
    @app_commands.describe(
        search_term="Part of the model name to search for",
        prompt="Your prompt/message to send to the model",
        system_prompt="Optional system prompt to set context",
        temperature="Controls randomness (0.0 to 1.0)",
        max_tokens="Maximum number of tokens in response",
        param_size="Optional parameter size filter (e.g. 7B, 13B)"
    )
    async def quick_prompt(
        interaction: discord.Interaction,
        search_term: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        param_size: str = ""
    ):
        if not await safe_defer(interaction):
            return
        
        try:
            # First, search for models matching the search term
            conn = Database()
            
            # Build the base query with proper JOIN and WHERE clauses
            base_query = """
                SELECT 
                    m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port, s.scan_date
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                JOIN verified_endpoints ve ON e.id = ve.endpoint_id
                LEFT JOIN servers s ON e.id = s.id
                WHERE e.verified = 1
            """
            
            conditions = []
            params = []
            
            # Add model name filter
            if search_term:
                conditions.append("LOWER(m.name) LIKE LOWER(?)")
                params.append(f"%{search_term}%")
            
            # Add parameter size filter if provided
            if param_size:
                conditions.append("LOWER(m.parameter_size) LIKE LOWER(?)")
                params.append(f"%{param_size}%")
            
            # Add conditions to query if any
            if conditions:
                base_query += " AND " + " AND ".join(conditions)
            
            # Add ORDER BY and LIMIT
            base_query += """
                ORDER BY s.scan_date DESC, m.name ASC
                LIMIT 10
            """
            
            # Execute the query
            results = Database.fetch_all(base_query, params)
            conn.close()
            
            if not results:
                param_msg = f" with parameter size '{param_size}'" if param_size else ""
                await safe_followup(interaction, f"No models found matching '{search_term}'{param_msg}")
                return
            
            # Randomly select up to 5 results to try
            random.shuffle(results)
            
            # Initialize variables for selected model
            selected_model = None
            
            # Try servers until we find a reachable one
            for result in results:
                # Safely handle result unpacking
                if len(result) < 7:
                    logger.warning(f"Unexpected result format: {result}")
                    continue
                
                model_id, name, param_size_info, quant_level, ip, port, scan_date = result
                
                # Check server connectivity
                is_reachable, error = await check_server_connectivity(ip, port)
                if is_reachable:
                    selected_model = result
                    break
                
            if not selected_model:
                await safe_followup(interaction, f"No reachable servers found for models matching '{search_term}'")
                return
            
            # Safely unpack the selected model
            model_id, name, param_size_info, quant_level, ip, port, scan_date = selected_model
            
            # Build the request based on provided parameters
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
            
            # Show user what we're doing
            model_desc = f"{name}"
            if param_size_info:
                model_desc += f" ({param_size_info}"
                if quant_level:
                    model_desc += f", {quant_level}"
                model_desc += ")"
            
            await safe_followup(interaction, f"**Using model: {model_desc}**\nSending prompt to {ip}:{port}...")
            
            try:
                # Use aiohttp instead of requests for async operation
                async with session.post(
                    f"http://{ip}:{port}/api/generate", 
                    json=request_data, 
                    timeout=60  # Increased timeout for longer responses
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("response", "No response received.")
                        
                        # Get some stats if available
                        eval_count = result.get("eval_count", 0)
                        eval_duration = result.get("eval_duration", 0)
                        
                        # Add some stats to the response
                        stats = f"\n\n---\nTokens: {eval_count} | Time: {eval_duration/1000000:.2f}s"
                        if eval_duration > 0 and eval_count > 0:
                            tokens_per_second = eval_count / (eval_duration / 1000000000)
                            stats += f" | Throughput: {tokens_per_second:.2f} tokens/sec"
                        
                        # Only add stats for longer responses
                        if len(response_text) > 10:
                            response_text += stats
                        
                        # Format the response with bold header but keep the model's output as is
                        formatted_response = f"**Response from {name}:**\n{response_text}"
                            
                        await safe_followup(interaction, formatted_response)
                        
                        # Store in chat history if available
                        try:
                            history_query = """
                                INSERT INTO chat_history 
                                (user_id, model_id, prompt, system_prompt, response, temperature, max_tokens, eval_count, eval_duration)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """
                            history_params = (
                                str(interaction.user.id),
                                model_id,
                                prompt,
                                system_prompt,
                                response_text,
                                temperature,
                                max_tokens,
                                eval_count,
                                eval_duration/1000000  # Convert to seconds
                            )
                            Database.execute(history_query, history_params)
                        except Exception as e:
                            logger.error(f"Error saving chat history: {str(e)}")
                    else:
                        response_text = await response.text()
                        await safe_followup(interaction, f"Error: {response.status} - {response_text}")
            except asyncio.TimeoutError:
                await safe_followup(interaction, "Request timed out. The model may be taking too long to respond.")
            except aiohttp.ClientError as e:
                logger.error(f"Connection error in quick_prompt: {str(e)}")
                await safe_followup(interaction, f"Request failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in quick_prompt: {str(e)}")
            await safe_followup(interaction, f"Error: {str(e)}")
    
    @bot.tree.command(name="updateallmodels", description="Update model list from all API endpoints in the database")
    async def update_all_models(interaction: discord.Interaction):
        """Updates all models from every server in the database, including latest scanner discoveries"""
        if not await safe_defer(interaction):
            return
        
        try:
            # First check if there are any newly scanned servers that need processing
            await safe_followup(interaction, "🔍 Checking for newly scanned servers and refreshing database...")
            
            # Connect to database
            conn = Database()
            # Using Database methods instead of cursor
            
            # Get last sync time from a metadata table, or create it if it doesn't exist
            try:
                query = "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
                Database.execute(query)
                
                query = "SELECT value FROM metadata WHERE key = 'last_scanner_sync'"
                result = Database.fetch_one(query)
                last_sync_time = result[0] if result else "1970-01-01 00:00:00"  # Default to epoch if no value
            except:
                last_sync_time = "1970-01-01 00:00:00"  # Default to epoch if error
                
            # Query for recently scanned servers (servers added or updated since last sync)
            query = """
                SELECT COUNT(*) FROM servers 
                WHERE scan_date > ?
            """
            params = (last_sync_time,)
            
            new_server_count = Database.fetch_one(query, params)[0]
            
            # Update the last sync time to now
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query = "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)"
            params = ("last_scanner_sync", current_time)
            Database.execute(query, params)
            # Commit handled by Database methods
            
            # Report on new servers found
            if new_server_count > 0:
                await safe_followup(interaction, f"📊 Found {new_server_count} newly scanned servers since last update.")
            else:
                await safe_followup(interaction, "📊 No new servers found since last update.")
            
            # Get all servers from the database
            query = "SELECT id, ip, port FROM servers ORDER BY scan_date DESC"
            servers = Database.fetch_all(query)
            conn.close()
            
            if not servers:
                await safe_followup(interaction, "No servers found in the database.")
                return
            
            # Status counters
            total_servers = len(servers)
            success_count = 0
            failed_count = 0
            added_models = []
            updated_models = []
            deleted_models = []
            unreachable_servers = []
            
            # Progress message
            progress_msg = await safe_followup(interaction, f"🔄 Starting update of models from {total_servers} servers...")
            
            # Process each server
            for server_id, ip, port in servers:
                try:
                    # Update progress every few servers
                    if success_count % 5 == 0 or failed_count % 5 == 0:
                        await safe_followup(interaction, 
                                        f"⏳ Progress: {success_count + failed_count}/{total_servers} servers processed " +
                                        f"({success_count} successful, {failed_count} failed)")
                    
                    # Check connectivity first
                    is_reachable, error = await check_server_connectivity(ip, port)
                    if not is_reachable:
                        failed_count += 1
                        unreachable_servers.append(f"{ip}:{port} - {error}")
                        continue
                    
                    # Make API call to get models
                    logger.info(f"Fetching models from server: {ip}:{port}")
                    async with session.get(f"http://{ip}:{port}/api/tags", timeout=10) as response:
                        if response.status != 200:
                            failed_count += 1
                            logger.error(f"Failed to get models from {ip}:{port} - Status: {response.status}")
                            continue
                        
                        server_models = await response.json()
                        models_list = server_models.get("models", [])
                    
                    # Get existing models for this server
                    conn = Database()
                    # Using Database methods instead of cursor
                    query = "SELECT id, name FROM models WHERE endpoint_id = ?"
                    params = (server_id,)
                    result = Database.fetch_all(query, params)
                    existing_models = {row[1]: row[0] for row in result}
                    
                    # Track models found on server
                    found_models = set()
                    
                    # Process models from server
                    for model in models_list:
                        name = model.get("name", "")
                        if not name:
                            continue
                        
                        found_models.add(name)
                        
                        # Extract model details
                        model_size_mb = model.get("size", 0) / (1024 * 1024)  # Convert to MB
                        
                        parameter_size = ""
                        quantization_level = ""
                        
                        # Get detailed info if available
                        if "details" in model:
                            parameter_size = model["details"].get("parameter_size", "")
                            quantization_level = model["details"].get("quantization_level", "")
                        
                        # Check if model exists in database
                        if name in existing_models:
                            # Update model details
                            query = """
                                UPDATE models SET 
                                parameter_size = ?, 
                                quantization_level = ?, 
                                size_mb = ?
                                WHERE id = ?
                            """
                            params = (parameter_size, quantization_level, model_size_mb, existing_models[name])
                            Database.execute(query, params)
                            
                            # Since we can't access rowcount directly with our Database abstraction
                            updated_models.append(f"{name} on {ip}:{port}")
                        else:
                            # Add new model
                            query = """
                                INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                                VALUES (?, ?, ?, ?, ?)
                            """
                            params = (server_id, name, parameter_size, quantization_level, model_size_mb)
                            Database.execute(query, params)
                            
                            added_models.append(f"{name} on {ip}:{port}")
                    
                    # Remove models that are no longer on the server
                    for db_name, model_id in existing_models.items():
                        if db_name not in found_models:
                            query = "DELETE FROM models WHERE id = ?"
                            params = (model_id,)
                            Database.execute(query, params)
                            deleted_models.append(f"{db_name} on {ip}:{port}")
                    
                    # Update server scan date
                    query = "UPDATE servers SET scan_date = ? WHERE id = ?"
                    params = (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), server_id)
                    Database.execute(query, params)
                    
                    # Commit handled by Database methods
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Error syncing models for server {ip}:{port}: {str(e)}")
                    failed_count += 1
                finally:
                    if conn:
                        conn.close()
            
            # Prepare final report
            summary = []
            summary.append(f"**📋 Model Update Summary:**")
            summary.append(f"- 🔄 Servers processed: {success_count + failed_count}/{total_servers}")
            summary.append(f"- ✅ Successful servers: {success_count}")
            summary.append(f"- ❌ Failed servers: {failed_count}")
            
            if added_models:
                models_to_show = min(10, len(added_models))
                summary.append(f"- ➕ Added {len(added_models)} new models" + 
                               (f" (showing first {models_to_show})" if len(added_models) > models_to_show else ""))
                for i in range(models_to_show):
                    summary.append(f"  - {added_models[i]}")
            
            if updated_models:
                models_to_show = min(10, len(updated_models))
                summary.append(f"- 🔄 Updated {len(updated_models)} existing models" + 
                               (f" (showing first {models_to_show})" if len(updated_models) > models_to_show else ""))
                for i in range(models_to_show):
                    summary.append(f"  - {updated_models[i]}")
            
            if deleted_models:
                models_to_show = min(10, len(deleted_models))
                summary.append(f"- 🗑️ Removed {len(deleted_models)} non-existent models" + 
                               (f" (showing first {models_to_show})" if len(deleted_models) > models_to_show else ""))
                for i in range(models_to_show):
                    summary.append(f"  - {deleted_models[i]}")
            
            if unreachable_servers:
                servers_to_show = min(10, len(unreachable_servers))
                summary.append(f"- 🔌 {len(unreachable_servers)} unreachable servers" + 
                               (f" (showing first {servers_to_show})" if len(unreachable_servers) > servers_to_show else ""))
                for i in range(servers_to_show):
                    summary.append(f"  - {unreachable_servers[i]}")
            
            # Send final report
            await safe_followup(interaction, "\n".join(summary))
            
        except Exception as e:
            logger.error(f"Error in update_all_models: {str(e)}")
            await safe_followup(interaction, f"❌ Error occurred during update: {str(e)}")
    
    logger.info("Additional commands registered from commands_for_syncing.py")
    return [quick_prompt, update_all_models]  # Return all commands for registration 