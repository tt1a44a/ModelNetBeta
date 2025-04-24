#!/bin/bash
# Setup script for unified commands with Discord bot

set -e  # Exit on error

# Console colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}   UNIFIED COMMANDS SETUP AND MIGRATION     ${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# Check if virtual environment is active
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}Warning: No virtual environment detected.${NC}"
    echo "It's recommended to run this in a Python virtual environment."
    echo "Continue anyway? (y/n)"
    read -r response
    if [[ "$response" != "y" ]]; then
        echo "Exiting..."
        exit 1
    fi
fi

# Function to check if PostgreSQL is running
check_postgres() {
    echo -e "\n${BLUE}Checking PostgreSQL connection...${NC}"
    if ! python -c "import psycopg2; conn=psycopg2.connect(dbname='ollama_scanner', user='ollama', password='ollama_scanner_password', host='localhost', port='5433', connect_timeout=3); conn.close()" 2>/dev/null; then
        echo -e "${RED}Error: Cannot connect to PostgreSQL database.${NC}"
        echo "Please ensure PostgreSQL is running and the database credentials are correct."
        echo "Would you like to continue anyway? (y/n)"
        read -r continue_response
        if [[ "$continue_response" != "y" ]]; then
            echo "Exiting setup..."
            exit 1
        fi
    else
        echo -e "${GREEN}PostgreSQL connection successful!${NC}"
    fi
}

# Function to run migration
run_migration() {
    echo -e "\n${BLUE}Running migration to unified commands...${NC}"
    if ! python migrate_to_unified_commands.py --force; then
        echo -e "${RED}Migration encountered errors but we'll continue...${NC}"
    else
        echo -e "${GREEN}Migration completed successfully!${NC}"
    fi
}

# Function to check permissions and fix them if needed
check_and_fix_permissions() {
    echo -e "\n${BLUE}Checking Discord bot permissions...${NC}"
    python verify_bot_permissions.py
    permission_status=$?
    
    if [ $permission_status -eq 0 ]; then
        echo -e "\n${GREEN}Bot permissions are correctly set!${NC}"
        return 0
    else
        echo -e "\n${YELLOW}Bot permissions need to be fixed. Generating invite URL...${NC}"
        python fix_permissions.py --reauth
        
        echo -e "\n${YELLOW}Important: You need to remove and re-add the bot to your Discord server.${NC}"
        echo "Have you removed and re-added the bot with the proper permissions? (y/n)"
        read -r readded
        
        if [[ "$readded" == "y" ]]; then
            echo -e "${GREEN}Great! Let's verify the permissions again...${NC}"
            python verify_bot_permissions.py
            return $?
        else
            echo -e "${YELLOW}Please complete these steps before continuing:${NC}"
            echo "1. Remove the bot from your Discord server"
            echo "2. Re-add it using the invite URL generated above"
            echo "3. Run this script again"
            return 1
        fi
    fi
}

# Function to run the guild unified commands
run_guild_commands() {
    echo -e "\n${BLUE}Starting guild unified commands...${NC}"
    if ! python guild_unified_commands.py; then
        echo -e "${RED}Error running guild unified commands.${NC}"
        echo "Check the logs for more details."
        return 1
    else
        echo -e "${GREEN}Guild unified commands started successfully!${NC}"
        return 0
    fi
}

# Function to show final setup instructions
show_final_instructions() {
    echo -e "\n${BLUE}=============================================${NC}"
    echo -e "${GREEN}Setup completed successfully!${NC}"
    echo -e "${BLUE}=============================================${NC}"
    echo -e "\nTo run the bot in the future, use:"
    echo -e "  ${YELLOW}python guild_unified_commands.py${NC}"
    echo ""
    echo "Available commands in Discord:"
    echo "  /ping - Test bot responsiveness"
    echo "  /unified_search - Search for models"
    echo "  /server - Server management commands"
    echo "  /model - Model management commands"
    echo "  /chat - Chat with a selected model"
    echo "  /help - Show help information"
    echo ""
    echo "Legacy commands will automatically redirect to their unified equivalents."
    echo -e "${BLUE}=============================================${NC}"
}

# Main workflow
main() {
    # Step 1: Check PostgreSQL
    check_postgres
    
    # Step 2: Run migration
    run_migration
    
    # Step 3: Check and fix permissions
    if ! check_and_fix_permissions; then
        echo -e "${YELLOW}Please fix the permissions and run this script again.${NC}"
        exit 1
    fi
    
    # Step 4: Run guild commands
    if ! run_guild_commands; then
        echo -e "${RED}Failed to run guild commands. Please check the logs and try again.${NC}"
        exit 1
    fi
    
    # Step 5: Show final instructions
    show_final_instructions
}

# Run the main workflow
main 