#!/usr/bin/env python3
"""
Generate a proper Discord bot invite URL with all required permissions and scopes
"""

import os
from dotenv import load_dotenv

# Load environment variables
print("Loading environment variables...")
load_dotenv()

# Get client ID from environment
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
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

# Generate the invite URL
INVITE_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={CLIENT_ID}"
    f"&permissions={PERMISSION}"
    f"&scope={'%20'.join(SCOPES)}"
)

print("\nRegenerated Bot Invite URL with FULL PERMISSIONS:")
print("================================================")
print(INVITE_URL)
print("\nInstructions:")
print("1. Copy this URL and open it in your browser")
print("2. Select the server where you want to add the bot with FULL PERMISSIONS")
print("3. Make sure to authorize ALL the requested permissions")
print("4. If you're re-adding to an existing server, you may need to remove the bot first")
print("\nThis URL grants ADMINISTRATOR access to ensure all required permissions are available.") 