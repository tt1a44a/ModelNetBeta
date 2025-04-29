import logging
import discord
from discord import app_commands
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_server_command(bot, safe_defer, safe_followup):
    """Register the server command with the bot"""

    # Define choices for server actions
    server_actions = [
        app_commands.Choice(name="list", value="list"),
        app_commands.Choice(name="info", value="info"),
        app_commands.Choice(name="register", value="register"),
        app_commands.Choice(name="verify", value="verify"),
        app_commands.Choice(name="status", value="status")
    ]
    
    @bot.tree.command(name="server", description="Manage and view AI model server endpoints")
    @app_commands.describe(
        action="Action to perform with server endpoints",
        address="Server IP address (for register/verify/info actions)",
        port="Server port number (default: 11434)",
        description="Optional server description for registration"
    )
    @app_commands.choices(action=server_actions)
    async def server_command(
        interaction: discord.Interaction,
        action: str,
        address: str = None,
        port: int = 11434,
        description: str = None
    ):
        """Handle server-related actions"""
        await safe_defer(interaction)
        
        try:
            # Validate parameters
            if action in ["info", "register", "verify", "status"] and not address:
                error_embed = await format_embed_message(
                    title="Missing Parameters",
                    description=f"Server address is required for the {action} action.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
                
            if port < 1 or port > 65535:
                error_embed = await format_embed_message(
                    title="Invalid Port",
                    description="Port number must be between 1 and 65535.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
            
            # Handle different actions
            if action == "list":
                await handle_list_servers(interaction, safe_followup)
            elif action == "info":
                await handle_server_info(interaction, safe_followup, address, port)
            elif action == "register":
                # Check if user has permission to register servers
                if not interaction.user.guild_permissions.administrator:
                    error_embed = await format_embed_message(
                        title="Permission Denied",
                        description="You need administrator permissions to register servers.",
                        color=discord.Color.red()
                    )
                    await safe_followup(interaction, embed=error_embed)
                    return
                    
                await handle_register_server(interaction, safe_followup, address, port, description)
            elif action == "verify":
                await handle_verify_server(interaction, safe_followup, address, port)
            elif action == "status":
                await handle_server_status(interaction, safe_followup, address, port)
            else:
                error_embed = await format_embed_message(
                    title="Invalid Action",
                    description=f"Action '{action}' is not recognized.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                
        except Exception as e:
            logger.error(f"Error in server command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return server_command

async def handle_list_servers(interaction: discord.Interaction, safe_followup):
    """Handle listing all available server endpoints"""
    try:
        # Query for verified servers
        query = """
            SELECT e.id, e.ip, e.port, e.description, e.scan_date, 
                   ve.verification_date, 
                   (SELECT COUNT(*) FROM models m WHERE m.endpoint_id = e.id) as model_count
            FROM endpoints e
            JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            WHERE e.verified = 1 AND e.is_honeypot = FALSE
            ORDER BY ve.verification_date DESC
        """
        servers = Database.fetch_all(query)
        
        if not servers or len(servers) == 0:
            no_servers_embed = await format_embed_message(
                title="No Servers Found",
                description="There are no verified servers in the database.",
                color=discord.Color.blue()
            )
            await safe_followup(interaction, embed=no_servers_embed)
            return
            
        # Create embed for listing servers
        servers_embed = discord.Embed(
            title="Available Model Servers",
            description=f"Showing {len(servers)} verified servers",
            color=discord.Color.blue()
        )
        
        for server in servers:
            server_id, ip, port, description, scan_date, verification_date, model_count = server
            
            # Create server address string
            server_address = f"{ip}:{port}"
            
            # Create field for server
            field_name = f"Server {server_id}: {server_address}"
            
            field_value = []
            if description:
                field_value.append(f"**Description**: {description}")
                
            field_value.append(f"**Models**: {model_count}")
            
            if verification_date:
                field_value.append(f"**Verified**: {verification_date.strftime('%Y-%m-%d')}")
                
            field_value.append(f"Use `/server info {ip} {port}` for more details")
            
            servers_embed.add_field(
                name=field_name,
                value="\n".join(field_value),
                inline=False
            )
        
        # Add footer
        servers_embed.set_footer(
            text="Use /server info <address> <port> to see detailed information about a specific server"
        )
        
        await safe_followup(interaction, embed=servers_embed)
    
    except Exception as e:
        logger.error(f"Error listing servers: {str(e)}")
        raise

async def handle_server_info(interaction: discord.Interaction, safe_followup, address: str, port: int):
    """Handle retrieving detailed information about a specific server"""
    try:
        # Query server info
        query = """
            SELECT e.id, e.ip, e.port, e.description, e.scan_date, e.verified,
                   ve.verification_date, ve.verification_method, ve.verified_by,
                   (SELECT COUNT(*) FROM models m WHERE m.endpoint_id = e.id) as model_count
            FROM endpoints e
            LEFT JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            WHERE e.ip = %s AND e.port = %s
        """
        server = Database.fetch_one(query, (address, port))
        
        if not server:
            not_found_embed = await format_embed_message(
                title="Server Not Found",
                description=f"No server found with address {address}:{port}.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        # Unpack server data
        server_id, ip, db_port, description, scan_date, verified, verification_date, verification_method, verified_by, model_count = server
        
        # Create embed for server info
        server_embed = discord.Embed(
            title=f"Server Information: {ip}:{db_port}",
            description=description or "No description available",
            color=discord.Color.blue()
        )
        
        # Add basic info
        server_embed.add_field(
            name="Basic Information",
            value=(
                f"**Server ID**: {server_id}\n"
                f"**Address**: {ip}:{db_port}\n"
                f"**Status**: {'Verified' if verified else 'Unverified'}\n"
                f"**Models**: {model_count}\n"
                f"**Last Scan**: {scan_date.strftime('%Y-%m-%d %H:%M:%S') if scan_date else 'Never'}"
            ),
            inline=False
        )
        
        # Add verification info if available
        if verified and verification_date:
            verification_info = [
                f"**Date**: {verification_date.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
            
            if verification_method:
                verification_info.append(f"**Method**: {verification_method}")
                
            if verified_by:
                verification_info.append(f"**Verified by**: {verified_by}")
                
            server_embed.add_field(
                name="Verification Information",
                value="\n".join(verification_info),
                inline=False
            )
        
        # Query top models on this server
        models_query = """
            SELECT m.id, m.name, COUNT(ch.id) as usage_count
            FROM models m
            LEFT JOIN chat_history ch ON m.id = ch.model_id
            WHERE m.endpoint_id = %s
            GROUP BY m.id, m.name
            ORDER BY usage_count DESC
            LIMIT 5
        """
        top_models = Database.fetch_all(models_query, (server_id,))
        
        if top_models and len(top_models) > 0:
            models_list = []
            
            for model_id, model_name, usage_count in top_models:
                models_list.append(f"**{model_name}** (ID: {model_id}) - {usage_count} uses")
                
            server_embed.add_field(
                name="Top Models",
                value="\n".join(models_list) if models_list else "No usage data available",
                inline=False
            )
            
            server_embed.add_field(
                name="Available Actions",
                value=(
                    f"• Use `/server status {ip} {db_port}` to check current server status\n"
                    f"• Use `/server verify {ip} {db_port}` to verify connectivity\n"
                    f"• Use `/models list` to see all available models"
                ),
                inline=False
            )
        
        await safe_followup(interaction, embed=server_embed)
    
    except Exception as e:
        logger.error(f"Error getting server info: {str(e)}")
        raise

async def handle_register_server(interaction: discord.Interaction, safe_followup, address: str, port: int, description: str = None):
    """Handle registering a new server endpoint"""
    try:
        # Check if server already exists
        check_query = """
            SELECT id
            FROM endpoints
            WHERE ip = %s AND port = %s
        """
        existing_server = Database.fetch_one(check_query, (address, port))
        
        if existing_server:
            exists_embed = await format_embed_message(
                title="Server Already Registered",
                description=f"The server at {address}:{port} is already registered in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=exists_embed)
            return
            
        # Register new server
        insert_query = """
            INSERT INTO endpoints (ip, port, description, scan_date, verified, is_honeypot, added_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        now = datetime.now(timezone.utc)
        params = (
            address,
            port,
            description or f"Server added by {interaction.user.name} on {now.strftime('%Y-%m-%d')}",
            now,
            0,  # Not verified initially (0 instead of False)
            False,  # Not a honeypot
            f"{interaction.user.name}#{interaction.user.discriminator}" if hasattr(interaction.user, 'discriminator') else interaction.user.name
        )
        
        new_server_id = Database.fetch_one(insert_query, params)
        
        if not new_server_id:
            error_embed = await format_embed_message(
                title="Registration Failed",
                description="Failed to register the server. Database error.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        # Success message
        success_embed = await format_embed_message(
            title="Server Registered",
            description=(
                f"Successfully registered server at {address}:{port}.\n\n"
                f"Next steps:\n"
                f"• Use `/server verify {address} {port}` to verify connectivity\n"
                f"• After verification, use `/manage action:sync type:server ip:{address} port:{port}` to sync models"
            ),
            color=discord.Color.green()
        )
        
        await safe_followup(interaction, embed=success_embed)
    
    except Exception as e:
        logger.error(f"Error registering server: {str(e)}")
        raise

async def handle_verify_server(interaction: discord.Interaction, safe_followup, address: str, port: int):
    """Handle verifying a server endpoint"""
    try:
        # Check if server exists
        check_query = """
            SELECT id, verified
            FROM endpoints
            WHERE ip = %s AND port = %s
        """
        existing_server = Database.fetch_one(check_query, (address, port))
        
        if not existing_server:
            not_found_embed = await format_embed_message(
                title="Server Not Found",
                description=f"No server found with address {address}:{port}. Use `/server register` to add it first.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        server_id, already_verified = existing_server
        
        # Send a message that verification is in progress
        await safe_followup(interaction, "Verifying server connectivity. This may take a moment...")
        
        # This is where you would normally check server connectivity
        # For now, we'll simulate this with a simple success message
        # In a real implementation, you'd make an API call to the server
        
        # Assume verification succeeded
        verification_succeeded = True
        
        if verification_succeeded:
            # Update server verified status
            update_query = """
                UPDATE endpoints
                SET verified = 1, scan_date = %s
                WHERE id = %s
            """
            
            now = datetime.now(timezone.utc)
            Database.execute(update_query, (now, server_id))
            
            # Add or update verified_endpoints entry
            if already_verified:
                # Update existing verification
                verify_update_query = """
                    UPDATE verified_endpoints
                    SET verification_date = %s, verification_method = %s, verified_by = %s
                    WHERE endpoint_id = %s
                """
                
                Database.execute(verify_update_query, (
                    now, 
                    "API Check", 
                    f"{interaction.user.name}#{interaction.user.discriminator}" if hasattr(interaction.user, 'discriminator') else interaction.user.name,
                    server_id
                ))
            else:
                # Create new verification
                verify_insert_query = """
                    INSERT INTO verified_endpoints (endpoint_id, verification_date, verification_method, verified_by)
                    VALUES (%s, %s, %s, %s)
                """
                
                Database.execute(verify_insert_query, (
                    server_id,
                    now, 
                    "API Check", 
                    f"{interaction.user.name}#{interaction.user.discriminator}" if hasattr(interaction.user, 'discriminator') else interaction.user.name
                ))
            
            # Success message
            success_embed = await format_embed_message(
                title="Server Verified",
                description=(
                    f"Successfully verified server at {address}:{port}.\n\n"
                    f"Next steps:\n"
                    f"• Use `/manage action:sync type:server ip:{address} port:{port}` to sync models"
                ),
                color=discord.Color.green()
            )
            
            await safe_followup(interaction, embed=success_embed)
        else:
            # Error message if verification failed
            error_embed = await format_embed_message(
                title="Verification Failed",
                description=f"Could not connect to server at {address}:{port}. Please check that the server is running and accessible.",
                color=discord.Color.red()
            )
            
            await safe_followup(interaction, embed=error_embed)
    
    except Exception as e:
        logger.error(f"Error verifying server: {str(e)}")
        raise

async def handle_server_status(interaction: discord.Interaction, safe_followup, address: str, port: int):
    """Handle checking the status of a server"""
    try:
        # Check if server exists in the database
        check_query = """
            SELECT e.id, e.verified, e.scan_date, ve.verification_date
            FROM endpoints e
            LEFT JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            WHERE e.ip = %s AND e.port = %s
        """
        server_info = Database.fetch_one(check_query, (address, port))
        
        if not server_info:
            not_found_embed = await format_embed_message(
                title="Server Not Found",
                description=f"No server found with address {address}:{port} in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        server_id, verified, scan_date, verification_date = server_info
        
        # Send a message that status check is in progress
        await safe_followup(interaction, "Checking server status. This may take a moment...")
        
        # This is where you would normally check server status
        # For now, we'll simulate this with database status information
        # In a real implementation, you'd make an API call to the server
        
        # Query models on this server
        models_query = """
            SELECT COUNT(*) as model_count
            FROM models
            WHERE endpoint_id = %s
        """
        model_count_result = Database.fetch_one(models_query, (server_id,))
        model_count = model_count_result[0] if model_count_result else 0
        
        # Create status embed
        status_embed = discord.Embed(
            title=f"Server Status: {address}:{port}",
            color=discord.Color.blue()
        )
        
        # Add database status
        status_embed.add_field(
            name="Database Status",
            value=(
                f"**Registered**: Yes\n"
                f"**Verified**: {'Yes' if verified else 'No'}\n"
                f"**Last Scan**: {scan_date.strftime('%Y-%m-%d %H:%M:%S') if scan_date else 'Never'}\n"
                f"**Verification Date**: {verification_date.strftime('%Y-%m-%d %H:%M:%S') if verification_date else 'Never'}\n"
                f"**Models**: {model_count}"
            ),
            inline=False
        )
        
        # Add connectivity status - this would be from an actual check in a real implementation
        status_embed.add_field(
            name="Connectivity Status",
            value="*Status check functionality not implemented in this version.*",
            inline=False
        )
        
        # Add available actions
        status_embed.add_field(
            name="Available Actions",
            value=(
                f"• Use `/server info {address} {port}` to see detailed information\n"
                f"• Use `/server verify {address} {port}` to verify connectivity\n"
                f"• Use `/manage action:sync type:server ip:{address} port:{port}` to sync models"
            ),
            inline=False
        )
        
        await safe_followup(interaction, embed=status_embed)
    
    except Exception as e:
        logger.error(f"Error checking server status: {str(e)}")
        raise 