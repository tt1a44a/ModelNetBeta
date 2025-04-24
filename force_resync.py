#!/usr/bin/env python3
"""
Force Resync Script for Discord Commands

This script forces a resync of Discord commands for a specified guild ID.
It loads the bot token from the environment and performs a sync operation.

Usage:
    ./force_resync.py <guild_id>
"""

import os
import sys
import discord
from discord import app_commands
import asyncio
import logging
import argparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('force_resync')

class ResyncBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.synced = False
    
    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('Bot is ready for command sync operations.')
        
        # List all guilds the bot is in
        logger.info(f'Bot is in {len(self.guilds)} guilds:')
        for guild in self.guilds:
            logger.info(f'- {guild.name} (ID: {guild.id})')
    
    async def fetch_commands(self, guild_id=None):
        """Fetch existing commands for the specified guild or global commands"""
        try:
            if guild_id:
                guild = self.get_guild(guild_id)
                if not guild:
                    logger.error(f"Guild with ID {guild_id} not found")
                    return []
                commands = await self.tree.fetch_commands(guild=guild)
                logger.info(f"Found {len(commands)} commands in guild {guild.name}")
            else:
                commands = await self.tree.fetch_commands()
                logger.info(f"Found {len(commands)} global commands")
            
            return commands
        except Exception as e:
            logger.error(f"Error fetching commands: {e}")
            return []
    
    async def sync_commands(self, guild_id=None):
        """Sync commands to the specified guild or globally"""
        try:
            if guild_id:
                guild = self.get_guild(guild_id)
                if not guild:
                    logger.error(f"Guild with ID {guild_id} not found")
                    return False
                
                # First fetch the existing commands
                before_commands = await self.fetch_commands(guild_id)
                logger.info(f"Before sync: {len(before_commands)} commands in guild {guild.name}")
                
                # Sync commands to the guild
                synced = await self.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} commands to guild {guild.name}")
                
                # List the command names
                command_names = [cmd.name for cmd in synced]
                logger.info(f"Synced commands: {', '.join(command_names)}")
                
                self.synced = True
                return True
            else:
                # First fetch the existing global commands
                before_commands = await self.fetch_commands()
                logger.info(f"Before sync: {len(before_commands)} global commands")
                
                # Sync commands globally
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} commands globally")
                
                # List the command names
                command_names = [cmd.name for cmd in synced]
                logger.info(f"Synced commands: {', '.join(command_names)}")
                
                self.synced = True
                return True
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")
            return False

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Force resync Discord commands for a specific guild')
    parser.add_argument('guild_id', type=int, nargs='?', help='Discord guild ID to sync commands to')
    args = parser.parse_args()
    
    # Load environment variables
    # Try loading from the current directory first
    if os.path.exists('.env'):
        load_dotenv()
        logger.info("Loaded .env file from current directory")
    # If not found, try loading from DiscordBot directory
    elif os.path.exists('DiscordBot/.env'):
        load_dotenv('DiscordBot/.env')
        logger.info("Loaded .env file from DiscordBot directory")
    else:
        logger.warning("No .env file found, using existing environment variables")
    
    # Get token from environment
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN environment variable not found")
        return 1
    
    # Create and start the bot
    bot = ResyncBot()
    
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        await bot.close()
    except discord.LoginFailure:
        logger.error("Invalid Discord token")
        return 1
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return 1
    finally:
        # Check if we need to close the bot
        if bot.is_ready():
            await bot.close()
    
    return 0

if __name__ == '__main__':
    # Use asyncio.run for Python 3.7+
    # For older versions, use the event loop directly
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(0) 