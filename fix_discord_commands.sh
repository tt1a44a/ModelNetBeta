#!/bin/bash
# Script to fix Discord command syncing issues
# This script provides multiple approaches to fix Discord command syncing issues

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

APP_DIR=$(pwd)
DISCORD_BOT_DIR="$APP_DIR/DiscordBot"
LOG_FILE="$APP_DIR/discord_commands_fix.log"

# Make sure we're in the right directory
if [ ! -d "$DISCORD_BOT_DIR" ]; then
    echo -e "${RED}Error: DiscordBot directory not found at $DISCORD_BOT_DIR${NC}"
    echo "Please run this script from the root directory of the Ollama Scanner project."
    exit 1
fi

# Initialize log file
echo "Discord Commands Fix Log - $(date)" > "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"

# Function to log messages
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Show help
show_help() {
    echo -e "${BLUE}Discord Command Sync Fix Tool${NC}"
    echo "This script helps diagnose and fix Discord command syncing issues."
    echo
    echo -e "${YELLOW}Usage:${NC}"
    echo "  $0 [options]"
    echo
    echo -e "${YELLOW}Options:${NC}"
    echo "  -h, --help                Show this help message"
    echo "  -g, --guild-id <id>       Specify a Discord guild ID for syncing"
    echo "  -r, --restart             Restart the Discord bot after fixing"
    echo "  -f, --force               Force resync all commands"
    echo "  -l, --list                List all available commands in the bot"
    echo "  -d, --debug               Run with debug output"
    echo
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 --guild-id 123456789 --restart"
    echo "  $0 --force --debug"
    echo
}

# Function to restart Discord bot
restart_bot() {
    log "${YELLOW}Restarting Discord bot...${NC}"
    
    # Check if Discord bot is running
    if pgrep -f "python.*discord_bot.py" > /dev/null; then
        log "${BLUE}Stopping Discord bot...${NC}"
        pkill -f "python.*discord_bot.py" || log "${RED}Failed to stop Discord bot${NC}"
        sleep 2
    fi
    
    # Start Discord bot
    log "${BLUE}Starting Discord bot...${NC}"
    cd "$DISCORD_BOT_DIR"
    if [ "$DEBUG" = true ]; then
        python discord_bot.py > discord_bot_restart.log 2>&1 &
    else
        nohup python discord_bot.py > discord_bot_restart.log 2>&1 &
    fi
    
    log "${GREEN}Discord bot restarted with PID: $!${NC}"
    cd "$APP_DIR"
}

# Function to list commands
list_commands() {
    log "${YELLOW}Analyzing Discord bot commands...${NC}"
    
    cd "$DISCORD_BOT_DIR"
    COMMANDS=$(grep -r "@tree\\.command" --include="*.py" . | grep -v "#" | grep -oP '@tree\.command\(\K[^)]+' | sort | uniq)
    
    log "${BLUE}Found commands:${NC}"
    echo "$COMMANDS" | tee -a "$LOG_FILE"
    
    # Also list app_commands.describe to find parameter descriptions
    PARAMS=$(grep -r "@app_commands.describe" --include="*.py" . | grep -v "#" | sort)
    
    log "${BLUE}Command parameters:${NC}"
    echo "$PARAMS" | tee -a "$LOG_FILE"
    
    cd "$APP_DIR"
}

# Function to force resync using the Python script
force_resync() {
    if [ -n "$GUILD_ID" ]; then
        log "${YELLOW}Force resyncing commands for guild ID: $GUILD_ID${NC}"
        python force_resync.py "$GUILD_ID" | tee -a "$LOG_FILE"
    else
        log "${YELLOW}Force resyncing commands globally${NC}"
        python force_resync.py | tee -a "$LOG_FILE"
    fi
}

# Function to check for verbose parameter in chat command
check_verbose_param() {
    log "${YELLOW}Checking for verbose parameter in chat command...${NC}"
    
    cd "$DISCORD_BOT_DIR"
    VERBOSE_CHECK=$(grep -r "verbose" --include="*.py" . | grep "chat" | grep -v "#")
    
    if [ -n "$VERBOSE_CHECK" ]; then
        log "${GREEN}Found verbose parameter in chat command:${NC}"
        echo "$VERBOSE_CHECK" | tee -a "$LOG_FILE"
    else
        log "${RED}Could not find verbose parameter in chat command${NC}"
    fi
    
    cd "$APP_DIR"
}

# Parse command line arguments
GUILD_ID=""
RESTART=false
FORCE=false
LIST=false
DEBUG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -g|--guild-id)
            GUILD_ID="$2"
            shift 2
            ;;
        -r|--restart)
            RESTART=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -l|--list)
            LIST=true
            shift
            ;;
        -d|--debug)
            DEBUG=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Execute requested actions
if [ "$LIST" = true ]; then
    list_commands
    check_verbose_param
fi

if [ "$FORCE" = true ]; then
    force_resync
fi

if [ "$RESTART" = true ]; then
    restart_bot
fi

# If no options were specified, show help
if [ "$LIST" = false ] && [ "$FORCE" = false ] && [ "$RESTART" = false ]; then
    show_help
fi

log "${GREEN}Discord command fix operations completed!${NC}"
log "Log file: $LOG_FILE" 