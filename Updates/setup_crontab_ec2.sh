#!/bin/bash
# Setup crontab entry for weekly honeypot cleanup on EC2

# Set variables
SCRIPT_PATH="/home/ec2-user/ModelNetBeta/cleanup_honeypots.py"
LOG_FILE="/var/log/honeypot_cleanup.log"
CRON_SCHEDULE="0 2 * * 0"  # Every Sunday at 2 AM

echo "Setting up honeypot cleanup crontab for EC2 server..."

# Ensure the script is executable
chmod +x "$SCRIPT_PATH"

# Ensure log directory exists and is writable
if [ ! -d "$(dirname $LOG_FILE)" ]; then
    echo "Creating log directory..."
    sudo mkdir -p "$(dirname $LOG_FILE)"
    sudo chmod 755 "$(dirname $LOG_FILE)"
fi

# Make sure log file exists and has proper permissions
sudo touch "$LOG_FILE"
sudo chmod 644 "$LOG_FILE"
sudo chown ec2-user:ec2-user "$LOG_FILE"

# Add crontab entry for ec2-user
echo "Adding crontab entry..."
(crontab -u ec2-user -l 2>/dev/null | grep -v "$SCRIPT_PATH") | crontab -u ec2-user -
(crontab -u ec2-user -l 2>/dev/null; echo "$CRON_SCHEDULE /usr/bin/python3 $SCRIPT_PATH >> $LOG_FILE 2>&1") | crontab -u ec2-user -

echo "Setup complete!"
echo "Honeypot cleanup will run every Sunday at 2 AM"
echo "Script: $SCRIPT_PATH"
echo "Log: $LOG_FILE"
echo "Current crontab:"
crontab -u ec2-user -l 