# Enhanced Honeypot Detection Implementation Plan

## 1. Update the `is_likely_honeypot_response` Function

### 1.1 Add Detection for Log Outputs Containing Timestamps and Log Levels

```python
# Update the honeypot_indicators list to include log format patterns
honeypot_indicators = [
    # ... existing indicators ...
    
    # Common log indicators
    "[INFO]", "[DEBUG]", "[ERROR]", "[WARNING]", 
    "INFO:", "DEBUG:", "ERROR:", "WARNING:",
]

# Add timestamp pattern detection
timestamp_patterns = [
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',  # ISO format: 2023-01-01 12:34:56
    r'\d{2}/\d{2}/\d{4}',  # Date format: 01/02/2023
    r'\d{2}:\d{2}:\d{2}\.\d+',  # Time with milliseconds: 12:34:56.789
]

for pattern in timestamp_patterns:
    if re.search(pattern, text):
        logger.debug(f"Timestamp pattern found in response: '{pattern}'")
        return True
```

### 1.2 Look for Tokens, PostgreSQL Connection Strings, and Sensitive Info

```python
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
```

### 1.3 Improve Gibberish Detection

```python
# Improve gibberish detection, especially for responses mixing real and gibberish content
# Keep tracking examples of gibberish words for debugging
gibberish_words = []

# Check for gibberish/random text followed by normal text (a common pattern)
if len(text) > 100:
    # Split into first and second half
    first_half = text[:len(text)//2]
    second_half = text[len(text)//2:]
    
    # If first half is mostly gibberish and second half has normal words
    if has_high_gibberish_ratio(first_half) and not has_high_gibberish_ratio(second_half):
        logger.debug("Honeypot pattern detected: gibberish followed by normal text")
        return True
        
# Enhanced check for mixed content in sections
sections = re.split(r'[.!?\n]+', text)
mixed_content_sections = 0

for section in sections:
    if len(section.strip()) < 10:
        continue
    
    # Check for sections with mixed gibberish and normal text
    words = section.strip().split()
    if words:
        gibberish_words_in_section = sum(1 for word in words 
            if (len(word) > 7 and all(c.isalpha() for c in word) and not has_vowels(word))
            or (len(word) > 8 and sum(1 for c in word if c.isdigit()) > 1 
                and sum(1 for c in word if c.isalpha()) > 1))
        
        # If we have some gibberish words but not all words are gibberish
        if 0 < gibberish_words_in_section < len(words):
            mixed_content_sections += 1

# If we have multiple sections with mixed content, it's likely a honeypot
if mixed_content_sections >= 2 or (len(sections) > 0 and mixed_content_sections / len(sections) > 0.25):
    logger.debug(f"Honeypot detected: {mixed_content_sections} sections with mixed gibberish and normal content")
    return True
```

## 2. Implement Detection for Delayed Honeypot Behavior

### 2.1 Add Database Schema for Tracking Response History

```sql
-- Create new table for tracking verification responses over time
CREATE TABLE IF NOT EXISTS endpoint_verifications (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER REFERENCES endpoints(id),
    verification_date TIMESTAMP DEFAULT NOW(),
    response_sample TEXT,
    detected_models TEXT[],
    is_honeypot BOOLEAN DEFAULT FALSE,
    response_metrics JSONB,
    UNIQUE (endpoint_id, verification_date)
);
```

### 2.2 Update the Endpoint Check Function to Record Responses

```python
# In the check_endpoint function, after we get a response:
try:
    # Save the response for future comparison
    response_metrics = {
        "length": len(response_text),
        "gibberish_ratio": gibberish_ratio,
        "word_count": len(words)
    }
    
    Database.execute("""
        INSERT INTO endpoint_verifications 
        (endpoint_id, verification_date, response_sample, detected_models, is_honeypot, response_metrics)
        VALUES (%s, NOW(), %s, %s, %s, %s)
    """, (endpoint_id, response_text[:500], json.dumps([m.get("name", "") for m in models]), 
          is_honeypot, json.dumps(response_metrics)))
except Exception as e:
    logger.warning(f"Failed to record verification data: {e}")
```

### 2.3 Implement Comparison with Previous Responses

```python
# Add function to detect behavior changes over time
def detect_behavior_change(endpoint_id, current_response):
    """
    Check if an endpoint's behavior has changed significantly since last verification
    Returns (changed, reason) tuple
    """
    # Get the most recent verification record
    previous = Database.fetch_one("""
        SELECT response_sample, response_metrics, verification_date
        FROM endpoint_verifications
        WHERE endpoint_id = %s AND verification_date < NOW() - INTERVAL '1 day'
        ORDER BY verification_date DESC
        LIMIT 1
    """, (endpoint_id,))
    
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
```

## 3. Fix Issue with the Specific Endpoint (15.168.9.113:3749)

### 3.1 Update the Check Process to Test Multiple Prompts

```python
# In the check_endpoint function, modify to test multiple prompts
# Test with multiple prompts for more reliable detection
prompts = [
    "Say hello in one short sentence",
    "What is your name?",
    "Tell me about yourself"
]

honeypot_detections = 0
all_responses = []

for i, prompt in enumerate(prompts):
    # Only test max 3 prompts to avoid overloading
    if i >= 3:
        break
        
    # ... send request with this prompt ...
    
    all_responses.append(response_text)
    if is_likely_honeypot_response(response_text):
        honeypot_detections += 1
        
# If the majority of prompts trigger detection, mark as honeypot
if len(all_responses) > 0 and honeypot_detections / len(all_responses) >= 0.5:
    reason = f"Response appears to be from a honeypot ({honeypot_detections}/{len(all_responses)} prompts triggered detection)"
    logger.warning(f"Endpoint {ip}:{port} likely honeypot - Detection ratio: {honeypot_detections/len(all_responses):.2f}")
    mark_endpoint_as_honeypot(endpoint_id, reason)
    return False, reason
```

### 3.2 Add Debugging Options to the Script

```python
# Add a debug flag to the script
parser.add_argument('--debug-endpoint', help='Test a specific endpoint (format: IP:PORT)')
parser.add_argument('--debug-response', action='store_true', help='Save full response content to debug file')

# In the main function, check for debug endpoint
if args.debug_endpoint:
    ip, port = args.debug_endpoint.split(':')
    logger.info(f"DEBUG MODE: Testing specific endpoint {ip}:{port}")
    endpoint_info = Database.fetch_one(
        "SELECT id, verified, is_honeypot FROM endpoints WHERE ip = %s AND port = %s", 
        (ip, port)
    )
    
    if endpoint_info:
        endpoint_id, verified, is_honeypot = endpoint_info
        logger.info(f"Found endpoint ID: {endpoint_id}, verified: {verified}, is_honeypot: {is_honeypot}")
        success, reason = asyncio.run(check_endpoint(endpoint_id, ip, int(port), timeout=args.timeout))
        logger.info(f"Test result: {success}, reason: {reason}")
    else:
        logger.error(f"Endpoint {ip}:{port} not found in database")
    return
```

## 4. Integration Plan

1. Implement the enhanced detection functions
2. Update database schema if needed
3. Add debug mode options to the script
4. Test with known problem endpoints
5. Run a small batch of tests against the database
6. Update documentation
7. Deploy changes to production

## 5. Validation Plan

1. Test against known honeypots to ensure they're properly detected
2. Test against legitimate endpoints to avoid false positives
3. Specifically test against the endpoint 15.168.9.113:3749
4. Compare performance of the original and enhanced detection functions
5. Monitor detection rates after deployment 