#!/usr/bin/env python3
"""
Consolidated Discord Bot Commands

This module implements the consolidated commands according to the plan,
reducing the 20+ commands to 8 consolidated commands (5 user, 3 admin).
"""

import discord
from discord import app_commands
import logging
import json
import asyncio
import aiohttp
from datetime import datetime, timezone
import os
from typing import Optional, List, Dict, Any, Union, Tuple

# Database access
from database import Database, get_db_boolean

# Try different import strategies for utils
try:
    # Try direct import first
    from utils import format_embed_message, safe_defer, safe_followup, truncate_string
except ImportError:
    try:
        # Try relative import
        from .utils import format_embed_message, safe_defer, safe_followup, truncate_string
    except ImportError:
        # Try absolute import with full path
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from utils import format_embed_message, safe_defer, safe_followup, truncate_string

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("discord_bot.log")
    ]
)
logger = logging.getLogger('consolidated_commands')

# Create specialized loggers
honeypot_logger = logging.getLogger('honeypot')
security_logger = logging.getLogger('security')

# Function to register the consolidated commands
def register_consolidated_commands(bot, safe_defer, safe_followup):
    """
    Register the consolidated commands with the bot.
    
    Args:
        bot: The Discord bot instance
        safe_defer: Function for safely deferring interactions
        safe_followup: Function for safely following up on interactions
    
    Returns:
        dict: A mapping of command names to command functions
    """
    
    # Dictionary to store our registered commands
    registered_commands = {}
    
    # Function to get database statistics
    def get_database_stats():
        """Get comprehensive statistics from the database"""
        try:
            # Get endpoint count
            query = "SELECT COUNT(*) FROM endpoints"
            endpoint_count = Database.fetch_one(query)[0]
            
            # Get total model count
            query = "SELECT COUNT(*) FROM models"
            total_models = Database.fetch_one(query)[0]
            
            # Get unique model count
            query = "SELECT COUNT(DISTINCT name) FROM models"
            unique_models = Database.fetch_one(query)[0]
            
            # Get parameter size distribution
            query = "SELECT parameter_size, COUNT(*) FROM models WHERE parameter_size IS NOT NULL GROUP BY parameter_size ORDER BY COUNT(*) DESC"
            param_counts = Database.fetch_all(query)
            
            # Get quantization level distribution
            query = "SELECT quantization_level, COUNT(*) FROM models WHERE quantization_level IS NOT NULL GROUP BY quantization_level ORDER BY COUNT(*) DESC"
            quant_counts = Database.fetch_all(query)
            
            # Get top models
            query = "SELECT name, COUNT(*) FROM models GROUP BY name ORDER BY COUNT(*) DESC LIMIT 10"
            top_models = Database.fetch_all(query)
            
            return {
                "endpoint_count": endpoint_count,
                "total_models": total_models,
                "unique_models": unique_models,
                "parameter_sizes": param_counts,
                "quantization_levels": quant_counts,
                "top_models": top_models
            }
            
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return None
            
    @bot.tree.command(name="models", description="Search, filter, and view available Ollama models")
    @app_commands.describe(
        search="Optional: Search for models by name",
        size="Optional: Filter by parameter size (e.g. 7B, 13B)",
        quantization="Optional: Filter by quantization level (e.g. Q4_K_M)",
        action="Optional: Action to perform (list, search, details)",
        sort_by="Optional: Sort results by this field",
        descending="Optional: Sort in descending order",
        limit="Optional: Maximum number of results to return",
        show_endpoints="Optional: Show endpoint details for each model"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Models", value="list"),
        app_commands.Choice(name="Search Models", value="search"),
        app_commands.Choice(name="Model Details", value="details"),
        app_commands.Choice(name="Find Endpoints", value="endpoints")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Parameters", value="params"),
        app_commands.Choice(name="Quantization", value="quant"),
        app_commands.Choice(name="Count", value="count")
    ])
    async def models_command(
        interaction: discord.Interaction,
        action: str = "list",
        search: str = None,
        size: str = None,
        quantization: str = None,
        sort_by: str = None,
        descending: bool = True,
        limit: int = 25,
        show_endpoints: bool = False
    ):
        """Unified command for model discovery and information"""
        await safe_defer(interaction)
        
        try:
            # Handle different actions
            if action == "list":
                await handle_list_models(interaction, search, size, quantization, sort_by, descending, limit, show_endpoints)
            elif action == "search":
                await handle_search_models(interaction, search, sort_by, descending, limit, show_endpoints)
            elif action == "details":
                await handle_model_details(interaction, search)
            elif action == "endpoints":
                await handle_find_endpoints(interaction, search, size, quantization, limit, show_endpoints)
            else:
                # Default to list
                await handle_list_models(interaction, search, size, quantization, sort_by, descending, limit, show_endpoints)
                
        except Exception as e:
            logger.error(f"Error in models command: {e}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # Add to registered commands
    registered_commands["models"] = models_command
    
    async def handle_list_models(interaction, search, size, quantization, sort_by, descending, limit, show_endpoints):
        """Handler for listing models"""
        # Base query - using a WITH clause to handle the count separately
        query = """
            WITH model_counts AS (
                SELECT name, COUNT(*) as count 
                FROM models
                GROUP BY name
            )
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                   e.ip, e.port, m.size_mb, mc.count
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            JOIN model_counts mc ON m.name = mc.name
            WHERE 1=1
        """
        params = []
        
        # Add filters if provided
        if search:
            query += " AND m.name LIKE %s"
            params.append(f"%{search}%")
        
        if quantization:
            query += " AND m.quantization_level LIKE %s"
            params.append(f"%{quantization}%")
        
        if size:
            query += " AND m.parameter_size LIKE %s"
            params.append(f"%{size}%")
            
        # Add honeypot and verification filters to ensure safety
        query += f" AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}"
        query += f" AND e.is_honeypot = {get_db_boolean(False, as_string=True)}"
        query += f" AND e.is_active = {get_db_boolean(True, as_string=True)}"
        
        # Add GROUP BY to ensure distinct model-endpoint combinations
        query += " GROUP BY m.id, m.name, m.parameter_size, m.quantization_level, e.ip, e.port, m.size_mb, mc.count"
        
        # Add sorting
        if sort_by == "name":
            query += " ORDER BY m.name"
        elif sort_by == "params":
            query += " ORDER BY m.parameter_size"
        elif sort_by == "quant":
            query += " ORDER BY m.quantization_level"
        elif sort_by == "count":
            query += " ORDER BY mc.count"  # Use the count from the CTE
        else:
            query += " ORDER BY m.name"  # Default sort
            
        if not descending:
            query += " ASC"
        else:
            query += " DESC"
            
        # Add limit
        query += " LIMIT %s"
        params.append(limit)
        
        # Execute query
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            no_results_embed = await format_embed_message(
                title="No Models Found",
                description="No models were found matching your search criteria.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=no_results_embed)
            return
        
        # Format the results into an embed
        embed = await format_embed_message(
            title="Available Ollama Models",
            description=f"Found {len(results)} models matching your criteria",
            color=discord.Color.blue()
        )
        
        # Add model information to the embed
        for i, model in enumerate(results[:min(25, len(results))]):
            model_id, name, param_size, quant, ip, port, size_mb, count = model
            
            # Format model size if available
            size_str = f" ({size_mb:.2f} MB)" if size_mb else ""
            
            # Format model information
            model_info = f"**ID:** {model_id}\n"
            model_info += f"**Parameters:** {param_size or 'Unknown'}\n"
            model_info += f"**Quantization:** {quant or 'Unknown'}{size_str}\n"
            
            if show_endpoints:
                model_info += f"**Endpoint:** {ip}:{port}\n"
                
            if count > 1:
                model_info += f"**Available on:** {count} endpoint{'s' if count > 1 else ''}\n"
                
            embed.add_field(
                name=f"{i+1}. {name}",
                value=model_info,
                inline=True
            )
        
        # Add footer with usage instructions
        embed.set_footer(text="Use /models action:details search:model_name for more details on a specific model")
        
        # Send the response
        await interaction.followup.send(embed=embed)
    
    async def handle_search_models(interaction, search, sort_by, descending, limit, show_endpoints):
        """Handler for searching models by name"""
        if not search:
            error_embed = await format_embed_message(
                title="Search Term Required",
                description="Please provide a search term to find models.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=error_embed)
            return
            
        # This is essentially the same as list_models but with a search term enforced
        await handle_list_models(interaction, search, None, None, sort_by, descending, limit, show_endpoints)
    
    async def handle_model_details(interaction, model_identifier):
        """Handler for viewing detailed model information"""
        if not model_identifier:
            error_embed = await format_embed_message(
                title="Model Identifier Required",
                description="Please provide a model ID or name to view details.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=error_embed)
            return
            
        # Check if model_identifier is numeric (model ID) or text (model name)
        is_id = model_identifier.isdigit()
        
        if is_id:
            # Fetch by ID
            query = """
                SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                       e.ip, e.port, m.size_mb, e.verification_date, e.scan_date
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                WHERE m.id = %s
                AND e.verified = %s
                AND e.is_honeypot = %s
                AND e.is_active = %s
            """
            model = Database.fetch_one(query, (int(model_identifier), get_db_boolean(True, as_string=True, for_verified=True), 
                                              get_db_boolean(False, as_string=True), 
                                              get_db_boolean(True, as_string=True)))
        else:
            # Fetch by name (first match)
            query = """
                SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                       e.ip, e.port, m.size_mb, e.verification_date, e.scan_date
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                WHERE m.name LIKE %s
                AND e.verified = %s
                AND e.is_honeypot = %s
                AND e.is_active = %s
                LIMIT 1
            """
            model = Database.fetch_one(query, (f"%{model_identifier}%", get_db_boolean(True, as_string=True, for_verified=True), get_db_boolean(False, as_string=True), get_db_boolean(True, as_string=True)))
        
        if not model:
            await interaction.followup.send(embed=await format_embed_message(
                title="Model Not Found",
                description=f"Could not find a model matching '{model_identifier}'",
                color=discord.Color.orange()
            ))
            return
            
        # Unpack model information
        model_id, name, param_size, quant, ip, port, size_mb, verification_date, scan_date = model
        
        # Get the count of endpoints with this model
        query = """
            SELECT COUNT(*)
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.name = %s
            AND e.verified = %s
            AND e.is_honeypot = %s
            AND e.is_active = %s
        """
        count_result = Database.fetch_one(query, (name, get_db_boolean(True, as_string=True, for_verified=True), get_db_boolean(False, as_string=True), get_db_boolean(True, as_string=True)))
        endpoint_count = count_result[0] if count_result else 0
        
        # Create detailed embed for the model
        embed = await format_embed_message(
            title=f"Model Details: {name}",
            color=discord.Color.blue()
        )
        
        # Add fields with model details
        embed.add_field(name="Model ID", value=str(model_id), inline=True)
        embed.add_field(name="Parameter Size", value=param_size or "Unknown", inline=True)
        embed.add_field(name="Quantization", value=quant or "Unknown", inline=True)
        
        if size_mb:
            embed.add_field(name="Size", value=f"{size_mb:.2f} MB", inline=True)
            
        embed.add_field(name="Available On", value=f"{endpoint_count} endpoint{'s' if endpoint_count > 1 else ''}", inline=True)
        
        # Add current endpoint details
        endpoint_info = f"**IP:** {ip}\n**Port:** {port}\n"
        if verification_date:
            endpoint_info += f"**Verified:** {verification_date}\n"
        if scan_date:
            endpoint_info += f"**Scanned:** {scan_date}"
            
        embed.add_field(name="Current Endpoint", value=endpoint_info, inline=False)
        
        # Add usage instructions
        embed.add_field(
            name="Usage",
            value=f"To chat with this model, use:\n`/chat model:{model_id} prompt:\"Your message here\"`",
            inline=False
        )
        
        # Send the response
        await interaction.followup.send(embed=embed)
    
    async def handle_find_endpoints(interaction, model_name, param_size, quant_level, limit, show_endpoints):
        """Handler for finding endpoints with a specific model"""
        if not model_name:
            error_embed = await format_embed_message(
                title="Model Name Required",
                description="Please provide a model name to find endpoints.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=error_embed)
            return
        
        # Build query to find endpoints with the specified model
        query = """
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                   e.ip, e.port, e.verification_date, m.size_mb
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.name LIKE %s
            AND e.verified = %s
            AND e.is_honeypot = %s
            AND e.is_active = %s
        """
        params = [f"%{model_name}%", get_db_boolean(True, as_string=True, for_verified=True), get_db_boolean(False, as_string=True), get_db_boolean(True, as_string=True)]
        
        # Add optional filters
        if param_size:
            query += " AND m.parameter_size LIKE %s"
            params.append(f"%{param_size}%")
            
        if quant_level:
            query += " AND m.quantization_level LIKE %s"
            params.append(f"%{quant_level}%")
            
        # Add sort and limit
        query += " ORDER BY e.verification_date DESC LIMIT %s"
        params.append(limit)
        
        # Execute query
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            no_results_embed = await format_embed_message(
                title="No Endpoints Found",
                description=f"No endpoints found hosting model '{model_name}'",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=no_results_embed)
            return
        
        # Format the results into an embed
        embed = await format_embed_message(
            title=f"Endpoints Hosting '{model_name}'",
            description=f"Found {len(results)} endpoint{'s' if len(results) > 1 else ''} hosting this model",
            color=discord.Color.blue()
        )
        
        # Add endpoint information to the embed
        for i, endpoint in enumerate(results):
            model_id, name, param_size, quant, ip, port, verification_date, size_mb = endpoint
            
            # Format model size if available
            size_str = f" ({size_mb:.2f} MB)" if size_mb else ""
            
            # Format endpoint information
            endpoint_info = f"**Model ID:** {model_id}\n"
            endpoint_info += f"**Parameters:** {param_size or 'Unknown'}\n"
            endpoint_info += f"**Quantization:** {quant or 'Unknown'}{size_str}\n"
            endpoint_info += f"**Endpoint:** {ip}:{port}\n"
            
            if verification_date:
                endpoint_info += f"**Verified:** {verification_date}\n"
                
            embed.add_field(
                name=f"{i+1}. {name}",
                value=endpoint_info,
                inline=True
            )
        
        # Add footer with usage instructions
        embed.set_footer(text="Use /chat model:<model_id> to chat with a specific model instance")
        
        # Send the response
        await interaction.followup.send(embed=embed)

    #
    # 1.2. /chat Command Implementation
    #
    @bot.tree.command(name="chat", description="Chat with any Ollama model")
    @app_commands.describe(
        model="Model ID or name to chat with",
        prompt="Your message to the model",
        system_prompt="Optional system prompt to guide the model",
        temperature="Controls randomness (0.0 to 1.0)",
        max_tokens="Maximum tokens in the response",
        save_history="Save this chat in your history",
        verbose="Show detailed API information"
    )
    async def chat_command(
        interaction: discord.Interaction,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        save_history: bool = True,
        verbose: bool = False
    ):
        """Unified command for chatting with models"""
        await safe_defer(interaction)
        
        try:
            # Determine if model is ID or name
            model_id = None
            model_name = None
            endpoint_ip = None
            endpoint_port = None
            
            if model.isdigit():
                # Model is an ID
                model_id = int(model)
                
                # Get model info from database
                query = """
                    SELECT m.id, m.name, e.ip, e.port
                    FROM models m
                    JOIN endpoints e ON m.endpoint_id = e.id
                    WHERE m.id = %s
                    AND e.verified = %s
                    AND e.is_honeypot = %s
                    AND e.is_active = %s
                """
                result = Database.fetch_one(query, (model_id, get_db_boolean(True, as_string=True, for_verified=True), 
                                                   get_db_boolean(False, as_string=True), 
                                                   get_db_boolean(True, as_string=True)))
                
                if not result:
                    error_embed = await format_embed_message(
                        title="🚫 Model Not Found",
                        description=f"Could not find model with ID {model_id}",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=error_embed)
                    return
                
                # Extract model info
                model_id, model_name, endpoint_ip, endpoint_port = result
                
            else:
                # Model is a name, find an available endpoint
                query = """
                    SELECT m.id, m.name, e.ip, e.port
                    FROM models m
                    JOIN endpoints e ON m.endpoint_id = e.id
                    WHERE m.name LIKE %s
                    AND e.verified = %s
                    AND e.is_honeypot = %s
                    AND e.is_active = %s
                    ORDER BY e.verification_date DESC
                    LIMIT 1
                """
                result = Database.fetch_one(query, (f"%{model}%", get_db_boolean(True, as_string=True, for_verified=True), 
                                                   get_db_boolean(False, as_string=True), 
                                                   get_db_boolean(True, as_string=True)))
                
                if not result:
                    error_embed = await format_embed_message(
                        title="🚫 Model Not Found",
                        description=f"Could not find an available endpoint for model '{model}'",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=error_embed)
                    return
                    
                model_id, model_name, endpoint_ip, endpoint_port = result
            
            # Log the chat attempt
            security_logger.info(f"Chat attempt with model ID {model_id} from user {interaction.user.id} ({interaction.user.name})")
            
            # Now send the chat request to the endpoint
            api_url = f"http://{endpoint_ip}:{endpoint_port}/api/chat"
            
            chat_request = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt} if system_prompt else None,
                    {"role": "user", "content": prompt}
                ],
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                },
                "stream": False
            }
            
            # Remove None messages
            chat_request["messages"] = [msg for msg in chat_request["messages"] if msg]
            
            # If verbose mode is enabled, show the request details
            if verbose:
                request_embed = await format_embed_message(
                    title="API Request Details",
                    description="```json\n" + json.dumps(chat_request, indent=2) + "\n```",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=request_embed)
            
            # Create a session for the request
            async with aiohttp.ClientSession() as session:
                try:
                    # Start timing the request
                    start_time = asyncio.get_event_loop().time()
                    
                    # Set a timeout for the request to prevent hanging
                    timeout = aiohttp.ClientTimeout(total=60)  # 60 second timeout
                    
                    async with session.post(api_url, json=chat_request, timeout=timeout) as response:
                        # Calculate time taken
                        end_time = asyncio.get_event_loop().time()
                        duration = end_time - start_time
                        
                        if response.status != 200:
                            error_text = await response.text()
                            error_embed = await format_embed_message(
                                title="❌ API Error",
                                description=f"The API returned status code {response.status}:\n```\n{error_text}\n```",
                                color=discord.Color.red()
                            )
                            await interaction.followup.send(embed=error_embed)
                            return
                        
                        # Parse the response
                        chat_response = await response.json()
                        
                        # Extract response text
                        model_response = chat_response.get('message', {}).get('content', '')
                        
                        # Get token metrics if available
                        eval_count = chat_response.get('eval_count', 0)
                        eval_duration = chat_response.get('eval_duration', 0)
                        
                        # Save to history if requested
                        if save_history:
                            # Create table if it doesn't exist
                            Database.execute("""
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
                            """)
                            
                            # Save the chat to the history
                            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            Database.execute("""
                                INSERT INTO chat_history 
                                (user_id, model_id, prompt, system_prompt, response, temperature, max_tokens, timestamp, eval_count, eval_duration)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                str(interaction.user.id), model_id, prompt, system_prompt, model_response, 
                                temperature, max_tokens, now, eval_count, eval_duration
                            ))
                        
                        # Format the response as an embed
                        description = f"**Your prompt:** {prompt}\n\n**Response:**\n{model_response}"
                        
                        # If the description is too long, truncate it and create multiple embeds
                        if len(description) > 4000:
                            # Send the prompt in one embed
                            prompt_embed = await format_embed_message(
                                title=f"Chat with {model_name}",
                                description=f"**Your prompt:** {prompt}",
                                color=discord.Color.blue()
                            )
                            await interaction.followup.send(embed=prompt_embed)
                            
                            # Send the response in another embed (or multiple if needed)
                            chunks = [model_response[i:i+4000] for i in range(0, len(model_response), 4000)]
                            for i, chunk in enumerate(chunks):
                                response_embed = await format_embed_message(
                                    title=f"Response from {model_name} (Part {i+1}/{len(chunks)})",
                                    description=chunk,
                                    color=discord.Color.blue()
                                )
                                
                                # Only add footer to the last chunk
                                if i == len(chunks) - 1:
                                    response_embed.set_footer(text=f"Generated in {duration:.2f}s • {eval_count} tokens")
                                
                                await interaction.followup.send(embed=response_embed)
                        else:
                            # Send a single embed
                            response_embed = await format_embed_message(
                                title=f"Chat with {model_name}",
                                description=description,
                                color=discord.Color.blue()
                            )
                            response_embed.set_footer(text=f"Generated in {duration:.2f}s • {eval_count} tokens")
                            await interaction.followup.send(embed=response_embed)
                        
                        # If verbose, send additional details
                        if verbose:
                            details_embed = await format_embed_message(
                                title="API Response Details",
                                description="```json\n" + json.dumps(chat_response, indent=2) + "\n```",
                                color=discord.Color.blue()
                            )
                            await interaction.followup.send(embed=details_embed, ephemeral=True)
                        
                except asyncio.TimeoutError:
                    timeout_embed = await format_embed_message(
                        title="⏱️ Request Timeout",
                        description="The request to the Ollama API timed out. This might be due to high server load or a very complex prompt.",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=timeout_embed)
                
                except Exception as e:
                    logger.error(f"Error in chat with {model_name} on {endpoint_ip}:{endpoint_port} - {str(e)}")
                    error_embed = await format_embed_message(
                        title="❌ Error",
                        description=f"An error occurred while communicating with the model: ```\n{str(e)}\n```",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=error_embed)
                    
        except Exception as e:
            logger.error(f"Error in chat command: {str(e)}")
            error_embed = await format_embed_message(
                title="❌ Error",
                description=f"An error occurred: ```\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed) 

    # Add to registered commands 
    registered_commands["chat"] = chat_command
    
    @bot.tree.command(name="server", description="View and manage Ollama servers")
    @app_commands.describe(
        action="Action to perform",
        ip="Server IP address (for specific server actions)",
        port="Server port (default: 11434)",
        sort_by="Field to sort results by",
        limit="Maximum number of results to return"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Servers", value="list"),
        app_commands.Choice(name="Server Details", value="details"),
        app_commands.Choice(name="Check Models", value="check"),
        app_commands.Choice(name="Verify Connectivity", value="verify")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="IP Address", value="ip"),
        app_commands.Choice(name="Last Verified", value="date"),
        app_commands.Choice(name="Model Count", value="count")
    ])
    async def server_command(
        interaction: discord.Interaction,
        action: str,
        ip: str = None,
        port: int = 11434,
        sort_by: str = None,
        limit: int = 25
    ):
        """Unified command for server management"""
        await safe_defer(interaction)
        
        try:
            if action == "list":
                await handle_list_servers(interaction, sort_by, limit)
            elif action == "details":
                if not ip:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Server IP Required",
                        description="Please provide a server IP address to view details.",
                        color=discord.Color.orange()
                    ))
                    return
                await handle_server_details(interaction, ip, port)
            elif action == "check":
                if not ip:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Server IP Required",
                        description="Please provide a server IP address to check models.",
                        color=discord.Color.orange()
                    ))
                    return
                await handle_check_server(interaction, ip, port)
            elif action == "verify":
                if not ip:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Server IP Required",
                        description="Please provide a server IP address to verify connectivity.",
                        color=discord.Color.orange()
                    ))
                    return
                await handle_verify_server(interaction, ip, port)
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Unknown Action",
                    description="The specified action is not recognized.",
                    color=discord.Color.red()
                ))
        
        except Exception as e:
            logger.error(f"Error in server command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    async def handle_list_servers(interaction, sort_by, limit):
        """Handler for listing servers"""
        # Build query based on sort and limit parameters
        query = """
            SELECT e.id, e.ip, e.port, e.verification_date, e.scan_date, 
                   COUNT(m.id) as model_count
            FROM endpoints e
            LEFT JOIN models m ON e.id = m.endpoint_id
            WHERE e.is_honeypot = %s
            AND e.is_active = %s
            GROUP BY e.id, e.ip, e.port, e.verification_date, e.scan_date
        """
        params = [get_db_boolean(False), get_db_boolean(True)]
        
        # Add sorting
        if sort_by == "ip":
            query += " ORDER BY e.ip"
        elif sort_by == "date":
            query += " ORDER BY e.verification_date DESC NULLS LAST"
        elif sort_by == "count":
            query += " ORDER BY model_count DESC"
        else:
            query += " ORDER BY e.verification_date DESC NULLS LAST"  # Default sort
        
        # Add limit
        query += " LIMIT %s"
        params.append(limit)
        
        # Execute query
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            no_results_embed = await format_embed_message(
                title="No Servers Found",
                description="No active servers were found in the database.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=no_results_embed)
            return
        
        # Format the results into an embed
        embed = await format_embed_message(
            title="Available Ollama Servers",
            description=f"Found {len(results)} active servers",
            color=discord.Color.blue()
        )
        
        # Add server information to the embed
        for i, server in enumerate(results):
            server_id, ip, port, verification_date, scan_date, model_count = server
            
            # Format server information
            server_info = f"**ID:** {server_id}\n"
            server_info += f"**Port:** {port}\n"
            server_info += f"**Models:** {model_count}\n"
            
            if verification_date:
                server_info += f"**Verified:** {verification_date}\n"
                
            if scan_date:
                server_info += f"**Scanned:** {scan_date}\n"
                
            embed.add_field(
                name=f"{i+1}. {ip}",
                value=server_info,
                inline=True
            )
        
        # Add footer with usage instructions
        embed.set_footer(text="Use /server action:details ip:<ip> for more info on a specific server")
        
        # Send the response
        await interaction.followup.send(embed=embed)
    
    async def handle_server_details(interaction, ip, port):
        """Handler for showing detailed server information"""
        # Get server info
        query = """
            SELECT e.id, e.ip, e.port, e.verification_date, e.scan_date, 
                   e.verified, e.is_active, e.inactive_reason
            FROM endpoints e
            WHERE e.ip = %s
            AND (e.port = %s OR %s IS NULL)
            AND e.is_honeypot = %s
            LIMIT 1
        """
        server = Database.fetch_one(query, (ip, port, port, get_db_boolean(False)))
        
        if not server:
            not_found_embed = await format_embed_message(
                title="Server Not Found",
                description=f"Could not find server with IP {ip}" + (f" and port {port}" if port else ""),
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=not_found_embed)
            return
            
        # Get models on this server
        query = """
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, m.size_mb
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.ip = %s
            AND e.port = %s
            ORDER BY m.name
        """
        models = Database.fetch_all(query, (ip, port))
        
        # Unpack server info
        server_id, server_ip, server_port, verification_date, scan_date, verified, is_active, inactive_reason = server
        
        # Create detailed embed for the server
        embed = await format_embed_message(
            title=f"Server Details: {server_ip}:{server_port}",
            color=discord.Color.blue()
        )
        
        # Add fields with server details
        embed.add_field(name="Server ID", value=str(server_id), inline=True)
        embed.add_field(name="IP Address", value=server_ip, inline=True)
        embed.add_field(name="Port", value=str(server_port), inline=True)
        
        # Status information
        status_info = ""
        if verified:
            status_info += "✅ Verified\n"
        else:
            status_info += "❌ Not Verified\n"
            
        if is_active:
            status_info += "🟢 Active"
        else:
            status_info += f"🔴 Inactive\nReason: {inactive_reason or 'Unknown'}"
            
        embed.add_field(name="Status", value=status_info, inline=False)
        
        # Dates
        dates_info = ""
        if verification_date:
            dates_info += f"**Last Verified:** {verification_date}\n"
        if scan_date:
            dates_info += f"**Last Scanned:** {scan_date}"
            
        if dates_info:
            embed.add_field(name="Dates", value=dates_info, inline=False)
        
        # Add models information
        if models:
            models_info = f"This server has {len(models)} models:\n\n"
            
            for model in models[:10]:  # Show first 10 models
                model_id, name, param_size, quant, size_mb = model
                size_str = f" ({size_mb:.2f} MB)" if size_mb else ""
                models_info += f"• **{name}** - ID: {model_id}, {param_size or 'Unknown'}, {quant or 'Unknown'}{size_str}\n"
                
            if len(models) > 10:
                models_info += f"\n...and {len(models) - 10} more models"
                
            embed.add_field(name="Models", value=models_info, inline=False)
        else:
            embed.add_field(name="Models", value="No models found on this server", inline=False)
        
        # Add usage instructions
        embed.add_field(
            name="Actions",
            value="• Use `/server action:check ip:" + server_ip + "` to check models\n"
                  "• Use `/server action:verify ip:" + server_ip + "` to verify connectivity",
            inline=False
        )
        
        # Send the response
        await interaction.followup.send(embed=embed)
    
    async def handle_check_server(interaction, ip, port):
        """Handler for checking available models on a server"""
        try:
            # First check if the server exists in our database
            query = """
                SELECT id, verified, is_active
                FROM endpoints
                WHERE ip = %s AND port = %s
            """
            server = Database.fetch_one(query, (ip, port))
            
            if not server:
                # Server doesn't exist, so we'll add it first if it's reachable
                await interaction.followup.send(embed=await format_embed_message(
                    title="Checking New Server",
                    description=f"Server {ip}:{port} is not in our database. Attempting to connect and catalog models...",
                    color=discord.Color.blue()
                ))
                
                # Test connectivity
                api_url = f"http://{ip}:{port}/api/tags"
                
                async with aiohttp.ClientSession() as session:
                    try:
                        # Set a timeout for the request
                        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
                        async with session.get(api_url, timeout=timeout) as response:
                            if response.status != 200:
                                await interaction.followup.send(embed=await format_embed_message(
                                    title="Connection Failed",
                                    description=f"Could not connect to server at {ip}:{port}. The server returned status code {response.status}.",
                                    color=discord.Color.red()
                                ))
                                return
                                
                            # Successfully connected, add server to database
                            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            query = """
                                INSERT INTO endpoints (ip, port, scan_date, verified, verification_date, is_honeypot, is_active)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                RETURNING id
                            """
                            result = Database.fetch_one(query, (ip, port, now, get_db_boolean(True, for_verified=True), now, get_db_boolean(False), get_db_boolean(True)))
                            
                            if not result:
                                await interaction.followup.send(embed=await format_embed_message(
                                    title="Database Error",
                                    description=f"Failed to add server {ip}:{port} to the database.",
                                    color=discord.Color.red()
                                ))
                                return
                                
                            server_id = result[0]
                                
                    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Connection Failed",
                            description=f"Could not connect to server at {ip}:{port}. Error: {str(e)}",
                            color=discord.Color.red()
                        ))
                        return
            else:
                server_id, verified, is_active = server
                
                if not is_active:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Server Inactive",
                        description=f"Server {ip}:{port} is marked as inactive in our database. Use 'verify' action to check connectivity.",
                        color=discord.Color.orange()
                    ))
                    return
            
            # Now fetch models from the server
            api_url = f"http://{ip}:{port}/api/tags"
            
            async with aiohttp.ClientSession() as session:
                try:
                    # Set a timeout for the request
                    timeout = aiohttp.ClientTimeout(total=15)  # 15 second timeout
                    async with session.get(api_url, timeout=timeout) as response:
                        if response.status != 200:
                            await interaction.followup.send(embed=await format_embed_message(
                                title="API Error",
                                description=f"The server returned status code {response.status} when requesting models.",
                                color=discord.Color.red()
                            ))
                            return
                            
                        # Parse the response
                        try:
                            models_data = await response.json()
                            models = models_data.get('models', [])
                        except json.JSONDecodeError:
                            await interaction.followup.send(embed=await format_embed_message(
                                title="API Error",
                                description="Failed to parse the server response as JSON.",
                                color=discord.Color.red()
                            ))
                            return
                        
                        if not models:
                            await interaction.followup.send(embed=await format_embed_message(
                                title="No Models Found",
                                description=f"No models were found on server {ip}:{port}.",
                                color=discord.Color.orange()
                            ))
                            return
                        
                        # Process and display the models
                        embed = await format_embed_message(
                            title=f"Models on {ip}:{port}",
                            description=f"Found {len(models)} models on this server",
                            color=discord.Color.blue()
                        )
                        
                        # Process and sync models with database
                        updated_count = 0
                        for model in models:
                            model_name = model.get('name')
                            if not model_name:
                                continue
                                
                            # Try to extract size and quantization from the name
                            param_size = None
                            quant_level = None
                            
                            # Parse parameter size (e.g., 7B, 13B, etc.)
                            for size in ["70b", "65b", "34b", "33b", "13b", "8b", "7b", "3b", "2b", "1b"]:
                                if size in model_name.lower():
                                    param_size = size.upper()
                                    break
                            
                            # Parse quantization level if present
                            quant_patterns = [
                                "q2_k", "q3_k_m", "q3_k_s", "q4_0", "q4_k_m", "q4_k_s", 
                                "q5_0", "q5_k_m", "q5_k_s", "q6_k", "q8_0", "f16", "f32"
                            ]
                            for pattern in quant_patterns:
                                if pattern in model_name.lower():
                                    quant_level = pattern.upper()
                                    break
                            
                            # Check if this model already exists in the database for this server
                            query = """
                                SELECT id
                                FROM models
                                WHERE name = %s AND endpoint_id = %s
                            """
                            existing = Database.fetch_one(query, (model_name, server_id))
                            
                            if existing:
                                # Update existing model if needed
                                if param_size or quant_level:
                                    update_query = """
                                        UPDATE models SET
                                        parameter_size = COALESCE(%s, parameter_size),
                                        quantization_level = COALESCE(%s, quantization_level)
                                        WHERE id = %s
                                    """
                                    Database.execute(update_query, (param_size, quant_level, existing[0]))
                                    updated_count += 1
                            else:
                                # Add new model
                                insert_query = """
                                    INSERT INTO models (name, endpoint_id, parameter_size, quantization_level)
                                    VALUES (%s, %s, %s, %s)
                                """
                                Database.execute(insert_query, (model_name, server_id, param_size, quant_level))
                                updated_count += 1
                            
                            # Add to the embed
                            model_info = f"**Name:** {model_name}\n"
                            if param_size:
                                model_info += f"**Parameters:** {param_size}\n"
                            if quant_level:
                                model_info += f"**Quantization:** {quant_level}\n"
                                
                            embed.add_field(
                                name=f"{model_name}",
                                value=model_info,
                                inline=True
                            )
                        
                        # Add footer with summary
                        embed.set_footer(text=f"Updated {updated_count} models in database • Use /models action:list to view all models")
                        
                        # Send the response
                        await interaction.followup.send(embed=embed)
                        
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Connection Error",
                        description=f"Error connecting to server: {str(e)}",
                        color=discord.Color.red()
                    ))
        
        except Exception as e:
            logger.error(f"Error checking server {ip}:{port}: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error",
                description=f"An error occurred while checking the server: ```\n{str(e)}\n```",
                color=discord.Color.red()
            ))
    
    async def handle_verify_server(interaction, ip, port):
        """Handler for verifying server connectivity"""
        try:
            status_embed = await format_embed_message(
                title="Verifying Server",
                description=f"Checking connectivity to {ip}:{port}...",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=status_embed)
            
            # Attempt to connect to the server
            api_url = f"http://{ip}:{port}/api/version"
            
            async with aiohttp.ClientSession() as session:
                try:
                    # Set a timeout for the request
                    timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
                    start_time = asyncio.get_event_loop().time()
                    
                    async with session.get(api_url, timeout=timeout) as response:
                        end_time = asyncio.get_event_loop().time()
                        response_time = round((end_time - start_time) * 1000)  # in ms
                        
                        if response.status != 200:
                            # Server responded but with an error
                            error_text = await response.text()
                            await interaction.followup.send(embed=await format_embed_message(
                                title="Server Responded with Error",
                                description=f"The server at {ip}:{port} responded with status code {response.status}.\n```\n{error_text}\n```",
                                color=discord.Color.orange()
                            ))
                            
                            # Update the database to mark server as verified but with issues
                            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            query = """
                                INSERT INTO endpoints (ip, port, scan_date, verified, verification_date, is_honeypot, is_active, inactive_reason)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (ip, port) DO UPDATE SET
                                verification_date = %s,
                                is_active = %s,
                                inactive_reason = %s
                                RETURNING id
                            """
                            Database.execute(query, (
                                ip, port, now, get_db_boolean(True, for_verified=True), now, get_db_boolean(False), get_db_boolean(False),
                                f"API error: Status {response.status}", now, get_db_boolean(False), f"API error: Status {response.status}"
                            ))
                            return
                            
                        # Success - Parse the response to get the version
                        try:
                            version_data = await response.json()
                            version = version_data.get('version', 'Unknown')
                        except json.JSONDecodeError:
                            version = "Unknown (Invalid JSON response)"
                        
                        # Update the database to mark server as verified and active
                        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        query = """
                            INSERT INTO endpoints (ip, port, scan_date, verified, verification_date, is_honeypot, is_active)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ip, port) DO UPDATE SET
                            verification_date = %s,
                            verified = %s,
                            is_active = %s,
                            inactive_reason = NULL
                            RETURNING id
                        """
                        result = Database.fetch_one(query, (
                            ip, port, now, get_db_boolean(True, for_verified=True), now, get_db_boolean(False), get_db_boolean(True),
                            now, get_db_boolean(True, for_verified=True), get_db_boolean(True)
                        ))
                        
                        server_id = result[0] if result else None
                        
                        # Send success response
                        await interaction.followup.send(embed=await format_embed_message(
                            title="✅ Server Verified",
                            description=f"Successfully connected to Ollama server at {ip}:{port}\n\n"
                                      f"**Version:** {version}\n"
                                      f"**Response Time:** {response_time}ms\n"
                                      f"**Server ID:** {server_id}",
                            color=discord.Color.green()
                        ))
                        
                        # Add action buttons
                        action_embed = await format_embed_message(
                            title="Available Actions",
                            description=f"• Use `/server action:check ip:{ip} port:{port}` to scan for models\n"
                                      f"• Use `/server action:details ip:{ip} port:{port}` to view server details",
                            color=discord.Color.blue()
                        )
                        await interaction.followup.send(embed=action_embed)
                        
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    # Update the database to mark server as verified but inactive
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    query = """
                        INSERT INTO endpoints (ip, port, scan_date, verified, verification_date, is_honeypot, is_active, inactive_reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ip, port) DO UPDATE SET
                        verification_date = %s,
                        is_active = %s,
                        inactive_reason = %s
                        RETURNING id
                    """
                    Database.execute(query, (
                        ip, port, now, get_db_boolean(True, for_verified=True), now, get_db_boolean(False), get_db_boolean(False),
                        f"Connection error: {str(e)}", now, get_db_boolean(False), f"Connection error: {str(e)}"
                    ))
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="❌ Connection Failed",
                        description=f"Could not connect to server at {ip}:{port}.\n\n**Error:** {str(e)}",
                        color=discord.Color.red()
                    ))
        
        except Exception as e:
            logger.error(f"Error verifying server {ip}:{port}: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error",
                description=f"An error occurred while verifying the server: ```\n{str(e)}\n```",
                color=discord.Color.red()
            )) 

    # Add to registered commands
    registered_commands["server"] = server_command

    #
    # 1.4. /help Command Implementation
    #
    @bot.tree.command(name="help", description="Show help information")
    @app_commands.describe(
        topic="Optional: Get help on a specific topic"
    )
    @app_commands.choices(topic=[
        app_commands.Choice(name="Models", value="models"),
        app_commands.Choice(name="Chat", value="chat"),
        app_commands.Choice(name="Servers", value="servers"),
        app_commands.Choice(name="Admin", value="admin"),
        app_commands.Choice(name="Examples", value="examples")
    ])
    async def help_command(
        interaction: discord.Interaction,
        topic: str = None
    ):
        """Updated help command reflecting the new command structure"""
        try:
            if topic:
                # Topic-specific help
                if topic == "models":
                    embed = await create_models_help_embed()
                elif topic == "chat":
                    embed = await create_chat_help_embed()
                elif topic == "servers":
                    embed = await create_servers_help_embed()
                elif topic == "admin":
                    embed = await create_admin_help_embed()
                elif topic == "examples":
                    embed = await create_examples_help_embed()
                else:
                    embed = await create_general_help_embed()
            else:
                # General help overview
                embed = await create_general_help_embed()
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in help command: {str(e)}")
            await interaction.response.send_message(f"Error generating help: {str(e)}", ephemeral=True)
    
    async def create_general_help_embed():
        """Create the general help embed with command overview"""
        embed = discord.Embed(
            title="🤖 Ollama Discord Bot Help",
            description="This bot allows you to interact with Ollama models directly from Discord.",
            color=discord.Color.blurple()
        )
        
        # User commands section
        embed.add_field(
            name="📋 User Commands",
            value=(
                "• `/models` - Search, filter, and view available models\n"
                "• `/chat` - Chat with any Ollama model by ID or name\n"
                "• `/server` - View and manage Ollama servers\n"
                "• `/history` - View your chat history\n"
                "• `/help` - Show help information on specific topics"
            ),
            inline=False
        )
        
        # Admin commands section
        embed.add_field(
            name="⚙️ Admin Commands",
            value=(
                "• `/admin` - Administrative functions and tools\n"
                "• `/manage` - Manage models and servers\n"
                "• `/stats` - View statistics and analytics"
            ),
            inline=False
        )
        
        # Add usage tip
        embed.add_field(
            name="Usage Tip",
            value="Use `/help [topic]` to get detailed help on specific commands",
            inline=False
        )
        
        embed.set_footer(text="Type / to see all available commands • Parameters are shown when you select a command")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed
    
    async def create_models_help_embed():
        """Create help embed for the models command"""
        embed = discord.Embed(
            title="🔍 Models Command Help",
            description="The `/models` command allows you to search, filter, and view available Ollama models.",
            color=discord.Color.blue()
        )
        
        # Basic usage
        embed.add_field(
            name="Basic Usage",
            value=(
                "• `/models` - List all available models\n"
                "• `/models search:llama` - Search for models containing 'llama'\n"
                "• `/models action:details search:llama3` - View details for a specific model\n"
                "• `/models size:7B` - Filter models by parameter size\n"
                "• `/models quantization:Q4_K_M` - Filter models by quantization"
            ),
            inline=False
        )
        
        # Parameters
        embed.add_field(
            name="Available Parameters",
            value=(
                "• `action` - Type of search (list, search, details, endpoints)\n"
                "• `search` - Search term for model names\n"
                "• `size` - Filter by parameter size (e.g., 7B, 13B)\n"
                "• `quantization` - Filter by quantization level\n"
                "• `sort_by` - Sort results by field (name, params, quant, count)\n"
                "• `descending` - Sort in descending/ascending order\n"
                "• `limit` - Maximum number of results (default: 25)\n"
                "• `show_endpoints` - Show endpoint details for each model"
            ),
            inline=False
        )
        
        # Examples
        embed.add_field(
            name="Examples",
            value=(
                "• `/models action:list sort_by:count` - List models sorted by count\n"
                "• `/models action:details search:65` - View details for 65B models\n"
                "• `/models action:endpoints search:mistral` - Find endpoints with mistral\n"
                "• `/models size:7B quantization:Q4_K_M` - Find specific model variants"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the /chat command to interact with a model after finding it")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed
    
    async def create_chat_help_embed():
        """Create help embed for the chat command"""
        embed = discord.Embed(
            title="💬 Chat Command Help",
            description="The `/chat` command allows you to interact with any Ollama model.",
            color=discord.Color.green()
        )
        
        # Basic usage
        embed.add_field(
            name="Basic Usage",
            value=(
                "• `/chat model:llama3 prompt:Hello there!` - Chat with a model by name\n"
                "• `/chat model:42 prompt:How do I use Python?` - Chat with a model by ID\n"
                "• `/chat model:mistral prompt:Explain quantum physics system_prompt:You are a helpful physics expert` - Use a system prompt"
            ),
            inline=False
        )
        
        # Parameters
        embed.add_field(
            name="Available Parameters",
            value=(
                "• `model` - Model ID or name to chat with (required)\n"
                "• `prompt` - Your message to the model (required)\n"
                "• `system_prompt` - Instructions to guide the model's behavior\n"
                "• `temperature` - Controls randomness (0.0 to 1.0, default: 0.7)\n"
                "• `max_tokens` - Maximum response length (default: 1000)\n"
                "• `save_history` - Save this chat in your history (default: true)\n"
                "• `verbose` - Show detailed API information (default: false)"
            ),
            inline=False
        )
        
        # Tips
        embed.add_field(
            name="Tips",
            value=(
                "• Use `/models` first to find available models\n"
                "• Higher temperature (>0.7) = more creative responses\n"
                "• Lower temperature (<0.3) = more deterministic responses\n"
                "• Use system prompts to set the tone or give special instructions\n"
                "• View your chat history with `/history`"
            ),
            inline=False
        )
        
        embed.set_footer(text="Model responses are generated by external Ollama servers and not controlled by this bot")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed
    
    async def create_servers_help_embed():
        """Create help embed for the server command"""
        embed = discord.Embed(
            title="🖥️ Server Command Help",
            description="The `/server` command helps you view and manage Ollama servers.",
            color=discord.Color.gold()
        )
        
        # Basic usage
        embed.add_field(
            name="Basic Usage",
            value=(
                "• `/server action:list` - List all available servers\n"
                "• `/server action:details ip:1.2.3.4` - View details for a specific server\n"
                "• `/server action:check ip:1.2.3.4 port:11434` - Check models on a server\n"
                "• `/server action:verify ip:1.2.3.4` - Verify connectivity to a server"
            ),
            inline=False
        )
        
        # Parameters
        embed.add_field(
            name="Available Parameters",
            value=(
                "• `action` - Action to perform (list, details, check, verify)\n"
                "• `ip` - Server IP address (required for all actions except list)\n"
                "• `port` - Server port (default: 11434)\n"
                "• `sort_by` - Sort results by field (ip, date, count)\n"
                "• `limit` - Maximum number of results (default: 25)"
            ),
            inline=False
        )
        
        # Tips
        embed.add_field(
            name="Tips",
            value=(
                "• Use the verify action before checking models on a new server\n"
                "• The check action will auto-add verified servers to the database\n"
                "• Servers marked as inactive need to be verified again\n"
                "• Sort by model count to find servers with the most models"
            ),
            inline=False
        )
        
        embed.set_footer(text="Only verified, active, non-honeypot servers are used for model interactions")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed
    
    async def create_admin_help_embed():
        """Create help embed for admin commands"""
        embed = discord.Embed(
            title="⚙️ Admin Commands Help",
            description="Administrative commands for managing the bot and database.",
            color=discord.Color.dark_red()
        )
        
        # Admin permission notice
        embed.add_field(
            name="⚠️ Admin Permissions Required",
            value="These commands are only available to server administrators.",
            inline=False
        )
        
        # Commands overview
        embed.add_field(
            name="Available Commands",
            value=(
                "• `/admin` - Administrative functions and tools\n"
                "• `/manage` - Manage models and servers\n"
                "• `/stats` - View statistics and analytics"
            ),
            inline=False
        )
        
        # Admin command
        embed.add_field(
            name="/admin Command",
            value=(
                "Perform administrative tasks:\n"
                "• `action:db_info` - Show database information\n"
                "• `action:refresh` - Refresh commands\n"
                "• `action:cleanup` - Cleanup database\n"
                "• `action:verify` - Verify all servers\n"
                "• `action:sync` - Sync all models"
            ),
            inline=False
        )
        
        # Manage command
        embed.add_field(
            name="/manage Command",
            value=(
                "Manage models and servers:\n"
                "• `action:add type:model` - Add a model\n"
                "• `action:delete type:model` - Delete a model\n"
                "• `action:add type:server` - Add a server\n"
                "• `action:delete type:server` - Delete a server"
            ),
            inline=False
        )
        
        # Stats command
        embed.add_field(
            name="/stats Command",
            value=(
                "View system statistics:\n"
                "• `type:models` - Model statistics\n"
                "• `type:servers` - Server statistics\n"
                "• `type:endpoints` - Endpoint statistics\n"
                "• `type:usage` - Usage statistics"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use these commands with caution - they affect the entire system")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed
    
    async def create_examples_help_embed():
        """Create help embed with usage examples"""
        embed = discord.Embed(
            title="📝 Usage Examples",
            description="Here are some common usage examples for the bot commands.",
            color=discord.Color.purple()
        )
        
        # Find and chat with a model
        embed.add_field(
            name="Find and Chat with a Model",
            value=(
                "1. `/models search:llama3` - Find Llama 3 models\n"
                "2. Look for a model ID in the results\n"
                "3. `/chat model:123 prompt:Explain quantum computing`\n"
                "4. To use a different model: `/models search:mistral`"
            ),
            inline=False
        )
        
        # Using system prompts
        embed.add_field(
            name="Using System Prompts",
            value=(
                "System prompts help guide the model's behavior:\n"
                "```\n/chat model:phi3 prompt:Write a short story about space exploration system_prompt:You are a creative sci-fi writer. Write in a descriptive style with vivid imagery. Include dialogue between characters.\n```"
            ),
            inline=False
        )
        
        # Finding specific model variants
        embed.add_field(
            name="Finding Specific Model Variants",
            value=(
                "To find specific model variants:\n"
                "1. `/models size:7B quantization:Q4_K_M` - Find 7B Q4_K_M models\n"
                "2. `/models action:details search:llama3` - Get details about Llama 3\n"
                "3. `/models action:endpoints search:mistral` - Find all endpoints with Mistral"
            ),
            inline=False
        )
        
        # Working with servers
        embed.add_field(
            name="Working with Servers",
            value=(
                "To check a new Ollama server:\n"
                "1. `/server action:verify ip:1.2.3.4` - Verify server connectivity\n"
                "2. `/server action:check ip:1.2.3.4` - Check available models\n"
                "3. `/server action:details ip:1.2.3.4` - View server details"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /help [topic] for detailed help on specific commands")
        embed.timestamp = datetime.now(timezone.utc)
        
        return embed

    #
    # 1.5. /history Command Implementation
    #
    @bot.tree.command(name="history", description="View and manage your chat history")
    @app_commands.describe(
        action="Action to perform",
        limit="Maximum number of history items to show",
        model_id="Filter by model ID",
        search="Search term to filter history by"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="View History", value="view"),
        app_commands.Choice(name="Clear History", value="clear"),
        app_commands.Choice(name="Continue Chat", value="continue")
    ])
    async def history_command(
        interaction: discord.Interaction,
        action: str = "view",
        limit: int = 5,
        model_id: int = None,
        search: str = None
    ):
        """Command for viewing and managing chat history"""
        await safe_defer(interaction)
        
        try:
            # Get user ID for history lookup
            user_id = str(interaction.user.id)
            
            if action == "view":
                await handle_view_history(interaction, user_id, limit, model_id, search)
            elif action == "clear":
                await handle_clear_history(interaction, user_id, model_id)
            elif action == "continue":
                await handle_continue_chat(interaction, user_id)
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Unknown Action",
                    description="The specified action is not recognized.",
                    color=discord.Color.red()
                ))
                
        except Exception as e:
            logger.error(f"Error in history command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    async def handle_view_history(interaction, user_id, limit, model_id, search):
        """Handler for viewing chat history"""
        # Create table if it doesn't exist
        Database.execute("""
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
        """)
            
        # Build query to fetch history
        query = """
            SELECT ch.id, ch.model_id, m.name, ch.prompt, ch.response, ch.timestamp, 
                   ch.system_prompt, ch.temperature, ch.max_tokens, ch.eval_count, ch.eval_duration
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            WHERE ch.user_id = %s
        """
        params = [user_id]
        
        # Add filters if provided
        if model_id:
            query += " AND ch.model_id = %s"
            params.append(model_id)
            
        if search:
            query += " AND (ch.prompt LIKE %s OR ch.response LIKE %s)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
            
        # Add sorting and limit
        query += " ORDER BY ch.timestamp DESC LIMIT %s"
        params.append(limit)
        
        # Execute query
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            await interaction.followup.send(embed=await format_embed_message(
                title="No Chat History",
                description="You don't have any chat history matching these criteria.",
                color=discord.Color.blue()
            ))
            return
            
        # Format results as embed
        embed = await format_embed_message(
            title="Your Chat History",
            description=f"Showing your {len(results)} most recent chats" + 
                      (f" matching '{search}'" if search else "") +
                      (f" with model ID {model_id}" if model_id else ""),
            color=discord.Color.blue()
        )
        
        # Add each history item
        for i, entry in enumerate(results):
            history_id, model_id, model_name, prompt, response, timestamp, system_prompt, temp, max_tokens, eval_count, eval_duration = entry
            
            # Truncate long texts
            if prompt and len(prompt) > 100:
                prompt = prompt[:97] + "..."
            if response and len(response) > 150:
                response = response[:147] + "..."
                
            # Format the history entry
            entry_text = f"**Prompt:** {prompt}\n"
            entry_text += f"**Response:** {response}\n"
            entry_text += f"**Time:** {timestamp}\n"
            
            # Add additional details
            details = []
            if system_prompt:
                details.append(f"System prompt: {len(system_prompt)} chars")
            if temp != 0.7:  # Only show if different from default
                details.append(f"Temp: {temp}")
            if max_tokens != 1000:  # Only show if different from default
                details.append(f"Max tokens: {max_tokens}")
            if eval_count:
                details.append(f"Tokens: {eval_count}")
            if eval_duration:
                details.append(f"Duration: {eval_duration:.2f}s")
                
            if details:
                entry_text += f"**Details:** {', '.join(details)}\n"
                
            # Add a link to continue this chat
            entry_text += f"Use `/history action:continue` to continue this conversation"
            
            embed.add_field(
                name=f"{i+1}. {model_name} (ID: {model_id})",
                value=entry_text,
                inline=False
            )
        
        # Add footer with instructions
        embed.set_footer(text="Use /history action:clear to clear your history")
        
        # Send the response
        await interaction.followup.send(embed=embed)
    
    async def handle_clear_history(interaction, user_id, model_id):
        """Handler for clearing chat history"""
        # Build query to delete history
        query = "DELETE FROM chat_history WHERE user_id = %s"
        params = [user_id]
        
        # Add model filter if provided
        if model_id:
            query += " AND model_id = %s"
            params.append(model_id)
            
        # Execute query
        try:
            Database.execute(query, tuple(params))
            
            # Send confirmation
            if model_id:
                await interaction.followup.send(embed=await format_embed_message(
                    title="History Cleared",
                    description=f"Your chat history with model ID {model_id} has been cleared.",
                    color=discord.Color.green()
                ))
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="History Cleared",
                    description="Your entire chat history has been cleared.",
                    color=discord.Color.green()
                ))
                
        except Exception as e:
            logger.error(f"Error clearing history: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error Clearing History",
                description=f"An error occurred while clearing your history: ```\n{str(e)}\n```",
                color=discord.Color.red()
            ))
    
    async def handle_continue_chat(interaction, user_id):
        """Handler for continuing the last chat"""
        # Find the last chat
        query = """
            SELECT ch.id, ch.model_id, m.name, m.parameter_size, m.quantization_level, 
                   e.ip, e.port, ch.prompt, ch.system_prompt, ch.response, 
                   ch.temperature, ch.max_tokens
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE ch.user_id = %s
            ORDER BY ch.timestamp DESC
            LIMIT 1
        """
        result = Database.fetch_one(query, (user_id,))
        
        if not result:
            await interaction.followup.send(embed=await format_embed_message(
                title="No Chat History",
                description="You don't have any chat history to continue from.",
                color=discord.Color.orange()
            ))
            return
            
        # Extract chat details
        (chat_id, model_id, model_name, param_size, quant_level, 
         ip, port, last_prompt, system_prompt, last_response, 
         temperature, max_tokens) = result
        
        # Check if server is still available
        server_available, error = await check_server_connectivity(ip, port)
        if not server_available:
            await interaction.followup.send(embed=await format_embed_message(
                title="Server Unavailable",
                description=f"The server for this model ({ip}:{port}) is no longer available: {error}",
                color=discord.Color.red()
            ))
            return
            
        # Display a continuation message with the model and last exchange
        prompt_preview = last_prompt[:150] + "..." if len(last_prompt) > 150 else last_prompt
        response_preview = last_response[:150] + "..." if len(last_response) > 150 else last_response
        
        # Format the model name with parameter size and quantization level
        full_model_name = model_name
        if param_size:
            full_model_name += f" ({param_size}"
            if quant_level:
                full_model_name += f", {quant_level}"
            full_model_name += ")"
            
        embed = await format_embed_message(
            title="Continue Chat Session",
            description=f"You can continue your conversation with **{full_model_name}**.\n\nUse `/chat` with this model to continue the conversation.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Last Exchange",
            value=f"**You:** {prompt_preview}\n\n**Model:** {response_preview}",
            inline=False
        )
        
        embed.add_field(
            name="Settings",
            value=f"Model ID: `{model_id}`\nTemperature: `{temperature}`\nMax Tokens: `{max_tokens}`",
            inline=False
        )
        
        embed.add_field(
            name="Continue With",
            value=f"Use this command to continue:\n```\n/chat model:{model_id} prompt:Your new message\n```",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    # Store the history command
    registered_commands["history"] = history_command

    #
    # 2.3. /stats Command Implementation
    #
    @bot.tree.command(name="stats", description="View statistics and analytics")
    @app_commands.describe(
        type="Type of statistics to view",
        format="Output format for the statistics",
        check_connectivity="Check server connectivity when viewing server stats"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Database Overview", value="overview"),
        app_commands.Choice(name="Model Statistics", value="models"),
        app_commands.Choice(name="Server Statistics", value="servers"),
        app_commands.Choice(name="Parameter Sizes", value="param_sizes"),
        app_commands.Choice(name="Quantization Levels", value="quant_levels"),
        app_commands.Choice(name="Top Models", value="top_models")
    ])
    @app_commands.choices(format=[
        app_commands.Choice(name="Table", value="table"),
        app_commands.Choice(name="Detailed", value="detailed")
    ])
    async def stats_command(
        interaction: discord.Interaction,
        type: str = "overview",
        format: str = "detailed",
        check_connectivity: bool = False
    ):
        """Command for viewing statistics and analytics"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
            
        await safe_defer(interaction)
        
        try:
            # Get database statistics
            stats = get_database_stats()
            
            if not stats:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Error Retrieving Statistics",
                    description="Could not retrieve database statistics. Check the logs for details.",
                    color=discord.Color.red()
                ))
                return
                
            if type == "overview":
                # Database overview
                embed = await format_embed_message(
                    title="📊 Database Statistics Overview",
                    description="General statistics about the database content",
                    color=discord.Color.blue()
                )
                
                embed.add_field(name="Endpoints", value=f"{stats['endpoint_count']:,}", inline=True)
                embed.add_field(name="Total Models", value=f"{stats['total_models']:,}", inline=True)
                embed.add_field(name="Unique Models", value=f"{stats['unique_models']:,}", inline=True)
                
                # Add timestamp
                embed.set_footer(text="Last updated")
                
                await interaction.followup.send(embed=embed)
                
            elif type == "models":
                # Model statistics
                embed = await format_embed_message(
                    title="📊 Model Statistics",
                    description=f"Statistics for {stats['total_models']:,} total models across {stats['endpoint_count']:,} endpoints",
                    color=discord.Color.blue()
                )
                
                # Add model distribution info
                models_text = f"**Total Models:** {stats['total_models']:,}\n"
                models_text += f"**Unique Model Types:** {stats['unique_models']:,}\n\n"
                
                # Add top models if available
                if stats['top_models']:
                    models_text += "**Top Models by Count:**\n"
                    for i, (model, count) in enumerate(stats['top_models'][:5]):
                        models_text += f"{i+1}. **{model}**: {count:,} instances\n"
                
                embed.add_field(name="Model Distribution", value=models_text, inline=False)
                
                await interaction.followup.send(embed=embed)
                
            elif type == "servers":
                # Server statistics
                embed = await format_embed_message(
                    title="📊 Server Statistics",
                    description=f"Statistics for {stats['endpoint_count']:,} endpoints in the database",
                    color=discord.Color.blue()
                )
                
                # Add server info
                servers_text = f"**Total Endpoints:** {stats['endpoint_count']:,}\n"
                servers_text += f"**Average Models per Endpoint:** {stats['total_models'] / max(1, stats['endpoint_count']):.1f}\n"
                
                embed.add_field(name="Server Distribution", value=servers_text, inline=False)
                
                await interaction.followup.send(embed=embed)
                
            elif type == "param_sizes":
                # Parameter size distribution
                embed = await format_embed_message(
                    title="📊 Parameter Size Distribution",
                    description="Distribution of models by parameter size",
                    color=discord.Color.blue()
                )
                
                if stats['parameter_sizes']:
                    params_text = ""
                    for param_size, count in stats['parameter_sizes']:
                        # Handle None values
                        size_display = param_size if param_size else "Unknown"
                        params_text += f"**{size_display}**: {count:,} models\n"
                    
                    embed.add_field(name="Parameter Size Counts", value=params_text, inline=False)
                else:
                    embed.add_field(
                        name="No Data Available",
                        value="No parameter size information found in the database.",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed)
                
            elif type == "quant_levels":
                # Quantization level distribution
                embed = await format_embed_message(
                    title="📊 Quantization Level Distribution",
                    description="Distribution of models by quantization level",
                    color=discord.Color.blue()
                )
                
                if stats['quantization_levels']:
                    quant_text = ""
                    for quant_level, count in stats['quantization_levels']:
                        # Handle None values
                        level_display = quant_level if quant_level else "Unknown"
                        quant_text += f"**{level_display}**: {count:,} models\n"
                    
                    embed.add_field(name="Quantization Level Counts", value=quant_text, inline=False)
                else:
                    embed.add_field(
                        name="No Data Available",
                        value="No quantization level information found in the database.",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed)
                
            elif type == "top_models":
                # Top models
                embed = await format_embed_message(
                    title="📊 Top Models by Instance Count",
                    description=f"Most popular models across {stats['endpoint_count']:,} endpoints",
                    color=discord.Color.blue()
                )
                
                if stats['top_models']:
                    models_text = ""
                    for i, (model, count) in enumerate(stats['top_models']):
                        models_text += f"{i+1}. **{model}**: {count:,} instances\n"
                    
                    embed.add_field(name="Model Popularity", value=models_text, inline=False)
                else:
                    embed.add_field(
                        name="No Data Available",
                        value="No model data found in the database.",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed)
            
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Unknown Statistics Type",
                    description=f"The statistics type '{type}' is not recognized.",
                    color=discord.Color.red()
                ))
                
        except Exception as e:
            logger.error(f"Error in stats command: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            ))
    
    # Store the stats command
    registered_commands["stats"] = stats_command
    
    # Add admin command
    @bot.tree.command(name="admin", description="Administrative functions and tools")
    @app_commands.describe(
        action="Action to perform",
        target="Target for the action",
        force="Force the action even if it might be destructive"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Database Info", value="db_info"),
        app_commands.Choice(name="Refresh Commands", value="refresh"),
        app_commands.Choice(name="Cleanup Database", value="cleanup"),
        app_commands.Choice(name="Verify All Servers", value="verify"),
        app_commands.Choice(name="Sync Models", value="sync")
    ])
    @app_commands.choices(target=[
        app_commands.Choice(name="Global", value="global"),
        app_commands.Choice(name="Guild", value="guild"),
        app_commands.Choice(name="All Servers", value="all")
    ])
    async def admin_command(
        interaction: discord.Interaction,
        action: str,
        target: str = "guild",
        force: bool = False
    ):
        """Administrative command for managing the bot and database"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        await safe_defer(interaction)
        
        try:
            # Create a wrapper for safe_followup that supports the 'embed' parameter
            # This wrapper is needed for compatibility with functions imported from admin_command.py
            async def safe_followup_wrapper(interaction, content=None, embed=None, ephemeral=False):
                if embed:
                    await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
                else:
                    await interaction.followup.send(content=content, ephemeral=ephemeral)
            
            if action == "db_info":
                # Import the detailed handler from admin_command.py
                from admin_command import handle_db_info
                # Call the detailed implementation with our wrapper
                await handle_db_info(interaction, safe_followup_wrapper)
                
            elif action == "refresh":
                # Import the handler from admin_command.py
                try:
                    from admin_command import handle_refresh_commands
                    await handle_refresh_commands(interaction, target, bot, safe_followup_wrapper)
                except ImportError:
                    # Fallback to built-in implementation if import fails
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Command Refresh Initiated",
                        description=f"Refreshing commands for target: {target}",
                        color=discord.Color.blue()
                    ))
                    
                    try:
                        if target == "guild":
                            # Sync with the current guild
                            synced = await bot.tree.sync(guild=interaction.guild)
                            await interaction.followup.send(embed=await format_embed_message(
                                title="Commands Refreshed",
                                description=f"Successfully synced {len(synced)} commands with this guild.",
                                color=discord.Color.green()
                            ))
                        elif target == "global":
                            # Sync globally
                            synced = await bot.tree.sync()
                            await interaction.followup.send(embed=await format_embed_message(
                                title="Commands Refreshed",
                                description=f"Successfully synced {len(synced)} commands globally.",
                                color=discord.Color.green()
                            ))
                        else:
                            await interaction.followup.send(embed=await format_embed_message(
                                title="Invalid Target",
                                description=f"Target '{target}' is not recognized.",
                                color=discord.Color.red()
                            ))
                    except Exception as e:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Error Refreshing Commands",
                            description=f"An error occurred: ```{str(e)}```",
                            color=discord.Color.red()
                        ))
                    
            elif action == "cleanup":
                # Import the handler from admin_command.py
                try:
                    from admin_command import handle_cleanup_database
                    await handle_cleanup_database(interaction, force, safe_followup_wrapper)
                except ImportError:
                    # Fallback to built-in implementation if import fails
                    # Cleanup database
                    if not force:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Confirmation Required",
                            description="This action will clean up the database by removing duplicate entries and potentially outdated information. Use `force:true` to confirm.",
                            color=discord.Color.gold()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Database Cleanup Initiated",
                        description="Cleaning up the database. This may take a while...",
                        color=discord.Color.blue()
                    ))
                    
                    try:
                        # Remove duplicate endpoints
                        query = """
                            DELETE FROM endpoints 
                            WHERE id IN (
                                SELECT e1.id 
                                FROM endpoints e1 
                                JOIN endpoints e2 ON e1.ip = e2.ip AND e1.port = e2.port 
                                WHERE e1.id > e2.id
                            )
                        """
                        result = Database.execute(query)
                        
                        # Remove orphaned models
                        query = """
                            DELETE FROM models 
                            WHERE endpoint_id NOT IN (
                                SELECT id FROM endpoints
                            )
                        """
                        result2 = Database.execute(query)
                        
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Database Cleanup Complete",
                            description="Database has been cleaned up successfully.",
                            color=discord.Color.green()
                        ))
                    except Exception as e:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Error Cleaning Database",
                            description=f"An error occurred: ```{str(e)}```",
                            color=discord.Color.red()
                        ))
                    
            elif action == "verify":
                # Import the handler from admin_command.py
                try:
                    from admin_command import handle_verify_all_servers
                    await handle_verify_all_servers(interaction, force, safe_followup_wrapper)
                except ImportError:
                    # Fallback to built-in implementation if import fails
                    # Verify all servers
                    if not force:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Confirmation Required",
                            description="This action will verify all servers in the database, which may take a long time. Use `force:true` to confirm.",
                            color=discord.Color.gold()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Server Verification Initiated",
                        description="Verifying all servers in the database. This may take a while...",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
            elif action == "sync":
                # Import the handler from admin_command.py
                try:
                    from admin_command import handle_sync_models
                    await handle_sync_models(interaction, target, force, safe_followup_wrapper)
                except ImportError:
                    # Fallback to built-in implementation if import fails
                    # Sync models
                    if not force:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Confirmation Required",
                            description="This action will sync all models with their servers, which may take a long time. Use `force:true` to confirm.",
                            color=discord.Color.gold()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Model Sync Initiated",
                        description="Syncing all models with their servers. This may take a while...",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Unknown Action",
                    description=f"The action '{action}' is not recognized.",
                    color=discord.Color.red()
                ))
                
        except Exception as e:
            logger.error(f"Error in admin command: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            ))
    
    # Store the admin command
    registered_commands["admin"] = admin_command
    
    # Add manage command
    @bot.tree.command(name="manage", description="Manage models and servers")
    @app_commands.describe(
        action="Action to perform",
        type="Type of resource to manage",
        ip="Server IP address (for server actions)",
        port="Server port (default: 11434)",
        model_name="Model name (for model actions)",
        model_id="Model ID (for model actions)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Delete", value="delete"),
        app_commands.Choice(name="Sync", value="sync"),
        app_commands.Choice(name="Update", value="update")
    ])
    @app_commands.choices(type=[
        app_commands.Choice(name="Model", value="model"),
        app_commands.Choice(name="Server", value="server")
    ])
    async def manage_command(
        interaction: discord.Interaction,
        action: str,
        type: str,
        ip: str = None,
        port: int = 11434,
        model_name: str = None,
        model_id: int = None
    ):
        """Management command for models and servers"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        await safe_defer(interaction)
        
        try:
            # Handle model management
            if type == "model":
                if action == "add":
                    if not ip or not model_name:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To add a model, both `ip` and `model_name` parameters are required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Adding Model",
                        description=f"Attempting to add model '{model_name}' to server {ip}:{port}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                elif action == "delete":
                    if not model_id:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To delete a model, the `model_id` parameter is required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Deleting Model",
                        description=f"Attempting to delete model with ID {model_id}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                elif action == "sync":
                    if not model_id:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To sync a model, the `model_id` parameter is required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Syncing Model",
                        description=f"Attempting to sync model with ID {model_id}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                else:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Unknown Action",
                        description=f"The action '{action}' is not recognized for type 'model'.",
                        color=discord.Color.red()
                    ))
                    
            # Handle server management
            elif type == "server":
                if action == "add":
                    if not ip:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To add a server, the `ip` parameter is required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Adding Server",
                        description=f"Attempting to add server {ip}:{port}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                elif action == "delete":
                    if not ip:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To delete a server, the `ip` parameter is required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Deleting Server",
                        description=f"Attempting to delete server {ip}:{port}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                elif action == "sync":
                    if not ip:
                        await interaction.followup.send(embed=await format_embed_message(
                            title="Missing Parameters",
                            description="To sync a server, the `ip` parameter is required.",
                            color=discord.Color.red()
                        ))
                        return
                    
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Syncing Server",
                        description=f"Attempting to sync server {ip}:{port}",
                        color=discord.Color.blue()
                    ))
                    
                    # Implementation would go here
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Not Implemented",
                        description="This functionality is not yet fully implemented.",
                        color=discord.Color.gold()
                    ))
                    
                else:
                    await interaction.followup.send(embed=await format_embed_message(
                        title="Unknown Action",
                        description=f"The action '{action}' is not recognized for type 'server'.",
                        color=discord.Color.red()
                    ))
                    
            else:
                await interaction.followup.send(embed=await format_embed_message(
                    title="Unknown Type",
                    description=f"The type '{type}' is not recognized.",
                    color=discord.Color.red()
                ))
                
        except Exception as e:
            logger.error(f"Error in manage command: {str(e)}")
            await interaction.followup.send(embed=await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            ))
    
    # Store the manage command
    registered_commands["manage"] = manage_command
    
    # Return all registered commands
    return registered_commands