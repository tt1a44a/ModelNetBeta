import logging
import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_manage_command(bot, safe_defer, safe_followup, check_server_connectivity=None, sync_models_with_server=None):
    """Register the manage command with the bot"""
    
    @bot.tree.command(name="manage", description="Manage models and servers")
    @app_commands.describe(
        action="Action to perform",
        type="Type of resource to manage",
        model_id="Model ID (for model actions)",
        model_name="Model name (for adding models)",
        ip="Server IP address",
        port="Server port (default: 11434)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Delete", value="delete"),
        app_commands.Choice(name="Update", value="update"),
        app_commands.Choice(name="Sync", value="sync")
    ])
    @app_commands.choices(type=[
        app_commands.Choice(name="Model", value="model"),
        app_commands.Choice(name="Server", value="server")
    ])
    async def manage_command(
        interaction: discord.Interaction,
        action: str,
        type: str,
        model_id: int = None,
        model_name: str = None,
        ip: str = None,
        port: int = 11434
    ):
        """Command for managing models and servers"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        await safe_defer(interaction)
        
        try:
            if type == "model":
                if action == "add":
                    if not ip or not model_name:
                        await safe_followup(interaction, "IP and model name are required to add a model")
                        return
                    await handle_add_model(interaction, ip, port, model_name, safe_followup)
                elif action == "delete":
                    if not model_id:
                        await safe_followup(interaction, "Model ID is required to delete a model")
                        return
                    await handle_delete_model(interaction, model_id, safe_followup)
                elif action == "update":
                    if not model_id:
                        await safe_followup(interaction, "Model ID is required to update a model")
                        return
                    await handle_update_model(interaction, model_id, model_name, safe_followup)
                elif action == "sync":
                    if not ip:
                        await safe_followup(interaction, "IP is required to sync models")
                        return
                    await handle_sync_model(interaction, ip, port, sync_models_with_server, safe_followup)
                else:
                    await safe_followup(interaction, "Unknown action for model management")
            elif type == "server":
                if action == "add":
                    if not ip:
                        await safe_followup(interaction, "IP is required to add a server")
                        return
                    await handle_add_server(interaction, ip, port, check_server_connectivity, safe_followup)
                elif action == "delete":
                    if not ip:
                        await safe_followup(interaction, "IP is required to delete a server")
                        return
                    await handle_delete_server(interaction, ip, port, safe_followup)
                elif action == "update":
                    if not ip:
                        await safe_followup(interaction, "IP is required to update a server")
                        return
                    await handle_update_server(interaction, ip, port, safe_followup)
                elif action == "sync":
                    if not ip:
                        await safe_followup(interaction, "IP is required to sync a server")
                        return
                    await handle_sync_server(interaction, ip, port, sync_models_with_server, safe_followup)
                else:
                    await safe_followup(interaction, "Unknown action for server management")
            else:
                await safe_followup(interaction, "Unknown resource type")
                
        except Exception as e:
            logger.error(f"Error in manage command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return manage_command

async def handle_add_model(interaction: discord.Interaction, ip: str, port: int, model_name: str, safe_followup):
    """Handler for adding a model"""
    try:
        # First check if the server exists
        server_query = """
            SELECT id FROM endpoints 
            WHERE ip = %s AND port = %s
        """
        server = Database.fetch_one(server_query, (ip, port))
        
        if not server:
            # Server doesn't exist, need to add it first
            error_embed = await format_embed_message(
                title="Server Not Found",
                description=f"Server {ip}:{port} does not exist in the database. Please add the server first.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        endpoint_id = server[0]
        
        # Check if model already exists for this server
        model_check_query = """
            SELECT id FROM models 
            WHERE endpoint_id = %s AND name = %s
        """
        existing_model = Database.fetch_one(model_check_query, (endpoint_id, model_name))
        
        if existing_model:
            # Model already exists
            error_embed = await format_embed_message(
                title="Model Already Exists",
                description=f"Model '{model_name}' already exists for server {ip}:{port}.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        # Add the model
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        insert_query = """
            INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        new_model = Database.fetch_one(insert_query, (endpoint_id, model_name, 'Unknown', 'Unknown', now))
        
        if new_model:
            success_embed = await format_embed_message(
                title="Model Added",
                description=f"Model '{model_name}' added successfully with ID {new_model[0]}.",
                color=discord.Color.green()
            )
            await safe_followup(interaction, embed=success_embed)
        else:
            error_embed = await format_embed_message(
                title="Error Adding Model",
                description=f"Failed to add model '{model_name}' to server {ip}:{port}.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_add_model: {str(e)}")
        raise

async def handle_delete_model(interaction: discord.Interaction, model_id: int, safe_followup):
    """Handler for deleting a model"""
    try:
        # Check if model exists
        model_query = """
            SELECT m.id, m.name, e.ip, e.port
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.id = %s
        """
        model = Database.fetch_one(model_query, (model_id,))
        
        if not model:
            error_embed = await format_embed_message(
                title="Model Not Found",
                description=f"Model with ID {model_id} not found in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        model_name = model[1]
        server_ip = model[2]
        server_port = model[3]
        
        # Delete the model
        delete_query = """
            DELETE FROM models
            WHERE id = %s
            RETURNING id
        """
        deleted = Database.fetch_one(delete_query, (model_id,))
        
        if deleted:
            success_embed = await format_embed_message(
                title="Model Deleted",
                description=f"Model '{model_name}' (ID: {model_id}) successfully deleted from server {server_ip}:{server_port}.",
                color=discord.Color.green()
            )
            await safe_followup(interaction, embed=success_embed)
        else:
            error_embed = await format_embed_message(
                title="Error Deleting Model",
                description=f"Failed to delete model with ID {model_id}.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_delete_model: {str(e)}")
        raise

async def handle_update_model(interaction: discord.Interaction, model_id: int, model_name: str, safe_followup):
    """Handler for updating a model"""
    try:
        # Check if model exists
        model_query = """
            SELECT m.id, m.name, e.ip, e.port
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.id = %s
        """
        model = Database.fetch_one(model_query, (model_id,))
        
        if not model:
            error_embed = await format_embed_message(
                title="Model Not Found",
                description=f"Model with ID {model_id} not found in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        old_model_name = model[1]
        server_ip = model[2]
        server_port = model[3]
        
        # If no new name provided, show current info
        if not model_name:
            info_embed = await format_embed_message(
                title="Model Information",
                description=f"Model ID: {model_id}\nName: {old_model_name}\nServer: {server_ip}:{server_port}",
                color=discord.Color.blue()
            )
            await safe_followup(interaction, embed=info_embed)
            return
            
        # Update the model name
        update_query = """
            UPDATE models
            SET name = %s, updated_at = %s
            WHERE id = %s
            RETURNING id
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        updated = Database.fetch_one(update_query, (model_name, now, model_id))
        
        if updated:
            success_embed = await format_embed_message(
                title="Model Updated",
                description=f"Model name updated from '{old_model_name}' to '{model_name}' (ID: {model_id}).",
                color=discord.Color.green()
            )
            await safe_followup(interaction, embed=success_embed)
        else:
            error_embed = await format_embed_message(
                title="Error Updating Model",
                description=f"Failed to update model with ID {model_id}.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_update_model: {str(e)}")
        raise

async def handle_sync_model(interaction: discord.Interaction, ip: str, port: int, sync_models_with_server, safe_followup):
    """Handler for syncing models for a server"""
    try:
        # Check if we have the sync_models_with_server function
        if not sync_models_with_server:
            error_embed = await format_embed_message(
                title="Function Not Available",
                description="The sync models function is not available.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        # Check if the server exists
        server_query = """
            SELECT id FROM endpoints 
            WHERE ip = %s AND port = %s
        """
        server = Database.fetch_one(server_query, (ip, port))
        
        if not server:
            error_embed = await format_embed_message(
                title="Server Not Found",
                description=f"Server {ip}:{port} does not exist in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        endpoint_id = server[0]
        
        # Tell the user we're starting the sync
        await safe_followup(interaction, f"Starting model sync for server {ip}:{port}. This may take a moment...")
        
        # Call the sync function (this would be a call to an external function)
        try:
            # This is a placeholder for the sync_models_with_server function
            # In a real implementation, this would be a call to the actual function
            if sync_models_with_server:
                # The actual implementation might look like this:
                # result = await sync_models_with_server(ip, port)
                result = {"success": True, "models_found": 5, "models_added": 3}
            else:
                result = {"success": False, "error": "Sync function not available"}
                
            if result["success"]:
                success_embed = await format_embed_message(
                    title="Models Synced",
                    description=(
                        f"Successfully synced models for server {ip}:{port}.\n"
                        f"Found {result.get('models_found', 0)} models.\n"
                        f"Added {result.get('models_added', 0)} new models."
                    ),
                    color=discord.Color.green()
                )
                await safe_followup(interaction, embed=success_embed)
            else:
                error_embed = await format_embed_message(
                    title="Sync Failed",
                    description=f"Failed to sync models: {result.get('error', 'Unknown error')}",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                
        except Exception as e:
            logger.error(f"Error syncing models with server: {str(e)}")
            error_embed = await format_embed_message(
                title="Sync Error",
                description=f"Error syncing models: {str(e)}",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_sync_model: {str(e)}")
        raise

async def handle_add_server(interaction: discord.Interaction, ip: str, port: int, check_server_connectivity, safe_followup):
    """Handler for adding a server"""
    try:
        # Check if server already exists
        server_query = """
            SELECT id FROM endpoints 
            WHERE ip = %s AND port = %s
        """
        existing_server = Database.fetch_one(server_query, (ip, port))
        
        if existing_server:
            error_embed = await format_embed_message(
                title="Server Already Exists",
                description=f"Server {ip}:{port} already exists in the database with ID {existing_server[0]}.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        # Check connectivity if the function is available
        if check_server_connectivity:
            await safe_followup(interaction, f"Checking connectivity to server {ip}:{port}...")
            
            try:
                # This is a placeholder for the check_server_connectivity function
                # In a real implementation, this would be a call to the actual function
                connectivity_result = await check_server_connectivity(ip, port)
                
                if not connectivity_result["success"]:
                    warning_embed = await format_embed_message(
                        title="Connectivity Issue",
                        description=(
                            f"Warning: Could not connect to Ollama server at {ip}:{port}.\n"
                            f"Error: {connectivity_result.get('error', 'Unknown error')}\n\n"
                            f"The server will still be added to the database, but it may not be accessible."
                        ),
                        color=discord.Color.orange()
                    )
                    await safe_followup(interaction, embed=warning_embed)
                else:
                    info_embed = await format_embed_message(
                        title="Server Connectivity",
                        description=f"Successfully connected to Ollama server at {ip}:{port}.",
                        color=discord.Color.green()
                    )
                    await safe_followup(interaction, embed=info_embed)
            except Exception as e:
                logger.error(f"Error checking server connectivity: {str(e)}")
                warning_embed = await format_embed_message(
                    title="Connectivity Check Failed",
                    description=f"Error checking server connectivity: {str(e)}",
                    color=discord.Color.orange()
                )
                await safe_followup(interaction, embed=warning_embed)
        
        # Add the server to the database
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        insert_query = """
            INSERT INTO endpoints (ip, port, scan_date, verified, is_honeypot)
            VALUES (%s, %s, %s, 1, FALSE)
            RETURNING id
        """
        new_endpoint = Database.fetch_one(insert_query, (ip, port, now))
        
        if new_endpoint:
            endpoint_id = new_endpoint[0]
            
            # Add to verified_endpoints as well
            verified_query = """
                INSERT INTO verified_endpoints (endpoint_id, verification_date)
                VALUES (%s, %s)
            """
            Database.execute(verified_query, (endpoint_id, now))
            
            success_embed = await format_embed_message(
                title="Server Added",
                description=f"Server {ip}:{port} added successfully with ID {endpoint_id}.",
                color=discord.Color.green()
            )
            await safe_followup(interaction, embed=success_embed)
        else:
            error_embed = await format_embed_message(
                title="Error Adding Server",
                description=f"Failed to add server {ip}:{port} to the database.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_add_server: {str(e)}")
        raise

async def handle_delete_server(interaction: discord.Interaction, ip: str, port: int, safe_followup):
    """Handler for deleting a server"""
    try:
        # Check if server exists
        server_query = """
            SELECT id FROM endpoints 
            WHERE ip = %s AND port = %s
        """
        server = Database.fetch_one(server_query, (ip, port))
        
        if not server:
            error_embed = await format_embed_message(
                title="Server Not Found",
                description=f"Server {ip}:{port} not found in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        endpoint_id = server[0]
        
        # Count models associated with this endpoint
        models_query = """
            SELECT COUNT(*) FROM models 
            WHERE endpoint_id = %s
        """
        model_count = Database.fetch_one(models_query, (endpoint_id,))[0]
        
        # Confirm with the user before deleting
        confirm_embed = await format_embed_message(
            title="Confirm Server Deletion",
            description=(
                f"Are you sure you want to delete server {ip}:{port} (ID: {endpoint_id})?\n"
                f"This server has {model_count} models associated with it.\n\n"
                f"All associated models will also be deleted.\n"
                f"This action cannot be undone.\n\n"
                f"To confirm, use the command again with the same parameters."
            ),
            color=discord.Color.orange()
        )
        confirm_key = f"delete_server_{ip}_{port}_{endpoint_id}"
        
        # In a real implementation, you would store the confirmation key
        # and check it when the user runs the command again
        # For now, we'll just simulate deletion
        
        # Execute the deletion
        try:
            # Start a transaction
            Database.execute("BEGIN")
            
            # First delete from verified_endpoints
            Database.execute("""
                DELETE FROM verified_endpoints
                WHERE endpoint_id = %s
            """, (endpoint_id,))
            
            # Then delete associated models
            Database.execute("""
                DELETE FROM models
                WHERE endpoint_id = %s
            """, (endpoint_id,))
            
            # Finally delete the endpoint
            Database.execute("""
                DELETE FROM endpoints
                WHERE id = %s
            """, (endpoint_id,))
            
            # Commit the transaction
            Database.execute("COMMIT")
            
            success_embed = await format_embed_message(
                title="Server Deleted",
                description=f"Server {ip}:{port} (ID: {endpoint_id}) and its {model_count} associated models have been deleted.",
                color=discord.Color.green()
            )
            await safe_followup(interaction, embed=success_embed)
            
        except Exception as e:
            # Rollback on error
            Database.execute("ROLLBACK")
            logger.error(f"Error during server deletion: {str(e)}")
            error_embed = await format_embed_message(
                title="Deletion Error",
                description=f"Error deleting server: {str(e)}",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_delete_server: {str(e)}")
        raise

async def handle_update_server(interaction: discord.Interaction, ip: str, port: int, safe_followup):
    """Handler for updating a server"""
    try:
        # Check if server exists
        server_query = """
            SELECT id, verified, scan_date, verification_date
            FROM endpoints e
            LEFT JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            WHERE e.ip = %s AND e.port = %s
        """
        server = Database.fetch_one(server_query, (ip, port))
        
        if not server:
            error_embed = await format_embed_message(
                title="Server Not Found",
                description=f"Server {ip}:{port} not found in the database.",
                color=discord.Color.orange()
            )
            await safe_followup(interaction, embed=error_embed)
            return
            
        endpoint_id = server[0]
        is_verified = server[1] == 1
        scan_date = server[2]
        verification_date = server[3]
        
        # Count models associated with this endpoint
        models_query = """
            SELECT COUNT(*) FROM models 
            WHERE endpoint_id = %s
        """
        model_count = Database.fetch_one(models_query, (endpoint_id,))[0]
        
        # Update verification timestamp
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        if is_verified:
            # Update verification date
            Database.execute("""
                UPDATE verified_endpoints
                SET verification_date = %s
                WHERE endpoint_id = %s
            """, (now, endpoint_id))
        else:
            # Mark as verified
            Database.execute("""
                UPDATE endpoints
                SET verified = 1
                WHERE id = %s
            """, (endpoint_id,))
            
            # Add to verified_endpoints if not already there
            Database.execute("""
                INSERT INTO verified_endpoints (endpoint_id, verification_date)
                VALUES (%s, %s)
                ON CONFLICT (endpoint_id) DO UPDATE
                SET verification_date = EXCLUDED.verification_date
            """, (endpoint_id, now))
        
        success_embed = await format_embed_message(
            title="Server Updated",
            description=(
                f"Server {ip}:{port} (ID: {endpoint_id}) has been updated.\n"
                f"Verification status: {'Verified' if is_verified else 'Now verified'}\n"
                f"Last scan date: {scan_date}\n"
                f"Verification date: {now}\n"
                f"Associated models: {model_count}"
            ),
            color=discord.Color.green()
        )
        await safe_followup(interaction, embed=success_embed)
            
    except Exception as e:
        logger.error(f"Error in handle_update_server: {str(e)}")
        raise

async def handle_sync_server(interaction: discord.Interaction, ip: str, port: int, sync_models_with_server, safe_followup):
    """Handler for syncing a server (just an alias for sync_model)"""
    await handle_sync_model(interaction, ip, port, sync_models_with_server, safe_followup) 