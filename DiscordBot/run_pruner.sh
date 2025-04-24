#!/bin/bash
# run_pruner.sh - Script to run Ollama Bad Endpoint Pruner with virtual environment and PostgreSQL database

# Stop on any error
set -e

# Define paths - adjusted to work from DiscordBot directory
DISCORDBOT_DIR="$(pwd)"
WORKSPACE_DIR="$(dirname "${DISCORDBOT_DIR}")"
VENV_DIR="${WORKSPACE_DIR}/venv"
PRUNER_SCRIPT="${DISCORDBOT_DIR}/prune_bad_endpoints.py"
SYNC_SCRIPT="${DISCORDBOT_DIR}/sync_endpoints_to_servers.py"
DB_SETUP_SCRIPT="${DISCORDBOT_DIR}/setup_database.sh"

# Load environment variables for PostgreSQL
if [ -f "${DISCORDBOT_DIR}/.env" ]; then
    source <(grep -v '^#' "${DISCORDBOT_DIR}/.env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Display banner
echo "=========================================="
echo "   OLLAMA BAD ENDPOINT PRUNER"
echo "=========================================="
echo "DiscordBot Dir: ${DISCORDBOT_DIR}"
echo "Workspace: ${WORKSPACE_DIR}"
echo "Database Type: ${DATABASE_TYPE:-postgres}"
echo "Database Host: ${POSTGRES_HOST:-localhost}"

# Print detailed environment information
echo "----------------------------------------"
echo "Environment Variables:"
echo "SQLITE_DB_PATH: ${SQLITE_DB_PATH}"
echo "POSTGRES_DB: ${POSTGRES_DB:-ollama_scanner}"
echo "POSTGRES_USER: ${POSTGRES_USER:-ollama}"
echo "POSTGRES_HOST: ${POSTGRES_HOST:-localhost}"
echo "POSTGRES_PORT: ${POSTGRES_PORT:-5432}"
echo "----------------------------------------"

# Check if the setup script exists
if [ ! -f "${DB_SETUP_SCRIPT}" ]; then
    echo "Error: Database setup script not found at ${DB_SETUP_SCRIPT}"
    exit 1
fi

# Run the setup script to ensure database is ready
echo "Verifying database setup..."
bash "${DB_SETUP_SCRIPT}"

# Check if pruner script exists
if [ ! -f "${PRUNER_SCRIPT}" ]; then
    echo "Error: Pruner script not found at ${PRUNER_SCRIPT}"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

# Verify python and key packages are available
echo "Checking Python version and dependencies..."
python --version

# Simplified dependency check - just check for requests
if ! python -c "import requests" 2>/dev/null; then
    echo "Error: Python requests package is missing!"
    echo "Please install it: pip install requests"
    exit 1
else
    echo "✓ Required Python dependencies found"
fi

# Sync endpoints to servers before running the pruner
echo "Syncing endpoints to servers..."
if [ -f "${SYNC_SCRIPT}" ]; then
    python "${SYNC_SCRIPT}"
else
    echo "Warning: Sync script not found at ${SYNC_SCRIPT}"
fi

# Parse command line arguments
LIMIT=0
WORKERS=5
DRY_RUN=false
FORCE=false
HONEYPOT_CHECK=true
SAFETY_THRESHOLD=0.5
MAX_RUNTIME=0  # In minutes, 0 means no limit

# Process arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
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

# Set environment variable for database type
export DATABASE_TYPE="${DATABASE_TYPE:-postgres}"

# Record pruner start in metadata using psql if PostgreSQL is configured
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording pruner start in PostgreSQL metadata..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
        -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_start', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
fi

# Build command
CMD="python ${PRUNER_SCRIPT}"

if [ "$LIMIT" -gt 0 ]; then
    CMD="${CMD} --limit ${LIMIT}"
fi

CMD="${CMD} --workers ${WORKERS}"

if [ "$DRY_RUN" = true ]; then
    CMD="${CMD} --dry-run"
fi

if [ "$FORCE" = true ]; then
    CMD="${CMD} --force"
fi

if [ "$HONEYPOT_CHECK" = false ]; then
    CMD="${CMD} --honeypot-check false"
fi

CMD="${CMD} --safety-threshold ${SAFETY_THRESHOLD}"

# Display command
echo ""
echo "Command to execute:"
echo "${CMD}"
echo ""

echo "Starting pruner (press Ctrl+C to stop)..."
echo "----------------------------------------"

# Set up a trap for clean shutdown
function cleanup {
    echo ""
    echo "Pruner stopping, performing cleanup..."
    
    # Update metadata for PostgreSQL
    if [ "$DATABASE_TYPE" = "postgres" ]; then
        echo "Recording pruner end and statistics in PostgreSQL metadata..."
        
        # Update prune end time
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
        
        # Update statistics
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('server_count', (SELECT COUNT(*) FROM servers)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM servers)::text, updated_at = NOW();"
        
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('model_count', (SELECT COUNT(*) FROM models)::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM models)::text, updated_at = NOW();"
        
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
            -c "INSERT INTO metadata (key, value, updated_at) VALUES ('verified_server_count', (SELECT COUNT(*) FROM servers WHERE status='verified')::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM servers WHERE status='verified')::text, updated_at = NOW();"
        
        # Run database maintenance for PostgreSQL
        echo "Running database maintenance..."
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-ollama}" -d "${POSTGRES_DB:-ollama_scanner}" \
            -c "ANALYZE;"
    fi
    
    echo "Cleanup complete! Database optimized."
    exit 0
}

# Handle SIGINT (Ctrl+C) and SIGTERM signals
trap cleanup SIGINT SIGTERM

# Run pruner with optional time limit
if [ "$MAX_RUNTIME" -gt 0 ]; then
    echo "Pruner will automatically stop after ${MAX_RUNTIME} minutes."
    # Use timeout command to limit runtime
    timeout --signal=SIGTERM ${MAX_RUNTIME}m ${CMD} || {
        if [ $? -eq 124 ]; then  # timeout exit code
            echo "Pruner reached maximum runtime of ${MAX_RUNTIME} minutes."
            cleanup
        else
            echo "Pruner failed with error code $?"
            cleanup
        fi
    }
else
    # Run pruner without time limit
    ${CMD}
    # Run cleanup even after normal completion
    cleanup
fi 