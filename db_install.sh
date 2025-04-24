#!/bin/bash

# Ollama Scanner Filter Database Installation Script
# This script installs the Ollama Scanner filter and registers it in the OpenWebUI database

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if container name is provided
if [ -z "$1" ]; then
    log_error "Container name not provided. Usage: ./db_install.sh <container_name>"
    exit 1
fi

CONTAINER_NAME="$1"

# Check if container exists
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    log_error "Container $CONTAINER_NAME not found. Please check the name and make sure it's running."
    exit 1
fi

# Define directories and files
FILTERS_DIR="/app/backend/filters"
CONFIGS_DIR="/app/backend/filters/configs"
DB_PATH="/app/backend/data/database.db"
CURRENT_DIR="$(pwd)"

log_info "Installing Ollama Scanner filter into $CONTAINER_NAME with database registration..."

# Step 1: Install files like before
log_info "Creating directories in the container..."
docker exec -it "$CONTAINER_NAME" mkdir -p "$FILTERS_DIR" "$CONFIGS_DIR"

log_info "Copying filter files to the container..."
# Use the fixed filter file
docker cp "$CURRENT_DIR/fixed_filter.py" "$CONTAINER_NAME:$FILTERS_DIR/ollama_scanner_filter.py"
docker cp "$CURRENT_DIR/ollama_scanner_filter_config.json" "$CONTAINER_NAME:$CONFIGS_DIR/"

log_info "Installing required Python dependencies..."
docker exec -it "$CONTAINER_NAME" pip install shodan requests pydantic

# Step 2: Register in the database
log_info "Registering the filter in the OpenWebUI database..."

# For simplicity, we'll use a temp file to hold our SQL
TEMP_SQL_FILE="$CURRENT_DIR/temp_register.sql"
cat > "$TEMP_SQL_FILE" << EOF
-- Check if 'function' table exists
CREATE TABLE IF NOT EXISTS function (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    version TEXT,
    author TEXT,
    license TEXT,
    type TEXT,
    enabled INTEGER DEFAULT 0,
    global INTEGER DEFAULT 0,
    creation_date TEXT,
    update_date TEXT
);

-- Insert or update the Ollama Scanner filter
INSERT OR REPLACE INTO function (
    id, name, description, version, author, license, type, enabled, global, creation_date, update_date
) VALUES (
    'ollama_scanner_filter',
    'Ollama Scanner',
    'Discover, analyze, and connect to Ollama instances across the internet using Shodan API',
    '1.0.0',
    'Ollama Scanner Team',
    'MIT',
    'filter',
    0,
    0,
    datetime('now'),
    datetime('now')
);
EOF

# Copy SQL file to container
docker cp "$TEMP_SQL_FILE" "$CONTAINER_NAME:/tmp/"

# Execute SQL file
log_info "Running SQL to register the filter..."
docker exec -it "$CONTAINER_NAME" sqlite3 "$DB_PATH" < "/tmp/temp_register.sql"

# Clean up temp file
rm "$TEMP_SQL_FILE"
docker exec -it "$CONTAINER_NAME" rm "/tmp/temp_register.sql"

# Step 3: Verify installation
log_info "Verifying installation..."

# Check files
if ! docker exec -it "$CONTAINER_NAME" [ -f "$FILTERS_DIR/ollama_scanner_filter.py" ] || \
   ! docker exec -it "$CONTAINER_NAME" [ -f "$CONFIGS_DIR/ollama_scanner_filter_config.json" ]; then
    log_error "Filter files not properly installed."
    exit 1
fi

# Check database registration
DB_CHECK=$(docker exec -it "$CONTAINER_NAME" sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM function WHERE id='ollama_scanner_filter';")
if [ "$DB_CHECK" -eq "0" ]; then
    log_error "Filter not properly registered in the database."
    exit 1
fi

log_success "Ollama Scanner filter files installed and registered in the database!"
log_info "Now restart the container with: docker restart $CONTAINER_NAME"
log_info "After restart, go to Workspace > Functions in OpenWebUI to enable the filter."

exit 0 