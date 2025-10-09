#!/bin/bash
# Import PostgreSQL database into Docker container
# This script is meant to run on the VPS

IMPORT_FILE="$1"

if [ -z "$IMPORT_FILE" ]; then
    echo "Usage: $0 <export_file.sql>"
    echo ""
    echo "Example:"
    echo "  $0 ollama_scanner_export_20251009_123456.sql"
    echo ""
    echo "Available export files:"
    ls -lh database_exports/*.sql 2>/dev/null || echo "  No export files found"
    exit 1
fi

if [ ! -f "$IMPORT_FILE" ]; then
    echo "Error: File not found: $IMPORT_FILE"
    exit 1
fi

echo "===================================="
echo "  Database Import Script"
echo "===================================="
echo ""
echo "Import file: $IMPORT_FILE"
echo "File size: $(du -h "$IMPORT_FILE" | cut -f1)"
echo ""

# Check if container is running
if ! docker ps | grep -q ollama_scanner_postgres; then
    echo "PostgreSQL container not running. Starting it..."
    docker-compose up -d postgres
    echo "Waiting for PostgreSQL to be ready..."
    sleep 10
fi

# Wait for PostgreSQL to be ready
echo "Checking if PostgreSQL is ready..."
for i in {1..30}; do
    if docker exec ollama_scanner_postgres pg_isready -U ollama -d postgres &>/dev/null; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "WARNING: This will DROP and RECREATE the database!"
echo "All existing data will be replaced with the imported data."
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Import cancelled."
    exit 0
fi

echo ""
echo "Importing database..."
echo "This may take a few minutes depending on database size..."
echo ""

# Import the database dump
cat "$IMPORT_FILE" | docker exec -i ollama_scanner_postgres psql -U ollama -d postgres

if [ $? -eq 0 ]; then
    echo ""
    echo "===================================="
    echo "  Import Successful!"
    echo "===================================="
    echo ""
    
    # Show statistics
    echo "Database Statistics:"
    docker exec ollama_scanner_postgres psql -U ollama -d ollama_scanner -t -c \
        "SELECT 
            'Endpoints: ' || COUNT(*) FROM endpoints
         UNION ALL
         SELECT 'Verified: ' || COUNT(*) FROM endpoints WHERE verified > 0
         UNION ALL
         SELECT 'Honeypots: ' || COUNT(*) FROM endpoints WHERE is_honeypot=true
         UNION ALL
         SELECT 'Models: ' || COUNT(*) FROM models;"
    
    echo ""
    echo "Database import complete!"
    echo ""
    echo "Next steps:"
    echo "1. Start the scanner and pruner:"
    echo "   ./run_both.sh --scanner-method shodan --pruner-workers 10"
    echo ""
    echo "2. Start the Discord bot:"
    echo "   cd DiscordBot && ./run_bot.sh"
    echo ""
    echo "3. Query the database:"
    echo "   python query_models_fixed.py servers"
    echo ""
else
    echo ""
    echo "===================================="
    echo "  Import Failed!"
    echo "===================================="
    echo "Check the error messages above."
    exit 1
fi

