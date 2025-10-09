#!/bin/bash
# Complete database transfer script - exports locally and imports to VPS
# Usage: ./transfer_database_to_vps.sh user@your-vps-ip [remote_path]

VPS_HOST="$1"
REMOTE_PATH="${2:-/root/ModelNetBeta}"

if [ -z "$VPS_HOST" ]; then
    echo "Usage: $0 <user@vps-ip> [remote_path]"
    echo ""
    echo "Examples:"
    echo "  $0 root@192.168.1.100"
    echo "  $0 root@your-vps.com /home/user/ModelNetBeta"
    echo ""
    exit 1
fi

echo "===================================="
echo "  Complete Database Transfer"
echo "===================================="
echo "VPS: $VPS_HOST"
echo "Remote path: $REMOTE_PATH"
echo ""

# Step 1: Export database locally
echo "Step 1: Exporting local database..."
./export_database.sh

if [ $? -ne 0 ]; then
    echo "Export failed! Aborting."
    exit 1
fi

# Get the latest export file
EXPORT_FILE=$(ls -t database_exports/ollama_scanner_export_*.sql | head -1)

if [ -z "$EXPORT_FILE" ]; then
    echo "Error: No export file found!"
    exit 1
fi

echo ""
echo "Export file: $EXPORT_FILE"
echo "File size: $(du -h "$EXPORT_FILE" | cut -f1)"
echo ""

# Step 2: Transfer to VPS
echo "Step 2: Transferring to VPS..."
echo "This may take a while depending on your connection speed..."
echo ""

scp "$EXPORT_FILE" "$VPS_HOST:$REMOTE_PATH/"

if [ $? -ne 0 ]; then
    echo ""
    echo "Error: Failed to transfer file to VPS!"
    echo "Make sure:"
    echo "  1. You can SSH to $VPS_HOST"
    echo "  2. The remote path $REMOTE_PATH exists"
    echo "  3. You have write permissions"
    exit 1
fi

echo ""
echo "Transfer complete!"
echo ""

# Step 3: Import on VPS
echo "Step 3: Importing on VPS..."
echo ""

EXPORT_FILENAME=$(basename "$EXPORT_FILE")

ssh "$VPS_HOST" "cd $REMOTE_PATH && ./import_database.sh $EXPORT_FILENAME"

if [ $? -eq 0 ]; then
    echo ""
    echo "===================================="
    echo "  Database Transfer Complete!"
    echo "===================================="
    echo ""
    echo "Your database has been successfully transferred and imported to:"
    echo "  $VPS_HOST:$REMOTE_PATH"
    echo ""
    echo "You can now:"
    echo "  1. SSH to your VPS: ssh $VPS_HOST"
    echo "  2. Navigate to: cd $REMOTE_PATH"
    echo "  3. Start the system: ./start_everything.sh"
    echo ""
else
    echo ""
    echo "===================================="
    echo "  Import Failed!"
    echo "===================================="
    echo "The file was transferred but import failed."
    echo "SSH to your VPS and run manually:"
    echo "  ssh $VPS_HOST"
    echo "  cd $REMOTE_PATH"
    echo "  ./import_database.sh $EXPORT_FILENAME"
    exit 1
fi

