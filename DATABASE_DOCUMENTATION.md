# Ollama Scanner Database Documentation

This document provides comprehensive documentation for the Ollama Scanner database system, including the schema, maintenance procedures, and fixes implemented.

## Table of Contents

1. [Database Schema](#database-schema)
2. [Schema Fixes](#schema-fixes)
   - [View Update Fix](#view-update-fix)
   - [Database Maintenance](#database-maintenance)
3. [Maintenance Procedures](#maintenance-procedures)
   - [Regular Health Checks](#regular-health-checks)
   - [Backup and Recovery](#backup-and-recovery)
   - [Automated Maintenance](#automated-maintenance)
4. [Common Operations](#common-operations)
5. [Scripts and Tools](#scripts-and-tools)
6. [Troubleshooting](#troubleshooting)

## Database Schema

The Ollama Scanner system uses a PostgreSQL database with the following main tables:

1. **endpoints**: Stores information about discovered Ollama endpoints
   - `id`: Primary key
   - `ip`: IP address of the endpoint
   - `port`: Port number (default: 11434)
   - `scan_date`: Timestamp of when the endpoint was scanned
   - `verified`: Status (0=unverified, 1=verified, 2=failed)
   - `verification_date`: Timestamp of when the endpoint was last verified
   - `is_honeypot`: Boolean flag for honeypot endpoints
   - `honeypot_reason`: Reason why endpoint was flagged as honeypot
   - `is_active`: Boolean flag for active endpoints
   - `inactive_reason`: Reason why endpoint was marked inactive
   - `last_check_date`: Timestamp of last status check

2. **verified_endpoints**: Links to verified endpoints in the endpoints table
   - `id`: Primary key
   - `endpoint_id`: Foreign key to endpoints.id
   - `verification_date`: Timestamp of verification

3. **models**: Stores information about models available on endpoints
   - `id`: Primary key
   - `endpoint_id`: Foreign key to endpoints.id
   - `name`: Model name
   - `parameter_size`: Size of the model (e.g., "7B", "13B")
   - `quantization_level`: Quantization level of the model (e.g., "Q4_K_M")
   - `size_mb`: Size of the model in MB

4. **benchmark_results**: Stores performance benchmark results for endpoints
   - `id`: Primary key
   - `endpoint_id`: Foreign key to endpoints.id
   - `model_id`: Foreign key to models.id
   - Various performance metrics fields

5. **metadata**: Stores system metadata and statistics
   - `key`: Primary key (string)
   - `value`: Value corresponding to the key
   - `updated_at`: Timestamp of last update

6. **servers** (VIEW): Backward compatibility view that combines endpoints and verified_endpoints
   - `id`: From endpoints.id
   - `ip`: From endpoints.ip
   - `port`: From endpoints.port
   - `scan_date`: From endpoints.scan_date

### Relationships

- An endpoint can have many models (one-to-many)
- An endpoint can have many benchmark results (one-to-many)
- A model can have many benchmark results (one-to-many)
- A verified endpoint must have one corresponding endpoint (one-to-one)

## Schema Fixes

### View Update Fix

The `servers` view is used for backward compatibility with older code that expected a `servers` table. Initially, this view had issues with data synchronization since changes to the view did not propagate to the underlying tables. 

**The fix implemented INSTEAD OF triggers for INSERT, UPDATE, and DELETE operations:**

1. **INSTEAD OF INSERT**: When a record is inserted into the `servers` view, the trigger:
   - Inserts a new record into the `endpoints` table with `verified = 1`
   - Inserts a matching record into the `verified_endpoints` table
   - Handles conflict cases (duplicate IP/port) gracefully

2. **INSTEAD OF UPDATE**: When a record in the `servers` view is updated, the trigger:
   - Updates the corresponding record in the `endpoints` table
   - Maintains the relationship with `verified_endpoints`

3. **INSTEAD OF DELETE**: When a record is deleted from the `servers` view, the trigger:
   - Deletes the corresponding record from the `endpoints` table
   - The deletion cascades to `verified_endpoints` through foreign key constraints

This fix ensures that all components (scanner, pruner, Discord bot) can read and write to the database consistently.

**Implementation Files:**
- [fix_servers_view.sql](fix_servers_view.sql): SQL commands to create the INSTEAD OF triggers
- [apply_view_update_fix.sh](apply_view_update_fix.sh): Script to apply the fix and verify it works
- [VIEW_UPDATE_FIX_README.md](VIEW_UPDATE_FIX_README.md): Detailed documentation of the fix

### Database Maintenance

A comprehensive database schema review identified several maintenance issues that were fixed:

1. **NULL Values in Date Columns**: Updated NULL values in `verification_date` and `last_check_date` columns
2. **Foreign Key Constraints**: Fixed the `benchmark_results_model_id_fkey` to use `CASCADE` for delete operations
3. **Table Bloat**: Performed `VACUUM ANALYZE` on tables with high dead tuple percentages
4. **Data Consistency**: Ensured consistency between `endpoints.verified=1` and `verified_endpoints` records

**Implementation Files:**
- [check_db_schema_issues.py](check_db_schema_issues.py): Script to check for database schema issues
- [db_schema_issues_report.md](db_schema_issues_report.md): Report of identified issues
- [fix_db_maintenance_issues.sql](fix_db_maintenance_issues.sql): SQL commands to fix maintenance issues
- [apply_db_maintenance_fixes.sh](apply_db_maintenance_fixes.sh): Script to apply maintenance fixes

## Maintenance Procedures

### Regular Health Checks

Regular database health checks should be performed to identify potential issues:

```bash
./check_db_schema_issues.py
```

This script performs a comprehensive analysis of the database schema and generates a report with any identified issues, warnings, and recommendations.

### Backup and Recovery

Regular backups are essential for data safety:

```bash
# Create a backup
./backup_database.sh

# Restore from a backup
./restore_database.sh --file backups/ollama_scanner_20250418_120000.backup
# OR
./restore_database.sh --latest
```

The backup script creates a compressed backup of the database and maintains a symlink to the latest backup. It also automatically cleans up backups older than 30 days. The restore script includes safety features such as creating a pre-restore backup and validating the restored database.

### Automated Maintenance

Automated maintenance can be set up using the provided script:

```bash
./setup_db_maintenance.sh
```

This script sets up cron jobs for:
- Daily backups
- Weekly maintenance (schema check and fixes)
- Monthly full maintenance (including VACUUM FULL)

To check the status of the maintenance tasks:

```bash
./check_maintenance_status.sh
```

## Common Operations

### Adding a New Index

If performance analysis suggests a new index is needed:

```sql
-- Example: Add an index on endpoints.last_check_date
CREATE INDEX idx_endpoints_last_check_date ON endpoints(last_check_date);
```

### Checking Table Sizes

To monitor database growth:

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('ollama_scanner')) AS db_size;

-- Check table sizes
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size
FROM
    pg_catalog.pg_statio_user_tables
ORDER BY
    pg_total_relation_size(relid) DESC;
```

### Manually Running VACUUM

To reclaim space and update statistics:

```sql
-- Regular vacuum
VACUUM ANALYZE endpoints;

-- Full vacuum (locks the table but reclaims more space)
VACUUM FULL ANALYZE endpoints;
```

## Scripts and Tools

| Script | Description |
|--------|-------------|
| `check_db_schema_issues.py` | Checks for database schema issues and generates a report |
| `fix_servers_view.sql` | SQL commands to create INSTEAD OF triggers for the servers view |
| `apply_view_update_fix.sh` | Applies the servers view update fix |
| `fix_db_maintenance_issues.sql` | SQL commands to fix database maintenance issues |
| `apply_db_maintenance_fixes.sh` | Applies database maintenance fixes |
| `backup_database.sh` | Creates a compressed backup of the database |
| `restore_database.sh` | Restores the database from a backup |
| `setup_db_maintenance.sh` | Sets up automated database maintenance via cron |
| `check_maintenance_status.sh` | Checks the status of database maintenance tasks |

## Troubleshooting

### Common Issues and Solutions

1. **Connection Issues**
   - Check the `.env` file for correct database connection parameters
   - Verify the PostgreSQL server is running: `ps aux | grep postgres`
   - Test connection: `PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT version();"`

2. **Data Inconsistency Between Components**
   - Run `./apply_view_update_fix.sh` to ensure the servers view has the proper triggers
   - Run `./apply_db_maintenance_fixes.sh` to fix any inconsistencies between tables

3. **Performance Issues**
   - Run `VACUUM ANALYZE` on the affected tables
   - Check for missing indexes using `./check_db_schema_issues.py`
   - Review query patterns and add appropriate indexes

4. **Backup Failures**
   - Check disk space: `df -h`
   - Verify PostgreSQL user has permission to run pg_dump
   - Check the backup logs in the backups directory

### Logs and Monitoring

Important log files:
- `db_schema_check.log`: Logs from the schema check script
- `view_update_fix.log`: Logs from the view update fix script
- `db_maintenance_fix.log`: Logs from the maintenance fix script
- `backups/backup_*.log`: Logs from the backup script
- `backups/restore_*.log`: Logs from the restore script
- `backups/cron_*.log`: Logs from the cron jobs

For additional help, consult the PostgreSQL documentation or contact the system administrator. 