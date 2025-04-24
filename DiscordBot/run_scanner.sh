#!/bin/bash
# Ollama Scanner Runner Script
# This script runs the Ollama scanner to find Ollama instances

echo "==========================================="
echo "   OLLAMA SCANNER"
echo "==========================================="
echo "Workspace: $(pwd)"

# Load environment variables
if [ -f ".env" ]; then
    echo "Loading environment from .env file"
    export $(grep -v '^#' .env | xargs)
else
    echo "No .env file found, using default environment"
fi

echo "Database Type: ${DATABASE_TYPE:-PostgreSQL}"

# Activate virtual environment if it exists
if [ -d "../venv" ]; then
    echo "Activating virtual environment..."
    source ../venv/bin/activate
fi

# Check Python version and dependencies
echo "Checking Python version and dependencies..."
python_version=$(python --version)
echo "$python_version"

# Run the scanner
echo ""
echo "Command to execute:"
echo "python ./ollama_scanner.py" 
echo ""

echo "Starting scanner (press Ctrl+C to stop)..."
echo "----------------------------------------"
python ./ollama_scanner.py "$@"

# If we get here, the scanner completed successfully
exit_code=$?

echo ""
echo "==========================================="
if [ $exit_code -eq 0 ]; then
    echo "Scanner completed successfully."
else
    echo "Scanner exited with code $exit_code"
fi
echo "===========================================" 