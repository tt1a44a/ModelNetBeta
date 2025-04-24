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

- `!listmodels` - List all available Ollama models
- `!selectmodel <model_id>` - Select a model by ID
- `!addmodel <ip> <port> <name> <info>` - Add a new Ollama model
  - Example: `!addmodel 192.168.1.100 11434 llama2 {"description": "Llama 2 7B model"}`
- `!deletemodel <model_id>` - Delete a model by ID
- `!interact <model_id> <message>` - Interact with a selected Ollama model
  - Example: `!interact 1 What is the capital of France?`

## How It Works

The bot connects to your SQLite database of Ollama instances and provides commands to manage and interact with them. When you use the `!interact` command, the bot sends your message to the selected Ollama instance and returns the response.

## Troubleshooting

- Make sure your Discord bot has the necessary permissions in your server.
- Ensure the Ollama instances in your database are accessible from where the bot is running.
- Check that your Discord bot token is correctly set in the `.env` file.

## Security Note

This bot is intended for use with Ollama instances that you own or have permission to access. Do not use it to access systems you don't own or have permission to access. 