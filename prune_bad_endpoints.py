#!/usr/bin/env python3
"""
Prune bad endpoints from the Ollama Scanner database
"""

# Added by migration script
from database import Database, init_database, DATABASE_TYPE

import os
import sys
import re
import json
import time
import asyncio
import aiohttp
import random
import logging
import argparse
import threading
from datetime import datetime
from dotenv import load_dotenv
import concurrent.futures

# Function to get proper boolean representation for different database types
def get_db_boolean(value, as_string=True, for_verified=False):
    """
    Get the proper boolean value for the current database type
    Args:
        value (bool): Python boolean value
        as_string (bool): Whether to return the value as a string
        for_verified (bool): Whether this is for the verified column (which is INTEGER in both databases)
    
    Returns:
        String or integer representation of the boolean value for SQL
    """
    if for_verified:
        # 'verified' column is INTEGER in both database types
        return "1" if value else "0" if as_string else 1 if value else 0
    
    if DATABASE_TYPE == "postgres":
        # PostgreSQL
        return "TRUE" if value else "FALSE" if as_string else True if value else False
    else:
        # SQLite
        return "1" if value else "0" if as_string else 1 if value else 0

# Constants
MAX_CONCURRENT_REQUESTS = 10
TIMEOUT = 10  # Default timeout in seconds
BATCH_SIZE = 100  # Default batch size for processing

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default level, will be modified via --verbose flag
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("prune_endpoints.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
init_database()

# Load environment variables
load_dotenv()

# Global arguments
args = None

# Function to get endpoints to prune based on status
async def get_endpoints_to_prune(batch_size=BATCH_SIZE, offset=0):
    """Get a batch of endpoints that need pruning based on status"""
    try:
        if DATABASE_TYPE == "postgres":
            if args.retest_all:
                # Process all endpoints if retest_all is enabled, ordered by oldest verification date first
                query = """
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    ORDER BY verification_date ASC NULLS FIRST, scan_date ASC
                    LIMIT %s OFFSET %s
                """
                return Database.fetch_all(query, (batch_size, offset))
            elif args.force:
                # Process all endpoints if force is enabled
                query = """
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    ORDER BY scan_date
                    LIMIT %s OFFSET %s
                """
                return Database.fetch_all(query, (batch_size, offset))
            else:
                # Determine verified value based on input status
                verified_value = "1" if args.input_status == "verified" else "0"
                
                # Only process endpoints with input_status
                query = f"""
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    WHERE verified = {verified_value}
                    ORDER BY scan_date
                    LIMIT %s OFFSET %s
                """
                return Database.fetch_all(query, (batch_size, offset))
        else:
            # SQLite
            if args.retest_all:
                # Process all endpoints if retest_all is enabled, ordered by oldest verification date first
                query = """
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    ORDER BY verification_date ASC NULLS FIRST, scan_date ASC
                    LIMIT ? OFFSET ?
                """
                return Database.fetch_all(query, (batch_size, offset))
            elif args.force:
                # Process all endpoints if force is enabled
                query = """
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    ORDER BY scan_date
                    LIMIT ? OFFSET ?
                """
                return Database.fetch_all(query, (batch_size, offset))
            else:
                # Determine verified value based on input status
                verified_value = "1" if args.input_status == "verified" else "0"
                
                # Only process endpoints with input_status
                query = f"""
                    SELECT id, ip, port, verified 
                    FROM endpoints
                    WHERE verified = {verified_value}
                    ORDER BY scan_date
                    LIMIT ? OFFSET ?
                """
                return Database.fetch_all(query, (batch_size, offset))
    except Exception as e:
        logger.error(f"Error getting endpoints to prune: {e}")
        return []

# Function to count total endpoints that match criteria
async def count_endpoints_to_prune():
    """Count total endpoints that need pruning based on status"""
    try:
        if DATABASE_TYPE == "postgres":
            if args.retest_all:
                # Count all endpoints if retest_all is enabled
                query = "SELECT COUNT(*) FROM endpoints"
                return Database.fetch_one(query)[0]
            elif args.force:
                # Count all endpoints if force is enabled
                query = "SELECT COUNT(*) FROM endpoints"
                return Database.fetch_one(query)[0]
            else:
                # Determine verified value based on input status
                verified_value = "1" if args.input_status == "verified" else "0"
                
                # Count endpoints with input_status
                query = f"SELECT COUNT(*) FROM endpoints WHERE verified = {verified_value}"
                return Database.fetch_one(query)[0]
        else:
            # SQLite
            if args.retest_all:
                # Count all endpoints if retest_all is enabled
                query = "SELECT COUNT(*) FROM endpoints"
                return Database.fetch_one(query)[0]
            elif args.force:
                # Count all endpoints if force is enabled
                query = "SELECT COUNT(*) FROM endpoints"
                return Database.fetch_one(query)[0]
            else:
                # Determine verified value based on input status
                verified_value = "1" if args.input_status == "verified" else "0"
                
                # Count endpoints with input_status
                query = f"SELECT COUNT(*) FROM endpoints WHERE verified = {verified_value}"
                return Database.fetch_one(query)[0]
    except Exception as e:
        logger.error(f"Error counting endpoints to prune: {e}")
        return 0

# Function to mark endpoint as verified
def mark_endpoint_verified(endpoint_id, ip, port):
    """Mark endpoint as verified"""
    try:
        # Ensure database connection is properly initialized
        Database.ensure_pool_initialized()
        
        # Update endpoints table first
        Database.execute(f"""
            UPDATE endpoints
            SET verified = 1, 
                verification_date = NOW(),
                is_honeypot = {get_db_boolean(False)},
                honeypot_reason = NULL,
                is_active = {get_db_boolean(True)},
                inactive_reason = NULL,
                last_check_date = NOW()
            WHERE id = %s
        """, (endpoint_id,))
        
        # Check if this endpoint is already in verified_endpoints
        verified_exists = Database.fetch_one("SELECT id FROM verified_endpoints WHERE endpoint_id = %s", (endpoint_id,)) is not None
        
        if not verified_exists:
            # Add to verified_endpoints
            Database.execute("""
                INSERT INTO verified_endpoints (endpoint_id, verification_date)
                VALUES (%s, NOW())
            """, (endpoint_id,))
        else:
            # Update verification date
            Database.execute("""
                UPDATE verified_endpoints 
                SET verification_date = NOW() 
                WHERE endpoint_id = %s
            """, (endpoint_id,))
        
        logger.info(f"Endpoint {ip}:{port} verified successfully")
        return True
    except Exception as e:
        logger.error(f"Error marking endpoint as verified: {e}")
        return False

# Function to mark endpoint as failed
def mark_endpoint_failed(endpoint_id, ip, port, reason=None):
    """Mark endpoint as failed"""
    try:
        # For both PostgreSQL and SQLite
        Database.execute("""
            UPDATE endpoints
            SET verified = 0
            WHERE id = %s
        """, (endpoint_id,))
        
        # Remove from verified_endpoints if it exists
        Database.execute("DELETE FROM verified_endpoints WHERE endpoint_id = %s", (endpoint_id,))
        
        logger.info(f"Endpoint {ip}:{port} failed verification: {reason}")
        return True
    except Exception as e:
        logger.error(f"Error marking endpoint {ip}:{port} as failed: {e}")
        return False

# Function to mark endpoint as honeypot
def mark_endpoint_as_honeypot(endpoint_id, reason):
    """
    Mark an endpoint as a honeypot in the database
    
    Args:
        endpoint_id: The ID of the endpoint to mark as a honeypot
        reason: The reason why the endpoint is considered a honeypot
        
    Returns:
        bool: Success status
    """
    try:
        # Ensure database connection is properly initialized
        Database.ensure_pool_initialized()
        
        # Get the IP and port for logging
        endpoint_info = Database.fetch_one(
            "SELECT ip, port FROM endpoints WHERE id = %s",
            (endpoint_id,)
        )
        
        if not endpoint_info:
            logger.warning(f"Endpoint with ID {endpoint_id} not found when trying to mark as honeypot")
            return False
            
        ip, port = endpoint_info
        
        # Update the endpoint status in the database
        Database.execute(
            f"UPDATE endpoints SET is_honeypot = {get_db_boolean(True)}, honeypot_reason = %s, last_check_date = NOW() WHERE id = %s",
            (reason, endpoint_id)
        )
        
        # Also mark as failed/unverified
        Database.execute("UPDATE endpoints SET verified = 0 WHERE id = %s", (endpoint_id,))
        
        # Remove from verified_endpoints if it exists
        Database.execute("DELETE FROM verified_endpoints WHERE endpoint_id = %s", (endpoint_id,))
        
        logger.info(f"Marked endpoint {ip}:{port} (ID: {endpoint_id}) as honeypot: {reason}")
        return True
        
    except Exception as e:
        logger.error(f"Error marking endpoint {endpoint_id} as honeypot: {str(e)}")
        return False

# Function to mark endpoint as inactive
def mark_endpoint_as_inactive(endpoint_id, reason):
    """
    Mark an endpoint as inactive in the database
    
    Args:
        endpoint_id: The ID of the endpoint to mark as inactive
        reason: The reason why the endpoint is considered inactive
        
    Returns:
        bool: Success status
    """
    try:
        # Ensure database connection is properly initialized
        Database.ensure_pool_initialized()
        
        # Get the IP and port for logging
        endpoint_info = Database.fetch_one(
            "SELECT ip, port FROM endpoints WHERE id = %s",
            (endpoint_id,)
        )
        
        if not endpoint_info:
            logger.warning(f"Endpoint with ID {endpoint_id} not found when trying to mark as inactive")
            return False
            
        ip, port = endpoint_info
        
        # Update the endpoint status in the database
        try:
            Database.execute(
                f"UPDATE endpoints SET is_active = {get_db_boolean(False)}, verified = 0, inactive_reason = %s, last_check_date = NOW() WHERE id = %s",
                (reason, endpoint_id)
            )
            
            # Remove from verified_endpoints if it exists
            Database.execute("DELETE FROM verified_endpoints WHERE endpoint_id = %s", (endpoint_id,))
        except Exception as e:
            # Fall back to old method if column doesn't exist or there's an error
            logger.warning(f"Error updating inactive status, falling back to basic update: {e}")
            Database.execute("UPDATE endpoints SET verified = 0 WHERE id = %s", (endpoint_id,))
        
        logger.info(f"Marked endpoint {ip}:{port} (ID: {endpoint_id}) as inactive: {reason}")
        return True
        
    except Exception as e:
        logger.error(f"Error marking endpoint {endpoint_id} as inactive: {str(e)}")
        return False

# Function to check if an Ollama server is accessible
async def check_endpoint(endpoint_id, ip, port, timeout=TIMEOUT):
    """Check if an Ollama endpoint is accessible and retrieve model information"""
    tags_url = f"http://{ip}:{port}/api/tags"
    
    try:
        # Step 1: Check if /api/tags endpoint is accessible
        logger.info(f"Checking endpoint {ip}:{port} - Testing /api/tags endpoint")
        async with aiohttp.ClientSession() as session:
            async with session.get(tags_url, timeout=timeout) as response:
                if response.status == 200:
                    # Successfully connected
                    data = await response.json()
                    logger.info(f"Endpoint {ip}:{port} /api/tags response: {json.dumps(data, indent=2)}")
                    
                    # Check if there are available models
                    models = data.get("models", [])
                    if not models:
                        reason = "No models available"
                        logger.warning(f"Endpoint {ip}:{port} has no models")
                        mark_endpoint_failed(endpoint_id, ip, port, reason)
                        return False, reason
                    
                    # Step 2: Try to send multiple generation requests to validate API compliance
                    logger.info(f"Testing model generation on {ip}:{port}")
                    
                    # Select the first model to test
                    model_name = models[0].get("name", "")
                    if not model_name:
                        reason = "Invalid model data"
                        logger.warning(f"Endpoint {ip}:{port} returned invalid model data")
                        mark_endpoint_failed(endpoint_id, ip, port, reason)
                        return False, reason
                    
                    # Test with multiple prompts for more reliable detection
                    prompts = [
                        "Say hello in one short sentence",
                        "What is your name?",
                        "Tell me about yourself"
                    ]
                    
                    honeypot_detections = 0
                    all_responses = []
                    
                    for i, prompt in enumerate(prompts):
                        # Only test up to 3 prompts to avoid overloading the endpoint
                        if i >= len(prompts):
                            break
                            
                        # Following the Ollama API docs to test a chat generation
                        generate_url = f"http://{ip}:{port}/api/generate"
                        
                        # Simple prompt to test if the API works
                        payload = {
                            "model": model_name,
                            "prompt": prompt,
                            "stream": False,
                            "max_tokens": 50
                        }
                        
                        try:
                            logger.info(f"Sending test prompt #{i+1} to {ip}:{port} with model {model_name}")
                            async with session.post(generate_url, json=payload, timeout=timeout) as gen_response:
                                if gen_response.status == 200:
                                    gen_data = await gen_response.json()
                                    response_text = gen_data.get("response", "")
                                    all_responses.append(response_text)
                                    
                                    # Log the full response
                                    logger.info(f"Endpoint {ip}:{port} generation response #{i+1}: '{response_text}'")
                                    
                                    # Check for honeypot/invalid responses
                                    is_honeypot = is_likely_honeypot_response(response_text)
                                    logger.info(f"Honeypot detection for prompt #{i+1}: {is_honeypot}")
                                    
                                    if is_honeypot:
                                        honeypot_detections += 1
                                else:
                                    reason = f"Generation failed: HTTP {gen_response.status}"
                                    logger.warning(f"Endpoint {ip}:{port} generation test #{i+1} failed: {reason}")
                                    
                            # Add slight delay between requests
                            await asyncio.sleep(1)
                        except Exception as e:
                            reason = f"Generation test #{i+1} failed: {str(e)}"
                            logger.warning(f"Endpoint {ip}:{port} generation test error: {reason}")
                    
                    # If we have responses to analyze
                    if all_responses:
                        # Try to record verification data if the endpoint_verifications table exists
                        try:
                            # Check if the endpoint_verifications table exists
                            if DATABASE_TYPE == "postgres":
                                table_exists = Database.fetch_one("""
                                    SELECT EXISTS (
                                        SELECT FROM information_schema.tables 
                                        WHERE table_schema = 'public' 
                                        AND table_name = 'endpoint_verifications'
                                    )
                                """)
                            else:
                                # SQLite
                                table_exists = Database.fetch_one("""
                                    SELECT name FROM sqlite_master 
                                    WHERE type='table' AND name='endpoint_verifications'
                                """)
                            
                            if table_exists:
                                # Calculate metrics for the first response
                                if len(all_responses) > 0:
                                    response_text = all_responses[0]
                                    words = response_text.split()
                                    
                                    # Count gibberish words
                                    gibberish_count = 0
                                    for word in words:
                                        if len(word) > 4 and sum(1 for c in word if not c.isalpha()) > len(word) * 0.3:
                                            gibberish_count += 1
                                        elif len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word):
                                            gibberish_count += 1
                                        elif len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 and sum(1 for c in word if c.isalpha()) > 1:
                                            gibberish_count += 1
                                    
                                    gibberish_ratio = gibberish_count / len(words) if words else 0
                                    
                                    # Create metrics JSON
                                    response_metrics = {
                                        "length": len(response_text),
                                        "gibberish_ratio": gibberish_ratio,
                                        "word_count": len(words)
                                    }
                                    
                                    # Record verification data
                                    if DATABASE_TYPE == "postgres":
                                        Database.execute("""
                                            INSERT INTO endpoint_verifications 
                                            (endpoint_id, verification_date, response_sample, detected_models, is_honeypot, response_metrics)
                                            VALUES (%s, NOW(), %s, %s, %s, %s)
                                        """, (
                                            endpoint_id, 
                                            response_text[:1000], 
                                            json.dumps([m.get("name", "") for m in models]), 
                                            honeypot_detections > 0, 
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
                                            json.dumps([m.get("name", "") for m in models]), 
                                            1 if honeypot_detections > 0 else 0, 
                                            json.dumps(response_metrics)
                                        ))
                                    
                                    logger.debug(f"Recorded verification data for endpoint {ip}:{port} (ID: {endpoint_id})")
                        except Exception as e:
                            # Failure to record verification data is not critical
                            logger.debug(f"Failed to record verification data: {e}")
                        
                        # Check if the majority of prompts triggered honeypot detection
                        honeypot_ratio = honeypot_detections / len(all_responses)
                        
                        if honeypot_ratio >= 0.5:  # If 50% or more responses appear to be from a honeypot
                            reason = f"Response appears to be from a honeypot ({honeypot_detections}/{len(all_responses)} prompts triggered detection)"
                            logger.warning(f"Endpoint {ip}:{port} likely honeypot - Response ratio: {honeypot_ratio:.2f}")
                            # Mark as honeypot in the database
                            mark_endpoint_as_honeypot(endpoint_id, reason)
                            return False, reason
                        
                        # Process models and mark as verified if it's not a honeypot
                        logger.info(f"Endpoint {ip}:{port} validation successful")
                        mark_endpoint_verified(endpoint_id, ip, port)
                        process_models(endpoint_id, ip, port, models)
                        return True, f"Verified: {len(models)} models found, generation test passed"
                    else:
                        # No responses received
                        reason = "No responses received from generation tests"
                        logger.warning(f"Endpoint {ip}:{port} failed: {reason}")
                        mark_endpoint_failed(endpoint_id, ip, port, reason)
                        return False, reason
                else:
                    # Failed with HTTP error
                    reason = f"HTTP error: {response.status}"
                    logger.warning(f"Endpoint {ip}:{port} /api/tags request failed: {reason}")
                    
                    # Mark as inactive in the database if it's a 404 or similar error
                    if response.status in [404, 403, 401, 500]:
                        mark_endpoint_as_inactive(endpoint_id, reason)
                    else:
                        mark_endpoint_failed(endpoint_id, ip, port, reason)
                    
                    return False, reason
    except asyncio.TimeoutError:
        reason = f"Connection timeout ({timeout}s)"
        logger.warning(f"Endpoint {ip}:{port} timed out after {timeout}s")
        mark_endpoint_as_inactive(endpoint_id, reason)
        return False, reason
    except aiohttp.ClientError as e:
        reason = f"Connection error: {str(e)}"
        logger.warning(f"Endpoint {ip}:{port} connection error: {str(e)}")
        mark_endpoint_as_inactive(endpoint_id, reason)
        return False, reason
    except Exception as e:
        reason = f"Unexpected error: {str(e)}"
        logger.error(f"Endpoint {ip}:{port} unexpected error: {str(e)}")
        mark_endpoint_failed(endpoint_id, ip, port, reason)
        return False, reason

# Function to check if a response appears to be from a honeypot
def is_likely_honeypot_response(text):
    """
    Check if the response text appears to be from a honeypot
    Returns True if the response is likely from a honeypot, False otherwise
    """
    if not text:
        logger.debug("Empty response detected - suspicious")
        return True  # Empty response is suspicious
    
    # Check for common honeypot patterns
    honeypot_indicators = [
        # Messages that reveal it's a honeypot
        "honeypot",
        "this is a trap",
        
        # Typical prefixes that shouldn't be in the response
        "Using Model:",
        "Sending prompt to",
        "Loading Model:",
        "Loaded Model:",
        "Retrieving from",
        
        # API debugging output that shouldn't be in the response
        "curl",
        "wget",
        "ollama",
        "request:",
        "response:",
        "api/generate",
        
        # References to known honeypot tools
        "cowrie",
        
        # Patterns found in example honeypot responses
        "model_id:",
        "endpoint_id:",
        
        # Common log indicators
        "[INFO]", "[DEBUG]", "[ERROR]", "[WARNING]",
        "INFO:", "DEBUG:", "ERROR:", "WARNING:"
    ]
    
    # Check for any obvious indicators
    for indicator in honeypot_indicators:
        if indicator.lower() in text.lower():
            logger.debug(f"Honeypot indicator found: '{indicator}' in response")
            return True
    
    # Check for timestamp patterns in logs
    timestamp_patterns = [
        r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',  # ISO format: 2023-01-01 12:34:56
        r'\d{2}/\d{2}/\d{4}',  # Date format: 01/02/2023
        r'\d{2}:\d{2}:\d{2}\.\d+',  # Time with milliseconds: 12:34:56.789
    ]
    
    for pattern in timestamp_patterns:
        if re.search(pattern, text):
            logger.debug(f"Timestamp pattern found in response: '{pattern}'")
            return True
    
    # Check for sensitive information
    sensitive_patterns = [
        # API keys and tokens
        r'(?:api[_-]?key|token|secret|access[_-]?key)[=:]\s*[\w\-]{10,}',
        # PostgreSQL connection strings
        r'postgres(?:ql)?://\w+:[^@]+@[\w\-\.]+(?::\d+)?/\w+',
        # Other database connection strings
        r'(?:mysql|mongodb|redis)://',
        # AWS keys
        r'(?:AKIA|ASIA)[A-Z0-9]{16}',
        # IP addresses with ports in suspicious contexts
        r'connecting to \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+',
        # File paths that shouldn't be exposed
        r'/(?:home|var|etc|root)/\w+/',
        # Environment variables
        r'(?:ENV|ENVIRONMENT|API_KEY|SECRET)='
    ]
    
    for pattern in sensitive_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logger.debug(f"Sensitive information pattern found: '{pattern}'")
            return True
    
    # Check for gibberish/random text followed by normal text (a common pattern)
    if len(text) > 100:
        # Split into first and second half
        first_half = text[:len(text)//2]
        second_half = text[len(text)//2:]
        
        # If first half is mostly gibberish and second half has normal words
        if has_high_gibberish_ratio(first_half) and not has_high_gibberish_ratio(second_half):
            logger.debug("Honeypot pattern detected: gibberish followed by normal text")
            return True
    
    # Check for gibberish/random text
    # Count intelligible words vs random character sequences
    words = text.split()
    if len(words) < 3:
        return False  # Too short to analyze
    
    # Check percentage of words that appear random/gibberish
    gibberish_count = 0
    gibberish_words = []
    
    for word in words:
        is_gibberish = False
        
        # Simplified check: words with unusual character patterns are likely gibberish
        if len(word) > 4 and sum(1 for c in word if not c.isalpha()) > len(word) * 0.3:
            gibberish_count += 1
            is_gibberish = True
        # Check for words that are just random letters
        elif len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word):
            gibberish_count += 1
            is_gibberish = True
        # Check for random character strings with mixed numbers and letters
        elif len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 and sum(1 for c in word if c.isalpha()) > 1:
            gibberish_count += 1
            is_gibberish = True
            
        if is_gibberish and len(gibberish_words) < 5:
            gibberish_words.append(word)
    
    gibberish_ratio = gibberish_count / len(words) if words else 0
    
    # Log some examples of gibberish words if in debug mode
    if gibberish_words and logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Examples of suspicious gibberish words: {', '.join(gibberish_words[:5])}")
    
    # If more than 30% of words appear to be gibberish, it's likely a honeypot
    if gibberish_ratio > 0.3:
        logger.debug(f"Honeypot detected: high gibberish ratio {gibberish_ratio:.2f}")
        return True
    
    # Enhanced check for mixed content in sections
    sections = re.split(r'[.!?\n]+', text)
    mixed_content_sections = 0
    
    for section in sections:
        if len(section.strip()) < 10:
            continue
        
        # Check for sections with mixed gibberish and normal text
        section_words = section.strip().split()
        if section_words:
            gibberish_words_in_section = sum(1 for word in section_words 
                if (len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word))
                or (len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 
                    and sum(1 for c in word if c.isalpha()) > 1))
            
            # If we have some gibberish words but not all words are gibberish
            if 0 < gibberish_words_in_section < len(section_words):
                mixed_content_sections += 1
    
    # If we have multiple sections with mixed content, it's likely a honeypot
    if mixed_content_sections >= 2 or (len(sections) > 0 and mixed_content_sections / len(sections) > 0.25):
        logger.debug(f"Honeypot detected: {mixed_content_sections} sections with mixed gibberish and normal content")
        return True
        
    return False

# Helper function to check if a word has vowels (real words typically do)
def has_vowels(word):
    """Check if a word contains vowels, which most real words do"""
    return any(c in "aeiouAEIOU" for c in word)

# Helper function to check for high gibberish ratio in text
def has_high_gibberish_ratio(text):
    """Check if text has a high ratio of gibberish words"""
    words = text.split()
    if len(words) < 3:
        return False
        
    gibberish_count = 0
    for word in words:
        if (len(word) > 4 and sum(1 for c in word if not c.isalpha()) > len(word) * 0.3) or \
           (len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word)) or \
           (len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 and sum(1 for c in word if c.isalpha()) > 1):
            gibberish_count += 1
    
    return gibberish_count / len(words) > 0.3 if words else False

# Function to process models for an endpoint
def process_models(endpoint_id, ip, port, models):
    """Process models for a verified endpoint"""
    try:
        for model in models:
            name = model.get("name", "Unknown")
            
            # Check if this model already exists for this endpoint
            model_exists = Database.fetch_one(
                "SELECT id FROM models WHERE endpoint_id = %s AND name = %s", 
                (endpoint_id, name)
            ) is not None
            
            # Extract model details
            size = model.get("size", 0)
            size_mb = size / (1024 * 1024) if size else 0
            
            details = model.get("details", {})
            parameter_size = details.get("parameter_size", "Unknown")
            quantization_level = details.get("quantization_level", "Unknown")
            
            if model_exists:
                # Update existing model
                Database.execute("""
                    UPDATE models
                    SET parameter_size = %s, quantization_level = %s, size_mb = %s
                    WHERE endpoint_id = %s AND name = %s
                """, (parameter_size, quantization_level, size_mb, endpoint_id, name))
            else:
                # Insert new model
                Database.execute("""
                    INSERT INTO models (endpoint_id, name, parameter_size, quantization_level, size_mb)
                    VALUES (%s, %s, %s, %s, %s)
                """, (endpoint_id, name, parameter_size, quantization_level, size_mb))
        
        logger.info(f"Processed {len(models)} models for endpoint {ip}:{port}")
        return True
    except Exception as e:
        logger.error(f"Error processing models for endpoint {ip}:{port}: {e}")
        return False

# Function to check multiple endpoints concurrently
async def check_endpoints(endpoints, timeout=TIMEOUT, max_concurrent=MAX_CONCURRENT_REQUESTS):
    """Check multiple endpoints concurrently"""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _check_with_semaphore(endpoint):
        endpoint_id, ip, port, status = endpoint
        async with semaphore:
            return await check_endpoint(endpoint_id, ip, port, timeout)
    
    total = len(endpoints)
    logger.info(f"Checking {total} endpoints with timeout {timeout}s")
    
    tasks = []
    for endpoint in endpoints:
        tasks.append(_check_with_semaphore(endpoint))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    verified_count = sum(1 for r in results if not isinstance(r, Exception) and r[0])
    failed_count = sum(1 for r in results if not isinstance(r, Exception) and not r[0])
    error_count = sum(1 for r in results if isinstance(r, Exception))
    
    logger.info(f"Results: {verified_count} verified, {failed_count} failed, {error_count} errors")
    
    return verified_count, failed_count, error_count

# Main pruning function with batch processing
async def prune_endpoints_batch():
    """Main function to prune endpoints using batch processing"""
    if args.retest_all:
        logger.info("Retesting ALL endpoints regardless of current status")
    logger.info(f"Starting pruning with input_status={args.input_status}, output_status={args.output_status}, fail_status={args.fail_status}")
    
    # Check if this is a dry run
    if args.dry_run:
        logger.info(f"DRY RUN: Would check endpoints")
        return 0, 0, 0
    
    # Get total endpoints count
    total_endpoints = await count_endpoints_to_prune()
    
    if total_endpoints == 0:
        logger.info(f"No endpoints found with status '{args.input_status}'")
        return 0, 0, 0
    
    logger.info(f"Found {total_endpoints} endpoints to check")
    
    # Apply limit if specified
    if args.limit > 0 and args.limit < total_endpoints:
        total_endpoints = args.limit
        logger.info(f"Limited to {total_endpoints} endpoints per user request")
    
    # Calculate number of batches
    batch_size = min(args.batch_size, MAX_CONCURRENT_REQUESTS * 5)
    num_batches = (total_endpoints + batch_size - 1) // batch_size
    
    logger.info(f"Processing {total_endpoints} endpoints in {num_batches} batches of {batch_size}")
    
    # Track totals
    total_verified = 0
    total_failed = 0
    total_errors = 0
    
    # Process in batches
    for batch_num in range(num_batches):
        offset = batch_num * batch_size
        remaining = min(batch_size, total_endpoints - offset)
        
        logger.info(f"Processing batch {batch_num+1}/{num_batches} (offset {offset}, size {remaining})")
        
        # Get batch of endpoints
        endpoints = await get_endpoints_to_prune(batch_size=remaining, offset=offset)
        
        if not endpoints:
            logger.warning(f"No endpoints returned for batch {batch_num+1}")
            continue
        
        # Check endpoints in this batch
        verified_count, failed_count, error_count = await check_endpoints(
            endpoints, 
            timeout=args.timeout,
            max_concurrent=args.workers
        )
        
        # Update totals
        total_verified += verified_count
        total_failed += failed_count
        total_errors += error_count
        
        logger.info(f"Batch {batch_num+1} completed: {verified_count} verified, {failed_count} failed, {error_count} errors")
        
        # Slight delay between batches to avoid overwhelming the system
        if batch_num < num_batches - 1:
            await asyncio.sleep(1)
    
    # Update metadata
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if DATABASE_TYPE == "postgres":
        # Record statistics in metadata
        total_verified_endpoints = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE verified = 1")[0]
        total_failed_endpoints = Database.fetch_one("SELECT COUNT(*) FROM endpoints WHERE verified = 0")[0]
        
        # Update metadata
        Database.execute(
            "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s",
            ('last_prune_end', now, now, now, now)
        )
        
        Database.execute(
            "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s",
            ('verified_count', str(total_verified_endpoints), now, str(total_verified_endpoints), now)
        )
        
        Database.execute(
            "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s",
            ('failed_count', str(total_failed_endpoints), now, str(total_failed_endpoints), now)
        )
    
    logger.info(f"Pruning completed: {total_verified} verified, {total_failed} failed, {total_errors} errors")
    
    return total_verified, total_failed, total_errors

# Command line interface
def main():
    global args
    
    # Initialize database
    init_database()
    
    parser = argparse.ArgumentParser(description="Prune Ollama endpoints in the database")
    parser.add_argument('--input-status', default='scanned', help='Status of endpoints to process')
    parser.add_argument('--output-status', default='verified', help='Status to assign to working endpoints')
    parser.add_argument('--fail-status', default='failed', help='Status to assign to non-working endpoints')
    parser.add_argument('--force', action='store_true', help='Process all endpoints regardless of current status')
    parser.add_argument('--retest-all', action='store_true', help='Retest ALL endpoints regardless of previous status, oldest verification first')
    parser.add_argument('--timeout', type=int, default=TIMEOUT, help=f"Connection timeout in seconds (default: {TIMEOUT})")
    parser.add_argument('--workers', type=int, default=MAX_CONCURRENT_REQUESTS, help=f"Maximum concurrent workers (default: {MAX_CONCURRENT_REQUESTS})")
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help=f"Number of endpoints to process in each batch (default: {BATCH_SIZE})")
    parser.add_argument('--limit', type=int, default=0, help="Limit the number of endpoints to process (default: 0 = all)")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done without making changes")
    parser.add_argument('--verbose', '-v', action='store_true', help="Enable verbose output")
    parser.add_argument('--debug-endpoint', help='Debug a specific endpoint (format: IP:PORT)')
    parser.add_argument('--debug-response', action='store_true', help='Save full response content to a debug file')
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Check if we should test a specific endpoint
    if args.debug_endpoint:
        try:
            ip, port = args.debug_endpoint.split(':')
            port = int(port)
            logger.info(f"DEBUG MODE: Testing specific endpoint {ip}:{port}")
            
            # Find endpoint in the database
            endpoint_info = Database.fetch_one(
                "SELECT id, verified, is_honeypot, honeypot_reason FROM endpoints WHERE ip = %s AND port = %s", 
                (ip, str(port))
            )
            
            if endpoint_info:
                endpoint_id, verified, is_honeypot, reason = endpoint_info
                logger.info(f"Found endpoint ID: {endpoint_id}, verified: {verified}, is_honeypot: {is_honeypot}, reason: {reason}")
                
                # Test the endpoint
                success, result = asyncio.run(check_endpoint(endpoint_id, ip, port, timeout=args.timeout))
                
                # Get updated status
                updated_info = Database.fetch_one(
                    "SELECT id, verified, is_honeypot, honeypot_reason FROM endpoints WHERE ip = %s AND port = %s", 
                    (ip, str(port))
                )
                
                if updated_info:
                    _, new_verified, new_is_honeypot, new_reason = updated_info
                    logger.info(f"Updated status: verified={new_verified}, is_honeypot={new_is_honeypot}, reason={new_reason}")
                
                logger.info(f"Test result: {success}, reason: {result}")
                print(f"\nDebug Test Summary:")
                print(f"- Endpoint: {ip}:{port} (ID: {endpoint_id})")
                print(f"- Original status: verified={verified}, is_honeypot={is_honeypot}")
                print(f"- Updated status: verified={new_verified}, is_honeypot={new_is_honeypot}")
                print(f"- Test result: {'SUCCESS' if success else 'FAILED'}")
                print(f"- Reason: {result}")
                
                return 0
            else:
                logger.error(f"Endpoint {ip}:{port} not found in database")
                print(f"\nERROR: Endpoint {ip}:{port} not found in database")
                return 1
        except ValueError:
            logger.error(f"Invalid endpoint format: {args.debug_endpoint}. Use IP:PORT format.")
            print(f"\nERROR: Invalid endpoint format: {args.debug_endpoint}. Use IP:PORT format.")
            return 1
        except Exception as e:
            logger.error(f"Error testing endpoint {args.debug_endpoint}: {str(e)}")
            print(f"\nERROR: Failed to test endpoint: {str(e)}")
            return 1
    
    # Record start time in metadata
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if DATABASE_TYPE == "postgres":
        Database.execute(
            "INSERT INTO metadata (key, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s",
            ('last_prune_start', now, now, now, now)
        )
    
    # Run the pruning process with batch processing
    verified_count, failed_count, error_count = asyncio.run(prune_endpoints_batch())
    
    print(f"\nPruning Summary:")
    print(f"- Verified endpoints: {verified_count}")
    print(f"- Failed endpoints: {failed_count}")
    print(f"- Errors: {error_count}")
    
    if args.dry_run:
        print("\nNOTE: This was a dry run. No changes were made to the database.")
        
    return 0

if __name__ == "__main__":
    main() 