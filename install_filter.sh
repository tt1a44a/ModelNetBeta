#!/bin/bash

# Ollama Scanner Filter Installation Script for OpenWebUI Docker
# This script installs the Ollama Scanner filter into an existing OpenWebUI Docker container

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
    log_error "Container name not provided. Usage: ./install_filter.sh <container_name>"
    exit 1
fi

CONTAINER_NAME="$1"

# Check if container exists
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    log_error "Container $CONTAINER_NAME not found. Please check the name and make sure it's running."
    exit 1
fi

# Define directories
FILTERS_DIR="/app/backend/filters"
CONFIGS_DIR="/app/backend/filters/configs"
CURRENT_DIR="$(pwd)"

log_info "Installing Ollama Scanner filter into $CONTAINER_NAME..."

# Create necessary directories in the container
log_info "Creating directories in the container..."
docker exec -it "$CONTAINER_NAME" mkdir -p "$FILTERS_DIR" "$CONFIGS_DIR" || {
    log_error "Failed to create directories in the container."
    exit 1
}

# Copy files
log_info "Copying filter files to the container..."

# Copy the filter Python file
docker cp "$CURRENT_DIR/ollama_scanner_filter.py" "$CONTAINER_NAME:$FILTERS_DIR/" || {
    log_error "Failed to copy filter Python file."
    exit 1
}

# Copy the config JSON file
docker cp "$CURRENT_DIR/ollama_scanner_filter_config.json" "$CONTAINER_NAME:$CONFIGS_DIR/" || {
    log_error "Failed to copy filter config file."
    exit 1
}

# Install required dependencies
log_info "Installing required Python dependencies..."
docker exec -it "$CONTAINER_NAME" pip install shodan requests || {
    log_warn "Failed to install some dependencies. The filter may not work correctly."
}

# Add ollama_scanner_filter to the filters.json file if it exists
log_info "Updating filters configuration..."
docker exec -it "$CONTAINER_NAME" bash -c "
    if [ -f '/app/backend/filters.json' ]; then
        cat /app/backend/filters.json | grep -q 'ollama_scanner_filter' || {
            # Filter doesn't exist yet, add it
            # Check if the file has any filters already
            if grep -q '\"filters\":\s*\[\s*\]' /app/backend/filters.json; then
                # Empty filters array
                sed -i 's/\"filters\":\s*\[\s*\]/\"filters\": [\"ollama_scanner_filter\"]/' /app/backend/filters.json
            elif grep -q '\"filters\":\s*\[' /app/backend/filters.json; then
                # Has filters, add to the end
                sed -i 's/\"filters\":\s*\[/\"filters\": [\"ollama_scanner_filter\", /' /app/backend/filters.json
            else
                # No filters key or file is malformed
                echo '{\"filters\": [\"ollama_scanner_filter\"]}' > /app/backend/filters.json
            fi
        }
    else
        # Create a new file
        echo '{\"filters\": [\"ollama_scanner_filter\"]}' > /app/backend/filters.json
    fi
"

# Verify installation
log_info "Verifying installation..."
if docker exec -it "$CONTAINER_NAME" [ -f "$FILTERS_DIR/ollama_scanner_filter.py" ] && \
   docker exec -it "$CONTAINER_NAME" [ -f "$CONFIGS_DIR/ollama_scanner_filter_config.json" ]; then
    log_success "Ollama Scanner filter installed successfully!"
    log_info "Now you need to restart the container or the OpenWebUI application for changes to take effect."
    log_info "After restart, go to Workspace > Functions in OpenWebUI to enable the filter."
else
    log_error "Installation verification failed. The filter files were not found in the expected locations."
    exit 1
fi

# Instructions for manual restart
log_info "To restart the container, run: docker restart $CONTAINER_NAME"
log_info "You may need to wait a minute or two for the application to fully initialize after restart."

exit 0 