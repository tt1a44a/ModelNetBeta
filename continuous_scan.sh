#!/bin/bash

# Set default values
TARGET_IPS="${1:-192.168.0.0/24}"  # Replace with your target IP range(s)
SCAN_RATE="${2:-1000}"  # Default scan rate
INTERVAL="${3:-3600}"  # Default interval of 1 hour between scans
DB_PATH="${4:-ollama_servers.db}"  # Default database path
STATUS="${5:-scanned}"  # Default status to assign
PRESERVE="${6:-true}"  # Whether to preserve verified instances

echo "Starting continuous Ollama scanning..."
echo "Target IPs: $TARGET_IPS"
echo "Scan rate: $SCAN_RATE packets/sec"
echo "Interval: $INTERVAL seconds"
echo "Database: $DB_PATH"
echo "Status: $STATUS"
echo "Preserve verified: $PRESERVE"

# Set preserve option based on the PRESERVE variable
if [ "$PRESERVE" = "true" ]; then
  PRESERVE_OPTION="--preserve-verified"
else
  PRESERVE_OPTION="--no-preserve-verified"
fi

# Run indefinitely
while true; do
  echo "----------------------------------------"
  echo "Starting scan at $(date)"
  echo "----------------------------------------"
  
  # Run the scan
  python3 ollama_scanner.py --method masscan --network $TARGET_IPS --rate $SCAN_RATE --db $DB_PATH --status $STATUS $PRESERVE_OPTION
  
  # Show timestamp for next scan
  echo "----------------------------------------"
  echo "Scan completed at $(date)"
  echo "Next scan will start in $INTERVAL seconds"
  echo "----------------------------------------"
  
  # Wait for the specified interval
  sleep $INTERVAL
done 