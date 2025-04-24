#!/usr/bin/env python3
"""
Script to check offline endpoints and reactivate them if they become available again.
Run this script regularly (e.g., hourly) using a cron job or scheduler.
"""

# Added by migration script
from database import Database, init_database, DATABASE_TYPE
import asyncio
import logging
import time
import os
import sys
from datetime import datetime, timedelta
import argparse

# Import existing endpoint checking logic
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from prune_bad_endpoints import check_endpoint, mark_endpoint_verified

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("check_offline_endpoints.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

async def get_inactive_endpoints(hours_threshold=1, batch_size=100):
    """
    Get inactive endpoints that haven't been checked in the last X hours
    
    Args:
        hours_threshold: Only check endpoints that haven't been checked in this many hours
        batch_size: Maximum number of endpoints to return
    
    Returns:
        List of tuples (id, ip, port) for inactive endpoints
    """
    try:
        if DATABASE_TYPE == "postgres":
            query = """
                SELECT id, ip, port
                FROM endpoints
                WHERE is_active = FALSE
                AND (last_check_date IS NULL OR last_check_date < NOW() - INTERVAL '1 hour' * %s)
                ORDER BY last_check_date ASC NULLS FIRST
                LIMIT %s
            """
            return Database.fetch_all(query, (hours_threshold, batch_size))
        else:
            # SQLite
            # Calculate timestamp for the threshold
            threshold_time = datetime.now() - timedelta(hours=hours_threshold)
            threshold_str = threshold_time.strftime('%Y-%m-%d %H:%M:%S')
            
            query = """
                SELECT id, ip, port
                FROM endpoints
                WHERE is_active = 0
                AND (last_check_date IS NULL OR last_check_date < ?)
                ORDER BY last_check_date ASC
                LIMIT ?
            """
            return Database.fetch_all(query, (threshold_str, batch_size))
    except Exception as e:
        logger.error(f"Error getting inactive endpoints: {e}")
        return []

async def check_endpoints(endpoints, max_concurrent=10, timeout=10):
    """Check multiple inactive endpoints concurrently"""
    if not endpoints:
        logger.info("No inactive endpoints to check")
        return 0, 0

    total = len(endpoints)
    logger.info(f"Checking {total} inactive endpoints with timeout {timeout}s")
    
    # Create a semaphore to limit concurrent connections
    sem = asyncio.Semaphore(max_concurrent)
    
    async def _check_with_semaphore(endpoint):
        async with sem:
            endpoint_id, ip, port = endpoint
            return await check_endpoint(endpoint_id, ip, port, timeout)
    
    # Create tasks for each endpoint
    tasks = [_check_with_semaphore(endpoint) for endpoint in endpoints]
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count successes and failures
    successes = 0
    failures = 0
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Error checking endpoint {endpoints[i][1]}:{endpoints[i][2]}: {result}")
            failures += 1
        else:
            is_valid, _ = result
            if is_valid:
                successes += 1
            else:
                failures += 1
    
    logger.info(f"Reactivated {successes} endpoints, {failures} remain offline")
    return successes, failures

async def main(hours_threshold=1, batch_size=100, max_concurrent=10, timeout=10):
    """Main function to check and reactivate inactive endpoints"""
    start_time = time.time()
    
    # Get inactive endpoints
    endpoints = await get_inactive_endpoints(hours_threshold, batch_size)
    logger.info(f"Found {len(endpoints)} inactive endpoints to check")
    
    # Check endpoints
    if endpoints:
        successes, failures = await check_endpoints(endpoints, max_concurrent, timeout)
    else:
        successes, failures = 0, 0
    
    # Update statistics
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Completed in {duration:.2f} seconds")
    logger.info(f"Reactivated: {successes}, Still offline: {failures}")
    
    return successes, failures

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check and reactivate offline Ollama endpoints")
    parser.add_argument("--hours", type=int, default=1, help="Only check endpoints not checked in this many hours")
    parser.add_argument("--batch", type=int, default=100, help="Maximum number of endpoints to check")
    parser.add_argument("--concurrent", type=int, default=10, help="Maximum number of concurrent checks")
    parser.add_argument("--timeout", type=int, default=10, help="Connection timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    # Set log level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Run the main function
    asyncio.run(main(args.hours, args.batch, args.concurrent, args.timeout)) 