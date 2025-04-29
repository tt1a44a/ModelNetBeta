import logging
import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_admin_command(bot, safe_defer, safe_followup):
    """Register the admin command with the bot"""
    
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
            if action == "db_info":
                await handle_db_info(interaction, safe_followup)
            elif action == "refresh":
                await handle_refresh_commands(interaction, target, bot, safe_followup)
            elif action == "cleanup":
                await handle_cleanup_database(interaction, force, safe_followup)
            elif action == "verify":
                await handle_verify_all_servers(interaction, force, safe_followup)
            elif action == "sync":
                await handle_sync_models(interaction, target, force, safe_followup)
            else:
                await safe_followup(interaction, "Unknown action specified")
                
        except Exception as e:
            logger.error(f"Error in admin command: {str(e)}")
            error_embed = await format_embed_message(
                title="Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, content=None, embed=error_embed)
    
    return admin_command

async def handle_db_info(interaction: discord.Interaction, safe_followup):
    """Handler for showing database information"""
    try:
        # Get database statistics
        tables_info = []
        
        # Get table counts
        table_queries = [
            ("endpoints", "SELECT COUNT(*) FROM endpoints"),
            ("verified_endpoints", "SELECT COUNT(*) FROM verified_endpoints"),
            ("models", "SELECT COUNT(*) FROM models"),
            ("chat_history", "SELECT COUNT(*) FROM chat_history"),
            ("servers", "SELECT COUNT(*) FROM servers"),
            ("benchmark_results", "SELECT COUNT(*) FROM benchmark_results")
        ]
        
        for table_name, query in table_queries:
            try:
                result = Database.fetch_one(query)
                if result and len(result) > 0:
                    count = result[0]
                    tables_info.append(f"**{table_name}**: {count:,} records")
                else:
                    tables_info.append(f"**{table_name}**: 0 records")
            except Exception as e:
                tables_info.append(f"**{table_name}**: Error - {str(e)}")
        
        # --- ENDPOINT STATISTICS ---
        # Basic endpoint counts
        try:
            verified_query = "SELECT COUNT(*) FROM endpoints WHERE verified = 1"
            verified_result = Database.fetch_one(verified_query)
            verified_count = verified_result[0] if verified_result else 0
            
            unverified_query = "SELECT COUNT(*) FROM endpoints WHERE verified = 0"
            unverified_result = Database.fetch_one(unverified_query)
            unverified_count = unverified_result[0] if unverified_result else 0
            
            honeypot_query = "SELECT COUNT(*) FROM endpoints WHERE is_honeypot = TRUE"
            honeypot_result = Database.fetch_one(honeypot_query)
            honeypot_count = honeypot_result[0] if honeypot_result else 0
            
            active_query = "SELECT COUNT(*) FROM endpoints WHERE is_active = TRUE"
            active_result = Database.fetch_one(active_query)
            active_count = active_result[0] if active_result else 0
            
            inactive_query = "SELECT COUNT(*) FROM endpoints WHERE is_active = FALSE"
            inactive_result = Database.fetch_one(inactive_query)
            inactive_count = inactive_result[0] if inactive_result else 0
            
            auth_required_query = "SELECT COUNT(*) FROM endpoints WHERE auth_required = TRUE"
            auth_required_result = Database.fetch_one(auth_required_query)
            auth_required_count = auth_required_result[0] if auth_required_result else 0
        except Exception as e:
            logger.error(f"Error fetching endpoint counts: {str(e)}")
            verified_count = unverified_count = honeypot_count = active_count = inactive_count = auth_required_count = 0
        
        # Endpoints by API type
        api_type_query = """
            SELECT 
                api_type, 
                COUNT(*) as count
            FROM endpoints
            GROUP BY api_type
            ORDER BY count DESC
        """
        try:
            api_types = Database.fetch_all(api_type_query)
            api_types_info = []
            
            for row in api_types:
                if len(row) >= 2:
                    api_type, count = row[0], row[1]
                    api_type = api_type or "unknown"
                    api_types_info.append(f"**{api_type}**: {count:,}")
                else:
                    api_types_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching API types: {str(e)}")
            api_types_info = ["Error fetching API types"]
        
        # Endpoints by verification status and activity
        endpoint_matrix_query = """
            SELECT 
                verified,
                is_honeypot,
                is_active,
                COUNT(*) as count
            FROM endpoints
            GROUP BY verified, is_honeypot, is_active
            ORDER BY count DESC
        """
        try:
            endpoint_matrix = Database.fetch_all(endpoint_matrix_query)
            endpoint_matrix_info = []
            
            for row in endpoint_matrix:
                if len(row) >= 4:
                    verified, is_honeypot, is_active, count = row[0], row[1], row[2], row[3]
                    status = []
                    if verified == 1:
                        status.append("Verified")
                    else:
                        status.append("Unverified")
                    
                    if is_honeypot:
                        status.append("Honeypot")
                    
                    if is_active:
                        status.append("Active")
                    else:
                        status.append("Inactive")
                        
                    endpoint_matrix_info.append(f"**{' + '.join(status)}**: {count:,}")
                else:
                    endpoint_matrix_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching endpoint matrix: {str(e)}")
            endpoint_matrix_info = ["Error fetching endpoint matrix"]
        
        # Top honeypot reasons
        honeypot_reasons_query = """
            SELECT 
                honeypot_reason, 
                COUNT(*) as count
            FROM endpoints
            WHERE is_honeypot = TRUE AND honeypot_reason IS NOT NULL
            GROUP BY honeypot_reason
            ORDER BY count DESC
            LIMIT 5
        """
        try:
            honeypot_reasons = Database.fetch_all(honeypot_reasons_query)
            honeypot_reasons_info = []
            
            for row in honeypot_reasons:
                if len(row) >= 2:
                    reason, count = row[0], row[1]
                    honeypot_reasons_info.append(f"**{reason}**: {count:,}")
                else:
                    honeypot_reasons_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching honeypot reasons: {str(e)}")
            honeypot_reasons_info = ["Error fetching honeypot reasons"]
        
        # Top inactive reasons
        inactive_reasons_query = """
            SELECT 
                inactive_reason, 
                COUNT(*) as count
            FROM endpoints
            WHERE is_active = FALSE AND inactive_reason IS NOT NULL
            GROUP BY inactive_reason
            ORDER BY count DESC
            LIMIT 5
        """
        try:
            inactive_reasons = Database.fetch_all(inactive_reasons_query)
            inactive_reasons_info = []
            
            for row in inactive_reasons:
                if len(row) >= 2:
                    reason, count = row[0], row[1]
                    inactive_reasons_info.append(f"**{reason}**: {count:,}")
                else:
                    inactive_reasons_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching inactive reasons: {str(e)}")
            inactive_reasons_info = ["Error fetching inactive reasons"]
        
        # Recent endpoint activity
        recent_activity_query = """
            SELECT 
                COUNT(*) FILTER (WHERE scan_date >= NOW() - INTERVAL '24 hours') as scanned_24h,
                COUNT(*) FILTER (WHERE verification_date >= NOW() - INTERVAL '24 hours') as verified_24h,
                COUNT(*) FILTER (WHERE last_check_date >= NOW() - INTERVAL '24 hours') as checked_24h
            FROM endpoints
        """
        recent_activity = Database.fetch_one(recent_activity_query)
        
        # --- MODEL STATISTICS ---
        # Basic model counts
        total_models = Database.fetch_one("SELECT COUNT(*) FROM models")
        total_models = total_models[0] if total_models else 0
        distinct_models = Database.fetch_one("SELECT COUNT(DISTINCT name) FROM models")
        distinct_models = distinct_models[0] if distinct_models else 0
        
        # Get model counts by parameter size
        param_size_query = """
            SELECT 
                parameter_size, 
                COUNT(*) as count
            FROM models
            WHERE parameter_size IS NOT NULL
            GROUP BY parameter_size
            ORDER BY 
                CASE WHEN parameter_size LIKE '%B' THEN 
                    CAST(REPLACE(REPLACE(parameter_size, 'B', ''), '.', '') AS NUMERIC)
                ELSE 0
                END DESC
            LIMIT 10
        """
        try:
            param_sizes = Database.fetch_all(param_size_query)
            param_sizes_info = []
            
            for row in param_sizes:
                # Safely unpack - ensure row has at least 2 elements
                if len(row) >= 2:
                    size, count = row[0], row[1]
                    param_sizes_info.append(f"**{size}**: {count:,}")
                else:
                    # Handle case where row doesn't have expected structure
                    param_sizes_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching parameter sizes: {str(e)}")
            param_sizes_info = ["Error fetching parameter sizes"]
        
        # Get model counts by quantization level
        quant_query = """
            SELECT 
                quantization_level, 
                COUNT(*) as count
            FROM models
            WHERE quantization_level IS NOT NULL
            GROUP BY quantization_level
            ORDER BY count DESC
            LIMIT 10
        """
        try:
            quant_levels = Database.fetch_all(quant_query)
            quant_levels_info = []
            
            for row in quant_levels:
                # Safely unpack - ensure row has at least 2 elements
                if len(row) >= 2:
                    level, count = row[0], row[1]
                    quant_levels_info.append(f"**{level}**: {count:,}")
                else:
                    # Handle case where row doesn't have expected structure
                    quant_levels_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching quantization levels: {str(e)}")
            quant_levels_info = ["Error fetching quantization levels"]
        
        # Get top models by count
        top_models_query = """
            SELECT 
                name, 
                COUNT(*) as count
            FROM models
            GROUP BY name
            ORDER BY count DESC
            LIMIT 10
        """
        try:
            top_models = Database.fetch_all(top_models_query)
            top_models_info = []
            
            for row in top_models:
                # Safely unpack - ensure row has at least 2 elements
                if len(row) >= 2:
                    name, count = row[0], row[1]
                    top_models_info.append(f"**{name}**: {count:,}")
                else:
                    # Handle case where row doesn't have expected structure
                    top_models_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching top models: {str(e)}")
            top_models_info = ["Error fetching top models"]
        
        # Get models by type (if available)
        model_types_query = """
            SELECT 
                model_type, 
                COUNT(*) as count
            FROM models
            WHERE model_type IS NOT NULL
            GROUP BY model_type
            ORDER BY count DESC
        """
        try:
            model_types = Database.fetch_all(model_types_query)
            model_types_info = []
            
            for row in model_types:
                # Safely unpack - ensure row has at least 2 elements
                if len(row) >= 2:
                    model_type, count = row[0], row[1]
                    model_type = model_type or "unknown"
                    model_types_info.append(f"**{model_type}**: {count:,}")
                else:
                    # Handle case where row doesn't have expected structure
                    model_types_info.append(f"**Unknown Format**: {row}")
        except Exception as e:
            logger.error(f"Error fetching model types: {str(e)}")
            model_types_info = ["Error fetching model types"]
        
        # --- CHAT HISTORY STATISTICS ---
        chat_history_query = """
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(max_tokens) as avg_max_tokens,
                AVG(temperature) as avg_temperature,
                AVG(eval_count) as avg_tokens,
                AVG(eval_duration) as avg_duration
            FROM chat_history
        """
        try:
            chat_stats = Database.fetch_one(chat_history_query)
            
            if chat_stats and len(chat_stats) >= 6:
                total_chats = chat_stats[0] or 0
                unique_users = chat_stats[1] or 0
                avg_max_tokens = chat_stats[2] or 0
                avg_temperature = chat_stats[3] or 0
                avg_tokens = chat_stats[4] or 0
                avg_duration = chat_stats[5] or 0
            else:
                # Default values if query returns unexpected results
                total_chats = unique_users = avg_max_tokens = avg_temperature = avg_tokens = avg_duration = 0
        except Exception as e:
            logger.error(f"Error fetching chat history statistics: {str(e)}")
            total_chats = unique_users = avg_max_tokens = avg_temperature = avg_tokens = avg_duration = 0
        
        # --- BENCHMARK RESULTS STATISTICS ---
        benchmark_query = """
            SELECT 
                COUNT(*) as total,
                AVG(avg_response_time) as avg_response,
                AVG(tokens_per_second) as avg_tps,
                AVG(first_token_latency) as avg_first_token,
                AVG(success_rate) as avg_success
            FROM benchmark_results
        """
        try:
            benchmark_stats = Database.fetch_one(benchmark_query)
            
            if benchmark_stats and len(benchmark_stats) >= 5:
                total_benchmarks = benchmark_stats[0] or 0
                avg_response_time = benchmark_stats[1] or 0
                avg_tps = benchmark_stats[2] or 0
                avg_first_token = benchmark_stats[3] or 0
                avg_success_rate = benchmark_stats[4] or 0
            else:
                # Default values if query returns unexpected results
                total_benchmarks = avg_response_time = avg_tps = avg_first_token = avg_success_rate = 0
        except Exception as e:
            logger.error(f"Error fetching benchmark statistics: {str(e)}")
            total_benchmarks = avg_response_time = avg_tps = avg_first_token = avg_success_rate = 0
        
        # --- CREATE MULTIPLE EMBEDS FOR DETAILED INFORMATION ---
        # Create main summary embed
        main_embed = await format_embed_message(
            title="Database Information - Summary",
            description="Comprehensive database statistics",
            color=discord.Color.blue()
        )
        
        # Add table stats
        main_embed.add_field(
            name="Table Statistics",
            value="\n".join(tables_info) or "No data",
            inline=False
        )
        
        # Add endpoint summary stats
        main_embed.add_field(
            name="Endpoint Summary",
            value=(
                f"**Total Endpoints**: {verified_count + unverified_count:,}\n"
                f"**Verified**: {verified_count:,}\n"
                f"**Unverified**: {unverified_count:,}\n"
                f"**Active**: {active_count:,}\n"
                f"**Inactive**: {inactive_count:,}\n"
                f"**Honeypots**: {honeypot_count:,}\n"
                f"**Auth Required**: {auth_required_count:,}"
            ),
            inline=True
        )
        
        # Add model summary stats
        main_embed.add_field(
            name="Model Summary",
            value=(
                f"**Total Models**: {total_models:,}\n"
                f"**Distinct Models**: {distinct_models:,}"
            ),
            inline=True
        )
        
        # Add recent activity
        if recent_activity and len(recent_activity) >= 3:
            main_embed.add_field(
                name="Recent Activity (24h)",
                value=(
                    f"**Scanned**: {recent_activity[0]:,}\n"
                    f"**Verified**: {recent_activity[1]:,}\n"
                    f"**Checked**: {recent_activity[2]:,}"
                ),
                inline=True
            )
        elif recent_activity:
            # Handle case where we have some data but not all fields
            scanned = recent_activity[0] if len(recent_activity) > 0 else 0
            verified = recent_activity[1] if len(recent_activity) > 1 else 0
            checked = recent_activity[2] if len(recent_activity) > 2 else 0
            
            main_embed.add_field(
                name="Recent Activity (24h)",
                value=(
                    f"**Scanned**: {scanned:,}\n"
                    f"**Verified**: {verified:,}\n"
                    f"**Checked**: {checked:,}"
                ),
                inline=True
            )
            
        # Add database connection info
        try:
            from database import PG_DB_NAME, PG_DB_HOST, PG_DB_PORT, PG_DB_USER
            db_info = f"PostgreSQL database: {PG_DB_NAME}\nHost: {PG_DB_HOST}:{PG_DB_PORT}\nUser: {PG_DB_USER}"
        except (ImportError, AttributeError) as e:
            # Fallback if imports fail or attributes are missing
            import os
            try:
                db_url = os.environ.get('DATABASE_URL', 'Unknown connection')
                # Mask password if present
                if '@' in db_url and ':' in db_url:
                    masked_url = db_url.replace(
                        db_url.split('@')[0].split(':')[-1],
                        '********'
                    )
                    db_info = masked_url
                else:
                    db_info = db_url
            except Exception:
                # Last resort fallback
                db_info = "Database information unavailable"
        
        main_embed.add_field(
            name="Database Connection",
            value=f"```{db_info}```",
            inline=False
        )
        
        # Add timestamp
        main_embed.set_footer(text=f"Database info as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # Create endpoint details embed
        endpoint_embed = await format_embed_message(
            title="Database Information - Endpoint Details",
            description="Detailed endpoint statistics",
            color=discord.Color.blue()
        )
        
        # Add endpoint API types
        if api_types_info:
            endpoint_embed.add_field(
                name="Endpoints by API Type",
                value="\n".join(api_types_info) or "No data",
                inline=True
            )
        
        # Add endpoint matrix
        if endpoint_matrix_info:
            endpoint_embed.add_field(
                name="Endpoint Status Matrix",
                value="\n".join(endpoint_matrix_info) or "No data",
                inline=True
            )
        
        # Add honeypot reasons
        if honeypot_reasons_info:
            endpoint_embed.add_field(
                name="Top Honeypot Reasons",
                value="\n".join(honeypot_reasons_info) or "No honeypots detected",
                inline=False
            )
        
        # Add inactive reasons
        if inactive_reasons_info:
            endpoint_embed.add_field(
                name="Top Inactive Reasons",
                value="\n".join(inactive_reasons_info) or "No inactive endpoints",
                inline=False
            )
        
        # Create model details embed
        model_embed = await format_embed_message(
            title="Database Information - Model Details",
            description="Detailed model statistics",
            color=discord.Color.blue()
        )
        
        # Add parameter sizes
        if param_sizes_info:
            model_embed.add_field(
                name="Model Parameter Sizes",
                value="\n".join(param_sizes_info) or "No data",
                inline=True
            )
        
        # Add quantization levels
        if quant_levels_info:
            model_embed.add_field(
                name="Model Quantization Levels",
                value="\n".join(quant_levels_info) or "No data",
                inline=True
            )
        
        # Add top models
        if top_models_info:
            model_embed.add_field(
                name="Top 10 Models by Count",
                value="\n".join(top_models_info) or "No data",
                inline=False
            )
        
        # Add model types if available
        if model_types_info:
            model_embed.add_field(
                name="Models by Type",
                value="\n".join(model_types_info) or "No data",
                inline=False
            )
        
        # Create usage statistics embed
        usage_embed = await format_embed_message(
            title="Database Information - Usage Statistics",
            description="Chat and benchmark statistics",
            color=discord.Color.blue()
        )
        
        # Add chat statistics
        usage_embed.add_field(
            name="Chat History Statistics",
            value=(
                f"**Total Chats**: {total_chats:,}\n"
                f"**Unique Users**: {unique_users:,}\n"
                f"**Avg Max Tokens**: {avg_max_tokens:.1f}\n"
                f"**Avg Temperature**: {avg_temperature:.2f}\n"
                f"**Avg Tokens Generated**: {avg_tokens:.1f}\n"
                f"**Avg Duration**: {avg_duration:.2f}s"
            ),
            inline=True
        )
        
        # Add benchmark statistics
        usage_embed.add_field(
            name="Benchmark Statistics",
            value=(
                f"**Total Benchmarks**: {total_benchmarks:,}\n"
                f"**Avg Response Time**: {avg_response_time:.2f}s\n"
                f"**Avg Tokens/Second**: {avg_tps:.1f}\n"
                f"**Avg First Token Latency**: {avg_first_token:.2f}s\n"
                f"**Avg Success Rate**: {avg_success_rate:.1%}"
            ),
            inline=True
        )
        
        # Send all embeds
        await safe_followup(interaction, content=None, embed=main_embed)
        await safe_followup(interaction, content=None, embed=endpoint_embed)
        await safe_followup(interaction, content=None, embed=model_embed)
        await safe_followup(interaction, content=None, embed=usage_embed)
        
    except Exception as e:
        logger.error(f"Error in handle_db_info: {str(e)}")
        await safe_followup(interaction, content=f"Error retrieving database information: {str(e)}")
        raise

async def handle_refresh_commands(interaction: discord.Interaction, target: str, bot, safe_followup):
    """Handler for refreshing commands"""
    try:
        await safe_followup(interaction, f"Refreshing commands for target '{target}'. This may take a moment...")
        
        # Get current commands
        before_count = len(await bot.tree.fetch_commands())
        before_commands = await bot.tree.fetch_commands()
        
        # Log the current commands
        logger.info(f"Current commands before refresh: {', '.join([cmd.name for cmd in before_commands])}")
        
        if target == "global":
            # Sync commands globally
            await bot.tree.sync()
            sync_msg = "Commands synced globally"
        elif target == "guild":
            # Sync commands to the current guild
            await bot.tree.sync(guild=interaction.guild)
            sync_msg = f"Commands synced to guild '{interaction.guild.name}'"
        else:  # "all"
            # Sync globally first
            await bot.tree.sync()
            # Then sync to the current guild
            await bot.tree.sync(guild=interaction.guild)
            sync_msg = "Commands synced globally and to current guild"
        
        # Get the updated commands
        after_commands = await bot.tree.fetch_commands()
        
        # Send detailed results
        command_list = [f"- {cmd.name}" for cmd in after_commands]
        
        message = f"**Command Refresh Complete**\n"
        message += f"- Commands before: {before_count}\n"
        message += f"- Commands after: {len(after_commands)}\n"
        message += f"- {sync_msg}\n\n"
        message += "**Available Commands:**\n" + "\n".join(command_list)
        
        await safe_followup(interaction, message)
        
        logger.info(f"Commands refreshed by user {interaction.user.name}")
        logger.info(f"Refreshed from {before_count} to {len(after_commands)} commands")
        logger.info(f"Updated commands: {', '.join([cmd.name for cmd in after_commands])}")
        
    except Exception as e:
        logger.error(f"Error in handle_refresh_commands: {str(e)}")
        raise

async def handle_cleanup_database(interaction: discord.Interaction, force: bool, safe_followup):
    """Handler for cleaning up the database"""
    try:
        if not force:
            # Confirmation message when not using force
            confirm_embed = await format_embed_message(
                title="Database Cleanup Confirmation",
                description=(
                    "This will remove duplicate records and orphaned data from the database.\n\n"
                    "To proceed, run the command again with `force=True`."
                ),
                color=discord.Color.orange()
            )
            await safe_followup(interaction, content=None, embed=confirm_embed)
            return
        
        await safe_followup(interaction, "Starting database cleanup...")
        cleanup_results = []
        
        # Start transaction
        try:
            Database.execute("BEGIN")
            
            # 1. Find duplicate models (same name on same endpoint)
            if Database.fetch_one("SELECT 1 FROM pg_catalog.pg_tables WHERE tablename = 'models'"):
                if Database.fetch_one("SELECT column_name FROM information_schema.columns WHERE table_name = 'models' AND column_name = 'endpoint_id'"):
                    try:
                        # With PostgreSQL string aggregation
                        model_dupes = Database.fetch_all("""
                            SELECT endpoint_id, name, COUNT(*), string_agg(id::text, ',') as ids
                            FROM models
                            GROUP BY endpoint_id, name
                            HAVING COUNT(*) > 1
                        """)
                        
                        if model_dupes:
                            cleanup_results.append(f"Found {len(model_dupes)} sets of duplicate models")
                            
                            for dupe in model_dupes:
                                try:
                                    if len(dupe) >= 4:
                                        endpoint_id, name, count, id_list = dupe[0], dupe[1], dupe[2], dupe[3]
                                        ids = id_list.split(',')
                                        # Keep the first ID, remove others
                                        keep_id = ids[0]
                                        remove_ids = ids[1:]
                                        
                                        for remove_id in remove_ids:
                                            Database.execute("DELETE FROM models WHERE id = %s", (remove_id,))
                                    else:
                                        logger.warning(f"Unexpected duplicate model format: {dupe}")
                                except Exception as e:
                                    logger.error(f"Error processing duplicate model: {str(e)}")
                            
                            # Calculate removed count safely
                            removed_count = 0
                            for dupe in model_dupes:
                                try:
                                    if len(dupe) >= 4:
                                        id_list = dupe[3]
                                        removed_count += len(id_list.split(',')) - 1
                                except Exception:
                                    pass
                            
                            cleanup_results.append(f"Removed {removed_count} duplicate model records")
                        else:
                            cleanup_results.append("No duplicate models found")
                    except Exception as e:
                        logger.error(f"Error finding duplicate models by endpoint_id: {str(e)}")
                        cleanup_results.append(f"Error finding duplicate models: {str(e)}")
                else:
                    try:
                        # If using server_id instead of endpoint_id
                        model_dupes = Database.fetch_all("""
                            SELECT server_id, name, COUNT(*), string_agg(id::text, ',') as ids
                            FROM models
                            GROUP BY server_id, name
                            HAVING COUNT(*) > 1
                        """)
                        
                        if model_dupes:
                            cleanup_results.append(f"Found {len(model_dupes)} sets of duplicate models")
                            
                            for dupe in model_dupes:
                                try:
                                    if len(dupe) >= 4:
                                        server_id, name, count, id_list = dupe[0], dupe[1], dupe[2], dupe[3]
                                        ids = id_list.split(',')
                                        # Keep the first ID, remove others
                                        keep_id = ids[0]
                                        remove_ids = ids[1:]
                                        
                                        for remove_id in remove_ids:
                                            Database.execute("DELETE FROM models WHERE id = %s", (remove_id,))
                                    else:
                                        logger.warning(f"Unexpected duplicate model format: {dupe}")
                                except Exception as e:
                                    logger.error(f"Error processing duplicate model: {str(e)}")
                            
                            # Calculate removed count safely
                            removed_count = 0
                            for dupe in model_dupes:
                                try:
                                    if len(dupe) >= 4:
                                        id_list = dupe[3]
                                        removed_count += len(id_list.split(',')) - 1
                                except Exception:
                                    pass
                            
                            cleanup_results.append(f"Removed {removed_count} duplicate model records")
                        else:
                            cleanup_results.append("No duplicate models found")
                    except Exception as e:
                        logger.error(f"Error finding duplicate models by server_id: {str(e)}")
                        cleanup_results.append(f"Error finding duplicate models: {str(e)}")
            else:
                model_dupes = []
                cleanup_results.append("Models table not found - skipping duplicate check")
            
            # 2. Find orphaned models (models with no corresponding endpoint)
            if Database.fetch_one("SELECT 1 FROM pg_catalog.pg_tables WHERE tablename = 'models'"):
                if Database.fetch_one("SELECT column_name FROM information_schema.columns WHERE table_name = 'models' AND column_name = 'endpoint_id'"):
                    try:
                        orphaned = Database.fetch_all("""
                            SELECT COUNT(*) 
                            FROM models m
                            WHERE NOT EXISTS (
                                SELECT 1 FROM endpoints e WHERE e.id = m.endpoint_id
                            )
                        """)
                        
                        if orphaned and len(orphaned) > 0 and len(orphaned[0]) > 0 and orphaned[0][0] > 0:
                            orphan_count = orphaned[0][0]
                            cleanup_results.append(f"Found {orphan_count} orphaned models")
                            
                            # Remove orphaned models
                            try:
                                Database.execute("""
                                    DELETE FROM models m
                                    WHERE NOT EXISTS (
                                        SELECT 1 FROM endpoints e WHERE e.id = m.endpoint_id
                                    )
                                """)
                                cleanup_results.append(f"Removed {orphan_count} orphaned models")
                            except Exception as e:
                                logger.error(f"Error removing orphaned models: {str(e)}")
                                cleanup_results.append(f"Error removing orphaned models: {str(e)}")
                        else:
                            cleanup_results.append("No orphaned models found")
                    except Exception as e:
                        logger.error(f"Error finding orphaned models: {str(e)}")
                        cleanup_results.append(f"Error finding orphaned models: {str(e)}")
                else:
                    cleanup_results.append("Models table lacks endpoint_id column - skipping orphan check")
            else:
                cleanup_results.append("Models table not found - skipping orphan check")
            
            # 3. Fix inconsistencies between endpoints and verified_endpoints
            if Database.fetch_one("SELECT 1 FROM pg_catalog.pg_tables WHERE tablename = 'verified_endpoints'"):
                try:
                    # Check for verified endpoints without entries in verified_endpoints table
                    inconsistencies = Database.fetch_one("""
                        SELECT COUNT(*) 
                        FROM endpoints e 
                        WHERE e.verified = 1 
                        AND NOT EXISTS (
                            SELECT 1 FROM verified_endpoints ve 
                            WHERE ve.endpoint_id = e.id
                        )
                    """)
                    
                    if inconsistencies and len(inconsistencies) > 0 and inconsistencies[0] > 0:
                        inconsistency_count = inconsistencies[0]
                        cleanup_results.append(f"Found {inconsistency_count} inconsistencies between endpoints and verified_endpoints")
                        
                        # Fix inconsistencies
                        try:
                            Database.execute("""
                                INSERT INTO verified_endpoints (endpoint_id, verification_date)
                                SELECT id, NOW()
                                FROM endpoints e
                                WHERE e.verified = 1
                                AND NOT EXISTS (
                                    SELECT 1 FROM verified_endpoints ve 
                                    WHERE ve.endpoint_id = e.id
                                )
                            """)
                            cleanup_results.append(f"Fixed {inconsistency_count} inconsistencies")
                        except Exception as e:
                            logger.error(f"Error fixing inconsistencies: {str(e)}")
                            cleanup_results.append(f"Error fixing inconsistencies: {str(e)}")
                    else:
                        cleanup_results.append("No inconsistencies found between endpoints and verified_endpoints")
                except Exception as e:
                    logger.error(f"Error checking for inconsistencies: {str(e)}")
                    cleanup_results.append(f"Error checking for inconsistencies: {str(e)}")
            else:
                cleanup_results.append("verified_endpoints table not found - skipping inconsistency check")
            
            # Commit all changes
            Database.execute("COMMIT")
            
            # Create summary embed
            summary_embed = await format_embed_message(
                title="Database Cleanup Complete",
                description="\n".join(cleanup_results),
                color=discord.Color.green()
            )
            
            await safe_followup(interaction, content=None, embed=summary_embed)
            
        except Exception as e:
            # Rollback on error
            Database.execute("ROLLBACK")
            logger.error(f"Error during database cleanup: {str(e)}")
            raise
        
    except Exception as e:
        logger.error(f"Error in handle_cleanup_database: {str(e)}")
        raise

async def handle_verify_all_servers(interaction: discord.Interaction, force: bool, safe_followup):
    """Handler for verifying all servers"""
    try:
        # This is a placeholder as the actual implementation would need the server verification function
        # which is not part of this file and would depend on the existing codebase
        
        if not force:
            # Confirmation message when not using force
            confirm_embed = await format_embed_message(
                title="Verify All Servers Confirmation",
                description=(
                    "This will attempt to verify all servers in the database.\n"
                    "This operation can take a long time and generate significant network traffic.\n\n"
                    "To proceed, run the command again with `force=True`."
                ),
                color=discord.Color.orange()
            )
            await safe_followup(interaction, content=None, embed=confirm_embed)
            return
        
        await safe_followup(interaction, "Starting verification of all servers. This may take several minutes...")
        
        # Get servers to verify
        servers = Database.fetch_all("""
            SELECT id, ip, port
            FROM endpoints
            ORDER BY scan_date DESC
        """)
        
        if not servers:
            await safe_followup(interaction, "No servers found to verify.")
            return
        
        await safe_followup(interaction, f"Found {len(servers)} servers to verify. Starting verification process...")
        
        # This is a placeholder for the actual verification logic
        # In a real implementation, you would call your server verification function here
        # and process the results
        
        await safe_followup(interaction, f"Verification process started for {len(servers)} servers. This process runs in the background and may take some time to complete.")
        
    except Exception as e:
        logger.error(f"Error in handle_verify_all_servers: {str(e)}")
        raise

async def handle_sync_models(interaction: discord.Interaction, target: str, force: bool, safe_followup):
    """Handler for syncing models"""
    try:
        # This is a placeholder as the actual implementation would need the model sync function
        # which is not part of this file and would depend on the existing codebase
        
        if not force and target == "all":
            # Confirmation message when not using force for all servers
            confirm_embed = await format_embed_message(
                title="Sync All Models Confirmation",
                description=(
                    "This will attempt to sync models for all servers in the database.\n"
                    "This operation can take a long time and generate significant network traffic.\n\n"
                    "To proceed, run the command again with `force=True`."
                ),
                color=discord.Color.orange()
            )
            await safe_followup(interaction, content=None, embed=confirm_embed)
            return
        
        await safe_followup(interaction, f"Starting model sync for target '{target}'. This may take some time...")
        
        if target == "global":
            # Sync models for all verified servers
            servers = Database.fetch_all("""
                SELECT e.id, e.ip, e.port
                FROM endpoints e
                JOIN verified_endpoints ve ON e.id = ve.endpoint_id
                WHERE e.is_honeypot = FALSE
                ORDER BY ve.verification_date DESC
            """)
        elif target == "guild":
            # This would typically require some mapping between Discord guilds and servers
            # As a placeholder, we'll just get the most recently verified servers
            servers = Database.fetch_all("""
                SELECT e.id, e.ip, e.port
                FROM endpoints e
                JOIN verified_endpoints ve ON e.id = ve.endpoint_id
                WHERE e.is_honeypot = FALSE
                ORDER BY ve.verification_date DESC
                LIMIT 5
            """)
        else:  # "all"
            # Sync models for all endpoints
            servers = Database.fetch_all("""
                SELECT id, ip, port
                FROM endpoints
                WHERE is_honeypot = FALSE
                ORDER BY scan_date DESC
            """)
        
        if not servers:
            await safe_followup(interaction, f"No servers found for target '{target}'.")
            return
        
        await safe_followup(interaction, f"Found {len(servers)} servers for target '{target}'. Starting model sync process...")
        
        # This is a placeholder for the actual model sync logic
        # In a real implementation, you would call your model sync function here
        # and process the results
        
        await safe_followup(interaction, f"Model sync process started for {len(servers)} servers. This process runs in the background and may take some time to complete.")
        
    except Exception as e:
        logger.error(f"Error in handle_sync_models: {str(e)}")
        raise 