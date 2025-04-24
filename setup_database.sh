#!/bin/bash
# Setup script for Scanner-Pruner-Bot database
# This script sets up the PostgreSQL database schema and performs optional migration

# Exit on any error
set -e

# Load environment variables
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

# Function to print help message
print_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --help             Show this help message"
    echo "  --init-only        Only initialize the database schema (no migration)"
    echo "  --migrate-only     Only migrate data from existing schema"
    echo "  --test-only        Only run schema tests"
    echo "  --force            Force reinitialization even if tables exist"
    echo "  --dry-run          For migration: perform a dry run without making changes"
}

# Default options
INIT_DB=true
MIGRATE_DATA=true
TEST_SCHEMA=true
FORCE_OPTION=""
DRY_RUN_OPTION=""

# Process command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            print_help
            exit 0
            ;;
        --init-only)
            MIGRATE_DATA=false
            TEST_SCHEMA=false
            shift
            ;;
        --migrate-only)
            INIT_DB=false
            TEST_SCHEMA=false
            shift
            ;;
        --test-only)
            INIT_DB=false
            MIGRATE_DATA=false
            shift
            ;;
        --force)
            FORCE_OPTION="--force"
            shift
            ;;
        --dry-run)
            DRY_RUN_OPTION="--dry-run"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Check if psycopg2 is installed
if ! python3 -c "import psycopg2" &> /dev/null; then
    echo "Installing psycopg2-binary package..."
    pip install psycopg2-binary
fi

# Create schema directory if it doesn't exist
mkdir -p schema

# Ensure PostgreSQL is running and accessible
echo "Checking PostgreSQL connection..."
if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" &> /dev/null; then
    echo "Error: Cannot connect to PostgreSQL server"
    echo "Please ensure PostgreSQL is running and accessible"
    exit 1
fi

echo "PostgreSQL server is running and accessible"

# Initialize database schema
if [ "$INIT_DB" = true ]; then
    echo "Initializing database schema..."
    
    # Check if schema file exists
    if [ ! -f "schema/postgres_schema.sql" ]; then
        echo "Schema file not found. Creating it..."
        
        # Create schema directory if it doesn't exist
        mkdir -p schema

        # Create schema file
        cat > schema/postgres_schema.sql << 'EOF'
-- PostgreSQL schema for Ollama Scanner
-- This file defines the new database schema for the Scanner-Pruner-Bot Integration

-- Create extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create servers table
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 11434,
    status VARCHAR(50) DEFAULT 'scanned',
    scan_date TIMESTAMP DEFAULT NOW(),
    verified_date TIMESTAMP,
    UNIQUE(ip, port)
);

-- Create models table
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    params VARCHAR(50),
    quant VARCHAR(50),
    size BIGINT,
    count INTEGER DEFAULT 0,
    UNIQUE(name, server_id)
);

-- Create metadata table
CREATE TABLE IF NOT EXISTS metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add indexes for better query performance
CREATE INDEX idx_servers_status ON servers(status);
CREATE INDEX idx_servers_scan_date ON servers(scan_date);
CREATE INDEX idx_models_name ON models(name);
CREATE INDEX idx_models_server_id ON models(server_id);

-- Initialize default metadata values
INSERT INTO metadata (key, value, updated_at) 
VALUES 
('last_scan_start', NULL, NOW()),
('last_scan_end', NULL, NOW()),
('last_prune_start', NULL, NOW()),
('last_prune_end', NULL, NOW()),
('scanned_count', '0', NOW()),
('verified_count', '0', NOW()),
('failed_count', '0', NOW())
ON CONFLICT (key) DO NOTHING;

-- Create schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- Insert initial schema version
INSERT INTO schema_version (version) VALUES ('1.0.0');

-- Grant permissions to the database user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ollama;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ollama;
EOF
    fi
    
    # Run database initialization script
    if [ -f "init_database.py" ]; then
        echo "Running database initialization script..."
        python3 init_database.py ${FORCE_OPTION}
    else
        echo "Database initialization script not found. Creating database manually..."
        
        # Create database if it doesn't exist
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d postgres \
            -c "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}'" | grep -q 1 || \
            PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d postgres \
            -c "CREATE DATABASE ${POSTGRES_DB}"
        
        # Execute schema SQL
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -f schema/postgres_schema.sql
    fi
    
    echo "Database schema initialized"
fi

# Migrate data from existing schema
if [ "$MIGRATE_DATA" = true ]; then
    echo "Migrating data from existing schema..."
    
    if [ -f "migrate_to_new_schema.py" ]; then
        python3 migrate_to_new_schema.py ${FORCE_OPTION} ${DRY_RUN_OPTION}
    else
        echo "Migration script not found. Skipping migration."
    fi
fi

# Test schema
if [ "$TEST_SCHEMA" = true ]; then
    echo "Testing database schema..."
    
    if [ -f "test_schema.py" ]; then
        python3 test_schema.py
    else
        echo "Test script not found. Skipping tests."
    fi
fi

echo "Database setup complete!"
echo "You can now use the database with the Scanner-Pruner-Bot integration system." 