#!/usr/bin/env python3
"""
Migrate to Unified Commands

This script helps migrate from the legacy command system to the unified commands system,
ensuring smooth transition and compatibility with PostgreSQL.
"""

import os
import sys
import logging
import argparse
import json
import importlib.util
from pathlib import Path
import shutil
import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("command_migration.log")
    ]
)
logger = logging.getLogger('command_migration')

def backup_file(file_path):
    """Make a backup of a file with timestamp"""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, skipping backup: {file_path}")
        return False
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak.{timestamp}"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {str(e)}")
        return False

def load_module_from_path(module_path, module_name):
    """Load a Python module from file path"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"Failed to load module {module_name} from {module_path}: {str(e)}")
        return None

def update_env_file(env_path, guild_id=None, client_id=None):
    """Update .env file with proper configuration"""
    if not os.path.exists(env_path):
        logger.warning(f".env file not found: {env_path}")
        return False
        
    # Backup the env file
    backup_file(env_path)
    
    # Read existing content
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Dictionary to track if variables are present
    env_vars = {
        'DISCORD_GUILD_ID': False,
        'DISCORD_CLIENT_ID': False,
        'DATABASE_TYPE': False
    }
    
    # Update existing variables
    for i, line in enumerate(lines):
        if line.strip().startswith('#'):
            continue
            
        if '=' in line:
            key, _ = line.split('=', 1)
            key = key.strip()
            
            if key == 'DISCORD_GUILD_ID' and guild_id:
                lines[i] = f"DISCORD_GUILD_ID={guild_id}\n"
                env_vars['DISCORD_GUILD_ID'] = True
            elif key == 'DISCORD_CLIENT_ID' and client_id:
                lines[i] = f"DISCORD_CLIENT_ID={client_id}\n"
                env_vars['DISCORD_CLIENT_ID'] = True
            elif key == 'DATABASE_TYPE':
                lines[i] = "DATABASE_TYPE=postgres\n"
                env_vars['DATABASE_TYPE'] = True
    
    # Add missing variables at the end
    if guild_id and not env_vars['DISCORD_GUILD_ID']:
        lines.append(f"DISCORD_GUILD_ID={guild_id}\n")
    
    if client_id and not env_vars['DISCORD_CLIENT_ID']:
        lines.append(f"DISCORD_CLIENT_ID={client_id}\n")
        
    if not env_vars['DATABASE_TYPE']:
        lines.append("DATABASE_TYPE=postgres\n")
    
    # Write updated content
    with open(env_path, 'w') as f:
        f.writelines(lines)
        
    logger.info(f"Updated .env file: {env_path}")
    return True

def create_command_mapping(discord_bot_file):
    """Create a mapping file for legacy commands to unified commands"""
    try:
        # Get the directory containing this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Define the mapping of legacy commands to unified commands
        command_mapping = {
            # Search commands
            "searchmodels": {"unified_command": "unified_search", "type": "name"},
            "modelsbyparam": {"unified_command": "unified_search", "type": "params"},
            "allmodels": {"unified_command": "unified_search", "type": "all"},
            "models_with_servers": {"unified_command": "unified_search", "type": "with_servers"},
            
            # Server commands
            "listservers": {"unified_command": "server", "action": "list"},
            "checkserver": {"unified_command": "server", "action": "check"},
            "syncserver": {"unified_command": "server", "action": "sync"},
            "serverinfo": {"unified_command": "server", "action": "info"},
            "verifyall": {"unified_command": "server", "action": "verify"},
            "purgeunreachable": {"unified_command": "server", "action": "purge"},
            
            # Admin commands
            "refreshcommands": {"unified_command": "admin", "action": "refresh"},
            "guild_sync": {"unified_command": "admin", "action": "guild_sync"},
            "refreshcommandsv2": {"unified_command": "admin", "action": "full_refresh"},
            "cleanup": {"unified_command": "admin", "action": "cleanup"},
            "updateallmodels": {"unified_command": "admin", "action": "update_models"},
            
            # Model commands
            "listmodels": {"unified_command": "model", "action": "list"},
            "selectmodel": {"unified_command": "model", "action": "select"},
            "addmodel": {"unified_command": "model", "action": "add"},
            "deletemodel": {"unified_command": "model", "action": "delete"},
            "currentmodel": {"unified_command": "model", "action": "current"},
            
            # Chat commands
            "interact": {"unified_command": "chat"},
            "quickprompt": {"unified_command": "chat"},
            "benchmark": {"unified_command": "benchmark"},
            
            # Help command
            "help": {"unified_command": "help"}
        }
        
        # Save mapping to a JSON file
        mapping_file = os.path.join(script_dir, "command_mapping.json")
        with open(mapping_file, 'w') as f:
            json.dump(command_mapping, f, indent=4)
            
        logger.info(f"Command mapping saved to: {mapping_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to create command mapping: {str(e)}")
        return False

def inject_command_redirects(discord_bot_file):
    """Inject code to redirect legacy commands to unified commands"""
    if not os.path.exists(discord_bot_file):
        logger.error(f"Discord bot file not found: {discord_bot_file}")
        return False
    
    # Backup the file
    if not backup_file(discord_bot_file):
        return False
    
    try:
        # Read the file content
        with open(discord_bot_file, 'r') as f:
            content = f.read()
        
        # Check if the redirects are already implemented
        if "# Legacy command redirects" in content:
            logger.info("Command redirects already implemented, skipping.")
            return True
        
        # Find the right insertion point - after imports but before command definitions
        # This is a simplistic approach and might need manual tuning
        import_section_end = content.find("# Global aiohttp session for API requests")
        if import_section_end == -1:
            import_section_end = content.find("bot = commands.Bot(")
        
        if import_section_end == -1:
            logger.error("Could not find suitable insertion point in discord_bot.py")
            return False
        
        # Prepare the redirection code
        redirect_code = """
# Legacy command redirects - added by migration script
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_mapping.json"), 'r') as f:
        LEGACY_TO_UNIFIED = json.load(f)
except Exception as e:
    logger.warning(f"Failed to load command mapping: {str(e)}")
    LEGACY_TO_UNIFIED = {}

# Wrapper for legacy commands to redirect to unified commands
def legacy_command_wrapper(legacy_name):
    async def wrapper(interaction, **kwargs):
        if legacy_name not in LEGACY_TO_UNIFIED:
            await interaction.response.send_message(f"Command '{legacy_name}' is not configured for redirection.", ephemeral=True)
            return
            
        mapping = LEGACY_TO_UNIFIED[legacy_name]
        unified_command = mapping["unified_command"]
        
        # Get the unified command from the command tree
        command = bot.tree.get_command(unified_command)
        if not command:
            await interaction.response.send_message(
                f"Error: Unified command '{unified_command}' not found. Please use the new command directly: /{unified_command}",
                ephemeral=True
            )
            return
        
        # Add mapping parameters to kwargs
        for param, value in mapping.items():
            if param != "unified_command" and param not in kwargs:
                kwargs[param] = value
        
        try:
            # Invoke the unified command with the parameters
            logger.info(f"Redirecting legacy command '{legacy_name}' to '{unified_command}' with params: {kwargs}")
            await command.callback(interaction, **kwargs)
        except Exception as e:
            logger.error(f"Error redirecting command {legacy_name} to {unified_command}: {str(e)}")
            await interaction.response.send_message(
                f"Error executing redirected command: {str(e)}\\n\\n"
                f"Please use the new command directly: /{unified_command}",
                ephemeral=True
            )
    
    return wrapper

"""
        
        # Insert the redirection code
        new_content = content[:import_section_end] + redirect_code + content[import_section_end:]
        
        # Find where command registration happens
        command_reg_section = new_content.find("@bot.event\nasync def on_ready():")
        if command_reg_section == -1:
            logger.warning("Could not find on_ready event handler. Redirection might not work automatically.")
        else:
            # Add code to register legacy command redirects
            legacy_reg_code = """
    # Register legacy command redirects
    logger.info("Registering legacy command redirects")
    try:
        for legacy_name in LEGACY_TO_UNIFIED:
            # Skip if the command is already registered
            if bot.tree.get_command(legacy_name, guild=MY_GUILD):
                continue
                
            # Create a dummy command description
            mapping = LEGACY_TO_UNIFIED[legacy_name]
            unified_cmd = mapping["unified_command"]
            description = f"Legacy command - redirects to /{unified_cmd}"
                
            # Register the command with the legacy name but redirect to unified command
            command = app_commands.Command(
                name=legacy_name,
                description=description,
                callback=legacy_command_wrapper(legacy_name),
                parent=None
            )
            bot.tree.add_command(command, guild=MY_GUILD)
            logger.info(f"Registered legacy redirect: /{legacy_name} -> /{unified_cmd}")
    except Exception as e:
        logger.error(f"Error setting up legacy command redirects: {str(e)}")
"""
            
            # Find the end of the on_ready function
            on_ready_end = new_content.find("@bot.tree.command", command_reg_section)
            if on_ready_end == -1:
                on_ready_end = new_content.find("def main():", command_reg_section)
            
            if on_ready_end != -1:
                # Find the last line of the on_ready function
                last_line = new_content.rfind("\n", command_reg_section, on_ready_end)
                if last_line != -1:
                    # Insert the legacy registration code before the end of on_ready
                    new_content = new_content[:last_line] + legacy_reg_code + new_content[last_line:]
        
        # Write the modified content back
        with open(discord_bot_file, 'w') as f:
            f.write(new_content)
            
        logger.info(f"Successfully injected command redirects into: {discord_bot_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to inject command redirects: {str(e)}")
        return False

def check_postgresql_connection():
    """Check if PostgreSQL is properly configured and accessible"""
    try:
        # Try to import psycopg2
        import psycopg2
        
        # Load database module to get connection parameters
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_module_path = os.path.join(script_dir, "database.py")
        
        if not os.path.exists(db_module_path):
            logger.error(f"Database module not found: {db_module_path}")
            return False
            
        db_module = load_module_from_path(db_module_path, "database")
        if not db_module:
            return False
            
        # Check if needed variables are available in the module
        if not all(hasattr(db_module, var) for var in ['PG_DB_NAME', 'PG_DB_USER', 'PG_DB_PASSWORD', 'PG_DB_HOST', 'PG_DB_PORT']):
            logger.error("Database module is missing required variables")
            return False
            
        # Try to connect to PostgreSQL
        logger.info(f"Testing PostgreSQL connection to {db_module.PG_DB_USER}@{db_module.PG_DB_HOST}:{db_module.PG_DB_PORT}/{db_module.PG_DB_NAME}")
        
        try:
            conn = psycopg2.connect(
                dbname=db_module.PG_DB_NAME,
                user=db_module.PG_DB_USER,
                password=db_module.PG_DB_PASSWORD,
                host=db_module.PG_DB_HOST,
                port=db_module.PG_DB_PORT,
                connect_timeout=10
            )
            
            # Test query
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            conn.close()
            
            logger.info(f"Successfully connected to PostgreSQL: {version}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
            return False
    except ImportError:
        logger.error("psycopg2 package not installed. Please install it with: pip install psycopg2-binary")
        return False
    except Exception as e:
        logger.error(f"Error checking PostgreSQL connection: {str(e)}")
        return False

def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(description='Migrate to unified commands system')
    parser.add_argument('--force', action='store_true', help='Force migration even if checks fail')
    parser.add_argument('--guild-id', type=str, help='Discord guild ID for command registration')
    parser.add_argument('--bot-file', type=str, default='direct_guild_bot.py', help='Discord bot file to modify')
    args = parser.parse_args()
    
    logger.info("Starting migration to unified commands system")
    
    # Set paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    discord_bot_file = os.path.join(script_dir, args.bot_file)
    env_file = os.path.join(script_dir, '.env')
    
    # Check if files exist
    if not os.path.exists(discord_bot_file):
        logger.error(f"Discord bot file not found: {discord_bot_file}")
        return False
        
    if not os.path.exists(env_file):
        logger.error(f".env file not found: {env_file}")
        return False
    
    # Check PostgreSQL connection
    pg_ok = check_postgresql_connection()
    if not pg_ok and not args.force:
        logger.error("PostgreSQL check failed. Fix database connection or use --force to continue anyway.")
        return False
    
    # Get GUILD_ID from arguments or environment
    guild_id = args.guild_id
    if not guild_id:
        # Try to get from environment
        guild_id = os.getenv('DISCORD_GUILD_ID')
    
    # Extract client ID from token if possible
    from dotenv import load_dotenv
    load_dotenv(env_file)
    
    token = os.getenv('DISCORD_TOKEN')
    client_id = None
    
    if token:
        try:
            import base64
            token_parts = token.split('.')
            if len(token_parts) >= 1:
                # Add padding if needed
                first_part = token_parts[0]
                padding = '=' * (4 - len(first_part) % 4)
                
                # Decode the first part
                try:
                    decoded = base64.b64decode(first_part + padding).decode('utf-8')
                    client_id = decoded
                    logger.info(f"Extracted client ID from token: {client_id}")
                except:
                    logger.warning("Failed to extract client ID from token")
        except:
            pass
    
    # Update .env file
    env_updated = update_env_file(env_file, guild_id, client_id)
    if not env_updated and not args.force:
        logger.error("Failed to update .env file. Use --force to continue anyway.")
        return False
    
    # Create command mapping
    mapping_created = create_command_mapping(discord_bot_file)
    if not mapping_created and not args.force:
        logger.error("Failed to create command mapping. Use --force to continue anyway.")
        return False
    
    # Inject command redirects
    redirects_injected = inject_command_redirects(discord_bot_file)
    if not redirects_injected and not args.force:
        logger.error("Failed to inject command redirects. Use --force to continue anyway.")
        return False
    
    # Create a README file with instructions
    readme_path = os.path.join(script_dir, "UNIFIED_COMMANDS_README.md")
    with open(readme_path, 'w') as f:
        f.write("""# Unified Commands Migration

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
""")
    
    logger.info(f"Created README with instructions: {readme_path}")
    
    # Print migration status
    print("\n==================================================")
    print("  MIGRATION TO UNIFIED COMMANDS COMPLETED")
    print("==================================================\n")
    
    print(f"PostgreSQL Check: {'✅ Passed' if pg_ok else '⚠️ Failed'}")
    print(f"Environment Update: {'✅ Updated' if env_updated else '⚠️ Not updated'}")
    print(f"Command Mapping: {'✅ Created' if mapping_created else '⚠️ Not created'}")
    print(f"Command Redirects: {'✅ Injected' if redirects_injected else '⚠️ Not injected'}")
    
    print("\nNEXT STEPS:")
    print("1. Run fix_permissions.py to get proper bot invite URL")
    print("2. Re-invite bot with administrator permissions")
    print("3. Run guild_unified_commands.py to register commands with proper permissions")
    print("4. Test the commands and check for any issues")
    print("\nSee UNIFIED_COMMANDS_README.md for more details.")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 