# Ollama Discord Bot

A Discord bot for interacting with Ollama AI models.

## Overview

This Discord bot allows you to manage and interact with Ollama AI models through Discord. It connects to your database of Ollama instances and provides commands to list, select, add, delete, and interact with models.

## Features

- List all available Ollama models
- Select a specific model by ID
- Add new models to the database
- Delete models from the database
- Interact with models through Discord
- Modern, visually appealing Discord UI with embeds
- Smart message formatting and pagination
- Proper code block handling in model responses

## Requirements

- Python 3.6+
- Discord Bot Token
- Required Python packages:
  - discord.py
  - requests
  - python-dotenv

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/Ollama_Scanner.git
   cd Ollama_Scanner/DiscordBot
   ```

2. Install the required packages:
   ```
   pip install discord.py requests python-dotenv
   ```

3. Create a `.env` file in the DiscordBot directory with your Discord bot token:
   ```
   DISCORD_BOT_TOKEN=your_discord_bot_token
   ```

4. Make sure you have the `ollama_instances.db` database file in the same directory (or create it by running the scanner first).

## Usage

Run the bot:

```
python discord_bot.py
```

### Commands

The bot uses Discord slash commands for all operations:

- `/list_models` - List all available Ollama models with filtering options
- `/searchmodels <model_name>` - Search for models by name
- `/modelsbyparam <parameter_size>` - Find models with specific parameters
- `/chat <model_id> <prompt>` - Chat with a specific model by ID
- `/quickprompt <model_name> <prompt>` - Quickly chat with any model by name
- `/help` - Show available commands and information
- `/addmodel <ip> <port> <name>` - Add a new Ollama model
- `/deletemodel <model_id>` - Delete a model by ID
- `/serverinfo <ip> <port>` - Show detailed info about a server
- `/checkserver <ip> <port>` - Check available models on a specific server

See the full list of commands by typing `/` in Discord after adding the bot.

## Message Formatting

The bot uses modern Discord formatting features to provide a clean, attractive user interface:

- **Embeds**: Most responses use embeds with appropriate colors for different message types
- **Emoji**: Commands and sections are marked with relevant emoji for quick visual identification
- **Structured Data**: Information is organized into properly formatted fields and sections
- **Code Blocks**: Model responses preserve code blocks and syntax highlighting
- **Pagination**: Long lists are automatically paginated for easier reading

For developers, a reference file `message_formatting.md` is included with examples and best practices.

## How It Works

The bot connects to your database of Ollama instances and provides commands to manage and interact with them. When you use the `/chat` or `/quickprompt` commands, the bot:

1. Shows a "Thinking..." indicator
2. Sends your prompt to the specified Ollama model
3. Displays the response with proper formatting 
4. Includes metrics about the generation (tokens, time, etc.)

Long or code-containing responses are specially formatted to maintain readability within Discord's limitations.

## Troubleshooting

- Make sure your Discord bot has the necessary permissions in your server
- Ensure the Ollama instances in your database are accessible from where the bot is running
- Check that your Discord bot token is correctly set in the `.env` file

## Security Note

This bot is intended for use with Ollama instances that you own or have permission to access. Do not use it to access systems you don't own or have permission to access. 

## Customizing the UI

You can adjust the visual appearance of the bot by modifying the formatting helper functions in `discord_bot.py`:

- `format_embed_message()` - Controls the appearance of embeds
- `format_list_as_pages()` - Controls pagination for lists
- `format_model_details()` - Controls how model information is displayed
- `format_code_or_text()` - Controls how code and text are formatted 