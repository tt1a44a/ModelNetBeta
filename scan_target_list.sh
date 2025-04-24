#!/bin/bash

# Path to the target IPs file
TARGET_FILE="target_ips.txt"

# Check if target file exists
if [ ! -f "$TARGET_FILE" ]; then
  echo "Error: Target file $TARGET_FILE not found!"
  exit 1
fi

# Extract targets from file, ignoring comments and empty lines
TARGETS=$(grep -v "^#" "$TARGET_FILE" | grep -v "^$" | tr '\n' ' ')

if [ -z "$TARGETS" ]; then
  echo "Error: No targets found in $TARGET_FILE"
  exit 1
fi

echo "Found $(echo $TARGETS | wc -w) targets/ranges to scan"

# Set a moderate scan rate
SCAN_RATE=1000

# Increase file descriptor limits for this process
ulimit -n 100000

echo "Running scan with rate: $SCAN_RATE packets/sec"

# Run masscan with the specified targets
sudo bash -c "ulimit -n 100000 && masscan $TARGETS -p 11434 --rate $SCAN_RATE -oG targeted_results.txt"

# If successful, process the results
if [ $? -eq 0 ]; then
  echo "Scan completed successfully"
  echo "Found $(grep -c "Host:" targeted_results.txt) potential hosts"
  
  # Process with the scanner
  python3 ollama_scanner.py --method masscan --input targeted_results.txt --threads 10 --status scanned --preserve-verified
else
  echo "Scan failed with error code $?"
fi 