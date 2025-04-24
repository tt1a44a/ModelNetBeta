#!/bin/bash
# Database Backup Script for Ollama Scanner
# This script creates a compressed backup of the PostgreSQL database

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
mkdir -p "$BACKUP_DIR"

# Set up backup filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.backup"

# Set up logging
LOGFILE="${BACKUP_DIR}/backup_${TIMESTAMP}.log"
echo "$(date): Starting database backup" | tee -a "$LOGFILE"

# Perform the backup
echo "Creating backup of database ${DB_NAME} to ${BACKUP_FILE}..." | tee -a "$LOGFILE"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F c -f "$BACKUP_FILE" 2>&1 | tee -a "$LOGFILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    # Check backup file exists and has size
    if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo "Backup completed successfully. Backup size: $BACKUP_SIZE" | tee -a "$LOGFILE"
        
        # Create a symlink to the latest backup
        ln -sf "$BACKUP_FILE" "${BACKUP_DIR}/latest.backup"
        echo "Created symlink to latest backup: ${BACKUP_DIR}/latest.backup" | tee -a "$LOGFILE"
        
        # Clean up old backups (keep last 30 days)
        echo "Cleaning up old backups (keeping last 30 days)..." | tee -a "$LOGFILE"
        find "$BACKUP_DIR" -name "${DB_NAME}_*.backup" -mtime +30 -delete
        
        # Show remaining backups
        BACKUP_COUNT=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.backup" | wc -l)
        echo "Remaining backups: $BACKUP_COUNT" | tee -a "$LOGFILE"
    else
        echo "Error: Backup file is empty or does not exist" | tee -a "$LOGFILE"
        exit 1
    fi
else
    echo "Error: Database backup failed" | tee -a "$LOGFILE"
    exit 1
fi

echo "Backup process completed at $(date)" | tee -a "$LOGFILE" 