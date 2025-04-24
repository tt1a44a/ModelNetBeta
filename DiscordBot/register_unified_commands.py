#!/usr/bin/env python3
"""
Register Unified Commands

This script helps integrate the unified commands into the Discord bot
while maintaining backward compatibility.
"""

import discord
from discord import app_commands
import sqlite3
import logging
import os
import sys
from discord.ext import commands
import asyncio
from typing import Dict, List, Any, Optional

# Add path for local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DiscordBot.unified_commands import register_unified_commands

# Added by migration script
from database import Database, init_database

logger = logging.getLogger("discord_bot")

def setup_unified_commands(bot, DB_FILE, session, logger):
    """
    Set up unified commands in the Discord bot
    
    Args:
        bot: The Discord bot instance
        DB_FILE: Path to SQLite database
        session: aiohttp session
        logger: Logger instance
        
    Returns:
        dict: Mapping of original command names to unified commands
    """
    # Define helper functions that will be passed to register_unified_commands
    async def safe_defer(interaction):
        """Safely defer a Discord interaction"""
        try:
            await interaction.response.defer(thinking=True)
            return True
        except Exception as e:
            logger.error(f"Error deferring interaction: {str(e)}")
            try:
                await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)
            except:
                pass
            return False
            
    async def safe_followup(interaction, content, **kwargs):
        """Safely follow up on a Discord interaction"""
        try:
            await interaction.followup.send(content, **kwargs)
            return True
        except Exception as e:
            logger.error(f"Error following up interaction: {str(e)}")
            try:
                # Try to send as a new message if followup fails
                await interaction.channel.send(f"Error sending response: {str(e)}\n\nOriginal content was too long or failed to send.")
            except:
                pass
            return False
    
    # Implement server connectivity check
    async def check_server_connectivity(ip, port):
        """Check if an Ollama server is reachable"""
        try:
            async with session.get(f"http://{ip}:{port}/api/tags", timeout=5) as response:
                if response.status == 200:
                    return True, None
                else:
                    return False, f"HTTP {response.status}"
        except Exception as e:
            return False, str(e)
    
    # Function to sync models with server
    def sync_models_with_server(ip, port):
        """
        Sync models with a server
        
        Args:
            ip: Server IP
            port: Server port
            
        Returns:
            tuple: (added_models, updated_models, removed_models)
        """
        # Simplified placeholder for actual implementation
        # Real implementation would call to your existing code
        return ([], [], [])
        
    # Function to get servers
    def get_servers():
        """Get all servers from the database"""
        try:
            conn = Database()
            # Using Database methods instead of cursor
            
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
    
    # Register the unified commands
    unified_commands = register_unified_commands(
        bot, 
        DB_FILE, 
        safe_defer, 
        safe_followup, 
        session, 
        check_server_connectivity, 
        logger,
        sync_models_with_server,
        get_servers
    )
    
    # Create a mapping of original command names to unified commands
    command_mapping = {
        # Search commands
        "searchmodels": "unified_search",
        "modelsbyparam": "unified_search",
        "allmodels": "unified_search",
        "models_with_servers": "unified_search",
        
        # Server commands
        "listservers": "server",
        "checkserver": "server",
        "syncserver": "server",
        "serverinfo": "server",
        "verifyall": "server",
        "purgeunreachable": "server",
        
        # Admin commands
        "refreshcommands": "admin",
        "guild_sync": "admin",
        "refreshcommandsv2": "admin",
        "cleanup": "admin",
        "updateallmodels": "admin",
        
        # Model commands
        "listmodels": "model",
        "selectmodel": "model",
        "addmodel": "model",
        "deletemodel": "model",
        
        # Chat commands
        "interact": "chat",
        "quickprompt": "chat",
        "benchmark": "chat"
    }
    
    return unified_commands, command_mapping

def create_usage_guide():
    """
    Create a guide for using the new unified commands
    
    Returns:
        str: Markdown-formatted usage guide
    """
    guide = """
# Unified Commands Usage Guide

The bot now features a streamlined command system with unified commands that replace multiple specific commands.

## Search Command
`/unified_search`
- Replaces: searchmodels, modelsbyparam, allmodels, models_with_servers
- Options:
  - search_type: "name", "params", "all", "with_servers"
  - query: search term (for name/params search)
  - sort_by, descending, limit: sorting options
  - show_endpoints: show server details for each model

## Server Command
`/server`
- Replaces: listservers, checkserver, syncserver, serverinfo, verifyall, purgeunreachable
- Options:
  - action: "list", "check", "sync", "info", "verify", "purge"
  - ip, port: server coordinates (when needed)
  - sort_by, descending, limit: sorting options

## Admin Command
`/admin`
- Replaces: refreshcommands, guild_sync, refreshcommandsv2, cleanup, updateallmodels
- Options:
  - action: "refresh", "guild_sync", "full_refresh", "cleanup", "update_models"
  - scope: "global" or "guild"

## Model Command
`/model`
- Replaces: listmodels, selectmodel, addmodel, deletemodel
- Options:
  - action: "list", "select", "add", "delete"
  - model_id: for select/delete actions
  - ip, port, model_name, info: for add action

## Chat Command
`/chat`
- Replaces: interact, quickprompt, benchmark
- Options:
  - action: "interact", "quick", "benchmark"
  - model_id: for direct interaction
  - search_term: for quick interaction
  - prompt, system_prompt, temperature, max_tokens, param_size: interaction settings

Legacy commands will continue to work but are deprecated and may be removed in future.
"""
    return guide

async def register_commands(bot: commands.Bot, guild_ids: Optional[List[int]] = None) -> None:
    """Register all unified commands with Discord.
    
    Args:
        bot: The Discord bot instance
        guild_ids: Optional list of guild IDs to register commands to. If None, registers globally.
    """
    try:
        logger.info("Registering unified commands...")
        
        if guild_ids:
            for guild_id in guild_ids:
                guild = discord.Object(id=guild_id)
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
                logger.info(f"Synchronized commands to guild {guild_id}")
        else:
            await bot.tree.sync()
            logger.info("Synchronized commands globally")
            
        logger.info("Unified command registration complete")
    except Exception as e:
        logger.error(f"Error registering unified commands: {e}")

class LegacyCommandMapping:
    """Maps legacy commands to their unified counterparts."""
    
    @staticmethod
    def get_legacy_to_unified_map() -> Dict[str, Dict[str, Any]]:
        """Returns a mapping of legacy commands to their unified counterparts.
        
        Returns:
            Dict[str, Dict[str, Any]]: Mapping of legacy commands to their unified counterparts
        """
        return {
            # Search-related commands
            "listmodels": {
                "unified_command": "unified_search",
                "params": {"action": "list_all"}
            },
            "searchmodels": {
                "unified_command": "unified_search",
                "params": {"action": "by_name"}
            },
            "modelsbyparam": {
                "unified_command": "unified_search",
                "params": {"action": "by_parameter"}
            },
            "allmodels": {
                "unified_command": "unified_search",
                "params": {"action": "list_all"}
            },
            "models_with_servers": {
                "unified_command": "unified_search",
                "params": {"action": "with_servers"}
            },
            
            # Server-related commands
            "listservers": {
                "unified_command": "server",
                "params": {"action": "list"}
            },
            "checkserver": {
                "unified_command": "server",
                "params": {"action": "check"}
            },
            "syncserver": {
                "unified_command": "server",
                "params": {"action": "sync"}
            },
            "serverinfo": {
                "unified_command": "server",
                "params": {"action": "info"}
            },
            
            # Model management commands
            "selectmodel": {
                "unified_command": "model",
                "params": {"action": "select"}
            },
            "addmodel": {
                "unified_command": "model",
                "params": {"action": "add"}
            },
            "deletemodel": {
                "unified_command": "model",
                "params": {"action": "delete"}
            },
            
            # Admin commands
            "refreshcommands": {
                "unified_command": "admin",
                "params": {"action": "refresh_commands"}
            },
            "refreshcommandsv2": {
                "unified_command": "admin",
                "params": {"action": "full_refresh"}
            },
            "guild_sync": {
                "unified_command": "admin",
                "params": {"action": "guild_sync"}
            },
            "cleanup": {
                "unified_command": "admin",
                "params": {"action": "cleanup"}
            },
            "updateallmodels": {
                "unified_command": "admin",
                "params": {"action": "update_all_models"}
            },
            
            # Interaction commands
            "interact": {
                "unified_command": "chat",
                "params": {"action": "interact"}
            },
            "quickprompt": {
                "unified_command": "chat",
                "params": {"action": "quick"}
            },
            "benchmark": {
                "unified_command": "chat",
                "params": {"action": "benchmark"}
            }
        }

class LegacyCommandHandler(commands.Cog):
    """Handles legacy commands and maps them to the unified command system."""
    
    def __init__(self, bot: commands.Bot):
        """Initialize the LegacyCommandHandler cog.
        
        Args:
            bot: The Discord bot instance
        """
        self.bot = bot
        self.command_map = LegacyCommandMapping.get_legacy_to_unified_map()
        
    async def handle_legacy_command(self, interaction: discord.Interaction, legacy_command: str, **kwargs) -> None:
        """Handle a legacy command by mapping it to its unified counterpart.
        
        Args:
            interaction: The Discord interaction
            legacy_command: The legacy command name
            **kwargs: Additional parameters for the command
        """
        if legacy_command not in self.command_map:
            await interaction.response.send_message(
                f"This command has been deprecated and has no unified equivalent.",
                ephemeral=True
            )
            return
            
        mapping = self.command_map[legacy_command]
        unified_command = mapping["unified_command"]
        
        # Combine default params from the mapping with any provided kwargs
        params = {**mapping.get("params", {}), **kwargs}
        
        await interaction.response.send_message(
            f"This command is now part of the unified command system. Please use `/{unified_command}` instead.",
            ephemeral=True
        )
        
        # Log the command usage for tracking adoption
        logger.info(f"Legacy command '{legacy_command}' used. Mapped to '{unified_command}' with params {params}")

def setup_legacy_commands(bot: commands.Bot) -> None:
    """Setup legacy command handling.
    
    Args:
        bot: The Discord bot instance
    """
    logger.info("Setting up legacy command handling...")
    
    # Add the LegacyCommandHandler cog
    bot.add_cog(LegacyCommandHandler(bot))
    
    # Dynamically create app_commands for all legacy commands
    command_map = LegacyCommandMapping.get_legacy_to_unified_map()
    
    for legacy_command, mapping in command_map.items():
        # Create a function that will handle this specific legacy command
        async def legacy_command_handler(interaction: discord.Interaction, **kwargs):
            legacy_handler = bot.get_cog("LegacyCommandHandler")
            if legacy_handler:
                await legacy_handler.handle_legacy_command(
                    interaction,
                    legacy_command=legacy_command,
                    **kwargs
                )
            else:
                await interaction.response.send_message(
                    "Legacy command handler not available. Please use the unified command system.",
                    ephemeral=True
                )
        
        # Create the app_command
        command = app_commands.Command(
            name=legacy_command,
            description=f"Legacy command, now part of /{mapping['unified_command']}",
            callback=legacy_command_handler,
        )
        
        # Add the command to the bot's command tree
        bot.tree.add_command(command)
    
    logger.info(f"Set up {len(command_map)} legacy commands with mappings to unified commands")

async def setup_unified_command_system(bot: commands.Bot, guild_ids: Optional[List[int]] = None) -> None:
    """Main function to setup the unified command system.
    
    Args:
        bot: The Discord bot instance
        guild_ids: Optional list of guild IDs to register commands to. If None, registers globally.
    """
    try:
        # 1. Load the unified commands cog
        bot.load_extension("unified_commands")
        logger.info("Loaded unified_commands extension")
        
        # 2. Setup legacy command handling
        setup_legacy_commands(bot)
        
        # 3. Register commands with Discord
        await register_commands(bot, guild_ids)
        
        logger.info("Unified command system setup complete")
    except Exception as e:
        logger.error(f"Error setting up unified command system: {e}")

if __name__ == "__main__":
    print("This file should be imported from discord_bot.py") 