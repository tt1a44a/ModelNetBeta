#!/bin/bash

# Ollama Scanner Filter Web Installation Script
# This script helps install the Ollama Scanner filter by copying the proper import file
# and providing instructions for importing through the OpenWebUI interface

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
    log_error "Container name not provided. Usage: ./web_install.sh <container_name>"
    exit 1
fi

CONTAINER_NAME="$1"

# Check if container exists
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    log_error "Container $CONTAINER_NAME not found. Please check the name and make sure it's running."
    exit 1
fi

# Define directories and files
WEBUI_STATIC_DIR="/app/build/assets"
CURRENT_DIR="$(pwd)"

log_info "Setting up the Ollama Scanner filter for web import in $CONTAINER_NAME..."

# Step 1: Copy the import file to a location accessible by the web UI
log_info "Copying import file to the container's static assets directory..."
docker cp "$CURRENT_DIR/owui_function_import.json" "$CONTAINER_NAME:$WEBUI_STATIC_DIR/ollama_scanner_filter.json"

# Set permissions for the file
log_info "Setting proper file permissions..."
docker exec -it "$CONTAINER_NAME" chmod 644 "$WEBUI_STATIC_DIR/ollama_scanner_filter.json"

# Install dependencies
log_info "Installing required Python dependencies..."
docker exec -it "$CONTAINER_NAME" pip install pydantic

# Success message and instructions
log_success "Ollama Scanner filter import file is now available on your OpenWebUI server!"
log_info "To import the filter, follow these steps:"
log_info "1. Go to your OpenWebUI instance in a browser"
log_info "2. Navigate to Workspace > Functions"
log_info "3. Click the 'Import' or '+' button"
log_info "4. Select 'Import from URL' and use this URL:"
log_info "   http://localhost:3000/assets/ollama_scanner_filter.json"
log_info "   (adjust the port/domain if your instance is on a different URL)"
log_info "5. Click Import and enable the filter"
log_info ""
log_info "Alternatively, you can import using the local file method:"
log_info "1. Save the owui_function_import.json file to your local computer"
log_info "2. In OpenWebUI, go to Workspace > Functions"
log_info "3. Click 'Import' or '+', then select 'Upload JSON'"
log_info "4. Browse for the saved JSON file and import it"

exit 0 