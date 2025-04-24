# Database Maintenance Guide

This document explains the database maintenance procedures for the Ollama Scanner system.

## Overview

Regular database maintenance is essential for ensuring optimal performance, data integrity, and system reliability. This guide covers the tools and procedures implemented for maintaining the PostgreSQL database used by the Ollama Scanner system.

## Maintenance Tools

The following tools are provided for database maintenance:

1. **Database Schema Check**: `check_db_schema_issues.py`
   - Performs comprehensive analysis of the database schema
   - Identifies potential issues, inconsistencies, and optimization opportunities
   - Generates a detailed report with recommendations

2. **Database Maintenance Fix**: `fix_db_maintenance_issues.sql` and `apply_db_maintenance_fixes.sh`
   - Applies fixes for common database issues
   - Updates NULL values in date columns
   - Fixes foreign key constraints
   - Performs VACUUM and ANALYZE operations to optimize performance

## Maintenance Procedures

### Regular Database Health Check

It's recommended to run the database schema check weekly to identify potential issues:

```bash
./check_db_schema_issues.py
```

This will generate a report (`db_schema_issues_report.md`) with any identified issues, warnings, and recommendations.

### Applying Maintenance Fixes

When issues are identified, run the maintenance fix script:

```bash
./apply_db_maintenance_fixes.sh
```

This script will:
1. Update NULL values in verification_date and last_check_date columns
2. Fix foreign key constraints to ensure proper cascading deletes
3. Perform VACUUM and ANALYZE operations to reclaim space and update statistics
4. Generate a detailed log of all operations performed

### Monitoring Database Size

To monitor database size and growth, use PostgreSQL's built-in functions:

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

### Automated Maintenance

A cron job should be set up to run the maintenance tasks automatically:

```bash
# Add to crontab (crontab -e)
# Run database maintenance every Sunday at 3:00 AM
0 3 * * 0 cd /path/to/ollama_scanner && ./check_db_schema_issues.py && ./apply_db_maintenance_fixes.sh
```

## Backup Procedures

Regular backups are essential. The following backup script is included:

```bash
# Backup the database
pg_dump -h localhost -p 5433 -U ollama -d ollama_scanner -F c -f backups/ollama_scanner_$(date +%Y%m%d_%H%M%S).backup
```

It's recommended to run this backup script daily and retain backups for at least 30 days.

## Database Recovery

If database recovery is needed, use the following command:

```bash
# Restore from backup
pg_restore -h localhost -p 5433 -U ollama -d ollama_scanner -c backups/ollama_scanner_YYYYMMDD_HHMMSS.backup
```

## Performance Optimization

For optimal performance:

1. **Regular Maintenance**: Run VACUUM ANALYZE weekly
2. **Index Optimization**: Periodically review unused indexes
3. **Connection Pooling**: Use connection pooling to manage database connections efficiently
4. **Query Optimization**: Monitor and optimize slow queries using pg_stat_statements

## Conclusion

Regular database maintenance is crucial for the Ollama Scanner system's performance and reliability. By following these procedures, you can ensure your database remains healthy and optimized.

For assistance with database issues, refer to the PostgreSQL documentation or contact the system administrator. 