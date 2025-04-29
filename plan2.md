# Discord Bot Command Consolidation Implementation Plan

This document outlines the detailed implementation plan for consolidating the Discord bot's commands into 5 user commands and 3 admin commands.

## Overview

Current state: 20+ commands with overlapping functionality
Target state: 8 consolidated commands (5 user commands, 3 admin commands)

## 1. Implement Unified User Commands

### 1.1. Create `/models` Command ✅

This command will consolidate all model discovery functionality.

#### 1.1.1. Define Command Structure ✅

```python
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
        # Handle different actions
        if action == "list":
            await handle_list_models(interaction, search, size, quantization, sort_by, descending, limit)
        elif action == "search":
            await handle_search_models(interaction, search, sort_by, descending, limit)
        elif action == "details":
            await handle_model_details(interaction, search)
        elif action == "endpoints":
            await handle_find_endpoints(interaction, search, size, quantization, limit, show_endpoints)
        else:
            # Default to list
            await handle_list_models(interaction, search, size, quantization, sort_by, descending, limit)
            
    except Exception as e:
        logger.error(f"Error in models command: {e}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 1.1.2. Implement Handlers for Each Action ✅

```python
async def handle_list_models(interaction, search, size, quantization, sort_by, descending, limit):
    """Handler for listing models"""
    # Base query
    query = """
        SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
               e.ip, e.port, m.size_mb,
               COUNT(m2.id) OVER(PARTITION BY m.name) as count
        FROM models m
        JOIN endpoints e ON m.endpoint_id = e.id
        LEFT JOIN models m2 ON m.name = m2.name
        WHERE 1=1
    """
    params = []
    
    # Add filters if provided
    if search:
        query += " AND m.name LIKE %s"
        params.append(f"%{search}%")
    
    if quantization:
        query += " AND m.quantization_level LIKE %s"
        params.append(f"%{quantization}%")
    
    if size:
        query += " AND m.parameter_size LIKE %s"
        params.append(f"%{size}%")
    
    # Add sorting
    if sort_by == "name":
        query += " ORDER BY m.name"
    elif sort_by == "params":
        query += " ORDER BY m.parameter_size"
    elif sort_by == "quant":
        query += " ORDER BY m.quantization_level"
    elif sort_by == "count":
        query += " ORDER BY count"
    else:
        query += " ORDER BY m.name"  # Default sort
        
    if not descending:
        query += " ASC"
    else:
        query += " DESC"
        
    # Add limit
    query += " LIMIT %s"
    params.append(limit)
    
    # Execute query
    results = Database.fetch_all(query, tuple(params))
    
    # Process and display results
    # [Rest of implementation...]
```

#### 1.1.3. Implement Model Details View ✅

```python
async def handle_model_details(interaction, model_identifier):
    """Handler for viewing detailed model information"""
    # Check if model_identifier is numeric (model ID) or text (model name)
    is_id = model_identifier.isdigit()
    
    if is_id:
        # Fetch by ID
        query = """
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                   e.ip, e.port, m.size_mb, e.verification_date, e.scan_date
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.id = %s
            AND e.verified = 1
            AND e.is_honeypot = FALSE
        """
        model = Database.fetch_one(query, (int(model_identifier),))
    else:
        # Fetch by name (first match)
        query = """
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, 
                   e.ip, e.port, m.size_mb, e.verification_date, e.scan_date
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.name LIKE %s
            AND e.verified = 1
            AND e.is_honeypot = FALSE
            LIMIT 1
        """
        model = Database.fetch_one(query, (f"%{model_identifier}%",))
    
    if not model:
        await interaction.followup.send(embed=await format_embed_message(
            title="Model Not Found",
            description=f"Could not find a model matching '{model_identifier}'",
            color=discord.Color.orange()
        ))
        return
        
    # Create detailed embed for the model
    # [Rest of implementation...]
```

#### 1.1.4. Implement Find Endpoints Handler ✅

```python
async def handle_find_endpoints(interaction, model_name, param_size, quant_level, limit, test_connectivity):
    """Handler for finding endpoints with a specific model"""
    # Similar to the existing find_model_endpoints command but simplified
    # [Implementation...]
```

### 1.2. Create `/chat` Command ✅

This command will consolidate all model interaction functionality.

#### 1.2.1. Define Command Structure ✅

```python
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
        # Determine if model is ID or name
        model_id = None
        model_name = None
        endpoint_ip = None
        endpoint_port = None
        
        if model.isdigit():
            # Model is an ID
            model_id = int(model)
            validation_result = await validate_model_id(model_id)
            
            if not validation_result["valid"]:
                error_embed = await format_embed_message(
                    title="🚫 Model Not Found",
                    description=validation_result["message"],
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed)
                return
            
            # Get model info
            model_id = validation_result["model_id"]
            model_name = validation_result["name"]
            endpoint_ip = validation_result["ip"]
            endpoint_port = validation_result["port"]
        else:
            # Model is a name, find an available endpoint
            result = await find_model_by_name(model)
            if not result:
                error_embed = await format_embed_message(
                    title="🚫 Model Not Found",
                    description=f"Could not find an available endpoint for model '{model}'",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed)
                return
                
            model_id = result["id"]
            model_name = result["name"]
            endpoint_ip = result["ip"]
            endpoint_port = result["port"]
            
        # Proceed with chat using the resolved model information
        # [Rest of implementation using the existing chat code...]
    
    except Exception as e:
        logger.error(f"Error in chat command: {str(e)}")
        error_embed = await format_embed_message(
            title="❌ Error",
            description=f"An error occurred: ```\n{str(e)}\n```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 1.2.2. Implement Helper for Finding Model by Name ✅

```python
async def find_model_by_name(model_name):
    """Find a model by name and return an available endpoint"""
    try:
        # Query to find a verified, non-honeypot endpoint with this model
        query = f"""
            SELECT m.id, m.name, e.ip, e.port
            FROM models m
            JOIN endpoints e ON m.endpoint_id = e.id
            WHERE m.name LIKE %s
            AND e.verified = {get_db_boolean(True, as_string=True, for_verified=True)}
            AND e.is_honeypot = {get_db_boolean(False)}
            AND e.is_active = {get_db_boolean(True)}
            ORDER BY e.verification_date DESC
            LIMIT 1
        """
        result = Database.fetch_one(query, (f"%{model_name}%",))
        
        if not result:
            return None
            
        return {
            "id": result[0],
            "name": result[1],
            "ip": result[2],
            "port": result[3]
        }
        
    except Exception as e:
        logger.error(f"Error finding model by name: {str(e)}")
        return None
```

#### 1.2.3. Chat Implementation and Response Formatting ✅

This will reuse much of the existing chat command logic but with the new unified approach.

### 1.3. Create `/server` Command ✅

This command will consolidate all server management functionality.

#### 1.3.1. Define Command Structure ✅

```python
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
        if action == "list":
            await handle_list_servers(interaction, sort_by, limit)
        elif action == "details":
            if not ip:
                await interaction.followup.send("Server IP address is required for details")
                return
            await handle_server_details(interaction, ip, port)
        elif action == "check":
            if not ip:
                await interaction.followup.send("Server IP address is required to check models")
                return
            await handle_check_server(interaction, ip, port)
        elif action == "verify":
            if not ip:
                await interaction.followup.send("Server IP address is required to verify connectivity")
                return
            await handle_verify_server(interaction, ip, port)
        else:
            await interaction.followup.send("Unknown action specified")
    
    except Exception as e:
        logger.error(f"Error in server command: {str(e)}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 1.3.2. Implement Server Listing Handler ✅

```python
async def handle_list_servers(interaction, sort_by, limit):
    """Handler for listing servers"""
    # Build query based on sort and limit parameters
    # [Implementation...]
```

#### 1.3.3. Implement Server Details Handler ✅

```python
async def handle_server_details(interaction, ip, port):
    """Handler for showing detailed server information"""
    # [Implementation...]
```

#### 1.3.4. Implement Check Server Models Handler ✅

```python
async def handle_check_server(interaction, ip, port):
    """Handler for checking available models on a server"""
    # This can reuse most of the existing checkserver command implementation
    # [Implementation...]
```

### 1.4. Create `/help` Command ✅

The help command is already implemented in a good format, but should be updated to reflect the new command structure.

#### 1.4.1. Update Help Command with New Structure ✅

```python
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
        if topic:
            # Topic-specific help
            if topic == "models":
                embed = await create_models_help_embed()
            elif topic == "chat":
                embed = await create_chat_help_embed()
            elif topic == "servers":
                embed = await create_servers_help_embed()
            elif topic == "admin":
                embed = await create_admin_help_embed()
            elif topic == "examples":
                embed = await create_examples_help_embed()
            else:
                embed = await create_general_help_embed()
        else:
            # General help overview
            embed = await create_general_help_embed()
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}")
        await interaction.response.send_message(f"Error generating help: {str(e)}", ephemeral=True)
```

#### 1.4.2. Implement Help Embed Generators ✅

```python
async def create_general_help_embed():
    """Create the general help embed with command overview"""
    embed = discord.Embed(
        title="🤖 Ollama Discord Bot Help",
        description="This bot allows you to interact with Ollama models directly from Discord.",
        color=discord.Color.blurple()
    )
    
    # Add bot icon as thumbnail if available
    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    
    # User commands section
    embed.add_field(
        name="📋 User Commands",
        value=(
            "• `/models` - Search, filter, and view available models\n"
            "• `/chat` - Chat with any Ollama model by ID or name\n"
            "• `/server` - View and manage Ollama servers\n"
            "• `/history` - View your chat history\n"
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
        name="Usage Tip",
        value="Use `/help [topic]` to get detailed help on specific commands",
        inline=False
    )
    
    embed.set_footer(text="Type / to see all available commands • Parameters are shown when you select a command")
    embed.timestamp = datetime.now(timezone.utc)
    
    return embed
```

### 1.5. Create `/history` Command ✅

This command will handle viewing and managing chat history.

#### 1.5.1. Define Command Structure ✅

```python
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
        # Get user ID for history lookup
        user_id = str(interaction.user.id)
        
        if action == "view":
            await handle_view_history(interaction, user_id, limit, model_id, search)
        elif action == "clear":
            await handle_clear_history(interaction, user_id, model_id)
        elif action == "continue":
            await handle_continue_chat(interaction, user_id)
        else:
            await interaction.followup.send("Unknown action specified")
            
    except Exception as e:
        logger.error(f"Error in history command: {str(e)}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 1.5.2. Implement View History Handler ✅

```python
async def handle_view_history(interaction, user_id, limit, model_id, search):
    """Handler for viewing chat history"""
    # Build query to fetch history
    query = """
        SELECT ch.id, ch.model_id, m.name, ch.prompt, ch.response, ch.timestamp
        FROM chat_history ch
        JOIN models m ON ch.model_id = m.id
        WHERE ch.user_id = %s
    """
    params = [user_id]
    
    # Add filters if provided
    if model_id:
        query += " AND ch.model_id = %s"
        params.append(model_id)
        
    if search:
        query += " AND (ch.prompt LIKE %s OR ch.response LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
        
    # Add sorting and limit
    query += " ORDER BY ch.timestamp DESC LIMIT %s"
    params.append(limit)
    
    # Execute query
    results = Database.fetch_all(query, tuple(params))
    
    if not results:
        await interaction.followup.send(embed=await format_embed_message(
            title="No Chat History",
            description="You don't have any chat history matching these criteria.",
            color=discord.Color.blue()
        ))
        return
        
    # Format results as embed
    # [Implementation...]
```

## 2. Implement Admin Commands

### 2.1. Create `/admin` Command

This command will handle various administrative functions.

#### 2.1.1. Define Command Structure

```python
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
            await handle_db_info(interaction)
        elif action == "refresh":
            await handle_refresh_commands(interaction, target)
        elif action == "cleanup":
            await handle_cleanup_database(interaction, force)
        elif action == "verify":
            await handle_verify_all_servers(interaction, force)
        elif action == "sync":
            await handle_sync_models(interaction, target, force)
        else:
            await interaction.followup.send("Unknown action specified")
            
    except Exception as e:
        logger.error(f"Error in admin command: {str(e)}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 2.1.2. Implement DB Info Handler

```python
async def handle_db_info(interaction):
    """Handler for showing database information"""
    # This can reuse most of the existing db_info command implementation
    # [Implementation...]
```

#### 2.1.3. Implement Other Admin Handlers

Similar handlers for each action type, reusing code from existing commands where possible.

### 2.2. Create `/manage` Command

This command will handle model and server management.

#### 2.2.1. Define Command Structure

```python
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
                    await interaction.followup.send("IP and model name are required to add a model")
                    return
                await handle_add_model(interaction, ip, port, model_name)
            elif action == "delete":
                if not model_id:
                    await interaction.followup.send("Model ID is required to delete a model")
                    return
                await handle_delete_model(interaction, model_id)
            elif action == "update":
                if not model_id:
                    await interaction.followup.send("Model ID is required to update a model")
                    return
                await handle_update_model(interaction, model_id, model_name)
            else:
                await interaction.followup.send("Unknown action for model management")
        elif type == "server":
            if action == "add":
                if not ip:
                    await interaction.followup.send("IP is required to add a server")
                    return
                await handle_add_server(interaction, ip, port)
            elif action == "delete":
                if not ip:
                    await interaction.followup.send("IP is required to delete a server")
                    return
                await handle_delete_server(interaction, ip, port)
            elif action == "sync":
                if not ip:
                    await interaction.followup.send("IP is required to sync a server")
                    return
                await handle_sync_server(interaction, ip, port)
            else:
                await interaction.followup.send("Unknown action for server management")
        else:
            await interaction.followup.send("Unknown resource type")
            
    except Exception as e:
        logger.error(f"Error in manage command: {str(e)}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 2.2.2. Implement Model Management Handlers

```python
async def handle_add_model(interaction, ip, port, model_name):
    """Handler for adding a model"""
    # This can reuse most of the existing addmodel command implementation
    # [Implementation...]
```

#### 2.2.3. Implement Server Management Handlers

Similar handlers for server management actions.

### 2.3. Create `/stats` Command ✅

This command will provide statistics and analytics.

#### 2.3.1. Define Command Structure ✅

```python
@bot.tree.command(name="stats", description="View statistics and analytics")
@app_commands.describe(
    type="Type of statistics to view",
    days="Number of days to include in statistics",
    format="Output format"
)
@app_commands.choices(type=[
    app_commands.Choice(name="Models", value="models"),
    app_commands.Choice(name="Servers", value="servers"),
    app_commands.Choice(name="Endpoints", value="endpoints"),
    app_commands.Choice(name="Honeypots", value="honeypots"),
    app_commands.Choice(name="Usage", value="usage")
])
@app_commands.choices(format=[
    app_commands.Choice(name="Table", value="table"),
    app_commands.Choice(name="Detailed", value="detailed")
])
async def stats_command(
    interaction: discord.Interaction,
    type: str,
    days: int = 30,
    format: str = "table"
):
    """Command for viewing statistics and analytics"""
    # Check if user has admin privileges
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command.", ephemeral=True)
        return
        
    await safe_defer(interaction)
    
    try:
        if type == "models":
            await handle_model_stats(interaction, days, format)
        elif type == "servers":
            await handle_server_stats(interaction, days, format)
        elif type == "endpoints":
            await handle_endpoint_stats(interaction, days, format)
        elif type == "honeypots":
            await handle_honeypot_stats(interaction, days, format)
        elif type == "usage":
            await handle_usage_stats(interaction, days, format)
        else:
            await interaction.followup.send("Unknown statistics type")
            
    except Exception as e:
        logger.error(f"Error in stats command: {str(e)}")
        error_embed = await format_embed_message(
            title="Error Processing Command",
            description=f"An error occurred: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
```

#### 2.3.2. Implement Statistics Handlers ✅

```python
async def handle_model_stats(interaction, days, format):
    """Handler for showing model statistics"""
    # [Implementation...]
```

## 3. Update Existing Functionality

### 3.1. Create Transition Plan

#### 3.1.1. Keep Existing Commands Temporarily

During transition, keep existing commands functioning but mark them as deprecated in the help text.

```python
@bot.tree.command(name="listmodels", description="[DEPRECATED] Use /models instead")
async def list_models_deprecated(interaction: discord.Interaction):
    """Deprecated version of list_models command"""
    embed = await format_embed_message(
        title="Command Deprecated",
        description="This command is deprecated. Please use `/models` instead which offers more options and better formatting.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Call the new command handler
    await models_command(interaction, action="list")
```

#### 3.1.2. Update Command Registration

Update `setup` or main function to register all new commands.

```python
def register_commands():
    """Register all commands with Discord"""
    # User commands
    bot.tree.add_command(models_command)
    bot.tree.add_command(chat_command)
    bot.tree.add_command(server_command)
    bot.tree.add_command(help_command)
    bot.tree.add_command(history_command)
    
    # Admin commands
    bot.tree.add_command(admin_command)
    bot.tree.add_command(manage_command)
    bot.tree.add_command(stats_command)
```

### 3.2. Update Documentation

#### 3.2.1. Update README.md

Update the README.md file to reflect the new command structure.

#### 3.2.2. Create Usage Guide

Create a detailed usage guide for the new commands.

## 4. Testing and Deployment

### 4.1. Local Testing

#### 4.1.1. Test Each Command Individually

Verify each command works as expected with various parameter combinations.

#### 4.1.2. Test Command Interactions

Ensure commands interact properly with shared resources.

### 4.2. Deployment

#### 4.2.1. Deploy Updated Bot

Deploy the updated bot to the production environment.

#### 4.2.2. Monitor Performance

Monitor command usage and error rates to catch any issues.

## 5. Maintenance Plan

### 5.1. Removal of Legacy Commands

#### 5.1.1. Schedule for Removal

After a transition period (e.g., 1 month), remove the deprecated commands.

#### 5.1.2. Announce Command Changes

Announce the command changes to users ahead of time.

### 5.2. Future Enhancements

#### 5.2.1. Pagination Enhancements

Add button-based pagination for lists and results.

#### 5.2.2. Advanced Search Features

Add more advanced search and filtering options to the `/models` command. 