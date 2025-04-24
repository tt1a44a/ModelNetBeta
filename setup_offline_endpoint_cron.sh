#!/bin/bash

# Install the cron job to run check_offline_endpoints.py hourly

# Get the absolute path to the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/check_offline_endpoints.py"

# Make sure the script is executable
chmod +x "$PYTHON_SCRIPT"

# Create a temporary cron file
TEMP_CRON=$(mktemp)

# Export current crontab
crontab -l > "$TEMP_CRON" 2>/dev/null || true

# Check if the job is already installed
if grep -q "check_offline_endpoints.py" "$TEMP_CRON"; then
    echo "Cron job for check_offline_endpoints.py already exists"
else
    # Add the hourly job
    echo "# Check offline endpoints hourly" >> "$TEMP_CRON"
    echo "0 * * * * cd $SCRIPT_DIR && python3 $PYTHON_SCRIPT --hours 1 --batch 100 --concurrent 10 --timeout 10 >> $SCRIPT_DIR/check_offline_endpoints.log 2>&1" >> "$TEMP_CRON"
    
    # Install the new crontab
    crontab "$TEMP_CRON"
    echo "Installed hourly cron job for check_offline_endpoints.py"
fi

# Clean up
rm "$TEMP_CRON"

echo "Cron setup complete!"
echo "To run a manual check now, execute:"
echo "  python3 $PYTHON_SCRIPT --hours 1 --batch 100 --concurrent 10 --timeout 10 --verbose"
echo "To see statistics of offline endpoints, use the Discord command:"
echo "  /offline_endpoints action:Statistics" 