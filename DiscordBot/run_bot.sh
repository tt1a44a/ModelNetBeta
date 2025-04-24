#!/bin/bash

# Set the environment variables explicitly
export DATABASE_TYPE=postgres
export POSTGRES_DB=ollama_scanner
export POSTGRES_USER=ollama
export POSTGRES_PASSWORD=ollama_scanner_password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5433

# Increase database connection pool parameters
export DB_MIN_CONNECTIONS=10
export DB_MAX_CONNECTIONS=100
export DB_CONNECTION_TIMEOUT=10
export DB_POOL_CLEANUP_INTERVAL=300  # 5 minutes

echo "Starting Ollama Scanner Discord Bot..."
echo "Database configuration:"
echo "  Type: $DATABASE_TYPE"
echo "  Connection Pool: min=$DB_MIN_CONNECTIONS, max=$DB_MAX_CONNECTIONS"

# Run the Discord bot
python3 discord_bot.py

# Handle exit
echo "Bot has stopped. Checking for database issues..."
if [ $? -ne 0 ]; then
    echo "Bot exited with an error. Check logs for details."
else
    echo "Bot shutdown normally."
fi 