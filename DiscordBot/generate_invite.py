#!/usr/bin/env python3
"""
Generate Discord bot invite URL with correct permissions
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
print("Loading environment variables...")
load_dotenv()

# Get client ID from environment
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')  # Not used in URL, just for validation
REDIRECT_URI = 'http://localhost:4466/callback'

# Validate environment variables
if not CLIENT_ID:
    print("ERROR: DISCORD_CLIENT_ID not found in environment variables.")
    print("Make sure to add it to your .env file.")
    sys.exit(1)

if not CLIENT_SECRET:
    print("WARNING: DISCORD_CLIENT_SECRET not found in environment variables.")
    print("This is needed for the OAuth2 callback server.")
    print("Make sure to add it to your .env file before using the invite URL.")

print(f"Using Client ID: {CLIENT_ID[:5]}... (length: {len(CLIENT_ID)})")
if CLIENT_SECRET:
    print(f"Client Secret loaded: {CLIENT_SECRET[:5]}... (length: {len(CLIENT_SECRET)})")

# Permissions needed for the bot
PERMISSIONS = [
    '2048',  # View Channels
    '4096',  # Send Messages
    '8192',  # Read Message History
    '16384', # Use Slash Commands
]

# Calculate the total permission integer
PERMISSION_INTEGER = sum(int(p) for p in PERMISSIONS)
print(f"Permission integer: {PERMISSION_INTEGER}")

# Generate the invite URL
INVITE_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_type=code"
    f"&scope=bot%20applications.commands"
    f"&permissions={PERMISSION_INTEGER}"
)

print("\nDiscord Bot Invite URL:")
print("=======================")
print(INVITE_URL)
print("\nInstructions:")
print("1. Copy this URL and open it in your browser")
print("2. Select the server where you want to add the bot")
print("3. Complete the authorization process")
print("4. The bot will be added to your server with the correct permissions")
print("\nNote: Make sure the OAuth2 callback server is running when you use this URL")
print("      Start it with: python oauth_server.py") 