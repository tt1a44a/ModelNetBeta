#!/usr/bin/env python3

import requests
import time
import json
import sys
import random
import argparse
import sqlite3
import os
from datetime import datetime
import concurrent.futures
import string
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

# Database configuration
if DATABASE_TYPE == "sqlite":
    DB_FILE = os.getenv("SQLITE_DB_PATH", "ollama_instances.db")
else:
    # For PostgreSQL, we don't need a DB_FILE
    DB_FILE = None

# Base prompt for simple testing
TEST_PROMPT = "Explain quantum computing in 50 words"

# Longer prompt for throughput testing
LONG_PROMPT = "Write a detailed essay about artificial intelligence, its history, current applications, and future potential. Include examples and discuss ethical considerations."

# Context testing prompt template
CONTEXT_TEMPLATE = """
Here is a document:
{}
Summarize the above document in 3 sentences.
"""

# How many times to run each test
REPEAT_TESTS = 3

# Timeout in seconds
TIMEOUT = 25  # Increased for longer tests

# Concurrency test settings
CONCURRENCY_TEST_COUNT = 5  # Number of concurrent requests to test
REQUEST_TIMEOUT = 20  # Timeout for concurrent request tests

# Delay between tests to avoid server overload
TEST_DELAY = 10  # Wait 10 seconds between tests

# Max retries when server is busy
MAX_RETRIES = 3

# Server list
servers = [
    "116.14.227.16:5271"  # This server works with qwen2.5:14b
]

# Model name to use
MODEL = "qwen2.5:14b"  # This model is available and responds

# Generate text of different lengths for context testing
def get_context_text(size):
    # Lorem ipsum style text generation
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
             "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
             "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", "exercitation",
             "ullamco", "laboris", "nisi", "ut", "aliquip", "ex", "ea", "commodo", "consequat",
             "duis", "aute", "irure", "dolor", "in", "reprehenderit", "in", "voluptate", "velit",
             "esse", "cillum", "dolore", "eu", "fugiat", "nulla", "pariatur", "excepteur", "sint",
             "occaecat", "cupidatat", "non", "proident", "sunt", "in", "culpa", "qui", "officia",
             "deserunt", "mollit", "anim", "id", "est", "laborum"]
    
    result = []
    sentences = size // 10  # approximate number of sentences
    
    for i in range(sentences):
        sentence_length = random.randint(5, 15)
        sentence = [random.choice(words) for _ in range(sentence_length)]
        sentence[0] = sentence[0].capitalize()
        result.append(" ".join(sentence) + ".")
    
    return " ".join(result)

def test_simple_generation(server_address, model_name):
    print("  Running basic generation test...")
    
    url = "http://" + server_address + "/api/generate"
    
    # Test data
    data = {
        "model": model_name,
        "prompt": TEST_PROMPT,
        "stream": False
    }
    
    # Results storage
    times = []
    token_counts = []
    errors = 0
    
    # Run multiple tests
    for i in range(REPEAT_TESTS):
        retry_count = 0
        success = False
        
        while retry_count < MAX_RETRIES and not success:
            try:
                if retry_count > 0:
                    print(f"    Retry {retry_count}/{MAX_RETRIES} for test {i+1}/{REPEAT_TESTS}...")
                    # Exponential backoff
                    backoff_time = TEST_DELAY * (2 ** retry_count)
                    print(f"    Waiting {backoff_time} seconds before retry...")
                    time.sleep(backoff_time)
                else:
                    print(f"    Basic test {i+1}/{REPEAT_TESTS}...")
                
                # Record start time
                start_time = time.time()
                
                # Make the request
                response = requests.post(url, json=data, timeout=TIMEOUT)
                
                # Calculate time
                end_time = time.time()
                elapsed = end_time - start_time
                
                # If successful, process the response
                if response.status_code == 200:
                    try:
                        result = response.json()
                        response_text = result.get("response", "")
                        
                        # Count tokens (very rough estimate - just words)
                        token_count = len(response_text.split())
                        
                        # Store results
                        times.append(elapsed)
                        token_counts.append(token_count)
                        
                        print(f"      Success - {round(elapsed, 2)} seconds, ~{token_count} tokens")
                        success = True
                    except Exception as e:
                        print(f"      Error parsing response: {str(e)}")
                        errors += 1
                else:
                    print(f"      Failed with status code: {response.status_code}")
                    print(f"      Response: {response.text[:100]}")
                    
                    # If server is busy, retry
                    if "server busy" in response.text and retry_count < MAX_RETRIES-1:
                        retry_count += 1
                        continue
                    else:
                        errors += 1
                        break
                    
            except requests.RequestException as e:
                print(f"      Connection error: {str(e)}")
                errors += 1
                break
        
        # Sleep a bit between tests
        if i < REPEAT_TESTS - 1:  # Don't sleep after the last test
            print(f"    Waiting {TEST_DELAY} seconds before next test...")
            time.sleep(TEST_DELAY)
    
    # Calculate average if we have any successful tests
    if len(times) > 0:
        avg_time = sum(times) / len(times)
        avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 0
        tokens_per_sec = sum(token_counts) / sum(times) if sum(times) > 0 else 0
        
        return {
            "simple_avg_time": avg_time,
            "simple_avg_tokens": avg_tokens,
            "simple_tokens_per_sec": tokens_per_sec,
            "simple_success_rate": (REPEAT_TESTS - errors) / REPEAT_TESTS,
            "simple_errors": errors
        }
    else:
        # All tests failed
        return {
            "simple_avg_time": float('inf'),
            "simple_avg_tokens": 0,
            "simple_tokens_per_sec": 0,
            "simple_success_rate": 0,
            "simple_errors": errors
        }

def test_throughput(server_address, model_name):
    print("  Running throughput test...")
    
    url = "http://" + server_address + "/api/generate"
    
    # Test data for throughput (longer generation)
    data = {
        "model": model_name,
        "prompt": LONG_PROMPT,
        "stream": False
    }
    
    try:
        print("    Generating long text...")
        
        # Record start time
        start_time = time.time()
        
        # Make the request
        response = requests.post(url, json=data, timeout=TIMEOUT)
        
        # Calculate time
        end_time = time.time()
        elapsed = end_time - start_time
        
        # If successful, process the response
        if response.status_code == 200:
            try:
                result = response.json()
                response_text = result.get("response", "")
                
                # Count tokens (very rough estimate - just words)
                token_count = len(response_text.split())
                
                # Calculate throughput
                tokens_per_sec = token_count / elapsed
                
                print("      Success - " + str(round(elapsed, 2)) + " seconds, ~" + 
                      str(token_count) + " tokens (" + str(round(tokens_per_sec, 1)) + " tokens/sec)")
                
                return {
                    "throughput_time": elapsed,
                    "throughput_tokens": token_count,
                    "throughput_tokens_per_sec": tokens_per_sec,
                    "throughput_success": True
                }
            except Exception as e:
                print("      Error parsing response: " + str(e))
        else:
            print("      Failed with status code: " + str(response.status_code))
            print("      Response: " + response.text[:100])  # Print first 100 chars of error
                
    except requests.RequestException as e:
        print("      Connection error: " + str(e))
    
    # Return failure data
    return {
        "throughput_time": 0,
        "throughput_tokens": 0,
        "throughput_tokens_per_sec": 0,
        "throughput_success": False
    }

def test_context_handling(server_address, model_name):
    print("  Running context handling test...")
    
    url = "http://" + server_address + "/api/generate"
    context_sizes = [500, 1000, 2000]  # Test with different context sizes
    results = {}
    
    for size in context_sizes:
        print("    Testing with " + str(size) + " word context...")
        
        # Generate context of specified size
        context = get_context_text(size)
        
        # Create prompt with context
        prompt = CONTEXT_TEMPLATE.format(context)
        
        # Test data
        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            # Record start time
            start_time = time.time()
            
            # Make the request
            response = requests.post(url, json=data, timeout=TIMEOUT)
            
            # Calculate time
            end_time = time.time()
            elapsed = end_time - start_time
            
            # If successful, process the response
            if response.status_code == 200:
                try:
                    result = response.json()
                    response_text = result.get("response", "")
                    
                    # Count tokens (very rough estimate - just words)
                    token_count = len(response_text.split())
                    
                    # Calculate throughput
                    tokens_per_sec = token_count / elapsed
                    
                    print("      Success - " + str(round(elapsed, 2)) + " seconds for " + 
                          str(size) + " context, ~" + str(token_count) + " response tokens")
                    
                    results[size] = {
                        "time": elapsed,
                        "response_tokens": token_count,
                        "tokens_per_sec": tokens_per_sec,
                        "success": True
                    }
                except Exception as e:
                    print("      Error parsing response: " + str(e))
                    results[size] = {"success": False}
            else:
                print("      Failed with status code: " + str(response.status_code))
                print("      Response: " + response.text[:100])  # Print first 100 chars of error
                results[size] = {"success": False}
                    
        except requests.RequestException as e:
            print("      Connection error: " + str(e))
            results[size] = {"success": False}
        
        # Sleep a bit between tests
        time.sleep(TEST_DELAY)
    
    return results

def test_first_token_latency(server_address, model_name):
    print("  Testing first token latency...")
    
    url = "http://" + server_address + "/api/generate"
    
    # Test data
    data = {
        "model": model_name,
        "prompt": TEST_PROMPT,
        "stream": True  # Use streaming to measure first token latency
    }
    
    latencies = []
    errors = 0
    
    for i in range(REPEAT_TESTS):
        try:
            print("    First token test " + str(i+1) + "/" + str(REPEAT_TESTS) + "...")
            
            # Record start time
            start_time = time.time()
            
            # Make streaming request
            response = requests.post(url, json=data, timeout=TIMEOUT, stream=True)
            
            if response.status_code == 200:
                # Read the first chunk to get first token latency
                first_chunk = False
                for chunk in response.iter_lines():
                    if chunk:
                        # Calculate time for first token
                        first_token_time = time.time() - start_time
                        latencies.append(first_token_time)
                        print("      First token received in " + str(round(first_token_time, 3)) + " seconds")
                        
                        # We only need the first chunk, so break after receiving it
                        break
            else:
                print("      Failed with status code: " + str(response.status_code))
                print("      Response: " + response.text[:100])  # Print first 100 chars of error
                errors += 1
                
        except requests.RequestException as e:
            print("      Connection error: " + str(e))
            errors += 1
        
        # Sleep a bit between tests
        time.sleep(TEST_DELAY)
    
    # Calculate average if we have any successful tests
    if len(latencies) > 0:
        avg_latency = sum(latencies) / len(latencies)
        return {
            "first_token_latency": avg_latency,
            "first_token_success_rate": (REPEAT_TESTS - errors) / REPEAT_TESTS
        }
    else:
        return {
            "first_token_latency": float('inf'),
            "first_token_success_rate": 0
        }

def test_concurrency(server_address, model_name):
    """Test how well the server handles concurrent requests."""
    print("  Testing concurrency handling...")
    
    results = {}
    num_concurrent = CONCURRENCY_TEST_COUNT  # Number of concurrent requests
    
    def make_request(session):
        url = f"http://{server_address}/api/generate"
        data = {
            "model": model_name,
            "prompt": TEST_PROMPT,
            "stream": False
        }
        try:
            response = session.post(url, json=data, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return True
            else:
                return False
        except Exception:
            return False
            
    # Use a connection pool with a session
    session = requests.Session()
    
    # Use ThreadPoolExecutor to run concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(make_request, session) for _ in range(num_concurrent)]
        results_list = [future.result() for future in futures]
    
    # Calculate success rate
    successful = [r for r in results_list if r]
    success_rate = len(successful) / num_concurrent if num_concurrent > 0 else 0
    
    print(f"    Concurrent request success rate: {int(success_rate * 100)}%")
    
    results["concurrency_success_rate"] = success_rate
    
    return results

def test_server(server_address, model_name=None):
    """Run comprehensive tests on a server and model"""
    # Use provided model name or default
    test_model = model_name if model_name else MODEL
    
    # Initialize results
    results = {
        "server": server_address,
        "model": test_model,
        "test_date": datetime.now().isoformat()
    }
    
    print("\n-------------------------------------------------")
    print(f"TESTING MODEL: {test_model}")
    print(f"SERVER: {server_address}")
    print("-------------------------------------------------")
    
    # 1. Simple generation test
    simple_results = test_simple_generation(server_address, test_model)
    results.update(simple_results)
    
    # If simple test failed, skip advanced tests
    if results.get("simple_success_rate", 0) == 0:
        print("  Basic tests failed. Skipping advanced tests.")
        return results
    
    # Wait before next test
    print(f"  Waiting {TEST_DELAY} seconds before next test...")
    time.sleep(TEST_DELAY)
    
    # 2. First token latency test
    try:
        latency_results = test_first_token_latency(server_address, test_model)
        results.update(latency_results)
    except Exception as e:
        print(f"  First token latency test error: {str(e)}")
        results["first_token_success_rate"] = 0
    
    # Wait before next test
    print(f"  Waiting {TEST_DELAY} seconds before next test...")
    time.sleep(TEST_DELAY)
    
    # 3. Throughput test (longer generation)
    try:
        throughput_results = test_throughput(server_address, test_model)
        results.update(throughput_results)
    except Exception as e:
        print(f"  Throughput test error: {str(e)}")
        results["throughput_success"] = False
    
    # Wait before next test
    print(f"  Waiting {TEST_DELAY} seconds before next test...")
    time.sleep(TEST_DELAY)
    
    # 4. Context handling test
    try:
        context_results = test_context_handling(server_address, test_model)
        results["context_handling"] = context_results
    except Exception as e:
        print(f"  Context handling test error: {str(e)}")
        results["context_handling"] = {}
    
    # 5. Concurrency test
    try:
        concurrency_results = test_concurrency(server_address, test_model)
        results.update(concurrency_results)
    except Exception as e:
        print(f"  Concurrency test error: {str(e)}")
        results["concurrency_success_rate"] = 0
    
    return results

# Database functions
def setup_benchmark_database():
    """Initialize the database and create benchmark tables if they don't exist"""
    # For SQLite, check if database file exists
    if DATABASE_TYPE == "sqlite" and DB_FILE is not None:
        if not os.path.exists(DB_FILE):
            print(f"ERROR: Database file {DB_FILE} not found!")
            print("Run ollama_scanner.py first to collect data.")
            return False
    
    # Initialize database connection
    init_database()
    
    # Check if the servers table exists
    if DATABASE_TYPE == "sqlite":
        query = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='servers'"
    else:
        # PostgreSQL
        query = """
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'servers'
        """
    
    if Database.fetch_one(query)[0] == 0:
        print("ERROR: Database does not contain the required tables.")
        print("Run ollama_scanner.py first to collect data.")
        return False
    
    # Create benchmark_results table if it doesn't exist
    if DATABASE_TYPE == "sqlite":
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            model_id INTEGER,
            test_date TEXT NOT NULL,
            avg_response_time REAL,
            tokens_per_second REAL,
            first_token_latency REAL,
            throughput_tokens REAL,
            throughput_time REAL,
            context_500_tps REAL,
            context_1000_tps REAL,
            context_2000_tps REAL,
            max_concurrent_requests INTEGER,
            concurrency_success_rate REAL,
            concurrency_avg_time REAL,
            success_rate REAL,
            FOREIGN KEY (server_id) REFERENCES servers(id),
            FOREIGN KEY (model_id) REFERENCES models(id)
        )
        '''
    else:
        # PostgreSQL
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id SERIAL PRIMARY KEY,
            server_id INTEGER,
            model_id INTEGER,
            test_date TIMESTAMP NOT NULL,
            avg_response_time REAL,
            tokens_per_second REAL,
            first_token_latency REAL,
            throughput_tokens REAL,
            throughput_time REAL,
            context_500_tps REAL,
            context_1000_tps REAL,
            context_2000_tps REAL,
            max_concurrent_requests INTEGER,
            concurrency_success_rate REAL,
            concurrency_avg_time REAL,
            success_rate REAL,
            FOREIGN KEY (server_id) REFERENCES servers(id),
            FOREIGN KEY (model_id) REFERENCES models(id)
        )
        '''
    
    Database.execute(create_table_query)
    return True

def get_model_server_pairs(model_filter=None, server_filter=None, limit=None):
    """Get model/server pairs from the database"""
    # Initialize database connection
    conn = Database()
    
    # Build query to get model/server pairs
    query = """
    SELECT 
        m.id as model_id, 
        s.id as server_id,
        m.name as model_name, 
        m.parameter_size, 
        m.quantization_level,
        m.size_mb,
        s.ip, 
        s.port
    FROM models m
    JOIN servers s ON m.server_id = s.id
    """
    
    # Check the database schema to confirm column names
    if DATABASE_TYPE == "postgres":
        # For PostgreSQL, check the actual column names
        schema_query = """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'models' AND column_name = 'server_id'
        """
        server_id_column = Database.fetch_one(schema_query)
        
        if not server_id_column:
            # If server_id not found, try endpoint_id which might be used instead
            schema_query = """
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'models' AND column_name = 'endpoint_id'
            """
            endpoint_id_column = Database.fetch_one(schema_query)
            
            if endpoint_id_column:
                # Use endpoint_id instead of server_id
                query = """
                SELECT 
                    m.id as model_id, 
                    e.id as server_id,
                    m.name as model_name, 
                    m.parameter_size, 
                    m.quantization_level,
                    m.size_mb,
                    e.ip, 
                    e.port
                FROM models m
                JOIN endpoints e ON m.endpoint_id = e.id
                """
    
    params = []
    
    # Add model filter if specified
    if model_filter:
        query += " WHERE m.name LIKE ?"
        params.append(f"%{model_filter}%")
    
    # Add server filter if specified
    if server_filter:
        if model_filter:
            query += " AND "
        else:
            query += " WHERE "
        
        # Check if we're using endpoints table
        if "endpoints e" in query:
            query += "e.ip = ?"
        else:
            query += "s.ip = ?"
        
        params.append(server_filter)
    
    # Order by model name and server
    query += " ORDER BY m.name"
    
    if "endpoints e" in query:
        query += ", e.ip, e.port"
    else:
        query += ", s.ip, s.port"
    
    # Add limit if specified
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    # Execute query and fetch all model/server pairs
    pairs = Database.fetch_all(query, params)
    
    return pairs

def save_benchmark_results(results):
    """Save benchmark results to the database"""
    # Initialize database connection
    conn = Database()
    
    # Extract values from the results
    server_id = results.get("server_id")
    model_id = results.get("model_id")
    test_date = results.get("test_date")
    avg_response_time = results.get("simple_avg_time", float('inf'))
    tokens_per_second = results.get("simple_tokens_per_sec", 0)
    first_token_latency = results.get("first_token_latency", float('inf'))
    throughput_tokens = results.get("throughput_tokens", 0)
    throughput_time = results.get("throughput_time", 0)
    success_rate = results.get("simple_success_rate", 0)
    
    # Extract context handling times
    context_handling = results.get("context_handling", {})
    context_500_tps = context_handling.get(500, {}).get("tokens_per_sec", 0) if 500 in context_handling else 0
    context_1000_tps = context_handling.get(1000, {}).get("tokens_per_sec", 0) if 1000 in context_handling else 0
    context_2000_tps = context_handling.get(2000, {}).get("tokens_per_sec", 0) if 2000 in context_handling else 0
    
    # Extract concurrency results
    concurrency_success_rate = results.get("concurrency_success_rate", 0)
    concurrency_avg_time = results.get("concurrency_avg_time", float('inf'))
    
    # Insert the benchmark results
    Database.execute('''
    INSERT INTO benchmark_results (
        server_id, model_id, test_date, avg_response_time, tokens_per_second,
        first_token_latency, throughput_tokens, throughput_time,
        context_500_tps, context_1000_tps, context_2000_tps,
        concurrency_success_rate, concurrency_avg_time, success_rate
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        server_id, model_id, test_date, avg_response_time, tokens_per_second,
        first_token_latency, throughput_tokens, throughput_time,
        context_500_tps, context_1000_tps, context_2000_tps,
        concurrency_success_rate, concurrency_avg_time, success_rate
    ))
    
    print(f"Benchmark results saved to database for {results['model']} on {results['server']}")

def format_benchmark_results(results):
    """Format benchmark results for display"""
    output = [
        f"MODEL: {results['model']}",
        f"SERVER: {results['server']}",
        f"TEST DATE: {results['test_date']}",
        ""
    ]
    
    # Add basic results
    if results["simple_success_rate"] > 0:
        output.extend([
            "BASIC SPEED TEST:",
            f"  Average response time: {round(results['simple_avg_time'], 2)} seconds",
            f"  Tokens per second: {round(results['simple_tokens_per_sec'], 1)}",
            f"  Success rate: {int(results['simple_success_rate'] * 100)}%",
            ""
        ])
    else:
        output.extend([
            "BASIC SPEED TEST: Failed",
            ""
        ])
    
    # Add throughput results if available
    if results.get("throughput_success", False):
        output.extend([
            "THROUGHPUT TEST:",
            f"  Tokens generated: {results['throughput_tokens']}",
            f"  Generation time: {round(results['throughput_time'], 2)} seconds",
            f"  Tokens per second: {round(results['throughput_tokens_per_sec'], 1)}",
            ""
        ])
    
    # Add first token latency if available
    if "first_token_latency" in results and results["first_token_latency"] < float('inf'):
        output.extend([
            "FIRST TOKEN LATENCY:",
            f"  Average latency: {round(results['first_token_latency'], 3)} seconds",
            f"  Success rate: {int(results['first_token_success_rate'] * 100)}%",
            ""
        ])
    
    # Add context handling results if available
    if "context_handling" in results:
        output.append("CONTEXT HANDLING:")
        for size in [500, 1000, 2000]:
            if size in results["context_handling"] and results["context_handling"][size]["success"]:
                output.append(f"  {size} words: {round(results['context_handling'][size]['time'], 2)} seconds")
            else:
                output.append(f"  {size} words: Failed")
        output.append("")
    
    # Add concurrency results if available
    if "concurrency_success_rate" in results:
        output.extend([
            "CONCURRENCY TEST:",
            f"  Success rate: {int(results['concurrency_success_rate'] * 100)}%",
            f"  Average response time: {round(results.get('concurrency_avg_time', float('inf')), 2)} seconds",
            ""
        ])
    
    return "\n".join(output)

# New run_benchmarks function - for database integration
def run_benchmarks(model_filter=None, max_count=None, server_ip=None, server_port=None, model_name=None):
    """Run benchmarks on model/server pairs"""
    # Initialize the database
    if not setup_benchmark_database():
        return
    
    # If specific server/model provided, benchmark just that
    if server_ip and model_name:
        port = int(server_port) if server_port else 11434
        server_address = f"{server_ip}:{port}"
        print(f"Running benchmark for model {model_name} on server {server_address}")
        
        results = test_server(server_address, model_name)
        
        # Print results
        print("\n=================================================")
        print("  BENCHMARK RESULTS")
        print("=================================================")
        print(format_benchmark_results(results))
        
        return
    
    # Otherwise, get model/server pairs from database
    pairs = get_model_server_pairs(model_filter, server_ip, max_count)
    
    if not pairs:
        print("No model/server pairs found in the database.")
        if model_filter:
            print(f"No models match the filter: {model_filter}")
        return
    
    print(f"Found {len(pairs)} model/server pairs to benchmark")
    
    # Run benchmarks for each pair
    all_results = []
    
    for pair in pairs:
        try:
            model_id, server_id, model_name, param_size, quant_level, size_mb, ip, port = pair
        except ValueError:
            # If size_mb is not in the query results, try this alternative unpacking
            model_id, model_name, param_size, quant_level, server_id, ip, port = pair
            size_mb = 0  # Default value if not available
        
        # Run benchmark
        server_address = f"{ip}:{port}"
        results = test_server(server_address, model_name)
        
        # Add IDs for database saving
        results["server_id"] = server_id
        results["model_id"] = model_id
        
        all_results.append(results)
        
        # Save results to database
        if results["simple_success_rate"] > 0:
            save_benchmark_results(results)
        
        # Print results
        print("\n=================================================")
        print("  BENCHMARK RESULTS")
        print("=================================================")
        print(format_benchmark_results(results))
        
        # Wait a bit before next benchmark
        if pair != pairs[-1]:
            print(f"Waiting {TEST_DELAY} seconds before next benchmark...")
            time.sleep(TEST_DELAY)
    
    # Print summary
    print("\n=================================================")
    print("  BENCHMARK SUMMARY")
    print("=================================================")
    print(f"Total benchmarks run: {len(all_results)}")
    print(f"Successful benchmarks: {sum(1 for r in all_results if r['simple_success_rate'] > 0)}")
    print(f"Failed benchmarks: {sum(1 for r in all_results if r['simple_success_rate'] == 0)}")
    
    # Get top performers in different categories
    successful = [r for r in all_results if r["simple_success_rate"] > 0]
    
    if successful:
        # Sort by speed
        by_speed = sorted(successful, key=lambda x: x.get("simple_tokens_per_sec", 0), reverse=True)
        if by_speed:
            fastest = by_speed[0]
            print(f"\nFastest model/server: {fastest['model']} on {fastest['server']}")
            print(f"  Tokens per second: {round(fastest['simple_tokens_per_sec'], 1)}")
        
        # Sort by latency
        by_latency = sorted(
            [r for r in successful if "first_token_latency" in r and r["first_token_latency"] < float('inf')],
            key=lambda x: x["first_token_latency"]
        )
        if by_latency:
            lowest_latency = by_latency[0]
            print(f"\nLowest latency model/server: {lowest_latency['model']} on {lowest_latency['server']}")
            print(f"  First token latency: {round(lowest_latency['first_token_latency'], 3)} seconds")
        
        # Sort by throughput
        by_throughput = sorted(
            [r for r in successful if r.get("throughput_success", False)],
            key=lambda x: x["throughput_tokens_per_sec"],
            reverse=True
        )
        if by_throughput:
            highest_throughput = by_throughput[0]
            print(f"\nHighest throughput model/server: {highest_throughput['model']} on {highest_throughput['server']}")
            print(f"  Throughput: {round(highest_throughput['throughput_tokens_per_sec'], 1)} tokens/sec")

def query_benchmark_results(model_filter=None, limit=10):
    """Query and display benchmark results from the database"""
    # For SQLite, check if database file exists
    if DATABASE_TYPE == "sqlite" and DB_FILE is not None:
        if not os.path.exists(DB_FILE):
            print(f"ERROR: Database file {DB_FILE} not found!")
            return
    
    # Initialize database connection
    init_database()
    
    # Check if benchmark_results table exists
    if DATABASE_TYPE == "sqlite":
        query = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='benchmark_results'"
    else:
        # PostgreSQL
        query = """
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'benchmark_results'
        """
        
    if Database.fetch_one(query)[0] == 0:
        print("No benchmark results found in the database.")
        return
    
    # Build query
    query = """
    SELECT 
        br.test_date,
        m.name as model_name,
        s.ip,
        s.port,
        br.avg_response_time,
        br.tokens_per_second,
        br.first_token_latency
    FROM benchmark_results br
    JOIN servers s ON br.server_id = s.id
    JOIN models m ON br.model_id = m.id
    """
    
    params = []
    
    # Add model filter if specified
    if model_filter:
        query += " WHERE m.name LIKE ?"
        params.append(f"%{model_filter}%")
    
    # Order by test date (newest first)
    query += " ORDER BY br.test_date DESC"
    
    # Add limit
    query += " LIMIT ?"
    params.append(limit)
    
    # Execute query and fetch results
    results = Database.fetch_all(query, params)
    
    # Display results
    if not results:
        print("No benchmark results found.")
        if model_filter:
            print(f"No results match the filter: {model_filter}")
        return
    
    print("\n=================================================")
    print("  BENCHMARK RESULTS HISTORY")
    print("=================================================")
    print(f"Model Filter: {model_filter if model_filter else 'All'}")
    print(f"Showing {len(results)} most recent results")
    print("\nDate                 | Model                 | Server            | Avg Time | Tokens/s | Latency")
    print("-" * 100)
    
    for result in results:
        test_date, model_name, ip, port, avg_time, tokens_per_sec, latency = result
        
        # Format model name (truncate if too long)
        if len(model_name) > 20:
            model_name = model_name[:17] + "..."
        
        # Format server
        server = f"{ip}:{port}"
        if len(server) > 18:
            server = server[:15] + "..."
        
        # Format metrics
        avg_time_str = f"{round(avg_time, 2)}" if avg_time < float('inf') else "N/A"
        tokens_per_sec_str = f"{round(tokens_per_sec, 1)}" if tokens_per_sec > 0 else "N/A"
        latency_str = f"{round(latency, 3)}" if latency < float('inf') else "N/A"
        
        print(f"{test_date} | {model_name.ljust(20)} | {server.ljust(18)} | {avg_time_str.ljust(8)} | {tokens_per_sec_str.ljust(8)} | {latency_str}")

# Main entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Benchmark Tool")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Original mode (no args) - for backward compatibility
    
    # Run benchmarks command
    run_parser = subparsers.add_parser("run", help="Run benchmarks on model/server pairs")
    run_parser.add_argument("--model", help="Filter models by name (e.g., 'llama' for all llama models)")
    run_parser.add_argument("--count", type=int, help="Maximum number of model/server pairs to benchmark")
    run_parser.add_argument("--server", help="Specific server IP to benchmark")
    run_parser.add_argument("--port", type=int, help="Specific server port to benchmark")
    run_parser.add_argument("--model-name", help="Specific model name to test")
    
    # Query results command
    query_parser = subparsers.add_parser("query", help="Query benchmark results from the database")
    query_parser.add_argument("--model", help="Filter results by model name")
    query_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to show")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check command and run appropriate function
    if args.command == "run":
        run_benchmarks(args.model, args.count, args.server, args.port, args.model_name)
    elif args.command == "query":
        query_benchmark_results(args.model, args.limit)
    else:
        # Original mode - for backward compatibility
        run_benchmark() 