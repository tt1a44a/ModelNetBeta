#!/bin/bash
# Script to install required dependencies for the Discord Bot

echo "Setting up dependencies for the Discord Bot..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Python 3 is required but not installed. Please install Python 3 first."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null
then
    echo "pip3 is required but not installed. Installing pip..."
    python3 -m ensurepip --upgrade
fi

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install or upgrade dependencies
echo "Installing required packages..."
pip install --upgrade pip
pip install -r requirements.txt || {
    echo "requirements.txt not found. Installing core dependencies..."
    pip install discord.py
    pip install python-dotenv
    pip install aiohttp
    pip install psycopg2-binary
    
    # Create requirements.txt
    echo "discord.py>=2.0.0" > requirements.txt
    echo "python-dotenv>=0.19.0" >> requirements.txt
    echo "aiohttp>=3.8.0" >> requirements.txt
    echo "psycopg2-binary>=2.9.3" >> requirements.txt
    
    echo "Created requirements.txt with core dependencies."
}

# Create a .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file template..."
    echo "# Discord Bot Configuration" > .env
    echo "DISCORD_TOKEN=your_discord_bot_token_here" >> .env
    echo "# Database Configuration" >> .env
    echo "DB_TYPE=sqlite  # Options: postgres, sqlite" >> .env
    echo "# PostgreSQL settings (if using postgres)" >> .env
    echo "POSTGRES_HOST=localhost" >> .env
    echo "POSTGRES_PORT=5432" >> .env
    echo "POSTGRES_DB=ollama_db" >> .env
    echo "POSTGRES_USER=postgres" >> .env
    echo "POSTGRES_PASSWORD=password" >> .env
    echo "# SQLite settings (if using sqlite)" >> .env
    echo "SQLITE_DB=ollama_instances.db" >> .env
    echo "Please update the .env file with your actual configuration values."
fi

echo "Setup complete! You can now run the bot with: python discord_bot.py"
echo "Don't forget to update your .env file with your Discord token and database settings."

# Deactivate virtual environment
deactivate 