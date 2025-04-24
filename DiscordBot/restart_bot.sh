#!/bin/bash
# restart_bot.sh
# Script to stop all running instances of the Discord bot and restart with new command setup

# Display banner
echo "================================================"
echo " Ollama Scanner Discord Bot - Restart Script"
echo "================================================"
echo

# Check if running as root/sudo (required for some process management)
if [ "$EUID" -ne 0 ]; then
  echo "[WARNING] Not running with sudo. Some operations might fail."
  echo "Consider running with: sudo $0"
  echo
fi

# Find and stop all running instances of the Discord bot
echo "[1/4] Finding and stopping existing Discord bot processes..."
BOT_PROCESSES=$(pgrep -f "python.*discord_bot\.py")

if [ -n "$BOT_PROCESSES" ]; then
    echo "Found running Discord bot processes (PIDs: $BOT_PROCESSES)"
    
    # Try to gracefully terminate each process
    for PID in $BOT_PROCESSES; do
        echo "Stopping Discord bot process: $PID"
        kill -15 $PID 2>/dev/null
    done
    
    # Wait a bit for graceful shutdown
    echo "Waiting for processes to terminate..."
    sleep 3
    
    # Check if processes are still running
    REMAINING=$(pgrep -f "python.*discord_bot\.py")
    if [ -n "$REMAINING" ]; then
        echo "Some processes did not terminate gracefully. Force killing..."
        for PID in $REMAINING; do
            echo "Force killing process: $PID"
            kill -9 $PID 2>/dev/null
        done
    fi
    
    echo "Discord bot processes stopped."
else
    echo "No running Discord bot processes found."
fi

# Make sure the virtual environment is active
echo "[2/4] Activating virtual environment..."
if [ -d "../venv/bin" ]; then
    source ../venv/bin/activate
elif [ -d "../venv/Scripts" ]; then
    source ../venv/Scripts/activate
else
    echo "Virtual environment not found in expected location."
    echo "Please manually activate your virtual environment and try again."
    exit 1
fi

# Verify Python and dependencies
echo "[3/4] Verifying Python installation and dependencies..."
python -c "import sys; print(f'Python version: {sys.version}')"

# Required packages
REQUIRED_PACKAGES="discord.py aiohttp"
for package in $REQUIRED_PACKAGES; do
    if ! python -c "import $package" 2>/dev/null; then
        echo "Required package '$package' is missing. Installing..."
        pip install $package
    fi
done

# Start the Discord bot in the background with nohup
echo "[4/4] Starting Discord bot with streamlined commands..."
cd "$(dirname "$0")"  # Ensure we're in the DiscordBot directory

# Create a log file with timestamp
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="discord_bot_$TIMESTAMP.log"

# Start the bot in the background, redirecting output to the log file
nohup python discord_bot.py > "$LOG_FILE" 2>&1 &

# Get the PID of the new process
NEW_PID=$!
echo "Discord bot started with PID: $NEW_PID"
echo "Log file: $LOG_FILE"

# Give it a moment to initialize
sleep 2

# Check if process is still running
if ps -p $NEW_PID > /dev/null; then
    echo "Discord bot successfully started!"
    echo "Available commands:"
    echo "  - /manage_models (add/delete)"
    echo "  - /quickprompt"
    echo "  - /list_models"
    echo "  - /db_info"
    echo "  - /chat"
    echo "  - /benchmark"
    echo "  - /help"
    echo "  - /ping"
else
    echo "Error: Discord bot failed to start. Check the log file for details:"
    echo "tail -f $LOG_FILE"
fi

echo
echo "================================================"
echo " Bot restart complete!"
echo "================================================" 