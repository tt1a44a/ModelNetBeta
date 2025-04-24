# Ollama Scanner and Benchmark Tool

A collection of tools for discovering, analyzing, and benchmarking exposed Ollama API servers.

## Features

- **Server Discovery**: Scan for publicly exposed Ollama API servers using Shodan
- **Model Indexing**: Catalog available models and their metadata
- **Duplicate Prevention**: Avoid adding duplicate servers or models to the database
- **Continuous Scanning**: Keep your database up to date with automatic periodic scanning
- **Database Pruning**: Clean up duplicate entries from the database
- **Comprehensive Queries**: Search models by name, parameter size, and other attributes
- **Performance Benchmarking**: Test and compare model performance across servers

## Requirements

- Python 3.6+
- Required packages:
  - requests
  - sqlite3 (usually included with Python)
  - argparse (usually included with Python)
  - concurrent.futures (usually included with Python)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/YourUsername/Ollama_Scanner.git
   cd Ollama_Scanner
   ```

2. Install required packages:
   ```
   pip install requests
   ```

## Usage

### Scanner Tool

The main scanner tool discovers Ollama model servers and indexes their models:

```
python3 ollama_scanner.py [OPTIONS]
```

#### Options:

- `--method METHOD`: Scanning method (choices: masscan, shodan, censys, all, iplist; default: masscan)
- `--input FILE`: Input file with existing masscan or IP list results
- `--network RANGE`: Network range to scan (default: 0.0.0.0/0)
- `--port PORT`: Port to scan (default: 11434)
- `--rate RATE`: Masscan rate in packets per second (default: 10000)
- `--threads THREADS`: Number of threads for verification (default: 5)
- `--timeout SECONDS`: Connection timeout in seconds (default: 10)
- `--status STATUS`: Status to assign to verified instances (default: 'scanned')
- `--preserve-verified`: Preserve existing verified instances in database (default: True)
- `--no-preserve-verified`: Do not preserve existing verified instances
- `--limit LIMIT`: Limit the number of IPs to process (default: 0 = no limit)
- `--pages PAGES`: Number of pages to fetch from Censys (default: 1)
- `--verbose`, `-v`: Enable verbose output
- `--continuous`: Run in continuous scanning mode to keep discovering new servers
- `--interval SECONDS`: Set the interval between scans in continuous mode (default: 3600 seconds)
- `--prune`: Remove duplicate entries from the database

### Automated Scanner Script

For convenience, you can use the provided shell script which handles database connections and parameter passing:

```
./run_scanner.sh [OPTIONS]
```

#### Options:

- `--status VALUE`: Status to assign to verified instances (default: 'scanned')
- `--preserve-verified`: Preserve existing verified instances in database (default)
- `--no-preserve-verified`: Do not preserve existing verified instances
- `--limit VALUE`: Limit the number of IPs to process (0 = no limit)
- `--network VALUE`: Network range to scan (default: 0.0.0.0/0)
- `--threads VALUE`: Number of threads for verification (default: 5)
- `--timeout VALUE`: Connection timeout in seconds (default: 10)
- `--verbose`: Enable verbose output
- `--help`: Display usage information

#### Example:

```
./run_scanner.sh --status verified --limit 1000 --network 192.168.1.0/24 --threads 10 --verbose
```

### Query Tool

Query the database of discovered Ollama servers and models:

```
python3 query_models.py COMMAND [OPTIONS]
```

#### Commands:

- `servers`: List all servers in the database
- `models`: List all unique models
- `models-servers`: List all models with their server IPs
- `search MODEL_NAME`: Search for models by name
- `params PARAMETER_SIZE`: Find models with specific parameter size (e.g., "7B", "13B")
- `server IP [--port PORT]`: Show details of a specific server
- `prune`: Remove duplicate entries from the database

#### Sorting Options:

- `--sort FIELD`: Sort results by specified field
  - For servers: `ip`, `date`, `models`
  - For models: `name`, `params`, `quant`, `count`, `size`
- `--desc`: Sort in descending order

### Benchmark Tool

Benchmark the performance of models across different servers:

```
python3 ollama_benchmark_db.py COMMAND [OPTIONS]
```

#### Commands:

- `run`: Run benchmarks on model/server pairs in the database
  - `--model MODEL_NAME`: Filter models to benchmark by name
  - `--count NUMBER`: Limit number of model/server pairs to benchmark
  - `--server IP`: Test a specific server IP
  - `--port PORT`: Specify server port (default: 11434)
  - `--model-name NAME`: Specify model name to test
- `query`: View benchmark results from the database
  - `--model MODEL_NAME`: Filter results by model name
  - `--limit NUMBER`: Maximum number of results to show (default: 10)

#### Benchmark Metrics:

The benchmark collects the following metrics:
- **Basic Response Time**: Average time to generate a short response
- **Tokens Per Second**: Generation throughput rate
- **First Token Latency**: Time to receive the first token (responsiveness)
- **Context Handling**: Performance with different context sizes (500, 1000, 2000 words)
- **Concurrency**: How well the server handles multiple simultaneous requests
- **Success Rate**: Reliability of the server/model combination

### UPDATED BENCHMARKING TUTORIAL!!

if ur getting errors about missing columns u need to run update_schema.py first!!!! this adds the missing columns to fix errors like ERROR: table benchmark_results has no column named throughput_tokens!!!

commands:

```
# FIX DB SCHEMA FIRST!!!!!
python3 update_schema.py

# run benchmark on ALL codellama models (this will take a long time!!!)
python3 ollama_benchmark_db.py run --model codellama

# u can set limit to not test all servers
python3 ollama_benchmark_db.py run --model llama --count 5  # only test 5 servers

# benchmark specific model on specific server (FAST!!)
python3 ollama_benchmark_db.py run --server 13.124.24.76 --port 9094 --model-name codellama:13b

# check results
python3 ollama_benchmark_db.py query --model codellama:13b
```

COMMON ERRORS:
- "not enough values to unpack (expected 8, got 7)" - update ur database schema!!!
- "ERROR: table benchmark_results has no column named throughput_tokens" - RUN update_schema.py!!
- "type object 'datetime.datetime' has no attribute 'datetime'" - FIXED in latest version

if u want 2 get BEST results try running the query command to see which r fastest:
```
python3 ollama_benchmark_db.py query --model llama
```

note: some servers may take LONG TIME to respond or fail completely.. this is NORMAL!!!!

## Database Structure

The database (ollama_instances.db) contains the following tables:

### Servers Table
- `id`: Unique identifier
- `ip`: Server IP address
- `port`: Server port
- `scan_date`: When the server was discovered/scanned

### Models Table
- `id`: Unique identifier
- `server_id`: Reference to server table
- `name`: Model name
- `parameter_size`: Size of the model (e.g., "7B", "13B")
- `quantization_level`: Quantization used (e.g., "Q4_K_M")
- `size_mb`: Size in megabytes

### Benchmark Results Table
- `id`: Unique identifier
- `server_id`: Reference to server table
- `model_id`: Reference to model table
- `test_date`: When the benchmark was run
- `avg_response_time`: Average response time for simple generation
- `tokens_per_second`: Average tokens per second
- `first_token_latency`: Time to receive first token
- Various other performance metrics

## How Duplicate Prevention Works

The scanner checks if a server already exists in the database before adding it. If a server is found with the same IP and port, it will update the existing entry rather than creating a duplicate.

Similarly, when adding models, the scanner checks if the model already exists for a particular server.

## Continuous Scanning Mode

When run with the `--continuous` flag, the scanner will:
1. Perform an initial scan
2. Wait for the specified interval (default: 1 hour)
3. Scan again for new servers
4. Automatically prune duplicates
5. Repeat indefinitely

This keeps your database up-to-date with minimal manual intervention.

## Benchmarking Process

The benchmarking tool:
1. Queries the database for model/server combinations
2. Runs a series of tests on each combination:
   - Simple generation test
   - Throughput test with longer content
   - Context handling with different sizes
   - First token latency measurement
   - Concurrent request handling
3. Saves results to the database for comparison
4. Provides a summary of top performers

## Security Considerations

This tool is intended for research and educational purposes only. Always respect server owners' privacy and terms of service. Do not use this tool to access or utilize models in ways that violate terms of service or applicable laws.

## License

This project is released under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 