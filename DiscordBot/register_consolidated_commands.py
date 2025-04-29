#!/usr/bin/env python3
"""
Command Registration Script for Consolidated Discord Bot Commands

This script registers the consolidated commands with the main Discord bot.
"""

import logging
import discord
from consolidated_commands import register_consolidated_commands

# Try different import strategies for utils
try:
    # Try direct import first
    from utils import safe_defer, safe_followup, format_embed_message
except ImportError:
    try:
        # Try relative import
        from .utils import safe_defer, safe_followup, format_embed_message
    except ImportError:
        # Try absolute import with full path
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from utils import safe_defer, safe_followup, format_embed_message

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("discord_bot.log")
    ]
)
logger = logging.getLogger('register_consolidated_commands')

def register_commands_with_bot(
    bot, 
    safe_defer, 
    safe_followup
):
    """
    Register consolidated commands with the Discord bot.
    
    Args:
        bot: The Discord bot instance
        safe_defer: Function for safely deferring interactions
        safe_followup: Function for safely following up on interactions
    
    Returns:
        dict: A mapping of command names to command functions
    """
    try:
        logger.info("Registering consolidated commands...")
        
        # Create a wrapper for safe_followup that supports the 'embed' parameter
        # This ensures compatibility with functions from admin_command.py
        async def safe_followup_wrapper(interaction, content=None, embed=None, ephemeral=False):
            if embed:
                return await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            else:
                return await interaction.followup.send(content=content, ephemeral=ephemeral)
        
        # Remove any existing commands with the same names to avoid conflicts
        consolidated_command_names = [
            "models", "chat", "server", "history", "help", "admin", "manage", "stats", "ping"
        ]
        
        # Check for existing commands and remove them
        for cmd_name in consolidated_command_names:
            existing_cmd = bot.tree.get_command(cmd_name)
            if existing_cmd:
                logger.info(f"Removing existing command: {cmd_name}")
                bot.tree.remove_command(cmd_name)
        
        # Register the consolidated commands using our wrapper
        commands = register_consolidated_commands(bot, safe_defer, safe_followup_wrapper)
        
        # Additionally, register the ping command separately since it's not part of the main consolidated set
        # but is still needed for basic functionality
        register_ping_command(bot, safe_defer, safe_followup_wrapper)
        
        # Log the registered commands
        logger.info(f"Registered commands: {', '.join(commands.keys())}")
        
        return commands
        
    except Exception as e:
        logger.error(f"Error registering consolidated commands: {e}")
        raise

# Add a function to register the ping command
def register_ping_command(bot, safe_defer, safe_followup):
    """Register the basic ping command"""
    try:
        @bot.tree.command(name="ping", description="Check if the bot is responding")
        async def ping_command(interaction: discord.Interaction):
            if not await safe_defer(interaction):
                return
            
            try:
                import time
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
        
        logger.info("Registered ping command")
        return ping_command
    except Exception as e:
        logger.error(f"Error registering ping command: {e}")
        raise

def apply_command_deprecation(bot):
    """
    Add deprecation notices to old commands that are replaced by consolidated commands.
    
    Args:
        bot: The Discord bot instance
    """
    try:
        logger.info("Adding deprecation notices to old commands...")
        
        # The list of commands that are now deprecated
        deprecated_commands = {
            "listmodels": "models",
            "searchmodels": "models",
            "modelsbyparam": "models",
            "allmodels": "models",
            "models_with_servers": "models",
            "find_model_endpoints": "models action:endpoints",
            
            "chat": "chat",
            "quickprompt": "chat",
            "interact": "chat",
            
            "listservers": "server action:list",
            "serverinfo": "server action:details",
            "checkserver": "server action:check",
            
            "list_models": "models"
        }
        
        # Add deprecation notices to commands
        for old_command, new_command in deprecated_commands.items():
            # Check if the command exists
            if not bot.tree.get_command(old_command):
                logger.warning(f"Command '{old_command}' not found, skipping deprecation notice")
                continue
                
            # Add deprecation notice
            old_cmd = bot.tree.get_command(old_command)
            old_description = old_cmd.description
            
            # Update description only if it doesn't already have a deprecation notice
            if not old_description.startswith("[DEPRECATED]"):
                old_cmd.description = f"[DEPRECATED] Use /{new_command} instead"
                logger.info(f"Added deprecation notice to '{old_command}'")
        
        logger.info("Finished adding deprecation notices")
        
    except Exception as e:
        logger.error(f"Error applying command deprecation: {e}")
        raise


if __name__ == "__main__":
    # This is just for testing - actual registration will happen in the main bot
    logger.info("This script should be imported by the main bot, not run directly.")
    logger.info("For testing, create a bot instance and call register_commands_with_bot()") 