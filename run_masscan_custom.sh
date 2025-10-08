#!/bin/bash
# Custom masscan runner with configurable target ranges
# Usage: ./run_masscan_custom.sh <target_range> [rate] [threads]
#
# Examples:
#   ./run_masscan_custom.sh "104.16.0.0/12"
#   ./run_masscan_custom.sh "192.168.1.0/24" 1000 10
#   ./run_masscan_custom.sh "8.8.8.0/24,1.1.1.0/24" 5000 20

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Error: This script must be run as root (masscan requires root privileges)"
    echo "Please run: sudo $0 $@"
    exit 1
fi

# Get target range from argument
TARGET_RANGE="${1}"
SCAN_RATE="${2:-10000}"  # Default: 10000 pps
THREADS="${3:-25}"        # Default: 25 threads
PORT="11434"              # Ollama default port

# Validate target range
if [ -z "$TARGET_RANGE" ]; then
    echo "Error: No target range specified"
    echo ""
    echo "Usage: $0 <target_range> [rate] [threads]"
    echo ""
    echo "Examples:"
    echo "  $0 \"104.16.0.0/12\""
    echo "  $0 \"192.168.1.0/24\" 1000 10"
    echo "  $0 \"8.8.8.0/24,1.1.1.0/24\" 5000 20"
    echo ""
    echo "WARNING: Only scan networks you own or have explicit permission to scan!"
    exit 1
fi

echo "===================================="
echo "     Masscan Scanner for Ollama     "
echo "===================================="
echo "Target Range: $TARGET_RANGE"
echo "Port: $PORT"
echo "Scan Rate: $SCAN_RATE pps"
echo "Threads: $THREADS"
echo "Output File: masscan_results_$(date +%Y%m%d_%H%M%S).txt"
echo "===================================="
echo ""
echo "WARNING: Only scan networks you own or have explicit permission to scan!"
echo "Unauthorized scanning may be illegal in your jurisdiction."
echo ""
read -p "Do you want to continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Scan cancelled."
    exit 1
fi

# Create output filename with timestamp
OUTPUT_FILE="masscan_results_$(date +%Y%m%d_%H%M%S).txt"

echo ""
echo "Starting masscan..."
echo "This may take some time depending on the target range size."
echo ""

# Run masscan with exclusions for private networks
masscan $TARGET_RANGE \
    -p $PORT \
    --rate $SCAN_RATE \
    -oG "$OUTPUT_FILE" \
    --exclude 255.255.255.255,127.0.0.0/8,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12,169.254.0.0/16,224.0.0.0/4,240.0.0.0/4

# Check if masscan completed successfully
if [ $? -eq 0 ]; then
    echo ""
    echo "===================================="
    echo "Masscan completed successfully!"
    echo "===================================="
    echo "Results saved to: $OUTPUT_FILE"
    
    # Count results
    RESULT_COUNT=$(grep -c "Host:" "$OUTPUT_FILE" 2>/dev/null || echo "0")
    echo "Found $RESULT_COUNT potential Ollama instances"
    echo ""
    
    # Ask if user wants to process results
    read -p "Do you want to process these results now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Processing results with ollama_scanner.py..."
        
        # Activate venv if it exists
        if [ -d "venv" ]; then
            source venv/bin/activate
        fi
        
        # Run scanner with masscan results
        python3 ollama_scanner.py \
            --method masscan \
            --input "$OUTPUT_FILE" \
            --threads $THREADS \
            --status scanned \
            --preserve-verified
            
        echo ""
        echo "Processing complete!"
        echo ""
        echo "To view results:"
        echo "  python query_models_fixed.py servers"
        echo "  python query_models_fixed.py models"
    else
        echo ""
        echo "To process the results later, run:"
        echo "  python3 ollama_scanner.py --method masscan --input $OUTPUT_FILE --threads $THREADS"
    fi
else
    echo ""
    echo "===================================="
    echo "Masscan failed!"
    echo "===================================="
    echo "Check the error messages above for details."
    exit 1
fi

