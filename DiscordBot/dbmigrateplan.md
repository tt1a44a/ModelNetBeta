# Migration Plan: SQLite to PostgreSQL for Ollama Scanner

## Overview

This document outlines the step-by-step process to migrate the Ollama Scanner database from SQLite to PostgreSQL. This migration will resolve the "Too many open files" error and improve concurrent database operations during scanning.

## Migration Goals

1. Replace SQLite with PostgreSQL while maintaining existing functionality
2. Implement connection pooling to handle concurrent operations
3. Modify database access patterns across the codebase
4. Add error handling and logging for database operations
5. Ensure all components (Discord bot, scanner, pruner) work with the new database
6. Provide data migration tools to transfer existing data

## Prerequisites

1. PostgreSQL server installation
2. `psycopg2` Python package
3. Connection information (host, port, username, password)
4. Backup of existing SQLite database

## Implementation Steps

### 1. Environment Setup

- [ ] Install PostgreSQL server
- [ ] Create database and user with appropriate permissions
- [ ] Install required Python packages (`psycopg2-binary`, `psycopg2-pool`)
- [ ] Configure connection settings in `.env` file
- [ ] Create database initialization script

### 2. Database Schema Migration

- [ ] Convert SQLite schema to PostgreSQL compatible format
- [ ] Adapt data types (INTEGER → SERIAL, REAL → NUMERIC, etc.)
- [ ] Implement proper foreign key constraints
- [ ] Create indexes for performance optimization
- [ ] Implement schema version tracking

### 3. Connection Management Implementation

- [ ] Create a connection pooling module
- [ ] Implement connection acquisition and release functions
- [ ] Configure optimal pool size based on threading model
- [ ] Add timeout and retry mechanisms
- [ ] Implement monitoring for connection pool health

### 4. Code Modifications

- [ ] Identify all SQLite connection points in code
- [ ] Refactor database functions to use connection pool
- [ ] Update SQL queries for PostgreSQL compatibility
- [ ] Replace `?` parameter syntax with `%s` in parameterized queries
- [ ] Modify transaction handling for PostgreSQL
- [ ] Update any SQLite-specific functionality (PRAGMA statements, etc.)

#### Files requiring changes:

- [ ] `ollama_scanner.py` (main scanner file)
- [ ] `discord_bot.py` (Discord bot implementation)
- [ ] `prune_bad_endpoints.py` (pruning script)
- [ ] `ollama_models.py` (model management)
- [ ] `sync_endpoints_to_servers.py` (endpoint synchronization)
- [ ] All database utility scripts

### 5. Data Migration

- [ ] Create data export script from SQLite
- [ ] Create data import script to PostgreSQL
- [ ] Implement validation checks for migrated data
- [ ] Add resume capability for interrupted migrations
- [ ] Implement migration logging and progress indicators

### 6. Testing Strategy

- [ ] Unit tests for new database functions
- [ ] Integration tests for database operations
- [ ] Concurrency testing with multiple simultaneous operations
- [ ] Performance comparisons (SQLite vs PostgreSQL)
- [ ] Edge case testing (connection failures, network issues)
- [ ] Full-system testing with Discord bot and scanning

### 7. Error Handling and Logging

- [ ] Implement specific exception handling for PostgreSQL errors
- [ ] Add detailed logging for database operations
- [ ] Create recovery mechanisms for common failure scenarios
- [ ] Add monitoring for connection pool status
- [ ] Implement auto-reconnect capabilities

### 8. Deployment Strategy

- [ ] Create backup of original SQLite database
- [ ] Create rollback plan in case of migration failure
- [ ] Update setup and installation scripts
- [ ] Update documentation and README files
- [ ] Create user guide for new PostgreSQL setup

### 9. Post-Migration Tasks

- [ ] Monitor performance and reliability
- [ ] Optimize database configuration based on usage patterns
- [ ] Implement database maintenance tasks (vacuuming, etc.)
- [ ] Create improved backup strategies
- [ ] Update any CI/CD pipelines for PostgreSQL

## File-Specific Changes

### ollama_scanner.py
- Replace SQLite connection handling with PostgreSQL pool
- Update database initialization function
- Modify endpoint verification to use pooled connections
- Update transaction handling for concurrent operations

### discord_bot.py
- Replace all SQLite connections with PostgreSQL pool
- Update model and server queries
- Modify command handlers that interact with database
- Implement connection error handling for user-facing commands

### prune_bad_endpoints.py
- Update connection handling for multi-threaded operations
- Modify bulk update operations for PostgreSQL
- Implement proper transaction handling for pruning operations

### Required New Files
- `db_connection_pool.py` - Central connection pool management
- `migrate_data.py` - Data migration between SQLite and PostgreSQL
- `postgres_init.sql` - Database schema initialization

## Timeline
1. Environment setup and schema migration (Day 1)
2. Core connection pooling implementation (Day 2)
3. Update main scanner functionality (Day 3)
4. Update Discord bot database interactions (Day 4)
5. Update pruning and utility scripts (Day 5)
6. Testing and debugging (Days 6-7)
7. Documentation and deployment (Day 8)

## Risk Mitigation
- Create comprehensive backup strategy before starting
- Implement dual-write capability during transition
- Test thoroughly with production-like workloads
- Create monitoring for database performance
- Prepare rollback plan with detailed steps
