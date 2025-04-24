#!/bin/bash
# Database Restore Script for Ollama Scanner
# This script restores the PostgreSQL database from a backup file

# Set up error handling
set -e
set -o pipefail

# Load environment variables
if [ -f ".env" ]; then
    source .env
else
    # Try to look in the DiscordBot directory
    if [ -f "DiscordBot/.env" ]; then
        source DiscordBot/.env
    fi
fi

# Default database connection parameters if not set in .env
DB_HOST=${POSTGRES_HOST:-"localhost"}
DB_PORT=${POSTGRES_PORT:-"5433"}
DB_NAME=${POSTGRES_DB:-"ollama_scanner"}
DB_USER=${POSTGRES_USER:-"ollama"}
DB_PASSWORD=${POSTGRES_PASSWORD:-"ollama_scanner_password"}

# Set up backup directory
BACKUP_DIR="backups"

# Set up logging
LOGFILE="${BACKUP_DIR}/restore_$(date +"%Y%m%d_%H%M%S").log"
echo "$(date): Starting database restore" | tee -a "$LOGFILE"

# Function to display usage
usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -f, --file BACKUP_FILE    Specify the backup file to restore"
    echo "  -l, --latest              Restore from the latest backup"
    echo "  -h, --help                Display this help message"
    echo
    echo "Example:"
    echo "  $0 --file backups/ollama_scanner_20250418_123456.backup"
    echo "  $0 --latest"
}

# Parse command line arguments
BACKUP_FILE=""
USE_LATEST=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        -l|--latest)
            USE_LATEST=true
            shift
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

# If using latest backup, set the backup file path
if [ "$USE_LATEST" = true ]; then
    if [ -L "${BACKUP_DIR}/latest.backup" ]; then
        BACKUP_FILE="${BACKUP_DIR}/latest.backup"
        echo "Using latest backup: $(readlink -f "$BACKUP_FILE")" | tee -a "$LOGFILE"
    else
        echo "Error: No latest backup symlink found" | tee -a "$LOGFILE"
        exit 1
    fi
fi

# Check if backup file is specified
if [ -z "$BACKUP_FILE" ]; then
    echo "Error: No backup file specified" | tee -a "$LOGFILE"
    usage
    exit 1
fi

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file does not exist: $BACKUP_FILE" | tee -a "$LOGFILE"
    exit 1
fi

# Confirm restore operation
echo "WARNING: This will PERMANENTLY DELETE all data in the $DB_NAME database and replace it with data from $BACKUP_FILE" | tee -a "$LOGFILE"
echo "Are you sure you want to proceed? [y/N]"
read -r confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Restore operation canceled" | tee -a "$LOGFILE"
    exit 0
fi

# Create a backup before restoring
echo "Creating a safety backup before restore..." | tee -a "$LOGFILE"
SAFETY_BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_pre_restore_$(date +"%Y%m%d_%H%M%S").backup"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F c -f "$SAFETY_BACKUP_FILE" 2>&1 | tee -a "$LOGFILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "Safety backup created: $SAFETY_BACKUP_FILE" | tee -a "$LOGFILE"
else
    echo "Warning: Failed to create safety backup. Proceeding with restore anyway..." | tee -a "$LOGFILE"
fi

# Restore the database
echo "Restoring database from backup $BACKUP_FILE..." | tee -a "$LOGFILE"
PGPASSWORD="$DB_PASSWORD" pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$BACKUP_FILE" 2>&1 | tee -a "$LOGFILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "Restore completed successfully" | tee -a "$LOGFILE"
else
    # Check if there were non-fatal errors during restore
    if grep -q "PostgreSQL restore completes with some errors" "$LOGFILE"; then
        echo "Restore completed with some non-fatal errors. Check the log file for details: $LOGFILE" | tee -a "$LOGFILE"
    else
        echo "Error: Database restore failed" | tee -a "$LOGFILE"
        echo "You may need to restore from the safety backup: $SAFETY_BACKUP_FILE" | tee -a "$LOGFILE"
        exit 1
    fi
fi

# Analyze the database after restore
echo "Analyzing the database..." | tee -a "$LOGFILE"
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;" 2>&1 | tee -a "$LOGFILE"

# Show database statistics
echo "Database restore completed. Showing statistics:" | tee -a "$LOGFILE"
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 'Endpoints' AS table, COUNT(*) FROM endpoints
UNION ALL
SELECT 'Verified Endpoints', COUNT(*) FROM verified_endpoints
UNION ALL
SELECT 'Models', COUNT(*) FROM models
UNION ALL
SELECT 'Benchmark Results', COUNT(*) FROM benchmark_results;" 2>&1 | tee -a "$LOGFILE"

echo "Restore process completed at $(date)" | tee -a "$LOGFILE"
echo "Log file: $LOGFILE" 