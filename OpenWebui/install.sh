#!/bin/bash
# Ollama Scanner Installation Script for OpenWebUI Docker containers
# This script installs the Ollama Scanner components into an existing OpenWebUI Docker container

# Exit on error, but allow for proper cleanup
set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script variables
SCRIPT_VERSION="1.0.1"
MIN_OPENWEBUI_VERSION="0.2.0"
REQUIRED_DISK_SPACE=10 # MB

# Define directories
BACKEND_DIR="/app/backend"
FRONTEND_DIR="/app/frontend"
FUNCTIONS_DIR="${BACKEND_DIR}/functions"
CONFIGS_DIR="${FUNCTIONS_DIR}/configs"
ADMIN_DIR="${FRONTEND_DIR}/src/routes/admin"
TMP_DIR="/tmp/ollama_scanner"
BACKUP_DIR="/tmp/ollama_scanner_backup"
LOG_FILE="/tmp/ollama_scanner_install.log"

# Initialize empty arrays for backed up files
declare -a BACKED_UP_FILES
declare -a CREATED_FILES

# Start logging
exec > >(tee -a "$LOG_FILE") 2>&1

# Function to print colored messages
log() {
    local level=$1
    local message=$2
    
    case $level in
        "info")
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        "success")
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
        "warn")
            echo -e "${YELLOW}[WARNING]${NC} $message"
            ;;
        "error")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        *)
            echo "$message"
            ;;
    esac
}

# Function to clean up temporary files
cleanup() {
    log "info" "Cleaning up temporary files..."
    rm -rf "$TMP_DIR"
    log "success" "Cleanup completed."
}

# Function to handle errors
handle_error() {
    local error_message=$1
    log "error" "$error_message"
    
    # Ask if user wants to rollback changes
    if [ ${#CREATED_FILES[@]} -gt 0 ] || [ ${#BACKED_UP_FILES[@]} -gt 0 ]; then
        echo
        read -p "Do you want to rollback changes? (y/n): " choice
        case "$choice" in
            y|Y)
                rollback
                ;;
            *)
                log "info" "Keeping partial installation. You may need to manually clean up."
                ;;
        esac
    fi
    
    cleanup
    log "info" "Installation failed. Check $LOG_FILE for details."
    exit 1
}

# Function to rollback changes
rollback() {
    log "info" "Rolling back changes..."
    
    # Remove created files
    for file in "${CREATED_FILES[@]}"; do
        if [ -f "$file" ]; then
            log "info" "Removing $file"
            rm -f "$file"
        fi
    done
    
    # Restore backed up files
    for file in "${BACKED_UP_FILES[@]}"; do
        if [ -f "${BACKUP_DIR}${file}" ]; then
            log "info" "Restoring $file from backup"
            mkdir -p "$(dirname "$file")"
            cp -f "${BACKUP_DIR}${file}" "$file"
        fi
    done
    
    log "success" "Rollback completed."
}

# Function to backup a file before modification
backup_file() {
    local file=$1
    if [ -f "$file" ]; then
        local backup_path="${BACKUP_DIR}${file}"
        mkdir -p "$(dirname "$backup_path")"
        cp -f "$file" "$backup_path"
        BACKED_UP_FILES+=("$file")
        log "info" "Backed up $file"
    fi
}

# Function to register a file as created (for rollback purposes)
register_created_file() {
    local file=$1
    CREATED_FILES+=("$file")
}

# Print banner
echo "===== Ollama Scanner Installation Script v${SCRIPT_VERSION} ====="
echo "This script will install the Ollama Scanner in your OpenWebUI Docker container."

# Check if running as root or with sudo privileges
if [ "$EUID" -ne 0 ]; then
    log "warn" "Not running as root. Some operations may require elevated privileges."
fi

# Check OpenWebUI version
if [ -f "${BACKEND_DIR}/VERSION" ]; then
    OPENWEBUI_VERSION=$(cat "${BACKEND_DIR}/VERSION")
    log "info" "Detected OpenWebUI version: $OPENWEBUI_VERSION"
    
    # Simple version check (can be enhanced for more complex version comparison)
    if [[ "$OPENWEBUI_VERSION" < "$MIN_OPENWEBUI_VERSION" ]]; then
        handle_error "OpenWebUI version $OPENWEBUI_VERSION is not supported. Minimum required: $MIN_OPENWEBUI_VERSION"
    fi
else
    log "warn" "Could not detect OpenWebUI version. Continuing without version check."
fi

# Check directory permissions
for dir in "$BACKEND_DIR" "$FRONTEND_DIR" "$FUNCTIONS_DIR" "$CONFIGS_DIR" "$ADMIN_DIR"; do
    if [ ! -d "$dir" ]; then
        if ! mkdir -p "$dir" 2>/dev/null; then
            handle_error "Cannot create directory: $dir (permission denied)"
        fi
    elif [ ! -w "$dir" ]; then
        handle_error "No write permission for directory: $dir"
    fi
done

# Check available disk space
available_space=$(df -m "$BACKEND_DIR" | awk 'NR==2 {print $4}')
if [ "$available_space" -lt "$REQUIRED_DISK_SPACE" ]; then
    handle_error "Not enough disk space. Required: ${REQUIRED_DISK_SPACE}MB, Available: ${available_space}MB"
fi

# Create temporary and backup directories
log "info" "Creating temporary working directory..."
mkdir -p ${TMP_DIR}/{backend,frontend}
mkdir -p "$BACKUP_DIR"

# Detect package manager
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt"
    INSTALL_CMD="apt-get update && apt-get install -y"
elif command -v apk &> /dev/null; then
    PKG_MANAGER="apk"
    INSTALL_CMD="apk add --no-cache"
else
    log "warn" "Could not detect package manager. Will attempt to use existing tools."
    PKG_MANAGER="unknown"
    INSTALL_CMD="echo 'Cannot install:'"
fi

# Check and install required tools
check_and_install_tool() {
    local tool=$1
    local package=${2:-$1}
    
    log "info" "Checking for $tool..."
    if ! command -v "$tool" &> /dev/null; then
        log "info" "Installing $tool..."
        if ! $INSTALL_CMD "$package"; then
            handle_error "Failed to install $package. Please install it manually."
        fi
        log "success" "$tool installed successfully."
    else
        log "info" "$tool is already installed."
    fi
}

# Check required tools
check_and_install_tool "curl" 
check_and_install_tool "jq"
check_and_install_tool "pip" "python3-pip"
check_and_install_tool "python3" "python3"
check_and_install_tool "sqlite3" "sqlite3"

# Check if the container uses Node.js (required for building frontend)
if ! command -v node &> /dev/null; then
    log "warn" "Node.js not found. Frontend compilation may not work properly."
fi

# Install required Python packages with version pinning
log "info" "Installing required Python packages..."
if ! pip install "shodan>=1.28.0" "requests>=2.28.0" --no-cache-dir; then
    handle_error "Failed to install Python packages."
fi
log "success" "Python packages installed successfully."

# Function to create a file with error checking
create_file() {
    local target_path=$1
    local content=$2
    local file_description=$3
    
    # Ensure directory exists
    mkdir -p "$(dirname "$target_path")"
    
    # Backup existing file
    backup_file "$target_path"
    
    # Create file
    echo "$content" > "$target_path"
    
    if [ $? -ne 0 ]; then
        handle_error "Failed to create $file_description at $target_path"
    fi
    
    # Register file as created for rollback
    register_created_file "$target_path"
    log "success" "Created $file_description at $target_path"
}

# Function to install all files from temp directory to final destinations
install_files() {
    log "info" "Installing backend files..."
    
    # Install Python function file
    local target_path="${FUNCTIONS_DIR}/ollama_scanner_function.py"
    if [ -f "$target_path" ]; then
        log "warn" "Existing ollama_scanner_function.py found. Backing up..."
        backup_file "$target_path"
    fi
    
    if ! cp "${TMP_DIR}/backend/ollama_scanner_function.py" "$target_path"; then
        handle_error "Failed to install Python function file"
    fi
    chmod +x "$target_path"
    register_created_file "$target_path"
    log "success" "Installed ollama_scanner_function.py"
    
    # Install config file
    local config_path="${CONFIGS_DIR}/ollama_scanner_config.json"
    if [ -f "$config_path" ]; then
        log "warn" "Existing ollama_scanner_config.json found. Backing up..."
        backup_file "$config_path"
    fi
    
    if ! cp "${TMP_DIR}/backend/ollama_scanner_config.json" "$config_path"; then
        handle_error "Failed to install config file"
    fi
    register_created_file "$config_path"
    log "success" "Installed ollama_scanner_config.json"
    
    # Install frontend files
    log "info" "Installing frontend files..."
    
    # Create Scanner components directory
    local components_dir="${FRONTEND_DIR}/src/lib/components/admin/OllamaScanner"
    mkdir -p "$components_dir"
    
    # Install frontend components
    for component in DashboardTab SearchTab ScannerTab OllamaScanner; do
        local component_path="${components_dir}/${component}.svelte"
        if [ -f "$component_path" ]; then
            log "warn" "Existing ${component}.svelte found. Backing up..."
            backup_file "$component_path"
        fi
        
        if ! cp "${TMP_DIR}/frontend/${component}.svelte" "$component_path"; then
            handle_error "Failed to install ${component}.svelte component"
        fi
        register_created_file "$component_path"
        log "success" "Installed ${component}.svelte"
    done
    
    # Install admin route
    local route_path="${ADMIN_DIR}/ollama-scanner.svelte"
    if [ -f "$route_path" ]; then
        log "warn" "Existing admin route found. Backing up..."
        backup_file "$route_path"
    fi
    
    if ! cp "${TMP_DIR}/frontend/routes/ollama-scanner-route.svelte" "$route_path"; then
        handle_error "Failed to install admin route"
    fi
    register_created_file "$route_path"
    log "success" "Installed admin route"
    
    # Update admin navigation (if it exists)
    local nav_path="${ADMIN_DIR}/+layout.svelte"
    if [ -f "$nav_path" ]; then
        log "info" "Updating admin navigation..."
        backup_file "$nav_path"
        
        # Use sed to add navigation entry (might require more sophisticated approach for real implementation)
        if ! sed -i '/navItems = \[/a \    { name: "Ollama Scanner", path: "/admin/ollama-scanner", icon: "search" },' "$nav_path"; then
            log "warn" "Failed to update admin navigation. You may need to add it manually."
        else
            log "success" "Updated admin navigation"
        fi
    else
        log "warn" "Admin navigation file not found. Navigation entry not added."
    fi
}

log "info" "Downloading backend files..."

cat > ${TMP_DIR}/frontend/routes/ollama-scanner-route.svelte << 'EOF'
<script>
  import OllamaScanner from '../OllamaScanner.svelte';
</script>

<OllamaScanner />
EOF

# Install all files from temporary directory to final destinations
log "info" "Starting installation of Ollama Scanner components..."
install_files

# Verify installation
verify_installation() {
    local errors=0
    
    log "info" "Verifying installation..."
    
    # Check if function file exists
    if [ ! -f "${FUNCTIONS_DIR}/ollama_scanner_function.py" ]; then
        log "error" "Function file missing: ${FUNCTIONS_DIR}/ollama_scanner_function.py"
        errors=$((errors + 1))
    fi
    
    # Check if config file exists
    if [ ! -f "${CONFIGS_DIR}/ollama_scanner_config.json" ]; then
        log "error" "Config file missing: ${CONFIGS_DIR}/ollama_scanner_config.json"
        errors=$((errors + 1))
    fi
    
    # Check if frontend components exist
    local components_dir="${FRONTEND_DIR}/src/lib/components/admin/OllamaScanner"
    for component in DashboardTab SearchTab ScannerTab OllamaScanner; do
        if [ ! -f "${components_dir}/${component}.svelte" ]; then
            log "error" "Component file missing: ${components_dir}/${component}.svelte"
            errors=$((errors + 1))
        fi
    done
    
    # Check if admin route exists
    if [ ! -f "${ADMIN_DIR}/ollama-scanner.svelte" ]; then
        log "error" "Admin route missing: ${ADMIN_DIR}/ollama-scanner.svelte"
        errors=$((errors + 1))
    fi
    
    # Check if Python function runs
    if ! python3 -c "import sys; sys.path.insert(0, '${FUNCTIONS_DIR}'); from ollama_scanner_function import setup_database; setup_database(); print('Function check passed')" &>/dev/null; then
        log "error" "Python function check failed. The function may have errors."
        errors=$((errors + 1))
    fi
    
    # Return result
    if [ $errors -eq 0 ]; then
        log "success" "Installation verification passed!"
        return 0
    else
        log "error" "Installation verification found $errors errors."
        return 1
    fi
}

# Run verification
if ! verify_installation; then
    echo
    read -p "Installation verification failed. Do you want to rollback? (y/n): " choice
    case "$choice" in
        y|Y)
            rollback
            cleanup
            log "info" "Installation rolled back due to verification failure."
            exit 1
            ;;
        *)
            log "warn" "Continuing despite verification failure. The installation may be incomplete."
            ;;
    esac
fi

# Clean up temporary files
cleanup

# Post-installation instructions
log "success" "==================================================="
log "success" "Ollama Scanner installation completed successfully!"
log "success" "==================================================="
echo
log "info" "You can now access Ollama Scanner from the OpenWebUI admin panel."
log "info" "Navigate to: http://your-openwebui-url/admin/ollama-scanner"
echo
log "info" "To use the scanner, you'll need a Shodan API key:"
log "info" "1. Get a free API key from https://account.shodan.io/"
log "info" "2. Enter it in the Scanner tab to begin discovering Ollama instances"
echo
log "warn" "IMPORTANT SECURITY NOTICE:"
log "warn" "Please use this tool responsibly and ethically."
log "warn" "Never attempt to access or use Ollama instances without proper authorization."
echo
log "info" "Installation log saved to: $LOG_FILE"
echo
log "info" "If you need to uninstall, run 'rm -rf ${FUNCTIONS_DIR}/ollama_scanner_function.py ${CONFIGS_DIR}/ollama_scanner_config.json ${FRONTEND_DIR}/src/lib/components/admin/OllamaScanner ${ADMIN_DIR}/ollama-scanner.svelte'"
echo
