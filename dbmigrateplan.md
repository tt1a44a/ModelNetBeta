# Database Migration Plan: SQLite to PostgreSQL

## Overview
This document outlines the plan for migrating the Ollama Scanner database from SQLite to PostgreSQL. The migration is necessary to improve performance, enable concurrent access, and provide better scalability as the application grows.

## Current Architecture
- **Database Engine**: SQLite
- **Location**: Local file-based database (`ollama_instances.db`)
- **Key Components Dependent on DB**:
  - Discord Bot
  - Benchmarking tools
  - Scanner components

## Target Architecture
- **Database Engine**: PostgreSQL 15
- **Deployment**: Docker container (for development/testing), dedicated instance (for production)
- **Connection**: Connection pooling for improved performance

## Migration Steps

### 1. Preparation Phase
- [x] Create a Docker Compose configuration for PostgreSQL
- [x] Create an example .env file with configuration options
- [ ] Add connection utilities for both database types
- [ ] Create database backup mechanism

### 2. Schema Migration
- [ ] Extract schema from SQLite database
- [ ] Create PostgreSQL-compatible schema
- [ ] Handle data type differences (SQLite vs PostgreSQL)
- [ ] Implement indices and constraints

### 3. Data Migration
- [ ] Develop migration script to transfer data
- [ ] Implement data validation to ensure integrity
- [ ] Create test cases to verify data consistency

### 4. Application Updates
- [ ] Modify database connection code to support both SQLite and PostgreSQL
- [ ] Implement connection pooling for PostgreSQL
- [ ] Update queries to be compatible with PostgreSQL syntax
- [ ] Add configuration option to switch between database types

### 5. Testing
- [ ] Unit tests for database connection and operations
- [ ] Integration tests for Discord bot functionality
- [ ] Benchmark tests to compare performance
- [ ] Error handling and edge case testing

### 6. Deployment
- [ ] Create deployment instructions for PostgreSQL
- [ ] Update documentation with new database configuration
- [ ] Provide rollback procedure in case of issues

## Database Tables to Migrate

1. `models` - Model information
2. `servers` - Server information
3. `instances` - Ollama instances
4. `benchmark_results` - Benchmark test results
5. `ip_info` - IP geolocation data
6. Additional metadata tables

## Type Mapping

| SQLite Type | PostgreSQL Type |
|-------------|-----------------|
| INTEGER     | INTEGER or BIGINT |
| TEXT        | TEXT |
| REAL        | DOUBLE PRECISION |
| BLOB        | BYTEA |
| NULL        | NULL |
| DATETIME    | TIMESTAMP |
| BOOLEAN     | BOOLEAN |

## Risk Mitigation
- Maintain SQLite support during transition
- Implement feature flag to switch between database engines
- Comprehensive testing before deployment
- Backup and restore procedures

## Timeline
- Development: 1 week
- Testing: 3 days
- Deployment: 1 day
- Verification and Monitoring: 3 days

## Success Criteria
- All functionality works with PostgreSQL
- No data loss during migration
- Equal or better performance with PostgreSQL
- All application components operate properly with new database 