#!/bin/bash
# Script to apply the servers view update fix
# This script applies INSTEAD OF triggers to make the servers view updatable

# Set up error handling
set -e
set -o pipefail

# Load environment variables
if [ -f ".env" ]; then
    source .env
else
    # Try to look in the DiscordBot directory
    if [ -f "DiscordBot/.env" ]; then
        source DiscordBot/.env
    fi
fi

# Default database connection parameters if not set in .env
DB_HOST=${POSTGRES_HOST:-"localhost"}
DB_PORT=${POSTGRES_PORT:-"5433"}
DB_NAME=${POSTGRES_DB:-"ollama_scanner"}
DB_USER=${POSTGRES_USER:-"ollama"}
DB_PASSWORD=${POSTGRES_PASSWORD:-"ollama_scanner_password"}

# Set up logging
LOGFILE="view_update_fix.log"
echo "$(date): Starting servers view update fix" | tee -a "$LOGFILE"

# Function to run a query and log the output
run_query() {
    local query="$1"
    echo "$(date): Executing query: $query" >> "$LOGFILE"
    
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$query" 2>&1 | tee -a "$LOGFILE"
    
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo "$(date): Error executing query" | tee -a "$LOGFILE"
        return 1
    fi
    return 0
}

# Check database connection
echo "Testing database connection..." | tee -a "$LOGFILE"
if ! run_query "SELECT version();"; then
    echo "Error: Could not connect to the database. Please check your connection parameters." | tee -a "$LOGFILE"
    exit 1
fi

# Show current database state before fix
echo "Current database state before applying fix:" | tee -a "$LOGFILE"
run_query "SELECT 'Endpoint counts before fix' AS description;"
run_query "SELECT 
  (SELECT COUNT(*) FROM endpoints) AS total_endpoints,
  (SELECT COUNT(*) FROM endpoints WHERE verified = 1) AS verified_endpoints_status,
  (SELECT COUNT(*) FROM verified_endpoints) AS verified_endpoints_table,
  (SELECT COUNT(*) FROM servers) AS servers_view;"

# Apply the fix
echo "Applying the servers view update fix..." | tee -a "$LOGFILE"

# Check if fix_servers_view.sql exists
if [ -f "fix_servers_view.sql" ]; then
    # Execute the SQL file
    echo "Executing fix_servers_view.sql..." | tee -a "$LOGFILE"
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "fix_servers_view.sql" 2>&1 | tee -a "$LOGFILE"
    
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo "Error: Failed to apply fix_servers_view.sql" | tee -a "$LOGFILE"
        exit 1
    fi
else
    echo "Error: fix_servers_view.sql not found" | tee -a "$LOGFILE"
    exit 1
fi

# Test if the fix was successful
echo "Testing if the fix was applied successfully..." | tee -a "$LOGFILE"

# Try to insert a test record
TEST_IP="127.0.0.1"
TEST_PORT="11434"

run_query "INSERT INTO servers (ip, port) VALUES ('$TEST_IP', $TEST_PORT) ON CONFLICT DO NOTHING;"

# Check if the record exists in both tables
run_query "SELECT 'Test record in endpoints table:' AS description;"
run_query "SELECT * FROM endpoints WHERE ip = '$TEST_IP' AND port = $TEST_PORT;"

run_query "SELECT 'Test record in verified_endpoints table:' AS description;"
run_query "SELECT ve.* FROM verified_endpoints ve JOIN endpoints e ON ve.endpoint_id = e.id WHERE e.ip = '$TEST_IP' AND e.port = $TEST_PORT;"

run_query "SELECT 'Test record in servers view:' AS description;"
run_query "SELECT * FROM servers WHERE ip = '$TEST_IP' AND port = $TEST_PORT;"

# Remove the test record
run_query "DELETE FROM servers WHERE ip = '$TEST_IP' AND port = $TEST_PORT;"

# Show final database state
echo "Database state after applying fix:" | tee -a "$LOGFILE"
run_query "SELECT 'Endpoint counts after fix' AS description;"
run_query "SELECT 
  (SELECT COUNT(*) FROM endpoints) AS total_endpoints,
  (SELECT COUNT(*) FROM endpoints WHERE verified = 1) AS verified_endpoints_status,
  (SELECT COUNT(*) FROM verified_endpoints) AS verified_endpoints_table,
  (SELECT COUNT(*) FROM servers) AS servers_view;"

echo "Servers view update fix applied successfully!" | tee -a "$LOGFILE"
echo "For detailed logs, see $LOGFILE" 