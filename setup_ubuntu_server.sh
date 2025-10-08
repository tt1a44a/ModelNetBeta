#!/bin/bash
# Setup script for ModelNetBeta on Ubuntu Server
# Run this script to get the entire system up and running

# Update system packages
sudo apt update
sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3 python3-pip python3-venv postgresql-client docker.io docker-compose git

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (logout/login required for this to take effect)
sudo usermod -aG docker $USER

# Clone the repository (adjust URL as needed)
# git clone https://github.com/yourusername/ModelNetBeta.git
# cd ModelNetBeta

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python requirements
pip install -r requirements.txt
pip install -r DiscordBot/requirements.txt

# Create .env file with database configuration
cat > .env << 'EOF'
# Database Configuration
DATABASE_TYPE=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=ollama_scanner
POSTGRES_USER=ollama
POSTGRES_PASSWORD=ollama_scanner_password

# API Keys - ADD YOUR ACTUAL KEYS HERE
SHODAN_API_KEY=your_shodan_api_key_here
CENSYS_API_ID=your_censys_api_id_here
CENSYS_API_SECRET=your_censys_api_secret_here

# Discord Bot Configuration - ADD YOUR DISCORD BOT TOKEN HERE
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Database Connection Pool Settings
DB_MIN_CONNECTIONS=10
DB_MAX_CONNECTIONS=100
DB_CONNECTION_TIMEOUT=10
DB_POOL_CLEANUP_INTERVAL=300

# PgAdmin Configuration (optional)
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin
PGADMIN_PORT=5050
EOF

# Fix Docker Compose version if needed
sed -i 's/version: .*/version: "3.3"/' docker-compose.yml

# Start PostgreSQL with Docker
docker-compose up -d postgres

# Wait for PostgreSQL to start
sleep 15

# Create database if it doesn't exist
docker exec ollama_scanner_postgres psql -U ollama -d postgres -c "CREATE DATABASE ollama_scanner;" 2>/dev/null || echo "Database already exists"

# Setup database schema
docker exec -i ollama_scanner_postgres psql -U ollama -d ollama_scanner < schema/postgres_schema.sql

# Create the fixed query tool if it doesn't exist
if [ ! -f "query_models_fixed.py" ]; then
    cat > query_models_fixed.py << 'EOF'
#!/usr/bin/env python3
"""
Query tool for searching the Ollama Scanner database
"""

import os
import sys
import argparse
from database import Database, init_database

def checkDB():
    """Check if database has data"""
    try:
        # how many servers do we have?
        count = Database.fetch_one("SELECT COUNT(*) FROM servers")[0]
        
        if count == 0:
            print("No data found in the database.")
            print("Run ollama_scanner.py first to collect data.")
            return False
        
        print(f"Database contains {count} servers.")
        return True
    except Exception as e:
        print(f"Error checking database: {e}")
        return False

def listServers():
    """List all servers in the database"""
    try:
        servers = Database.fetch_all("SELECT * FROM servers ORDER BY scan_date DESC")
        
        if not servers:
            print("No servers found in database.")
            return
        
        print(f"\nFound {len(servers)} servers:")
        print("-" * 80)
        print(f"{'ID':<5} {'IP':<15} {'Port':<6} {'Scan Date':<20}")
        print("-" * 80)
        
        for server in servers:
            print(f"{server[0]:<5} {server[1]:<15} {server[2]:<6} {str(server[3]):<20}")
            
    except Exception as e:
        print(f"Error listing servers: {e}")

def listModels():
    """List all models in the database"""
    try:
        models = Database.fetch_all("SELECT * FROM models ORDER BY name")
        
        if not models:
            print("No models found in database.")
            return
        
        print(f"\nFound {len(models)} models:")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<30} {'Server ID':<10} {'Params':<10}")
        print("-" * 80)
        
        for model in models:
            print(f"{model[0]:<5} {model[1]:<30} {model[2]:<10} {model[3] or 'N/A':<10}")
            
    except Exception as e:
        print(f"Error listing models: {e}")

def searchModels(search_term):
    """Search for models by name"""
    try:
        query = "SELECT * FROM models WHERE name ILIKE %s ORDER BY name"
        models = Database.fetch_all(query, (f"%{search_term}%",))
        
        if not models:
            print(f"No models found matching '{search_term}'.")
            return
        
        print(f"\nFound {len(models)} models matching '{search_term}':")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<30} {'Server ID':<10} {'Params':<10}")
        print("-" * 80)
        
        for model in models:
            print(f"{model[0]:<5} {model[1]:<30} {model[2]:<10} {model[3] or 'N/A':<10}")
            
    except Exception as e:
        print(f"Error searching models: {e}")

def main():
    parser = argparse.ArgumentParser(description='Query Ollama Scanner database')
    parser.add_argument('command', choices=['servers', 'models', 'search'], 
                       help='Command to execute')
    parser.add_argument('search_term', nargs='?', 
                       help='Search term for search command')
    
    args = parser.parse_args()
    
    # Initialize database
    init_database()
    
    if args.command == 'servers':
        if checkDB():
            listServers()
    elif args.command == 'models':
        if checkDB():
            listModels()
    elif args.command == 'search':
        if not args.search_term:
            print("Error: search command requires a search term")
            return
        if checkDB():
            searchModels(args.search_term)

if __name__ == "__main__":
    main()
EOF
fi

# Make scripts executable
chmod +x run_scanner.sh
chmod +x run_pruner.sh
chmod +x run_both.sh
chmod +x setup_database.sh
chmod +x query_models_fixed.py
chmod +x DiscordBot/run_bot.sh
chmod +x DiscordBot/run_scanner.sh
chmod +x DiscordBot/run_pruner.sh
chmod +x DiscordBot/run_both.sh
chmod +x DiscordBot/setup_database.sh

# Test the system
echo "Testing system components..."
source venv/bin/activate

# Test scanner
if python ollama_scanner.py --help > /dev/null 2>&1; then
    echo "Scanner: OK"
else
    echo "Scanner: ERROR"
fi

# Test pruner
if python prune_bad_endpoints.py --help > /dev/null 2>&1; then
    echo "Pruner: OK"
else
    echo "Pruner: ERROR"
fi

# Test query tool (check if file exists first)
if [ -f "query_models_fixed.py" ]; then
    if python query_models_fixed.py servers > /dev/null 2>&1; then
        echo "Query Tool: OK"
    else
        echo "Query Tool: ERROR"
    fi
else
    echo "Query Tool: FILE NOT FOUND"
fi

echo ""
echo "Setup complete!"
echo ""
echo "IMPORTANT: Edit the .env file and add your actual API keys:"
echo "  - SHODAN_API_KEY=your_actual_shodan_key"
echo "  - CENSYS_API_ID=your_actual_censys_id"
echo "  - CENSYS_API_SECRET=your_actual_censys_secret"
echo "  - DISCORD_BOT_TOKEN=your_discord_bot_token_here"
echo ""
echo "To start the system:"
echo "  # Scanner only:"
echo "  ./run_scanner.sh --method shodan --limit 100"
echo ""
echo "  # Scanner + Pruner:"
echo "  ./run_both.sh --scanner-method shodan --scanner-threads 5 --pruner-workers 5"
echo ""
echo "  # Discord Bot:"
echo "  cd DiscordBot && ./run_bot.sh"
echo ""
echo "  # Query database:"
echo "  python query_models_fixed.py servers"
echo "  python query_models_fixed.py models"
echo "  python query_models_fixed.py search llama"
