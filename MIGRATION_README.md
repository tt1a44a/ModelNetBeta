# SQLite to PostgreSQL Migration Guide

This document provides step-by-step instructions for migrating the Ollama Scanner database from SQLite to PostgreSQL.

## Prerequisites

1. Docker and Docker Compose installed
2. Python 3.8+ with pip
3. Required Python packages:
   - psycopg2-binary
   - python-dotenv
   - tqdm

## Installation

Install required Python packages:

```bash
pip install psycopg2-binary python-dotenv tqdm
```

## Migration Process

### 1. Configure Environment

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit the `.env` file and configure:
   - Keep `DATABASE_TYPE=sqlite` during migration
   - Set your PostgreSQL credentials
   - Set your Discord bot token

### 2. Start PostgreSQL with Docker

Start the PostgreSQL database in Docker:

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL container on port 5432
- Start pgAdmin for database management on port 5050
- Initialize the database schema using `DiscordBot/postgres_init.sql`

Verify PostgreSQL is running:

```bash
docker ps
```

### 3. Migrate Data

Use the migration script to transfer data from SQLite to PostgreSQL:

```bash
python migrate_data.py
```

The script will:
- Connect to both databases
- Extract data from SQLite
- Create tables in PostgreSQL if needed
- Transfer data with progress indicators
- Validate the migration

### 4. Modify Code (Optional Helper)

A script is provided to help identify and modify SQLite-specific code:

```bash
python modify_db_code.py .
```

This will:
- Scan Python files for SQLite usage
- Suggest replacements using the new `Database` abstraction layer
- Apply changes if requested (`--apply` flag)

### 5. Test PostgreSQL Connection

Test that your application can connect to PostgreSQL:

```bash
# First, test the database module
python database.py

# Then test application components with PostgreSQL
DATABASE_TYPE=postgres python ollama_scanner.py --help
```

### 6. Switch to PostgreSQL

When ready to switch to PostgreSQL permanently:

1. Edit `.env` file and change:
```
DATABASE_TYPE=postgres
```

2. Run your application as normal - it will now use PostgreSQL

## Important Files

- `database.py`: Database abstraction layer for both SQLite and PostgreSQL
- `docker-compose.yml`: PostgreSQL container configuration
- `DiscordBot/postgres_init.sql`: PostgreSQL schema initialization
- `migrate_data.py`: Data migration script
- `modify_db_code.py`: Helper for code modifications

## Using PostgreSQL in Your Code

The `database.py` module provides a unified interface:

```python
from database import Database, init_database

# Initialize database schema
init_database()

# Execute a query
Database.execute("INSERT INTO endpoints (ip, port) VALUES (?, ?)", ("127.0.0.1", 11434))

# Fetch data
servers = Database.fetch_all("SELECT * FROM servers")
```

## Accessing PostgreSQL from Host

Your tools and Discord bot can access the PostgreSQL database using:

- Host: `localhost` or `127.0.0.1` (mapped from container)
- Port: `5432` (or configured port in .env)
- User/Password: As configured in .env
- Database: `ollama_scanner` (or configured name)

## Accessing pgAdmin

pgAdmin is available for database management:

1. Open http://localhost:5050 in your browser
2. Login with credentials from .env:
   - Email: `admin@example.com` (default)
   - Password: `pgadmin_password` (from .env)
3. Add a new server connection:
   - Host: `postgres` (service name in Docker network)
   - Port: `5432`
   - Database: `ollama_scanner`
   - Username: As configured in .env
   - Password: As configured in .env

## Troubleshooting

### Connection Issues

If your application can't connect to PostgreSQL:

1. Check if PostgreSQL container is running:
```bash
docker ps
```

2. Verify PostgreSQL is accepting connections:
```bash
docker exec ollama_scanner_postgres pg_isready
```

3. Check database logs:
```bash
docker logs ollama_scanner_postgres
```

### Migration Issues

If data migration fails:

1. Check the migration log file: `migration.log`
2. Verify SQLite database is not corrupted
3. Make sure PostgreSQL has enough disk space
4. Try running with verbose output: `python migrate_data.py --verbose`

## Rollback Procedure

To rollback to SQLite:

1. Edit `.env` file and change `DATABASE_TYPE=sqlite`
2. Your application will use SQLite again
3. PostgreSQL data remains in the Docker volume

To remove PostgreSQL containers and volumes:

```bash
docker-compose down -v
``` 