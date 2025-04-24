#!/bin/bash
# run_both.sh - Run both Ollama Scanner and Pruner in parallel

# Stop on any error
set -e

# Define paths - adjusted to work from DiscordBot directory
DISCORDBOT_DIR="$(pwd)"
WORKSPACE_DIR="$(dirname "${DISCORDBOT_DIR}")"
SCANNER_SCRIPT="${DISCORDBOT_DIR}/run_scanner.sh"
PRUNER_SCRIPT="${DISCORDBOT_DIR}/run_pruner.sh"
DB_FILE="${DISCORDBOT_DIR}/ollama_instances.db"

# Display banner
echo "=========================================="
echo "   OLLAMA SCANNER + PRUNER COMBINED"
echo "=========================================="
echo "Running both scanner and pruner in parallel"
echo "DiscordBot Dir: ${DISCORDBOT_DIR}"
echo "Workspace: ${WORKSPACE_DIR}"
echo "Database: ${DB_FILE}"

# Check if database doesn't exist or needs to be linked to main DB
if [ ! -L "${DB_FILE}" ] && [ -f "${WORKSPACE_DIR}/ollama_instances.db" ]; then
    echo "Creating symbolic link to main database..."
    # Create a backup of existing DB if it exists
    if [ -f "${DB_FILE}" ] && [ ! -L "${DB_FILE}" ]; then
        echo "Backing up existing database to ollama_instances.db.bak.$(date +%s)"
        cp "${DB_FILE}" "${DB_FILE}.bak.$(date +%s)"
    fi
    # Create symbolic link
    ln -sf "${WORKSPACE_DIR}/ollama_instances.db" "${DB_FILE}"
    echo "Symbolic link created."
fi

# Check if scripts exist
if [ ! -f "${SCANNER_SCRIPT}" ]; then
    echo "Error: Scanner script not found at ${SCANNER_SCRIPT}"
    exit 1
fi

if [ ! -f "${PRUNER_SCRIPT}" ]; then
    echo "Error: Pruner script not found at ${PRUNER_SCRIPT}"
    exit 1
fi

# Make sure both scripts are executable
chmod +x "${SCANNER_SCRIPT}" "${PRUNER_SCRIPT}"

# Default scanner and pruner options
SCANNER_OPTS=""
PRUNER_OPTS="--workers 10 --force"  # We need --force to allow the pruner to run

# Parse command line arguments to set options
while [[ $# -gt 0 ]]; do
    case $1 in
        --scanner-method)
            SCANNER_OPTS="${SCANNER_OPTS} --method $2"
            shift 2
            ;;
        --scanner-threads)
            SCANNER_OPTS="${SCANNER_OPTS} --threads $2"
            shift 2
            ;;
        --scanner-continuous)
            SCANNER_OPTS="${SCANNER_OPTS} --continuous"
            shift
            ;;
        --pruner-limit)
            PRUNER_OPTS="${PRUNER_OPTS} --limit $2"
            shift 2
            ;;
        --pruner-workers)
            PRUNER_OPTS="${PRUNER_OPTS} --workers $2"
            shift 2
            ;;
        --pruner-dry-run)
            PRUNER_OPTS="${PRUNER_OPTS} --dry-run"
            shift
            ;;
        --verbose)
            SCANNER_OPTS="${SCANNER_OPTS} --verbose"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done

# Function to run the scanner
run_scanner() {
    echo "Starting scanner with options: ${SCANNER_OPTS}"
    ${SCANNER_SCRIPT} ${SCANNER_OPTS}
}

# Function to run the pruner
run_pruner() {
    echo "Starting pruner with options: ${PRUNER_OPTS}"
    
    # Wait a bit before starting the pruner to allow scanner to begin
    sleep 10
    
    # Run pruner every 30 minutes (adjust as needed)
    while true; do
        echo "Running pruner cycle at $(date)"
        ${PRUNER_SCRIPT} ${PRUNER_OPTS}
        
        echo "Pruner cycle complete. Waiting 30 minutes before next run..."
        sleep 1800
    done
}

# Run both in the background
run_scanner &
SCANNER_PID=$!

run_pruner &
PRUNER_PID=$!

# Set up trap to kill both processes on exit
trap "kill $SCANNER_PID $PRUNER_PID 2>/dev/null" EXIT

# Wait for either process to finish
wait $SCANNER_PID $PRUNER_PID

echo "One process finished. Exiting." 