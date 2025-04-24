#!/bin/bash

# Show banner
echo "===================================="  
echo "     Starting Ollama Scanner!       "
echo "===================================="

# Run the scanner
source venv/bin/activate
python ollama_scanner.py

# Show query options
echo ""
echo "To search the database, try:"
echo "  ./query_models.py servers   - List all servers"
echo "  ./query_models.py models    - List all models"
echo "  ./query_models.py search llama - Search for models with name 'llama'"
echo "  ./query_models.py --help    - See all options"
echo ""

# Wait for user input when done
echo "Scan is finished! Press Enter to close..."
read 