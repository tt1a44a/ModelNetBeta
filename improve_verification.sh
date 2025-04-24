#!/bin/bash

# Check if masscan_results.txt exists
if [ ! -f "masscan_results.txt" ]; then
  echo "Error: masscan_results.txt not found!"
  echo "Please run the scan first to generate the results file."
  exit 1
fi

# Count discovered hosts
HOST_COUNT=$(grep -c "Host:" masscan_results.txt)
echo "Found $HOST_COUNT potential hosts in masscan_results.txt"

# Extract IPs only
echo "Extracting IPs from scan results..."
grep -o -E "Host: ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)" masscan_results.txt | cut -d' ' -f2 > ips_to_verify.txt
IP_COUNT=$(wc -l < ips_to_verify.txt)
echo "Extracted $IP_COUNT unique IPs"

# Set more generous timeout
export SCAN_TIMEOUT=15

# Run the scanner with increased timeout and fewer threads for better reliability
echo "Running verification with increased timeout ($SCAN_TIMEOUT seconds) and 10 threads..."
python3 ollama_scanner.py --method masscan --input masscan_results.txt --threads 10 --timeout $SCAN_TIMEOUT --status verified --preserve-verified --verbose

# Report results
echo "Verification complete!"
echo "Check the database for valid Ollama instances:"
echo "python3 query_models.py --list-servers" 