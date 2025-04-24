# Ollama Scanner Database System

Welcome to the Ollama Scanner Database System documentation. This README provides an overview of the database system and links to detailed documentation.

## Overview

The Ollama Scanner system uses a PostgreSQL database to store information about Ollama endpoints, models, and benchmark results. The database system has been optimized for reliability, performance, and ease of maintenance.

## Quick Start

### Setup

1. Ensure PostgreSQL is installed and running
2. Configure database connection parameters in `.env`
3. Initialize the database (if not already done):
   ```bash
   ./setup_database.sh
   ```

### Basic Commands

```bash
# Check database health
./check_db_schema_issues.py

# Run maintenance
./apply_db_maintenance_fixes.sh

# Create a backup
./backup_database.sh

# Restore from the latest backup
./restore_database.sh --latest

# Set up automated maintenance
./setup_db_maintenance.sh
```

## Documentation

The database system is thoroughly documented. Here are the key documents:

- [Database Documentation](DATABASE_DOCUMENTATION.md) - Comprehensive documentation of the schema, maintenance procedures, and operations
- [Database Maintenance Guide](DATABASE_MAINTENANCE_README.md) - Guide for maintaining the database system
- [View Update Fix](VIEW_UPDATE_FIX_README.md) - Documentation of the servers view update fix
- [Implementation Summary](DATABASE_IMPLEMENTATION_SUMMARY.md) - Summary of the database improvements implemented

## Maintenance Scripts

| Script | Purpose |
|--------|---------|
| `check_db_schema_issues.py` | Check for database schema issues |
| `apply_db_maintenance_fixes.sh` | Apply database maintenance fixes |
| `backup_database.sh` | Create a database backup |
| `restore_database.sh` | Restore the database from a backup |
| `setup_db_maintenance.sh` | Set up automated maintenance tasks |
| `check_maintenance_status.sh` | Check maintenance status |

## Schema Overview

The database consists of several key tables:

- `endpoints` - Stores information about discovered Ollama endpoints
- `verified_endpoints` - Links to verified endpoints
- `models` - Stores information about models available on endpoints
- `benchmark_results` - Stores performance benchmark results
- `metadata` - Stores system metadata and statistics
- `servers` (VIEW) - Backward compatibility view combining endpoints and verified_endpoints

For a detailed schema description, see the [Database Documentation](DATABASE_DOCUMENTATION.md#database-schema).

## Troubleshooting

If you encounter issues with the database system, see the [Troubleshooting](DATABASE_DOCUMENTATION.md#troubleshooting) section in the Database Documentation.

## Recent Improvements

Recent improvements to the database system include:

1. View Update Fix - Implementation of INSTEAD OF triggers for the servers view
2. Database Schema Review - Comprehensive check of the database schema
3. Database Maintenance - Tools for regular maintenance
4. Backup and Recovery - Robust backup and recovery procedures
5. Documentation - Comprehensive documentation of all database aspects

For details, see the [Implementation Summary](DATABASE_IMPLEMENTATION_SUMMARY.md).

## Contributing

If you make changes to the database system, please update the relevant documentation and ensure all scripts are working properly.

## License

This software is part of the Ollama Scanner project and is subject to its licensing terms. 