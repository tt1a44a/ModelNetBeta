# Database Transfer Guide

Complete guide for transferring your Ollama Scanner database from local to VPS.

## Quick Start

### Option 1: Automatic Transfer (Recommended)
Transfer everything in one command:
```bash
./transfer_database_to_vps.sh root@your-vps-ip
```

### Option 2: Manual Transfer
If you prefer manual control:

**On Local Machine:**
```bash
# Export database
./export_database.sh
```

**Transfer file to VPS:**
```bash
scp database_exports/ollama_scanner_export_*.sql root@your-vps:/root/ModelNetBeta/
```

**On VPS:**
```bash
# Import database
cd /root/ModelNetBeta
./import_database.sh ollama_scanner_export_20251009_123456.sql
```

## What Gets Transferred

The database export includes:
- ✅ **All endpoints** (1,340 total)
  - Verified endpoints (162)
  - Unverified endpoints (1,178)
  - Honeypots detected (127)
- ✅ **All models** associated with endpoints
- ✅ **Metadata** (scan history, statistics)
- ✅ **Schema** (tables, indexes, constraints)

## Prerequisites

### Local Machine
- Docker container running with PostgreSQL
- Export scripts in place

### VPS
- Docker and Docker Compose installed
- ModelNetBeta repository cloned
- SSH access configured
- Import script in place

## Detailed Steps

### 1. Export Database Locally

```bash
cd /home/adam/Documents/git/ModelNetBeta
./export_database.sh
```

**Output:**
- Creates `database_exports/ollama_scanner_export_TIMESTAMP.sql`
- Shows database statistics
- Displays file size

**What it exports:**
- Complete schema (DROP IF EXISTS, then CREATE)
- All table data
- Indexes and constraints
- No ownership/privilege info (for portability)

### 2. Transfer to VPS

**Manual SCP:**
```bash
scp database_exports/ollama_scanner_export_*.sql root@192.168.1.100:/root/ModelNetBeta/
```

**Using transfer script:**
```bash
./transfer_database_to_vps.sh root@192.168.1.100 /root/ModelNetBeta
```

**Transfer size:**
- Expect ~1-10 MB for 1,340 endpoints (depends on data)
- Transfer time depends on connection speed

### 3. Import on VPS

**SSH to VPS:**
```bash
ssh root@your-vps-ip
cd /root/ModelNetBeta
```

**Run import:**
```bash
./import_database.sh ollama_scanner_export_20251009_123456.sql
```

**What happens:**
1. Checks if PostgreSQL container is running
2. Starts container if needed
3. Waits for PostgreSQL to be ready
4. Prompts for confirmation (destructive operation!)
5. Drops existing database
6. Imports new data
7. Shows statistics

### 4. Verify Import

**Check database statistics:**
```bash
docker exec ollama_scanner_postgres psql -U ollama -d ollama_scanner -c "
SELECT 
    (SELECT COUNT(*) FROM endpoints) as endpoints,
    (SELECT COUNT(*) FROM endpoints WHERE verified > 0) as verified,
    (SELECT COUNT(*) FROM models) as models;"
```

**Query endpoints:**
```bash
python query_models_fixed.py servers
```

## Troubleshooting

### Export fails: "Container not running"
```bash
docker-compose up -d postgres
sleep 10
./export_database.sh
```

### Transfer fails: "Permission denied"
```bash
# Ensure SSH key is configured or use password
ssh-copy-id root@your-vps-ip
```

### Import fails: "Database already exists"
The script handles this automatically with DROP/CREATE.
If it fails, manually drop:
```bash
docker exec ollama_scanner_postgres psql -U ollama -d postgres -c "DROP DATABASE IF EXISTS ollama_scanner;"
```

### Verify schema version
```bash
docker exec ollama_scanner_postgres psql -U ollama -d ollama_scanner -c "SELECT * FROM schema_version;"
```

## Automation

### Scheduled Backups
Add to crontab for daily backups:
```bash
0 2 * * * cd /home/adam/Documents/git/ModelNetBeta && ./export_database.sh
```

### Sync to VPS Daily
```bash
0 3 * * * cd /home/adam/Documents/git/ModelNetBeta && ./transfer_database_to_vps.sh root@your-vps
```

## File Locations

**Local:**
- Export script: `./export_database.sh`
- Exports directory: `./database_exports/`
- Transfer script: `./transfer_database_to_vps.sh`

**VPS:**
- Import script: `./import_database.sh`
- Docker Compose: `./docker-compose.yml`
- Database in Docker volume: `postgres_data`

## Security Notes

1. **Backup first!** Export creates a new file, doesn't delete anything
2. **Import is destructive!** It drops and recreates the database
3. **Transfer over SSH** uses encrypted connection
4. **Database dumps are plain text** - contain all your data
5. **Don't commit exports to git** - they're in `.gitignore`

## Post-Import Checklist

- [ ] Database statistics match local
- [ ] Start scanner: `./run_scanner.sh --method shodan`
- [ ] Start pruner: `./run_pruner.sh --workers 10`
- [ ] Start Discord bot: `cd DiscordBot && ./run_bot.sh`
- [ ] Verify endpoints: `python query_models_fixed.py servers`
- [ ] Check logs: `tail -f database.log`

## Need Help?

- Check Docker logs: `docker-compose logs postgres`
- View export file: `head -100 database_exports/your_export.sql`
- Test connection: `docker exec ollama_scanner_postgres psql -U ollama -d ollama_scanner -c "SELECT 1;"`

