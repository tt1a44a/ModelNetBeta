#!/usr/bin/env python3
"""
Ollama Benchmark with Database Integration - test performance of models found in the scanner database
"""

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
from database import Database, init_database

# Database file
# TODO: Replace SQLite-specific code: DB_FILE = 'ollama_instances.db'

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
TIMEOUT = 25

# Delay between tests to avoid server overload
TEST_DELAY = 10

# Initialize database and create benchmark tables if needed
def init_database():
    """Initialize the database and create benchmark tables if they don't exist"""
    # Check if database exists
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file {DB_FILE} not found!")
        print("Run ollama_scanner.py first to collect data.")
        return False
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Check if the servers table exists
    Database.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='servers'")
    if Database.fetch_one(query, params)[0] == 0:
        print("ERROR: Database does not contain the required tables.")
        print("Run ollama_scanner.py first to collect data.")
        conn.close()
        return False
    
    # Create benchmark_results table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS benchmark_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER,
        model_id INTEGER,
        test_date TIMESTAMP,
        avg_response_time REAL,
        tokens_per_second REAL,
        first_token_latency REAL,
        context_500_tps REAL,
        context_1000_tps REAL,
        context_2000_tps REAL,
        max_concurrent_requests INTEGER,
        success_rate REAL,
        FOREIGN KEY (server_id) REFERENCES servers (id),
        FOREIGN KEY (model_id) REFERENCES models (id)
    )
    ''')
    
    # Commit handled by Database methods
    conn.close()
    return True

# Generate text of different lengths for context testing
def get_context_text(size):
    """Generate random text of specified size for context testing"""
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
             "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
             "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud", "exercitation",
             "ullamco", "laboris", "nisi", "ut", "aliquip", "ex", "ea", "commodo", "consequat"]
    
    result = []
    sentences = size // 10  # approximate number of sentences
    
    for i in range(sentences):
        sentence_length = random.randint(5, 15)
        sentence = [random.choice(words) for _ in range(sentence_length)]
        sentence[0] = sentence[0].capitalize()
        result.append(" ".join(sentence) + ".")
    
    return " ".join(result)

def test_simple_generation(server_address, model_name):
    """Run simple generation test on a server with a specific model"""
    print(f"  Running basic generation test for {model_name} on {server_address}...")
    
    url = f"http://{server_address}/api/generate"
    
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
        
        while retry_count < 3 and not success:
            try:
                if retry_count > 0:
                    print(f"    Retry {retry_count}/3 for test {i+1}/{REPEAT_TESTS}...")
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
                    if "server busy" in response.text and retry_count < 2:
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
    """Test throughput with longer text generation"""
    print(f"  Running throughput test for {model_name} on {server_address}...")
    
    url = f"http://{server_address}/api/generate"
    
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
        response = requests.post(url, json=data, timeout=TIMEOUT * 2)  # Double timeout for longer text
        
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
                
                print(f"      Success - {round(elapsed, 2)} seconds, ~{token_count} tokens ({round(tokens_per_sec, 1)} tokens/sec)")
                
                return {
                    "throughput_time": elapsed,
                    "throughput_tokens": token_count,
                    "throughput_tokens_per_sec": tokens_per_sec,
                    "throughput_success": True
                }
            except Exception as e:
                print(f"      Error parsing response: {str(e)}")
        else:
            print(f"      Failed with status code: {response.status_code}")
            print(f"      Response: {response.text[:100]}")
                
    except requests.RequestException as e:
        print(f"      Connection error: {str(e)}")
    
    # Return failure data
    return {
        "throughput_time": 0,
        "throughput_tokens": 0,
        "throughput_tokens_per_sec": 0,
        "throughput_success": False
    }

def test_context_handling(server_address, model_name):
    """Test how well the model handles different context sizes"""
    print(f"  Running context handling test for {model_name} on {server_address}...")
    
    url = f"http://{server_address}/api/generate"
    context_sizes = [500, 1000, 2000]  # Test with different context sizes
    results = {}
    
    for size in context_sizes:
        print(f"    Testing with {size} word context...")
        
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
            timeout_for_context = TIMEOUT * (size / 500)  # Scale timeout with context size
            response = requests.post(url, json=data, timeout=timeout_for_context)
            
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
                    
                    print(f"      Success - {round(elapsed, 2)} seconds for {size} context, ~{token_count} response tokens")
                    
                    results[size] = {
                        "time": elapsed,
                        "response_tokens": token_count,
                        "tokens_per_sec": tokens_per_sec,
                        "success": True
                    }
                except Exception as e:
                    print(f"      Error parsing response: {str(e)}")
                    results[size] = {"success": False}
            else:
                print(f"      Failed with status code: {response.status_code}")
                print(f"      Response: {response.text[:100]}")
                results[size] = {"success": False}
                    
        except requests.RequestException as e:
            print(f"      Connection error: {str(e)}")
            results[size] = {"success": False}
        
        # Sleep a bit between tests
        time.sleep(TEST_DELAY)
    
    return results

def test_first_token_latency(server_address, model_name):
    """Test first token latency using streaming"""
    print(f"  Testing first token latency for {model_name} on {server_address}...")
    
    url = f"http://{server_address}/api/generate"
    
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
            print(f"    First token test {i+1}/{REPEAT_TESTS}...")
            
            # Record start time
            start_time = time.time()
            
            # Make streaming request
            response = requests.post(url, json=data, timeout=TIMEOUT, stream=True)
            
            if response.status_code == 200:
                # Read the first chunk to get first token latency
                for chunk in response.iter_lines():
                    if chunk:
                        # Calculate time for first token
                        first_token_time = time.time() - start_time
                        latencies.append(first_token_time)
                        print(f"      First token received in {round(first_token_time, 3)} seconds")
                        
                        # We only need the first chunk, so break after receiving it
                        break
                
                # Close response
                response.close()
            else:
                print(f"      Failed with status code: {response.status_code}")
                print(f"      Response: {response.text[:100]}")
                errors += 1
                
        except requests.RequestException as e:
            print(f"      Connection error: {str(e)}")
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
    """Test how well the server handles concurrent requests"""
    print(f"  Testing concurrent requests for {model_name} on {server_address}...")
    
    url = f"http://{server_address}/api/generate"
    concurrent_requests = 3  # Number of concurrent requests to make
    
    # Simple request function for threads
    def make_request():
        try:
            data = {
                "model": model_name,
                "prompt": TEST_PROMPT,
                "stream": False
            }
            
            start_time = time.time()
            response = requests.post(url, json=data, timeout=TIMEOUT)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                token_count = len(response_text.split())
                return {
                    "success": True,
                    "time": elapsed,
                    "tokens": token_count
                }
            else:
                return {"success": False}
        except:
            return {"success": False}
    
    print(f"    Making {concurrent_requests} concurrent requests...")
    
    # Use ThreadPoolExecutor to run concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
        futures = [executor.submit(make_request) for _ in range(concurrent_requests)]
        results = [future.result() for future in futures]
    
    # Calculate success rate and averages
    successful = [r for r in results if r["success"]]
    success_rate = len(successful) / concurrent_requests if concurrent_requests > 0 else 0
    
    if successful:
        avg_time = sum(r["time"] for r in successful) / len(successful)
        print(f"    Concurrent request success rate: {int(success_rate * 100)}%")
        print(f"    Average response time: {round(avg_time, 2)} seconds")
        return {
            "concurrency_success_rate": success_rate,
            "concurrency_avg_time": avg_time
        }
    else:
        print("    All concurrent requests failed")
        return {
            "concurrency_success_rate": 0,
            "concurrency_avg_time": float('inf')
        }

def benchmark_model_server(server_ip, server_port, model_name, server_id=None, model_id=None):
    """Run all benchmark tests for a specific model on a specific server"""
    server_address = f"{server_ip}:{server_port}"
    
    print("\n-------------------------------------------------")
    print(f"TESTING MODEL: {model_name}")
    print(f"SERVER: {server_address}")
    print("-------------------------------------------------")
    
    # All test results
    results = {
        "server": server_address,
        "model": model_name,
        "test_date": datetime.now().isoformat(),
        "server_id": server_id,
        "model_id": model_id
    }
    
    # Test 1: Simple generation (basic speed test)
    simple_results = test_simple_generation(server_address, model_name)
    results.update(simple_results)
    
    # Check if basic tests passed before continuing
    if simple_results["simple_success_rate"] > 0:
        # Test 2: Throughput (longer text generation)
        throughput_results = test_throughput(server_address, model_name)
        results.update(throughput_results)
        
        # Test 3: Context handling (how well it handles different context sizes)
        context_results = test_context_handling(server_address, model_name)
        results["context_handling"] = context_results
        
        # Test 4: First token latency (responsiveness)
        first_token_results = test_first_token_latency(server_address, model_name)
        results.update(first_token_results)
        
        # Test 5: Concurrency (handling multiple requests)
        concurrency_results = test_concurrency(server_address, model_name)
        results.update(concurrency_results)
    else:
        print("  Basic tests failed. Skipping advanced tests.")
    
    # Return the benchmark results
    return results

def save_benchmark_results(results):
    """Save benchmark results to the database"""
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
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
    cursor.execute('''
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
    
    # Commit handled by Database methods
    conn.close()
    
    print(f"Benchmark results saved to database for {results['model']} on {results['server']}")

def get_model_server_pairs(model_filter=None, server_filter=None, limit=None):
    """Get model/server pairs from the database"""
    conn = Database()
    conn.row_factory = sqlite3.Row
    cursor = # Using Database methods instead of cursor
    
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
    
    params = []
    
    # Add model filter if specified
    if model_filter:
        query += " WHERE m.name LIKE ?"
        params.append(f"%{model_filter}%")
    
    # Add server filter if specified
    if server_filter:
        query += " AND s.ip = ?"
        params.append(server_filter)
    
    # Order by model name and server
    query += " ORDER BY m.name, s.ip, s.port"
    
    # Add limit if specified
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    # Execute query
    Database.execute(query, params)
    
    # Fetch all model/server pairs
    pairs = Database.fetch_all(query, params)
    
    # Close connection
    conn.close()
    
    return pairs

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

def run_benchmarks(model_filter=None, max_count=None, server_ip=None, server_port=None, model_name=None):
    """Run benchmarks on model/server pairs"""
    # Initialize the database
    if not init_database():
        return
    
    # If specific server/model provided, benchmark just that
    if server_ip and model_name:
        port = int(server_port) if server_port else 11434
        print(f"Running benchmark for model {model_name} on server {server_ip}:{port}")
        
        results = benchmark_model_server(server_ip, port, model_name)
        
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
        results = benchmark_model_server(ip, port, model_name, server_id, model_id)
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
    # Check if database exists
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file {DB_FILE} not found!")
        return
    
    conn = Database()
    cursor = # Using Database methods instead of cursor
    
    # Check if benchmark_results table exists
    Database.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='benchmark_results'")
    if Database.fetch_one(query, params)[0] == 0:
        print("No benchmark results found in the database.")
        conn.close()
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
    
    # Execute query
    Database.execute(query, params)
    
    # Fetch results
    results = Database.fetch_all(query, params)
    
    # Display results
    if not results:
        print("No benchmark results found.")
        if model_filter:
            print(f"No results match the filter: {model_filter}")
        conn.close()
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
    
    conn.close()

def main():
    """Main function to parse arguments and run benchmarks"""
    parser = argparse.ArgumentParser(description="Ollama Benchmark with Database Integration")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run benchmarks command
    run_parser = subparsers.add_parser("run", help="Run benchmarks on model/server pairs")
    run_parser.add_argument("--model", help="Filter models by name (e.g., 'llama' for all llama models)")
    run_parser.add_argument("--count", type=int, help="Maximum number of model/server pairs to benchmark")
    run_parser.add_argument("--server", help="Specific server IP to benchmark")
    run_parser.add_argument("--port", type=int, help="Specific server port to benchmark")
    run_parser.add_argument("--model-name", help="Specific model name to benchmark")
    
    # Query results command
    query_parser = subparsers.add_parser("query", help="Query benchmark results from the database")
    query_parser.add_argument("--model", help="Filter results by model name")
    query_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to show")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run command
    if args.command == "run":
        run_benchmarks(args.model, args.count, args.server, args.port, args.model_name)
    elif args.command == "query":
        query_benchmark_results(args.model, args.limit)
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user. Exiting...")
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1) 