#!/bin/bash
# Script to apply LocalAI migration to the PostgreSQL database

# Set directory paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables for PostgreSQL
if [ -f ".env" ]; then
    source <(grep -v '^#' ".env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Set default variables if not defined
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"

# Check if PostgreSQL is being used
if [ "$DATABASE_TYPE" != "postgres" ]; then
    echo "Error: This migration is only for PostgreSQL databases."
    exit 1
fi

# Check if PGPASSWORD is set
if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "Error: POSTGRES_PASSWORD environment variable is not set."
    echo "Please set it in your .env file or export it before running this script."
    exit 1
fi

# Check if migration file exists
MIGRATION_FILE="${SCRIPT_DIR}/migrate_localai_support.sql"
if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

echo "Applying LocalAI migration to PostgreSQL database..."
echo "Host: $POSTGRES_HOST"
echo "Port: $POSTGRES_PORT"
echo "Database: $POSTGRES_DB"
echo "User: $POSTGRES_USER"

# Apply migration
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f "$MIGRATION_FILE"

# Check if migration was successful
if [ $? -eq 0 ]; then
    echo "Migration completed successfully!"
    
    # Verify migration
    echo "Verifying migration..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "SELECT api_type, COUNT(*) FROM endpoints GROUP BY api_type;"
    
    echo "Migration verification complete."
else
    echo "Error: Migration failed."
    exit 1
fi

exit 0 