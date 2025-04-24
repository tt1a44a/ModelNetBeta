# PostgreSQL Migration Implementation Plan

## Overview
This plan outlines the specific steps required to complete the migration from SQLite to PostgreSQL for the Ollama Scanner project. The database schema migration has already been completed, but code changes are still needed to ensure compatibility with PostgreSQL.

## Current State Analysis

Based on examination of the codebase:

- `database.py` has a dual-database architecture that supports both SQLite and PostgreSQL
- `db_connection_pool.py` implements a connection pool for PostgreSQL
- Environment variables in `.env` are set up for both database types
- There are several linter errors in `ollama_scanner.py` related to incomplete database migration
- Shell scripts like `run_scanner.sh` and `run_pruner.sh` still use SQLite-specific commands

## Implementation Progress

### Phase 1: Fix the Database Abstraction Layer - ✅ COMPLETED

1. **Update Database Class in database.py** - ✅ COMPLETED
   - [x] Database class exists with static methods for common operations
   - [x] Fix cursor initialization lines: `cursor = # Using Database methods instead of cursor`
   - [x] Fix the `Database.fetch_one(query, params)` and `Database.fetch_all(query, params)` calls
   - [x] Ensure proper transaction handling and autocommit settings

2. **Improve Connection Pool Management** - ✅ COMPLETED
   - [x] Verify that `DatabasePool` in `db_connection_pool.py` is properly implemented
   - [x] Fix cursor initialization in test connection: `with # Using Database methods instead of cursor as cursor:`
   - [x] Fix context manager in `DatabaseConnection.__enter__` and `DatabaseConnection.__exit__`

### Phase 2: Update Shell Scripts - ✅ COMPLETED

1. **Update `run_scanner.sh`** - ✅ COMPLETED
   - [x] Remove SQLite-specific optimization code (lines 35-47)
   - [x] Remove WAL mode checks and setup
   - [x] Remove database file symlink creation (lines 50-59)
   - [x] Replace SQLite-specific database initialization
   - [x] Update dependency check to include psycopg2 instead of sqlite3
   - [x] Replace SQLite-specific metadata operations (lines 142-148, 192-200)

2. **Update `run_pruner.sh`** - ✅ COMPLETED
   - [x] Remove SQLite-specific optimization code
   - [x] Remove WAL mode checks and setup
   - [x] Remove database file symlink creation
   - [x] Update dependency check to include psycopg2 instead of sqlite3
   - [x] Replace SQLite-specific metadata operations

3. **Update or Create `setup_database.sh`** - ✅ COMPLETED
   - [x] Add PostgreSQL initialization support
   - [x] Test PostgreSQL connection
   - [x] Create necessary tables if not already created

### Phase 3: Fix Core Scanner Code - ✅ COMPLETED

1. **Fix Linter Errors in `ollama_scanner.py`** - ✅ COMPLETED
   - [x] Fix all cursor assignment statements
   - [x] Fix all instances of Database.fetch_one and Database.fetch_all calls
   - [x] Update direct SQL calls to use parameterized queries with `%s` instead of `?`

2. **Fix Transactions in Scanner Code** - ✅ COMPLETED
   - [x] Replace direct rollback calls with Database transaction methods
   - [x] Ensure proper connection cleanup

### Phase 4: Update Other Files - 🔄 IN PROGRESS

1. **Fix Discord Bot Database Interactions** - 🔄 IN PROGRESS
   - [x] Update setup_database function in discord_bot.py
   - [x] Update get_database_stats function in discord_bot.py
   - [x] Update get_servers function in register_unified_commands.py
   - [x] Update setup_additional_tables in unified_commands.py
   - [x] Update get_user_selected_model function in unified_commands.py
   - [x] Update save_user_model_selection function in unified_commands.py
   - [x] Update save_chat_history function in unified_commands.py
   - [x] Update get_servers function in ollama_models.py
   - [ ] Fix remaining cursor initializations in discord_bot.py:
     - [ ] Fix get_scan_date function
     - [ ] Fix db_info command
     - [ ] Fix linter errors related to indentation in on_ready function
     - [ ] Fix various command functions (search_models, models_by_param, etc.)
   - [ ] Fix remaining cursor initializations in ollama_models.py

2. **Update Auxiliary Scripts** - 🔄 IN PROGRESS
   - [ ] Fix cursor initializations in DiscordBot/prune_bad_endpoints.py
   - [ ] Fix cursor initializations in DiscordBot/update_ollama_models.py
   - [ ] Fix cursor initializations in DiscordBot/commands_for_syncing.py
   - [ ] Fix cursor initializations in DiscordBot/setup_fix.py
   - [ ] Fix cursor initializations in DiscordBot/debug_ollama_endpoints.py
   - [ ] Fix cursor initializations in DiscordBot/sync_endpoints_to_servers.py

### Phase 5: Testing

1. **Basic Functionality Testing**
   - [ ] Test database connection
   - [ ] Test simple queries
   - [ ] Test transactions
   - [ ] Create a test script to verify database operations

2. **Integration Testing**
   - [ ] Test Discord bot functionality
   - [ ] Test scanner functionality
   - [ ] Test pruner functionality
   - [ ] Create automated tests for critical functions

3. **Performance Testing**
   - [ ] Test with multiple concurrent connections
   - [ ] Compare query performance with SQLite
   - [ ] Optimize slow queries if needed

## Next Steps

1. Continue fixing cursor initialization issues in discord_bot.py
2. Fix the remaining linter errors in each file
3. Create a testing plan for verifying the migration
4. Test functionality with the new PostgreSQL setup
5. Document the migration process for future reference 