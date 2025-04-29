import logging
import discord
from discord import app_commands
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_history_command(bot, safe_defer, safe_followup):
    """Register the history command with the bot"""
    
    # Define choices for history actions
    history_actions = [
        app_commands.Choice(name="View History", value="view"),
        app_commands.Choice(name="View Specific Entry", value="view_entry"),
        app_commands.Choice(name="Delete Entry", value="delete"),
        app_commands.Choice(name="Clear History", value="clear"),
        app_commands.Choice(name="View Stats", value="stats")
    ]
    
    # Define choices for time periods
    time_periods = [
        app_commands.Choice(name="All Time", value="all"),
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="This Week", value="week"),
        app_commands.Choice(name="This Month", value="month")
    ]
    
    @bot.tree.command(name="history", description="View and manage your chat history")
    @app_commands.describe(
        action="Action to perform with your chat history",
        history_id="ID of the specific chat history entry (for view/delete actions)",
        model="Filter by model name or ID",
        limit="Maximum number of entries to return (default: 10)",
        time_period="Time period to filter history"
    )
    @app_commands.choices(action=history_actions, time_period=time_periods)
    async def history_command(
        interaction: discord.Interaction,
        action: str,
        history_id: int = None,
        model: str = None,
        limit: int = 10,
        time_period: str = "all"
    ):
        """Handle viewing and managing chat history"""
        await safe_defer(interaction, ephemeral=True)  # Always make history private
        
        try:
            # Validate parameters
            if action in ["view_entry", "delete"] and not history_id:
                error_embed = await format_embed_message(
                    title="Missing Parameters",
                    description=f"History ID is required for the {action} action.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                return
                
            if limit < 1 or limit > 50:
                limit = 10
            
            # Handle different actions
            if action == "view":
                await handle_list_history(interaction, safe_followup, model, limit, time_period)
            elif action == "view_entry":
                await handle_view_history(interaction, safe_followup, history_id)
            elif action == "delete":
                await handle_delete_history(interaction, safe_followup, history_id)
            elif action == "clear":
                await handle_clear_history(interaction, safe_followup, model, time_period)
            elif action == "stats":
                await handle_history_stats(interaction, safe_followup, time_period)
            else:
                error_embed = await format_embed_message(
                    title="Invalid Action",
                    description=f"Action '{action}' is not recognized.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                
        except Exception as e:
            logger.error(f"Error in history command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return history_command

async def handle_list_history(
    interaction: discord.Interaction, 
    safe_followup, 
    model: Optional[str] = None, 
    limit: int = 10, 
    time_period: str = "all"
):
    """Handle listing chat history entries"""
    try:
        user_id = interaction.user.id
        
        # Prepare query
        query_parts = [
            """
            SELECT 
                ch.id, ch.conversation_id, ch.model_id, m.name as model_name, 
                ch.prompt, ch.response, ch.created_at, ch.system_prompt,
                ch.prompt_tokens, ch.completion_tokens, ch.total_tokens
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            WHERE ch.user_id = %s
            """
        ]
        
        params = [user_id]
        
        # Add time filter if specified
        time_filter, time_desc = get_time_filter(time_period)
        if time_filter:
            query_parts.append(time_filter)
            
        # Add model filter if specified
        if model:
            if model.isdigit():
                # Filter by model ID
                query_parts.append("AND ch.model_id = %s")
                params.append(int(model))
            else:
                # Filter by model name
                query_parts.append("AND m.name LIKE %s")
                params.append(f"%{model}%")
        
        # Add order and limit
        query_parts.append("ORDER BY ch.created_at DESC")
        query_parts.append("LIMIT %s")
        params.append(limit)
        
        # Execute query
        query = " ".join(query_parts)
        history = Database.fetch_all(query, tuple(params))
        
        if not history or len(history) == 0:
            no_history_embed = await format_embed_message(
                title="No Chat History",
                description="You don't have any chat history matching these criteria.",
                color=discord.Color.blue()
            )
            await safe_followup(interaction, embed=no_history_embed)
            return
            
        # Create embed for history
        period_name = get_time_period_name(time_period)
        history_embed = discord.Embed(
            title=f"Your Chat History - {period_name}",
            description=f"Showing {len(history)} recent conversations",
            color=discord.Color.blue()
        )
        
        # Add entries to embed
        for entry in history:
            entry_id, conversation_id, model_id, model_name, prompt, response, created_at, system_prompt, prompt_tokens, completion_tokens, total_tokens = entry
            
            # Truncate prompt and response for display
            short_prompt = prompt[:100] + "..." if len(prompt) > 100 else prompt
            short_response = response[:100] + "..." if len(response) > 100 else response
            
            # Format date
            date_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown"
            
            # Create field for entry
            field_name = f"Chat {entry_id} with {model_name} ({date_str})"
            
            field_value = [
                f"**Prompt**: {short_prompt}",
                f"**Response**: {short_response}"
            ]
            
            if total_tokens:
                field_value.append(f"**Tokens**: {total_tokens}")
                
            field_value.append(f"Use `/history action:view_entry history_id:{entry_id}` for full conversation")
            
            history_embed.add_field(
                name=field_name,
                value="\n".join(field_value),
                inline=False
            )
        
        # Add footer with additional info
        history_embed.set_footer(
            text=f"Use /history with different filters to see more • All times are in UTC"
        )
        history_embed.timestamp = datetime.now(timezone.utc)
        
        await safe_followup(interaction, embed=history_embed)
    
    except Exception as e:
        logger.error(f"Error listing history: {str(e)}")
        raise

async def handle_view_history(interaction: discord.Interaction, safe_followup, history_id: int):
    """Handle viewing a specific history entry"""
    try:
        user_id = interaction.user.id
        
        # Fetch the specific history entry
        query = """
            SELECT 
                ch.id, ch.conversation_id, ch.model_id, m.name as model_name, m.provider,
                ch.prompt, ch.response, ch.system_prompt, ch.created_at,
                ch.prompt_tokens, ch.completion_tokens, ch.total_tokens,
                ch.parameters
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            WHERE ch.id = %s AND ch.user_id = %s
        """
        
        entry = Database.fetch_one(query, (history_id, user_id))
        
        if not entry:
            not_found_embed = await format_embed_message(
                title="Entry Not Found",
                description=f"Could not find chat history entry with ID {history_id} in your history.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        # Unpack entry data
        entry_id, conversation_id, model_id, model_name, provider, prompt, response, system_prompt, created_at, prompt_tokens, completion_tokens, total_tokens, parameters = entry
        
        # Create embed for the history entry
        entry_embed = discord.Embed(
            title=f"Chat with {model_name}",
            description=f"Conversation ID: {conversation_id}",
            color=discord.Color.blue()
        )
        
        # Add prompt
        entry_embed.add_field(
            name="Your Prompt:",
            value=prompt[:1024] if len(prompt) <= 1024 else prompt[:1021] + "...",
            inline=False
        )
        
        # Add response (split if needed)
        if len(response) <= 1024:
            entry_embed.add_field(
                name="AI Response:",
                value=response,
                inline=False
            )
        else:
            # Split response into chunks
            chunks = [response[i:i+1024] for i in range(0, len(response), 1024)]
            entry_embed.add_field(
                name="AI Response:",
                value=chunks[0],
                inline=False
            )
            
            for i, chunk in enumerate(chunks[1:], 1):
                entry_embed.add_field(
                    name=f"AI Response (continued {i}):",
                    value=chunk,
                    inline=False
                )
        
        # Add system prompt if available
        if system_prompt:
            entry_embed.add_field(
                name="System Prompt Used:",
                value=system_prompt[:1024] if len(system_prompt) <= 1024 else system_prompt[:1021] + "...",
                inline=False
            )
        
        # Add model info
        entry_embed.add_field(
            name="Model Info:",
            value=f"{model_name} (ID: {model_id}) by {provider}",
            inline=True
        )
        
        # Add token usage
        if total_tokens:
            token_info = []
            if prompt_tokens:
                token_info.append(f"Prompt: {prompt_tokens}")
            if completion_tokens:
                token_info.append(f"Completion: {completion_tokens}")
            token_info.append(f"Total: {total_tokens}")
            
            entry_embed.add_field(
                name="Token Usage:",
                value=" | ".join(token_info),
                inline=True
            )
        
        # Add timestamp
        entry_embed.add_field(
            name="Timestamp:",
            value=created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if created_at else "Unknown",
            inline=True
        )
        
        # Add footer with options
        entry_embed.set_footer(
            text=f"ID: {entry_id} • Use /history action:delete history_id:{entry_id} to delete this entry"
        )
        
        await safe_followup(interaction, embed=entry_embed)
    
    except Exception as e:
        logger.error(f"Error viewing history entry: {str(e)}")
        raise

async def handle_delete_history(interaction: discord.Interaction, safe_followup, history_id: int):
    """Handle deleting a specific history entry"""
    try:
        user_id = interaction.user.id
        
        # Verify the entry exists and belongs to the user
        check_query = """
            SELECT id, conversation_id
            FROM chat_history
            WHERE id = %s AND user_id = %s
        """
        
        entry = Database.fetch_one(check_query, (history_id, user_id))
        
        if not entry:
            not_found_embed = await format_embed_message(
                title="Entry Not Found",
                description=f"Could not find chat history entry with ID {history_id} in your history.",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        # Delete the entry
        delete_query = """
            DELETE FROM chat_history
            WHERE id = %s AND user_id = %s
        """
        
        Database.execute(delete_query, (history_id, user_id))
        
        # Success message
        success_embed = await format_embed_message(
            title="Entry Deleted",
            description=f"Successfully deleted chat history entry with ID {history_id}.",
            color=discord.Color.green()
        )
        
        await safe_followup(interaction, embed=success_embed)
    
    except Exception as e:
        logger.error(f"Error deleting history entry: {str(e)}")
        raise

async def handle_clear_history(
    interaction: discord.Interaction, 
    safe_followup, 
    model: Optional[str] = None,
    time_period: str = "all"
):
    """Handle clearing chat history"""
    try:
        user_id = interaction.user.id
        
        # Prepare base query
        query_parts = [
            "DELETE FROM chat_history WHERE user_id = %s"
        ]
        
        params = [user_id]
        
        # Add time filter if specified
        time_filter, time_desc = get_time_filter(time_period)
        if time_filter:
            # Remove "WHERE" from time_filter since we already have one
            modified_time_filter = time_filter.replace("WHERE", "AND")
            query_parts.append(modified_time_filter)
            
        # Add model filter if specified
        if model:
            if model.isdigit():
                # Filter by model ID
                query_parts.append("AND model_id = %s")
                params.append(int(model))
            else:
                # Filter by model name
                query_parts.append("AND model_id IN (SELECT id FROM models WHERE name LIKE %s)")
                params.append(f"%{model}%")
        
        # Execute delete
        query = " ".join(query_parts)
        Database.execute(query, tuple(params))
        
        # Create success message
        title = "History Cleared"
        description_parts = ["Successfully cleared your chat history"]
        
        if model:
            description_parts.append(f"with model '{model}'")
            
        description_parts.append(time_desc)
        
        success_embed = await format_embed_message(
            title=title,
            description=" ".join(description_parts) + ".",
            color=discord.Color.green()
        )
        
        await safe_followup(interaction, embed=success_embed)
    
    except Exception as e:
        logger.error(f"Error clearing history: {str(e)}")
        raise

async def handle_history_stats(interaction: discord.Interaction, safe_followup, time_period: str = "all"):
    """Handle viewing statistics about chat history"""
    try:
        user_id = interaction.user.id
        
        # Get time filter
        time_filter, time_desc = get_time_filter(time_period)
        period_name = get_time_period_name(time_period)
        
        # Base query part
        base_filter = f"WHERE user_id = %s {time_filter.replace('WHERE', 'AND') if time_filter else ''}"
        params = [user_id]
        
        # Fetch total conversations
        count_query = f"""
            SELECT COUNT(*) FROM chat_history
            {base_filter}
        """
        total_count = Database.fetch_one(count_query, tuple(params))
        total_count = total_count[0] if total_count else 0
        
        # Fetch tokens used
        tokens_query = f"""
            SELECT 
                SUM(prompt_tokens) as total_prompt,
                SUM(completion_tokens) as total_completion,
                SUM(total_tokens) as grand_total
            FROM chat_history
            {base_filter}
        """
        tokens = Database.fetch_one(tokens_query, tuple(params))
        prompt_tokens, completion_tokens, total_tokens = tokens if tokens else (0, 0, 0)
        
        # Fetch top models
        models_query = f"""
            SELECT 
                m.id, m.name,
                COUNT(*) as chat_count,
                SUM(ch.total_tokens) as tokens_used
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            {base_filter}
            GROUP BY m.id, m.name
            ORDER BY chat_count DESC
            LIMIT 5
        """
        top_models = Database.fetch_all(models_query, tuple(params))
        
        # Fetch conversation length stats
        length_query = f"""
            SELECT 
                AVG(LENGTH(prompt)) as avg_prompt_length,
                AVG(LENGTH(response)) as avg_response_length,
                MAX(LENGTH(response)) as max_response_length
            FROM chat_history
            {base_filter}
        """
        length_stats = Database.fetch_one(length_query, tuple(params))
        avg_prompt_len, avg_response_len, max_response_len = length_stats if length_stats else (0, 0, 0)
        
        # Create stats embed
        stats_embed = discord.Embed(
            title=f"Your Chat History Stats - {period_name}",
            description=f"Statistics for your conversations {time_desc.lower()}",
            color=discord.Color.blue()
        )
        
        # Add basic stats
        stats_embed.add_field(
            name="Overview",
            value=(
                f"**Total Conversations**: {total_count:,}\n"
                f"**Total Tokens Used**: {total_tokens or 0:,}\n"
                f"**Prompt Tokens**: {prompt_tokens or 0:,}\n"
                f"**Completion Tokens**: {completion_tokens or 0:,}"
            ),
            inline=False
        )
        
        # Add conversation length stats
        stats_embed.add_field(
            name="Conversation Stats",
            value=(
                f"**Average Prompt Length**: {int(avg_prompt_len or 0):,} characters\n"
                f"**Average Response Length**: {int(avg_response_len or 0):,} characters\n"
                f"**Longest Response**: {int(max_response_len or 0):,} characters"
            ),
            inline=False
        )
        
        # Add top models
        if top_models and len(top_models) > 0:
            models_text = []
            for model_id, model_name, chat_count, tokens_used in top_models:
                tokens_used = tokens_used or 0
                models_text.append(f"**{model_name}**: {chat_count:,} chats, {tokens_used:,} tokens")
                
            stats_embed.add_field(
                name="Top Models Used",
                value="\n".join(models_text) if models_text else "No model data available",
                inline=False
            )
        
        # Add footer
        stats_embed.set_footer(
            text="Use /history to view and manage your chat history"
        )
        stats_embed.timestamp = datetime.now(timezone.utc)
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting history stats: {str(e)}")
        raise

def get_time_filter(time_period: str) -> tuple:
    """Get SQL filter for time period and a description"""
    now = datetime.now(timezone.utc)
    
    if time_period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return f"WHERE created_at >= '{start.isoformat()}'", "From Today"
    elif time_period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return f"WHERE created_at >= '{start.isoformat()}'", "From This Week"
    elif time_period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return f"WHERE created_at >= '{start.isoformat()}'", "From This Month"
    else:  # "all"
        return "", "From All Time"

def get_time_period_name(time_period: str) -> str:
    """Get a user-friendly name for the time period"""
    if time_period == "today":
        return "Today"
    elif time_period == "week":
        return "This Week"
    elif time_period == "month":
        return "This Month"
    else:  # "all"
        return "All Time" 