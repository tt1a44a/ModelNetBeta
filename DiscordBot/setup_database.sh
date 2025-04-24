#!/bin/bash
# setup_database.sh - Initialize and optimize the Ollama Scanner database for either SQLite or PostgreSQL

# Stop on any error
set -e

# Define paths
DISCORDBOT_DIR="$(pwd)"
WORKSPACE_DIR="$(dirname "${DISCORDBOT_DIR}")"
POSTGRES_INIT_SQL="${DISCORDBOT_DIR}/postgres_init.sql"

# Load environment variables if .env exists
if [ -f "${DISCORDBOT_DIR}/.env" ]; then
    source <(grep -v '^#' "${DISCORDBOT_DIR}/.env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Determine database type - now always PostgreSQL
DATABASE_TYPE="postgres"
echo "Database Type: ${DATABASE_TYPE}"

# Display banner
echo "=========================================="
echo "   OLLAMA SCANNER DATABASE SETUP"
echo "=========================================="
echo "DiscordBot Dir: ${DISCORDBOT_DIR}"
echo "Workspace: ${WORKSPACE_DIR}"

# PostgreSQL setup
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ollama_scanner_password}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "PostgreSQL Database: ${POSTGRES_DB} on ${POSTGRES_HOST}:${POSTGRES_PORT}"

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "Error: PostgreSQL client (psql) is not installed."
    echo "Please install the PostgreSQL client tools."
    exit 1
fi

# Try to connect to PostgreSQL
echo "Testing connection to PostgreSQL server..."
if ! PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "SELECT 1" 2>/dev/null; then
    echo "Warning: Cannot connect to the PostgreSQL server."
    echo "The database may not exist or credentials are incorrect."
    
    # Ask if we should try to create the database
    read -p "Would you like to attempt to create the database? (y/n): " create_db
    if [ "$create_db" == "y" ] || [ "$create_db" == "Y" ]; then
        echo "Attempting to create database ${POSTGRES_DB}..."
        
        # Try to connect to postgres database to create our database
        if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "CREATE DATABASE ${POSTGRES_DB}" 2>/dev/null; then
            echo "Database ${POSTGRES_DB} created successfully."
        else
            echo "Error: Failed to create database. You may need to manually create it."
            echo "Example command: createdb -h ${POSTGRES_HOST} -p ${POSTGRES_PORT} -U ${POSTGRES_USER} ${POSTGRES_DB}"
            exit 1
        fi
    else
        echo "Skipping database creation."
        exit 1
    fi
fi

# Check if the initialization SQL file exists
if [ ! -f "${POSTGRES_INIT_SQL}" ]; then
    echo "Error: PostgreSQL initialization SQL file not found at ${POSTGRES_INIT_SQL}"
    echo "Creating a new initialization file..."
    
    # Create the initialization SQL file
    cat > "${POSTGRES_INIT_SQL}" << 'EOSQL'
-- PostgreSQL initialization script for Ollama Scanner

-- Create the endpoints table (if it doesn't exist)
CREATE TABLE IF NOT EXISTS endpoints (
    id SERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified INTEGER DEFAULT 0, -- 0 = unverified, 1 = verified, 2 = invalid/pruned
    verification_date TIMESTAMP,
    UNIQUE(ip, port)
);

-- Create the verified_endpoints table (for servers that have been verified)
CREATE TABLE IF NOT EXISTS verified_endpoints (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    UNIQUE(endpoint_id)
);

-- Create the models table
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    parameter_size TEXT,
    quantization_level TEXT,
    size_mb REAL,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    UNIQUE(endpoint_id, name)
);

-- Create the user_selected_models table for chat history
CREATE TABLE IF NOT EXISTS user_selected_models (
    user_id TEXT PRIMARY KEY,
    model_id INTEGER,
    selection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL
);

-- Create the chat_history table
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    model_id INTEGER,
    prompt TEXT,
    system_prompt TEXT,
    response TEXT, 
    temperature REAL,
    max_tokens INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    eval_count INTEGER,
    eval_duration REAL,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL
);

-- Create the benchmark_results table
CREATE TABLE IF NOT EXISTS benchmark_results (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    model_id INTEGER,
    test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    avg_response_time REAL,
    tokens_per_second REAL,
    first_token_latency REAL,
    throughput_tokens REAL,
    throughput_time REAL,
    context_500_tps REAL,
    context_1000_tps REAL,
    context_2000_tps REAL,
    max_concurrent_requests INTEGER,
    concurrency_success_rate REAL,
    concurrency_avg_time REAL,
    success_rate REAL,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL
);

-- Create a metadata table for storing system information
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- For backward compatibility, create a view that looks like the old 'servers' table
CREATE OR REPLACE VIEW servers AS
SELECT 
    e.id, 
    e.ip, 
    e.port, 
    e.scan_date
FROM 
    endpoints e
JOIN
    verified_endpoints ve ON e.id = ve.endpoint_id;

-- Create indices for faster lookups
CREATE INDEX IF NOT EXISTS idx_endpoints_ip_port ON endpoints (ip, port);
CREATE INDEX IF NOT EXISTS idx_endpoints_verified ON endpoints (verified);
CREATE INDEX IF NOT EXISTS idx_models_endpoint_id ON models (endpoint_id);
CREATE INDEX IF NOT EXISTS idx_models_name ON models (name);
CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_model_id ON chat_history (model_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_endpoint_id ON benchmark_results (endpoint_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_model_id ON benchmark_results (model_id);

-- Insert initial metadata
INSERT INTO metadata (key, value, updated_at) 
VALUES ('db_version', '1.0', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO UPDATE SET value = '1.0', updated_at = CURRENT_TIMESTAMP;

INSERT INTO metadata (key, value, updated_at) 
VALUES ('last_setup', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP)
ON CONFLICT (key) DO UPDATE SET value = CURRENT_TIMESTAMP::TEXT, updated_at = CURRENT_TIMESTAMP;
EOSQL

    echo "Created PostgreSQL initialization file."
fi

# Initialize the database using the SQL file
echo "Initializing PostgreSQL database schema..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f "${POSTGRES_INIT_SQL}"; then
    echo "PostgreSQL database initialized successfully!"
else
    echo "Error: Failed to initialize PostgreSQL database schema."
    exit 1
fi

# Verify connection to the database
echo "Verifying database connection and schema..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null; then
    echo "Connection successful. Database is ready to use."
else
    echo "Error: Failed to connect to the database after initialization."
    exit 1
fi

echo "Database setup complete!"
echo "The PostgreSQL database is now ready to use with the scanner and pruner scripts."
echo "Database: ${POSTGRES_DB} on ${POSTGRES_HOST}:${POSTGRES_PORT}"

# Make the script executable
chmod +x "${DISCORDBOT_DIR}/setup_database.sh" 