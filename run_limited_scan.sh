#!/bin/bash

# Specify a much smaller IP range to scan (example: Cloudflare's range)
# This is just an example - replace with ranges you have permission to scan
TARGET_RANGE="104.16.0.0/12"

# Set a moderate scan rate
SCAN_RATE=1000

# Increase file descriptor limits just for this process
ulimit -n 100000

echo "Running targeted scan of $TARGET_RANGE with rate: $SCAN_RATE packets/sec"
echo "This is a much smaller range than the entire internet"

# Run masscan with the specific range
sudo bash -c "ulimit -n 100000 && masscan $TARGET_RANGE -p 11434 --rate $SCAN_RATE -oG targeted_results.txt"

# If successful, process the results
if [ $? -eq 0 ]; then
  echo "Scan completed successfully"
  echo "Found $(grep -c "Host:" targeted_results.txt) potential hosts"
  
  # Process with the scanner
  python3 ollama_scanner.py --method masscan --input targeted_results.txt --threads 10
else
  echo "Scan failed with error code $?"
fi 