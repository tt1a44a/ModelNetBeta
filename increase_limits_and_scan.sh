#!/bin/bash

# Increase file descriptor limits for current session
echo "Increasing file descriptor limits..."
ulimit -n 100000
echo "New file descriptor limit: $(ulimit -n)"

# Increase socket buffer sizes (requires root)
echo "Attempting to increase socket buffer sizes..."
sudo sysctl -w net.core.rmem_max=26214400
sudo sysctl -w net.core.rmem_default=26214400
sudo sysctl -w net.core.wmem_max=26214400
sudo sysctl -w net.core.wmem_default=26214400

# Increase max backlog queue for TCP connections
sudo sysctl -w net.core.netdev_max_backlog=2000
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=8192

# Set scan rate - lower for reliability, higher for speed
SCAN_RATE=1000

# Run masscan with exclusions for protected networks
echo "Starting masscan with rate: $SCAN_RATE packets/sec"
sudo masscan 0.0.0.0/0 -p 11434 --rate $SCAN_RATE -oG masscan_results.txt \
  --exclude 255.255.255.255,127.0.0.0/8,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12,169.254.0.0/16,224.0.0.0/4,240.0.0.0/4

# Check if masscan completed successfully
if [ $? -eq 0 ]; then
  echo "Masscan completed successfully!"
  echo "Results saved to masscan_results.txt"
  echo "Lines in results file: $(wc -l < masscan_results.txt)"
  
  # Process the results with the scanner
  echo "Processing results with ollama_scanner.py..."
  python3 ollama_scanner.py --method masscan --input masscan_results.txt --threads 25 --status scanned --preserve-verified
else
  echo "Masscan exited with an error."
fi 