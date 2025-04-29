import logging
import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_stats_command(bot, safe_defer, safe_followup):
    """Register the stats command with the bot"""
    
    # Define choices for stats types
    stats_types = [
        app_commands.Choice(name="Models", value="models"),
        app_commands.Choice(name="Servers", value="servers"),
        app_commands.Choice(name="Usage", value="usage"),
        app_commands.Choice(name="Users", value="users"),
        app_commands.Choice(name="System", value="system")
    ]
    
    # Define choices for format options
    format_options = [
        app_commands.Choice(name="Summary", value="summary"),
        app_commands.Choice(name="Detailed", value="detailed"),
        app_commands.Choice(name="Chart", value="chart")
    ]
    
    @bot.tree.command(name="stats", description="View statistics and analytics")
    @app_commands.describe(
        type="Type of statistics to view",
        days="Number of days to include in statistics (default: 30)",
        format="Output format for statistics"
    )
    @app_commands.choices(type=stats_types, format=format_options)
    async def stats_command(
        interaction: discord.Interaction,
        type: str,
        days: int = 30,
        format: str = "summary"
    ):
        """Handle viewing statistics and analytics"""
        # Check if user has admin privileges
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
            return
            
        await safe_defer(interaction)
        
        try:
            # Validate parameters
            if days < 1 or days > 365:
                days = 30
                
            # Handle different stat types
            if type == "models":
                await handle_model_stats(interaction, safe_followup, days, format)
            elif type == "servers":
                await handle_server_stats(interaction, safe_followup, days, format)
            elif type == "usage":
                await handle_usage_stats(interaction, safe_followup, days, format)
            elif type == "users":
                await handle_user_stats(interaction, safe_followup, days, format)
            elif type == "system":
                await handle_system_stats(interaction, safe_followup, days, format)
            else:
                error_embed = await format_embed_message(
                    title="Invalid Type",
                    description=f"Statistics type '{type}' is not recognized.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
                
        except Exception as e:
            logger.error(f"Error in stats command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return stats_command

async def handle_model_stats(interaction: discord.Interaction, safe_followup, days: int, format: str):
    """Handle showing model statistics"""
    try:
        # Calculate the date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get model counts by category
        category_query = """
            SELECT 
                category, 
                COUNT(*) as model_count
            FROM models
            GROUP BY category
            ORDER BY model_count DESC
        """
        categories = Database.fetch_all(category_query)
        
        # Get most used models
        usage_query = """
            SELECT 
                m.id, m.name, m.provider, m.category,
                COUNT(ch.id) as usage_count,
                SUM(ch.total_tokens) as tokens_used
            FROM models m
            JOIN chat_history ch ON m.id = ch.model_id
            WHERE ch.created_at >= %s
            GROUP BY m.id, m.name, m.provider, m.category
            ORDER BY usage_count DESC
            LIMIT 10
        """
        top_models = Database.fetch_all(usage_query, (start_date,))
        
        # Get recently added models
        recent_query = """
            SELECT 
                id, name, provider, category, created_at
            FROM models
            WHERE created_at >= %s
            ORDER BY created_at DESC
            LIMIT 10
        """
        recent_models = Database.fetch_all(recent_query, (start_date,))
        
        # Get total counts
        counts_query = """
            SELECT 
                (SELECT COUNT(*) FROM models) as total_models,
                (SELECT COUNT(DISTINCT provider) FROM models) as total_providers,
                (SELECT COUNT(*) FROM models WHERE created_at >= %s) as new_models,
                (SELECT COUNT(*) FROM models WHERE is_available = TRUE) as available_models
        """
        counts = Database.fetch_one(counts_query, (start_date,))
        total_models, total_providers, new_models, available_models = counts if counts else (0, 0, 0, 0)
        
        # Create embed for model statistics
        stats_embed = discord.Embed(
            title="Model Statistics",
            description=f"Showing statistics for the past {days} days",
            color=discord.Color.blue()
        )
        
        # Add overview section
        stats_embed.add_field(
            name="Overview",
            value=(
                f"**Total Models**: {total_models:,}\n"
                f"**Available Models**: {available_models:,}\n"
                f"**Providers**: {total_providers:,}\n"
                f"**New Models**: {new_models:,} in the past {days} days"
            ),
            inline=False
        )
        
        # Add category breakdown if we have data
        if categories and len(categories) > 0:
            category_text = []
            for category, count in categories:
                if category:  # Skip empty categories
                    category_text.append(f"**{category}**: {count:,} models")
            
            if category_text:
                stats_embed.add_field(
                    name="Categories",
                    value="\n".join(category_text),
                    inline=False
                )
        
        # Add top models by usage if we have data
        if top_models and len(top_models) > 0:
            models_text = []
            for id, name, provider, category, usage_count, tokens_used in top_models:
                tokens_display = f", {tokens_used:,} tokens" if tokens_used else ""
                models_text.append(f"**{name}** ({provider}): {usage_count:,} uses{tokens_display}")
            
            if models_text:
                stats_embed.add_field(
                    name="Most Used Models",
                    value="\n".join(models_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add recent models if we have data and format is detailed
        if format == "detailed" and recent_models and len(recent_models) > 0:
            recent_text = []
            for id, name, provider, category, created_at in recent_models:
                date_str = created_at.strftime("%Y-%m-%d") if created_at else "Unknown"
                recent_text.append(f"**{name}** ({provider}): Added on {date_str}")
            
            if recent_text:
                stats_embed.add_field(
                    name="Recently Added Models",
                    value="\n".join(recent_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add footer
        stats_embed.set_footer(
            text=f"Use /models to explore the available models • Data as of {end_date.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting model stats: {str(e)}")
        raise

async def handle_server_stats(interaction: discord.Interaction, safe_followup, days: int, format: str):
    """Handle showing server statistics"""
    try:
        # Calculate the date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get server counts
        counts_query = """
            SELECT 
                COUNT(*) as total_servers,
                SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) as verified_servers,
                SUM(CASE WHEN is_honeypot = TRUE THEN 1 ELSE 0 END) as honeypot_servers,
                SUM(CASE WHEN scan_date >= %s THEN 1 ELSE 0 END) as recently_scanned
            FROM endpoints
        """
        counts = Database.fetch_one(counts_query, (start_date,))
        total_servers, verified_servers, honeypot_servers, recently_scanned = counts if counts else (0, 0, 0, 0)
        
        # Get most active servers (by number of models)
        active_query = """
            SELECT 
                e.id, e.ip, e.port, e.description,
                COUNT(m.id) as model_count,
                (SELECT COUNT(*) FROM chat_history ch JOIN models m2 ON ch.model_id = m2.id WHERE m2.endpoint_id = e.id AND ch.created_at >= %s) as usage_count,
                e.scan_date, ve.verification_date
            FROM endpoints e
            LEFT JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            LEFT JOIN models m ON e.id = m.endpoint_id
            WHERE e.verified = 1 AND e.is_honeypot = FALSE
            GROUP BY e.id, e.ip, e.port, e.description, e.scan_date, ve.verification_date
            ORDER BY model_count DESC, usage_count DESC
            LIMIT 10
        """
        active_servers = Database.fetch_all(active_query, (start_date,))
        
        # Get recently verified servers
        recent_query = """
            SELECT 
                e.id, e.ip, e.port, e.description, ve.verification_date, 
                COUNT(m.id) as model_count
            FROM endpoints e
            JOIN verified_endpoints ve ON e.id = ve.endpoint_id
            LEFT JOIN models m ON e.id = m.endpoint_id
            WHERE ve.verification_date >= %s
            GROUP BY e.id, e.ip, e.port, e.description, ve.verification_date
            ORDER BY ve.verification_date DESC
            LIMIT 10
        """
        recent_servers = Database.fetch_all(recent_query, (start_date,))
        
        # Create embed for server statistics
        stats_embed = discord.Embed(
            title="Server Statistics",
            description=f"Showing statistics for the past {days} days",
            color=discord.Color.blue()
        )
        
        # Add overview section
        stats_embed.add_field(
            name="Overview",
            value=(
                f"**Total Servers**: {total_servers:,}\n"
                f"**Verified Servers**: {verified_servers:,}\n"
                f"**Honeypot Servers**: {honeypot_servers:,}\n"
                f"**Recently Scanned**: {recently_scanned:,} in the past {days} days"
            ),
            inline=False
        )
        
        # Add active servers if we have data
        if active_servers and len(active_servers) > 0:
            servers_text = []
            for id, ip, port, description, model_count, usage_count, scan_date, verification_date in active_servers:
                server_name = f"{ip}:{port}"
                if description:
                    server_name = f"{description} ({server_name})"
                servers_text.append(f"**{server_name}**: {model_count:,} models, {usage_count:,} uses")
            
            if servers_text:
                stats_embed.add_field(
                    name="Most Active Servers",
                    value="\n".join(servers_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add recent servers if we have data and format is detailed
        if format == "detailed" and recent_servers and len(recent_servers) > 0:
            recent_text = []
            for id, ip, port, description, verification_date, model_count in recent_servers:
                server_name = f"{ip}:{port}"
                if description:
                    server_name = f"{description} ({server_name})"
                date_str = verification_date.strftime("%Y-%m-%d") if verification_date else "Unknown"
                recent_text.append(f"**{server_name}**: Verified on {date_str}, {model_count:,} models")
            
            if recent_text:
                stats_embed.add_field(
                    name="Recently Verified Servers",
                    value="\n".join(recent_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add footer
        stats_embed.set_footer(
            text=f"Use /server to explore the available servers • Data as of {end_date.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting server stats: {str(e)}")
        raise

async def handle_usage_stats(interaction: discord.Interaction, safe_followup, days: int, format: str):
    """Handle showing usage statistics"""
    try:
        # Calculate the date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get overall usage counts
        counts_query = """
            SELECT 
                COUNT(*) as total_conversations,
                COUNT(DISTINCT user_id) as total_users,
                COUNT(DISTINCT model_id) as models_used,
                SUM(prompt_tokens) as prompt_tokens,
                SUM(completion_tokens) as completion_tokens,
                SUM(total_tokens) as total_tokens
            FROM chat_history
            WHERE created_at >= %s
        """
        counts = Database.fetch_one(counts_query, (start_date,))
        total_conversations, total_users, models_used, prompt_tokens, completion_tokens, total_tokens = counts if counts else (0, 0, 0, 0, 0, 0)
        
        # Get daily usage statistics if detailed format
        daily_stats = None
        if format == "detailed":
            daily_query = """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as conversation_count,
                    COUNT(DISTINCT user_id) as user_count,
                    SUM(total_tokens) as tokens
                FROM chat_history
                WHERE created_at >= %s
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 7
            """
            daily_stats = Database.fetch_all(daily_query, (start_date,))
        
        # Get usage by model category
        category_query = """
            SELECT 
                m.category,
                COUNT(ch.id) as chat_count,
                SUM(ch.total_tokens) as tokens
            FROM chat_history ch
            JOIN models m ON ch.model_id = m.id
            WHERE ch.created_at >= %s
            GROUP BY m.category
            ORDER BY chat_count DESC
        """
        category_stats = Database.fetch_all(category_query, (start_date,))
        
        # Create embed for usage statistics
        stats_embed = discord.Embed(
            title="Usage Statistics",
            description=f"Showing statistics for the past {days} days",
            color=discord.Color.blue()
        )
        
        # Add overview section
        stats_embed.add_field(
            name="Overview",
            value=(
                f"**Total Conversations**: {total_conversations:,}\n"
                f"**Active Users**: {total_users:,}\n"
                f"**Models Used**: {models_used:,} different models\n"
                f"**Total Tokens**: {total_tokens:,}\n"
                f"**Prompt Tokens**: {prompt_tokens:,}\n"
                f"**Completion Tokens**: {completion_tokens:,}"
            ),
            inline=False
        )
        
        # Add category breakdown if we have data
        if category_stats and len(category_stats) > 0:
            category_text = []
            for category, chat_count, tokens in category_stats:
                if category:  # Skip empty categories
                    category_text.append(f"**{category}**: {chat_count:,} chats, {tokens:,} tokens")
            
            if category_text:
                stats_embed.add_field(
                    name="Usage by Model Category",
                    value="\n".join(category_text),
                    inline=False
                )
        
        # Add daily statistics if available
        if daily_stats and len(daily_stats) > 0:
            daily_text = []
            for date, count, users, tokens in daily_stats:
                date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
                daily_text.append(f"**{date_str}**: {count:,} chats, {users:,} users, {tokens:,} tokens")
            
            if daily_text:
                stats_embed.add_field(
                    name="Daily Usage (Last 7 Days)",
                    value="\n".join(daily_text),
                    inline=False
                )
        
        # Add footer
        stats_embed.set_footer(
            text=f"Use /models to discover AI models • Data as of {end_date.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting usage stats: {str(e)}")
        raise

async def handle_user_stats(interaction: discord.Interaction, safe_followup, days: int, format: str):
    """Handle showing user statistics"""
    try:
        # Calculate the date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get user counts
        counts_query = """
            SELECT 
                COUNT(DISTINCT user_id) as total_users,
                COUNT(DISTINCT CASE WHEN created_at >= %s THEN user_id ELSE NULL END) as active_users
            FROM chat_history
        """
        counts = Database.fetch_one(counts_query, (start_date,))
        total_users, active_users = counts if counts else (0, 0)
        
        # Get most active users by conversation count
        active_query = """
            SELECT 
                user_id,
                COUNT(*) as chat_count,
                COUNT(DISTINCT model_id) as models_used,
                SUM(total_tokens) as tokens_used,
                MAX(created_at) as last_activity
            FROM chat_history
            WHERE created_at >= %s
            GROUP BY user_id
            ORDER BY chat_count DESC
            LIMIT 10
        """
        active_users_data = Database.fetch_all(active_query, (start_date,))
        
        # Get new users
        new_query = """
            SELECT 
                user_id,
                MIN(created_at) as first_chat,
                COUNT(*) as chat_count
            FROM chat_history
            WHERE created_at >= %s
            GROUP BY user_id
            HAVING MIN(created_at) >= %s
            ORDER BY first_chat DESC
            LIMIT 10
        """
        new_users = Database.fetch_all(new_query, (start_date, start_date))
        
        # Create embed for user statistics
        stats_embed = discord.Embed(
            title="User Statistics",
            description=f"Showing statistics for the past {days} days",
            color=discord.Color.blue()
        )
        
        # Add overview section
        stats_embed.add_field(
            name="Overview",
            value=(
                f"**Total Users**: {total_users:,}\n"
                f"**Active Users**: {active_users:,} in the past {days} days\n"
                f"**New Users**: {len(new_users):,} in the past {days} days"
            ),
            inline=False
        )
        
        # Add most active users (anonymized)
        if active_users_data and len(active_users_data) > 0:
            users_text = []
            for i, (user_id, chat_count, models_used, tokens_used, last_activity) in enumerate(active_users_data, 1):
                last_active = last_activity.strftime("%Y-%m-%d") if last_activity else "Unknown"
                users_text.append(
                    f"**User {i}**: {chat_count:,} chats, {models_used:,} models, " +
                    f"{tokens_used:,} tokens, Last active: {last_active}"
                )
            
            if users_text:
                stats_embed.add_field(
                    name="Most Active Users (Anonymized)",
                    value="\n".join(users_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add new users if detailed format
        if format == "detailed" and new_users and len(new_users) > 0:
            new_text = []
            for i, (user_id, first_chat, chat_count) in enumerate(new_users, 1):
                joined = first_chat.strftime("%Y-%m-%d") if first_chat else "Unknown"
                new_text.append(f"**User {i}**: Joined {joined}, {chat_count:,} chats")
            
            if new_text:
                stats_embed.add_field(
                    name="New Users (Anonymized)",
                    value="\n".join(new_text[:5]),  # Show top 5
                    inline=False
                )
        
        # Add privacy note
        stats_embed.add_field(
            name="Privacy Note",
            value=(
                "All user statistics are anonymized. User IDs are not displayed or shared. "
                "This data is only used for aggregate analytics."
            ),
            inline=False
        )
        
        # Add footer
        stats_embed.set_footer(
            text=f"Data as of {end_date.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise

async def handle_system_stats(interaction: discord.Interaction, safe_followup, days: int, format: str):
    """Handle showing system statistics"""
    try:
        # Create embed for system statistics
        stats_embed = discord.Embed(
            title="System Statistics",
            description="General system and database information",
            color=discord.Color.blue()
        )
        
        # Get database statistics
        tables = [
            "models", "endpoints", "verified_endpoints", "chat_history", "servers"
        ]
        
        db_stats = []
        for table in tables:
            try:
                count_query = f"SELECT COUNT(*) FROM {table}"
                result = Database.fetch_one(count_query)
                if result:
                    count = result[0]
                    db_stats.append(f"**{table}**: {count:,} rows")
            except Exception as e:
                db_stats.append(f"**{table}**: Error - {str(e)}")
        
        if db_stats:
            stats_embed.add_field(
                name="Database Tables",
                value="\n".join(db_stats),
                inline=False
            )
        
        # Get bot uptime and version info (placeholder - would be implemented with actual bot info)
        stats_embed.add_field(
            name="Bot Information",
            value=(
                "**Version**: 1.0.0\n"
                "**Commands**: 8 user-facing commands\n"
                "**Framework**: discord.py\n"
                "**Database**: PostgreSQL"
            ),
            inline=False
        )
        
        # Get available server connections
        endpoint_query = """
            SELECT 
                SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) as verified_count,
                SUM(CASE WHEN verified = 0 THEN 1 ELSE 0 END) as unverified_count,
                SUM(CASE WHEN is_honeypot = TRUE THEN 1 ELSE 0 END) as honeypot_count
            FROM endpoints
        """
        endpoint_stats = Database.fetch_one(endpoint_query)
        verified_count, unverified_count, honeypot_count = endpoint_stats if endpoint_stats else (0, 0, 0)
        
        stats_embed.add_field(
            name="Endpoint Statistics",
            value=(
                f"**Verified**: {verified_count:,}\n"
                f"**Unverified**: {unverified_count:,}\n"
                f"**Honeypots**: {honeypot_count:,}"
            ),
            inline=False
        )
        
        # Add model statistics
        model_query = """
            SELECT COUNT(DISTINCT name) FROM models
        """
        distinct_models = Database.fetch_one(model_query)
        distinct_count = distinct_models[0] if distinct_models else 0
        
        stats_embed.add_field(
            name="Model Statistics",
            value=f"**Distinct Models**: {distinct_count:,}",
            inline=True
        )
        
        # Add timestamp
        stats_embed.set_footer(
            text=f"System stats as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        await safe_followup(interaction, embed=stats_embed)
    
    except Exception as e:
        logger.error(f"Error getting system stats: {str(e)}")
        raise 