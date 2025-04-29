# Discord Bot for Ollama Model Discovery

This Discord bot allows you to discover, search, and interact with Ollama models available on public servers.

## Command Structure

The bot provides a streamlined set of commands organized into user commands and admin commands.

### User Commands

| Command | Description | Examples |
|---------|-------------|----------|
| `/models` | Search, filter, and view available Ollama models | `/models action:list` <br> `/models action:search search:llama` <br> `/models action:details search:13` |
| `/chat` | Chat with any Ollama model by ID or name | `/chat model:llama-3 prompt:Hello!` <br> `/chat model:42 prompt:Tell me a joke` |
| `/server` | View and manage Ollama servers | `/server action:list` <br> `/server action:details ip:192.168.1.1` <br> `/server action:check ip:192.168.1.1` |
| `/history` | View and manage your chat history | `/history action:view limit:10` <br> `/history action:clear` |
| `/help` | Show help information on specific topics | `/help` <br> `/help topic:models` <br> `/help topic:chat` |

### Admin Commands

| Command | Description | Examples |
|---------|-------------|----------|
| `/admin` | Administrative functions and tools | `/admin action:db_info` <br> `/admin action:refresh target:guild` <br> `/admin action:cleanup force:true` |
| `/manage` | Manage models and servers | `/manage action:add type:server ip:192.168.1.1` <br> `/manage action:delete type:model model_id:42` |
| `/stats` | View statistics and analytics | `/stats type:models days:30` <br> `/stats type:usage format:detailed` |

## Detailed Command Reference

### `/models` Command

The `/models` command provides a unified interface for model discovery and information.

#### Parameters:

- `action`: The action to perform
  - `list`: List all models (default)
  - `search`: Search for specific models
  - `details`: Show detailed information about a model
  - `endpoints`: Find endpoints with a specific model
- `search`: Optional search term to filter models by name
- `size`: Optional filter by parameter size (e.g., "7B", "13B")
- `quantization`: Optional filter by quantization level (e.g., "Q4_K_M")
- `sort_by`: Field to sort results by (name, params, quant, count)
- `descending`: Whether to sort in descending order (default: true)
- `limit`: Maximum number of results to return (default: 25)
- `show_endpoints`: Show endpoint details for each model (default: false)

#### Examples:

```
/models action:list
/models action:search search:mistral size:7B
/models action:details search:phi
/models action:endpoints search:llama sort_by:params show_endpoints:true
```

### `/chat` Command

The `/chat` command allows you to interact with any available Ollama model.

#### Parameters:

- `model`: Model ID or name to chat with (required)
- `prompt`: Your message to the model (required)
- `system_prompt`: Optional system prompt to guide the model
- `temperature`: Controls randomness (0.0 to 1.0, default: 0.7)
- `max_tokens`: Maximum tokens in the response (default: 1000)
- `save_history`: Save this chat in your history (default: true)
- `verbose`: Show detailed API information (default: false)

#### Examples:

```
/chat model:llama-3 prompt:Hello, how are you?
/chat model:42 prompt:Explain quantum computing system_prompt:You are a physics expert
/chat model:phi prompt:Write a short poem temperature:0.9 max_tokens:500
```

### `/server` Command

The `/server` command provides functionality for viewing and managing Ollama servers.

#### Parameters:

- `action`: Action to perform (required)
  - `list`: List all servers
  - `details`: Show details for a specific server
  - `check`: Check available models on a server
  - `verify`: Verify connectivity to a server
- `ip`: Server IP address (required for specific server actions)
- `port`: Server port (default: 11434)
- `sort_by`: Field to sort results by (ip, date, count)
- `limit`: Maximum number of results to return (default: 25)

#### Examples:

```
/server action:list sort_by:count
/server action:details ip:192.168.1.1
/server action:check ip:192.168.1.1 port:11434
/server action:verify ip:192.168.1.1
```

### `/history` Command

The `/history` command allows you to view and manage your chat history.

#### Parameters:

- `action`: Action to perform (default: view)
  - `view`: View your chat history
  - `clear`: Clear your chat history
  - `continue`: Continue a previous chat
- `limit`: Maximum number of history items to show (default: 5)
- `model_id`: Filter by model ID
- `search`: Search term to filter history by

#### Examples:

```
/history action:view limit:10
/history action:view model_id:42
/history action:view search:quantum
/history action:clear
```

### `/help` Command

The `/help` command provides information about using the bot.

#### Parameters:

- `topic`: Optional topic to get help on
  - `models`: Help with the models command
  - `chat`: Help with the chat command
  - `servers`: Help with the server command
  - `admin`: Help with admin commands
  - `examples`: Usage examples

#### Examples:

```
/help
/help topic:models
/help topic:chat
/help topic:admin
```

### Admin Commands

The admin commands are only available to users with administrator permissions in your Discord server.

#### `/admin` Command

```
/admin action:db_info
/admin action:refresh target:guild
/admin action:cleanup force:true
/admin action:verify force:true
/admin action:sync target:all force:true
```

#### `/manage` Command

```
/manage action:add type:model ip:192.168.1.1 model_name:llama-3
/manage action:delete type:model model_id:42
/manage action:add type:server ip:192.168.1.1
/manage action:delete type:server ip:192.168.1.1
/manage action:sync type:server ip:192.168.1.1
```

#### `/stats` Command

```
/stats type:models days:30
/stats type:servers format:detailed
/stats type:usage days:7
```

## Additional Information

For more detailed information, use the `/help` command with a specific topic. If you encounter any issues, please contact the bot administrator. 