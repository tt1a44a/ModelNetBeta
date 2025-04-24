#!/bin/bash
# =======================================
# run_scanner.sh - Find Ollama instances and add them to the database
# =======================================

# Set directory paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISCORDBOT_DIR="${SCRIPT_DIR}"

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

# Default values
STATUS="scanned"
PRESERVE_VERIFIED=true
LIMIT=0
NETWORK="0.0.0.0/0"
WORKERS=5
TIMEOUT=10
METHOD="shodan"

# Process command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --status)
            STATUS="$2"
            shift 2
            ;;
        --no-preserve-verified)
            PRESERVE_VERIFIED=false
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --network)
            NETWORK="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --method)
            METHOD="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done

# Record scan start time in metadata
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording scanner start in PostgreSQL metadata..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_scan_start', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
fi

# Build scanner command with parameters
CMD="python ./ollama_scanner.py --method ${METHOD} --status ${STATUS}"

if [ "$PRESERVE_VERIFIED" = true ]; then
    CMD="${CMD} --preserve-verified"
else
    CMD="${CMD} --no-preserve-verified"
fi

if [ "$LIMIT" -gt 0 ]; then
    CMD="${CMD} --limit ${LIMIT}"
fi

CMD="${CMD} --threads ${WORKERS} --timeout ${TIMEOUT}"

# Execute scanner
echo "Starting scanner with command: ${CMD}"
${CMD}

# Get exit status of scanner
SCANNER_STATUS=$?

# Update metadata after scan completes
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording scan completion and statistics..."
    
    # Update scan end time
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_scan_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
    
    # Update scanned count
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('scanned_count', (SELECT COUNT(*) FROM endpoints WHERE verified=0)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM endpoints WHERE verified=0)::text, updated_at = NOW();"
    
    # Update verified count
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('verified_count', (SELECT COUNT(*) FROM endpoints WHERE verified=1)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM endpoints WHERE verified=1)::text, updated_at = NOW();"
fi

echo "Scanner completed with status: ${SCANNER_STATUS}"
exit ${SCANNER_STATUS} 