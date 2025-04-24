# Scanner-Pruner-Bot Database Schema

This document describes the database schema for the Scanner-Pruner-Bot integration system.

## Database Schema

The database consists of three main tables:

### `servers` Table

This table stores information about Ollama servers discovered by the scanner.

```sql
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 11434,
    status VARCHAR(50) DEFAULT 'scanned',
    scan_date TIMESTAMP DEFAULT NOW(),
    verified_date TIMESTAMP,
    UNIQUE(ip, port)
);

CREATE INDEX idx_servers_status ON servers(status);
CREATE INDEX idx_servers_scan_date ON servers(scan_date);
```

- `id`: Unique identifier for the server
- `ip`: The IP address of the server
- `port`: The port number (default: 11434)
- `status`: Current status of the server, can be:
  - `scanned`: Endpoint discovered by scanner but not verified
  - `verified`: Endpoint verified as working by pruner
  - `failed`: Endpoint failed verification
- `scan_date`: Timestamp of when the server was last scanned
- `verified_date`: Timestamp of when the server was last verified

### `models` Table

This table stores information about models available on each server.

```sql
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

CREATE INDEX idx_models_name ON models(name);
CREATE INDEX idx_models_server_id ON models(server_id);
```

- `id`: Unique identifier for the model
- `name`: The name of the model
- `server_id`: Reference to the server this model is hosted on
- `params`: Parameter size of the model (e.g., "7B", "13B")
- `quant`: Quantization level of the model (e.g., "Q4_K_M")
- `size`: Size of the model in bytes
- `count`: Counter for how many times this model has been used/queried

### `metadata` Table

This table stores general metadata about the system.

```sql
CREATE TABLE IF NOT EXISTS metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

- `key`: Unique key for the metadata entry
- `value`: Value of the metadata entry
- `updated_at`: Timestamp of when the metadata was last updated

Common metadata keys include:
- `last_scan_start`: Timestamp of when the last scan started
- `last_scan_end`: Timestamp of when the last scan ended
- `last_prune_start`: Timestamp of when the last prune started
- `last_prune_end`: Timestamp of when the last prune ended
- `scanned_count`: Number of servers with 'scanned' status
- `verified_count`: Number of servers with 'verified' status
- `failed_count`: Number of servers with 'failed' status

## Migration Process

Two scripts are provided to help with database setup and migration:

### 1. `init_database.py`

This script initializes the PostgreSQL database with the new schema.

```
python init_database.py
```

Options:
- `--force`: Force reinitialization even if tables exist

### 2. `migrate_to_new_schema.py`

This script migrates data from the existing schema to the new schema.

```
python migrate_to_new_schema.py
```

Options:
- `--force`: Force migration even if target tables exist
- `--dry-run`: Perform a dry run without making changes

The migration script handles two migration paths:
1. SQLite to PostgreSQL: Migrates from the old SQLite database to the new PostgreSQL schema
2. PostgreSQL to PostgreSQL: Migrates from the old PostgreSQL schema to the new PostgreSQL schema

## Environment Configuration

Configure the database connection in the `.env` file:

```
# Database Type (sqlite or postgres)
DATABASE_TYPE=postgres

# SQLite Configuration (for migration source)
SQLITE_DB_PATH=ollama_instances.db

# PostgreSQL Configuration
POSTGRES_DB=ollama_scanner
POSTGRES_USER=ollama
POSTGRES_PASSWORD=ollama_scanner_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Usage Example

```bash
# 1. Initialize the database
python init_database.py

# 2. Migrate existing data (if any)
python migrate_to_new_schema.py

# 3. Update .env to use PostgreSQL
# Change DATABASE_TYPE=sqlite to DATABASE_TYPE=postgres

# 4. Run the scanner and pruner with the new schema
./run_scanner.sh --status scanned --preserve-verified
./run_pruner.sh --input-status scanned --output-status verified --fail-status failed
```

## Troubleshooting

If you encounter any issues:

1. Check the log files:
   - `database_init.log`: Logs from database initialization
   - `migration.log`: Logs from the migration process

2. Ensure the PostgreSQL server is running and accessible.

3. Verify the database connection parameters in the `.env` file.

4. If migration fails, you might need to manually create the schema:
   ```
   psql -U ollama -d ollama_scanner -f schema/postgres_schema.sql
   ``` 