#!/usr/bin/env python3
"""
Condense Discord Bot Commands

This script analyzes the Discord bot commands and helps condense duplicates or
similar commands into a more manageable set of commands.
"""

import re
import os
import sys
import argparse
from collections import defaultdict

# Set up command-line arguments
parser = argparse.ArgumentParser(description='Condense Discord bot commands')
parser.add_argument('--file', default='DiscordBot/discord_bot.py', 
                    help='Path to the discord_bot.py file')
parser.add_argument('--update', action='store_true',
                    help='Update the help text in the bot file')
parser.add_argument('--dry-run', action='store_true',
                    help='Show recommendations without making changes')
args = parser.parse_args()

# Check if the file exists
if not os.path.exists(args.file):
    print(f"Error: File {args.file} does not exist")
    sys.exit(1)

# Read the file
with open(args.file, 'r') as f:
    bot_code = f.read()

# Find all commands
command_pattern = re.compile(r'@bot\.tree\.command\(name="([^"]+)",\s*description="([^"]+)"\)')
commands = command_pattern.findall(bot_code)

print(f"Found {len(commands)} commands in the bot")
print("-" * 50)

# Group similar commands by functionality
search_commands = []
list_commands = []
model_management_commands = []
server_management_commands = []
interaction_commands = []
admin_commands = []
utility_commands = []

# Sort commands into categories
for cmd_name, description in commands:
    if any(x in cmd_name.lower() for x in ["search", "find"]) or "model" in cmd_name.lower() and "param" in cmd_name.lower():
        search_commands.append((cmd_name, description))
    elif any(x in cmd_name.lower() for x in ["list", "all"]):
        list_commands.append((cmd_name, description))
    elif any(x in cmd_name.lower() for x in ["add", "delete", "select", "model"]) and not "search" in cmd_name.lower():
        model_management_commands.append((cmd_name, description))
    elif any(x in cmd_name.lower() for x in ["server", "sync"]):
        server_management_commands.append((cmd_name, description))
    elif any(x in cmd_name.lower() for x in ["interact", "prompt", "benchmark"]):
        interaction_commands.append((cmd_name, description))
    elif any(x in cmd_name.lower() for x in ["admin", "refresh", "sync", "cleanup"]):
        admin_commands.append((cmd_name, description))
    else:
        utility_commands.append((cmd_name, description))

# Find help text section
help_text_pattern = re.compile(r'help_text\s*=\s*"""(.*?)"""', re.DOTALL)
help_text_match = help_text_pattern.search(bot_code)

if not help_text_match:
    print("Error: Could not find help_text in the bot code")
    sys.exit(1)

help_text = help_text_match.group(1)

# Analyze the commands
duplicates = defaultdict(list)

# Look for commands that could be consolidated
consolidation_recommendations = []

# Compare search commands
if len(search_commands) > 1:
    consolidation_recommendations.append(
        "Consider consolidating search commands:\n" + 
        "\n".join([f"- {cmd}: {desc}" for cmd, desc in search_commands]) +
        "\nRecommendation: Combine into a unified `/search` command with type parameter"
    )

# Compare list commands
if len(list_commands) > 1:
    consolidation_recommendations.append(
        "Consider consolidating list commands:\n" + 
        "\n".join([f"- {cmd}: {desc}" for cmd, desc in list_commands]) +
        "\nRecommendation: Combine into a unified `/list` command with type parameter"
    )

# Compare admin commands for refreshing
refresh_commands = [(cmd, desc) for cmd, desc in admin_commands if "refresh" in cmd.lower()]
if len(refresh_commands) > 1:
    consolidation_recommendations.append(
        "Consider consolidating refresh commands:\n" + 
        "\n".join([f"- {cmd}: {desc}" for cmd, desc in refresh_commands]) +
        "\nRecommendation: Combine into one `/refresh` command with options"
    )

# Print results
print("\nCommand Categories:")
print(f"Search Commands: {len(search_commands)}")
print(f"List Commands: {len(list_commands)}")
print(f"Model Management: {len(model_management_commands)}")
print(f"Server Management: {len(server_management_commands)}")
print(f"Interaction: {len(interaction_commands)}")
print(f"Admin: {len(admin_commands)}")
print(f"Utility: {len(utility_commands)}")
print("-" * 50)

print("\nConsolidation Recommendations:")
for recommendation in consolidation_recommendations:
    print("-" * 50)
    print(recommendation)
    print()

# Create a condensed help text
if args.update or args.dry_run:
    new_help_text = """
**Ollama Scanner Bot Commands:**

**Server Management:**
- `/listservers` - List all Ollama servers in the database
- `/checkserver <ip> <port>` - Check which models are installed on a specific server
- `/syncserver <ip> <port>` - Synchronize the database with models available on the server
- `/serverinfo <ip> [port] [sort_by] [descending]` - Show detailed information about a specific server
- `/verifyall` - Verify connectivity to all servers (admin only)
- `/purgeunreachable` - Remove models hosted on unreachable servers (admin only)

**Model Management:**
- `/listmodels` - List all available Ollama models in the database
- `/selectmodel <model_id>` - Select a model by ID and view its details
- `/addmodel <ip> <port> <n> [info]` - Download a model to an Ollama server and add it to the database
- `/deletemodel <model_id>` - Delete a model from the server and database

**Search:**
- `/search <query>` - Quick search for models by name
- `/searchmodels <model_name> [sort_by] [descending] [limit]` - Search for models by name with sorting options
- `/modelsbyparam <parameter_size> [sort_by] [descending] [limit]` - Find models with specific parameter size
- `/allmodels [sort_by] [descending] [limit]` - List all models with sorting options
- `/models_with_servers [sort_by] [descending] [limit]` - List models with their server IPs and ports

**Interaction:**
- `/interact <model_id> <message> [system_prompt] [temperature] [max_tokens]` - Interact with a selected Ollama model
  - `model_id`: ID of the model to use
  - `message`: Your message/prompt to the model
  - `system_prompt` (optional): System prompt to set context
  - `temperature` (optional): Controls randomness (0.0 to 1.0, default 0.7)
  - `max_tokens` (optional): Maximum response length (default 1000)

- `/quickprompt <search_term> <prompt> [system_prompt] [temperature] [max_tokens] [param_size]` - All-in-one command to search, select and interact with a model
  - `search_term`: Part of the model name to search for
  - `prompt`: Your message/prompt to the model
  - `system_prompt` (optional): System prompt to set context
  - `temperature` (optional): Controls randomness (0.0 to 1.0, default 0.7)
  - `max_tokens` (optional): Maximum response length (default 1000)
  - `param_size` (optional): Parameter size of the model (e.g., 7B, 13B)

**Benchmark:**
- `/benchmark <model_id> [server_ip] [server_port] [model_name]` - Run benchmark on a specific model and server

**Maintenance:**
- `/cleanup` - Remove duplicate servers and models from the database
- `/refreshcommands` - Force refresh of bot commands (admin only)
- `/guild_sync` - Force sync commands to the current guild (admin only)
- `/ping` - Quick test to check if the bot is responding

**Troubleshooting:**
If models are unavailable:
1. Use `/verifyall` to check which servers and models are reachable 
2. Use `/purgeunreachable` to clean unreachable models from the database
3. Use `/syncserver` to refresh the models database for a specific server

**Command Visibility Issues:**
If commands are not appearing, administrators can:
1. Use `/guild_sync` to force commands to appear in the current server
2. Use `/refreshcommands` to refresh all commands
3. Wait up to 1 hour for Discord to globally cache all commands
"""

    if args.dry_run:
        print("\nProposed New Help Text:")
        print(new_help_text)
    else:
        # Update the help text in the file
        new_bot_code = help_text_pattern.sub(f'help_text = """{new_help_text}"""', bot_code)
        
        # Write back to the file
        with open(args.file, 'w') as f:
            f.write(new_bot_code)
        
        print(f"\nHelp text updated in {args.file}")
        print("Note: This script only updates the help text. To actually consolidate commands, you need to modify the command implementations.")

# Recommended implementation changes
print("\nRecommended Implementation Changes:")
print("""
1. Create a unified search command with a type parameter:
   - Implement a `/search` command with parameters:
     - type: "name", "param", "all"
     - query: search term
     - sort_by, descending, limit: as existing options

2. Create a unified list command with a type parameter:
   - Implement a `/list` command with parameters:
     - type: "models", "servers", "models_with_servers"
     - sort_by, descending, limit: as existing options

3. Consolidate refresh commands into one:
   - Implement a single `/refresh` command with parameters:
     - type: "commands", "guild", "all"
     - scope: "global", "guild"

These changes would reduce the total number of commands while maintaining all functionality.
""")

if __name__ == "__main__":
    pass 