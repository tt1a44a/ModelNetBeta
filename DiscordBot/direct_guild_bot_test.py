#!/usr/bin/env python3
"""
Test script to sync commands to a specific guild
"""

import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '936535618278809670'))

# Initialize Discord client with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Create guild object for command registration
MY_GUILD = discord.Object(id=GUILD_ID)

# Add a simple ping command
@bot.tree.command(
    name="ping_test", 
    description="Test command to verify permissions",
)
async def ping_command(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! Test successful!")

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user} (ID: {bot.user.id})")
    print(f"Target Guild ID: {GUILD_ID}")
    
    # First try syncing globally (might work)
    try:
        print("Attempting to sync commands globally first...")
        await bot.tree.sync()
        print("Global command sync successful!")
    except Exception as e:
        print(f"Global sync failed: {str(e)}")
    
    # Then try syncing to specific guild
    try:
        print(f"Syncing commands to guild {GUILD_ID}...")
        await bot.tree.sync(guild=MY_GUILD)
        print("Guild command sync complete!")
    except Exception as e:
        print(f"Error syncing commands to guild: {str(e)}")
        print("This could be due to:")
        print("1. Bot lacks 'applications.commands' scope in this guild")
        print("2. Bot lacks proper role permissions in the guild")
        print("3. Server has restrictions on who can add commands")
    
    print("Bot startup complete - keeping connection open...")

# Run the bot
print("Starting test bot...")
bot.run(TOKEN) 