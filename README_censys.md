# Censys Ollama Scanner

A tool to find exposed Ollama instances on the internet using the Censys API.

## Overview

This script uses the Censys API to search for Ollama instances by looking for the "ollama is running" text in HTTP responses. It then enumerates the port the Ollama instance is running on and checks if it's accessible.

## Features

- Search for Ollama instances using Censys API
- Detect the port Ollama is running on
- Verify if the instance is accessible
- Retrieve available models from each instance
- Save results to a SQLite database
- Multi-threaded scanning for faster results

## Requirements

- Python 3.6+
- Censys API credentials (API ID and Secret)
- Required Python packages:
  - requests
  - censys
  - python-dotenv

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/Ollama_Scanner.git
   cd Ollama_Scanner
   ```

2. Install the required packages:
   ```
   pip install requests censys python-dotenv
   ```

3. Create a `.env` file in the project directory with your Censys API credentials:
   ```
   CENSYS_API_ID=your_api_id
   CENSYS_API_SECRET=your_api_secret
   ```

## Usage

Run the script with default settings:

```
python censys_ollama_scanner.py
```

### Command Line Options

- `--threads`: Number of threads to use for scanning (default: 10)
- `--timeout`: Request timeout in seconds (default: 5)
- `--max-results`: Maximum number of results to process (default: 1000)

Example with custom options:

```
python censys_ollama_scanner.py --threads 20 --timeout 10 --max-results 2000
```

## How It Works

1. The script searches Censys for potential Ollama instances using multiple queries:
   - `services.http.response.body: "ollama is running"`
   - `services.http.response.body: ollama`
   - `services.port: 11434`
   - `services.http.response.body: /api/tags`
   - `services.http.response.body: models AND services.http.response.body: array`

2. For each potential instance, it:
   - Identifies the port Ollama is running on
   - Verifies if the instance is accessible
   - Retrieves the list of available models
   - Saves the results to a SQLite database

3. The script uses multi-threading to scan multiple instances in parallel.

## Database

The script saves results to a SQLite database named `ollama_instances.db` with two tables:

- `servers`: Contains information about each Ollama server
- `models`: Contains information about each model available on each server

## Security Note

This tool is intended for security research and educational purposes only. Do not use it to access systems you don't own or have permission to access.

## License

MIT 