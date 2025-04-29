import logging
import discord
from discord import app_commands
from datetime import datetime, timezone

from utils import format_embed_message

logger = logging.getLogger(__name__)

def register_deprecated_commands(bot, safe_defer, safe_followup, new_commands):
    """
    Register deprecated versions of commands that redirect to the new consolidated commands.
    This provides a transition period for users to adapt to the new command structure.
    
    Args:
        bot: The Discord bot instance
        safe_defer: Safe defer function
        safe_followup: Safe followup function
        new_commands: Dict of new command handlers (models_command, chat_command, etc.)
    """
    # Track registered deprecated commands
    deprecated_commands = []
    
    # ----- Model-related deprecated commands -----
    
    @bot.tree.command(name="listmodels", description="[DEPRECATED] Use /models instead")
    async def list_models_deprecated(interaction: discord.Interaction):
        """Deprecated version of list_models command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'list' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="list")
    
    deprecated_commands.append(list_models_deprecated)
    
    @bot.tree.command(name="findmodels", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(search="Model name to search for")
    async def find_models_deprecated(interaction: discord.Interaction, search: str):
        """Deprecated version of find_models command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'search' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="search", search=search)
    
    deprecated_commands.append(find_models_deprecated)
    
    @bot.tree.command(name="modeldetails", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(model_id="ID of the model to view details for")
    async def model_details_deprecated(interaction: discord.Interaction, model_id: int):
        """Deprecated version of modeldetails command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'details' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="details", search=str(model_id))
    
    deprecated_commands.append(model_details_deprecated)

    @bot.tree.command(name="searchmodels", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(model_name="Name to search for")
    async def search_models_deprecated(interaction: discord.Interaction, model_name: str):
        """Deprecated version of searchmodels command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'search' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="search", search=model_name)
    
    deprecated_commands.append(search_models_deprecated)

    @bot.tree.command(name="modelsbyparam", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(parameter_size="Parameter size to filter by")
    async def models_by_param_deprecated(interaction: discord.Interaction, parameter_size: str):
        """Deprecated version of modelsbyparam command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with size parameter instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="list", size=parameter_size)
    
    deprecated_commands.append(models_by_param_deprecated)

    @bot.tree.command(name="allmodels", description="[DEPRECATED] Use /models instead")
    async def all_models_deprecated(interaction: discord.Interaction):
        """Deprecated version of allmodels command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'list' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="list")
    
    deprecated_commands.append(all_models_deprecated)

    @bot.tree.command(name="models_with_servers", description="[DEPRECATED] Use /models instead")
    async def models_with_servers_deprecated(interaction: discord.Interaction):
        """Deprecated version of models_with_servers command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with show_endpoints=True instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="list", show_endpoints=True)
    
    deprecated_commands.append(models_with_servers_deprecated)

    @bot.tree.command(name="list_models", description="[DEPRECATED] Use /models instead")
    async def list_models_alt_deprecated(interaction: discord.Interaction):
        """Deprecated version of list_models command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="list")
    
    deprecated_commands.append(list_models_alt_deprecated)

    @bot.tree.command(name="find_model_endpoints", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(model_name="Name of model to find endpoints for")
    async def find_model_endpoints_deprecated(interaction: discord.Interaction, model_name: str):
        """Deprecated version of find_model_endpoints command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'endpoints' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="endpoints", search=model_name, show_endpoints=True)
    
    deprecated_commands.append(find_model_endpoints_deprecated)

    @bot.tree.command(name="model_status", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(model_id="ID of model to check status")
    async def model_status_deprecated(interaction: discord.Interaction, model_id: int):
        """Deprecated version of model_status command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'details' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="details", search=str(model_id))
    
    deprecated_commands.append(model_status_deprecated)

    @bot.tree.command(name="selectmodel", description="[DEPRECATED] Use /chat instead")
    @app_commands.describe(model_id="ID of model to select")
    async def select_model_deprecated(interaction: discord.Interaction, model_id: int):
        """Deprecated version of selectmodel command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/chat` with the model parameter instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    deprecated_commands.append(select_model_deprecated)
    
    # ----- Chat-related deprecated commands -----
    
    @bot.tree.command(name="chat_with_model", description="[DEPRECATED] Use /chat instead")
    @app_commands.describe(
        model_id="ID of the model to chat with",
        prompt="Your message to the model"
    )
    async def chat_with_model_deprecated(interaction: discord.Interaction, model_id: int, prompt: str):
        """Deprecated version of chat_with_model command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/chat` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'chat_command' in new_commands:
            await new_commands['chat_command'](interaction, model=str(model_id), prompt=prompt)
    
    deprecated_commands.append(chat_with_model_deprecated)

    @bot.tree.command(name="interact", description="[DEPRECATED] Use /chat instead")
    @app_commands.describe(
        model_id="ID of the model to chat with",
        message="Your message to the model"
    )
    async def interact_deprecated(interaction: discord.Interaction, model_id: int, message: str):
        """Deprecated version of interact command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/chat` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'chat_command' in new_commands:
            await new_commands['chat_command'](interaction, model=str(model_id), prompt=message)
    
    deprecated_commands.append(interact_deprecated)

    @bot.tree.command(name="quickprompt", description="[DEPRECATED] Use /chat instead")
    @app_commands.describe(
        model_name="Name of the model to chat with",
        prompt="Your message to the model"
    )
    async def quickprompt_deprecated(interaction: discord.Interaction, model_name: str, prompt: str):
        """Deprecated version of quickprompt command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/chat` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'chat_command' in new_commands:
            await new_commands['chat_command'](interaction, model=model_name, prompt=prompt)
    
    deprecated_commands.append(quickprompt_deprecated)
    
    # ----- Server-related deprecated commands -----
    
    @bot.tree.command(name="checkserver", description="[DEPRECATED] Use /server instead")
    @app_commands.describe(
        ip="Server IP address",
        port="Server port (default: 11434)"
    )
    async def check_server_deprecated(interaction: discord.Interaction, ip: str, port: int = 11434):
        """Deprecated version of checkserver command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/server` with action 'check' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'server_command' in new_commands:
            await new_commands['server_command'](interaction, action="check", ip=ip, port=port)
    
    deprecated_commands.append(check_server_deprecated)
    
    @bot.tree.command(name="listservers", description="[DEPRECATED] Use /server instead")
    async def list_servers_deprecated(interaction: discord.Interaction):
        """Deprecated version of listservers command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/server` with action 'list' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'server_command' in new_commands:
            await new_commands['server_command'](interaction, action="list")
    
    deprecated_commands.append(list_servers_deprecated)

    @bot.tree.command(name="serverinfo", description="[DEPRECATED] Use /server instead")
    @app_commands.describe(
        ip="Server IP address",
        port="Server port (default: 11434)"
    )
    async def server_info_deprecated(interaction: discord.Interaction, ip: str, port: int = 11434):
        """Deprecated version of serverinfo command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/server` with action 'details' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'server_command' in new_commands:
            await new_commands['server_command'](interaction, action="details", ip=ip, port=port)
    
    deprecated_commands.append(server_info_deprecated)

    @bot.tree.command(name="syncserver", description="[DEPRECATED] Use /server instead")
    @app_commands.describe(
        ip="Server IP address",
        port="Server port (default: 11434)"
    )
    async def sync_server_deprecated(interaction: discord.Interaction, ip: str, port: int = 11434):
        """Deprecated version of syncserver command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/server` with action 'verify' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'server_command' in new_commands:
            await new_commands['server_command'](interaction, action="verify", ip=ip, port=port)
    
    deprecated_commands.append(sync_server_deprecated)

    @bot.tree.command(name="offline_endpoints", description="[DEPRECATED] Use /server instead")
    async def offline_endpoints_deprecated(interaction: discord.Interaction):
        """Deprecated version of offline_endpoints command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/server` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'server_command' in new_commands:
            await new_commands['server_command'](interaction, action="list")
    
    deprecated_commands.append(offline_endpoints_deprecated)
    
    # ----- Admin-related deprecated commands -----
    
    @bot.tree.command(name="addmodel", description="[DEPRECATED] Use /manage instead")
    @app_commands.describe(
        ip="Server IP address",
        port="Server port (default: 11434)",
        model_name="Name of the model to add"
    )
    async def add_model_deprecated(interaction: discord.Interaction, ip: str, model_name: str, port: int = 11434):
        """Deprecated version of addmodel command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/manage` with action 'add' and type 'model' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'manage_command' in new_commands:
            await new_commands['manage_command'](interaction, action="add", type="model", ip=ip, port=port, model_name=model_name)
    
    deprecated_commands.append(add_model_deprecated)

    @bot.tree.command(name="deletemodel", description="[DEPRECATED] Use /manage instead")
    @app_commands.describe(model_id="ID of the model to delete")
    async def delete_model_deprecated(interaction: discord.Interaction, model_id: int):
        """Deprecated version of deletemodel command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/manage` with action 'delete' and type 'model' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'manage_command' in new_commands:
            await new_commands['manage_command'](interaction, action="delete", type="model", model_id=model_id)
    
    deprecated_commands.append(delete_model_deprecated)

    @bot.tree.command(name="manage_models", description="[DEPRECATED] Use /manage instead")
    async def manage_models_deprecated(interaction: discord.Interaction):
        """Deprecated version of manage_models command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/manage` instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    deprecated_commands.append(manage_models_deprecated)
    
    @bot.tree.command(name="addserver", description="[DEPRECATED] Use /manage instead")
    @app_commands.describe(
        ip="Server IP address",
        port="Server port (default: 11434)"
    )
    async def add_server_deprecated(interaction: discord.Interaction, ip: str, port: int = 11434):
        """Deprecated version of addserver command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/manage` with action 'add' and type 'server' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'manage_command' in new_commands:
            await new_commands['manage_command'](interaction, action="add", type="server", ip=ip, port=port)
    
    deprecated_commands.append(add_server_deprecated)
    
    @bot.tree.command(name="refreshcommands", description="[DEPRECATED] Use /admin instead")
    async def refresh_commands_deprecated(interaction: discord.Interaction):
        """Deprecated version of refreshcommands command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/admin` with action 'refresh' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'admin_command' in new_commands:
            await new_commands['admin_command'](interaction, action="refresh", target="guild")
    
    deprecated_commands.append(refresh_commands_deprecated)

    @bot.tree.command(name="guild_sync", description="[DEPRECATED] Use /admin instead")
    async def guild_sync_deprecated(interaction: discord.Interaction):
        """Deprecated version of guild_sync command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/admin` with action 'refresh' and target 'guild' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'admin_command' in new_commands:
            await new_commands['admin_command'](interaction, action="refresh", target="guild")
    
    deprecated_commands.append(guild_sync_deprecated)

    @bot.tree.command(name="refreshcommandsv2", description="[DEPRECATED] Use /admin instead")
    async def refreshcommandsv2_deprecated(interaction: discord.Interaction):
        """Deprecated version of refreshcommandsv2 command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/admin` with action 'refresh' and target 'global' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'admin_command' in new_commands:
            await new_commands['admin_command'](interaction, action="refresh", target="global")
    
    deprecated_commands.append(refreshcommandsv2_deprecated)

    @bot.tree.command(name="cleanup", description="[DEPRECATED] Use /admin instead")
    async def cleanup_deprecated(interaction: discord.Interaction):
        """Deprecated version of cleanup command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/admin` with action 'cleanup' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'admin_command' in new_commands:
            await new_commands['admin_command'](interaction, action="cleanup")
    
    deprecated_commands.append(cleanup_deprecated)
    
    @bot.tree.command(name="db_info", description="[DEPRECATED] Use /admin instead")
    async def db_info_deprecated(interaction: discord.Interaction):
        """Deprecated version of db_info command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/admin` with action 'db_info' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'admin_command' in new_commands:
            await new_commands['admin_command'](interaction, action="db_info")
    
    deprecated_commands.append(db_info_deprecated)

    @bot.tree.command(name="honeypot_stats", description="[DEPRECATED] Use /stats instead")
    async def honeypot_stats_deprecated(interaction: discord.Interaction):
        """Deprecated version of honeypot_stats command"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/stats` with type 'honeypots' instead which offers more options and better formatting.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'stats_command' in new_commands:
            await new_commands['stats_command'](interaction, type="honeypots")
    
    deprecated_commands.append(honeypot_stats_deprecated)

    @bot.tree.command(name="benchmark", description="[DEPRECATED] Use /models instead")
    @app_commands.describe(model_id="ID of model to benchmark")
    async def benchmark_deprecated(interaction: discord.Interaction, model_id: int):
        """Deprecated version of benchmark command"""
        embed = await format_embed_message(
            title="Command Deprecated",
            description="This command is deprecated. Please use `/models` with action 'details' instead which includes performance information.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Call the new command handler if available
        if 'models_command' in new_commands:
            await new_commands['models_command'](interaction, action="details", search=str(model_id))
    
    deprecated_commands.append(benchmark_deprecated)
    
    # Return the list of deprecated commands
    return deprecated_commands 