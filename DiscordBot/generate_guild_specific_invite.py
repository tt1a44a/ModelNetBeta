#!/usr/bin/env python3
"""
Generate a guild-specific Discord bot invite URL with all required permissions and scopes
"""

import os
from dotenv import load_dotenv

# Load environment variables
print("Loading environment variables...")
load_dotenv()

# Get client ID and guild ID from environment
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
GUILD_ID = os.getenv('DISCORD_GUILD_ID', '936535618278809670')  # Wackyjacky's server

if not CLIENT_ID:
    print("ERROR: DISCORD_CLIENT_ID not found in environment variables.")
    print("Make sure to add it to your .env file.")
    exit(1)

# Define the scopes needed (these are crucial)
SCOPES = [
    "bot",                    # Basic bot functionality
    "applications.commands"   # Ability to register slash commands
]

# Define the permissions (using Administrator to ensure all permissions)
# Administrator permission value = 8
PERMISSION = 8

# Generate the guild-specific invite URL
INVITE_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={CLIENT_ID}"
    f"&permissions={PERMISSION}"
    f"&guild_id={GUILD_ID}"
    f"&disable_guild_select=true"
    f"&scope={'%20'.join(SCOPES)}"
    f"&response_type=code"
    f"&redirect_uri=http%3A%2F%2Flocalhost%3A4466%2Fcallback"
)

print("\nGUILD-SPECIFIC Bot Invite URL with FULL PERMISSIONS:")
print("====================================================")
print(INVITE_URL)
print("\nInstructions:")
print(f"1. First REMOVE the bot from guild {GUILD_ID} (Wackyjacky's server)")
print("2. Make sure your OAuth server is running: python oauth_server.py")
print("3. Copy this URL and open it in your browser")
print("4. It will automatically select the specific server")
print("5. Make sure to authorize ALL permissions")
print("\nThis URL grants ADMINISTRATOR access and forces authorization for the specific guild.") 