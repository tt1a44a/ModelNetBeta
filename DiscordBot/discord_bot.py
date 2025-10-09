#!/usr/bin/env python3
"""
Discord Bot for interacting with Ollama Models.
"""

import os
import json
import requests
import discord
import logging
import aiohttp
import asyncio
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from ollama_models import (
    setup_database, 
    get_models, 
    get_model_by_id, 
    add_model, 
    delete_model, 
    sync_models_with_server, 
    get_servers
)
import sys
import subprocess
from pathlib import Path
import sqlite3
import time
import commands_for_syncing  # Import the new module

# Added by migration script
from database import Database, init_database, DATABASE_TYPE, get_db_manager

# Thread pool for running sync functions in async context
_thread_pool = ThreadPoolExecutor(max_workers=10)

async def run_in_thread(func, *args, **kwargs):
    """
    Compatibility wrapper for asyncio.to_thread() (Python 3.9+)
    Works on all Python versions by using ThreadPoolExecutor
    """
    loop = asyncio.get_event_loop()
    pfunc = partial(func, *args, **kwargs)
    return await loop.run_in_executor(_thread_pool, pfunc)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("discord_bot.log")
    ]
)
logger = logging.getLogger('ollama_bot')

# Create specialized loggers
honeypot_logger = logging.getLogger('honeypot')
honeypot_handler = logging.FileHandler("honeypot_detection.log")
honeypot_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
honeypot_logger.addHandler(honeypot_handler)
honeypot_logger.setLevel(logging.INFO)

security_logger = logging.getLogger('security')
security_handler = logging.FileHandler("security.log")
security_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s'))
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)

# Load environment variables from .env file
load_dotenv()
    
# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents)

# Define database file location for SQLite only
DB_FILE = "ollama_instances.db"

def setup_database():
    """Set up the database tables if they don't exist yet"""
    try:
        # For SQLite, ensure the database directory exists
        if DATABASE_TYPE == "sqlite":
            db_dir = os.path.dirname(DB_FILE)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created database directory: {db_dir}")
        
        conn = Database()
        
        # Create servers table with appropriate syntax for the database type
        if DATABASE_TYPE == "postgres":
            # PostgreSQL uses SERIAL for auto-incrementing columns
            Database.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id SERIAL PRIMARY KEY,
                ip TEXT,
                port INTEGER,
                scan_date TEXT,
                UNIQUE(ip, port)
            )
            """)
            
            # Create models table
            Database.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id SERIAL PRIMARY KEY,
                endpoint_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                parameter_size TEXT,
                quantization_level TEXT,
                size_mb NUMERIC(12, 2),
                FOREIGN KEY (endpoint_id) REFERENCES servers (id),
                UNIQUE(endpoint_id, name)
            )
            """)
        else:
            # SQLite syntax (though we require PostgreSQL now)
            Database.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                port INTEGER,
                scan_date TEXT,
                UNIQUE(ip, port)
            )
            """)
            
            # Create models table
            Database.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                parameter_size TEXT,
                quantization_level TEXT,
                size_mb REAL,
                FOREIGN KEY (endpoint_id) REFERENCES servers (id),
                UNIQUE(endpoint_id, name)
            )
            """)
        
        # Commit handled by Database methods
        conn.close()
        logger.info("Database setup complete")
    except Exception as e:
        logger.error(f"Database setup error: {str(e)}")
        raise

# Global aiohttp session
session = None

async def validate_model_id(model_id):
    """
    Validate that a model ID exists and return its details.
    
    This function explicitly filters out:
    - Unverified endpoints (verified = 0)
    - Honeypots (is_honeypot = TRUE)
    - Inactive endpoints (is_active = FALSE)
    
    Args:
        model_id: The model ID to validate
        
    Returns:
        dict: A dictionary with model validation status and details
    """
    try:
        # Log the validation attempt
        security_logger.info(f"Validating model ID: {model_id}")
        
        # Query model info using the updated schema
        query = f"""
            SELECT m.id, m.name, e.ip, e.port, e.is_honeypot
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.id = %s 
              AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
              AND e.is_honeypot = {get_db_boolean(False)}
              AND e.is_active = {get_db_boolean(True)}
        """
        params = (model_id,)
        result = Database.fetch_one(query, params)
        
        if not result:
            security_logger.warning(f"Model ID {model_id} not found or failed security filters")
            return {
                "valid": False,
                "message": f"Error: Model with ID {model_id} not found in the database."
            }
        
        # Safety check to ensure we never return honeypots
        is_honeypot = result[4]
        if is_honeypot:
            honeypot_logger.error(f"CRITICAL: Honeypot endpoint (model ID: {model_id}) was selected despite filters!")
            security_logger.error(f"CRITICAL SECURITY BREACH: Honeypot endpoint (model ID: {model_id}) was selected despite filters!")
            return {
                "valid": False,
                "message": f"Error: Model with ID {model_id} failed safety checks."
            }
        
        security_logger.info(f"Model ID {model_id} validated successfully (endpoint: {result[2]}:{result[3]})")
        return {
            "valid": True,
            "model_id": result[0],
            "name": result[1],
            "ip": result[2],
            "port": result[3]
        }
    except Exception as e:
        logger.error(f"Error validating model ID: {str(e)}")
        security_logger.error(f"Exception during model validation: {str(e)}")
        return {
            "valid": False,
            "message": f"Error validating model ID: {str(e)}"
        }

async def check_server_connectivity(ip, port):
    """Check if an Ollama server is reachable."""
    global session
    try:
        if not session:
            # Create session if not initialized
            timeout = aiohttp.ClientTimeout(total=10, sock_connect=5, sock_read=5)
            session = aiohttp.ClientSession(timeout=timeout)
            
        # Format the IP for IPv6 compatibility
        if ":" in ip and not ip.startswith("["):
            api_ip = f"[{ip}]"
        else:
            api_ip = ip
            
        api_url = f"http://{api_ip}:{port}/api/version"
        
        async with session.get(api_url, timeout=5) as response:
            if response.status == 200:
                return True, None
            else:
                response_text = await response.text()
                return False, f"Server returned status {response.status}: {response_text}"
    except aiohttp.ClientConnectorError:
        return False, f"Could not connect to server. Please check the IP and port."
    except aiohttp.ClientResponseError as e:
        return False, f"Server responded with an error: {str(e)}"
    except asyncio.TimeoutError:
        return False, f"Connection timed out. Server may be down or unreachable."
    except Exception as e:
        logger.error(f"Error checking server connectivity: {str(e)}")
        return False, f"Error connecting to server: {str(e)}"

# Register additional commands from the commands_for_syncing module
# This will happen after the session is initialized in on_ready

# Define sorting choices for different contexts
model_sort_choices = [
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Count", value="count")
]

server_sort_choices = [
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Size", value="size")
]

model_server_sort_choices = [
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Size", value="size"),
    app_commands.Choice(name="IP", value="ip")
]

@bot.tree.command(name="ping", description="Check if the bot is responding")
async def ping_command(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        start_time = time.time()
        
        # Get current time with more precision for latency calculation
        response = await interaction.followup.send("Pong!")
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to ms
        
        # Edit the message with the ping time
        await response.edit(content=f"Pong! Response time: {response_time:.2f}ms")
        
    except Exception as e:
        logger.error(f"Error in ping command: {e}")
        await safe_followup(interaction, f"Error in ping command: {e}")

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord"""
    try:
        # Create global aiohttp session with proper timeouts
        global session
        # Increase timeouts to better handle model pulls and large responses
        timeout = aiohttp.ClientTimeout(
            total=120,      # 2 minutes total timeout
            sock_connect=30, # 30 seconds to establish connection
            sock_read=60    # 60 seconds to read a response chunk
        )
        session = aiohttp.ClientSession(timeout=timeout)
        
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        logger.info("------")
        
        # Start a keep-alive task for preventing disconnections
        bot.loop.create_task(keep_alive())
        
        # Ensure database connection is properly initialized before registering commands
        try:
            logger.info("Initializing database connection pool...")
            Database.ensure_pool_initialized()
            # Test the connection to make sure it's working
            result = Database.fetch_one("SELECT NOW()")
            if result:
                logger.info(f"Database connection verified at: {result[0]}")
            else:
                logger.warning("Database connection test returned no result")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
        
        # The explicitly approved commands for the streamlined bot
        approved_commands = [
            "ping", 
            "help", 
            "benchmark", 
            "manage_models",
            "model_status",
            "offline_endpoints",  # Add the new command
            "list_models", 
            "db_info", 
            "honeypot_stats",
            "quickprompt", 
            "chat",
            "find_model_endpoints",
            "all_models",
            "server_info",
            "models_with_servers",
            "cleanup"
        ]
        
        # Get all currently registered commands
        try:
            # First check if commands are already registered properly
            current_commands = await bot.tree.fetch_commands()
            current_command_names = [cmd.name for cmd in current_commands]
            logger.info(f"Current commands: {', '.join(current_command_names) if current_command_names else 'None'}")
            
            # Check if our commands list matches what's already registered
            missing_commands = [cmd for cmd in approved_commands if cmd not in current_command_names]
            extra_commands = [cmd for cmd in current_command_names if cmd not in approved_commands]
            
            if not missing_commands and not extra_commands:
                logger.info("Command registration is up to date - skipping sync to avoid rate limits")
                
                # Set bot status
                activity = discord.Activity(type=discord.ActivityType.watching, name="Ollama instances")
                await bot.change_presence(activity=activity)
                
                logger.info("Bot is ready!")
                print(f"Bot is ready! Logged in as {bot.user} (ID: {bot.user.id})")
                return
            else:
                logger.info(f"Command list needs updating - missing: {missing_commands}, extra: {extra_commands}")
                
                # Check if we've synced recently - to avoid rate limits, skip sync if it hasn't been long enough
                last_sync_time = getattr(bot, '_last_sync_time', 0)
                current_time = time.time()
                if current_time - last_sync_time < 3600:  # Less than 1 hour since last sync
                    logger.warning("Skipping command sync due to recent sync - avoiding rate limits")
                    
                    # Set bot status anyway
                    activity = discord.Activity(type=discord.ActivityType.watching, name="Ollama instances")
                    await bot.change_presence(activity=activity)
                    
                    logger.info("Bot is ready (with outdated commands)!")
                    print(f"Bot is ready! Logged in as {bot.user} (ID: {bot.user.id})")
                    return
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limited
                logger.warning(f"Rate limited when fetching commands - waiting {e.retry_after} seconds")
                
                # Set bot status anyway
                activity = discord.Activity(type=discord.ActivityType.watching, name="Ollama instances")
                await bot.change_presence(activity=activity)
                
                logger.info("Bot is ready (with existing commands due to rate limit)!")
                print(f"Bot is ready! Logged in as {bot.user} (ID: {bot.user.id})")
                return
            else:
                logger.error(f"HTTP error when fetching commands: {e}")
        
        try:
            # We need to update commands - only do this if absolutely necessary due to rate limits
            # Make sure ONLY the commands we want are in the command tree
            all_commands = {}
            for command in bot.tree.get_commands():
                all_commands[command.name] = command
                
            for cmd_name in list(all_commands.keys()):
                if cmd_name not in approved_commands:
                    logger.info(f"Removing unauthorized command: {cmd_name}")
                    bot.tree.remove_command(cmd_name)
            
            # Sync the commands - this will update Discord with our command list
            # Note: This is where rate limits often occur, so we limit how often we do this
            await bot.tree.sync()
            setattr(bot, '_last_sync_time', time.time())  # Record when we synced
            
            # Register with each guild for immediate availability
            guilds_updated = 0
            for guild in bot.guilds:
                try:
                    # Only sync with a few guilds to avoid rate limits
                    if guilds_updated < 2:  # Limit to 2 guilds max per startup
                        await bot.tree.sync(guild=guild)
                        logger.info(f"Synced commands with guild: {guild.name} (ID: {guild.id})")
                        guilds_updated += 1
                    else:
                        logger.info(f"Skipped syncing with guild {guild.name} to avoid rate limits")
                except Exception as e:
                    logger.error(f"Error syncing commands with guild {guild.name}: {e}")
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limited
                logger.warning(f"Rate limited when syncing commands - waiting {e.retry_after} seconds")
            else:
                logger.error(f"HTTP error when syncing commands: {e}")
        
        # Set bot status
        activity = discord.Activity(type=discord.ActivityType.watching, name="Ollama instances")
        await bot.change_presence(activity=activity)
        
        logger.info("Bot is ready!")
        print(f"Bot is ready! Logged in as {bot.user} (ID: {bot.user.id})")
        
    except Exception as e:
        logger.error(f"Error in on_ready: {str(e)}")
        print(f"Error in on_ready: {str(e)}")

async def keep_alive():
    """Maintains bot connection and database health with periodic checks"""
    logger.info("Connection maintenance task initiated")
    
    # Track consecutive failures to avoid spam during extended outages
    consecutive_db_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5
    
    while not bot.is_closed():
        try:
            # Log a heartbeat message every 5 minutes
            logger.debug("Connection maintenance heartbeat")
            
            # Check database connectivity and reconnect if needed
            if consecutive_db_errors < MAX_CONSECUTIVE_ERRORS:
                try:
                    # Execute a simple query to test DB connection
                    test_query = "SELECT 1;"
                    result = Database.fetch_one(test_query)
                    
                    if result and result[0] == 1:
                        # Reset the error counter upon successful query
                        if consecutive_db_errors > 0:
                            logger.info(f"Database connection restored after {consecutive_db_errors} failures")
                            consecutive_db_errors = 0
                        logger.debug("Database connection check successful")
                    else:
                        logger.warning("Database connection test returned unexpected result")
                        consecutive_db_errors += 1
                        
                        # Force reconnection
                        if hasattr(Database, 'reconnect'):
                            logger.info("Attempting to reconnect to database...")
                            Database.reconnect()
                            
                except Exception as e:
                    consecutive_db_errors += 1
                    logger.error(f"Database connection check failed: {str(e)}")
                    
                    # Attempt to reconnect if we're getting connection errors
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        if hasattr(Database, 'reconnect'):
                            logger.info("Attempting to reconnect to database...")
                            try:
                                Database.reconnect()
                                logger.info("Database reconnection initiated")
                            except Exception as reconnect_error:
                                logger.error(f"Database reconnection failed: {str(reconnect_error)}")
            
            # Longer wait after reaching max consecutive errors to avoid log spam
            if consecutive_db_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.warning(f"Database maintenance suspended after {MAX_CONSECUTIVE_ERRORS} consecutive failures")
                consecutive_db_errors += 1  # Keep incrementing to track extended outage duration
                
                # Try again after a longer period if extended outage
                if consecutive_db_errors % 12 == 0:  # Approx every hour (12 * 5 min)
                    logger.info(f"Attempting to resume database maintenance after extended outage ({consecutive_db_errors} failures)")
                    consecutive_db_errors = MAX_CONSECUTIVE_ERRORS - 1  # Reset to just below threshold
            
            # Standard heartbeat interval
            await asyncio.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"Error in connection maintenance: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute and try again

@bot.event
async def on_close():
    # Close aiohttp session when bot closes
    if session:
        await session.close()
        logger.info("Closed aiohttp session")
    
    # Close database connections cleanly
    try:
        logger.info("Closing database connections...")
        Database.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {str(e)}")

async def safe_defer(interaction):
    """Safely defer an interaction with error handling for expired interactions"""
    try:
        # Check if the interaction is already responded to
        if interaction.response.is_done():
            logger.debug(f"Interaction {interaction.id} has already been responded to")
            return True
        
        # Set a shorter timeout for deferring to avoid common timeouts
        logger.debug(f"Deferring interaction {interaction.id}")
        
        # Use a timeout to ensure defer doesn't hang
        try:
            # Give a reasonable timeout for the defer operation
            await asyncio.wait_for(
                interaction.response.defer(thinking=True, ephemeral=False),
                timeout=2.0
            )
            logger.debug(f"Successfully deferred interaction {interaction.id}")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Defer operation timed out for interaction {interaction.id}")
            # Try to proceed anyway
            return True
            
    except discord.errors.NotFound as e:
        if e.code == 10062:  # Unknown interaction error code
            logger.warning(f"Interaction {interaction.id} expired before deferring")
            return False
        else:
            logger.error(f"Unidentified NotFound error in defer operation: {e}")
            raise
    except Exception as e:
        logger.error(f"Error during defer operation: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        return False

async def safe_followup(interaction, content, ephemeral=False):
    """Safely send a followup message with error handling"""
    try:
        # For embeds, just send directly with length check
        if isinstance(content, discord.Embed):
            return await interaction.followup.send(content, ephemeral=ephemeral)
        
        # Check if content contains code blocks that might need to be preserved
        contains_codeblock = "```" in content
        
        # If content is too long and contains codeblocks, handle special splitting
        if len(content) > 2000 and contains_codeblock:
            # Find all code blocks in the content
            import re
            # Regex to find code blocks with or without language specification
            code_block_pattern = r'```(?:\w+)?\n([\s\S]*?)```'
            
            # Split the content around code blocks
            parts = re.split(code_block_pattern, content)
            
            # Extract the code blocks themselves
            code_blocks = re.findall(code_block_pattern, content)
            
            # Initialize variables for reconstructing the message
            messages = []
            current_message = ""
            
            # If the content starts with text before a code block
            if not content.startswith("```"):
                current_message = parts[0]
                parts = parts[1:]
            
            # Process each code block and the text after it
            for i, code_block in enumerate(code_blocks):
                # Determine the language if specified
                # Look for the language specifier in the original content
                content_before_this_block = content[:content.find(code_block)]
                last_code_marker = content_before_this_block.rfind("```")
                if last_code_marker >= 0:
                    # Extract the text between ``` and the newline
                    lang_line = content_before_this_block[last_code_marker+3:].split("\n")[0].strip()
                    lang_spec = lang_line if lang_line else ""
                else:
                    lang_spec = ""
                
                # Format the code block with language specifier
                if lang_spec:
                    formatted_block = f"```{lang_spec}\n{code_block}```"
                else:
                    formatted_block = f"```\n{code_block}```"
                
                # Check if adding this block would exceed Discord's limit
                if len(current_message) + len(formatted_block) > 1950:
                    # Send the current message before it gets too long
                    if current_message:
                        messages.append(current_message)
                    current_message = formatted_block
                else:
                    current_message += formatted_block
                
                # Add any text that follows this code block (if any)
                if i < len(parts) - 1:
                    text_after = parts[i + 1]
                    if len(current_message) + len(text_after) > 1950:
                        messages.append(current_message)
                        current_message = text_after
                    else:
                        current_message += text_after
            
            # Add any remaining content
            if current_message:
                messages.append(current_message)
            
            # Send all the message parts
            responses = []
            for i, msg in enumerate(messages):
                if i == 0:
                    responses.append(await interaction.followup.send(msg, ephemeral=ephemeral))
                else:
                    responses.append(await interaction.channel.send(msg))
            return responses
        
        # For simple content without code blocks or short enough content
        elif len(content) > 2000:
            # Split into multiple messages of 2000 characters or less
            messages = []
            for i in range(0, len(content), 1900):
                chunk = content[i:i+1900]
                
                # Add indicators for continuation
                if i > 0:
                    chunk = "... " + chunk
                if i + 1900 < len(content):
                    chunk = chunk + " ..."
                
                # Wrap non-embed content in code blocks to prevent message splitting
                # But preserve content that contains Discord markdown formatting
                if not (
                    "**" in chunk or  # Bold
                    "*" in chunk or   # Italic
                    "~~" in chunk or  # Strikethrough
                    "`" in chunk or   # Inline code
                    "```" in chunk or # Code block
                    ">" in chunk or   # Quote
                    "||" in chunk     # Spoiler
                ):
                    chunk = f"```\n{chunk}\n```"
                
                if i == 0:
                    messages.append(await interaction.followup.send(chunk, ephemeral=ephemeral))
                else:
                    messages.append(await interaction.channel.send(chunk))
            
            return messages
        else:
            # Standard handling for content within Discord's limits
            # Wrap non-embed content in code blocks to prevent message splitting
            # But preserve content that contains Discord markdown formatting
            if not (
                "**" in content or  # Bold
                "*" in content or   # Italic
                "~~" in content or  # Strikethrough
                "`" in content or   # Inline code
                "```" in content or # Code block
                ">" in content or   # Quote
                "||" in content     # Spoiler
            ):
                content = f"```\n{content}\n```"
                
            return await interaction.followup.send(content, ephemeral=ephemeral)
    except discord.errors.NotFound:
        logger.warning(f"Interaction {interaction.id} expired before followup could be sent")
        return None
    except discord.errors.HTTPException as e:
        logger.error(f"HTTP error sending followup: {str(e)}")
        # Try to send a simpler message if possible
        try:
            return await interaction.followup.send("```\nError sending response. Message may exceed length limitations.\n```", ephemeral=True)
        except:
            return None
    except Exception as e:
        logger.error(f"Error sending followup message: {str(e)}")
        return None

async def safe_response(interaction, content, ephemeral=False):
    """Safely send a direct response message with error handling"""
    try:
        # For embeds, just send directly with length check
        if isinstance(content, discord.Embed):
            return await interaction.response.send_message(content, ephemeral=ephemeral)
        
        # Check if content contains code blocks that might need to be preserved
        contains_codeblock = "```" in content
        
        # If content is too long and contains codeblocks, handle special splitting
        if len(content) > 2000 and contains_codeblock:
            # Need to defer first to enable followup messages
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=ephemeral)
            except:
                pass  # Already responded or deferred
                
            # Use safe_followup since we're sending multiple messages
            return await safe_followup(interaction, content, ephemeral=ephemeral)
        
        # For simple content without code blocks or short enough content
        elif len(content) > 2000:
            # Need to use followup for multiple messages
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=ephemeral)
            except:
                pass  # Already responded or deferred
                
            # Use safe_followup for sending multiple messages
            return await safe_followup(interaction, content, ephemeral=ephemeral)
        else:
            # Standard handling for content within Discord's limits
            # Wrap non-embed content in code blocks to prevent message splitting
            # But preserve content that contains Discord markdown formatting
            if not (
                "**" in content or  # Bold
                "*" in content or   # Italic
                "~~" in content or  # Strikethrough
                "`" in content or   # Inline code
                "```" in content or # Code block
                ">" in content or   # Quote
                "||" in content     # Spoiler
            ):
                content = f"```\n{content}\n```"
                
            return await interaction.response.send_message(content, ephemeral=ephemeral)
    except discord.errors.NotFound:
        logger.warning(f"Interaction {interaction.id} expired before response could be sent")
        return None
    except discord.errors.HTTPException as e:
        logger.error(f"HTTP error sending response: {str(e)}")
        # Try to send a simpler message if possible
        try:
            return await interaction.response.send_message("```\nError sending response. Message may exceed length limitations.\n```", ephemeral=True)
        except:
            return None
    except Exception as e:
        logger.error(f"Error sending response message: {str(e)}")
        return None

@bot.tree.command(name="listmodels", description="List all available Ollama models")
async def list_models(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        models = get_models()
        if not models:
            await safe_followup(interaction, "No models found.")
            return
        
        # Organize models by server
        servers = {}
        for model in models:
            model_id, ip, port, name, param_size, quant_level, size_mb = model
            server_key = f"{ip}:{port}"
            
            if server_key not in servers:
                servers[server_key] = []
                
            model_info = f"ID: {model_id}, Name: {name}"
            if param_size:
                model_info += f", Params: {param_size}"
            if quant_level:
                model_info += f", Quant: {quant_level}"
            if size_mb:
                model_info += f", Size: {size_mb} MB"
                
            servers[server_key].append(model_info)
        
        # Create a single consolidated message
        full_message = ""
        for server, model_list in servers.items():
            full_message += f"**Server: {server}**\n"
            for model_info in model_list:
                full_message += f"- {model_info}\n"
            full_message += "\n"  # Add extra newline between servers
            
        # Send as a single message
        await safe_followup(interaction, full_message)
            
    except Exception as e:
        logger.error(f"Error in list_models: {str(e)}")
        await safe_followup(interaction, f"Error listing models: {str(e)}")

@bot.tree.command(name="selectmodel", description="Select a model by ID")
async def select_model(interaction: discord.Interaction, model_id: int):
    if not await safe_defer(interaction):
        return
    
    try:
        # Validate the model ID
        validation = await validate_model_id(model_id)
        
        if not validation["valid"]:
            await safe_followup(interaction, validation["message"])
            return
        
        # Get the validated model data
        model_id = validation["model_id"]
        name = validation["name"]
        param_size = validation["param_size"]
        quant_level = validation["quant_level"]
        size_mb = validation["size_mb"]
        server_id = validation["server_id"]
        ip = validation["ip"]
        port = validation["port"]
        
        # Get scan date
        conn = Database()
        
        scan_date = Database.fetch_one("SELECT scan_date FROM servers WHERE id = ?", (server_id,))[0]
        conn.close()
        
        # Format a detailed response
        info_embed = discord.Embed(
            title=f"Model: {name}",
            description=f"Complete details for model ID: {model_id}",
            color=discord.Color.blue()
        )
        
        # Model details
        info_embed.add_field(name="Model ID", value=str(model_id), inline=True)
        info_embed.add_field(name="Name", value=name, inline=True)
        info_embed.add_field(name="Parameters", value=param_size or "Unknown", inline=True)
        info_embed.add_field(name="Quantization", value=quant_level or "Unknown", inline=True)
        
        if size_mb:
            size_formatted = f"{size_mb:.2f} MB"
            if size_mb > 1024:
                size_formatted += f" ({size_mb/1024:.2f} GB)"
            info_embed.add_field(name="Size", value=size_formatted, inline=True)
        else:
            info_embed.add_field(name="Size", value="Unknown", inline=True)
        
        # Server details
        info_embed.add_field(name="Server ID", value=str(server_id), inline=True)
        info_embed.add_field(name="Server", value=f"{ip}:{port}", inline=True)
        info_embed.add_field(name="Last Scan", value=scan_date, inline=True)
        
        # Add usage examples
        info_embed.add_field(
            name="Usage Examples",
            value=(
                f"**Interact with model:**\n"
                f"`/interact model_id:{model_id} message:\"Your prompt here\"`\n\n"
                f"**Benchmark model:**\n"
                f"`/benchmark model_id:{model_id}`"
            ),
            inline=False
        )
        
        info_embed.set_footer(text=f"Use this model ID ({model_id}) with the interact command to chat with this model")
        
        # Send the embed response
        await safe_followup(interaction, info_embed)
        
    except Exception as e:
        logger.error(f"Error in select_model: {str(e)}")
        await safe_followup(interaction, f"Error selecting model: {str(e)}")

@bot.tree.command(name="addmodel", description="Add a new Ollama model or pull model to existing endpoint")
async def add_model_command(
    interaction: discord.Interaction, 
    ip: str, 
    port: int, 
    name: str, 
    info: str = "{}"
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Try to parse the info as JSON
        try:
            json_info = json.loads(info)
        except json.JSONDecodeError:
            json_info = {}
        
        # Clean the IP to remove any trailing/leading colons
        clean_ip = ip.strip(":")
        
        # Check if server is reachable before attempting to pull
        is_reachable, error = await check_server_connectivity(clean_ip, port)
        if not is_reachable:
            await safe_followup(interaction, f"Error: Server {clean_ip}:{port} is not reachable: {error}")
            return
        
        # First, let the user know we're starting the pull process
        await safe_followup(interaction, f"📥 Starting pull request for model `{name}` on server {clean_ip}:{port}...")
        
        # Initialize variables to track download progress
        last_update_time = time.time()
        last_status = None
        current_digest = None
        total_size = None
        completed_size = None
        
        # Use aiohttp instead of requests for async operation
        try:
            # Prepare the pull request payload according to Ollama API docs
            pull_payload = {
                "model": name,  # Per API docs, this should be "model" not "name"
                "insecure": json_info.get("insecure", False),
                "stream": True  # Enable streaming to track progress
            }
            
            logger.info(f"Pulling model {name} with payload: {pull_payload}")
            
            async with session.post(
                f"http://{clean_ip}:{port}/api/pull",
                json=pull_payload,
                timeout=30  # Initial connection timeout
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    await safe_followup(interaction, f"⚠️ Error: Failed to start model pull: {response_text}")
                    return
                
                # Model pull started successfully - add to database
                model_id = add_model(clean_ip, port, name, info)
                status_message = await safe_followup(
                    interaction, 
                    f"✅ Pull request initiated for model `{name}` on {clean_ip}:{port}.\n"
                    f"📊 Added to database with ID: {model_id}\n"
                    f"⏳ Downloading model... (0%)"
                )
                
                # Process the streaming response to track progress
                async for line in response.content:
                    try:
                        if not line.strip():
                            continue
                            
                        data = json.loads(line)
                        status = data.get("status")
                        
                        # Only update message if status has changed or significant progress has been made
                        current_time = time.time()
                        should_update = (
                            status != last_status or 
                            current_time - last_update_time > 3  # Update at least every 3 seconds
                        )
                        
                        if status == "pulling manifest":
                            if should_update:
                                await interaction.edit_original_response(
                                    content=f"📋 Pulling manifest for model `{name}`..."
                                )
                                last_update_time = current_time
                                last_status = status
                                
                        elif status == "downloading":
                            # Track download progress
                            current_digest = data.get("digest", "unknown")
                            total_size = data.get("total", 0)
                            completed_size = data.get("completed", 0)
                            
                            if total_size and completed_size:
                                percent = min(100, int((completed_size / total_size) * 100))
                                
                                # Update progress less frequently to avoid rate limits
                                if should_update:
                                    # Format sizes for better readability
                                    total_gb = total_size / (1024**3)
                                    completed_gb = completed_size / (1024**3)
                                    
                                    progress_bar = "█" * (percent // 5) + "░" * (20 - (percent // 5))
                                    
                                    await interaction.edit_original_response(
                                        content=(
                                            f"📥 Downloading model `{name}` on {clean_ip}:{port}...\n"
                                            f"📦 Digest: {current_digest[:12]}...\n"
                                            f"⏳ Progress: {percent}% |{progress_bar}| {completed_gb:.2f}GB / {total_gb:.2f}GB"
                                        )
                                    )
                                    last_update_time = current_time
                                    last_status = status
                                    
                        elif status == "verifying sha256 digest":
                            if should_update:
                                await interaction.edit_original_response(
                                    content=f"🔒 Verifying SHA256 digest for model `{name}`..."
                                )
                                last_update_time = current_time
                                last_status = status
                                
                        elif status == "writing manifest":
                            if should_update:
                                await interaction.edit_original_response(
                                    content=f"📝 Writing manifest for model `{name}`..."
                                )
                                last_update_time = current_time
                                last_status = status
                                
                        elif status == "removing any unused layers":
                            if should_update:
                                await interaction.edit_original_response(
                                    content=f"🧹 Cleaning up unused layers for model `{name}`..."
                                )
                                last_update_time = current_time
                                last_status = status
                                
                        elif status == "success":
                            # Final success message with full details
                            await interaction.edit_original_response(
                                content=(
                                    f"✅ Successfully pulled model `{name}` on {clean_ip}:{port}\n"
                                    f"📊 Database ID: {model_id}\n"
                                    f"🔗 Server URL: http://{clean_ip}:{port}\n"
                                    f"ℹ️ Use `/interact {model_id} <your message>` to chat with this model"
                                )
                            )
                            
                            # Sync with server to update model details
                            try:
                                await sync_models_with_server_async(clean_ip, port)
                                logger.info(f"Synced models for server {clean_ip}:{port} after successful pull")
                            except Exception as sync_error:
                                logger.error(f"Error syncing models after pull: {str(sync_error)}")
                            
                            return
                            
                        elif status and status.startswith("error"):
                            error_msg = data.get("error", "Unknown error")
                            await interaction.edit_original_response(
                                content=f"❌ Error pulling model `{name}`: {error_msg}"
                            )
                            return
                            
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
                    except Exception as e:
                        logger.error(f"Error processing streaming response: {str(e)}")
                
                # If we get here without a success status, show a final status message
                if last_status != "success":
                    await interaction.edit_original_response(
                        content=(
                            f"⚠️ Pull process for `{name}` on {clean_ip}:{port} is continuing in the background.\n"
                            f"The model has been added to the database with ID {model_id}.\n"
                            f"Last status: {last_status or 'Unknown'}"
                        )
                    )
                    
        except asyncio.TimeoutError:
            # Initial connection timeout
            await safe_followup(interaction, 
                f"⏱️ Connection timed out when attempting to reach {clean_ip}:{port}.\n"
                f"The pull request might still be processing in the background.\n" 
                f"Check server status with `/checkserver {clean_ip} {port}` later."
            )
        except aiohttp.ClientError as e:
            await safe_followup(interaction, f"🌐 Connection error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in add_model: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        await safe_followup(interaction, f"❌ Error adding model: {str(e)}")

@bot.tree.command(name="deletemodel", description="Delete a model from Ollama server and database")
async def delete_model_command(interaction: discord.Interaction, model_id: int):
    if not await safe_defer(interaction):
        return
    
    try:
        # Validate the model ID
        validation = await validate_model_id(model_id)
        
        if not validation["valid"]:
            await safe_followup(interaction, validation["message"])
            return
        
        # Get the validated model data
        model_id = validation["model_id"]
        name = validation["name"]
        ip = validation["ip"]
        port = validation["port"]
        
        # First, make API request to delete the model from the Ollama server
        await safe_followup(interaction, f"Attempting to delete model {name} from {ip}:{port}...")
        
        try:
            # Use aiohttp instead of requests for async operation
            async with session.delete(
                f"http://{ip}:{port}/api/delete",
                json={"model": name},  # Use "model" instead of "name" for consistency with Ollama API
                timeout=10
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    await safe_followup(interaction, f"Error: Failed to delete model from server: {response_text}")
                    return
                
                # If API call was successful, remove from our database
                delete_model(model_id)
                await safe_followup(interaction, f"Model {name} deleted successfully from server {ip}:{port} and database.")
        except asyncio.TimeoutError:
            await safe_followup(interaction, f"Connection timed out when attempting to reach {ip}:{port}")
    
    except aiohttp.ClientError as e:
        logger.error(f"Connection error in delete_model: {str(e)}")
        await safe_followup(interaction, f"Connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in delete_model: {str(e)}")
        await safe_followup(interaction, f"Error: {str(e)}")

@bot.tree.command(name="interact", description="Interact with a selected Ollama model")
async def interact_with_model(
    interaction: discord.Interaction, 
    model_id: int, 
    message: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1000
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Validate the model ID
        validation = await validate_model_id(model_id)
        
        if not validation["valid"]:
            await safe_followup(interaction, validation["message"])
            return
        
        # Get the validated model data
        model_id = validation["model_id"]
        name = validation["name"]
        ip = validation["ip"]
        port = validation["port"]
        
        # Build the request based on provided parameters
        request_data = {
            "model": name,
            "prompt": message,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add system prompt if provided
        if system_prompt:
            request_data["system"] = system_prompt
        
        await safe_followup(interaction, f"Sending request to {name} on {ip}:{port}...")
        
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
                    
                    response_text += stats
                    
                    # Format the response with bold header but keep the model's output as is
                    formatted_response = f"**Response from {name}:**\n{response_text}"
                        
                    await safe_followup(interaction, formatted_response)
                else:
                    response_text = await response.text()
                    await safe_followup(interaction, f"Error: {response.status} - {response_text}")
        except asyncio.TimeoutError:
            await safe_followup(interaction, "Request timed out. The model may be taking too long to respond.")
        except aiohttp.ClientError as e:
            logger.error(f"Connection error in interact: {str(e)}")
            await safe_followup(interaction, f"Request failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error in interact: {str(e)}")
        await safe_followup(interaction, f"Error: {str(e)}")

@bot.tree.command(name="help", description="Show help information")
async def help_command(interaction: discord.Interaction):
    """Display help information"""
    if not await safe_defer(interaction):
        return
    
    try:
        # Create the main help embed
        embed = discord.Embed(
            title="ModelNet Bot Help",
            description="This bot helps you interact with Ollama models hosted across many endpoints.",
            color=discord.Color.blue()
        )
        
        # Commands section
        embed.add_field(
            name="**📋 Basic Commands**",
            value=(
                "`/quickprompt <model_name> <prompt>` - Chat with any model by name\n"
                "`/list_models` - Browse available models with filters\n"
                "`/find_model_endpoints <model_name>` - Find endpoints hosting a specific model\n"
                "`/model_status <ip> <port>` - Check which models are loaded on a server\n"
                "`/db_info` - View database statistics"
            ),
            inline=False
        )
        
        # Model filtering section
        embed.add_field(
            name="**🔍 Model Selection & Filtering**",
            value=(
                "`/searchmodels <model_name>` - Search for models by name\n"
                "`/modelsbyparam <parameter_size>` - Find models with specific parameters\n"
                "`/allmodels` - List all available models"
            ),
            inline=False
        )
        
        # Add section about honeypot protection
        embed.add_field(
            name="**🛡️ Honeypot Protection**", 
            value=(
                "This bot automatically detects and filters out honeypot endpoints.\n"
                "All model interactions use only verified, legitimate endpoints.\n"
                "Honeypot statistics (via `/honeypot_stats`) are for informational purposes only."
            ), 
            inline=False
        )
        
        # Maintenance commands
        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="**⚙️ Admin Commands**",
                value=(
                    "`/addmodel <ip> <port> <name>` - Add a new model to the database\n"
                    "`/syncserver <ip> <port>` - Sync server models with database\n"
                    "`/checkserver <ip> <port>` - Check available models on server\n"
                    "`/cleanup` - Clean up duplicate database entries\n"
                    "`/offline_endpoints` - View and manage offline endpoints\n"
                ),
                inline=False
            )
        
        # Footer with version info
        embed.set_footer(text="ModelNet Bot v2.0")
        
        await safe_followup(interaction, "", embed=embed)
        
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}")
        await safe_followup(interaction, f"Error displaying help: {str(e)}")

@bot.tree.command(name="checkserver", description="Check which models are available on a specific server")
async def check_server(interaction: discord.Interaction, ip: str, port: int):
    if not await safe_defer(interaction):
        return
    
    try:
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
            
    except aiohttp.ClientError as e:
        logger.error(f"Connection error in check_server: {str(e)}")
        await safe_followup(interaction, f"Connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in check_server: {str(e)}")
        await safe_followup(interaction, f"Error: {str(e)}")

@bot.tree.command(name="syncserver", description="Sync the database with models actually on the server")
async def sync_server(interaction: discord.Interaction, ip: str, port: int):
    if not await safe_defer(interaction):
        return
    
    try:
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
    except Exception as e:
        logger.error(f"Error in sync_server: {str(e)}")
        await safe_followup(interaction, f"Error synchronizing models: {str(e)}")

@bot.tree.command(name="listservers", description="List all Ollama servers in the database")
async def list_servers(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
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
    except Exception as e:
        logger.error(f"Error in list_servers: {str(e)}")
        await safe_followup(interaction, f"Error listing servers: {str(e)}")

@bot.tree.command(name="benchmark", description="Run benchmark on a specific model and server")
async def benchmark_model(
    interaction: discord.Interaction, 
    model_id: int = None,
    server_ip: str = None,
    server_port: int = None,
    model_name: str = None
):
    if not await safe_defer(interaction):
        return
    
    try:
        # If model_id is provided, get the model details
        if model_id is not None:
            # Validate the model ID
            validation = await validate_model_id(model_id)
            
            if not validation["valid"]:
                await safe_followup(interaction, validation["message"])
                return
            
            # Get the validated model data
            model_id = validation["model_id"]
            name = validation["name"]
            ip = validation["ip"]
            port = validation["port"]
            
            await safe_followup(interaction, f"Initiating benchmark for model {name} on {ip}:{port}...")
            
            # Call the benchmark script with the model details
            benchmark_path = Path(__file__).parent.parent / "ollama_benchmark.py"
            cmd = [sys.executable, str(benchmark_path), "run", "--server", ip, "--port", str(port), "--model-name", name]
            
        # If direct server/model info is provided
        elif server_ip and model_name:
            port = server_port or 11434  # Default port if not specified
            await safe_followup(interaction, f"Initiating benchmark for model {model_name} on {server_ip}:{port}...")
            
            # Call the benchmark script with the provided details
            benchmark_path = Path(__file__).parent.parent / "ollama_benchmark.py"
            cmd = [sys.executable, str(benchmark_path), "run", "--server", server_ip, "--port", str(port), "--model-name", model_name]
            
        else:
            await safe_followup(interaction, "Please provide either a model_id or both server_ip and model_name parameters.")
            return
        
        # Run the benchmark process in a non-blocking way
        await safe_followup(interaction, "Benchmark process initiated. This operation may take several minutes. Results will be provided upon completion.")
        
        # Create a task to run the benchmark
        asyncio.create_task(run_benchmark_async(interaction, cmd))
        
    except Exception as e:
        logger.error(f"Error initiating benchmark: {str(e)}")
        await safe_followup(interaction, f"Error running benchmark: {str(e)}")

async def run_benchmark_async(interaction, cmd):
    """Run benchmark as an async task and post results when done"""
    try:
        # Create process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for process to complete
        stdout, stderr = await process.communicate()
        
        # Process complete - check results
        stdout_content = stdout.decode('utf-8')
        stderr_content = stderr.decode('utf-8')
        
        if process.returncode != 0:
            # Error occurred
            if stderr_content:
                error_msg = f"Benchmark operation failed with error:\n```\n{stderr_content[:1000]}...\n```"
                await safe_followup(interaction, error_msg)
            else:
                await safe_followup(interaction, "Benchmark operation failed with an unspecified error.")
            return
        
        # If successful, send summarized results
        # Extract the most important sections (looking for specific headers)
        lines = stdout_content.splitlines()
        
        # Find BENCHMARK RESULTS section
        result_section_started = False
        result_lines = []
        summary_started = False
        summary_lines = []
        
        for line in lines:
            if "BENCHMARK RESULTS" in line:
                result_section_started = True
                result_lines.append(line)
            elif result_section_started and line.strip():
                result_lines.append(line)
            elif "BENCHMARK SUMMARY" in line:
                summary_started = True
                summary_lines.append(line)
            elif summary_started and line.strip():
                summary_lines.append(line)
        
        # Send the results and summary (if found)
        if result_lines:
            # Send just the most important parts, limited to avoid Discord limits
            results_text = "\n".join(result_lines[:30])
            # Remove unnecessary code block wrapping as safe_followup will add it
            await safe_followup(interaction, f"Benchmark results:\n{results_text}")
            
        if summary_lines:
            summary_text = "\n".join(summary_lines)
            # Remove unnecessary code block wrapping as safe_followup will add it
            await safe_followup(interaction, f"Benchmark summary:\n{summary_text}")
            
        if not result_lines and not summary_lines:
            # If we couldn't find specific sections, just send the last bit
            truncated_output = "\n".join(lines[-25:])
            # Remove unnecessary code block wrapping as safe_followup will add it
            await safe_followup(interaction, f"Benchmark completed. Output:\n{truncated_output}")
    except Exception as e:
        logger.error(f"Error in benchmark process: {str(e)}")
        await safe_followup(interaction, f"Error during benchmark execution: {str(e)}")

async def sync_models_with_server_async(ip, port):
    """Async version of sync_models_with_server using aiohttp"""
    from ollama_models import sync_models_with_server
    
    # Create a task in the default thread pool to run the sync function
    # This allows the blocking database operations to run without blocking the main thread
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: sync_models_with_server(ip, port))

@bot.tree.command(name="searchmodels", description="Search for models by name with sorting options")
@app_commands.describe(
    model_name="Part of the model name to search for",
    sort_by="Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)",
    limit="Maximum number of results to return"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Count", value="count")
])
async def search_models(
    interaction: discord.Interaction,
    model_name: str,
    sort_by: str = None,
    descending: bool = True,
    limit: int = 25
):
    if not await safe_defer(interaction):
        return
    
    try:
        conn = Database()
        
        # Default sorting - by server count in descending order
        orderby = "server_count DESC"
        
        # Add wildcards to search pattern
        search = "%" + model_name + "%"
        
        # Search query with improved sorting
        query = f"""
            SELECT 
                m.name, 
                m.parameter_size, 
                m.quantization_level, 
                COUNT(*) as server_count
            FROM models m
            WHERE m.name LIKE ?
            GROUP BY m.name, m.parameter_size, m.quantization_level
            ORDER BY {orderby}
            LIMIT ?
        """
        
        # Define the parameters once
        query_params = (search, limit)
        
        # Execute and fetch the results with the same parameters
        Database.execute(query, query_params)
        
        results = Database.fetch_all(query, query_params)
        
        if not results:
            await safe_followup(interaction, f"No models found containing '{model_name}'")
            conn.close()
            return
        
        # Format the results
        message = f"**Models containing '{model_name}'**\nFound {len(results)} unique models\n\n"
        message += "Model Name | Parameters | Quantization | Count | Endpoints\n"
        message += "-" * 90 + "\n"
        
        for model in results:
            name, params, quant, count = model
            
            # Get ALL servers for this model (not just examples)
            servers_query = """
                SELECT m.id, s.ip, s.port
                FROM models m
                JOIN endpoints s ON m.endpoint_id = s.id
                WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
            """
            servers_params = (name, params, quant)
            servers = Database.fetch_all(servers_query, servers_params)
            
            # Trim long model names
            display_name = name
            if len(display_name) > 20:
                display_name = name[:17] + "..."
                
            # Add this model to the message with header info
            message += f"{display_name} | {params or 'N/A'} | {quant or 'N/A'} | {count} | "
            
            # Check if endpoint list is too long
            if len(servers) > 10:
                # List the first 5 servers
                servers_text = "\n  • " + "\n  • ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers[:5]])
                message += f"{servers_text}\n  • ... and {len(servers) - 5} more endpoints\n"
            else:
                # List all servers with bullet points for better readability
                servers_text = "\n  • " + "\n  • ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers])
                message += f"{servers_text}\n"
            
        # Check if message is too long and truncate if needed
        if len(message) > 1900:
            # Truncate and indicate there's more
            message = message[:1850] + "\n... (additional content truncated) ..."
            
        # Don't wrap in code blocks here as safe_followup will do it
        await safe_followup(interaction, message)
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in search_models: {str(e)}")
        await safe_followup(interaction, f"Error searching models: {str(e)}")

@bot.tree.command(name="modelsbyparam", description="Find models with specific parameter size")
@app_commands.describe(
    parameter_size="Parameter size to search for (e.g. 7B, 13B)",
    sort_by="Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)",
    limit="Maximum number of results to return"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Count", value="count")
])
async def models_by_param(
    interaction: discord.Interaction,
    parameter_size: str,
    sort_by: str = None,
    descending: bool = True,
    limit: int = 25
):
    if not await safe_defer(interaction):
        return
    
    try:
        conn = Database()
        
        # Default sorting
        orderby = "server_count DESC"
        
        # Apply sorting options if provided
        if sort_by:
            if sort_by == "name":
                if descending:
                    orderby = "name DESC"
                else:
                    orderby = "name ASC"
            elif sort_by == "params":
                # Simplify the parameter sorting to avoid complex nested CASE expressions
                orderby = """
                    CASE 
                        WHEN parameter_size IS NULL OR parameter_size = '' THEN 0
                        WHEN parameter_size ~ '^[0-9]+(\\.[0-9]+)?[Bb]$' THEN 
                            CAST(TRIM(TRAILING 'B' FROM TRIM(TRAILING 'b' FROM parameter_size)) AS NUMERIC)
                        WHEN parameter_size ~ '^[0-9]+(\\.[0-9]+)?$' THEN 
                            CAST(parameter_size AS NUMERIC)
                        ELSE 0
                    END """ + ("DESC" if descending else "ASC")
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
        
        # Add wildcards to search pattern
        search = "%" + parameter_size + "%"
        
        # Search query with improved sorting
        query = f"""
            SELECT 
                m.name, 
                m.parameter_size, 
                m.quantization_level, 
                COUNT(*) as server_count
            FROM models m
            WHERE m.parameter_size LIKE ?
            GROUP BY m.name, m.parameter_size, m.quantization_level
            ORDER BY {orderby}
            LIMIT ?
        """
        
        # Define query parameters
        query_params = (search, limit)
        Database.execute(query, query_params)
        
        results = Database.fetch_all(query, query_params)
        
        if not results:
            await safe_followup(interaction, f"No models found with parameter size containing '{parameter_size}'")
            conn.close()
            return
        
        # Format the results
        message = f"**Models with parameter size containing '{parameter_size}'**\nFound {len(results)} unique models\n\n"
        message += "Model Name | Parameters | Quantization | Count | Example Servers (ID:IP:Port)\n"
        message += "-" * 90 + "\n"
        
        for model in results:
            name, params, quant, count = model
            
            # Get example servers for this model WITH MODEL IDs
            servers_query = """
                SELECT m.id, s.ip, s.port
                FROM models m
                JOIN endpoints s ON m.endpoint_id = s.id
                WHERE m.name = ? AND m.parameter_size = ? AND m.quantization_level = ?
                LIMIT 3
            """
            servers_params = (name, params, quant)
            Database.execute(servers_query, servers_params)
            
            servers = Database.fetch_all(servers_query, servers_params)
            servers_text = ", ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers])
            
            if count > 3:
                servers_text += f" (+{count-3} more)"
            
            # Trim long model names
            display_name = name
            if len(display_name) > 20:
                display_name = name[:17] + "..."
                
            # Add this model to the message
            message += f"{display_name} | {params or 'N/A'} | {quant or 'N/A'} | {count} | {servers_text}\n"
        
        # Check if message is too long and truncate if needed
        if len(message) > 1900:
            # Truncate and indicate there's more
            message = message[:1850] + "\n... (additional models truncated) ..."
            
        # Don't wrap in code blocks here as safe_followup will do it
        await safe_followup(interaction, message)
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in models_by_param: {str(e)}")
        await safe_followup(interaction, f"Error finding models by parameter size: {str(e)}")

@bot.tree.command(name="allmodels", description="List all models with sorting options")
@app_commands.describe(
    sort_by="Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)",
    limit="Maximum number of results to return"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Count", value="count")
])
async def all_models(
    interaction: discord.Interaction,
    sort_by: str = None,
    descending: bool = True,
    limit: int = 25
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Default sorting
        orderby = "server_count DESC"
        
        # Apply sorting options if provided
        if sort_by:
            if sort_by == "name":
                orderby = "name " + ("DESC" if descending else "ASC")
            elif sort_by == "params":
                orderby = f"""
                CASE 
                    WHEN parameter_size LIKE '%B' THEN 
                        CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL)
                    ELSE 0
                END {("DESC" if descending else "ASC")}"""
            elif sort_by == "quant":
                orderby = "quantization_level " + ("DESC" if descending else "ASC")
            elif sort_by == "count":
                orderby = "server_count " + ("DESC" if descending else "ASC")
        
        # Safety check for limit parameter
        safe_limit = max(1, min(500, limit))  # Ensure limit is between 1 and 500
        
        # Query for all models with pagination - using PostgreSQL placeholder syntax
        query = f"""
            SELECT 
                name, 
                parameter_size, 
                quantization_level, 
                COUNT(*) as server_count
            FROM models
            GROUP BY name, parameter_size, quantization_level
            ORDER BY {orderby}
            LIMIT %s
        """
        
        # Execute and fetch results
        results = Database.fetch_all(query, (safe_limit,))
        
        if not results or len(results) == 0:
            await safe_followup(interaction, "No models found in the database.")
            return
        
        # Format the results
        message = f"**All Models**\nShowing {len(results)} unique models (limit: {safe_limit})\n\n"
        message += "Model Name | Parameters | Quantization | Count | Example Servers\n"
        message += "-" * 90 + "\n"
        
        for model in results:
            name, params, quant, count = model
            
            # Get example endpoints with model IDs for this model
            servers_query = """
                SELECT m.id, e.ip, e.port
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                WHERE m.name = %s 
                  AND (m.parameter_size = %s OR (m.parameter_size IS NULL AND %s IS NULL))
                  AND (m.quantization_level = %s OR (m.quantization_level IS NULL AND %s IS NULL))
                  AND e.verified = {get_db_boolean(True)}
                LIMIT 3
            """
            servers_params = (name, params, params, quant, quant)
            servers = Database.fetch_all(servers_query, servers_params) or []
            
            servers_text = ", ".join([f"ID:{s[0]}:{s[1]}:{s[2]}" for s in servers]) if servers else "None"
            
            if count > 3:
                servers_text += f" (+{count-3} more)"
            
            # Trim long model names
            display_name = name
            if len(display_name) > 20:
                display_name = name[:17] + "..."
                
            # Add this model to the message
            message += f"{display_name} | {params or 'N/A'} | {quant or 'N/A'} | {count} | {servers_text}\n"
        
        # Check if message is too long and truncate if needed
        if len(message) > 1900:
            # Truncate and indicate there's more
            message = message[:1850] + "\n... (additional models truncated) ..."
            
        # Don't wrap in code blocks here as safe_followup will do it
        await safe_followup(interaction, message)
        
    except Exception as e:
        logger.error(f"Error in all_models: {str(e)}\nQuery: {query if 'query' in locals() else 'unknown'}")
        await safe_followup(interaction, f"Error retrieving models: {str(e)}")

@bot.tree.command(name="serverinfo", description="Show detailed info about a specific server")
@app_commands.describe(
    ip="IP address of the server",
    port="Port number (defaults to 11434 if not specified)",
    sort_by="Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Size", value="size")
])
async def server_info(
    interaction: discord.Interaction,
    ip: str,
    port: int = None,
    sort_by: str = None,
    descending: bool = True
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Clean IP address
        clean_ip = ip.strip(":")
        
        # Look for endpoint(s) by IP and optional port
        if port is not None:
            query_endpoints = """
                SELECT e.id, e.scan_date 
                FROM endpoints e
                WHERE e.ip = %s AND e.port = %s AND e.verified = {get_db_boolean(True)}
            """
            endpoint_params = (clean_ip, port)
            endpoints = Database.fetch_all(query_endpoints, endpoint_params)
            if not endpoints or len(endpoints) == 0:
                await safe_followup(interaction, f"No verified endpoint found with IP {clean_ip} and port {port}")
                return
        else:
            query_endpoints = """
                SELECT e.id, e.port, e.scan_date 
                FROM endpoints e
                WHERE e.ip = %s AND e.verified = {get_db_boolean(True)}
            """
            endpoint_params = (clean_ip,)
            endpoints = Database.fetch_all(query_endpoints, endpoint_params)
            if not endpoints or len(endpoints) == 0:
                await safe_followup(interaction, f"No verified endpoints found with IP {clean_ip}")
                return
        
        # Default sorting
        orderby = "name ASC"
        
        # Apply sorting options if provided
        if sort_by:
            if sort_by == "name":
                orderby = "name " + ("DESC" if descending else "ASC")
            elif sort_by == "params":
                orderby = """
                    CASE 
                        WHEN parameter_size IS NULL THEN 0
                        WHEN parameter_size = '' THEN 0
                        WHEN parameter_size LIKE '%B' THEN 
                            CASE 
                                WHEN CAST(REPLACE(REPLACE(REPLACE(parameter_size, 'B', ''), '.', ''), ' ', '') AS TEXT) ~ '^[0-9]+$' THEN
                                    CAST(REPLACE(REPLACE(REPLACE(parameter_size, 'B', ''), '.', ''), ' ', '') AS REAL) 
                                ELSE 0 
                            END
                        ELSE 0
                    END """ + ("DESC" if descending else "ASC")
            elif sort_by == "quant":
                orderby = "quant " + ("DESC" if descending else "ASC")
            elif sort_by == "size":
                orderby = "size_mb " + ("DESC" if descending else "ASC")
            elif sort_by == "ip":
                orderby = "ip " + ("DESC" if descending else "ASC")
        
        # Process each endpoint
        for endpoint in endpoints:
            if port is not None:
                endpoint_id, scan_date = endpoint
                endpoint_port = port
            else:
                endpoint_id, endpoint_port, scan_date = endpoint
            
            # Get models for this endpoint
            models_query = f"""
                SELECT id, name, parameter_size, quantization_level, size_mb
                FROM models
                WHERE endpoint_id = %s
                ORDER BY {orderby}
            """
            
            models = Database.fetch_all(models_query, (endpoint_id,))
            model_count = len(models) if models else 0
            
            # Format the results
            message = f"**Server Info: {clean_ip}:{endpoint_port}**\n"
            message += f"Endpoint ID: {endpoint_id}\n"
            message += f"Last scan: {scan_date}\n"
            message += f"Models: {model_count}\n\n"
            
            if model_count > 0:
                message += "ID | Model Name | Parameters | Quantization | Size (MB)\n"
                message += "-" * 70 + "\n"
                
                for model in models:
                    model_id, name, params, quant, size = model
                    
                    # Handle NULL values with defaults
                    display_name = name or "Unknown"
                    display_params = params or "N/A"
                    display_quant = quant or "N/A"
                    display_size = f"{size:.2f}" if size else "N/A"
                    
                    # Trim long model names
                    if len(display_name) > 20:
                        display_name = display_name[:17] + "..."
                    
                    # Add this model to the message
                    message += f"{model_id} | {display_name} | {display_params} | {display_quant} | {display_size}\n"
                
                message += "\nUse the `/benchmark` command with these model IDs to test performance."
            else:
                message += "No models found for this server."
            
            # Check if message is too long and truncate if needed
            if len(message) > 1900:
                message = message[:1850] + "\n... (additional models truncated) ..."
            
            await safe_followup(interaction, message)
        
    except Exception as e:
        logger.error(f"Error in server_info: {str(e)}")
        await safe_followup(interaction, f"Error retrieving server info: {str(e)}")

@bot.tree.command(name="models_with_servers", description="List models with their server IPs and ports")
@app_commands.describe(
    sort_by="Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)",
    limit="Maximum number of results to return"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Size", value="size"),
    app_commands.Choice(name="IP", value="ip")
])
async def models_with_servers(
    interaction: discord.Interaction,
    sort_by: str = None,
    descending: bool = True,
    limit: int = 25
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Default sorting
        orderby = "name ASC"
        
        # Apply sorting options if provided
        if sort_by:
            if sort_by == "name":
                orderby = "name " + ("DESC" if descending else "ASC")
            elif sort_by == "params":
                orderby = """
                    CASE 
                        WHEN parameter_size IS NULL THEN 0
                        WHEN parameter_size = '' THEN 0
                        WHEN parameter_size LIKE '%B' THEN 
                            CASE 
                                WHEN CAST(REPLACE(REPLACE(REPLACE(parameter_size, 'B', ''), '.', ''), ' ', '') AS TEXT) ~ '^[0-9]+$' THEN
                                    CAST(REPLACE(REPLACE(REPLACE(parameter_size, 'B', ''), '.', ''), ' ', '') AS REAL) 
                                ELSE 0 
                            END
                        ELSE 0
                    END """ + ("DESC" if descending else "ASC")
            elif sort_by == "quant":
                orderby = "quant " + ("DESC" if descending else "ASC")
            elif sort_by == "size":
                orderby = "size_mb " + ("DESC" if descending else "ASC")
            elif sort_by == "ip":
                orderby = "ip " + ("DESC" if descending else "ASC")
        
        # Get all models with their endpoint information
        query = f"""
            SELECT 
                m.id, 
                m.name, 
                COALESCE(m.parameter_size, '') as parameter_size, 
                COALESCE(m.quantization_level, '') as quant, 
                COALESCE(m.size_mb, 0) as size_mb, 
                e.id as endpoint_id, 
                e.ip, 
                e.port
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            ORDER BY {orderby if sort_by != "params" else "m.name ASC"}
            LIMIT ?
        """
        
        results = Database.fetch_all(query, (limit,))
        
        if not results:
            await safe_followup(interaction, "No models found in the database.")
            return
        
        # Add detailed logging about the results
        logger.info(f"models_with_servers received {len(results)} results")
        logger.info(f"Result type: {type(results)}")
        if results:
            logger.info(f"First result type: {type(results[0])}")
            logger.info(f"First result: {results[0]}")
            if isinstance(results[0], dict):
                logger.info(f"Dictionary keys: {results[0].keys()}")
        
        # If sorting by parameter size, handle it in Python code
        if sort_by == "params":
            # Convert results to list if it's not already
            results = list(results)
            
            # Define a key function to extract parameter size as a numeric value
            def extract_param_size(model):
                # Handle both dict and tuple access
                if isinstance(model, dict):
                    param_str = model.get('parameter_size', '0')
                else:
                    # Assume tuple with parameter_size at index 2
                    param_str = model[2] if len(model) > 2 else '0'
                
                # Strip 'B' or 'b' suffix and convert to number
                param_str = param_str.strip()
                if param_str.endswith(('B', 'b')):
                    param_str = param_str[:-1].strip()
                
                # Try to convert to float
                try:
                    return float(param_str)
                except (ValueError, TypeError):
                    return 0
            
            # Sort the results
            results.sort(key=extract_param_size, reverse=descending)
            
        # Format the results
        message = f"**All Models with Server Information**\nShowing {len(results)} model instances (limit: {limit})\n\n"
        message += "Model ID | Model Name | Parameters | Quantization | Size (MB) | Endpoint ID | Server IP:Port\n"
        message += "-" * 100 + "\n"
        
        for model in results:
            try:
                # Handle both tuple and dictionary results
                if isinstance(model, dict):
                    # Dictionary access (DictCursor result)
                    model_id = model.get('id', 0)
                    name = model.get('name', 'Unknown')
                    params = model.get('parameter_size', '')
                    quant = model.get('quant', '')
                    size = model.get('size_mb', 0)
                    endpoint_id = model.get('endpoint_id', 0)
                    ip = model.get('ip', 'Unknown')
                    port = model.get('port', 0)
                elif isinstance(model, (list, tuple)) and len(model) >= 8:
                    # Tuple access (regular cursor result)
                    model_id, name, params, quant, size, endpoint_id, ip, port = model
                else:
                    # Invalid data format
                    logger.warning(f"Model result has unexpected format: {model}")
                    message += f"Error with model data: Unexpected format {type(model)}\n"
                    continue
                
                # Trim long model names
                display_name = name
                if len(display_name) > 15:
                    display_name = name[:12] + "..."
                
                # Format size with 2 decimal places
                size_str = f"{size:.2f}" if size else "N/A"
                
                message += f"{model_id} | {display_name} | {params or 'N/A'} | {quant or 'N/A'} | {size_str} | {endpoint_id} | {ip}:{port}\n"
            except Exception as e:
                logger.error(f"Error processing model result: {str(e)}, Model data: {model}")
                message += f"Error processing model data: {str(e)}\n"
        
        # Check if message is too long and truncate if needed
        if len(message) > 1900:
            # Truncate and indicate there's more
            message = message[:1850] + "\n... (additional models truncated) ..."
            
        await safe_followup(interaction, message)
        
    except Exception as e:
        logger.error(f"Error in models_with_servers: {str(e)}")
        await safe_followup(interaction, f"Error retrieving models with servers: {str(e)}")

@bot.tree.command(name="cleanup", description="Remove duplicate endpoints and models from the database")
async def cleanup_database(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        await safe_followup(interaction, "Checking for duplicate entries in the database...")
        
        # Find duplicate endpoints 
        dupes_query = """
            SELECT ip, port, COUNT(*), string_agg(id::text, ',') as ids
            FROM endpoints
            GROUP BY ip, port
            HAVING COUNT(*) > 1
        """
        
        dupes = Database.fetch_all(dupes_query)
        
        # Process duplicate endpoints
        if len(dupes) == 0:
            endpoint_msg = "No duplicate endpoints found."
        else:
            endpoint_msg = f"Found {len(dupes)} duplicate endpoint entries - resolving now..."
            
            # Process each set of duplicates
            for dupe in dupes:
                ip, port, count, ids = dupe
                id_list = ids.split(',')
                keep_id = id_list[0]  # Keep first one
                remove_ids = id_list[1:]  # Remove the rest
                
                endpoint_msg += f"\n  - Retaining endpoint: {ip}:{port} (ID {keep_id})"
                endpoint_msg += f"\n  - Removing {len(remove_ids)} duplicates with same IP/port"
                
                # Update models to point to the ID we're keeping
                for remove_id in remove_ids:
                    # Update models to use the keep_id
                    Database.execute(
                        "UPDATE models SET endpoint_id = ? WHERE endpoint_id = ?", 
                        (keep_id, remove_id)
                    )
                    
                    # Update the verification status if needed
                    Database.execute(
                        f"UPDATE endpoints SET verified = {get_db_boolean(True)} WHERE id = ? AND (SELECT verified FROM endpoints WHERE id = ?) = {get_db_boolean(True)}", 
                        (keep_id, remove_id)
                    )
                    
                    # Delete the duplicate endpoint
                    Database.execute(
                        "DELETE FROM endpoints WHERE id = ?", 
                        (remove_id,)
                    )
        
        # Find duplicate models
        dupe_models_query = """
            SELECT endpoint_id, name, COUNT(*), string_agg(id::text, ',') as ids
            FROM models
            GROUP BY endpoint_id, name
            HAVING COUNT(*) > 1
        """
        
        dupe_models = Database.fetch_all(dupe_models_query)
        
        # Process duplicate models
        if len(dupe_models) == 0:
            model_msg = "No duplicate models found."
        else:
            model_msg = f"Found {len(dupe_models)} duplicate model entries - resolving now..."
            
            # Process each set of duplicates
            for dupe in dupe_models:
                endpoint_id, name, count, ids = dupe
                id_list = ids.split(',')
                keep_id = id_list[0]  # Keep first one
                remove_ids = id_list[1:]  # Remove the rest
                
                # Get endpoint info
                endpoint_result = Database.fetch_one(
                    "SELECT ip, port FROM endpoints WHERE id = ?", 
                    (endpoint_id,)
                )
                
                if endpoint_result:
                    endpoint_ip, endpoint_port = endpoint_result
                    model_msg += f"\n  - Retaining model: {name} on {endpoint_ip}:{endpoint_port} (ID {keep_id})"
                    model_msg += f"\n  - Removing {len(remove_ids)} duplicates with same endpoint and name"
                
                # Delete the duplicate models
                for remove_id in remove_ids:
                    Database.execute(
                        "DELETE FROM models WHERE id = ?", 
                        (remove_id,)
                    )
        
        # Prepare final summary
        summary = "**Database Cleanup Results**\n\n"
        summary += f"**Endpoint Cleanup:**\n{endpoint_msg}\n\n"
        summary += f"**Model Cleanup:**\n{model_msg}"
        
        await safe_followup(interaction, summary)
        
    except Exception as e:
        logger.error(f"Error in cleanup_database: {str(e)}")
        await safe_followup(interaction, f"Error cleaning up database: {str(e)}")

@bot.tree.command(name="refreshcommands", description="Force refresh of bot commands (admin only)")
async def refresh_commands(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await safe_followup(interaction, "This command requires administrator permissions.")
            return
        
        # Get current commands
        before_count = len(await bot.tree.fetch_commands())
        before_commands = await bot.tree.fetch_commands()
        
        await safe_followup(interaction, "Refreshing commands. This may take up to a minute...")
        
        # Log the current commands
        logger.info(f"Current commands before refresh: {', '.join([cmd.name for cmd in before_commands])}")
        
        # Clear command cache in current guild
        bot.tree.clear_commands(guild=interaction.guild)
        
        # Sync globally first
        await bot.tree.sync()
        
        # Then sync to the current guild to ensure immediate visibility
        await bot.tree.sync(guild=interaction.guild)
        
        # Get the updated commands
        after_commands = await bot.tree.fetch_commands()
        
        # Send detailed results
        command_list = [f"- {cmd.name}" for cmd in after_commands]
        
        message = f"**Command Refresh Complete**\n"
        message += f"- Commands before: {before_count}\n"
        message += f"- Commands after: {len(after_commands)}\n\n"
        message += "**Available Commands:**\n" + "\n".join(command_list)
        
        await safe_followup(interaction, message)
        
        logger.info(f"Commands refreshed by user {interaction.user.name} in guild {interaction.guild.name}")
        logger.info(f"Refreshed from {before_count} to {len(after_commands)} commands")
        logger.info(f"Updated commands: {', '.join([cmd.name for cmd in after_commands])}")
        
    except Exception as e:
        logger.error(f"Error in refresh_commands: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        await safe_followup(interaction, f"Error refreshing commands: {str(e)}")

@bot.tree.command(name="guild_sync", description="Force sync commands to this guild (admin only)")
async def guild_sync_command(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await safe_followup(interaction, "This command requires administrator permissions.")
            return
        
        await safe_followup(interaction, "Syncing commands to this guild. This may take a moment...")
        
        # Get current guild command count
        try:
            before_commands = await bot.tree.fetch_commands(guild=interaction.guild)
            before_count = len(before_commands)
        except:
            before_count = 0
        
        # Do NOT clear commands first - this was causing problems
        # Just sync directly to the guild
        
        # Sync to the current guild
        synced = await bot.tree.sync(guild=interaction.guild)
        
        # Get the guild ID for logging
        guild_id = interaction.guild.id
        
        # Log the sync operation
        logger.info(f"Guild commands synced by {interaction.user.name} in guild {interaction.guild.name}")
        logger.info(f"Synced {len(synced)} commands to guild ID {guild_id}")
        
        # List all command names for verification
        command_list = [f"- {cmd.name}" for cmd in synced]
        
        message = f"**Command Sync Complete**\n"
        message += f"- Commands before: {before_count}\n"
        message += f"- Commands after: {len(synced)}\n\n"
        
        # Verify quickprompt is included
        quickprompt_included = any(cmd.name == "quickprompt" for cmd in synced)
        if quickprompt_included:
            message += "✅ quickprompt command successfully registered\n\n"
        else:
            message += "❌ quickprompt command NOT registered! Please contact the developer.\n\n"
            
        message += "**Synced Commands:**\n" + "\n".join(command_list)
        
        await safe_followup(interaction, message)
        
    except Exception as e:
        logger.error(f"Error in guild_sync: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        await safe_followup(interaction, f"Error syncing commands to guild: {str(e)}")

@bot.tree.command(name="refreshcommandsv2", description="Force complete refresh of all bot commands (admin only)")
async def refresh_commands_v2(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await safe_followup(interaction, "This command requires administrator permissions.")
            return
        
        # Get current commands
        before_count = len(await bot.tree.fetch_commands())
        before_commands = await bot.tree.fetch_commands()
        
        await safe_followup(interaction, "Refreshing all commands with a complete reset. This may take a minute...")
        
        # Log the current commands
        logger.info(f"Current commands before refresh: {', '.join([cmd.name for cmd in before_commands])}")
        
        try:
            # First sync to the guild to ensure immediate visibility
            # Doing this BEFORE clearing commands to avoid having a period with no commands
            guild_commands = await bot.tree.sync(guild=interaction.guild)
            logger.info(f"First step: Synced {len(guild_commands)} commands to guild")
            
            # Then sync globally
            global_commands = await bot.tree.sync()
            logger.info(f"Second step: Synced {len(global_commands)} commands globally")
            
            # Get the updated commands
            after_commands = await bot.tree.fetch_commands()
            
            # Send detailed results
            command_list = [f"- {cmd.name}" for cmd in after_commands]
            
            message = f"**Command Refresh Complete**\n"
            message += f"- Commands before: {before_count}\n"
            message += f"- Commands after: {len(after_commands)}\n\n"
            
            # Verify quickprompt is included
            quickprompt_included = any(cmd.name == "quickprompt" for cmd in after_commands)
            if quickprompt_included:
                message += "✅ quickprompt command successfully registered\n\n"
            else:
                message += "❌ quickprompt command NOT registered! Please contact the developer.\n\n"
                
            message += "**Available Commands:**\n" + "\n".join(command_list)
            
            await safe_followup(interaction, message)
            
            logger.info(f"Commands refreshed by user {interaction.user.name} in guild {interaction.guild.name}")
            logger.info(f"Refreshed from {before_count} to {len(after_commands)} commands")
            logger.info(f"Updated commands: {', '.join([cmd.name for cmd in after_commands])}")
            
        except Exception as e:
            logger.error(f"Error during command sync: {str(e)}")
            await safe_followup(interaction, f"Error during command sync: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in refresh_commands_v2: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        await safe_followup(interaction, f"Error refreshing commands: {str(e)}")

@bot.tree.command(name="manage_models", description="Add or delete models from an Ollama server")
@app_commands.describe(
    action="Action to perform (add or delete)",
    server_ip="Server IP address",
    server_port="Server port (default: 11434)",
    model_name="Name of the model to add or delete",
    model_id="ID of the model to delete (required for delete action)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="Add Model", value="add"),
    app_commands.Choice(name="Delete Model", value="delete"),
    app_commands.Choice(name="Refresh Models", value="refresh")
])
async def manage_models(
    interaction: discord.Interaction,
    action: str,
    server_ip: str = None, 
    server_port: int = 11434,
    model_name: str = None,
    model_id: int = None
):
    """
    Add, delete, or refresh models on an Ollama server
    
    Args:
        interaction: Discord interaction
        action: Action to perform (add, delete, or refresh)
        server_ip: Server IP address (required for add/refresh)
        server_port: Server port (default: 11434)
        model_name: Name of the model to add or delete
        model_id: ID of the model to delete (required for delete)
    """
    if not await safe_defer(interaction):
        return
    
    try:
        # Handle ADD action
        if action == "add":
            if not server_ip or not model_name:
                await safe_followup(interaction, "⚠️ Error: Both server_ip and model_name are required for adding a model.")
                return
                
            # Clean the IP for display (but use original for requests)
            clean_ip = server_ip
            if ":" in clean_ip:
                clean_ip = f"[{clean_ip}]"
            
            # Verify the server is reachable
            is_reachable, error = await check_server_connectivity(server_ip, server_port)
            if not is_reachable:
                await safe_followup(interaction, f"⚠️ Error: Cannot connect to server {clean_ip}:{server_port}: {error}")
                return
                
            # First, let the user know we're starting the pull process
            await safe_followup(interaction, f"📥 Starting pull request for model `{model_name}` on server {clean_ip}:{server_port}...")
            
            # Check if the model is already being pulled (it could be in progress from another request)
            try:
                api_url = f"http://{server_ip}:{server_port}/api/pull"
                
                # Increase timeout from 10 to 60 seconds for the initial connection
                # Use streaming mode to track progress, similar to add_model_command
                pull_payload = {
                    "model": model_name,
                    "stream": True  # Enable streaming to track progress
                }
                
                logger.info(f"Pulling model {model_name} with payload: {pull_payload}")
                
                async with session.post(
                    api_url,
                    json=pull_payload,
                    timeout=60  # Increased timeout for initial connection
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        await safe_followup(interaction, f"⚠️ Error: Failed to start model pull: {response_text}")
                        return
                    
                    # Model pull started successfully - add to database
                    try:
                        # Sync the models with the server 
                        # This will add the server to the database if it doesn't exist
                        await sync_models_with_server_async(server_ip, server_port)
                        
                        # Initialize variables to track download progress
                        last_update_time = time.time()
                        last_status = None
                        current_digest = None
                        total_size = None
                        completed_size = None
                        status_message = await safe_followup(
                            interaction, 
                            f"✅ Pull request initiated for model `{model_name}` on {clean_ip}:{server_port}.\n⏳ Downloading model... (0%)"
                        )
                        
                        # Process streaming response to track progress
                        try:
                            async for line in response.content:
                                if not line.strip():
                                    continue
                                    
                                data = json.loads(line)
                                status = data.get("status")
                                
                                # Only update message if status has changed or significant progress has been made
                                current_time = time.time()
                                should_update = (
                                    status != last_status or 
                                    current_time - last_update_time > 3  # Update at least every 3 seconds
                                )
                                
                                if status == "pulling manifest":
                                    if should_update:
                                        await interaction.edit_original_response(
                                            content=f"📋 Pulling manifest for model `{model_name}`..."
                                        )
                                        last_update_time = current_time
                                        last_status = status
                                        
                                elif status == "downloading":
                                    # Track download progress
                                    current_digest = data.get("digest", "unknown")
                                    total_size = data.get("total", 0)
                                    completed_size = data.get("completed", 0)
                                    
                                    if total_size and completed_size:
                                        percent = min(100, int((completed_size / total_size) * 100))
                                        
                                        # Update progress less frequently to avoid rate limits
                                        if should_update:
                                            # Format sizes for better readability
                                            total_gb = total_size / (1024**3)
                                            completed_gb = completed_size / (1024**3)
                                            
                                            progress_bar = "█" * (percent // 5) + "░" * (20 - (percent // 5))
                                            
                                            await interaction.edit_original_response(
                                                content=(
                                                    f"📥 Downloading model `{model_name}` on {clean_ip}:{server_port}...\n"
                                                    f"📦 Digest: {current_digest[:12]}...\n"
                                                    f"⏳ Progress: {percent}% |{progress_bar}| {completed_gb:.2f}GB / {total_gb:.2f}GB"
                                                )
                                            )
                                            last_update_time = current_time
                                            last_status = status
                                            
                                elif status == "verifying sha256 digest":
                                    if should_update:
                                        await interaction.edit_original_response(
                                            content=f"🔒 Verifying SHA256 digest for model `{model_name}`..."
                                        )
                                        last_update_time = current_time
                                        last_status = status
                                        
                                elif status == "writing manifest":
                                    if should_update:
                                        await interaction.edit_original_response(
                                            content=f"📝 Writing manifest for model `{model_name}`..."
                                        )
                                        last_update_time = current_time
                                        last_status = status
                                        
                                elif status == "removing any unused layers":
                                    if should_update:
                                        await interaction.edit_original_response(
                                            content=f"🧹 Cleaning up unused layers for model `{model_name}`..."
                                        )
                                        last_update_time = current_time
                                        last_status = status
                                        
                                elif status == "success":
                                    # Final success message with full details
                                    await interaction.edit_original_response(
                                        content=(
                                            f"✅ Successfully pulled model `{model_name}` on {clean_ip}:{server_port}\n"
                                            f"🔗 Server URL: http://{clean_ip}:{server_port}\n"
                                            f"ℹ️ Use `/checkserver {server_ip} {server_port}` to see all models on this server"
                                        )
                                    )
                                    
                                    # Sync with server to update model details
                                    try:
                                        await sync_models_with_server_async(server_ip, server_port)
                                        logger.info(f"Synced models for server {server_ip}:{server_port} after successful pull")
                                    except Exception as sync_error:
                                        logger.error(f"Error syncing models after pull: {str(sync_error)}")
                                    
                                    return
                                    
                                elif status and status.startswith("error"):
                                    error_msg = data.get("error", "Unknown error")
                                    await interaction.edit_original_response(
                                        content=f"❌ Error pulling model `{model_name}`: {error_msg}"
                                    )
                                    return
                                    
                        except asyncio.TimeoutError:
                            # Handle timeout during streaming
                            await interaction.edit_original_response(
                                content=(
                                    f"⚠️ Pull process for `{model_name}` on {clean_ip}:{server_port} is continuing in the background.\n"
                                    f"Last status: {last_status or 'Initializing'}\n"
                                    f"The connection timed out, but the download should continue on the server.\n"
                                    f"Check the status later with `/checkserver {server_ip} {server_port}`"
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error processing streaming response: {str(e)}")
                            await interaction.edit_original_response(
                                content=(
                                    f"⚠️ Error tracking pull progress for `{model_name}` on {clean_ip}:{server_port}: {str(e)}\n"
                                    f"The pull request might still be processing in the background.\n"
                                    f"Check the status later with `/checkserver {server_ip} {server_port}`"
                                )
                            )
                    except Exception as e:
                        logger.error(f"Error syncing models with server: {str(e)}")
                        await safe_followup(interaction, f"⚠️ Error syncing models with server: {str(e)}\nThe model pull might continue in the background.")
            except asyncio.TimeoutError:
                # Improved timeout message with clearer next steps
                await safe_followup(interaction, 
                    f"⚠️ Pull request timed out. The server might be busy or unreachable.\n"
                    f"The pull request might still be processing in the background.\n\n"
                    f"Check the status later with `/checkserver {server_ip} {server_port}`\n"
                    f"Large models can take a long time to download, especially on slower connections."
                )
            except Exception as e:
                logger.error(f"Error starting model pull: {str(e)}")
                await safe_followup(interaction, 
                    f"⚠️ Error starting model pull: {str(e)}\n\n"
                    f"The pull request might still be processing in the background.\n\n"
                    f"Check the status later with `/checkserver {server_ip} {server_port}`"
                )
        
        # Handle DELETE action
        elif action == "delete":
            if model_id is None:
                await safe_followup(interaction, "⚠️ Error: model_id is required for delete action.")
                return
            
            # Get model information
            conn = Database()
            
            # Query model info 
            model_query = """
                SELECT m.name, s.ip, s.port, s.id
                FROM models m
                JOIN endpoints s ON m.endpoint_id = s.id
                WHERE m.id = ?
            """
            model_params = (model_id,)
            Database.execute(model_query, model_params)
            
            model_info = Database.fetch_one(model_query, model_params)
            conn.close()
            
            if not model_info:
                await safe_followup(interaction, f"⚠️ Error: Model with ID {model_id} not found.")
                return
            
            name, ip, port, server_id = model_info
            
            # Clean the IP for display (but use original for API calls)
            clean_ip = ip
            if ":" in clean_ip:
                clean_ip = f"[{clean_ip}]"
        
            # Check if server is reachable
            is_reachable, error = await check_server_connectivity(ip, port)
            if not is_reachable:
                await safe_followup(interaction, f"⚠️ Error: Cannot connect to server {clean_ip}:{port}: {error}")
                return
            
            # Try to delete the model from Ollama
            try:
                api_url = f"http://{ip}:{port}/api/delete"
                response = await session.delete(
                    api_url,
                    json={"model": name},  # Use "model" instead of "name" for consistency with Ollama API
                    timeout=10
                )
                
                if response.status == 200:
                    # Delete from database
                    conn = Database()
                    Database.execute("DELETE FROM models WHERE id = ?", (model_id,))
                    # Commit handled by Database methods
                    conn.close()
                    
                    await safe_followup(interaction, f"✅ Model `{name}` deleted from server {clean_ip}:{port} and removed from database.")
                else:
                    response_text = await response.text()
                    await safe_followup(interaction, f"⚠️ Error: Failed to delete model from server: {response_text}")
            except Exception as e:
                logger.error(f"Error deleting model: {str(e)}")
                await safe_followup(interaction, f"⚠️ Error deleting model: {str(e)}")
        
        # Handle REFRESH action
        elif action == "refresh":
            if not server_ip:
                await safe_followup(interaction, "⚠️ Error: server_ip is required for refresh action.")
                return
                
            # Clean the IP for display (but use original for requests)
            clean_ip = server_ip
            if ":" in clean_ip:
                clean_ip = f"[{clean_ip}]"
            
            # Verify the server is reachable
            is_reachable, error = await check_server_connectivity(server_ip, server_port)
            if not is_reachable:
                await safe_followup(interaction, f"⚠️ Error: Cannot connect to server {clean_ip}:{server_port}: {error}")
                return
                
            await safe_followup(interaction, f"🔄 Refreshing models from server {clean_ip}:{server_port}...")
            
            try:
                # Use existing sync function to update the database with server's models
                result = await sync_models_with_server_async(server_ip, server_port)
                
                # Get the number of models found
                conn = Database()
                Database.execute("""
                    SELECT COUNT(*) 
                    FROM models m 
                    JOIN endpoints s ON m.endpoint_id = s.id 
                    WHERE s.ip = ? AND s.port = ?
                """, (server_ip, server_port))
                model_count = Database.fetch_one("""
                    SELECT COUNT(*) 
                    FROM models m 
                    JOIN endpoints s ON m.endpoint_id = s.id 
                    WHERE s.ip = ? AND s.port = ?
                """, (server_ip, server_port))[0]
                
                # Get models details for display
                Database.execute("""
                    SELECT m.id, m.name, m.parameter_size, m.quantization_level
                    FROM models m
                    JOIN endpoints s ON m.endpoint_id = s.id
                    WHERE s.ip = ? AND s.port = ?
                    ORDER BY m.name
                """, (server_ip, server_port))
                
                models = Database.fetch_all("""
                    SELECT m.id, m.name, m.parameter_size, m.quantization_level
                    FROM models m
                    JOIN endpoints s ON m.endpoint_id = s.id
                    WHERE s.ip = ? AND s.port = ?
                    ORDER BY m.name
                """, (server_ip, server_port))
                
                conn.close()
                
                # Create a formatted list of models for display
                if models:
                    # Get more detailed model information including file sizes
                    try:
                        api_url = f"http://{server_ip}:{server_port}/api/tags"
                        async with session.get(api_url, timeout=10) as response:
                            if response.status == 200:
                                api_data = await response.json()
                                model_details = {}
                                
                                # Create a lookup of model details from API
                                for model_info in api_data.get("models", []):
                                    name = model_info.get("name")
                                    size = model_info.get("size", 0)
                                    modified = model_info.get("modified_at", "")
                                    details = model_info.get("details", {})
                                    
                                    # Store comprehensive details
                                    model_details[name] = {
                                        "size": size,
                                        "size_formatted": format_file_size(size),
                                        "modified": modified,
                                        "parameter_size": details.get("parameter_size", "Unknown"),
                                        "quantization": details.get("quantization_level", "Unknown"),
                                        "format": details.get("format", "Unknown"),
                                        "family": details.get("family", "Unknown")
                                    }
                                
                                # Create a detailed list of models with sizes
                                models_list = []
                                for model in models:
                                    model_id, name, param_size, quant_level = model
                                    details = model_details.get(name, {})
                                    
                                    # Format size if available from API
                                    size_str = details.get("size_formatted", "Unknown")
                                    
                                    # Use API details if available, otherwise use database values
                                    param_str = details.get("parameter_size", param_size or "Unknown")
                                    quant_str = details.get("quantization", quant_level or "Unknown")
                                    
                                    models_list.append(
                                        f"• ID:{model_id} | {name} | {param_str} | {quant_str} | {size_str}"
                                    )
                                    
                                # Join the formatted models list
                                models_text = "\n".join(models_list)
                                
                                # Add headers for the table
                                final_text = "ID | Model Name | Parameters | Quantization | Size\n"
                                final_text += "-" * 70 + "\n"
                                final_text += models_text
                                
                                await interaction.edit_original_response(
                                    content=f"✅ Successfully refreshed models on server {clean_ip}:{server_port}\n\n"
                                            f"📊 Found {model_count} models:\n\n"
                                            f"{final_text}\n\n"
                                            f"Use `/chat <model_id> <prompt>` to chat with any of these models."
                                )
                                return
                    except Exception as model_detail_error:
                        logger.warning(f"Could not fetch detailed model info: {str(model_detail_error)}")
                        # Fall back to basic display if detailed view fails
                
                # Basic display without API details (fallback)
                models_list = "\n".join([f"• ID:{model[0]} | {model[1]} | {model[2] or 'N/A'} | {model[3] or 'N/A'}" for model in models])
                
                await interaction.edit_original_response(
                    content=f"✅ Successfully refreshed models on server {clean_ip}:{server_port}\n\n"
                            f"📊 Found {model_count} models:\n\n"
                            f"{models_list}\n\n"
                            f"Use `/chat <model_id> <prompt>` to chat with any of these models."
                )
            except Exception as e:
                logger.error(f"Error refreshing models: {str(e)}")
                await safe_followup(interaction, f"⚠️ Error refreshing models: {str(e)}")
        
        else:
            await safe_followup(interaction, f"⚠️ Invalid action: {action}. Must be 'add', 'delete', or 'refresh'.")
    
    except Exception as e:
        logger.error(f"Error in manage_models: {str(e)}")
        await safe_followup(interaction, f"⚠️ Error: {str(e)}")

@bot.tree.command(name="list_models", description="List all models with filtering and sorting options")
@app_commands.describe(
    search_term="Optional: Model name search term",
    quant_level="Optional: Filter by quantization level",
    param_size="Optional: Filter by parameter size",
    sort_by="Optional: Field to sort results by",
    descending="Sort in descending order (true) or ascending order (false)",
    limit="Maximum number of results to return"
)
@app_commands.choices(sort_by=[
    app_commands.Choice(name="Name", value="name"),
    app_commands.Choice(name="Parameters", value="params"),
    app_commands.Choice(name="Quantization", value="quant"),
    app_commands.Choice(name="Count", value="count")
])
async def list_models(
    interaction: discord.Interaction,
    search_term: str = None,
    quant_level: str = None,
    param_size: str = None,
    sort_by: str = None,
    descending: bool = True,
    limit: int = 25
):
    if not await safe_defer(interaction):
        return
    
    try:
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
                    orderby = "CASE WHEN parameter_size LIKE '%B' THEN CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL) ELSE 0 END DESC"
                else:
                    orderby = "CASE WHEN parameter_size LIKE '%B' THEN CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS REAL) ELSE 0 END ASC"
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
        
        # Build base query
        base_query = """
            SELECT 
                m.id,
                m.name, 
                m.parameter_size, 
                m.quantization_level, 
                COUNT(DISTINCT (s.ip || ':' || s.port)) as server_count
            FROM models m
            JOIN endpoints s ON m.endpoint_id = s.id
            WHERE 1=1
        """
        
        # We'll handle server list display separately without string_agg which might cause issues
        parameters = []
        
        # Add search filters
        if search_term:
            base_query += " AND m.name LIKE %s"
            parameters.append(f"%{search_term}%")
            
        if quant_level:
            base_query += " AND m.quantization_level LIKE %s"
            parameters.append(f"%{quant_level}%")
            
        if param_size:
            base_query += " AND m.parameter_size LIKE %s"
            parameters.append(f"%{param_size}%")
            
        # Complete the query with GROUP BY and ORDER BY
        query = base_query + f"""
            GROUP BY m.id, m.name, m.parameter_size, m.quantization_level
            ORDER BY {orderby}
            LIMIT %s
        """
        parameters.append(limit)
        
        # Execute query with properly formatted parameters
        results = Database.fetch_all(query.strip(), tuple(parameters))
        
        if not results:
            await safe_followup(interaction, "No models found matching your criteria.")
            return
            
        # Format the results with proper Discord markdown
        formatted_response = "# Model Search Results\n\n"
        
        # Add search criteria if any were used
        filters_used = []
        if search_term:
            filters_used.append(f"Name: '{search_term}'")
        if param_size:
            filters_used.append(f"Parameters: '{param_size}'")
        if quant_level:
            filters_used.append(f"Quantization: '{quant_level}'")
        
        if filters_used:
            formatted_response += "## Search Filters\n"
            formatted_response += "```\n"
            for filter_desc in filters_used:
                formatted_response += f"• {filter_desc}\n"
            formatted_response += "```\n\n"
        
        # Add result count and sorting info
        formatted_response += f"## Found {len(results)} Models\n"
        formatted_response += f"Sorted by: {sort_by or 'server count'} ({'descending' if descending else 'ascending'})\n\n"
        
        # Create the main results table
        formatted_response += "```\n"
        formatted_response += "ID     | Model Name                | Parameters | Quantization | Servers\n"
        formatted_response += "-------|---------------------------|------------|--------------|--------\n"
        
        for result in results:
            id, name, params, quant, count = result
            
            # Format each field with proper padding
            id_str = str(id).ljust(6)
            
            # Truncate long model names
            if len(name) > 25:
                name_str = name[:22] + "..."
            else:
                name_str = name.ljust(25)
            
            # Format parameters and quantization
            params_str = (params or "N/A").ljust(10)
            quant_str = (quant or "N/A").ljust(12)
            
            # Format the count
            count_str = str(count).rjust(7)
            
            # Add the line to the table
            formatted_response += f"{id_str} | {name_str} | {params_str} | {quant_str} | {count_str}\n"
        
        formatted_response += "```\n\n"
        
        # Add usage tips
        formatted_response += "## Usage Tips\n"
        formatted_response += "• Use `/chat <model_id> <prompt>` to chat with any model\n"
        formatted_response += "• Use `/benchmark <model_id>` to test model performance\n"
        formatted_response += "• Use `/find_model_endpoints <model_name>` to see all endpoints for a model\n"
        
        await safe_followup(interaction, formatted_response)
        
    except Exception as e:
        logger.error(f"Error in list_models: {str(e)}")
        await safe_followup(interaction, f"Error: {str(e)}")

@bot.tree.command(name="db_info", description="Show database statistics for models and endpoints")
async def db_info(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return
    
    try:
        # Get database connection parameters
        from database import PG_DB_NAME, PG_DB_USER, PG_DB_PASSWORD, PG_DB_HOST, PG_DB_PORT
        
        # Connect directly to the database using psycopg2
        import psycopg2
        
        # Create a connection
        conn = psycopg2.connect(
            dbname=PG_DB_NAME,
            user=PG_DB_USER,
            password=PG_DB_PASSWORD,
            host=PG_DB_HOST,
            port=PG_DB_PORT
        )
        
        # Create a cursor
        cursor = conn.cursor()
        
        # Count verified API endpoints - Handle verified column as integer (1) instead of boolean (TRUE)
        endpoint_query = f"SELECT COUNT(*) FROM endpoints WHERE verified = {get_db_boolean(True, as_string=True, for_verified=True)}"
        cursor.execute(endpoint_query)
        endpoint_count = cursor.fetchone()[0]
        
        # Count total models
        total_models_query = f"""
            SELECT COUNT(*) FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)} 
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
        """
        cursor.execute(total_models_query)
        total_models = cursor.fetchone()[0]
        
        # Count unique models
        unique_models_query = f"""
            SELECT COUNT(DISTINCT m.name) FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
        """
        cursor.execute(unique_models_query)
        unique_models = cursor.fetchone()[0]
        
        # Get model counts by parameter size using direct connection
        param_size_query = f"""
            SELECT m.parameter_size, COUNT(*) as count
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.parameter_size IS NOT NULL
            AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
            GROUP BY m.parameter_size 
            ORDER BY 
                CASE WHEN m.parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(m.parameter_size, 'B', ''), '.', '') AS NUMERIC)
                ELSE 0
                END DESC
        """
        cursor.execute(param_size_query)
        param_counts = cursor.fetchall()
        
        # Get model counts by quantization level
        quant_query = f"""
            SELECT m.quantization_level, COUNT(*) as count
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.quantization_level IS NOT NULL
            AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
            GROUP BY m.quantization_level 
            ORDER BY count DESC
        """
        cursor.execute(quant_query)
        quant_counts = cursor.fetchall()
        
        # Get top 5 models by count
        top_models_query = f"""
            SELECT m.name, COUNT(*) as count 
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
            GROUP BY m.name 
            ORDER BY count DESC 
            LIMIT 10
        """
        cursor.execute(top_models_query)
        top_models = cursor.fetchall()
        
        # Close the connection
        cursor.close()
        conn.close()
        
        # Format the results with proper Discord markdown
        formatted_response = "# Database Statistics\n\n"
        
        # Summary section
        formatted_response += "## Summary\n"
        formatted_response += "```\n"
        formatted_response += f"Verified API Endpoints: {endpoint_count:,}\n"
        formatted_response += f"Total Model Instances: {total_models:,}\n"
        formatted_response += f"Unique Model Types:    {unique_models:,}\n"
        formatted_response += "```\n\n"
        
        # Parameter Sizes section
        if param_counts:
            formatted_response += "## Parameter Size Distribution\n"
            formatted_response += "```\n"
            formatted_response += "Size    | Count   | Percentage\n"
            formatted_response += "--------|---------|------------\n"
            for param_size, count in param_counts[:10]:  # Limit to top 10
                percentage = (count / total_models) * 100 if total_models > 0 else 0
                formatted_response += f"{param_size or 'Unknown':<8} | {count:>7,} | {percentage:>6.1f}%\n"
            if len(param_counts) > 10:
                formatted_response += f"... and {len(param_counts) - 10} more sizes ...\n"
            formatted_response += "```\n\n"
            
        # Quantization Levels section
        if quant_counts:
            formatted_response += "## Quantization Level Distribution\n"
            formatted_response += "```\n"
            formatted_response += "Level   | Count   | Percentage\n"
            formatted_response += "--------|---------|------------\n"
            for quant_level, count in quant_counts:
                percentage = (count / total_models) * 100 if total_models > 0 else 0
                formatted_response += f"{quant_level or 'Unknown':<8} | {count:>7,} | {percentage:>6.1f}%\n"
            formatted_response += "```\n\n"
            
        # Top Models section
        if top_models:
            formatted_response += "## Most Common Models\n"
            formatted_response += "```\n"
            formatted_response += "Model Name                | Instances | Percentage\n"
            formatted_response += "-------------------------|-----------|------------\n"
            for name, count in top_models:
                percentage = (count / total_models) * 100 if total_models > 0 else 0
                # Truncate long model names
                display_name = name[:23] + "..." if len(name) > 23 else name.ljust(23)
                formatted_response += f"{display_name} | {count:>9,} | {percentage:>6.1f}%\n"
            formatted_response += "```\n\n"
        
        # Add usage tips
        formatted_response += "## Usage Tips\n"
        formatted_response += "• Use `/list_models` to see detailed model information\n"
        formatted_response += "• Use `/find_model_endpoints <model_name>` to find specific models\n"
        formatted_response += "• Use `/model_status <ip> <port>` to check loaded models on a server\n"
        
        await safe_followup(interaction, formatted_response)
        
    except Exception as e:
        logger.error(f"Error in db_info: {str(e)}")
        await safe_followup(interaction, f"Error querying database: {str(e)}\n\nPlease check the database connection and schema.")

@bot.tree.command(name="honeypot_stats", description="Show statistics about detected honeypots")
async def honeypot_stats(interaction: discord.Interaction):
    """Show statistics about detected honeypots"""
    if not await safe_defer(interaction):
        return
    
    try:
        # Count total endpoints
        total_count = Database.fetch_one("SELECT COUNT(*) FROM endpoints")[0]
        
        # Count honeypots
        honeypot_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_honeypot = {get_db_boolean(True)}")[0]
        
        # Count inactive endpoints
        inactive_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_active = {get_db_boolean(False)}")[0]
        
        # Count verified endpoints - Handle verified column as integer (1) instead of boolean (TRUE)
        verified_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE verified = {get_db_boolean(True, as_string=True, for_verified=True)}")[0]
        
        # Get most common honeypot reasons
        reasons_query = f"""
            SELECT honeypot_reason, COUNT(*) as count
            FROM endpoints
            WHERE is_honeypot = {get_db_boolean(True)}
            GROUP BY honeypot_reason
            ORDER BY count DESC
            LIMIT 5
        """
        honeypot_reasons = Database.fetch_all(reasons_query)
        
        # Get most common inactive reasons
        inactive_reasons_query = f"""
            SELECT inactive_reason, COUNT(*) as count
            FROM endpoints
            WHERE is_active = {get_db_boolean(False)}
            GROUP BY inactive_reason
            ORDER BY count DESC
            LIMIT 5
        """
        inactive_reasons = Database.fetch_all(inactive_reasons_query)
        
        # Create embed with clear labeling
        embed = discord.Embed(
            title="🔍 Endpoint Security Statistics",
            description="⚠️ **IMPORTANT:** Honeypots are tracked for security monitoring but are NEVER used for model interactions.",
            color=discord.Color.gold()
        )
        
        # Summary section
        embed.add_field(
            name="Summary", 
            value=f"Total Endpoints: {total_count}\nVerified Endpoints: {verified_count}\nHoneypots: {honeypot_count}\nInactive: {inactive_count}", 
            inline=False
        )
        
        if honeypot_count > 0:
            honeypot_percent = (honeypot_count / total_count) * 100
            embed.add_field(
                name="Honeypot Ratio", 
                value=f"{honeypot_percent:.1f}% of all endpoints are honeypots", 
                inline=False
            )
            
            if honeypot_reasons:
                reasons_text = "\n".join([f"• {reason or 'Unknown'}: {count} endpoints" for reason, count in honeypot_reasons])
                embed.add_field(
                    name="Common Honeypot Detection Reasons", 
                    value=reasons_text, 
                    inline=False
                )
        
        if inactive_count > 0:
            inactive_percent = (inactive_count / total_count) * 100
            embed.add_field(
                name="Inactive Ratio", 
                value=f"{inactive_percent:.1f}% of all endpoints are inactive", 
                inline=False
            )
            
            if inactive_reasons:
                reasons_text = "\n".join([f"• {reason or 'Unknown'}: {count} endpoints" for reason, count in inactive_reasons])
                embed.add_field(
                    name="Common Inactive Reasons", 
                    value=reasons_text, 
                    inline=False
                )
        
        # Add safety note
        embed.add_field(
            name="Safety Note", 
            value=(
                "All interactions with models use ONLY verified, non-honeypot endpoints.\n"
                "Our system continually monitors and filters out honeypots to keep users safe."
            ), 
            inline=False
        )
        
        embed.set_footer(text="Last updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        await safe_followup(interaction, "", embed=embed)
        
    except Exception as e:
        logger.error(f"Error in honeypot_stats: {str(e)}")
        await safe_followup(interaction, f"Error retrieving honeypot statistics: {str(e)}")

async def process_model_chat(
    interaction: discord.Interaction,
    model_name: str,
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1000
):
    """
    Process a chat with a model by name.
    
    This function explicitly filters out:
    - Unverified endpoints (verified = 0)
    - Honeypots (is_honeypot = TRUE)
    - Inactive endpoints (is_active = FALSE)
    
    All model interactions are guaranteed to use only verified, 
    non-honeypot, active endpoints for security.
    
    Args:
        interaction: Discord interaction
        model_name: Name of the model to use
        prompt: User message to the model
        system_prompt: Optional system prompt
        temperature: Model temperature parameter
        max_tokens: Maximum tokens in the response
    """
    try:
        # Validate input parameters
        if not model_name or not prompt:
            await safe_followup(interaction, "❌ Both model name and prompt are required.")
            return
            
        # Ensure temperature is within valid range
        safe_temp = max(0.0, min(1.0, temperature))
        
        # Ensure max_tokens is reasonable
        safe_max_tokens = max(10, min(4096, max_tokens))
        
        # Log the chat attempt
        security_logger.info(f"Model chat requested: {model_name} (user: {interaction.user.name}, user_id: {interaction.user.id})")
        
        # Set up query with timeout protection
        try:
            # Select a random model matching the name
            query = f"""
                SELECT m.id, m.name, e.ip, e.port, e.is_honeypot, e.verified, e.is_active,
                       m.parameter_size, m.quantization_level
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                WHERE LOWER(m.name) = LOWER(%s) 
                  AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)} 
                  AND e.is_honeypot = {get_db_boolean(False)}
                  AND e.is_active = {get_db_boolean(True)}
                ORDER BY RANDOM()
                LIMIT 1
            """
            
            # Set a short timeout for this fetch operation
            result = await asyncio.wait_for(
                run_in_thread(Database.fetch_one, query, (model_name,)),
                timeout=5.0  # 5 second timeout
            )
            
            if not result:
                # Try with broader search if exact match fails
                security_logger.info(f"No exact match for '{model_name}', trying broader search")
                query = f"""
                    SELECT m.id, m.name, e.ip, e.port, e.is_honeypot, e.verified, e.is_active,
                           m.parameter_size, m.quantization_level
                    FROM models m
                    JOIN endpoints e ON m.endpoint_id = e.id
                    WHERE LOWER(m.name) LIKE LOWER(%s) 
                      AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)} 
                      AND e.is_honeypot = {get_db_boolean(False)}
                      AND e.is_active = {get_db_boolean(True)}
                    ORDER BY RANDOM()
                    LIMIT 1
                """
                # Set a short timeout for this fetch operation
                result = await asyncio.wait_for(
                    run_in_thread(Database.fetch_one, query, (f"%{model_name}%",)),
                    timeout=5.0  # 5 second timeout
                )
        except asyncio.TimeoutError:
            logger.error(f"Database query timeout while searching for model: {model_name}")
            await safe_followup(interaction, "⚠️ The database query timed out. Please try again later.")
            return
        except Exception as db_error:
            logger.error(f"Database error in model search: {str(db_error)}")
            await safe_followup(interaction, f"⚠️ Database error: {str(db_error)}")
            return
        
        if not result:
            security_logger.warning(f"No models found matching '{model_name}' after broadened search")
            await safe_followup(interaction, f"Model '{model_name}' not found or no active endpoints available.")
            return
        
        model_id, model_name, ip, port, is_honeypot, is_verified, is_active, param_size, quant_level = result
        
        # Safety checks to ensure we never use honeypots or unverified endpoints
        try:
            assert is_honeypot is None or not is_honeypot, f"Critical error: Honeypot endpoint was selected for model {model_name}!"
            assert is_verified, f"Critical error: Unverified endpoint was selected for model {model_name}!"
            assert is_active is None or is_active, f"Critical error: Inactive endpoint was selected for model {model_name}!"
        except AssertionError as e:
            honeypot_logger.error(f"CRITICAL SECURITY VIOLATION: {str(e)} (user: {interaction.user.name}, endpoint: {ip}:{port})")
            security_logger.error(f"CRITICAL SECURITY VIOLATION: {str(e)} (user: {interaction.user.name}, endpoint: {ip}:{port})")
            raise
        
        # Check if endpoint is actually reachable
        is_reachable, error_msg = await check_server_connectivity(ip, port)
        if not is_reachable:
            security_logger.warning(f"Selected endpoint {ip}:{port} is not reachable: {error_msg}")
            await safe_followup(interaction, f"Error: Cannot connect to endpoint {ip}:{port} - {error_msg}\nThis endpoint may be offline. Please try again or try a different model.")
            
            # Mark the endpoint as inactive
            try:
                update_query = f"""
                    UPDATE endpoints 
                    SET is_active = {get_db_boolean(False)},
                        inactive_reason = %s,
                        last_check_date = NOW()
                    WHERE ip = %s AND port = %s
                """
                Database.execute(update_query, (f"Connection failed: {error_msg}", ip, port))
                security_logger.info(f"Marked endpoint {ip}:{port} as inactive due to connection failure")
            except Exception as update_err:
                logger.error(f"Failed to update endpoint status: {str(update_err)}")
            
            return
        
        # Log successful model selection
        security_logger.info(f"Selected model '{model_name}' (ID: {model_id}) from endpoint {ip}:{port}")
        
        # Build model description
        model_desc = f"{model_name}"
        if param_size:
            model_desc += f" ({param_size}"
            if quant_level:
                model_desc += f", {quant_level}"
            model_desc += ")"
        
        await safe_followup(interaction, f"**Using Model: {model_desc}**\nSending prompt to {ip}:{port}...")
        
        # Build request data according to Ollama API spec
        request_data = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "temperature": safe_temp,
            "max_tokens": safe_max_tokens
        }
        
        # Add system prompt if provided
        if system_prompt:
            request_data["system"] = system_prompt
        
        # Send request to Ollama API with stricter timeout
        try:
            # Use a shorter timeout for the model request (30 seconds)
            async with session.post(
                f"http://{ip}:{port}/api/generate", 
                json=request_data, 
                timeout=30  # Reduced from 60 seconds to 30 seconds
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("response", "No response received.")
                    
                    # Get stats if available
                    eval_count = result.get("eval_count", 0)
                    eval_duration = result.get("eval_duration", 0)
                    total_duration = result.get("total_duration", 0)
                    
                    # Add stats to the response
                    stats = f"\n\n---\n"
                    
                    if eval_count > 0:
                        stats += f"Tokens: {eval_count}"
                    
                    if total_duration > 0:
                        total_time_sec = total_duration / 1000000000
                        stats += f" | Total time: {total_time_sec:.2f}s"
                    elif eval_duration > 0:
                        eval_time_sec = eval_duration / 1000000
                        stats += f" | Generation time: {eval_time_sec:.2f}s"
                    
                    if eval_duration > 0 and eval_count > 0:
                        tokens_per_second = eval_count / (eval_duration / 1000000000)
                        stats += f" | Speed: {tokens_per_second:.2f} tokens/sec"
                    
                    response_text += stats
                    
                    # Format the response with bold header but keep the model's output as is
                    formatted_response = f"**Response from {model_name}:**\n{response_text}"
                    
                    # Log completion
                    security_logger.info(f"Completed chat with model '{model_name}', tokens: {eval_count}")
                    
                    await safe_followup(interaction, formatted_response)
                else:
                    response_text = await response.text()
                    security_logger.warning(f"API error from {ip}:{port}: {response.status} - {response_text[:100]}")
                    await safe_followup(interaction, f"Error: {response.status} - {response_text}")
        except asyncio.TimeoutError:
            security_logger.warning(f"Request timeout for model '{model_name}' at {ip}:{port}")
            await safe_followup(interaction, "Request timed out. The model may be taking too long to respond.")
        except aiohttp.ClientError as e:
            logger.error(f"Connection error in model chat: {str(e)}")
            security_logger.error(f"Connection error to endpoint {ip}:{port}: {str(e)}")
            await safe_followup(interaction, f"Request failed: {str(e)}")
            
            # Mark the endpoint as inactive
            try:
                update_query = f"""
                    UPDATE endpoints 
                    SET is_active = {get_db_boolean(False)},
                        inactive_reason = %s,
                        last_check_date = NOW()
                    WHERE ip = %s AND port = %s
                """
                Database.execute(update_query, (f"Connection failed: {str(e)}", ip, port))
                security_logger.info(f"Marked endpoint {ip}:{port} as inactive due to connection error")
            except Exception as update_err:
                logger.error(f"Failed to update endpoint status: {str(update_err)}")
                
        except Exception as e:
            logger.error(f"Unexpected error in model chat: {str(e)}")
            security_logger.error(f"Error communicating with endpoint {ip}:{port}: {str(e)}")
            await safe_followup(interaction, f"An unexpected error occurred: {str(e)}")
            
    except AssertionError as e:
        # Handle safety check failures
        logger.error(f"Safety check failed: {str(e)}")
        await safe_followup(interaction, f"Error: Could not process request due to safety checks. Please try a different model.")
    except Exception as e:
        logger.error(f"Error in model chat: {str(e)}")
        security_logger.error(f"Unexpected error in model chat: {str(e)}")
        await safe_followup(interaction, f"Error: {str(e)}")

@bot.tree.command(name="quickprompt", description="Quickly chat with any Ollama model by name")
@app_commands.describe(
    model_name="Name of the model to use (e.g. llama3, mistral, phi, etc.)",
    prompt="Your message to send to the model",
    system_prompt="Optional system prompt to set context",
    temperature="Controls randomness (0.0 to 1.0)",
    max_tokens="Maximum number of tokens in response"
)
async def quickprompt(
    interaction: discord.Interaction,
    model_name: str,
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1000
):
    """
    Quickly send a prompt to a model by name, automatically finding a suitable endpoint
    
    Args:
        interaction: Discord interaction
        model_name: Name of the model to use (case-insensitive partial match)
        prompt: Your message to the model
        system_prompt: Optional system prompt for context
        temperature: Controls randomness (0.0-1.0)
        max_tokens: Maximum tokens in response
    """
    if not await safe_defer(interaction):
        return
    
    # Call the shared implementation
    await process_model_chat(
        interaction, 
        model_name, 
        prompt, 
        system_prompt, 
        temperature, 
        max_tokens
    )

@bot.tree.command(name="chat", description="Chat with a specific model by ID")
@app_commands.describe(
    model_id="ID of the specific model to use",
    prompt="Your message to send to the model",
    system_prompt="Optional system prompt to set context",
    temperature="Controls randomness (0.0 to 1.0)",
    max_tokens="Maximum number of tokens in response",
    verbose="Show detailed API request and response information"
)
async def chat(
    interaction: discord.Interaction,
    model_id: int,
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1000,
    verbose: bool = False
):
    if not await safe_defer(interaction):
        return
    
    try:
        # Validate model ID
        model_info = await validate_model_id(model_id)
        
        if not model_info["valid"]:
            await safe_followup(interaction, model_info["message"])
            return
        
        # Extract model details
        name = model_info["name"]
        ip = model_info["ip"]
        port = model_info["port"]
        param_size = model_info.get("parameter_size") or "Unknown"
        
        # Validate input parameters
        if not prompt:
            await safe_followup(interaction, "Error: Prompt is required.")
            return
            
        # Ensure temperature is within valid range
        safe_temp = max(0.0, min(1.0, temperature))
        
        # Ensure max_tokens is reasonable
        safe_max_tokens = max(10, min(4096, max_tokens))
        
        # Check if endpoint is reachable
        is_reachable, error_msg = await check_server_connectivity(ip, port)
        if not is_reachable:
            await safe_followup(interaction, f"Error: Cannot connect to endpoint {ip}:{port} - {error_msg}")
            return
        
        # Build request data according to Ollama API spec
        request_data = {
            "model": name,
            "prompt": prompt,
            "stream": False,
            "temperature": safe_temp,
            "max_tokens": safe_max_tokens
        }
        
        # Add system prompt if provided
        if system_prompt:
            request_data["system"] = system_prompt
        
        # Calculate dynamic timeout based on prompt length, model size, and max tokens
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
        token_factor = max(1.0, safe_max_tokens / 1000)
        
        # Calculate final timeout (minimum 180s, maximum 900s)
        dynamic_timeout = min(900, max(180, base_timeout * prompt_factor * param_factor * token_factor))
        
        # Format timeout for display
        timeout_message = f"Timeout set to {int(dynamic_timeout)} seconds based on prompt length and model size."
        if verbose:
            logger.info(f"Dynamic timeout for {name}: {dynamic_timeout:.1f}s (prompt: {prompt_length} chars, model: {param_size}, max_tokens: {safe_max_tokens})")
            await safe_followup(interaction, f"Using Model: {name}\nSending prompt to {ip}:{port}...\n{timeout_message}")
        else:
            await safe_followup(interaction, f"Using Model: {name}\nSending prompt to {ip}:{port}...")
        
        # Record start time for verbose output
        start_time = datetime.now()
        
        # Send request to Ollama API
        try:
            async with session.post(
                f"http://{ip}:{port}/api/generate", 
                json=request_data, 
                timeout=dynamic_timeout
            ) as response:
                if response.status == 200:
                    # Get the raw response text for verbose output
                    raw_response_text = await response.text()
                    result = json.loads(raw_response_text)
                    response_text = result.get("response", "No response received.")
                    
                    # Get stats if available
                    eval_count = result.get("eval_count", 0)
                    eval_duration = result.get("eval_duration", 0)
                    total_duration = result.get("total_duration", 0)
                    
                    # Format the response with proper code blocks and sections
                    formatted_response = f"**Response from {name} (ID: {model_id}):**\n"
                    
                    # Check if response contains a <think> block
                    if "<think>" in response_text and "</think>" in response_text:
                        # Split into think and response parts
                        think_parts = response_text.split("</think>")
                        think_text = think_parts[0].replace("<think>", "").strip()
                        response_text = think_parts[1].strip() if len(think_parts) > 1 else ""
                        
                        # Format think block
                        formatted_response += "**Thinking Process:**\n```\n" + think_text + "\n```\n\n"
                        
                        if response_text:
                            formatted_response += "**Response:**\n"
                    
                    # Process the main response text
                    # Look for code blocks in the response
                    import re
                    code_pattern = r'```(?:\w+)?\n(.*?)```'
                    code_blocks = re.finditer(code_pattern, response_text, re.DOTALL)
                    last_end = 0
                    final_response = ""
                    
                    for match in code_blocks:
                        # Add text before this code block
                        text_before = response_text[last_end:match.start()].strip()
                        if text_before:
                            final_response += text_before + "\n\n"
                        
                        # Add the code block with its original language specifier if any
                        code_block = match.group(0)
                        final_response += code_block + "\n\n"
                        last_end = match.end()
                    
                    # Add any remaining text
                    if last_end < len(response_text):
                        remaining_text = response_text[last_end:].strip()
                        if remaining_text:
                            final_response += remaining_text
                    
                    formatted_response += final_response
                    
                    # Add stats
                    stats = "\n\n**Generation Stats:**\n```"
                    if eval_count > 0:
                        stats += f"\nTokens: {eval_count}"
                    if total_duration > 0:
                        total_time_sec = total_duration / 1000000000
                        stats += f"\nTotal time: {total_time_sec:.2f}s"
                    elif eval_duration > 0:
                        eval_time_sec = eval_duration / 1000000
                        stats += f"\nGeneration time: {eval_time_sec:.2f}s"
                    if eval_duration > 0 and eval_count > 0:
                        tokens_per_second = eval_count / (eval_duration / 1000000000)
                        stats += f"\nSpeed: {tokens_per_second:.2f} tokens/sec"
                    stats += "\n```"
                    
                    formatted_response += stats
                    
                    # If verbose mode is enabled, show the raw API request and response
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

@bot.tree.command(name="find_model_endpoints", description="Find endpoints hosting a specific model")
@app_commands.describe(
    model_name="Name of the model to search for",
    param_size="Filter by parameter size (e.g. 7b, 13b, 70b)",
    quant_level="Filter by quantization level (e.g. Q4_K_M, Q5_K_M)",
    sort_by="Field to sort by (name, verification_date, size_mb)",
    descending="Sort in descending order",
    test_connectivity="Test connectivity of endpoints",
    limit="Maximum number of results to return"
)
async def find_model_endpoints(
    interaction: discord.Interaction,
    model_name: str,
    param_size: Optional[str] = None,
    quant_level: Optional[str] = None,
    sort_by: str = "verification_date",
    descending: bool = True,
    test_connectivity: bool = False,
    limit: int = 25
):
    """
    Find endpoints hosting a specific model.
    
    This function explicitly filters out:
    - Unverified endpoints (verified = 0)
    - Honeypots (is_honeypot = TRUE) 
    - Inactive endpoints (is_active = FALSE)
    
    All results returned are from verified, non-honeypot, active endpoints only.
    
    Args:
        interaction: Discord interaction
        model_name: Model name to search for
        param_size: Optional filter by parameter size
        quant_level: Optional filter by quantization level
        sort_by: Field to sort results by
        descending: Whether to sort in descending order
        test_connectivity: Whether to test endpoint connectivity
        limit: Maximum number of results to return
    """
    await interaction.response.defer()
    
    # Safety check for limit
    if limit <= 0:
        limit = 25  # Default to 25 if invalid limit provided
    
    try:
        logger.info(f"Finding model endpoints for '{model_name}' (param_size={param_size}, quant_level={quant_level})")
        
        # Build the base query with explicit honeypot filtering
        query = f"""
        SELECT DISTINCT m.id, e.ip, e.port, m.name, m.parameter_size, m.quantization_level, m.size_mb, e.verification_date
        FROM endpoints e
        JOIN models m ON e.id = m.endpoint_id
        WHERE m.name LIKE ?
        AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
        AND e.is_active = {get_db_boolean(True)}
        AND e.is_honeypot = {get_db_boolean(False)}
        """
        params = [f"%{model_name}%"]
        
        # Add filters if provided
        if param_size:
            query += " AND m.parameter_size = ?"
            params.append(param_size)
        if quant_level:
            query += " AND m.quantization_level = ?"
            params.append(quant_level)
        
        # Add sorting
        valid_sort_fields = {
            "name": "m.name",
            "verification_date": "e.verification_date",
            "size_mb": "m.size_mb"
        }
        sort_field = valid_sort_fields.get(sort_by.lower(), "e.verification_date")
        query += f" ORDER BY {sort_field} {'DESC' if descending else 'ASC'}"
        
        # Add limit
        query += " LIMIT ?"
        params.append(limit)
        
        # Execute query
        results = Database.fetch_all(query, params)
        
        # Log query info and results count
        logger.info(f"Model endpoint search query completed for '{model_name}': {len(results)} results found")
        logger.debug(f"Used query: {query} with params {params}")
        
        if not results:
            await interaction.followup.send(f"No endpoints found hosting model '{model_name}'")
            return
        
        # Format the results into pages
        results_per_page = 10
        total_pages = (len(results) + results_per_page - 1) // results_per_page
        
        # Create the initial response with search criteria
        search_criteria = f"""
**Search Criteria**
Model Name:     {model_name}
Parameter Size: {param_size if param_size else 'Any'}
Quant Level:    {quant_level if quant_level else 'Any'}
Sort By:        {sort_by} ({'descending' if descending else 'ascending'})

**⚠️ IMPORTANT: Only verified, non-honeypot, active endpoints are shown in results**
"""
        
        # Send the search criteria first
        await interaction.followup.send(search_criteria)
        
        # Process and send results in pages
        for page in range(total_pages):
            start_idx = page * results_per_page
            end_idx = min(start_idx + results_per_page, len(results))
            page_results = results[start_idx:end_idx]
            
            # Format the results table for this page
            table = "```\n"
            table += f"{'ID':<6} {'Endpoint':<25} {'Parameters':<8} {'Quant':<10} {'Size':<8} {'Last Verified':<20} {'Status':<8}\n"
            table += "-" * 85 + "\n"
            
            for result in page_results:
                model_id, ip, port, name, param_size, quant_level, size_mb, verification_date = result
                
                # Format size in MB with 1 decimal place
                size_str = f"{size_mb:.1f}MB" if size_mb else "N/A"
                
                # Format verification date
                if verification_date:
                    try:
                        date_obj = datetime.strptime(verification_date, '%Y-%m-%d %H:%M:%S')
                        date_str = date_obj.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        date_str = verification_date
                else:
                    date_str = "Never"
                
                # Test connectivity if requested
                status = "Testing..." if test_connectivity else "Unknown"
                if test_connectivity:
                    try:
                        url = f"http://{ip}:{port}/api/tags"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(url, timeout=5) as response:
                                if response.status == 200:
                                    status = "Online"
                                else:
                                    status = "Offline"
                    except Exception:
                        status = "Offline"
                
                # Add row to table
                table += f"{model_id:<6} {ip}:{port:<17} {param_size:<8} {quant_level:<10} {size_str:<8} {date_str:<20} {status:<8}\n"
            
            table += "```"
            
            # Add page information
            page_info = f"\nPage {page + 1} of {total_pages}"
            
            # Send the page
            await interaction.followup.send(table + page_info)
        
        # Send usage tips
        tips = """
**Usage Tips:**
• Use `/chat` with an endpoint ID to interact with the model
• Use `/list_models` to see all available models
• Use `/db_info` to see database statistics
"""
        await interaction.followup.send(tips)
        
    except Exception as e:
        logger.error(f"Error in find_model_endpoints: {str(e)}")
        logger.error(f"Error in model_status: {str(e)}")
        await safe_followup(interaction, f"⚠️ Error checking model status: {str(e)}")

@bot.tree.command(name="offline_endpoints", description="View and manage offline endpoints")
@app_commands.describe(
    action="Action to perform",
    ip="Server IP address (for recheck action)",
    port="Server port (for recheck action)",
    hours="Hours threshold for last check (for list action)",
    limit="Maximum number of endpoints to display"
)
@app_commands.choices(action=[
    app_commands.Choice(name="List Offline Endpoints", value="list"),
    app_commands.Choice(name="Recheck Specific Endpoint", value="recheck"),
    app_commands.Choice(name="Statistics", value="stats")
])
async def offline_endpoints(
    interaction: discord.Interaction,
    action: str,
    ip: str = None,
    port: int = None,
    hours: int = 24,
    limit: int = 25
):
    """
    View and manage offline endpoints
    
    Args:
        interaction: Discord interaction
        action: Action to perform (list, recheck, stats)
        ip: Server IP for recheck action
        port: Server port for recheck action
        hours: Hours threshold for last check (for list action)
        limit: Maximum number of results to return
    """
    if not await safe_defer(interaction):
        return
        
    try:
        if action == "list":
            # Get offline endpoints
            conn = Database()
            
            if DATABASE_TYPE == "postgres":
                query = f"""
                    SELECT id, ip, port, is_honeypot, inactive_reason, last_seen, created_at
                    FROM endpoints
                    WHERE is_active = {get_db_boolean(False)}
                    ORDER BY last_seen DESC
                    LIMIT {limit}
                """
            else:
                # SQLite
                query = f"""
                    SELECT id, ip, port, is_honeypot, inactive_reason, last_seen, created_at
                    FROM endpoints
                    WHERE is_active = {get_db_boolean(False)}
                    ORDER BY last_seen DESC
                    LIMIT ?
                """
                
            endpoints = Database.fetch_all(query, (limit,))
            
            if not endpoints:
                await safe_followup(interaction, "✅ No offline endpoints found.")
                return
                
            # Format the list
            message = f"**Offline Endpoints (Last {hours} hours)**\n\n"
            message += "ID | IP:Port | Reason | Last Check\n"
            message += "-" * 80 + "\n"
            
            for endpoint in endpoints:
                endpoint_id, ip, port, is_honeypot, reason, last_seen, created_at = endpoint
                
                # Format last check time
                if last_seen:
                    try:
                        last_check_dt = datetime.fromisoformat(str(last_seen).replace('Z', '+00:00'))
                        last_check_str = last_check_dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        last_check_str = str(last_seen)
                else:
                    last_check_str = "Never"
                    
                message += f"{endpoint_id} | {ip}:{port} | {reason or 'Unknown'} | {last_check_str}\n"
                
            message += f"\nUse `/offline_endpoints action:Recheck Specific Endpoint ip:<ip> port:<port>` to recheck a specific endpoint."
            
            await safe_followup(interaction, message)
            
        elif action == "recheck":
            if not ip or not port:
                await safe_followup(interaction, "⚠️ Error: Both IP and port are required for recheck action.")
                return
                
            # Find the endpoint in the database
            conn = Database()
            
            if DATABASE_TYPE == "postgres":
                query = "SELECT id FROM endpoints WHERE ip = %s AND port = %s"
            else:
                # SQLite
                query = "SELECT id FROM endpoints WHERE ip = ? AND port = ?"
                
            endpoint = Database.fetch_one(query, (ip, port))
            
            if not endpoint:
                await safe_followup(interaction, f"⚠️ Error: Endpoint {ip}:{port} not found in the database.")
                return
                
            endpoint_id = endpoint[0]
            
            # Recheck the endpoint
            await safe_followup(interaction, f"🔄 Rechecking endpoint {ip}:{port}...")
            
            # Import the check_endpoint function
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from prune_bad_endpoints import check_endpoint
            
            # Check the endpoint
            is_valid, message = await check_endpoint(endpoint_id, ip, port)
            
            if is_valid:
                await interaction.edit_original_response(
                    content=f"✅ Endpoint {ip}:{port} is now back online and has been marked as active.\n\nStatus: {message}"
                )
            else:
                await interaction.edit_original_response(
                    content=f"❌ Endpoint {ip}:{port} is still offline.\n\nReason: {message}"
                )
                
        elif action == "stats":
            # Get statistics about offline vs. active endpoints
            conn = Database()
            
            # Get total endpoints
            total_count = Database.fetch_one("SELECT COUNT(*) FROM endpoints")[0]
            
            # Get active endpoints
            if DATABASE_TYPE == "postgres":
                active_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_active = {get_db_boolean(True)}")[0]
                inactive_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_active = {get_db_boolean(False)}")[0]
                honeypot_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_honeypot = {get_db_boolean(True)}")[0]
            else:
                # SQLite
                active_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_active = {get_db_boolean(True)}")[0]
                inactive_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_active = {get_db_boolean(False)}")[0]
                honeypot_count = Database.fetch_one(f"SELECT COUNT(*) FROM endpoints WHERE is_honeypot = {get_db_boolean(True)}")[0]
                
            # Calculate percentages
            active_percent = (active_count / total_count * 100) if total_count > 0 else 0
            inactive_percent = (inactive_count / total_count * 100) if total_count > 0 else 0
            honeypot_percent = (honeypot_count / total_count * 100) if total_count > 0 else 0
            
            # Get most common inactive reasons
            if DATABASE_TYPE == "postgres":
                reasons_query = f"""
                    SELECT inactive_reason, COUNT(*) as count
                    FROM endpoints
                    WHERE is_active = {get_db_boolean(False)} AND inactive_reason IS NOT NULL
                    GROUP BY inactive_reason
                    ORDER BY count DESC
                    LIMIT 5
                """
            else:
                reasons_query = f"""
                    SELECT inactive_reason, COUNT(*) as count
                    FROM endpoints
                    WHERE is_active = {get_db_boolean(False)} AND inactive_reason IS NOT NULL
                    GROUP BY inactive_reason
                    ORDER BY count DESC
                    LIMIT 5
                """
                
            reasons = Database.fetch_all(reasons_query)
            
            # Create a formatted message
            message = "**Endpoint Status Statistics**\n\n"
            message += f"Total Endpoints: {total_count}\n"
            message += f"Active Endpoints: {active_count} ({active_percent:.1f}%)\n"
            message += f"Inactive Endpoints: {inactive_count} ({inactive_percent:.1f}%)\n"
            message += f"Honeypot Endpoints: {honeypot_count} ({honeypot_percent:.1f}%)\n\n"
            
            if reasons:
                message += "**Top Inactive Reasons:**\n"
                for reason, count in reasons:
                    message += f"• {reason}: {count} endpoints\n"
                    
            await safe_followup(interaction, message)
            
        else:
            await safe_followup(interaction, f"⚠️ Invalid action: {action}. Must be 'list', 'recheck', or 'stats'.")
            
    except Exception as e:
        logger.error(f"Error in offline_endpoints command: {str(e)}")
        await safe_followup(interaction, f"⚠️ Error: {str(e)}")

# Add a new utility function after imports and before other functions
def get_db_boolean(value, as_string=True, for_verified=False):
    """
    Standardize boolean values for SQL queries based on database type.
    
    Args:
        value (bool): The boolean value to convert
        as_string (bool): Whether to return a string or a value
        for_verified (bool): Special handling for 'verified' column which is INTEGER (0,1) not BOOLEAN
        
    Returns:
        str or int: A database-appropriate representation of the boolean
    """
    if for_verified or DATABASE_TYPE != "postgres":
        # For verified column or SQLite, always use 1/0
        return "1" if value else "0" if as_string else 1 if value else 0
    else:
        # PostgreSQL boolean format for regular boolean columns
        return "TRUE" if value else "FALSE" if as_string else True if value else False

async def find_model(model_name=None, param_size=None, quant_level=None):
    """
    Find model records in the database.
    
    This function explicitly filters out:
    - Unverified endpoints (verified = 0)
    - Honeypots (is_honeypot = TRUE)
    - Inactive endpoints (is_active = FALSE)
    
    Args:
        model_name: Optional filter for model name
        param_size: Optional parameter size filter (e.g., "7B")
        quant_level: Optional quantization filter (e.g., "Q4_K_M")
    """
    try:
        security_logger.info(f"Searching for models: name='{model_name}', param_size='{param_size}', quant='{quant_level}'")
        
        # Build the base query
        query = f"""
            SELECT m.id, m.name, e.ip, e.port, m.parameter_size, m.quantization_level
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)} 
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
        """
        params = []

        # Apply filters if provided
        if model_name:
            params.append(f"%{model_name}%")
            query += " AND LOWER(m.name) LIKE LOWER(%s)"

        if param_size:
            params.append(f"%{param_size}%")
            query += " AND m.parameter_size LIKE %s"

        if quant_level:
            params.append(f"%{quant_level}%")
            query += " AND m.quantization_level LIKE %s"

        # Order by name
        query += " ORDER BY m.name, m.parameter_size"
        
        # Log the query for security audit
        security_logger.debug(f"Model search query: {query} with params: {params}")
        
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            security_logger.info(f"No models found matching criteria: name='{model_name}', param_size='{param_size}', quant='{quant_level}'")
            return None

        # Log found models count
        security_logger.info(f"Found {len(results)} models matching criteria")
        
        # For very large result sets, limit the return size
        if len(results) > 50:
            security_logger.info(f"Limiting results from {len(results)} to 50 for display")
            results = results[:50]

        return results
    except Exception as e:
        logger.error(f"Error finding models: {str(e)}")
        security_logger.error(f"Database exception during model search: {str(e)}")
        return None


async def find_model_endpoints(model_name=None, param_size=None, quant_level=None, limit=25):
    """
    Find model endpoints that match the given criteria.
    
    This function explicitly filters out:
    - Unverified endpoints (verified = 0)
    - Honeypots (is_honeypot = TRUE)
    - Inactive endpoints (is_active = FALSE)
    
    Args:
        model_name: Optional filter for model name
        param_size: Optional parameter size filter (e.g., "7B")
        quant_level: Optional quantization filter (e.g., "Q4_K_M")
        limit: Maximum number of results to return (default 25)
        
    Returns:
        A formatted message with the search results or an error message.
    """
    try:
        # Ensure limit is reasonable
        limit = min(max(1, limit), 100)
        
        # Log the search request
        security_logger.info(f"Searching for model endpoints: name='{model_name}', param_size='{param_size}', quant='{quant_level}', limit={limit}")
        
        # Build the base query
        query = f"""
            SELECT m.id, m.name, e.ip, e.port, m.parameter_size, m.quantization_level,
                   e.last_verified, e.verified_healthy
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE e.verified = {get_db_boolean(True, as_string=True, for_verified=True)} 
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
        """
        params = []

        # Apply filters if provided
        if model_name:
            params.append(f"%{model_name}%")
            query += " AND LOWER(m.name) LIKE LOWER(%s)"
            
        if param_size:
            params.append(f"%{param_size}%")
            query += " AND m.parameter_size LIKE %s"
            
        if quant_level:
            params.append(f"%{quant_level}%")
            query += " AND m.quantization_level LIKE %s"
            
        # Add order and limit
        query += " ORDER BY m.name, m.parameter_size LIMIT %s"
        params.append(limit)
        
        # Log the query for security audit
        security_logger.debug(f"Model endpoint search query: {query} with params: {params}")
        
        # Execute the query
        results = Database.fetch_all(query, tuple(params))
        
        if not results:
            security_logger.info(f"No model endpoints found matching criteria (honeypots filtered)")
            return "No model endpoints found matching your criteria."
            
        # Log results count
        security_logger.info(f"Found {len(results)} model endpoints matching criteria (honeypots filtered)")
        
        # Format results
        formatted_results = [
            f"**ID**: {result[0]} | **Name**: {result[1]} | **Endpoint**: {result[2]}:{result[3]}"
            f"{f' | **Params**: {result[4]}' if result[4] else ''}"
            f"{f' | **Quant**: {result[5]}' if result[5] else ''}"
            f" | **Last verified**: {result[6] or 'Unknown'}"
            f" | **Status**: {'✅ Healthy' if result[7] else '⚠️ Issues'}"
            for result in results
        ]
        
        # Create batches of 10 for pagination
        batches = [formatted_results[i:i + 10] for i in range(0, len(formatted_results), 10)]
        
        # Format final output
        pages = []
        for i, batch in enumerate(batches):
            page = f"**Model Endpoints Search Results (Page {i+1}/{len(batches)}):**\n"
            page += "```\n• " + "\n• ".join(batch) + "\n```"
            
            if i == 0:  # Add tips only to the first page
                page += "\n**Usage Tips:**\n• Use these IDs with /chat_model or /ask commands\n• All returned models are verified and active\n• Honeypot endpoints are automatically filtered out for your security"
                
            pages.append(page)
            
        return pages
    except Exception as e:
        logger.error(f"Error finding model endpoints: {str(e)}")
        security_logger.error(f"Exception during model endpoint search: {str(e)}")
        return f"Error searching for model endpoints: {str(e)}"

async def get_endpoint(endpoint_id):
    """
    Retrieve a specific endpoint by ID.
    
    This function explicitly filters out honeypots (is_honeypot = TRUE)
    to ensure security.
    
    Args:
        endpoint_id: The ID of the endpoint to retrieve
        
    Returns:
        Endpoint data tuple or None if not found/honeypot
    """
    try:
        security_logger.info(f"Retrieving endpoint ID={endpoint_id}")
        
        query = f"""
            SELECT id, ip, port, api_key, is_active, verified, is_honeypot, verified_healthy
            FROM endpoints
            WHERE id = %s
            AND is_honeypot = {get_db_boolean(False)}
        """
        
        # Log the query for security audit (omit sensitive data)
        security_logger.debug(f"Endpoint retrieval query for ID={endpoint_id}")
        
        result = Database.fetch_one(query, (endpoint_id,))
        
        if not result:
            security_logger.warning(f"Endpoint ID {endpoint_id} not found or is a honeypot")
            return None
            
        # Second safety check to ensure no honeypots get through
        if result[6]:  # is_honeypot
            honeypot_logger.error(f"CRITICAL: Honeypot endpoint (ID: {endpoint_id}) was retrieved despite filter!")
            security_logger.error(f"CRITICAL SECURITY BREACH: Honeypot endpoint (ID: {endpoint_id}) was retrieved despite filter!")
            return None
            
        security_logger.info(f"Endpoint ID {endpoint_id} retrieved successfully")
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving endpoint: {str(e)}")
        security_logger.error(f"Exception during endpoint retrieval: {str(e)}")
        return None

# Main function to run the bot
def main():
    """Main function to run the bot"""
    # Initialize database schema
    try:
        logger.info("Starting Ollama Scanner Discord bot")
        
        # Explicitly load .env file
        from dotenv import load_dotenv
        logger.info("Loading environment variables from .env")
        # Load the .env file from the same directory as the script
        dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path)
            logger.info(f"Loaded .env file from {dotenv_path}")
        else:
            logger.warning(f".env file not found at {dotenv_path}")
        
        # Set up the database - make sure it's initialized before the bot starts
        logger.info("Initializing database connection...")
        init_database()
        
        # Test database connection
        try:
            # Explicitly initialize the connection pool
            Database.ensure_pool_initialized()
            result = Database.fetch_one("SELECT version()")
            if result:
                logger.info(f"Connected to database: {result[0]}")
            else:
                logger.warning("Database connection test returned no result")
        except Exception as e:
            logger.error(f"Error testing database connection: {str(e)}")
            logger.error("Bot will start, but database operations may fail")
        
        # Run the bot with token
        # Load token directly from .env file to avoid environment variable conflicts
        token = None
        try:
            dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
            if os.path.exists(dotenv_path):
                with open(dotenv_path, 'r') as f:
                    for line in f:
                        if line.strip().startswith('DISCORD_BOT_TOKEN='):
                            token = line.strip().split('=', 1)[1]
                            # Remove quotes if present
                            if token.startswith('"') and token.endswith('"'):
                                token = token[1:-1]
                            elif token.startswith("'") and token.endswith("'"):
                                token = token[1:-1]
                            break
                logger.info(f"Token loaded directly from file")
            else:
                logger.warning(f".env file not found at {dotenv_path}")
        except Exception as e:
            logger.error(f"Error loading token from file: {str(e)}")
            
        # If direct file load fails, fall back to environment variable
        if not token:
            token = os.getenv('DISCORD_BOT_TOKEN')
            
        if not token:
            logger.error("Error: DISCORD_BOT_TOKEN not found in .env file or environment variables.")
            exit(1)
            
        # Add debug info about token (showing only first 5 chars for security)
        token_prefix = token[:5] if len(token) >= 5 else token
        logger.info(f"Token loaded (first 5 chars: {token_prefix}...)")
        
        logger.info("Starting bot...")
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Closing bot gracefully.")
    except discord.errors.LoginFailure:
        logger.error("Error: Invalid token. Please check your DISCORD_BOT_TOKEN environment variable.")
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
    finally:
        # Close the aiohttp session if it's been created
        if 'session' in globals() and session is not None:
            asyncio.run(session.close())
            logger.info("Closed aiohttp session")
        
        # Make sure database connections are properly closed
        try:
            db_manager = get_db_manager()
            # Only close connections if the pool exists and is initialized
            if hasattr(db_manager, '_is_initialized') and db_manager._is_initialized:
                Database.close()
                logger.info("Closed database connections")
            else:
                logger.info("No active database connections to close")
        except Exception as e:
            logger.error(f"Error closing database connections: {str(e)}")
        
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    main()
