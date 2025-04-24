# Honeypot Detection and Inactive Endpoint Implementation

This document outlines the implementation of honeypot detection and inactive endpoint tracking in the Ollama Scanner database.

## 1. Database Schema Changes

The following columns have been added to the `endpoints` table:

**Honeypot Detection:**
- `is_honeypot` - Boolean (PostgreSQL) / Integer (SQLite) - Indicates if the endpoint is a honeypot
- `honeypot_reason` - Text field that stores the reason why the endpoint was flagged as a honeypot

**Inactive Endpoint Tracking:**
- `is_active` - Boolean (PostgreSQL) / Integer (SQLite) - Indicates if the endpoint is active and responding
- `inactive_reason` - Text field that stores the reason why the endpoint was flagged as inactive
- `last_check_date` - Timestamp when the endpoint was last checked

**New Indexes:**
- `idx_endpoints_honeypot` - For faster filtering of honeypot endpoints
- `idx_endpoints_active` - For faster filtering of active endpoints
- `idx_endpoints_verified_honeypot` - For filtering verified non-honeypot endpoints
- `idx_endpoints_verified_active` - For filtering verified active endpoints

## 2. Migration Script

The `migrate_honeypot_columns.py` script adds the new columns to existing databases:

- Supports both PostgreSQL and SQLite
- Checks if the columns already exist before attempting to add them
- Creates appropriate indexes for performance
- Updates the metadata table to track migration status
- Updates the schema version to `1.1.0-honeypot`

**Usage:**
```bash
# Run the migration in dry-run mode (no changes)
python migrate_honeypot_columns.py --dry-run

# Run the migration
python migrate_honeypot_columns.py

# Run with verbose output
python migrate_honeypot_columns.py --verbose
```

## 3. Implementation Steps

1. **Backup Your Database**
   ```bash
   pg_dump -U ollama ollama_scanner > ollama_scanner_backup_$(date +%Y%m%d).sql
   ```

2. **Run the Migration Script**
   ```bash
   python migrate_honeypot_columns.py
   ```

3. **Update Endpoint Processing Code**
   - Update pruning script to mark honeypots using `is_honeypot` and `honeypot_reason`
   - Update verification logic to mark inactive endpoints using `is_active` and `inactive_reason`
   - Update verification process to reset honeypot and inactive flags when endpoints are verified

4. **Update Discord Bot Queries**
   - Modify model selection queries to exclude honeypots and inactive endpoints
   - Add honeypot statistics commands for monitoring

## 4. Query Examples

### Filtering Out Honeypots and Inactive Endpoints

```sql
SELECT m.id, m.name, m.parameter_size, m.quantization_level, e.ip, e.port
FROM models m
JOIN endpoints e ON m.endpoint_id = e.id
WHERE LOWER(m.name) = LOWER('llama3') 
  AND e.verified = 1 
  AND (e.is_honeypot = FALSE OR e.is_honeypot IS NULL)
  AND (e.is_active = TRUE OR e.is_active IS NULL)
ORDER BY RANDOM()
LIMIT 1;
```

### Honeypot Statistics

```sql
-- Get total count of honeypots
SELECT COUNT(*) FROM endpoints WHERE is_honeypot = TRUE;

-- Get most common honeypot reasons
SELECT honeypot_reason, COUNT(*) as count
FROM endpoints
WHERE is_honeypot = TRUE
GROUP BY honeypot_reason
ORDER BY count DESC
LIMIT 5;
```

## 5. Benefits

1. **Improved Quality**: Users will only interact with legitimate, functioning Ollama endpoints
2. **Better Monitoring**: Admins can track honeypots and inactive endpoints
3. **Persistence**: Honeypot detection is now stored in the database, not just in memory
4. **Performance**: Added indexes optimize query performance 