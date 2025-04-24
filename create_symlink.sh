#!/bin/bash

# Create a symlink from ollama_benchmark_db.py to ollama_benchmark.py for backward compatibility
echo "Creating symlink for backward compatibility..."

# Remove any existing symlink or file
if [ -e "ollama_benchmark_db.py" ]; then
    echo "Removing existing ollama_benchmark_db.py..."
    rm -f "ollama_benchmark_db.py"
fi

# Create the symlink
ln -s "ollama_benchmark.py" "ollama_benchmark_db.py"

if [ $? -eq 0 ]; then
    echo "Symlink created successfully. You can now use either ollama_benchmark.py or ollama_benchmark_db.py."
    echo "Both will execute the same file."
else
    echo "Error creating symlink. Please check file permissions."
    exit 1
fi

# Make the script executable
chmod +x "ollama_benchmark.py"

echo "Done!" 