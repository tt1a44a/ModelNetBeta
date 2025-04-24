#!/bin/bash

echo "=== Database Permission Fixer ==="
echo "This script will fix the SQLite database permissions issues"

DB_DIR="$(pwd)"
DB_FILE="$DB_DIR/ollama_instances.db"
BACKUP_FILE="$DB_DIR/ollama_instances.db.bak.$(date +%s)"

# First check if we have a circular symlink issue
if [ -L "$DB_FILE" ]; then
    echo "Removing symlink at $DB_FILE"
    rm "$DB_FILE"
fi

# Check parent directory symlink as well
if [ -L "$(dirname $DB_DIR)/ollama_instances.db" ]; then
    echo "Removing symlink at parent directory"
    rm "$(dirname $DB_DIR)/ollama_instances.db"
fi

# Create a new database file if it doesn't exist
if [ ! -f "$DB_FILE" ]; then
    echo "Creating new database file..."
    touch "$DB_FILE"
    chmod 664 "$DB_FILE"
    echo "New database file created with proper permissions"
else
    # If it exists but may have permission issues
    echo "Database file exists, fixing permissions..."
    # Make a backup first
    cp "$DB_FILE" "$BACKUP_FILE"
    echo "Backup created at $BACKUP_FILE"
    chmod 664 "$DB_FILE"
fi

# Initialize the database schema
echo "Initializing database schema..."
sqlite3 "$DB_FILE" << "EOSQL"
-- First create the new schema (for pruner)
CREATE TABLE IF NOT EXISTS endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT,
    port INTEGER,
    scan_date TEXT,
    verified INTEGER DEFAULT 0,
    verification_date TEXT,
    UNIQUE(ip, port)
);

CREATE TABLE IF NOT EXISTS verified_endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id INTEGER,
    verification_date TEXT,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id),
    UNIQUE(endpoint_id)
);

-- Create old schema (for Discord bot) - use a real table not a view
DROP TABLE IF EXISTS servers;
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT,
    port INTEGER,
    scan_date TEXT,
    status TEXT DEFAULT 'verified',
    UNIQUE(ip, port)
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id INTEGER,
    server_id INTEGER,
    name TEXT,
    parameter_size TEXT,
    quantization_level TEXT,
    size_mb REAL,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id),
    FOREIGN KEY (server_id) REFERENCES servers (id),
    UNIQUE(endpoint_id, name),
    UNIQUE(server_id, name)
);

-- Create metadata table for the pruner
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

-- Add initial metadata values
INSERT OR IGNORE INTO metadata (key, value, updated_at)
VALUES 
    ('server_count', '0', datetime('now')),
    ('model_count', '0', datetime('now')),
    ('verified_server_count', '0', datetime('now')),
    ('last_prune_start', datetime('now'), datetime('now')),
    ('last_prune_end', datetime('now'), datetime('now'));

-- Set WAL mode for better concurrency
PRAGMA journal_mode = WAL;

-- Other performance optimizations
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -30000; -- Use about 30MB of memory for cache
EOSQL

# Check if schema creation was successful
if [ $? -eq 0 ]; then
    echo "Database schema created successfully"
    
    # Create symlink for backward compatibility
    if [ ! -L "$(dirname $DB_DIR)/ollama_instances.db" ]; then
        echo "Creating symlink in parent directory for backward compatibility"
        ln -sf "$DB_FILE" "$(dirname $DB_DIR)/ollama_instances.db"
    fi
    
    # Show database file details
    echo "Database file details:"
    ls -la "$DB_FILE"
    echo "Database tables:"
    sqlite3 "$DB_FILE" ".tables"
    echo "Database is now ready to use"
else
    echo "Error creating database schema"
    exit 1
fi

echo "=== Database Fix Complete ==="
