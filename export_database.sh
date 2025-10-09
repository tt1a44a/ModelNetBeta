#!/bin/bash
# Export PostgreSQL database from Docker container
# This creates a complete database dump including schema and all data

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE="ollama_scanner_export_${TIMESTAMP}.sql"
BACKUP_DIR="database_exports"

echo "===================================="
echo "  Database Export Script"
echo "===================================="
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if container is running
if ! docker ps | grep -q ollama_scanner_postgres; then
    echo "Error: PostgreSQL container is not running!"
    echo "Start it with: docker-compose up -d postgres"
    exit 1
fi

echo "Exporting database from Docker container..."
echo "Container: ollama_scanner_postgres"
echo "Database: ollama_scanner"
echo "Export file: $BACKUP_DIR/$EXPORT_FILE"
echo ""

# Export database using pg_dump
docker exec ollama_scanner_postgres pg_dump -U ollama -d ollama_scanner \
    --clean \
    --if-exists \
    --create \
    --format=plain \
    --no-owner \
    --no-privileges \
    > "$BACKUP_DIR/$EXPORT_FILE"

if [ $? -eq 0 ]; then
    # Get file size
    SIZE=$(du -h "$BACKUP_DIR/$EXPORT_FILE" | cut -f1)
    
    echo "===================================="
    echo "  Export Successful!"
    echo "===================================="
    echo "File: $BACKUP_DIR/$EXPORT_FILE"
    echo "Size: $SIZE"
    echo ""
    
    # Get database statistics
    echo "Database Statistics:"
    docker exec ollama_scanner_postgres psql -U ollama -d ollama_scanner -t -c \
        "SELECT 
            (SELECT COUNT(*) FROM endpoints) as total_endpoints,
            (SELECT COUNT(*) FROM endpoints WHERE verified > 0) as verified,
            (SELECT COUNT(*) FROM endpoints WHERE is_honeypot=true) as honeypots,
            (SELECT COUNT(*) FROM models) as total_models;"
    
    echo ""
    echo "===================================="
    echo "Transfer to VPS:"
    echo "===================================="
    echo "1. Copy to VPS:"
    echo "   scp $BACKUP_DIR/$EXPORT_FILE user@your-vps:/path/to/ModelNetBeta/"
    echo ""
    echo "2. On VPS, import with:"
    echo "   ./import_database.sh $EXPORT_FILE"
    echo ""
    echo "Or use the combined script:"
    echo "   ./transfer_database_to_vps.sh user@your-vps"
    echo "===================================="
else
    echo "===================================="
    echo "  Export Failed!"
    echo "===================================="
    echo "Check if the database container is running properly."
    exit 1
fi

