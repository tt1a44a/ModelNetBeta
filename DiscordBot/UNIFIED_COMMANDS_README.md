# Unified Commands Migration

## What Changed?
This migration combines multiple specific commands into unified commands with type parameters.

## New Command Structure
- `/unified_search` - Replaces: searchmodels, modelsbyparam, allmodels
- `/server` - Replaces: listservers, checkserver, syncserver, etc.
- `/admin` - Replaces: refreshcommands, guild_sync, cleanup, etc.
- `/model` - Replaces: listmodels, selectmodel, addmodel, etc.
- `/chat` - Replaces: interact, quickprompt

## PostgreSQL Migration
The bot now uses PostgreSQL instead of SQLite. Make sure:
1. PostgreSQL is installed and running
2. Database user and permissions are properly set
3. DATABASE_TYPE=postgres in your .env file

## Fixing Permission Issues
If you see "Error syncing commands: 403 Forbidden (error code: 50001): Missing Access":

1. Run the fix_permissions.py script
2. Remove the bot from your server
3. Re-add the bot using the new invite URL with admin permissions
4. Run guild_unified_commands.py to register commands properly

## Legacy Commands
Legacy commands remain available but will redirect to their unified equivalents.
They may be removed in future versions.
