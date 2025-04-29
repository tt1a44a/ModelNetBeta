#!/usr/bin/env python3
"""
Delayed Honeypot Detector

This module detects endpoints that initially behave legitimately
but have later been converted to honeypots.
"""

import os
import sys
import re
import json
import logging
import argparse
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import from prune_bad_endpoints.py
from prune_bad_endpoints import (
    is_likely_honeypot_response,
    check_endpoint,
    has_vowels,
    has_high_gibberish_ratio,
    get_db_boolean,
    mark_endpoint_as_honeypot,
    mark_endpoint_verified,
    Database,
    init_database,
    DATABASE_TYPE
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("delayed_honeypot_detector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

def calculate_text_similarity(text1, text2):
    """
    Calculate a simple similarity score between two text strings
    Returns a value between 0 (completely different) and 1 (identical)
    """
    # Convert to lowercase and split into words
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # Calculate Jaccard similarity
    if not words1 and not words2:
        return 1.0  # Both empty = identical
    
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    return intersection / union if union > 0 else 0.0

def is_gibberish_word(word):
    """Check if a word appears to be gibberish"""
    # Simplified check: words with unusual character patterns are likely gibberish
    if len(word) > 4 and sum(1 for c in word if not c.isalpha()) > len(word) * 0.3:
        return True
    # Check for words that are just random letters
    elif len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word):
        return True
    # Check for random character strings with mixed numbers and letters
    elif len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 and sum(1 for c in word if c.isalpha()) > 1:
        return True
    return False

def record_verification_data(endpoint_id, response_text, models, is_honeypot):
    """Record verification data for future comparison"""
    
    try:
        # Calculate metrics
        words = response_text.split()
        gibberish_count = sum(1 for word in words if is_gibberish_word(word))
        gibberish_ratio = gibberish_count / len(words) if words else 0
        
        # Create metrics JSON
        response_metrics = {
            "length": len(response_text),
            "gibberish_ratio": gibberish_ratio,
            "word_count": len(words)
        }
        
        # Serialize model names
        if isinstance(models, list):
            model_names = [m.get("name", "") for m in models]
        else:
            model_names = []
            
        # Insert into database
        if DATABASE_TYPE == "postgres":
            Database.execute("""
                INSERT INTO endpoint_verifications 
                (endpoint_id, verification_date, response_sample, detected_models, is_honeypot, response_metrics)
                VALUES (%s, NOW(), %s, %s, %s, %s)
            """, (
                endpoint_id, 
                response_text[:1000], 
                json.dumps(model_names), 
                is_honeypot, 
                json.dumps(response_metrics)
            ))
        else:
            # SQLite
            Database.execute("""
                INSERT INTO endpoint_verifications 
                (endpoint_id, verification_date, response_sample, detected_models, is_honeypot, response_metrics)
                VALUES (?, datetime('now'), ?, ?, ?, ?)
            """, (
                endpoint_id, 
                response_text[:1000], 
                json.dumps(model_names), 
                1 if is_honeypot else 0, 
                json.dumps(response_metrics)
            ))
            
        logger.debug(f"Recorded verification data for endpoint {endpoint_id}")
        return True
    except Exception as e:
        logger.error(f"Error recording verification data: {e}")
        return False

def detect_behavior_change(endpoint_id, current_response):
    """
    Check if an endpoint's behavior has changed significantly since last verification
    Returns (changed, reason) tuple
    """
    try:
        # Get the most recent verification record that's at least a day old
        if DATABASE_TYPE == "postgres":
            query = """
                SELECT response_sample, response_metrics, verification_date
                FROM endpoint_verifications
                WHERE endpoint_id = %s AND verification_date < NOW() - INTERVAL '1 day'
                ORDER BY verification_date DESC
                LIMIT 1
            """
        else:
            # SQLite
            query = """
                SELECT response_sample, response_metrics, verification_date
                FROM endpoint_verifications
                WHERE endpoint_id = ? AND verification_date < datetime('now', '-1 day')
                ORDER BY verification_date DESC
                LIMIT 1
            """
            
        previous = Database.fetch_one(query, (endpoint_id,))
        
        if not previous:
            return False, "No previous verification data for comparison"
        
        prev_response, prev_metrics, prev_date = previous
        prev_metrics = json.loads(prev_metrics) if prev_metrics else {}
        
        # Calculate current metrics
        words = current_response.split()
        gibberish_count = sum(1 for word in words if is_gibberish_word(word))
        gibberish_ratio = gibberish_count / len(words) if words else 0
        
        current_metrics = {
            "length": len(current_response),
            "gibberish_ratio": gibberish_ratio,
            "word_count": len(words)
        }
        
        # Compare metrics
        significant_changes = []
        
        # Check if gibberish ratio has increased significantly
        prev_gibberish = prev_metrics.get("gibberish_ratio", 0)
        if gibberish_ratio > 0.3 and gibberish_ratio > prev_gibberish * 1.5:
            significant_changes.append(f"Gibberish ratio increased ({prev_gibberish:.2f} to {gibberish_ratio:.2f})")
        
        # Check if response length has changed drastically
        prev_length = prev_metrics.get("length", 0)
        if prev_length > 0:
            length_ratio = current_metrics["length"] / prev_length
            if length_ratio < 0.5 or length_ratio > 2:
                significant_changes.append(f"Response length changed by {abs(1-length_ratio):.2f}x")
        
        # Check for significant changes in content
        similarity = calculate_text_similarity(prev_response, current_response)
        if similarity < 0.3:
            significant_changes.append(f"Response content significantly different (similarity: {similarity:.2f})")
        
        if significant_changes:
            return True, "Behavior change detected: " + ", ".join(significant_changes)
        
        return False, "No significant behavior change detected"
    except Exception as e:
        logger.error(f"Error detecting behavior change: {e}")
        return False, f"Error in behavior detection: {str(e)}"

async def check_endpoint_with_history(endpoint_id, ip, port, timeout=10):
    """
    Enhanced version of check_endpoint that records verification history
    and checks for behavioral changes
    """
    try:
        # Call the original check_endpoint function
        success, result = await check_endpoint(endpoint_id, ip, port, timeout)
        
        # If successful, record the verification data
        # We need to make another request to get a response to analyze
        if success:
            # The endpoint is legitimate, let's record a sample response
            tags_url = f"http://{ip}:{port}/api/tags"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(tags_url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Get models
                        models = data.get("models", [])
                        
                        # Select the first model to test
                        if models and len(models) > 0:
                            model_name = models[0].get("name", "")
                            
                            if model_name:
                                # Send a test prompt to record the response
                                generate_url = f"http://{ip}:{port}/api/generate"
                                
                                payload = {
                                    "model": model_name,
                                    "prompt": "Say hello in one short sentence",
                                    "stream": False,
                                    "max_tokens": 50
                                }
                                
                                async with session.post(generate_url, json=payload, timeout=timeout) as gen_response:
                                    if gen_response.status == 200:
                                        gen_data = await gen_response.json()
                                        response_text = gen_data.get("response", "")
                                        
                                        # Check for behavior change compared to previous verification
                                        has_changed, change_reason = detect_behavior_change(endpoint_id, response_text)
                                        
                                        # Record verification data
                                        is_honeypot = is_likely_honeypot_response(response_text)
                                        record_verification_data(endpoint_id, response_text, models, is_honeypot)
                                        
                                        if has_changed and is_honeypot:
                                            # Endpoint behavior has changed AND it looks like a honeypot
                                            reason = f"Delayed honeypot detected: {change_reason}"
                                            logger.warning(f"Endpoint {ip}:{port} (ID: {endpoint_id}) {reason}")
                                            mark_endpoint_as_honeypot(endpoint_id, reason)
                                            return False, reason
                                        
                                        if has_changed:
                                            # Behavior changed but not necessarily a honeypot
                                            logger.info(f"Endpoint {ip}:{port} (ID: {endpoint_id}) behavior changed: {change_reason}")
        
        return success, result
    except Exception as e:
        logger.error(f"Error in check_endpoint_with_history: {e}")
        return False, f"Error: {str(e)}"

async def scan_verified_endpoints(days_since_last_check=7, limit=100, batch_size=10, timeout=10):
    """
    Scan verified endpoints that haven't been checked recently
    to detect delayed honeypot behavior
    """
    try:
        # Get endpoints to check
        if DATABASE_TYPE == "postgres":
            query = """
                SELECT id, ip, port
                FROM endpoints
                WHERE verified = 1
                AND (last_check_date IS NULL OR last_check_date < NOW() - INTERVAL '%s days')
                ORDER BY last_check_date ASC NULLS FIRST
                LIMIT %s
            """
            endpoints = Database.fetch_all(query, (days_since_last_check, limit))
        else:
            # SQLite
            query = """
                SELECT id, ip, port
                FROM endpoints
                WHERE verified = 1
                AND (last_check_date IS NULL OR last_check_date < datetime('now', '-%s days'))
                ORDER BY last_check_date ASC
                LIMIT ?
            """
            endpoints = Database.fetch_all(query.replace('%s', '?'), (days_since_last_check, limit))
        
        logger.info(f"Found {len(endpoints)} verified endpoints to check for delayed honeypot behavior")
        
        # Process endpoints in batches
        total_honeypots = 0
        total_checked = 0
        
        for i in range(0, len(endpoints), batch_size):
            batch = endpoints[i:i+batch_size]
            
            # Create tasks for concurrent checking
            tasks = []
            for endpoint in batch:
                endpoint_id, ip, port = endpoint
                tasks.append(check_endpoint_with_history(endpoint_id, ip, int(port), timeout))
            
            # Run tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error checking endpoint {batch[j][1]}:{batch[j][2]}: {result}")
                    continue
                
                success, reason = result
                endpoint_id, ip, port = batch[j]
                
                if not success and "honeypot" in reason.lower():
                    total_honeypots += 1
                    logger.warning(f"Detected delayed honeypot {ip}:{port} (ID: {endpoint_id}): {reason}")
                
                total_checked += 1
            
            # Add a brief pause between batches
            await asyncio.sleep(1)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(endpoints) + batch_size - 1)//batch_size}, detected {total_honeypots} honeypots")
        
        return total_checked, total_honeypots
    except Exception as e:
        logger.error(f"Error in scan_verified_endpoints: {e}")
        return 0, 0

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Delayed Honeypot Detector")
    parser.add_argument('--days', type=int, default=7, help='Days since last verification to check endpoints (default: 7)')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of endpoints to check (default: 100)')
    parser.add_argument('--batch-size', type=int, default=10, help='Number of endpoints to check concurrently (default: 10)')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout for requests in seconds (default: 10)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--test-endpoint', help='Test a specific endpoint (format: IP:PORT)')
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Test a specific endpoint if requested
    if args.test_endpoint:
        try:
            ip, port = args.test_endpoint.split(':')
            port = int(port)
            
            # Find endpoint in database
            endpoint_info = Database.fetch_one(
                "SELECT id, verified, is_honeypot FROM endpoints WHERE ip = %s AND port = %s", 
                (ip, str(port))
            )
            
            if not endpoint_info:
                logger.error(f"Endpoint {ip}:{port} not found in database")
                return
            
            endpoint_id, verified, is_honeypot = endpoint_info
            logger.info(f"Testing endpoint {ip}:{port} (ID: {endpoint_id}) for delayed honeypot behavior")
            
            # Check the endpoint
            success, result = await check_endpoint_with_history(endpoint_id, ip, port, args.timeout)
            
            # Get updated status
            updated_info = Database.fetch_one(
                "SELECT verified, is_honeypot, honeypot_reason FROM endpoints WHERE id = %s", 
                (endpoint_id,)
            )
            
            new_verified, new_is_honeypot, honeypot_reason = updated_info
            
            # Print results
            print(f"\nTest Results for {ip}:{port} (ID: {endpoint_id}):")
            print(f"  - Original status: verified={verified}, honeypot={is_honeypot}")
            print(f"  - New status: verified={new_verified}, honeypot={new_is_honeypot}")
            print(f"  - Test result: {result}")
            
            # If the status changed, show the reason
            if is_honeypot != new_is_honeypot:
                print(f"  - Reason for change: {honeypot_reason}")
            
            return
        except ValueError:
            logger.error(f"Invalid endpoint format: {args.test_endpoint}. Use IP:PORT")
            return
        except Exception as e:
            logger.error(f"Error testing endpoint {args.test_endpoint}: {e}")
            return
    
    # Otherwise, scan verified endpoints
    logger.info(f"Scanning verified endpoints that haven't been checked in {args.days} days")
    total_checked, total_honeypots = await scan_verified_endpoints(
        days_since_last_check=args.days,
        limit=args.limit,
        batch_size=args.batch_size,
        timeout=args.timeout
    )
    
    # Print summary
    print(f"\nScan Summary:")
    print(f"  - Endpoints checked: {total_checked}")
    print(f"  - Delayed honeypots detected: {total_honeypots}")
    print(f"  - Honeypot rate: {total_honeypots/total_checked*100:.2f}% (if >0 endpoints checked)")

if __name__ == "__main__":
    asyncio.run(main()) 