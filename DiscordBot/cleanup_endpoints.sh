#!/bin/bash
# Cleanup script to prune bad Ollama endpoints
# This script should be set up as a cron job to run regularly

# Change to the directory where the scripts are located
cd "$(dirname "$0")"

# Set the log file
LOG_FILE="cleanup_endpoints.log"
DATE=$(date "+%Y-%m-%d %H:%M:%S")

echo "[$DATE] Starting endpoint cleanup" | tee -a $LOG_FILE

# First, run the debug script to identify bad endpoints
echo "[$DATE] Running endpoint debugging to identify bad endpoints" | tee -a $LOG_FILE
python3 debug_ollama_endpoints.py --limit 200 --workers 20 | tee -a $LOG_FILE

# Wait a moment for the file to be written
sleep 2

# Then use the results to prune bad endpoints
echo "[$DATE] Pruning bad endpoints from database" | tee -a $LOG_FILE
python3 prune_bad_endpoints.py --load-from endpoint_results.json | tee -a $LOG_FILE

# Finally, run another batch directly
echo "[$DATE] Checking additional endpoints directly" | tee -a $LOG_FILE
python3 prune_bad_endpoints.py --limit 300 --workers 20 | tee -a $LOG_FILE

echo "[$DATE] Endpoint cleanup completed" | tee -a $LOG_FILE

# To set up as a cron job:
# crontab -e
# Add the following line to run daily at 2:00 AM:
# 0 2 * * * /path/to/DiscordBot/cleanup_endpoints.sh

exit 0 