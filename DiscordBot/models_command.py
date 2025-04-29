import logging
import discord
from discord import app_commands
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import math

from database import Database
from utils import format_embed_message, safe_defer

logger = logging.getLogger(__name__)

def register_models_command(bot, safe_defer, safe_followup):
    """Register the models command with the bot"""
    
    # Define choices for models actions with improved naming
    model_actions = [
        app_commands.Choice(name="List All Models", value="list"),
        app_commands.Choice(name="Search Models", value="search"),
        app_commands.Choice(name="Model Details", value="details"),
        app_commands.Choice(name="Find Endpoints", value="endpoints")
    ]
    
    # Define choices for model categories
    model_categories = [
        app_commands.Choice(name="All Categories", value="all"),
        app_commands.Choice(name="Text Generation", value="text"),
        app_commands.Choice(name="Chat Models", value="chat"),
        app_commands.Choice(name="Image Models", value="image"),
        app_commands.Choice(name="Audio Models", value="audio"),
        app_commands.Choice(name="Code Generation", value="code"),
        app_commands.Choice(name="Embedding Models", value="embedding")
    ]
    
    # Define choices for sort options with better descriptions
    sort_options = [
        app_commands.Choice(name="Model Name", value="name"),
        app_commands.Choice(name="Parameter Size", value="params"),
        app_commands.Choice(name="Quantization Level", value="quant"),
        app_commands.Choice(name="Usage Count", value="count"),
        app_commands.Choice(name="Date Added", value="date")
    ]
    
    @bot.tree.command(name="models", description="🔎 Search, filter, and view available AI models")
    @app_commands.describe(
        search="Search for models by name, provider, or description",
        size="Filter by parameter size (e.g., 7B, 13B, 70B)",
        quantization="Filter by quantization level (e.g., Q4_K_M, Q5_K_M)",
        action="Action to perform with models",
        category="Filter models by their category",
        sort_by="Sort results by this field",
        descending="Sort in descending order (newest/largest first)",
        limit="Maximum number of models to show (5-100)",
        show_endpoints="Show available endpoints for each model"
    )
    @app_commands.choices(
        action=model_actions,
        category=model_categories,
        sort_by=sort_options
    )
    async def models_command(
        interaction: discord.Interaction,
        action: str = "list",
        search: str = None,
        category: str = "all",
        size: str = None,
        quantization: str = None,
        sort_by: str = "name",
        descending: bool = True,
        limit: int = 25,
        show_endpoints: bool = False
    ):
        """Unified command for model discovery and information"""
        await safe_defer(interaction)
        
        try:
            # Validate parameters
            if limit < 5 or limit > 100:
                limit = 25
                
            # Handle different actions
            if action == "list":
                await handle_list_models(interaction, safe_followup, category, size, quantization, sort_by, descending, limit, show_endpoints)
            elif action == "details":
                if not search:
                    error_embed = await format_embed_message(
                        title="❓ Missing Parameter",
                        description="Please provide a model ID or name using the `search` parameter to view model details.",
                        color=discord.Color.gold()
                    )
                    await safe_followup(interaction, embed=error_embed)
                    return
                await handle_model_details(interaction, safe_followup, search, show_endpoints)
            elif action == "search":
                if not search:
                    error_embed = await format_embed_message(
                        title="❓ Missing Parameter",
                        description="Please provide a search term using the `search` parameter to find models.",
                        color=discord.Color.gold()
                    )
                    await safe_followup(interaction, embed=error_embed)
                    return
                await handle_search_models(interaction, safe_followup, search, category, size, quantization, sort_by, descending, limit, show_endpoints)
            elif action == "endpoints":
                if not search:
                    error_embed = await format_embed_message(
                        title="❓ Missing Parameter",
                        description="Please provide a model ID or name using the `search` parameter to find its endpoints.",
                        color=discord.Color.gold()
                    )
                    await safe_followup(interaction, embed=error_embed)
                    return
                await handle_model_endpoints(interaction, safe_followup, search, sort_by, descending, limit)
            else:
                error_embed = await format_embed_message(
                    title="⚠️ Invalid Action",
                    description=f"Action '{action}' is not recognized. Please use one of: list, search, details, endpoints.",
                    color=discord.Color.red()
                )
                await safe_followup(interaction, embed=error_embed)
        except Exception as e:
            logger.error(f"Error in models command: {str(e)}")
            error_embed = await format_embed_message(
                title="⚠️ Error Processing Command",
                description=f"An error occurred: ```{str(e)}```",
                color=discord.Color.red()
            )
            await safe_followup(interaction, embed=error_embed)
    
    return models_command

async def handle_list_models(
    interaction: discord.Interaction,
    safe_followup,
    category: str = "all",
    size: str = None,
    quantization: str = None,
    sort_by: str = "name",
    descending: bool = True,
    limit: int = 25,
    show_endpoints: bool = False
):
    """Handle listing available models"""
    try:
        # Build the query based on filters
        query_parts = [
            "SELECT m.id, m.name, m.provider, m.category, m.description, m.parameters, m.created_at",
            "FROM models m"
        ]
        
        where_clauses = []
        params = []
        
        # Add category filter
        if category != "all":
            where_clauses.append("m.category = %s")
            params.append(category)
            
        # Add size filter
        if size:
            where_clauses.append("m.parameters LIKE %s")
            params.append(f"%{size}%")
            
        # Add quantization filter
        if quantization:
            where_clauses.append("m.name LIKE %s")
            params.append(f"%{quantization}%")
            
        # Combine WHERE clauses if any exist
        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))
            
        # Add sort options
        sort_direction = "DESC" if descending else "ASC"
        
        if sort_by == "name":
            query_parts.append(f"ORDER BY m.name {sort_direction}")
        elif sort_by == "params":
            query_parts.append(f"ORDER BY m.parameters {sort_direction}")
        elif sort_by == "quant":
            query_parts.append(f"ORDER BY m.name {sort_direction}")  # Using name as proxy for quantization which is often in name
        elif sort_by == "date":
            query_parts.append(f"ORDER BY m.created_at {sort_direction}")
        elif sort_by == "count":
            # Most/least used models first (requires subquery to count usages)
            usage_query = """
                SELECT m.id, m.name, m.provider, m.category, m.description, m.parameters, m.created_at,
                COALESCE((
                   SELECT COUNT(*) FROM chat_history ch WHERE ch.model_id = m.id
                ), 0) AS usage_count
                FROM models m
            """
            if where_clauses:
                usage_query += " WHERE " + " AND ".join(where_clauses)
                
            usage_query += f" ORDER BY usage_count {sort_direction}"
            
            query_parts = [usage_query]
        else:
            # Default sort
            query_parts.append(f"ORDER BY m.name {sort_direction}")
            
        # Add limit
        query_parts.append("LIMIT %s")
        params.append(limit)
            
        # Execute query
        query = " ".join(query_parts)
        models = Database.fetch_all(query, tuple(params))
        
        if not models or len(models) == 0:
            no_models_embed = await format_embed_message(
                title="🔍 No Models Found",
                description="No models match your criteria. Try adjusting your filters or categories.",
                color=discord.Color.blue()
            )
            await safe_followup(interaction, embed=no_models_embed)
            return
            
        # Create embed for listing models
        title = "📋 Available Models"
        if category != "all":
            category_display = category.replace("_", " ").title()
            title += f" - {category_display}"
            
        filter_details = []
        if size:
            filter_details.append(f"Size: {size}")
        if quantization:
            filter_details.append(f"Quantization: {quantization}")
            
        if filter_details:
            title += f" ({', '.join(filter_details)})"
            
        models_embed = discord.Embed(
            title=title,
            description=f"Found {len(models)} models matching your criteria",
            color=discord.Color.blue()
        )
        
        # Add timestamp
        models_embed.timestamp = datetime.now(timezone.utc)
        
        for model in models:
            # Handle different result formats based on sort
            if sort_by == "count":
                id, name, provider, cat, description, parameters, created_at, usage_count = model
            else:
                id, name, provider, cat, description, parameters, created_at = model
                usage_count = None
                
            # Format description - avoid truncation by using multiple fields if needed
            description_text = description or "No description available"
            
            # Create field for model
            field_name = f"🤖 {name} (ID: {id})"
            
            field_value = []
            field_value.append(f"**Provider**: {provider}")
            field_value.append(f"**Category**: {cat.replace('_', ' ').title()}")
            
            if parameters:
                field_value.append(f"**Parameters**: {parameters}")
            
            if usage_count is not None:
                field_value.append(f"**Usage Count**: {usage_count}")
            
            if created_at:
                field_value.append(f"**Added**: {created_at.strftime('%Y-%m-%d')}")
                
            # If show_endpoints is True, add endpoint info
            if show_endpoints:
                endpoints = get_model_endpoints(id)
                if endpoints:
                    endpoint_info = ", ".join([f"{ep['ip']}:{ep['port']}" for ep in endpoints[:3]])
                    if len(endpoints) > 3:
                        endpoint_info += f" and {len(endpoints) - 3} more"
                    field_value.append(f"**🌐 Endpoints**: {endpoint_info}")
            
            # Add the main model info field
            models_embed.add_field(
                name=field_name,
                value="\n".join(field_value),
                inline=False
            )
            
            # Add description as separate field to avoid truncation
            if description:
                desc_name = f"📝 Description"
                # Only truncate very long descriptions, with a higher limit
                if len(description) > 300:
                    desc_value = description[:300] + "..."
                else:
                    desc_value = description
                    
                models_embed.add_field(
                    name=desc_name,
                    value=desc_value,
                    inline=False
                )
        
        # Add footer with helpful info
        sort_name = next((c.name for c in sort_options if c.value == sort_by), "Name")
        order = "descending" if descending else "ascending"
        
        footer_text = f"Sorted by {sort_name} ({order}) • "
        footer_text += f"Use /models details search:<id> for detailed info • "
        footer_text += f"Use /chat model:<id> to start a conversation"
        
        models_embed.set_footer(text=footer_text)
        
        await safe_followup(interaction, embed=models_embed)
    
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise

async def handle_model_details(
    interaction: discord.Interaction,
    safe_followup,
    model_id: str,
    show_endpoints: bool = False
):
    """Handle retrieving detailed information about a specific model"""
    try:
        # Check if model_id is numeric or a name
        if model_id.isdigit():
            # Search by ID
            query = """
                SELECT 
                    m.id, m.name, m.provider, m.category, m.description, 
                    m.capabilities, m.parameters, m.context_length, 
                    m.pricing_input, m.pricing_output, m.created_at,
                    m.updated_at, m.version, m.is_available,
                    (SELECT COUNT(*) FROM chat_history ch WHERE ch.model_id = m.id) as usage_count
                FROM models m
                WHERE m.id = %s
            """
            model = Database.fetch_one(query, (int(model_id),))
        else:
            # Search by name (partial match)
            query = """
                SELECT 
                    m.id, m.name, m.provider, m.category, m.description, 
                    m.capabilities, m.parameters, m.context_length, 
                    m.pricing_input, m.pricing_output, m.created_at,
                    m.updated_at, m.version, m.is_available,
                    (SELECT COUNT(*) FROM chat_history ch WHERE ch.model_id = m.id) as usage_count
                FROM models m
                WHERE m.name LIKE %s
                LIMIT 1
            """
            model = Database.fetch_one(query, (f"%{model_id}%",))
        
        if not model:
            not_found_embed = await format_embed_message(
                title="🔍 Model Not Found",
                description=f"No model found with ID or name matching '{model_id}'.\n\nTry using `/models list` to see available models or check your spelling.",
                color=discord.Color.gold()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        # Unpack model data
        (
            id, name, provider, category, description, capabilities, 
            parameters, context_length, pricing_input, pricing_output, 
            created_at, updated_at, version, is_available, usage_count
        ) = model
        
        # Create embed for model info with improved styling
        model_embed = discord.Embed(
            title=f"🤖 {name}",
            description=f"**ID**: {id}\n" + (description or "No description available"),
            color=discord.Color.green() if is_available else discord.Color.red()
        )
        
        # Add thumbnail if available (placeholder for potential future feature)
        # model_embed.set_thumbnail(url="https://example.com/model_icon.png")
        
        # Format category with better readability
        category_display = category.replace("_", " ").title() if category else "Unknown"
        
        # Add basic info
        status_emoji = "✅" if is_available else "❌"
        model_embed.add_field(
            name="ℹ️ Basic Information",
            value=(
                f"**Provider**: {provider}\n"
                f"**Category**: {category_display}\n"
                f"**Version**: {version or 'N/A'}\n"
                f"**Status**: {status_emoji} {'Available' if is_available else 'Unavailable'}\n"
                f"**Usage**: {usage_count:,} conversations"
            ),
            inline=False
        )
        
        # Add technical details
        tech_details = []
        if parameters:
            tech_details.append(f"**Parameters**: {parameters}")
        if context_length:
            tech_details.append(f"**Context Length**: {context_length:,} tokens")
        if capabilities:
            tech_details.append(f"**Capabilities**: {capabilities}")
            
        if tech_details:
            model_embed.add_field(
                name="⚙️ Technical Details",
                value="\n".join(tech_details),
                inline=False
            )
        
        # Add pricing info
        if pricing_input or pricing_output:
            pricing_details = []
            if pricing_input:
                pricing_details.append(f"**Input**: {pricing_input}")
            if pricing_output:
                pricing_details.append(f"**Output**: {pricing_output}")
                
            model_embed.add_field(
                name="💰 Pricing",
                value="\n".join(pricing_details),
                inline=False
            )
        
        # Add timestamps in a more readable format
        dates = []
        if created_at:
            dates.append(f"**Added**: {created_at.strftime('%Y-%m-%d')}")
        if updated_at:
            dates.append(f"**Updated**: {updated_at.strftime('%Y-%m-%d')}")
            
        if dates:
            model_embed.add_field(
                name="📅 Dates",
                value="\n".join(dates),
                inline=False
            )
        
        # Add endpoint information if requested
        if show_endpoints:
            endpoints = get_model_endpoints(id)
            if endpoints:
                endpoint_info = []
                for i, ep in enumerate(endpoints[:5]):
                    verified_emoji = "✅" if ep['verified'] == "Yes" else "⚠️"
                    endpoint_info.append(f"{i+1}. **{ep['ip']}:{ep['port']}** {verified_emoji}")
                
                if len(endpoints) > 5:
                    endpoint_info.append(f"...and {len(endpoints) - 5} more endpoints")
                
                model_embed.add_field(
                    name=f"🌐 Available Endpoints ({len(endpoints)})",
                    value="\n".join(endpoint_info),
                    inline=False
                )
            else:
                model_embed.add_field(
                    name="🌐 Endpoints",
                    value="No endpoints found for this model",
                    inline=False
                )
            
        # Add usage example
        model_embed.add_field(
            name="💬 Usage Example",
            value=f"```/chat model:{id} prompt:\"Your message here\"```",
            inline=False
        )
        
        # Set footer with helpful tips
        model_embed.set_footer(
            text=f"Tip: Use /chat model:{id} to start a conversation • Use /models endpoints search:{id} to see all endpoints"
        )
        
        # Add timestamp
        model_embed.timestamp = datetime.now(timezone.utc)
        
        await safe_followup(interaction, embed=model_embed)
    
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        raise

async def handle_search_models(
    interaction: discord.Interaction,
    safe_followup,
    search_query: str,
    category: str = "all",
    size: str = None,
    quantization: str = None,
    sort_by: str = "name",
    descending: bool = True,
    limit: int = 25,
    show_endpoints: bool = False
):
    """Handle searching for models by name, provider, or description"""
    try:
        # Build the search query
        query_parts = [
            "SELECT m.id, m.name, m.provider, m.category, m.description, m.parameters, m.created_at",
            "FROM models m",
            "WHERE (m.name LIKE %s OR m.provider LIKE %s OR m.description LIKE %s)"
        ]
        
        search_param = f"%{search_query}%"
        params = [search_param, search_param, search_param]
        
        # Add category filter
        if category != "all":
            query_parts.append("AND m.category = %s")
            params.append(category)
            
        # Add size filter
        if size:
            query_parts.append("AND m.parameters LIKE %s")
            params.append(f"%{size}%")
            
        # Add quantization filter
        if quantization:
            query_parts.append("AND m.name LIKE %s")
            params.append(f"%{quantization}%")
            
        # Add sort options
        sort_direction = "DESC" if descending else "ASC"
        
        if sort_by == "name":
            query_parts.append(f"ORDER BY m.name {sort_direction}")
        elif sort_by == "params":
            query_parts.append(f"ORDER BY m.parameters {sort_direction}")
        elif sort_by == "quant":
            query_parts.append(f"ORDER BY m.name {sort_direction}")  # Using name as proxy for quantization
        elif sort_by == "date":
            query_parts.append(f"ORDER BY m.created_at {sort_direction}")
        elif sort_by == "count":
            # Handle usage count separately due to subquery
            usage_query = [
                "SELECT m.id, m.name, m.provider, m.category, m.description, m.parameters, m.created_at,",
                "COALESCE((",
                "   SELECT COUNT(*) FROM chat_history ch WHERE ch.model_id = m.id",
                "), 0) AS usage_count",
                "FROM models m",
                "WHERE (m.name LIKE %s OR m.provider LIKE %s OR m.description LIKE %s)"
            ]
            
            if category != "all":
                usage_query.append("AND m.category = %s")
            
            if size:
                usage_query.append("AND m.parameters LIKE %s")
            
            if quantization:
                usage_query.append("AND m.name LIKE %s")
                
            usage_query.append(f"ORDER BY usage_count {sort_direction}")
            
            query_parts = usage_query
        else:
            # Default sort
            query_parts.append(f"ORDER BY m.name {sort_direction}")
            
        # Add limit
        query_parts.append("LIMIT %s")
        params.append(limit)
            
        # Execute query
        query = " ".join(query_parts)
        models = Database.fetch_all(query, tuple(params))
        
        if not models or len(models) == 0:
            no_results_embed = await format_embed_message(
                title="🔍 No Models Found",
                description=f"No models match your search for '{search_query}'.\n\nTry different keywords or use `/models list` to browse all models.",
                color=discord.Color.gold()
            )
            await safe_followup(interaction, embed=no_results_embed)
            return
            
        # Create embed for search results
        category_display = category.replace("_", " ").title() if category != "all" else "All Categories"
        title = f"🔎 Search Results: '{search_query}'"
        subtitle = f"Category: {category_display}"
            
        filter_details = []
        if size:
            filter_details.append(f"Size: {size}")
        if quantization:
            filter_details.append(f"Quant: {quantization}")
            
        if filter_details:
            subtitle += f" | {', '.join(filter_details)}"
            
        search_embed = discord.Embed(
            title=title,
            description=f"Found {len(models)} matching models\n{subtitle}",
            color=discord.Color.blue()
        )
        
        # Add timestamp
        search_embed.timestamp = datetime.now(timezone.utc)
        
        for model in models:
            # Handle different result formats based on sort
            if sort_by == "count":
                id, name, provider, cat, description, parameters, created_at, usage_count = model
            else:
                id, name, provider, cat, description, parameters, created_at = model
                usage_count = None
                
            # Format description without excessive truncation
            description_text = description or "No description available"
            if len(description_text) > 200:
                short_desc = description_text[:200] + "..."
            else:
                short_desc = description_text
            
            # Create field for model
            field_name = f"🤖 {name} (ID: {id})"
            
            field_value = [
                f"**Provider**: {provider}",
                f"**Category**: {cat.replace('_', ' ').title()}"
            ]
            
            if parameters:
                field_value.append(f"**Parameters**: {parameters}")
                
            if usage_count is not None:
                field_value.append(f"**Usage Count**: {usage_count:,}")
            
            if created_at:
                field_value.append(f"**Added**: {created_at.strftime('%Y-%m-%d')}")
                
            # If show_endpoints is True, add endpoint info
            if show_endpoints:
                endpoints = get_model_endpoints(id)
                if endpoints:
                    endpoint_info = ", ".join([f"{ep['ip']}:{ep['port']}" for ep in endpoints[:3]])
                    if len(endpoints) > 3:
                        endpoint_info += f" and {len(endpoints) - 3} more"
                    field_value.append(f"**🌐 Endpoints**: {endpoint_info}")
            
            field_value.append(f"**Description**: {short_desc}")
            field_value.append(f"\n*Use* `/models details search:{id}` *for more details*")
            
            search_embed.add_field(
                name=field_name,
                value="\n".join(field_value),
                inline=False
            )
        
        # Add footer with helpful info
        sort_name = next((c.name for c in sort_options if c.value == sort_by), "Name")
        order = "descending" if descending else "ascending"
        
        footer_text = f"Sorted by {sort_name} ({order}) • "
        footer_text += f"Use /chat model:<id> to start a conversation"
        
        search_embed.set_footer(text=footer_text)
        
        await safe_followup(interaction, embed=search_embed)
    
    except Exception as e:
        logger.error(f"Error searching models: {str(e)}")
        raise

async def handle_model_endpoints(
    interaction: discord.Interaction,
    safe_followup,
    model_id: str,
    sort_by: str = "name",
    descending: bool = True,
    limit: int = 25
):
    """Handle finding endpoints that have a specific model"""
    try:
        # First, resolve the model ID or name
        model_info = None
        
        if model_id.isdigit():
            # Search by ID
            query = "SELECT id, name FROM models WHERE id = %s"
            model_info = Database.fetch_one(query, (int(model_id),))
        else:
            # Search by name
            query = "SELECT id, name FROM models WHERE name LIKE %s LIMIT 1"
            model_info = Database.fetch_one(query, (f"%{model_id}%",))
            
        if not model_info:
            not_found_embed = await format_embed_message(
                title="🔍 Model Not Found",
                description=f"No model found with ID or name matching '{model_id}'.\n\nTry using `/models list` to see all available models.",
                color=discord.Color.gold()
            )
            await safe_followup(interaction, embed=not_found_embed)
            return
            
        model_id_num, model_name = model_info
        
        # Now find endpoints with this model
        query_parts = [
            "SELECT e.ip, e.port, e.provider, e.verified, e.scan_date, e.last_check_status",
            "FROM endpoints e",
            "JOIN models m ON e.id = m.endpoint_id",
            "WHERE m.id = %s OR m.name = %s"
        ]
        
        # Add sort options
        sort_direction = "DESC" if descending else "ASC"
        
        if sort_by == "name":
            query_parts.append(f"ORDER BY e.provider {sort_direction}, e.ip {sort_direction}")
        elif sort_by == "date":
            query_parts.append(f"ORDER BY e.scan_date {sort_direction}")
        else:
            query_parts.append(f"ORDER BY e.ip {sort_direction}")
            
        # Add limit
        query_parts.append("LIMIT %s")
        
        # Execute query
        query = " ".join(query_parts)
        endpoints = Database.fetch_all(query, (model_id_num, model_name, limit))
        
        if not endpoints or len(endpoints) == 0:
            no_endpoints_embed = await format_embed_message(
                title=f"🌐 No Endpoints Found",
                description=f"No endpoints have been found that host the model '{model_name}'.\n\nThis model may no longer be available on any public server.",
                color=discord.Color.gold()
            )
            await safe_followup(interaction, embed=no_endpoints_embed)
            return
            
        # Create embed for endpoint results
        endpoints_embed = discord.Embed(
            title=f"🌐 Endpoints Hosting {model_name}",
            description=f"Found {len(endpoints)} endpoints hosting this model",
            color=discord.Color.blue()
        )
        
        # Add timestamp
        endpoints_embed.timestamp = datetime.now(timezone.utc)
        
        for endpoint in endpoints:
            # Unpack endpoint data safely
            ip, port = endpoint[0], endpoint[1]
            provider = endpoint[2] if len(endpoint) > 2 and endpoint[2] else "Unknown"
            verified = endpoint[3] if len(endpoint) > 3 else False
            scan_date = endpoint[4] if len(endpoint) > 4 else None
            status = endpoint[5] if len(endpoint) > 5 else None
            
            # Add status emoji
            status_emoji = "✅" if verified else "⚠️"
            
            # Format endpoint field
            field_name = f"{status_emoji} {ip}:{port}"
            
            field_value = [
                f"**Provider**: {provider}",
                f"**Verified**: {'Yes' if verified else 'No'}"
            ]
            
            if scan_date:
                field_value.append(f"**Last Scanned**: {scan_date.strftime('%Y-%m-%d')}")
                
            if status:
                field_value.append(f"**Status**: {status}")
                
            # Add command examples
            field_value.append(f"\n**Quick Access**:")
            field_value.append(f"• Check server: `/server action:check ip:{ip} port:{port}`")
            field_value.append(f"• Chat with model: `/chat model:{model_id_num} prompt:\"Hello!\"`")
            
            endpoints_embed.add_field(
                name=field_name,
                value="\n".join(field_value),
                inline=False
            )
        
        # Add footer
        endpoints_embed.set_footer(
            text=f"Use /server command to check endpoint details • Use /chat to start a conversation"
        )
        
        await safe_followup(interaction, embed=endpoints_embed)
    
    except Exception as e:
        logger.error(f"Error finding model endpoints: {str(e)}")
        raise

def get_model_endpoints(model_id: int) -> List[Dict[str, Any]]:
    """Get endpoints that have a specific model"""
    try:
        # Query to find endpoints for a specific model
        query = """
            SELECT e.ip, e.port, e.verified
            FROM endpoints e
            JOIN models m ON e.id = m.endpoint_id
            WHERE m.id = %s
            LIMIT 10
        """
        
        results = Database.fetch_all(query, (model_id,))
        
        if not results:
            return []
            
        endpoints = []
        for result in results:
            ip, port, verified = result
            endpoints.append({
                "ip": ip,
                "port": port,
                "verified": "Yes" if verified else "No"
            })
            
        return endpoints
    except Exception as e:
        logger.error(f"Error getting model endpoints: {str(e)}")
        return []

class PaginationView(discord.ui.View):
    """A view for paginating through model results"""
    
    def __init__(self, pages, current_page=0):
        super().__init__(timeout=180)  # 3 minute timeout
        self.pages = pages
        self.current_page = current_page
        self.total_pages = len(pages)
        self.update_buttons()
        
    def update_buttons(self):
        # Update button states based on current page
        prev_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="◀️ Previous",
            custom_id="prev_page",
            disabled=(self.current_page == 0)
        )
        prev_button.callback = self.prev_page
        
        next_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Next ▶️",
            custom_id="next_page",
            disabled=(self.current_page >= self.total_pages - 1)
        )
        next_button.callback = self.next_page
        
        page_indicator = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.current_page + 1}/{self.total_pages}",
            custom_id="page_indicator",
            disabled=True
        )
        
        # Clear existing buttons and add updated ones
        self.clear_items()
        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)
        
    async def prev_page(self, interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        
    async def next_page(self, interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self) 