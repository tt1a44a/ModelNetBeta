# Unified Command System

## Overview

This update introduces a streamlined command system that consolidates multiple redundant commands into unified command groups. This makes the bot easier to maintain and provides a more consistent user experience.

## Why Unified Commands?

The previous command system had many overlapping commands with similar functionality:
- Multiple ways to search models (`searchmodels`, `modelsbyparam`, etc.)
- Several server management commands (`listservers`, `checkserver`, etc.)
- Redundant administrative functions (`refreshcommands`, `refreshcommandsv2`, etc.)

The unified command system groups these by function rather than having many separate commands.

## Command Groups

### 1. Search Command (`/unified_search`)
Consolidates all model search functionality:
- Search by name
- Search by parameters
- List all models
- List models with their servers

### 2. Server Command (`/server`)
Handles all server-related operations:
- List all servers
- Check server connectivity
- Sync models with server
- Get detailed server info
- Verify all servers
- Purge unreachable servers

### 3. Admin Command (`/admin`)
For administrative tasks:
- Refresh commands
- Sync with guild
- Full refresh (commands + guilds)
- Database cleanup
- Update all models

### 4. Model Command (`/model`)
For model management:
- List models
- Select a model
- Add a model
- Delete a model

### 5. Chat Command (`/chat`)
For interactions with models:
- Interactive chat
- Quick prompt
- Benchmark

## Implementation Details

The unified commands are implemented through the following files:
- `unified_commands.py`: Core implementation of the unified commands
- `register_unified_commands.py`: Helper functions to integrate with the Discord bot

## Backward Compatibility

Legacy commands continue to work but are now mapped to their unified equivalents. This ensures a smooth transition for users while simplifying the codebase.

A mapping from legacy commands to unified commands is provided in `register_unified_commands.py`.

## Usage Guide

See the output of `/help` command for detailed usage information, or refer to the guide in the `create_usage_guide()` function in `register_unified_commands.py`.

## Future Development

Future commands should be added to the appropriate unified command group rather than creating new standalone commands. This keeps the command interface clean and consistent.

## Migrating Existing Code

When migrating existing command handlers to the unified system:
1. Identify which command group the functionality belongs to
2. Add the action as a new option in the appropriate command
3. Implement the handler in the unified command's callback
4. Update the command mapping in `register_unified_commands.py` 