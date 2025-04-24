#!/usr/bin/env python3
"""
Quick script to add the setup_database function to discord_bot.py
"""

import re

# Added by migration script
from database import Database, init_database

def insert_setup_database():
    # Read the discord_bot.py file
    with open('discord_bot.py', 'r') as f:
        content = f.read()
    
    # Define the setup_database function
    setup_function = '''
def setup_database():
    """Set up the database tables if they don't exist yet"""
    try:
        # Ensure database directory exists
        db_dir = os.path.dirname(DB_FILE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        
        conn = Database()
        cursor = # Using Database methods instead of cursor
        
        # Create servers table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            port INTEGER,
            scan_date TEXT,
            UNIQUE(ip, port)
        )
        """)
        
        # Create models table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            name TEXT,
            parameter_size TEXT,
            quantization_level TEXT,
            size_mb REAL,
            FOREIGN KEY (server_id) REFERENCES servers (id),
            UNIQUE(server_id, name)
        )
        """)
        
        # Commit handled by Database methods
        conn.close()
        logger.info("Database setup complete")
    except Exception as e:
        logger.error(f"Database setup error: {str(e)}")
        raise
'''
    
    # Use regex to insert the setup_database function after DB_FILE
    # TODO: Replace SQLite-specific code: # TODO: Replace SQLite-specific code: pattern = re.compile(r'(DB_FILE = "ollama_instances\.db")')
    new_content = pattern.sub(r'\1\n' + setup_function, content)
    
    # Save the modified content back to discord_bot.py
    with open('discord_bot.py', 'w') as f:
        f.write(new_content)
    
    print("Successfully added setup_database function to discord_bot.py")

if __name__ == '__main__':
    insert_setup_database() 