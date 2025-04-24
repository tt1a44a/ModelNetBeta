#!/usr/bin/env python3
"""
Guild Unified Commands

This script integrates unified commands with proper guild registration
to fix permission issues with command registration.
"""

import os
import sys
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import logging
import aiohttp
from typing import Optional, List, Tuple
import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("command_registration.log")
    ]
)
logger = logging.getLogger('command_registration')

# Add path for local imports if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the unified commands registration function
from unified_commands import register_unified_commands

# Import database abstraction
from database import Database, init_database, get_db_manager

# Load environment variables
load_dotenv()

# Set up Discord client with intents
intents = discord.Intents.default()
intents.message_content = True

# Get the guild ID from environment variable
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '936535618278809670'))
MY_GUILD = discord.Object(id=GUILD_ID)

# Database file path for SQLite (for backward compatibility)
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ollama_instances.db")

# Utility async functions
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

# Server connectivity functions
async def check_server_connectivity(ip, port, session):
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
    """
    Sync models with a server
    
    Args:
        ip: Server IP
        port: Server port
        
    Returns:
        tuple: (added_models, updated_models, removed_models)
    """
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
            SELECT 
                s.id, 
                s.ip, 
                s.port, 
                s.scan_date,
                COUNT(m.id) as model_count
            FROM 
                servers s
            LEFT JOIN 
                models m ON s.id = m.server_id
            GROUP BY 
                s.id, s.ip, s.port, s.scan_date
            ORDER BY 
                s.scan_date DESC
        """
        
        servers = Database.fetch_all(query)
        conn.close()
        return servers
    except Exception as e:
        logger.error(f"Error getting servers: {str(e)}")
        return []

class GuildUnifiedBot(commands.Bot):
    """A Discord bot with unified commands registered to a specific guild"""
    
    def __init__(self, command_prefix, intents, guild_id):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.guild_id = guild_id
        self.guild_object = discord.Object(id=guild_id)
        self.session = None
        
    async def setup_hook(self):
        """This is called when the bot is starting up"""
        self.session = aiohttp.ClientSession()
        
        # Register basic test commands
        @self.tree.command(name="ping", description="Test bot responsiveness", guild=self.guild_object)
        async def ping_command(interaction):
            await interaction.response.send_message("Pong! Bot is working correctly!", ephemeral=True)
            
        # Register the unified commands with the bot
        register_unified_commands(
            self,
            DB_FILE,
            safe_defer,
            safe_followup,
            self.session,
            lambda ip, port: check_server_connectivity(ip, port, self.session),
            logger,
            sync_models_with_server,
            get_servers
        )
        
        # Register debugging command
        @self.tree.command(name="listcommands", description="List all registered commands", guild=self.guild_object)
        async def list_commands(interaction):
            await interaction.response.defer(ephemeral=True)
            
            commands = self.tree.get_commands(guild=self.guild_object)
            command_list = "\n".join([f"- {cmd.name}" for cmd in commands])
            
            await interaction.followup.send(
                f"**{len(commands)} commands registered:**\n```\n{command_list}\n```",
                ephemeral=True
            )
        
        # Set up command error handler
        self.tree.error(self.on_command_error)
        
        # Sync commands to the guild
        try:
            logger.info(f"Syncing {len(self.tree.get_commands(guild=self.guild_object))} commands to guild {self.guild_id}")
            await self.tree.sync(guild=self.guild_object)
        except discord.errors.Forbidden as e:
            if e.code == 50001:  # Missing Access
                logger.error("MISSING ACCESS ERROR: Bot doesn't have permission to register commands.")
                logger.error("Run fix_permissions.py to generate a proper invite URL with admin permissions.")
                raise
        except Exception as e:
            logger.error(f"Error syncing commands: {str(e)}")
            raise
    
    async def on_command_error(self, interaction, error):
        """Handle errors from application commands"""
        if isinstance(error, app_commands.errors.CommandNotFound):
            await safe_followup(interaction, "Command not found. Please use /help to see available commands.", ephemeral=True)
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await safe_followup(interaction, f"You don't have the required permissions to use this command: {str(error)}", ephemeral=True)
        elif isinstance(error, app_commands.errors.BotMissingPermissions):
            await safe_followup(interaction, f"Bot is missing required permissions: {str(error)}\nPlease reinvite the bot with proper permissions.", ephemeral=True)
        else:
            error_id = f"{interaction.id}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.error(f"Command error ID: {error_id} - {str(error)}", exc_info=True)
            await safe_followup(
                interaction, 
                f"An error occurred: {str(error)}\nError ID: {error_id}\nPlease report this to the bot administrator.",
                ephemeral=True
            )
    
    async def close(self):
        """Close the bot and its session"""
        if self.session:
            await self.session.close()
        await super().close()

async def main():
    """Main function to run the bot"""
    # Initialize database
    init_database()
    
    # Create bot instance
    bot = GuildUnifiedBot(command_prefix="/", intents=intents, guild_id=GUILD_ID)
    
    # Load token from environment
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("No DISCORD_TOKEN found in environment variables!")
        return
    
    # Add ready event
    @bot.event
    async def on_ready():
        guild_count = len(bot.guilds)
        logger.info(f"Bot {bot.user} is connected to {guild_count} guild(s)")
        for guild in bot.guilds:
            logger.info(f"- {guild.name} (ID: {guild.id})")
        
        # List all commands
        commands = bot.tree.get_commands(guild=MY_GUILD)
        command_names = [cmd.name for cmd in commands]
        logger.info(f"Registered {len(commands)} guild commands: {', '.join(command_names)}")
    
    try:
        # Run the bot
        logger.info(f"Starting bot with token: {token[:5]}...{token[-5:]}")
        await bot.start(token)
    except discord.errors.Forbidden as e:
        if e.code == 50001:  # Missing Access error
            logger.error("MISSING ACCESS ERROR: The bot doesn't have the necessary permissions to register commands.")
            logger.error("Please follow these steps to fix the permission issue:")
            logger.error("1. Run the fix_permissions.py script to get the proper invite URL")
            logger.error("2. Remove the bot from your Discord server")
            logger.error("3. Re-add the bot using the new invite URL with administrator permissions")
            logger.error("4. Run this script again after re-adding the bot")
            
            # Try to send the fix instructions via system output as well
            print("\n" + "="*60)
            print("DISCORD PERMISSION ERROR DETECTED")
            print("="*60)
            print("\nThe bot doesn't have the necessary permissions to register commands.")
            print("\nTo fix this issue:")
            print("1. Run: python fix_permissions.py --reauth")
            print("2. Remove the bot from your Discord server")
            print("3. Re-add the bot using the generated invite URL")
            print("4. Run this script again\n")
            print("="*60 + "\n")
    except discord.errors.HTTPException as e:
        logger.error(f"HTTP Error from Discord: {e}")
        # Provide more detailed error handling based on error types
        if e.code == 10062:  # Unknown interaction
            logger.error("Unknown interaction error: Command may have timed out.")
        elif e.code == 50035:  # Invalid form body
            logger.error("Invalid form body: There may be issues with the command parameters.")
        print(f"\nDiscord API Error: {e}")
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
        print(f"\nUnexpected error: {str(e)}")
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    asyncio.run(main()) 