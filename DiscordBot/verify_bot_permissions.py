#!/usr/bin/env python3
"""
Verify Bot Permissions

This script checks whether the bot has the required permissions in Discord
and provides instructions for fixing any issues.
"""

import os
import sys
import discord
import asyncio
from dotenv import load_dotenv
import logging
import argparse
import requests
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('permission_check')

# Load environment variables
load_dotenv()

# Discord API endpoints
DISCORD_API = "https://discord.com/api/v10"

def get_token_and_client_id():
    """Get the bot token and client ID from environment variables"""
    token = os.getenv('DISCORD_TOKEN')
    client_id = os.getenv('DISCORD_CLIENT_ID')
    
    # Try to extract client ID from token if not set
    if token and not client_id:
        try:
            import base64
            token_parts = token.split('.')
            if len(token_parts) >= 1:
                # Add padding if needed
                first_part = token_parts[0]
                padding = '=' * (4 - len(first_part) % 4)
                
                # Decode the first part
                try:
                    decoded = base64.b64decode(first_part + padding).decode('utf-8')
                    client_id = decoded
                    logger.info(f"Extracted client ID from token: {client_id}")
                except:
                    logger.warning("Failed to extract client ID from token")
        except:
            pass
    
    return token, client_id

def generate_invite_url(client_id, guild_id=None):
    """Generate bot invite URL with admin permissions"""
    base_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands"
    if guild_id:
        return f"{base_url}&guild_id={guild_id}"
    return base_url

async def check_bot_permissions(guild_id=None):
    """Check if the bot has proper permissions in the specified guild"""
    token, client_id = get_token_and_client_id()
    
    if not token:
        logger.error("DISCORD_TOKEN not found in environment variables.")
        return False
        
    if not client_id:
        logger.warning("DISCORD_CLIENT_ID not found and couldn't be extracted from token.")
        
    # Initialize Discord client
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    permission_check_result = {"has_permissions": False, "error": None, "guilds": []}
    
    @client.event
    async def on_ready():
        """Handle bot ready event"""
        logger.info(f"Bot connected as {client.user} (ID: {client.user.id})")
        
        try:
            # If no specific guild ID is provided, check all guilds
            guilds_to_check = []
            if guild_id:
                guild = client.get_guild(int(guild_id))
                if guild:
                    guilds_to_check.append(guild)
                else:
                    permission_check_result["error"] = f"Bot is not in guild with ID {guild_id}"
            else:
                guilds_to_check = client.guilds
            
            permission_check_result["guilds"] = []
            
            for guild in guilds_to_check:
                # Get bot's permissions in the guild
                bot_member = guild.get_member(client.user.id)
                if not bot_member:
                    logger.error(f"Bot is not a member of guild: {guild.name} (ID: {guild.id})")
                    permission_check_result["guilds"].append({
                        "id": str(guild.id),
                        "name": guild.name,
                        "has_permissions": False,
                        "error": "Bot is not a member of this guild"
                    })
                    continue
                
                # Check for administrator permission
                has_admin = bot_member.guild_permissions.administrator
                
                # Check for manage_guild permission (minimum for registering commands)
                has_manage_guild = bot_member.guild_permissions.manage_guild
                
                guild_result = {
                    "id": str(guild.id),
                    "name": guild.name,
                    "has_permissions": has_admin,
                    "administrator": has_admin,
                    "manage_guild": has_manage_guild
                }
                permission_check_result["guilds"].append(guild_result)
                
                if has_admin:
                    logger.info(f"Bot has administrator permissions in guild: {guild.name} (ID: {guild.id})")
                else:
                    logger.warning(f"Bot does NOT have administrator permissions in guild: {guild.name} (ID: {guild.id})")
            
            # Set overall status based on all guilds
            if permission_check_result["guilds"]:
                permission_check_result["has_permissions"] = any(g["has_permissions"] for g in permission_check_result["guilds"])
            
        except Exception as e:
            logger.error(f"Error checking permissions: {e}")
            permission_check_result["error"] = str(e)
        finally:
            # Close the client connection
            await client.close()
    
    try:
        # Start the client
        await client.start(token)
    except discord.errors.LoginFailure:
        logger.error("Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
        permission_check_result["error"] = "Invalid Discord token"
    except Exception as e:
        logger.error(f"Error connecting to Discord: {e}")
        permission_check_result["error"] = str(e)
    
    return permission_check_result

def print_permissions_report(result, guild_id=None):
    """Print a report of the bot's permissions"""
    print("\n" + "="*60)
    print("             DISCORD BOT PERMISSIONS REPORT")
    print("="*60 + "\n")
    
    if result.get("error"):
        print(f"ERROR: {result['error']}\n")
        return
    
    # Print overall status
    if result.get("has_permissions", False):
        print("✅ Bot has administrator permissions in at least one guild.\n")
    else:
        print("❌ Bot does NOT have administrator permissions in any guild.\n")
    
    # Print guild-specific information
    print("Guild Permissions:")
    print("-----------------")
    for guild in result.get("guilds", []):
        guild_name = guild.get("name", "Unknown")
        guild_id = guild.get("id", "Unknown")
        
        status = "✅" if guild.get("has_permissions", False) else "❌"
        print(f"{status} Guild: {guild_name} (ID: {guild_id})")
        
        if "administrator" in guild:
            admin_status = "✅" if guild["administrator"] else "❌"
            print(f"   {admin_status} Administrator permission")
        
        if "manage_guild" in guild:
            manage_status = "✅" if guild["manage_guild"] else "❌"
            print(f"   {manage_status} Manage Guild permission")
        
        print("")
    
    # Print instructions for fixing permissions
    if not result.get("has_permissions", False):
        _, client_id = get_token_and_client_id()
        if client_id:
            invite_url = generate_invite_url(client_id, guild_id)
            
            print("INSTRUCTIONS TO FIX PERMISSIONS:")
            print("--------------------------------")
            print("1. Remove the bot from your server (Server Settings > Integrations)")
            print("2. Reinvite the bot using this URL (with administrator permissions):")
            print(f"   {invite_url}\n")
            print("3. Make sure to check all permission boxes when authorizing")
            print("4. Run the guild_unified_commands.py script again after reinviting\n")
        else:
            print("INSTRUCTIONS TO FIX PERMISSIONS:")
            print("--------------------------------")
            print("1. Run the fix_permissions.py script to generate a proper invite URL")
            print("2. Remove the bot from your server and reinvite it using the generated URL")
            print("3. Run the guild_unified_commands.py script again after reinviting\n")
    
    print("="*60)

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Verify Discord bot permissions")
    parser.add_argument("--guild-id", help="Specific guild ID to check")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    guild_id = args.guild_id or os.getenv('DISCORD_GUILD_ID')
    
    # Check bot permissions
    result = await check_bot_permissions(guild_id)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_permissions_report(result, guild_id)
    
    # Return success if permissions are OK, otherwise error
    return 0 if result.get("has_permissions", False) else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1) 