# Added by migration script
from database import Database, init_database

import os
import sys
import re
import json
import time
import aiohttp
import discord
import asyncio
import logging
import argparse
import threading
import emoji
from datetime import datetime, timedelta
from dotenv import load_dotenv
from discord import app_commands
from discord.ext import commands, tasks
import socket

# TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: DB_FILE = "ollama_instances.db"
# Our custom modules
try:
    from commands_for_syncing import Commands, get_commands
except ImportError:
    print("Error: commands_for_syncing.py not found. Make sure it's in the same directory.")
    sys.exit(1)
    
# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"discord_bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    logger.error("No Discord bot token found. Set the DISCORD_BOT_TOKEN environment variable.")
    sys.exit(1)

# Initialize database
init_database()

# Function to format model info for display
def format_model_info(model_info):
    """Format model information for display in a Discord embed"""
    if not model_info:
        return "No model information available"
        
    formatted = []
    for field, value in model_info.items():
        formatted.append(f"**{field.replace('_', ' ').title()}**: {value}")
    
    return "\n".join(formatted)

# Check if a server is accessible
async def check_server_connectivity(ip, port):
    """Check if a server is accessible by making a request to /api/tags"""
    url = f"http://{ip}:{port}/api/tags"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    return True, await response.json()
                else:
                    return False, f"Server returned status {response.status}"
    except asyncio.TimeoutError:
        return False, "Connection timed out"
    except Exception as e:
        return False, str(e)

# Function to get statistics about the database
def get_database_stats():
    try:
        # Get endpoint count
        query = "SELECT COUNT(*) FROM servers"
        endpoint_count = Database.fetch_one(query)[0]
        
        # Get total model count
        query = "SELECT COUNT(*) FROM models"
        total_models = Database.fetch_one(query)[0]
        
        # Get unique model count
        query = "SELECT COUNT(DISTINCT name) FROM models"
        unique_models = Database.fetch_one(query)[0]
        
        # Get parameter size distribution
        query = "SELECT parameter_size, COUNT(*) FROM models WHERE parameter_size IS NOT NULL GROUP BY parameter_size ORDER BY COUNT(*) DESC"
        param_counts = Database.fetch_all(query)
        
        # Get quantization level distribution
        query = "SELECT quantization_level, COUNT(*) FROM models WHERE quantization_level IS NOT NULL GROUP BY quantization_level ORDER BY COUNT(*) DESC"
        quant_counts = Database.fetch_all(query)
        
        # Get top models
        query = "SELECT name, COUNT(*) FROM models GROUP BY name ORDER BY COUNT(*) DESC LIMIT 10"
        top_models = Database.fetch_all(query)
        
        return {
            "endpoint_count": endpoint_count,
            "total_models": total_models,
            "unique_models": unique_models,
            "parameter_sizes": param_counts,
            "quantization_levels": quant_counts,
            "top_models": top_models
        }
        
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return None

# Function to search for servers
def search_servers(search=None, limit=10):
    try:
        if search:
            # Search by IP
            query = "SELECT id, ip, port, scan_date FROM servers WHERE ip LIKE ? ORDER BY scan_date DESC LIMIT ?"
            results = Database.fetch_all(query, (f"%{search}%", limit))
            
            if not results:
                # Try searching by model name
                query = '''
                    SELECT s.id, s.ip, s.port, s.scan_date 
                    FROM servers s
                    JOIN models m ON s.id = m.server_id
                    WHERE m.name LIKE ?
                    ORDER BY s.scan_date DESC
                    LIMIT ?
                '''
                results = Database.fetch_all(query, (f"%{search}%", limit))
            
            return results
        else:
            # No search term, return recent servers
            query = "SELECT id, ip, port, scan_date FROM servers ORDER BY scan_date DESC LIMIT ?"
            results = Database.fetch_all(query, (limit,))
            return results
        
    except Exception as e:
        logger.error(f"Error searching servers: {e}")
        return []

# Function to get server details by IP
def get_server_by_ip(ip_input):
    try:
        # Clean IP
        clean_ip = ip_input.strip()
        
        # Check if port is specified
        if ":" in clean_ip:
            clean_ip, port_str = clean_ip.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                return None, "Invalid port number."
                
            # Check for server by IP and port
            query = "SELECT id, scan_date FROM servers WHERE ip = ? AND port = ?"
            servers = Database.fetch_all(query, (clean_ip, port))
            
            if not servers:
                return None, f"No server found with IP {clean_ip} and port {port}."
            
            return servers[0], None
        else:
            # No port specified, list all servers with this IP
            query = "SELECT id, port, scan_date FROM servers WHERE ip = ?"
            servers = Database.fetch_all(query, (clean_ip,))
            
            if not servers:
                return None, f"No servers found with IP {clean_ip}."
            
            if len(servers) == 1:
                return servers[0], None
            else:
                server_list = [f"{clean_ip}:{s[1]} (last scan: {s[2]})" for s in servers]
                return None, f"Multiple servers found with IP {clean_ip}. Please specify a port:\n" + "\n".join(server_list)
    
    except Exception as e:
        logger.error(f"Error getting server by IP: {e}")
        return None, f"Error: {str(e)}"

# Function to get models for a server
def get_models_for_server(server_id):
    try:
        query = """
            SELECT id, name, parameter_size, quantization_level, size_mb
            FROM models
            WHERE server_id = ?
            ORDER BY name
        """
        models = Database.fetch_all(query, (server_id,))
        return models
    except Exception as e:
        logger.error(f"Error getting models for server {server_id}: {e}")
        return []

# Function to search for models
def search_models(search=None, limit=10):
    try:
        if search:
            query = """
                SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                FROM models m
                JOIN servers s ON m.server_id = s.id
                WHERE m.name LIKE ?
                ORDER BY m.name, s.scan_date DESC
                LIMIT ?
            """
            results = Database.fetch_all(query, (f"%{search}%", limit))
        else:
            query = """
                SELECT m.id, m.name, m.parameter_size, m.quantization_level, s.ip, s.port
                FROM models m
                JOIN servers s ON m.server_id = s.id
                ORDER BY s.scan_date DESC
                LIMIT ?
            """
            results = Database.fetch_all(query, (limit,))
        
        return results
    except Exception as e:
        logger.error(f"Error searching models: {e}")
        return []

# Function to find and remove duplicate servers
def find_duplicates():
    try:
        # Find servers with the same IP and port
        query = """
            SELECT s1.id, s1.ip, s1.port, s1.scan_date, s2.id, s2.scan_date
            FROM servers s1
            JOIN servers s2 ON s1.ip = s2.ip AND s1.port = s2.port AND s1.id < s2.id
            ORDER BY s1.ip, s1.port
        """
        dupes = Database.fetch_all(query)
        
        if not dupes:
            return "No duplicate servers found."
            
        result_msg = []
        removed = 0
        
        for dupe in dupes:
            keep_id, keep_ip, keep_port, keep_date, remove_id, remove_date = dupe
            
            # Find models for the server to be removed
            query = "SELECT id FROM models WHERE server_id = ?"
            dupe_models = Database.fetch_all(query, (remove_id,))
            
            # Delete the duplicate server
            Database.execute("DELETE FROM servers WHERE id = ?", (remove_id,))
            
            # Log the removal
            result_msg.append(f"Removed duplicate server {keep_ip}:{keep_port} (ID: {remove_id}, scan date: {remove_date})")
            result_msg.append(f"  Keeping server with ID: {keep_id}, scan date: {keep_date}")
            result_msg.append(f"  Removed {len(dupe_models)} associated models")
            
            removed += 1
        
        if removed > 0:
            result_msg.insert(0, f"Removed {removed} duplicate servers.")
        
        return "\n".join(result_msg)
        
    except Exception as e:
        logger.error(f"Error finding duplicates: {e}")
        return f"Error finding duplicates: {str(e)}"

# Function to get server scan date
def get_scan_date(server_id):
    try:
        query = "SELECT scan_date FROM servers WHERE id = ?"
        scan_date = Database.fetch_one(query, (server_id,))[0]
        return scan_date
    except Exception as e:
        logger.error(f"Error getting scan date for server {server_id}: {e}")
        return None

# Function to get model info by model ID
def get_model_info(model_id):
    try:
        query = """
            SELECT m.id, m.name, m.parameter_size, m.quantization_level, m.size_mb, s.ip, s.port
            FROM models m
            JOIN servers s ON m.server_id = s.id
            WHERE m.id = ?
        """
        model_info = Database.fetch_one(query, (model_id,))
        return model_info
    except Exception as e:
        logger.error(f"Error getting model info for model {model_id}: {e}")
        return None

# Function to delete a model
def delete_model(model_id):
    try:
        Database.execute("DELETE FROM models WHERE id = ?", (model_id,))
        return True
    except Exception as e:
        logger.error(f"Error deleting model {model_id}: {e}")
        return False

# Function to run a custom query
def run_custom_query(query, parameters=None):
    try:
        results = Database.fetch_all(query, parameters)
        return results
    except Exception as e:
        logger.error(f"Error running custom query: {e}")
        return None

def validate_server_from_text(server_text):
    """Extract and validate server IP and port from text input"""
    if not server_text:
        return None, "Please provide a server address."
    
    # Clean up input
    server_text = server_text.strip()
    
    # Check if port is specified
    if ":" in server_text:
        ip, port_str = server_text.split(":", 1)
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                return None, "Port must be between 1 and 65535."
        except ValueError:
            return None, "Invalid port number."
    else:
        ip = server_text
        port = 11434  # Default Ollama port
    
    # Validate IP address format
    ip = ip.strip()
    try:
        socket.inet_aton(ip)
        return ip, port
    except:
        # Try to handle domain names
        try:
            resolved_ip = socket.gethostbyname(ip)
            return resolved_ip, port
        except:
            return None, f"Invalid IP address or hostname: {ip}"

# Define the Discord bot class
class OllamaBot(commands.Bot):
    """Custom Discord bot class for Ollama interactions"""
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.ready_event = asyncio.Event()
    
    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        self.ready_event.set()
    
    async def setup_hook(self):
        """Setup hook called before the bot starts"""
        self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        logger.info("Synced slash commands")

# Main function
def main():
    # Initialize database
    init_database()
    
    # Create the bot instance
    intents = discord.Intents.default()
    intents.message_content = True
    bot = OllamaBot(command_prefix="!", intents=intents)
    
    # Run the bot using the token
    bot.run(TOKEN)

# Run the main function
if __name__ == "__main__":
    main() 

def setup_database():
    """Set up the database schema if it doesn't exist"""
    try:
        conn = Database()
        # Using Database methods instead of cursor
        
        # Create servers table
        Database.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            port INTEGER,
            scan_date TEXT,
            UNIQUE(ip, port)
        )
        """)
        
        # Create models table
        Database.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            name TEXT,
            parameter_size TEXT,
            quantization_level TEXT,
            size_mb REAL,
            FOREIGN KEY (server_id) REFERENCES servers (id) ON DELETE CASCADE
        )
        """)
        
        # Create user_selected_models table
        Database.execute("""
        CREATE TABLE IF NOT EXISTS user_selected_models (
            user_id TEXT PRIMARY KEY,
            model_id INTEGER,
            selection_date TEXT,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        """)
        
        # Create index on model name for faster searches
        Database.execute("CREATE INDEX IF NOT EXISTS idx_models_name ON models (name)")
        Database.execute("CREATE INDEX IF NOT EXISTS idx_models_server_id ON models (server_id)")
        
        # Commit is handled by Database.execute

        # Close connection
        conn.close()
        
        logging.info("Database schema initialized")
    except Exception as e:
        logging.error(f"Error setting up database: {str(e)}") 