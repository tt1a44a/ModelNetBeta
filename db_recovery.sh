#!/bin/bash
# =======================================
# db_recovery.sh - Database recovery script for Ollama Scanner
# =======================================

# Set directory paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables for PostgreSQL
if [ -f "${SCRIPT_DIR}/.env" ]; then
    source <(grep -v '^#' "${SCRIPT_DIR}/.env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Set default variables if not defined
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"

# Configure logging
LOG_FILE="${SCRIPT_DIR}/logs/$(date +%Y%m%d)_recovery.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Logger function
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_message "INFO" "Starting database recovery process"
log_message "INFO" "Connecting to ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"

# Check for interrupted operations
check_interrupted_operations() {
    local last_scan_start=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT value FROM metadata WHERE key = 'last_scan_start';" | xargs)
        
    local last_scan_end=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT value FROM metadata WHERE key = 'last_scan_end';" | xargs)
        
    local last_prune_start=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT value FROM metadata WHERE key = 'last_prune_start';" | xargs)
        
    local last_prune_end=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT value FROM metadata WHERE key = 'last_prune_end';" | xargs)
    
    log_message "INFO" "Last scan start: ${last_scan_start}"
    log_message "INFO" "Last scan end: ${last_scan_end}"
    log_message "INFO" "Last prune start: ${last_prune_start}"
    log_message "INFO" "Last prune end: ${last_prune_end}"
    
    # Check for interrupted scan operation
    if [ -n "$last_scan_start" ] && [ -z "$last_scan_end" ]; then
        log_message "WARNING" "Detected interrupted scan operation"
        return 1
    fi
    
    # Check for interrupted prune operation
    if [ -n "$last_prune_start" ] && [ -z "$last_prune_end" ]; then
        log_message "WARNING" "Detected interrupted prune operation"
        return 2
    fi
    
    log_message "INFO" "No interrupted operations detected"
    return 0
}

# Function to repair interrupted operations
repair_database() {
    local interrupted_op=$1
    
    if [ "$interrupted_op" -eq 1 ]; then
        log_message "INFO" "Repairing interrupted scan operation"
        
        # Update the last_scan_end to current time
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_scan_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
        
        # Update endpoint counts to ensure consistency
        update_endpoint_counts
        
        log_message "INFO" "Scan operation marked as completed"
        
    elif [ "$interrupted_op" -eq 2 ]; then
        log_message "INFO" "Repairing interrupted prune operation"
        
        # Update the last_prune_end to current time
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
        
        # Update endpoint counts to ensure consistency
        update_endpoint_counts
        
        log_message "INFO" "Prune operation marked as completed"
    fi
}

# Function to update endpoint counts
update_endpoint_counts() {
    log_message "INFO" "Updating endpoint counts"
    
    # Count endpoints by verified status
    VERIFIED_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM endpoints WHERE verified = 1;")
    VERIFIED_COUNT=$(echo $VERIFIED_COUNT | xargs)
    
    FAILED_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM endpoints WHERE verified = 0;")
    FAILED_COUNT=$(echo $FAILED_COUNT | xargs)
    
    # Update metadata
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('verified_count', '${VERIFIED_COUNT}', NOW()) ON CONFLICT (key) DO UPDATE SET value = '${VERIFIED_COUNT}', updated_at = NOW();"
    
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('failed_count', '${FAILED_COUNT}', NOW()) ON CONFLICT (key) DO UPDATE SET value = '${FAILED_COUNT}', updated_at = NOW();"
    
    log_message "INFO" "Endpoint counts updated: verified=${VERIFIED_COUNT}, failed=${FAILED_COUNT}"
}

# Check for inconsistencies in the database
check_database_consistency() {
    log_message "INFO" "Checking database consistency"
    
    # Check for inconsistencies between endpoints and verified_endpoints tables
    local inconsistencies=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM endpoints e WHERE e.verified = 1 AND NOT EXISTS (SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = e.id);")
    inconsistencies=$(echo $inconsistencies | xargs)
    
    if [ "$inconsistencies" -gt 0 ]; then
        log_message "WARNING" "Found ${inconsistencies} verified endpoints without entries in verified_endpoints table"
        
        # Fix inconsistencies
        log_message "INFO" "Fixing inconsistencies"
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "INSERT INTO verified_endpoints (endpoint_id, verification_date) SELECT id, NOW() FROM endpoints e WHERE e.verified = 1 AND NOT EXISTS (SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = e.id);"
        
        log_message "INFO" "Fixed ${inconsistencies} inconsistencies"
    else
        log_message "INFO" "No inconsistencies found between endpoints and verified_endpoints tables"
    fi
    
    # Check for orphaned models
    local orphaned_models=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM models m WHERE NOT EXISTS (SELECT 1 FROM endpoints e WHERE e.id = m.endpoint_id);")
    orphaned_models=$(echo $orphaned_models | xargs)
    
    if [ "$orphaned_models" -gt 0 ]; then
        log_message "WARNING" "Found ${orphaned_models} orphaned models without valid endpoints"
        
        # Fix orphaned models
        log_message "INFO" "Removing orphaned models"
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "DELETE FROM models WHERE NOT EXISTS (SELECT 1 FROM endpoints e WHERE e.id = models.endpoint_id);"
        
        log_message "INFO" "Removed ${orphaned_models} orphaned models"
    else
        log_message "INFO" "No orphaned models found"
    fi
}

# Main functionality
if [ "$DATABASE_TYPE" = "postgres" ]; then
    # Check for interrupted operations
    check_interrupted_operations
    result=$?
    
    if [ "$result" -ne 0 ]; then
        # Repair interrupted operations
        repair_database $result
        log_message "INFO" "Interrupted operation repaired"
    fi
    
    # Check database consistency
    check_database_consistency
    
    # Record recovery in metadata
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_recovery', NOW()::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW()::text, updated_at = NOW();"
    
    log_message "INFO" "Recovery process completed successfully"
else
    log_message "ERROR" "Recovery is currently only supported for PostgreSQL"
    exit 1
fi 