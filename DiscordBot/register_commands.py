import discord
from discord import app_commands
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from utils import format_embed_message, safe_defer, safe_followup
import asyncio

# Import command modules
from admin_command import register_admin_command
from manage_command import register_manage_command
from models_command import register_models_command
from chat_command import register_chat_command
from server_command import register_server_command
from help_command import register_help_command
from history_command import register_history_command
from stats_command import register_stats_command
from deprecated_commands import register_deprecated_commands

# Import consolidated commands registration 
from register_consolidated_commands import register_commands_with_bot

# Import our command handlers
from command_handlers import (
    handle_models_command,
    handle_chat_command,
    handle_server_command,
    handle_history_command,
    handle_help_command,
    handle_admin_command,
    handle_manage_command,
    handle_stats_command
)

logger = logging.getLogger("register_commands")

async def register_commands(client, guild_id=None):
    """
    Register slash commands with Discord. If guild_id is provided, registers as guild commands (instant update).
    Otherwise, registers as global commands (can take up to 1 hour to propagate).
    """
    try:
        # Define the consolidated commands
        models_command = app_commands.Command(
            name="models",
            description="Search, filter, and view available Ollama models",
            callback=handle_models_command,
            parameters=[
                app_commands.Parameter(
                    name="search",
                    description="Search for models by name or description",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="size",
                    description="Filter by model size (e.g., '7B', '13B')",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="quantization",
                    description="Filter by quantization level (e.g., 'Q4_0', 'Q8_0')",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="action",
                    description="Action to perform",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="List models", value="list"),
                        app_commands.Choice(name="Get model info", value="info"),
                        app_commands.Choice(name="Download model", value="download"),
                        app_commands.Choice(name="Remove model", value="remove")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="sort_by",
                    description="Sort results by",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Name", value="name"),
                        app_commands.Choice(name="Size", value="size"),
                        app_commands.Choice(name="Date", value="date")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="descending",
                    description="Sort in descending order",
                    type=discord.AppCommandOptionType.boolean,
                    required=False
                ),
                app_commands.Parameter(
                    name="limit",
                    description="Maximum number of results to show",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=25,
                    required=False
                ),
                app_commands.Parameter(
                    name="show_endpoints",
                    description="Show available endpoints for each model",
                    type=discord.AppCommandOptionType.boolean,
                    required=False
                )
            ]
        )
        
        chat_command = app_commands.Command(
            name="chat",
            description="Chat with any Ollama model",
            callback=handle_chat_command,
            parameters=[
                app_commands.Parameter(
                    name="model",
                    description="Model to chat with",
                    type=discord.AppCommandOptionType.string,
                    required=True
                ),
                app_commands.Parameter(
                    name="prompt",
                    description="Your message to the model",
                    type=discord.AppCommandOptionType.string,
                    required=True
                ),
                app_commands.Parameter(
                    name="system_prompt",
                    description="System instructions for the model",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="temperature",
                    description="Controls randomness (0.0-1.0)",
                    type=discord.AppCommandOptionType.number,
                    min_value=0.0,
                    max_value=2.0,
                    required=False
                ),
                app_commands.Parameter(
                    name="max_tokens",
                    description="Maximum response length",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=4096,
                    required=False
                ),
                app_commands.Parameter(
                    name="save_history",
                    description="Whether to save this chat in history",
                    type=discord.AppCommandOptionType.boolean,
                    required=False
                ),
                app_commands.Parameter(
                    name="verbose",
                    description="Show detailed information in the response",
                    type=discord.AppCommandOptionType.boolean,
                    required=False
                )
            ]
        )
        
        server_command = app_commands.Command(
            name="server",
            description="Manage Ollama server connections",
            callback=handle_server_command,
            parameters=[
                app_commands.Parameter(
                    name="action",
                    description="Action to perform",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="List servers", value="list"),
                        app_commands.Choice(name="Add server", value="add"),
                        app_commands.Choice(name="Remove server", value="remove"),
                        app_commands.Choice(name="Check server status", value="status")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="ip",
                    description="IP address of the server",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="port",
                    description="Port number (defaults to 11434)",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=65535,
                    required=False
                ),
                app_commands.Parameter(
                    name="sort_by",
                    description="Sort results by",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Name", value="name"),
                        app_commands.Choice(name="Status", value="status"),
                        app_commands.Choice(name="Models", value="models")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="limit",
                    description="Maximum number of results to show",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=25,
                    required=False
                )
            ]
        )
        
        history_command = app_commands.Command(
            name="history",
            description="View and manage your chat history",
            callback=handle_history_command,
            parameters=[
                app_commands.Parameter(
                    name="action",
                    description="Action to perform",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="List history", value="list"),
                        app_commands.Choice(name="View chat", value="view"),
                        app_commands.Choice(name="Delete chat", value="delete"),
                        app_commands.Choice(name="Export history", value="export")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="limit",
                    description="Maximum number of results to show",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=25,
                    required=False
                ),
                app_commands.Parameter(
                    name="model_id",
                    description="Filter by model name",
                    type=discord.AppCommandOptionType.string,
                    required=False
                ),
                app_commands.Parameter(
                    name="search",
                    description="Search for specific content or specify chat ID",
                    type=discord.AppCommandOptionType.string,
                    required=False
                )
            ]
        )
        
        help_command = app_commands.Command(
            name="help",
            description="Get help with ModelNet Bot commands",
            callback=handle_help_command,
            parameters=[
                app_commands.Parameter(
                    name="topic",
                    description="Help topic",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Models", value="models"),
                        app_commands.Choice(name="Chat", value="chat"),
                        app_commands.Choice(name="Server", value="server"),
                        app_commands.Choice(name="History", value="history"),
                        app_commands.Choice(name="Admin", value="admin"),
                        app_commands.Choice(name="Manage", value="manage"),
                        app_commands.Choice(name="Stats", value="stats")
                    ],
                    required=False
                )
            ]
        )
        
        admin_command = app_commands.Command(
            name="admin",
            description="Administrative functions (admin only)",
            callback=handle_admin_command,
            parameters=[
                app_commands.Parameter(
                    name="action",
                    description="Action to perform",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Restart bot", value="restart"),
                        app_commands.Choice(name="Manage users", value="users"),
                        app_commands.Choice(name="Configure bot", value="config")
                    ],
                    required=True
                )
            ]
        )
        
        manage_command = app_commands.Command(
            name="manage",
            description="Manage models, servers, and users (admin only)",
            callback=handle_manage_command,
            parameters=[
                app_commands.Parameter(
                    name="resource",
                    description="Resource to manage",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Models", value="models"),
                        app_commands.Choice(name="Servers", value="servers"),
                        app_commands.Choice(name="Users", value="users")
                    ],
                    required=True
                ),
                app_commands.Parameter(
                    name="action",
                    description="Action to perform",
                    type=discord.AppCommandOptionType.string,
                    required=True
                )
            ]
        )
        
        stats_command = app_commands.Command(
            name="stats",
            description="View usage statistics and analytics (admin only)",
            callback=handle_stats_command,
            parameters=[
                app_commands.Parameter(
                    name="type",
                    description="Type of statistics to view",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Usage", value="usage"),
                        app_commands.Choice(name="Users", value="users"),
                        app_commands.Choice(name="Models", value="models"),
                        app_commands.Choice(name="Servers", value="servers")
                    ],
                    required=False
                ),
                app_commands.Parameter(
                    name="days",
                    description="Time period in days",
                    type=discord.AppCommandOptionType.integer,
                    min_value=1,
                    max_value=90,
                    required=False
                ),
                app_commands.Parameter(
                    name="format",
                    description="Output format",
                    type=discord.AppCommandOptionType.string,
                    choices=[
                        app_commands.Choice(name="Text", value="text"),
                        app_commands.Choice(name="Graph", value="graph")
                    ],
                    required=False
                )
            ]
        )
        
        # Consolidate all commands
        commands = [
            models_command,
            chat_command,
            server_command,
            history_command,
            help_command,
            admin_command,
            manage_command,
            stats_command
        ]
        
        # Register commands
        if guild_id:
            # Guild commands update instantly
            guild = discord.Object(id=guild_id)
            client.tree.add_command(models_command, guild=guild)
            client.tree.add_command(chat_command, guild=guild)
            client.tree.add_command(server_command, guild=guild)
            client.tree.add_command(history_command, guild=guild)
            client.tree.add_command(help_command, guild=guild)
            client.tree.add_command(admin_command, guild=guild)
            client.tree.add_command(manage_command, guild=guild)
            client.tree.add_command(stats_command, guild=guild)
            
            await client.tree.sync(guild=guild)
            logger.info(f"Registered commands to guild: {guild_id}")
        else:
            # Global commands can take up to 1 hour to propagate
            client.tree.add_command(models_command)
            client.tree.add_command(chat_command)
            client.tree.add_command(server_command)
            client.tree.add_command(history_command)
            client.tree.add_command(help_command)
            client.tree.add_command(admin_command)
            client.tree.add_command(manage_command)
            client.tree.add_command(stats_command)
            
            await client.tree.sync()
            logger.info("Registered global commands")
            
    except Exception as e:
        logger.error(f"Error registering consolidated commands: {str(e)}")
        raise

async def update_commands_if_needed(client, guild_id=None):
    """
    Check if the commands list needs updating and update if necessary.
    """
    try:
        # Expected command names based on our current implementation
        expected_commands = ['models', 'chat', 'server', 'history', 'help', 'admin', 'manage', 'stats']
        
        # Get currently registered commands
        current_commands = []
        if guild_id:
            guild = discord.Object(id=guild_id)
            app_commands_list = await client.tree.fetch_commands(guild=guild)
        else:
            app_commands_list = await client.tree.fetch_commands()
            
        current_commands = [cmd.name for cmd in app_commands_list]
        
        # Check if updates are needed
        missing_commands = [cmd for cmd in expected_commands if cmd not in current_commands]
        extra_commands = [cmd for cmd in current_commands if cmd not in expected_commands]
        
        if missing_commands or extra_commands:
            logger.info(f"Command list needs updating - missing: {missing_commands}, extra: {extra_commands}")
            
            # Clear existing commands
            if guild_id:
                guild = discord.Object(id=guild_id)
                client.tree.clear_commands(guild=guild)
                await client.tree.sync(guild=guild)
            else:
                client.tree.clear_commands()
                await client.tree.sync()
                
            # Re-register commands
            await register_commands(client, guild_id)
            return True
        else:
            logger.info("Commands are up to date")
            return False
            
    except Exception as e:
        logger.error(f"Error checking/updating commands: {str(e)}")
        return False

def register_user_commands(bot):
    """Register user commands"""
    
    # 1. /models command
    @bot.tree.command(name="models", description="Search, filter, and view available Ollama models")
    @app_commands.describe(
        search="Optional: Search for models by name",
        size="Optional: Filter by parameter size (e.g. 7B, 13B)",
        quantization="Optional: Filter by quantization level (e.g. Q4_K_M)",
        action="Optional: Action to perform (list, search, details)",
        sort_by="Optional: Sort results by this field",
        descending="Optional: Sort in descending order",
        limit="Optional: Maximum number of results to return",
        show_endpoints="Optional: Show endpoint details for each model"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Models", value="list"),
        app_commands.Choice(name="Search Models", value="search"),
        app_commands.Choice(name="Model Details", value="details"),
        app_commands.Choice(name="Find Endpoints", value="endpoints")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Parameters", value="params"),
        app_commands.Choice(name="Quantization", value="quant"),
        app_commands.Choice(name="Count", value="count")
    ])
    async def models_command(
        interaction: discord.Interaction,
        action: str = "list",
        search: str = None,
        size: str = None,
        quantization: str = None,
        sort_by: str = None,
        descending: bool = True,
        limit: int = 25,
        show_endpoints: bool = False
    ):
        """Unified command for model discovery and information"""
        await safe_defer(interaction)
        
        try:
            await interaction.followup.send("The /models command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in models command: {e}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # 2. /chat command
    @bot.tree.command(name="chat", description="Chat with any Ollama model")
    @app_commands.describe(
        model="Model ID or name to chat with",
        prompt="Your message to the model",
        system_prompt="Optional system prompt to guide the model",
        temperature="Controls randomness (0.0 to 1.0)",
        max_tokens="Maximum tokens in the response",
        save_history="Save this chat in your history",
        verbose="Show detailed API information"
    )
    async def chat_command(
        interaction: discord.Interaction,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        save_history: bool = True,
        verbose: bool = False
    ):
        """Unified command for chatting with models"""
        await safe_defer(interaction)
        
        try:
            await interaction.followup.send("The /chat command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in chat command: {str(e)}")
            error_embed = await format_embed_message(
                title="❌ Error",
                description=f"An error occurred: ```\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # 3. /server command
    @bot.tree.command(name="server", description="View and manage Ollama servers")
    @app_commands.describe(
        action="Action to perform",
        ip="Server IP address (for specific server actions)",
        port="Server port (default: 11434)",
        sort_by="Field to sort results by",
        limit="Maximum number of results to return"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List All Servers", value="list"),
        app_commands.Choice(name="Server Details", value="details"),
        app_commands.Choice(name="Check Models", value="check"),
        app_commands.Choice(name="Verify Connectivity", value="verify")
    ])
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="IP Address", value="ip"),
        app_commands.Choice(name="Last Verified", value="date"),
        app_commands.Choice(name="Model Count", value="count")
    ])
    async def server_command(
        interaction: discord.Interaction,
        action: str,
        ip: str = None,
        port: int = 11434,
        sort_by: str = None,
        limit: int = 25
    ):
        """Unified command for server management"""
        await safe_defer(interaction)
        
        try:
            await interaction.followup.send("The /server command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in server command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # 4. /history command
    @bot.tree.command(name="history", description="View and manage your chat history")
    @app_commands.describe(
        action="Action to perform",
        limit="Maximum number of history items to show",
        model_id="Filter by model ID",
        search="Search term to filter history by"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="View History", value="view"),
        app_commands.Choice(name="Clear History", value="clear"),
        app_commands.Choice(name="Continue Chat", value="continue")
    ])
    async def history_command(
        interaction: discord.Interaction,
        action: str = "view",
        limit: int = 5,
        model_id: int = None,
        search: str = None
    ):
        """Command for viewing and managing chat history"""
        await safe_defer(interaction)
        
        try:
            await interaction.followup.send("The /history command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in history command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # 5. /help command
    @bot.tree.command(name="help", description="Show help information")
    @app_commands.describe(
        topic="Optional: Get help on a specific topic"
    )
    @app_commands.choices(topic=[
        app_commands.Choice(name="Models", value="models"),
        app_commands.Choice(name="Chat", value="chat"),
        app_commands.Choice(name="Servers", value="servers"),
        app_commands.Choice(name="Admin", value="admin"),
        app_commands.Choice(name="Examples", value="examples")
    ])
    async def help_command(
        interaction: discord.Interaction,
        topic: str = None
    ):
        """Updated help command reflecting the new command structure"""
        try:
            await interaction.response.send_message("The /help command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in help command: {str(e)}")
            await interaction.response.send_message(f"Error generating help: {str(e)}", ephemeral=True)

def register_admin_commands(bot):
    """Register admin commands"""
    
    # 1. /admin command
    @bot.tree.command(name="admin", description="Administrative functions and tools")
    @app_commands.describe(
        action="Action to perform",
        target="Target for the action",
        force="Force the action even if it might be destructive"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Database Info", value="db_info"),
        app_commands.Choice(name="Refresh Commands", value="refresh"),
        app_commands.Choice(name="Cleanup Database", value="cleanup"),
        app_commands.Choice(name="Verify All Servers", value="verify"),
        app_commands.Choice(name="Sync Models", value="sync")
    ])
    @app_commands.choices(target=[
        app_commands.Choice(name="Global", value="global"),
        app_commands.Choice(name="Guild", value="guild"),
        app_commands.Choice(name="All Servers", value="all")
    ])
    async def admin_command(
        interaction: discord.Interaction,
        action: str,
        target: str = "guild",
        force: bool = False
    ):
        """Administrative command for managing the bot and database"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        await safe_defer(interaction)
        
        try:
            await interaction.followup.send("The /admin command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in admin command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    # 2. /manage command
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
            await interaction.followup.send("The /manage command is being implemented. Please check back soon!")
        except Exception as e:
            logger.error(f"Error in manage command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)

async def sync_commands(bot, guild_id=None):
    """
    Sync all registered commands with Discord.
    
    Args:
        bot: The Discord bot instance
        guild_id: Optional guild ID to sync commands with
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Syncing commands {'to guild ' + str(guild_id) if guild_id else 'globally'}...")
        
        if guild_id:
            # Sync with specific guild
            guild = discord.Object(id=guild_id)
            await bot.tree.sync(guild=guild)
            logger.info(f"Synced commands with guild: {guild_id}")
        else:
            # Sync globally
            await bot.tree.sync()
            logger.info("Synced commands globally")
            
        return True
        
    except Exception as e:
        logger.error(f"Error syncing commands: {str(e)}")
        return False

async def register_all_commands(bot, safe_defer, safe_followup, check_server_connectivity=None, sync_models_with_server=None):
    """
    Main function to register all commands with the bot.
    Integrates both the legacy and new consolidated command systems.
    
    Args:
        bot: The Discord bot instance
        safe_defer: Function for safely deferring interactions
        safe_followup: Function for safely following up on interactions
        check_server_connectivity: Optional function for checking server connectivity
        sync_models_with_server: Optional function for syncing models with a server
        
    Returns:
        dict: A mapping of command names to command functions
    """
    try:
        logger.info("Registering all commands...")
        
        # Try to register using consolidated commands system first
        try:
            logger.info("Attempting to register using consolidated commands system...")
            commands = register_commands_with_bot(bot, safe_defer, safe_followup)
            logger.info(f"Successfully registered using consolidated commands: {', '.join(commands.keys())}")
            return commands
        except Exception as e:
            logger.error(f"Error registering using consolidated commands: {e}")
            logger.info("Falling back to traditional registration...")
        
        # If consolidated commands failed, register using traditional methods
        commands = {}
        
        # Register user commands (for all users)
        register_user_commands(bot)
        
        # Register admin commands (for admins only)
        register_admin_commands(bot)
        
        # Register deprecated commands (with deprecation notices)
        register_deprecated_commands(bot)
        
        logger.info("Command registration complete with traditional method")
        return {
            "models": handle_models_command,
            "chat": handle_chat_command,
            "server": handle_server_command,
            "history": handle_history_command,
            "help": handle_help_command,
            "admin": handle_admin_command,
            "manage": handle_manage_command,
            "stats": handle_stats_command
        }
        
    except Exception as e:
        logger.error(f"Error in register_all_commands: {e}")
        raise
