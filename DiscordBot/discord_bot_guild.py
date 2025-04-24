#!/usr/bin/env python3
"""
Discord Bot Interface for Ollama Scanner
This version uses GUILD-SPECIFIC COMMANDS to avoid rate limits
"""

import os
import sys
import time
import asyncio
import logging
import importlib
import json
import random
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime

# Import database abstraction layer
from database import Database, init_database

# Import unified commands registration
from unified_commands import register_unified_commands

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("discord_bot.log")
    ]
)
logger = logging.getLogger('ollama_bot')

# Initialize Discord client with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Global aiohttp session for API requests
session = None

# Global constants
DEFAULT_PORT = 11434
API_TIMEOUT = 5  # seconds

# Define your primary guild ID here (where commands will be registered)
PRIMARY_GUILD_ID = 936535618278809670  # Discord server ID for guild-specific commands

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord"""
    try:
        # Create global aiohttp session with proper timeouts
        global session
        timeout = aiohttp.ClientTimeout(total=30, sock_connect=10, sock_read=10)
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
            
        # Register unified commands
        DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ollama_instances.db")
        register_unified_commands(
            bot=bot,
            DB_FILE=DB_FILE,
            safe_defer=safe_defer,
            safe_followup=safe_followup,
            session=session,
            check_server_connectivity=check_server_connectivity,
            logger=logger,
            sync_models_with_server=sync_models_with_server,
            get_servers=get_servers
        )
        
        # The explicitly approved commands for the streamlined bot
        approved_commands = [
            "ping", 
            "help", 
            "benchmark", 
            "manage_models",
            "list_models", 
            "db_info", 
            "quickprompt", 
            "chat",
            "find_model_endpoints",
            "all_models",
            "server_info",
            "models_with_servers",
            "cleanup"
        ]
        
        # Get the guild object
        guild = discord.Object(id=PRIMARY_GUILD_ID)
        
        try:
            # IMPORTANT: Skip global command syncing entirely to avoid rate limits
            logger.info(f"Skipping global command sync to avoid rate limits")
            
            # Make sure ONLY the commands we want are in the command tree
            all_commands = {}
            for command in bot.tree.get_commands():
                all_commands[command.name] = command
                
            for cmd_name in list(all_commands.keys()):
                if cmd_name not in approved_commands:
                    logger.info(f"Removing unauthorized command: {cmd_name}")
                    bot.tree.remove_command(cmd_name)
            
            # GUILD SPECIFIC SYNC: Only sync with the specific guild
            # This has a much higher rate limit than global commands
            logger.info(f"Syncing commands with guild ID: {PRIMARY_GUILD_ID}")
            await bot.tree.sync(guild=guild)
            logger.info(f"Command sync with guild complete - commands are now available")
            
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limited
                logger.warning(f"Rate limited when syncing guild commands - waiting {getattr(e, 'retry_after', 'unknown')} seconds")
            else:
                logger.error(f"HTTP error when syncing guild commands: {e}")
        except Exception as e:
            logger.error(f"Error syncing guild commands: {e}")
        
        # Set bot status
        activity = discord.Activity(type=discord.ActivityType.watching, name="Ollama instances")
        await bot.change_presence(activity=activity)
        
        logger.info("Bot is ready with GUILD-SPECIFIC commands!")
        print(f"Bot is ready with GUILD-SPECIFIC commands! Logged in as {bot.user} (ID: {bot.user.id})")
        
    except Exception as e:
        logger.error(f"Error in on_ready: {str(e)}")
        print(f"Error in on_ready: {str(e)}")

async def keep_alive():
    """Maintains bot connection with periodic network activity"""
    logger.info("Connection maintenance task initiated")
    while not bot.is_closed():
        try:
            # Log a heartbeat message every 5 minutes
            logger.debug("Connection maintenance heartbeat")
            await asyncio.sleep(300)  # 5 minutes
        except Exception as e:
            logger.error(f"Error in connection maintenance: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute and try again

async def safe_defer(interaction):
    """Safely defer an interaction, handling potential timeouts"""
    try:
        await interaction.response.defer(thinking=True)
        return True
    except discord.errors.NotFound:
        # Interaction expired/unknown - likely took too long to respond
        logger.warning(f"Interaction expired before deferring: {interaction.command.name if interaction.command else 'unknown'}")
        return False
    except Exception as e:
        logger.error(f"Error deferring interaction: {str(e)}")
        return False

async def safe_followup(interaction, content="", ephemeral=True, file=None):
    """Safely follow up on an interaction, handling errors gracefully"""
    try:
        if interaction.response.is_done():
            if file:
                return await interaction.followup.send(content=content, ephemeral=ephemeral, file=file)
            else:
                return await interaction.followup.send(content=content, ephemeral=ephemeral)
        else:
            if file:
                return await interaction.response.send_message(content=content, ephemeral=ephemeral, file=file)
            else:
                return await interaction.response.send_message(content=content, ephemeral=ephemeral)
    except Exception as e:
        logger.error(f"Error in safe_followup: {str(e)}")
        return None

async def check_server_connectivity(ip, port):
    """Check if an Ollama server is reachable"""
    try:
        async with session.get(f"http://{ip}:{port}/api/tags", timeout=5) as response:
            if response.status == 200:
                return True, await response.json()
            else:
                return False, f"HTTP {response.status}"
    except Exception as e:
        return False, str(e)

def sync_models_with_server(ip, port):
    """Sync models with a server"""
    try:
        import requests
        response = requests.get(f"http://{ip}:{port}/api/tags", timeout=5)
        
        if response.status_code != 200:
            logger.error(f"Failed to get models from {ip}:{port}: HTTP {response.status_code}")
            return [], [], []
            
        server_models = response.json().get("models", [])
        
        # Get server ID
        conn = Database()
        server_query = "SELECT id FROM servers WHERE ip = %s AND port = %s"
        server_result = Database.fetch_one(server_query, (ip, port))
        
        if not server_result:
            logger.error(f"Server {ip}:{port} not found in database")
            return [], [], []
            
        server_id = server_result[0]
        
        # Get existing models for this server
        models_query = "SELECT id, name FROM models WHERE server_id = %s"
        existing_models = {model[1]: model[0] for model in Database.fetch_all(models_query, (server_id,))}
        
        added_models = []
        updated_models = []
        
        # Process each model from the server
        for model_info in server_models:
            model_name = model_info.get("name")
            
            if not model_name:
                continue
                
            # Parse model details (simplified example)
            param_size = "Unknown"
            quant_level = "Unknown"
            
            # Extract parameter size (e.g., "7B", "13B")
            import re
            param_match = re.search(r'(\d+)[bB]', model_name)
            if param_match:
                param_size = f"{param_match.group(1)}B"
                
            # Extract quantization (e.g., "Q4_0", "Q8_0")
            quant_match = re.search(r'[qQ](\d+(?:_\d+)?(?:_[kK])?(?:_[mM])?)', model_name)
            if quant_match:
                quant_level = f"Q{quant_match.group(1).upper()}"
            
            if model_name in existing_models:
                # Model exists, update it
                update_query = """
                    UPDATE models 
                    SET parameter_size = %s, quantization_level = %s, last_updated = NOW()
                    WHERE id = %s
                """
                Database.execute(update_query, (param_size, quant_level, existing_models[model_name]))
                updated_models.append(model_name)
            else:
                # New model, add it
                insert_query = """
                    INSERT INTO models (name, parameter_size, quantization_level, server_id, created_date)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id
                """
                result = Database.fetch_one(insert_query, (model_name, param_size, quant_level, server_id))
                if result:
                    added_models.append(model_name)
        
        # Check for models that need to be removed
        server_model_names = [m.get("name") for m in server_models if m.get("name")]
        models_to_remove = [model_id for model_name, model_id in existing_models.items() 
                           if model_name not in server_model_names]
        
        # Removed models (placeholder - in production you'd handle this carefully)
        removed_models = []
        
        conn.close()
        return added_models, updated_models, removed_models
    except Exception as e:
        logger.error(f"Error syncing models with server {ip}:{port}: {str(e)}")
        return [], [], []

def get_servers():
    """Get all servers from the database"""
    try:
        conn = Database()
        
        # Get servers with model counts
        query = """
            SELECT s.id, s.ip, s.port, s.last_scan_date, COUNT(m.id) as model_count
            FROM servers s
            LEFT JOIN models m ON s.id = m.server_id
            GROUP BY s.id, s.ip, s.port, s.last_scan_date
            ORDER BY s.id
        """
        
        results = Database.fetch_all(query)
        
        # Format results
        servers = []
        for row in results:
            servers.append({
                'id': row[0],
                'ip': row[1],
                'port': row[2],
                'last_scan_date': row[3],
                'model_count': row[4]
            })
        
        conn.close()
        return servers
    except Exception as e:
        logger.error(f"Error getting servers: {str(e)}")
        return []

# Main function to run the bot
def main():
    """Main function to run the bot with guild-specific commands"""
    # Initialize database schema
    try:
        logger.info("Starting Ollama Scanner Discord bot (GUILD-SPECIFIC VERSION)")
        
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
                            logger.info("Token loaded directly from file")
            
            if not token:
                # Fallback to environment variable
                token = os.getenv('DISCORD_BOT_TOKEN')
                logger.info("Token loaded from environment variable")
            
            if not token:
                logger.error("No Discord bot token found in .env file or environment variables")
                sys.exit(1)
            
            logger.info(f"Token loaded (first 5 chars: {token[:5]}...)")
            logger.info("Starting bot...")
            bot.run(token)
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)
    finally:
        # Clean up on exit
        if session and not session.closed:
            asyncio.run(session.close())
            logger.info("Closed aiohttp session")
        
        # Close database pool connections
        try:
            logger.info("Closing database connections...")
            Database.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
        
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    main() 