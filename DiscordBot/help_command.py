import logging
import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from utils import format_embed_message

logger = logging.getLogger(__name__)

def register_help_command(bot, safe_defer, safe_followup):
    """Register the help command with the bot"""
    
    # Define choices for help topics
    help_topics = [
        app_commands.Choice(name="Models", value="models"),
        app_commands.Choice(name="Chat", value="chat"),
        app_commands.Choice(name="Servers", value="servers"),
        app_commands.Choice(name="History", value="history"),
        app_commands.Choice(name="Admin Commands", value="admin"),
        app_commands.Choice(name="Examples", value="examples")
    ]
    
    @bot.tree.command(name="help", description="Get help on using the bot commands")
    @app_commands.describe(
        topic="Optional: Get help on a specific topic"
    )
    @app_commands.choices(topic=help_topics)
    async def help_command(
        interaction: discord.Interaction,
        topic: str = None
    ):
        """Command for showing help information"""
        try:
            # Always make help messages ephemeral (only visible to the user)
            await interaction.response.defer(ephemeral=True)
            
            if topic:
                # Topic-specific help
                if topic == "models":
                    embed = await create_models_help_embed()
                elif topic == "chat":
                    embed = await create_chat_help_embed()
                elif topic == "servers":
                    embed = await create_servers_help_embed()
                elif topic == "history":
                    embed = await create_history_help_embed()
                elif topic == "admin":
                    embed = await create_admin_help_embed()
                elif topic == "examples":
                    embed = await create_examples_help_embed()
                else:
                    embed = await create_general_help_embed()
            else:
                # General help overview
                embed = await create_general_help_embed()
                
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in help command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Generating Help",
                description=f"An error occurred while generating help content: ```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
    
    return help_command

async def create_general_help_embed() -> discord.Embed:
    """Create the general help embed with command overview"""
    embed = discord.Embed(
        title="🤖 AI Model Bot Help",
        description="This bot allows you to discover and chat with AI models across various servers.",
        color=discord.Color.blue()
    )
    
    # User commands section
    embed.add_field(
        name="📋 User Commands",
        value=(
            "• `/models` - Search, filter, and view available models\n"
            "• `/chat` - Chat with any AI model by ID or name\n"
            "• `/server` - View and manage AI model servers\n"
            "• `/history` - View and manage your chat history\n"
            "• `/help` - Show help information on specific topics"
        ),
        inline=False
    )
    
    # Admin commands section
    embed.add_field(
        name="⚙️ Admin Commands",
        value=(
            "• `/admin` - Administrative functions and tools\n"
            "• `/manage` - Manage models and servers\n"
            "• `/stats` - View statistics and analytics"
        ),
        inline=False
    )
    
    # Add usage tip
    embed.add_field(
        name="💡 Usage Tip",
        value="Use `/help [topic]` to get detailed help on specific commands",
        inline=False
    )
    
    embed.set_footer(text="Type / to see all available commands • Parameters are shown when you select a command")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_models_help_embed() -> discord.Embed:
    """Create help embed for the models command"""
    embed = discord.Embed(
        title="📋 Models Command Help",
        description="The `/models` command lets you discover and explore available AI models.",
        color=discord.Color.blue()
    )
    
    # Basic usage
    embed.add_field(
        name="Basic Usage",
        value=(
            "• `/models action:list` - List all available models\n"
            "• `/models action:info model_id:13` - Get detailed info about a specific model\n"
            "• `/models action:search search_query:llama` - Search for models by name"
        ),
        inline=False
    )
    
    # Parameters explanation
    embed.add_field(
        name="Parameters",
        value=(
            "**action**: The action to perform (list, info, or search)\n"
            "**model_id**: Model ID or name (required for 'info' action)\n"
            "**category**: Filter models by category (All, Text, Chat, Image, etc.)\n"
            "**sort_by**: Sort models by a specific field\n"
            "**search_query**: Search term to filter models (for 'search' action)\n"
            "**limit**: Maximum number of models to show (default: 10)"
        ),
        inline=False
    )
    
    # Examples
    embed.add_field(
        name="Examples",
        value=(
            "• `/models action:list category:Chat sort_by:Most Used`\n"
            "• `/models action:search search_query:gpt category:Text`\n" 
            "• `/models action:info model_id:llama-3`"
        ),
        inline=False
    )
    
    # Related commands
    embed.add_field(
        name="Related Commands",
        value=(
            "• `/chat` - Chat with a model after finding its ID\n"
            "• `/server` - Find servers hosting models"
        ),
        inline=False
    )
    
    embed.set_footer(text="Type /models to see all available parameters")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_chat_help_embed() -> discord.Embed:
    """Create help embed for the chat command"""
    embed = discord.Embed(
        title="💬 Chat Command Help",
        description="The `/chat` command lets you interact with AI models.",
        color=discord.Color.blue()
    )
    
    # Basic usage
    embed.add_field(
        name="Basic Usage",
        value=(
            "• `/chat model:llama-3 prompt:Hello, how are you?`\n"
            "• `/chat model:13 prompt:Tell me a joke`\n"
            "• `/chat model:phi prompt:Hello! quickprompt:true`"
        ),
        inline=False
    )
    
    # Parameters explanation
    embed.add_field(
        name="Parameters",
        value=(
            "**model**: Model ID or name to chat with (required)\n"
            "**prompt**: Your message to the AI (required)\n"
            "**system_prompt**: Optional system prompt to guide the AI's behavior\n"
            "**temperature**: Controls randomness (0.0-2.0, default: 0.7)\n"
            "**max_tokens**: Maximum response length (default: 1024)\n"
            "**public**: Make conversation visible to everyone (default: false)\n"
            "**continue_last**: Continue your last conversation with this model\n"
            "**quickprompt**: When true, finds any available model matching this name (like /quickprompt)"
        ),
        inline=False
    )
    
    # Advanced examples
    embed.add_field(
        name="Advanced Examples",
        value=(
            "• `/chat model:gpt-3 prompt:Tell me a story system_prompt:You are a fantasy author`\n"
            "• `/chat model:llama prompt:Explain quantum computing temperature:0.9 max_tokens:2000`\n"
            "• `/chat model:13 prompt:Hello! continue_last:true`\n"
            "• `/chat model:phi-2 prompt:Tell me a joke public:true`\n"
            "• `/chat model:mistral prompt:What's 2+2? quickprompt:true`"
        ),
        inline=False
    )
    
    # Tips
    embed.add_field(
        name="Tips",
        value=(
            "• Use `/models` first to find available models\n"
            "• Higher temperature means more creative but potentially less accurate responses\n"
            "• Use system prompts to guide the AI's persona or behavior\n"
            "• Use continue_last to maintain context in conversations"
        ),
        inline=False
    )
    
    embed.set_footer(text="Type /chat to see all available parameters")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_servers_help_embed() -> discord.Embed:
    """Create help embed for the server command"""
    embed = discord.Embed(
        title="🖥️ Server Command Help",
        description="The `/server` command lets you view and manage AI model servers.",
        color=discord.Color.blue()
    )
    
    # Basic usage
    embed.add_field(
        name="Basic Usage",
        value=(
            "• `/server action:list` - List all verified servers\n"
            "• `/server action:info address:192.168.1.100` - Get details about a server\n"
            "• `/server action:status address:192.168.1.100` - Check server status"
        ),
        inline=False
    )
    
    # Parameters explanation
    embed.add_field(
        name="Parameters",
        value=(
            "**action**: Action to perform (list, info, register, verify, status)\n"
            "**address**: Server IP address (required for specific server actions)\n"
            "**port**: Server port number (default: 11434)\n"
            "**description**: Server description (for registration)"
        ),
        inline=False
    )
    
    # Admin actions
    embed.add_field(
        name="Admin Actions",
        value=(
            "• `/server action:register address:192.168.1.100 description:My test server`\n"
            "• `/server action:verify address:192.168.1.100`"
        ),
        inline=False
    )
    
    # Tips
    embed.add_field(
        name="Tips",
        value=(
            "• Only administrators can register new servers\n"
            "• Use verify action to confirm a server is accessible\n"
            "• The status action shows more technical details about connectivity"
        ),
        inline=False
    )
    
    embed.set_footer(text="Type /server to see all available parameters")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_history_help_embed() -> discord.Embed:
    """Create help embed for the history command"""
    embed = discord.Embed(
        title="📜 History Command Help",
        description="The `/history` command lets you view and manage your chat history.",
        color=discord.Color.blue()
    )
    
    # Basic usage
    embed.add_field(
        name="Basic Usage",
        value=(
            "• `/history action:view` - View your recent chat history\n"
            "• `/history action:view model:llama-3` - View history with a specific model\n"
            "• `/history action:clear` - Clear all your chat history"
        ),
        inline=False
    )
    
    # Parameters explanation
    embed.add_field(
        name="Parameters",
        value=(
            "**action**: Action to perform (view, clear, continue)\n"
            "**history_id**: ID of a specific history entry\n"
            "**model**: Filter by model name or ID\n"
            "**limit**: Maximum number of entries to show (default: 10)\n"
            "**time_period**: Time period to filter (all, today, week, month)"
        ),
        inline=False
    )
    
    # Examples
    embed.add_field(
        name="Examples",
        value=(
            "• `/history action:view limit:20` - View your last 20 conversations\n"
            "• `/history action:view model:13 time_period:week` - View conversations with model ID 13 from the past week\n"
            "• `/history action:clear model:llama-3` - Clear only your history with llama-3"
        ),
        inline=False
    )
    
    # Privacy note
    embed.add_field(
        name="Privacy Note",
        value=(
            "• Only you can see your chat history\n"
            "• Administrators cannot view your private conversations\n"
            "• Clearing history is permanent and cannot be undone"
        ),
        inline=False
    )
    
    embed.set_footer(text="Type /history to see all available parameters")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_admin_help_embed() -> discord.Embed:
    """Create help embed for admin commands"""
    embed = discord.Embed(
        title="⚙️ Admin Commands Help",
        description="These commands are only available to server administrators.",
        color=discord.Color.blue()
    )
    
    # Admin command
    embed.add_field(
        name="/admin Command",
        value=(
            "Administrative functions for managing the bot:\n"
            "• `/admin action:db_info` - Show database information\n"
            "• `/admin action:refresh target:guild` - Refresh bot commands\n"
            "• `/admin action:cleanup force:true` - Clean up database\n"
            "• `/admin action:verify force:true` - Verify all servers\n"
            "• `/admin action:sync target:all force:true` - Sync all models"
        ),
        inline=False
    )
    
    # Manage command
    embed.add_field(
        name="/manage Command",
        value=(
            "Manage models and servers:\n"
            "• `/manage action:add type:server ip:192.168.1.100` - Add a server\n"
            "• `/manage action:add type:model ip:192.168.1.100 model_name:llama-3` - Add a model\n"
            "• `/manage action:delete type:model model_id:42` - Delete a model\n"
            "• `/manage action:sync type:server ip:192.168.1.100` - Sync models on a server"
        ),
        inline=False
    )
    
    # Stats command
    embed.add_field(
        name="/stats Command",
        value=(
            "View statistics and analytics:\n"
            "• `/stats type:models days:30` - View model statistics for last 30 days\n"
            "• `/stats type:servers format:detailed` - View detailed server stats\n"
            "• `/stats type:usage days:7` - View usage statistics for last 7 days"
        ),
        inline=False
    )
    
    # Warning
    embed.add_field(
        name="⚠️ Warning",
        value=(
            "Admin commands can make permanent changes to the bot's configuration and database. "
            "Use them with caution, especially the `force` parameter which bypasses confirmation prompts."
        ),
        inline=False
    )
    
    embed.set_footer(text="These commands require administrator permissions")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed

async def create_examples_help_embed() -> discord.Embed:
    """Create help embed with usage examples"""
    embed = discord.Embed(
        title="📝 Command Examples",
        description="Practical examples for using the bot commands.",
        color=discord.Color.blue()
    )
    
    # Model discovery examples
    embed.add_field(
        name="Discovering Models",
        value=(
            "• `/models action:list category:Chat` - List all chat models\n"
            "• `/models action:search search_query:gpt` - Search for GPT models\n"
            "• `/models action:info model_id:42` - Get details about model ID 42"
        ),
        inline=False
    )
    
    # Chat examples
    embed.add_field(
        name="Chatting with Models",
        value=(
            "• `/chat model:llama-3 prompt:What is machine learning?`\n"
            "• `/chat model:42 prompt:Write a poem about AI system_prompt:You are a poet`\n"
            "• `/chat model:gpt-4 prompt:Tell me a fact temperature:0.5 public:true`"
        ),
        inline=False
    )
    
    # Server management examples
    embed.add_field(
        name="Server Management",
        value=(
            "• `/server action:list` - View all available servers\n"
            "• `/server action:info address:192.168.1.100` - Get server details\n"
            "• `/server action:register address:192.168.1.100 description:Test server` (Admin only)"
        ),
        inline=False
    )
    
    # History examples
    embed.add_field(
        name="Managing History",
        value=(
            "• `/history action:view limit:15` - View last 15 conversations\n"
            "• `/history action:view model:llama` - View history with llama models\n"
            "• `/history action:clear` - Clear all your chat history"
        ),
        inline=False
    )
    
    # Admin examples
    embed.add_field(
        name="Admin Tasks",
        value=(
            "• `/admin action:db_info` - View database statistics\n"
            "• `/manage action:sync type:server ip:192.168.1.100` - Sync models on a server\n"
            "• `/stats type:usage days:30` - View 30-day usage statistics"
        ),
        inline=False
    )
    
    embed.set_footer(text="Use /help with a topic name for more detailed command help")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed 