#!/usr/bin/env python3
"""
Script to force register and sync all the consolidated commands at once.
"""

import logging
import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys

# Configure logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sync_commands.log")
    ]
)
logger = logging.getLogger("force_sync_commands")

print("Starting force_sync_commands.py script")
logger.info("Script initialized")

# Import the essential modules
try:
    print("Importing required modules...")
    from utils import format_embed_message, safe_defer, safe_followup
    from register_consolidated_commands import register_commands_with_bot, apply_command_deprecation
    print("Successfully imported required modules")
except ImportError as e:
    print(f"Failed to import required modules: {e}")
    logger.error(f"Failed to import required modules: {e}")
    raise

async def force_sync_commands():
    """
    Force register and sync all the consolidated commands.
    """
    print("Starting force_sync_commands() function")
    logger.info("Starting force_sync_commands() function")
    
    # Load environment variables
    print("Loading environment variables...")
    load_dotenv()
    print("Environment variables loaded")
    
    # Get bot token
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("No Discord bot token found in environment variables")
        logger.error("No Discord bot token found in environment variables")
        return
    
    token_prefix = token[:5] if len(token) >= 5 else token
    print(f"Found token (first 5 chars: {token_prefix}...)")
    logger.info(f"Found token (first 5 chars: {token_prefix}...)")
        
    print("Starting bot to register commands...")
    logger.info("Starting bot to register commands...")
    
    # Set up the bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)
    print("Bot instance created")
    
    @bot.event
    async def on_ready():
        try:
            print(f"Logged in as {bot.user} (ID: {bot.user.id})")
            logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
            
            # The consolidated commands we want to ensure are registered
            required_commands = [
                "models",   # Unified model discovery command
                "chat",     # Unified chat command
                "server",   # Unified server management command
                "history",  # Chat history command
                "help",     # Updated help command
                "admin",    # Administrative functions command
                "manage",   # Management command
                "stats",    # Statistics command
                "ping"      # Basic bot status check
            ]
            
            # Remove existing commands that match the ones we want to register
            print("Fetching existing commands...")
            existing_commands = await bot.tree.fetch_commands()
            existing_command_names = [cmd.name for cmd in existing_commands]
            print(f"Existing commands: {', '.join(existing_command_names) if existing_command_names else 'None'}")
            logger.info(f"Existing commands: {', '.join(existing_command_names) if existing_command_names else 'None'}")
            
            for cmd_name in existing_command_names:
                print(f"Removing command: {cmd_name}")
                logger.info(f"Removing command: {cmd_name}")
                bot.tree.remove_command(cmd_name)
            
            # Register consolidated commands
            try:
                print("Registering consolidated commands...")
                commands = register_commands_with_bot(bot, safe_defer, safe_followup)
                print(f"Successfully registered consolidated commands: {', '.join(commands.keys())}")
                logger.info(f"Successfully registered consolidated commands: {', '.join(commands.keys())}")
                
                # Apply deprecation notices to old commands
                print("Applying deprecation notices to old commands...")
                apply_command_deprecation(bot)
                print("Applied deprecation notices to old commands")
                logger.info("Applied deprecation notices to old commands")
            except Exception as e:
                print(f"Error registering consolidated commands: {e}")
                logger.error(f"Error registering consolidated commands: {e}")
            
            # Sync commands with Discord
            try:
                # Sync globally
                print("Syncing commands globally...")
                synced = await bot.tree.sync()
                print(f"Successfully synced {len(synced)} commands globally")
                logger.info(f"Successfully synced {len(synced)} commands globally")
                
                # Sync with each guild for immediate availability
                for guild in bot.guilds:
                    try:
                        print(f"Syncing commands with guild: {guild.name} (ID: {guild.id})...")
                        guild_synced = await bot.tree.sync(guild=guild)
                        print(f"Synced {len(guild_synced)} commands with guild: {guild.name}")
                        logger.info(f"Synced {len(guild_synced)} commands with guild: {guild.name} (ID: {guild.id})")
                    except Exception as e:
                        print(f"Error syncing commands with guild {guild.name}: {e}")
                        logger.error(f"Error syncing commands with guild {guild.name}: {e}")
            except Exception as e:
                print(f"Error syncing commands: {e}")
                logger.error(f"Error syncing commands: {e}")
            
            # Check if all required commands are registered
            print("Checking if all required commands are registered...")
            final_commands = await bot.tree.fetch_commands()
            final_command_names = [cmd.name for cmd in final_commands]
            print(f"Final commands: {', '.join(final_command_names) if final_command_names else 'None'}")
            logger.info(f"Final commands: {', '.join(final_command_names) if final_command_names else 'None'}")
            
            missing_commands = [cmd for cmd in required_commands if cmd not in final_command_names]
            if missing_commands:
                print(f"Some commands are still missing: {', '.join(missing_commands)}")
                logger.warning(f"Some commands are still missing: {', '.join(missing_commands)}")
            else:
                print("All required commands are now registered!")
                logger.info("All required commands are now registered!")
            
            # Close the bot
            print("Closing bot connection...")
            await bot.close()
            print("Bot connection closed")
        except Exception as e:
            print(f"Error in on_ready: {e}")
            logger.error(f"Error in on_ready: {e}")
            await bot.close()
        finally:
            # Properly close http sessions to avoid "unclosed connector" warnings
            if hasattr(bot, 'http') and hasattr(bot.http, '_HTTPClient__session') and bot.http._HTTPClient__session:
                print("Closing HTTP session...")
                try:
                    await bot.http._HTTPClient__session.close()
                    print("HTTP session closed")
                except Exception as e:
                    print(f"Error closing HTTP session: {e}")
                    logger.error(f"Error closing HTTP session: {e}")
                    
            # Clean up any other resources
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    try:
                        task.cancel()
                    except Exception:
                        pass
    
    try:
        # Start the bot
        print("Starting bot...")
        await bot.start(token)
    except Exception as e:
        print(f"Error starting bot: {e}")
        logger.error(f"Error starting bot: {e}")
    finally:
        print("Command sync complete")
        logger.info("Command sync complete")

# Main entry point
if __name__ == "__main__":
    print("Script running as __main__")
    try:
        print("Starting asyncio.run(force_sync_commands())")
        asyncio.run(force_sync_commands())
        print("asyncio.run completed")
    except Exception as e:
        print(f"Error in main: {e}")
        logger.error(f"Error in main: {e}")
    print("Script execution complete") 