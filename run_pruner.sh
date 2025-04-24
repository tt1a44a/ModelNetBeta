#!/bin/bash
# =======================================
# run_pruner.sh - Prune Ollama endpoints from the database
# =======================================

# Set directory paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISCORDBOT_DIR="${SCRIPT_DIR}"

# Load environment variables for PostgreSQL
if [ -f "${DISCORDBOT_DIR}/.env" ]; then
    source <(grep -v '^#' "${DISCORDBOT_DIR}/.env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Set default variables if not defined
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"

# Default values for pruner parameters
INPUT_STATUS="scanned"
OUTPUT_STATUS="verified"
FAIL_STATUS="failed" 
LIMIT=0
WORKERS=5
BATCH_SIZE=100
DRY_RUN=false
FORCE=false
RETEST_ALL=false
HONEYPOT_CHECK=true
SAFETY_THRESHOLD=0.5
MAX_RUNTIME=0
VERBOSE=false

# Process command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --input-status)
            INPUT_STATUS="$2"
            shift 2
            ;;
        --output-status)
            OUTPUT_STATUS="$2"
            shift 2
            ;;
        --fail-status)
            FAIL_STATUS="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --retest-all)
            RETEST_ALL=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --no-honeypot-check)
            HONEYPOT_CHECK=false
            shift
            ;;
        --safety-threshold)
            SAFETY_THRESHOLD="$2"
            shift 2
            ;;
        --max-runtime)
            MAX_RUNTIME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done

# Record pruner start in metadata
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording pruner start in PostgreSQL metadata..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_start', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
fi

# Define the pruner script path
PRUNER_SCRIPT="${DISCORDBOT_DIR}/prune_bad_endpoints.py"

# Build pruner command with parameters
CMD="python ${PRUNER_SCRIPT}"

CMD="${CMD} --input-status ${INPUT_STATUS}"
CMD="${CMD} --output-status ${OUTPUT_STATUS}"
CMD="${CMD} --fail-status ${FAIL_STATUS}"

if [ "$LIMIT" -gt 0 ]; then
    CMD="${CMD} --limit ${LIMIT}"
fi

CMD="${CMD} --workers ${WORKERS}"
CMD="${CMD} --batch-size ${BATCH_SIZE}"

if [ "$DRY_RUN" = true ]; then
    CMD="${CMD} --dry-run"
fi

if [ "$FORCE" = true ]; then
    CMD="${CMD} --force"
fi

if [ "$RETEST_ALL" = true ]; then
    CMD="${CMD} --retest-all"
fi

if [ "$VERBOSE" = true ]; then
    CMD="${CMD} --verbose"
fi

# Execute pruner
echo "Starting pruner with command: ${CMD}"
${CMD}

# Get exit status of pruner
PRUNER_STATUS=$?

# Record pruner completion in metadata
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording pruner completion in PostgreSQL metadata..."
    
    # Update prune end time
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
    
    # Update verified count
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('verified_count', (SELECT COUNT(*) FROM endpoints WHERE verified=1)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM endpoints WHERE verified=1)::text, updated_at = NOW();"
    
    # Update failed count
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('failed_count', (SELECT COUNT(*) FROM endpoints WHERE verified=0)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM endpoints WHERE verified=0)::text, updated_at = NOW();"
fi

echo "Pruner completed with status: ${PRUNER_STATUS}"
exit ${PRUNER_STATUS} 