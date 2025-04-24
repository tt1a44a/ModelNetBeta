#!/bin/bash
# Setup Database Maintenance Script
# This script sets up automated database maintenance using cron

# Set up error handling
set -e
set -o pipefail

# Get absolute path to the application directory
APP_DIR=$(pwd)

# Ensure all required scripts are executable
chmod +x "${APP_DIR}/check_db_schema_issues.py"
chmod +x "${APP_DIR}/apply_db_maintenance_fixes.sh"
chmod +x "${APP_DIR}/backup_database.sh"

# Create backup directory if it doesn't exist
BACKUP_DIR="${APP_DIR}/backups"
mkdir -p "$BACKUP_DIR"

# Function to display usage
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -d, --daily            Set up daily backups (default: yes)"
    echo "  -w, --weekly           Set up weekly maintenance (default: yes)"
    echo "  -m, --monthly          Set up monthly full maintenance (default: yes)"
    echo "  -t, --time HH:MM       Set time for scheduled tasks (default: 03:00)"
    echo "  -h, --help             Display this help message"
    echo
    echo "Example:"
    echo "  $0 --time 04:30        Set all tasks to run at 4:30 AM"
    echo "  $0 --daily no --weekly yes --monthly yes  Only set up weekly and monthly tasks"
}

# Default settings
SETUP_DAILY=true
SETUP_WEEKLY=true
SETUP_MONTHLY=true
SCHEDULED_TIME="03:00"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--daily)
            if [[ "$2" == "no" || "$2" == "false" ]]; then
                SETUP_DAILY=false
            fi
            shift 2
            ;;
        -w|--weekly)
            if [[ "$2" == "no" || "$2" == "false" ]]; then
                SETUP_WEEKLY=false
            fi
            shift 2
            ;;
        -m|--monthly)
            if [[ "$2" == "no" || "$2" == "false" ]]; then
                SETUP_MONTHLY=false
            fi
            shift 2
            ;;
        -t|--time)
            SCHEDULED_TIME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Extract hours and minutes from scheduled time
HOUR=$(echo "$SCHEDULED_TIME" | cut -d: -f1)
MINUTE=$(echo "$SCHEDULED_TIME" | cut -d: -f2)

# Verify time format
if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || ! [[ "$MINUTE" =~ ^[0-9]+$ ]] || [ "$HOUR" -gt 23 ] || [ "$MINUTE" -gt 59 ]; then
    echo "Error: Invalid time format. Please use HH:MM format (24-hour clock)"
    exit 1
fi

# Create temporary crontab file
TEMP_CRONTAB=$(mktemp)
crontab -l > "$TEMP_CRONTAB" 2>/dev/null || true

# Add header
echo "# Ollama Scanner Database Maintenance Tasks - Added $(date)" >> "$TEMP_CRONTAB"

# Add daily backup task
if [ "$SETUP_DAILY" = true ]; then
    # Run daily backup at the specified time
    echo "$MINUTE $HOUR * * * cd $APP_DIR && ./backup_database.sh >> $APP_DIR/backups/cron_backup.log 2>&1" >> "$TEMP_CRONTAB"
    echo "Added daily backup task at $SCHEDULED_TIME"
fi

# Add weekly maintenance task
if [ "$SETUP_WEEKLY" = true ]; then
    # Run weekly maintenance on Sunday at the specified time
    echo "$MINUTE $HOUR * * 0 cd $APP_DIR && ./check_db_schema_issues.py && ./apply_db_maintenance_fixes.sh >> $APP_DIR/backups/cron_maintenance.log 2>&1" >> "$TEMP_CRONTAB"
    echo "Added weekly maintenance task on Sunday at $SCHEDULED_TIME"
fi

# Add monthly full maintenance task
if [ "$SETUP_MONTHLY" = true ]; then
    # Run monthly full maintenance on the 1st of each month at the specified time
    echo "$MINUTE $HOUR 1 * * cd $APP_DIR && VACUUM_FULL=true ./apply_db_maintenance_fixes.sh >> $APP_DIR/backups/cron_full_maintenance.log 2>&1" >> "$TEMP_CRONTAB"
    echo "Added monthly full maintenance task on the 1st at $SCHEDULED_TIME"
fi

# Install the new crontab
crontab "$TEMP_CRONTAB"
rm "$TEMP_CRONTAB"

# Create a script to check maintenance status
cat > "${APP_DIR}/check_maintenance_status.sh" << 'EOF'
#!/bin/bash
# Script to check database maintenance status

echo "Database Maintenance Status"
echo "=========================="
echo

# Check cron jobs
echo "Scheduled Tasks:"
crontab -l | grep -E 'backup_database|check_db_schema_issues|apply_db_maintenance_fixes'
echo

# Check backup files
echo "Backup Files:"
find backups -name "*.backup" -type f | sort -r | head -5
echo

# Count total backups
BACKUP_COUNT=$(find backups -name "*.backup" -type f | wc -l)
echo "Total backups: $BACKUP_COUNT"

# Get latest backup info
LATEST_BACKUP=$(find backups -name "*.backup" -type f -printf "%T@ %p\n" | sort -nr | head -1 | cut -d' ' -f2-)
if [ -n "$LATEST_BACKUP" ]; then
    LATEST_DATE=$(stat -c %y "$LATEST_BACKUP")
    LATEST_SIZE=$(du -h "$LATEST_BACKUP" | cut -f1)
    echo "Latest backup: $LATEST_BACKUP"
    echo "Date: $LATEST_DATE"
    echo "Size: $LATEST_SIZE"
fi
echo

# Check logs
echo "Maintenance Logs:"
find backups -name "*.log" -type f -printf "%T@ %p\n" | sort -nr | head -5 | cut -d' ' -f2- | xargs -I{} ls -lh {}
echo

echo "Done."
EOF

chmod +x "${APP_DIR}/check_maintenance_status.sh"
echo "Created maintenance status script: ${APP_DIR}/check_maintenance_status.sh"

# Verify setup
echo
echo "Database maintenance setup completed successfully!"
echo "The following tasks have been scheduled:"
crontab -l | grep -E 'backup_database|check_db_schema_issues|apply_db_maintenance_fixes'
echo
echo "To check maintenance status, run: ${APP_DIR}/check_maintenance_status.sh"
echo "To backup the database immediately, run: ${APP_DIR}/backup_database.sh"
echo "To perform maintenance immediately, run: ${APP_DIR}/apply_db_maintenance_fixes.sh" 