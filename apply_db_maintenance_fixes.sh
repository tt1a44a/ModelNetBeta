#!/bin/bash
# Script to apply database maintenance fixes
# This script executes the SQL commands from fix_db_maintenance_issues.sql

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
LOGFILE="db_maintenance_fix.log"
echo "$(date): Starting database maintenance fixes" | tee -a "$LOGFILE"

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

# Show current database state before fixes
echo "Current database state before applying fixes:" | tee -a "$LOGFILE"
run_query "SELECT 'NULL verification_date values' AS description, COUNT(*) FROM endpoints WHERE verification_date IS NULL AND verified = 1;"
run_query "SELECT 'NULL last_check_date values' AS description, COUNT(*) FROM endpoints WHERE last_check_date IS NULL;"
run_query "SELECT 'Foreign key cascade rule' AS description, tc.constraint_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name WHERE tc.constraint_name = 'benchmark_results_model_id_fkey';"

# Check table bloat before
echo "Table bloat before vacuum:" | tee -a "$LOGFILE"
run_query "SELECT schemaname, relname, n_dead_tup, n_live_tup, round(n_dead_tup::numeric / NULLIF((n_live_tup + n_dead_tup), 0), 2) AS dead_ratio FROM pg_stat_user_tables WHERE n_dead_tup > 0 ORDER BY dead_ratio DESC LIMIT 5;"

# Apply the fixes
echo "Applying database maintenance fixes..." | tee -a "$LOGFILE"

# Check if fix_db_maintenance_issues.sql exists
if [ -f "fix_db_maintenance_issues.sql" ]; then
    # Execute the SQL file
    echo "Executing fix_db_maintenance_issues.sql..." | tee -a "$LOGFILE"
    PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "fix_db_maintenance_issues.sql" 2>&1 | tee -a "$LOGFILE"
    
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        echo "Error: Failed to apply fix_db_maintenance_issues.sql" | tee -a "$LOGFILE"
        exit 1
    fi
else
    echo "Error: fix_db_maintenance_issues.sql not found" | tee -a "$LOGFILE"
    exit 1
fi

# Show database state after fixes
echo "Database state after applying fixes:" | tee -a "$LOGFILE"
run_query "SELECT 'NULL verification_date values' AS description, COUNT(*) FROM endpoints WHERE verification_date IS NULL AND verified = 1;"
run_query "SELECT 'NULL last_check_date values' AS description, COUNT(*) FROM endpoints WHERE last_check_date IS NULL;"
run_query "SELECT 'Foreign key cascade rule' AS description, tc.constraint_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name WHERE tc.constraint_name = 'benchmark_results_model_id_fkey';"

# Check table bloat after
echo "Table bloat after vacuum:" | tee -a "$LOGFILE"
run_query "SELECT schemaname, relname, n_dead_tup, n_live_tup, round(n_dead_tup::numeric / NULLIF((n_live_tup + n_dead_tup), 0), 2) AS dead_ratio FROM pg_stat_user_tables WHERE n_dead_tup > 0 ORDER BY dead_ratio DESC LIMIT 5;"

echo "Database maintenance fixes applied successfully!" | tee -a "$LOGFILE"
echo "For detailed logs, see $LOGFILE" 