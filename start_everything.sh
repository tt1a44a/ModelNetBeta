#!/bin/bash
# Complete startup script for ModelNetBeta system

echo "===================================="
echo "    Starting ModelNetBeta System    "
echo "===================================="

# Navigate to project directory
cd /home/adam/Documents/git/ModelNetBeta

# Activate virtual environment
source venv/bin/activate

# Create DiscordBot .env file if it doesn't exist
if [ ! -f "DiscordBot/.env" ]; then
    echo "Creating DiscordBot .env file..."
    echo "Please add your Discord bot token to DiscordBot/.env file:"
    echo "DISCORD_BOT_TOKEN=your_token_here" > DiscordBot/.env
    echo "DiscordBot/.env file created with placeholder. Please edit it with your actual token."
fi

# Check if PostgreSQL is running
if ! docker ps | grep -q ollama_scanner_postgres; then
    echo "Starting PostgreSQL database..."
    docker-compose up -d postgres
    sleep 10
fi

# Start Scanner + Pruner in background
echo "Starting Scanner and Pruner..."
./run_both.sh --scanner-method shodan --scanner-threads 5 --pruner-workers 5 &
SCANNER_PID=$!

# Wait a moment for scanner to start
sleep 5

# Start Discord Bot in background
echo "Starting Discord Bot..."
cd DiscordBot
source ../venv/bin/activate
./run_bot.sh &
BOT_PID=$!

# Go back to main directory
cd ..

echo "===================================="
echo "     System Started Successfully    "
echo "===================================="
echo "Scanner/Pruner PID: $SCANNER_PID"
echo "Discord Bot PID: $BOT_PID"
echo ""
echo "To check status:"
echo "  ps aux | grep -E '(ollama_scanner|prune_bad_endpoints|discord_bot)' | grep -v grep"
echo ""
echo "To view logs:"
echo "  tail -f database.log"
echo "  tail -f DiscordBot/discord_bot.log"
echo ""
echo "To query database:"
echo "  python query_models_fixed.py servers"
echo "  python query_models_fixed.py models"
echo ""
echo "To stop everything:"
echo "  kill $SCANNER_PID $BOT_PID"
echo "===================================="
