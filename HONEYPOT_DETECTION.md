# Enhanced Honeypot Detection for Ollama Scanner

This document describes the enhanced honeypot detection system implemented in the Ollama Scanner. The system has been improved to better detect both obvious and more sophisticated honeypots that might mimic legitimate Ollama endpoints.

## Overview of Enhancements

The honeypot detection system has been enhanced in several ways:

1. **Improved Single-Sample Detection**: Better detection of honeypots based on individual responses
2. **Multi-Sample Testing**: Testing with multiple prompts for more reliable detection
3. **Historical Behavior Tracking**: Detection of endpoints that start legitimate but later become honeypots
4. **Debugging and Analysis Tools**: More tools to investigate suspicious endpoints

## 1. Enhanced Honeypot Detection

### 1.1 Improved Pattern Recognition

The `is_likely_honeypot_response` function has been enhanced to detect:

- **Log Outputs**: Detects responses containing log formats, timestamps, and log levels
- **Sensitive Information**: Identifies exposed credentials, tokens, and connection strings
- **Improved Gibberish Detection**: Better analysis of responses mixing real and gibberish content
- **Mixed Content Sections**: Identifies sections that mix legitimate text with gibberish

### 1.2 Multi-Prompt Testing

The system now tests each endpoint with multiple prompts:

```python
prompts = [
    "Say hello in one short sentence",
    "What is your name?",
    "Tell me about yourself"
]
```

If the majority of responses (≥ 50%) are flagged as suspicious, the endpoint is marked as a honeypot. This dramatically reduces false positives and false negatives.

## 2. Delayed Honeypot Detection

### 2.1 Schema and Data Collection

A new database table `endpoint_verifications` tracks endpoint responses over time:

```sql
CREATE TABLE endpoint_verifications (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER REFERENCES endpoints(id),
    verification_date TIMESTAMP DEFAULT NOW(),
    response_sample TEXT,
    detected_models JSONB,
    is_honeypot BOOLEAN DEFAULT FALSE,
    response_metrics JSONB,
    UNIQUE (endpoint_id, verification_date)
);
```

The `response_metrics` field contains:
- Response length
- Gibberish ratio
- Word count

### 2.2 Behavior Change Detection

The `detect_behavior_change` function compares current responses with historical data to identify:

- Significant increases in gibberish content
- Major changes in response length
- Text content changing significantly between verifications

If an endpoint's behavior changes substantially AND the new behavior resembles a honeypot, it's flagged as a "delayed honeypot."

## 3. Components and Usage

### 3.1 Installing Database Schema

Run `add_endpoint_verification_history.py` to add the necessary tables:

```bash
python add_endpoint_verification_history.py
```

Or use the `--dry-run` flag to preview changes:

```bash
python add_endpoint_verification_history.py --dry-run
```

### 3.2 The Main Pruner with Enhanced Detection

The main `prune_bad_endpoints.py` script has been enhanced with:

- Improved honeypot detection algorithms
- Multi-prompt testing
- Response history recording (if the endpoint_verifications table exists)
- Debug endpoint mode to test specific IPs

Example usage:

```bash
# Regular pruning with enhanced detection
python prune_bad_endpoints.py --retest-all

# Debug a specific endpoint
python prune_bad_endpoints.py --debug-endpoint 15.168.9.113:3749 --verbose
```

### 3.3 Delayed Honeypot Detector

The `delayed_honeypot_detector.py` script specifically checks for endpoints that have changed behavior:

```bash
# Scan verified endpoints that haven't been checked in the last 7 days
python delayed_honeypot_detector.py --days 7 --limit 100

# Test a specific endpoint for behavior changes
python delayed_honeypot_detector.py --test-endpoint 15.168.9.113:3749 --verbose
```

### 3.4 Advanced Analysis Tools

The `test_specific_pruner.py` script provides detailed analysis for suspicious endpoints:

```bash
python test_specific_pruner.py --ip 15.168.9.113 --port 3749 --verbose
```

## 4. Example Honeypot Patterns

Common honeypot responses include:

1. **Log Output Leakage**:
   ```
   2023-04-22 12:34:56 [INFO] Received request from 1.2.3.4
   ```

2. **Gibberish Text**:
   ```
   a7izgz6n6a2 y7coiarlqp4cf gkjz hua0a3i7d2ulf la1zax13riqw
   ```

3. **API Debugging Output**:
   ```
   Using Model: llama2:7b
   Sending prompt: Say hello
   ```

4. **Sensitive Information**:
   ```
   Connected to postgres://user:password@db.example.com:5432/ollama
   ```

## 5. Implementation Notes

### 5.1 Configuration Options

The detection system can be configured using command-line arguments:

- `--timeout`: Connection timeout (seconds)
- `--workers`: Maximum concurrent workers
- `--batch-size`: Batch size for processing
- `--verbose`: Enable detailed logging
- `--debug-endpoint`: Test a specific endpoint

### 5.2 Detection Thresholds

The system uses several thresholds that can be adjusted:

- **Gibberish Ratio**: Text with > 30% gibberish words is flagged
- **Honeypot Detection Ratio**: If ≥ 50% of prompts trigger detection, the endpoint is marked as honeypot
- **Behavior Change Similarity**: Text with < 30% similarity to previous responses indicates a change

## 6. Future Enhancements

Potential future improvements:

1. **Machine Learning Models**: Train ML models to detect honeypots based on response patterns
2. **Community Database**: Share known honeypot signatures across instances
3. **Response Content Analysis**: Deeper semantic analysis of generated text
4. **Automated Continuous Monitoring**: Regular checks of verified endpoints

## 7. Troubleshooting

### Common Issues

1. **False Positives**: If legitimate endpoints are being flagged, try:
   - Decreasing the gibberish ratio threshold
   - Increasing the number of test prompts
   - Using more specialized prompts for the domain

2. **False Negatives**: If honeypots are not being detected, try:
   - Increasing the gibberish ratio threshold
   - Adding more pattern detection rules
   - Using the dedicated test scripts for deeper analysis

### Logs

Detailed logs are available in:
- `prune_endpoints.log`: Main pruning log
- `specific_endpoint_test.log`: Detailed endpoint analysis log 
- `delayed_honeypot_detector.log`: Behavior change detection log
- `db_schema_update.log`: Database schema changes log

## 8. Case Study: 15.168.9.113:3749

The endpoint at 15.168.9.113:3749 was previously verified but is actually a honeypot. The enhanced detection system successfully identified it with the following observations:

1. **Response Pattern**: All responses consisted primarily of gibberish text
2. **Gibberish Ratio**: ~60% of words were identified as gibberish
3. **Multi-Prompt Testing**: 3/3 test prompts triggered honeypot detection
4. **Consistent Pattern**: All responses showed the same pattern of randomized alphanumeric strings

With the new system, this endpoint is now correctly identified as a honeypot. 