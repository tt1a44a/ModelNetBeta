#!/bin/bash
# =======================================
# db_maintenance.sh - Database maintenance for Ollama Scanner
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

echo "Running database maintenance on ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"

# Add indexes if they don't exist
echo "Adding performance indexes..."

# Function to check if index exists and create it if not
add_index() {
    local table=$1
    local column=$2
    local index_name="idx_${table}_${column}"
    
    # Check if index exists
    local exists=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT 1 FROM pg_indexes WHERE indexname = '${index_name}';")
    
    if [ -z "$exists" ]; then
        echo "Creating index ${index_name} on ${table}(${column})..."
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "CREATE INDEX ${index_name} ON ${table}(${column});"
    else
        echo "Index ${index_name} already exists."
    fi
}

# Add recommended indexes
if [ "$DATABASE_TYPE" = "postgres" ]; then
    # Endpoints table indexes
    add_index "endpoints" "verified"
    add_index "endpoints" "scan_date"
    add_index "endpoints" "verification_date"
    
    # Models table indexes
    add_index "models" "name"
    add_index "models" "endpoint_id"
    
    # Verified endpoints table index
    add_index "verified_endpoints" "endpoint_id"
    
    # Run VACUUM and ANALYZE to optimize the database
    echo "Running VACUUM ANALYZE to optimize the database..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "VACUUM ANALYZE;"
    
    # Update database statistics
    echo "Updating database statistics..."
    
    # Count endpoints by verified status
    VERIFIED_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM endpoints WHERE verified = 1;")
    VERIFIED_COUNT=$(echo $VERIFIED_COUNT | xargs)
    
    FAILED_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM endpoints WHERE verified = 0;")
    FAILED_COUNT=$(echo $FAILED_COUNT | xargs)
    
    # Count models
    MODEL_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
        -c "SELECT COUNT(*) FROM models;")
    MODEL_COUNT=$(echo $MODEL_COUNT | xargs)
    
    # Update metadata
    echo "Updating metadata statistics..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('verified_count', '${VERIFIED_COUNT}', NOW()) ON CONFLICT (key) DO UPDATE SET value = '${VERIFIED_COUNT}', updated_at = NOW();"
    
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('failed_count', '${FAILED_COUNT}', NOW()) ON CONFLICT (key) DO UPDATE SET value = '${FAILED_COUNT}', updated_at = NOW();"
    
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('model_count', '${MODEL_COUNT}', NOW()) ON CONFLICT (key) DO UPDATE SET value = '${MODEL_COUNT}', updated_at = NOW();"
    
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_maintenance', NOW()::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW()::text, updated_at = NOW();"
    
    echo "Maintenance completed successfully."
else
    echo "Maintenance is currently only supported for PostgreSQL."
    exit 1
fi 