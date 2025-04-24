#!/usr/bin/env python3
"""
Script to add the verbose flag to the chat command
"""

import os
import sys
import discord
from discord import app_commands
import asyncio
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("add_verbose_flag")

# Load environment variables
load_dotenv()

# Constants
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    logger.error("No Discord bot token found. Set the DISCORD_BOT_TOKEN environment variable.")
    sys.exit(1)

# Define a bot class
class UpdateBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_id = None  # Will be set from command line

    async def setup_hook(self):
        # Define the updated chat command with verbose flag
        @self.tree.command(
            name="chat",
            description="Chat with your selected model"
        )
        @app_commands.describe(
            prompt="Your message to the model",
            system_prompt="Optional system prompt to set context",
            temperature="Controls randomness (0.0 to 1.0)",
            max_tokens="Maximum number of tokens in response",
            model_id="Optional: Specific model ID to use instead of your default model",
            verbose="Show the raw API request and response"
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
            await interaction.response.send_message("Command updated with verbose flag. This is just a placeholder.")

        # Also add a resync command
        @self.tree.command(
            name="resync",
            description="Force resync of all commands"
        )
        async def resync(interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("You need admin permissions to use this command")
                return
                
            await interaction.response.defer(ephemeral=True)
            try:
                # Sync to the current guild
                if self.guild_id:
                    await self.tree.sync(guild=discord.Object(id=self.guild_id))
                    await interaction.followup.send("Commands synced to this server!")
                else:
                    # Global sync
                    await self.tree.sync()
                    await interaction.followup.send("Commands synced globally!")
            except Exception as e:
                await interaction.followup.send(f"Error: {str(e)}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
        
        try:
            # Sync commands to the specified guild
            if self.guild_id:
                await self.tree.sync(guild=discord.Object(id=self.guild_id))
                logger.info(f"Commands synced to guild ID: {self.guild_id}")
            else:
                # Global sync
                await self.tree.sync()
                logger.info("Commands synced globally")
            
            # Log success
            logger.info("Command definitions updated successfully!")
            logger.info("You may now restart your regular bot.")
            
            # Exit after syncing
            await self.close()
            
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")
            await self.close()

async def main():
    # Parse guild ID from command line if provided
    guild_id = None
    if len(sys.argv) > 1:
        try:
            guild_id = int(sys.argv[1])
            logger.info(f"Using guild ID: {guild_id}")
        except ValueError:
            logger.error("Invalid guild ID provided. Please provide a valid guild ID as a command-line argument.")
            sys.exit(1)
    else:
        logger.info("No guild ID provided. Commands will be synced globally.")
    
    # Create and run the bot
    bot = UpdateBot()
    bot.guild_id = guild_id
    
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        await bot.close()
    finally:
        logger.info("Bot shutting down")

if __name__ == "__main__":
    asyncio.run(main()) 