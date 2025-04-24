# Implementation Plan: Scanner-Pruner-Bot Integration

## 1. Database Schema Reference

### 1.1 PostgreSQL Tables

```sql
-- servers table
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 11434,
    status VARCHAR(50) DEFAULT 'scanned',
    scan_date TIMESTAMP DEFAULT NOW(),
    verified_date TIMESTAMP,
    UNIQUE(ip, port)
);

-- models table
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    params VARCHAR(50),
    quant VARCHAR(50),
    size BIGINT,
    count INTEGER DEFAULT 0,
    UNIQUE(name, server_id)
);

-- metadata table
CREATE TABLE IF NOT EXISTS metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 1.2 Status Values

- `scanned`: Endpoint discovered by scanner but not verified
- `verified`: Endpoint verified as working by pruner
- `failed`: Endpoint failed verification

## 2. Scanner Implementation (`run_scanner.sh`)

### 2.1 Environment Variable Handling

```bash
# Load environment variables for PostgreSQL
if [ -f ".env" ]; then
    source <(grep -v '^#' ".env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Set default variables if not defined
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"
```

### 2.2 Command-Line Parameters

```bash
# Default values
STATUS="scanned"
PRESERVE_VERIFIED=true
LIMIT=0
NETWORK="0.0.0.0/0"
WORKERS=5
TIMEOUT=10

# Process command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --status)
            STATUS="$2"
            shift 2
            ;;
        --no-preserve-verified)
            PRESERVE_VERIFIED=false
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --network)
            NETWORK="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done
```

### 2.3 Database Metadata Recording

```bash
# Record scan start time in metadata
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording scanner start in PostgreSQL metadata..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_scan_start', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
fi
```

### 2.4 Command Execution

```bash
# Build scanner command with parameters
CMD="python ./ollama_scanner.py --status ${STATUS}"

if [ "$PRESERVE_VERIFIED" = true ]; then
    CMD="${CMD} --preserve-verified"
fi

if [ "$LIMIT" -gt 0 ]; then
    CMD="${CMD} --limit ${LIMIT}"
fi

CMD="${CMD} --network ${NETWORK} --workers ${WORKERS} --timeout ${TIMEOUT}"

# Execute scanner
echo "Starting scanner with command: ${CMD}"
${CMD}
```

### 2.5 Post-Scan Metadata Update

```bash
# Update metadata after scan completes
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording scan completion and statistics..."
    
    # Update scan end time
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_scan_end', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
    
    # Update scanned count
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('scanned_count', (SELECT COUNT(*) FROM servers WHERE status='scanned')::text, NOW()) ON CONFLICT (key) DO UPDATE SET value = (SELECT COUNT(*) FROM servers WHERE status='scanned')::text, updated_at = NOW();"
fi
```

## 3. Scanner Script Requirements (`ollama_scanner.py`)

### 3.1 New Command-Line Arguments

```python
parser.add_argument('--status', default='scanned', help='Status to assign to discovered endpoints')
parser.add_argument('--preserve-verified', action='store_true', help='Preserve verified status for existing endpoints')
parser.add_argument('--network', default='0.0.0.0/0', help='Network range to scan')
parser.add_argument('--workers', type=int, default=5, help='Number of worker processes')
parser.add_argument('--timeout', type=int, default=10, help='Connection timeout in seconds')
parser.add_argument('--limit', type=int, default=0, help='Maximum number of endpoints to scan (0 = unlimited)')
```

### 3.2 Database Connection Function

```python
async def get_db_connection():
    """Establish database connection based on environment variables"""
    db_type = os.environ.get('DATABASE_TYPE', 'postgres')
    
    if db_type == 'postgres':
        return await asyncpg.connect(
            host=os.environ.get('POSTGRES_HOST', 'localhost'),
            port=os.environ.get('POSTGRES_PORT', 5432),
            database=os.environ.get('POSTGRES_DB', 'ollama_scanner'),
            user=os.environ.get('POSTGRES_USER', 'ollama'),
            password=os.environ.get('POSTGRES_PASSWORD', '')
        )
    else:  # Fallback to SQLite
        # Note: This would need sqlite-specific code
        pass
```

### 3.3 Endpoint Insert Query

```python
async def insert_endpoint(conn, ip, port, status):
    """Insert or update endpoint in database with proper status handling"""
    if args.preserve_verified:
        # Preserve verified status if enabled
        await conn.execute('''
            INSERT INTO servers (ip, port, status, scan_date) 
            VALUES ($1, $2, $3, NOW()) 
            ON CONFLICT (ip, port) DO UPDATE 
            SET status = CASE WHEN servers.status = 'verified' THEN servers.status ELSE $3 END,
                scan_date = NOW()
        ''', ip, port, status)
    else:
        # Always update status
        await conn.execute('''
            INSERT INTO servers (ip, port, status, scan_date) 
            VALUES ($1, $2, $3, NOW()) 
            ON CONFLICT (ip, port) DO UPDATE 
            SET status = $3, scan_date = NOW()
        ''', ip, port, status)
```

## 4. Pruner Implementation (`run_pruner.sh`)

### 4.1 Environment Variable Handling

```bash
# Load environment variables for PostgreSQL
if [ -f "${DISCORDBOT_DIR}/.env" ]; then
    source <(grep -v '^#' "${DISCORDBOT_DIR}/.env" | sed -E 's/(.*)=(.*)/export \1=\2/')
    echo "Loaded environment variables from .env file"
fi

# Set default variables if not defined
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ollama_scanner}"
POSTGRES_USER="${POSTGRES_USER:-ollama}"
```

### 4.2 New Command-Line Parameters

```bash
# Default values
INPUT_STATUS="scanned"
OUTPUT_STATUS="verified"
FAIL_STATUS="failed" 
LIMIT=0
WORKERS=5
DRY_RUN=false
FORCE=false
HONEYPOT_CHECK=true
SAFETY_THRESHOLD=0.5
MAX_RUNTIME=0

# Process arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --input-status)
            INPUT_STATUS="$2"
            shift 2
            ;;
        --output-status)
            OUTPUT_STATUS="$2"
            shift 2
            ;;
        --fail-status)
            FAIL_STATUS="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --no-honeypot-check)
            HONEYPOT_CHECK=false
            shift
            ;;
        --safety-threshold)
            SAFETY_THRESHOLD="$2"
            shift 2
            ;;
        --max-runtime)
            MAX_RUNTIME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            shift
            ;;
    esac
done
```

### 4.3 Database Metadata Recording

```bash
# Record pruner start in metadata
if [ "$DATABASE_TYPE" = "postgres" ]; then
    echo "Recording pruner start in PostgreSQL metadata..."
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "INSERT INTO metadata (key, value, updated_at) VALUES ('last_prune_start', NOW(), NOW()) ON CONFLICT (key) DO UPDATE SET value = NOW(), updated_at = NOW();"
fi
```

### 4.4 Command Execution

```bash
# Build pruner command with parameters
CMD="python ${PRUNER_SCRIPT}"

CMD="${CMD} --input-status ${INPUT_STATUS}"
CMD="${CMD} --output-status ${OUTPUT_STATUS}"
CMD="${CMD} --fail-status ${FAIL_STATUS}"

if [ "$LIMIT" -gt 0 ]; then
    CMD="${CMD} --limit ${LIMIT}"
fi

CMD="${CMD} --workers ${WORKERS}"

if [ "$DRY_RUN" = true ]; then
    CMD="${CMD} --dry-run"
fi

if [ "$FORCE" = true ]; then
    CMD="${CMD} --force"
fi

if [ "$HONEYPOT_CHECK" = false ]; then
    CMD="${CMD} --honeypot-check false"
fi

CMD="${CMD} --safety-threshold ${SAFETY_THRESHOLD}"

# Execute pruner
echo "Starting pruner with command: ${CMD}"
${CMD}
```

## 5. Pruner Script Requirements (`prune_bad_endpoints.py`)

### 5.1 New Command-Line Arguments

```python
parser.add_argument('--input-status', default='scanned', help='Status of endpoints to process')
parser.add_argument('--output-status', default='verified', help='Status to assign to working endpoints')
parser.add_argument('--fail-status', default='failed', help='Status to assign to non-working endpoints')
parser.add_argument('--force', action='store_true', help='Process all endpoints regardless of current status')
```

### 5.2 Database Query to Get Endpoints

```python
async def get_endpoints_to_prune(conn):
    """Get endpoints that need pruning based on status"""
    if args.force:
        # Process all endpoints if force is enabled
        return await conn.fetch('''
            SELECT id, ip, port, status FROM servers
            ORDER BY scan_date
            LIMIT $1
        ''', args.limit if args.limit > 0 else None)
    else:
        # Only process endpoints with input_status
        return await conn.fetch('''
            SELECT id, ip, port, status FROM servers
            WHERE status = $1
            ORDER BY scan_date
            LIMIT $2
        ''', args.input_status, args.limit if args.limit > 0 else None)
```

### 5.3 Status Update Functions

```python
async def mark_endpoint_verified(conn, server_id, ip, port):
    """Mark endpoint as verified"""
    await conn.execute('''
        UPDATE servers
        SET status = $1, verified_date = NOW()
        WHERE id = $2
    ''', args.output_status, server_id)
    print(f"Endpoint {ip}:{port} verified successfully")

async def mark_endpoint_failed(conn, server_id, ip, port, reason=None):
    """Mark endpoint as failed"""
    await conn.execute('''
        UPDATE servers
        SET status = $1
        WHERE id = $2
    ''', args.fail_status, server_id)
    print(f"Endpoint {ip}:{port} failed verification: {reason}")
```

### 5.4 Model Processing

```python
async def process_models_for_endpoint(conn, server_id, ip, port):
    """Process models for a verified endpoint"""
    # Get models from Ollama API
    # For each model found:
    await conn.execute('''
        INSERT INTO models (name, server_id, params, quant, size)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (name, server_id) DO UPDATE
        SET params = $3, quant = $4, size = $5
    ''', model_name, server_id, params, quant, size)
```

## 6. Workflow Integration

### 6.1 Typical Usage Pattern

```bash
# 1. Run scanner to discover endpoints
./run_scanner.sh --status scanned --preserve-verified

# 2. Run pruner to verify scanned endpoints
./run_pruner.sh --input-status scanned --output-status verified --fail-status failed

# 3. Discord bot will automatically use verified endpoints
```

### 6.2 Status Update Queries

```sql
-- Get statistics for monitoring
SELECT status, COUNT(*) FROM servers GROUP BY status;

-- Get all verified endpoints with their models
SELECT s.ip, s.port, s.verified_date, m.name, m.params, m.quant
FROM servers s
JOIN models m ON s.id = m.server_id
WHERE s.status = 'verified'
ORDER BY s.verified_date DESC;
```

### 6.3 Metadata Tracking

```sql
-- Track important metadata values
INSERT INTO metadata (key, value, updated_at) 
VALUES 
  ('last_scan_date', NOW(), NOW()),
  ('last_prune_date', NOW(), NOW()),
  ('scanned_count', (SELECT COUNT(*) FROM servers WHERE status='scanned')::text, NOW()),
  ('verified_count', (SELECT COUNT(*) FROM servers WHERE status='verified')::text, NOW()),
  ('failed_count', (SELECT COUNT(*) FROM servers WHERE status='failed')::text, NOW())
ON CONFLICT (key) DO UPDATE 
SET value = EXCLUDED.value, updated_at = NOW();
```

## 7. Edge Case Handling

### 7.1 Network Errors vs. Real Failures

```python
async def verify_endpoint(ip, port):
    """Verify endpoint with retries for network issues"""
    retries = 3
    for attempt in range(retries):
        try:
            # Try to connect
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{ip}:{port}/api/tags", timeout=10) as response:
                    if response.status == 200:
                        return True, "Connection successful"
        except asyncio.TimeoutError:
            # Timeout might be temporary
            if attempt < retries - 1:
                await asyncio.sleep(2)
                continue
            return False, "Connection timeout"
        except aiohttp.ClientError as e:
            # Connection error
            return False, f"Connection error: {str(e)}"
    return False, "Failed after retries"
```

### 7.2 Honeypot Detection

```python
async def check_if_honeypot(ip, port):
    """Check if endpoint is likely a honeypot"""
    # Implement honeypot detection logic
    suspicious_signs = 0
    
    # Add checks for:
    # 1. Responds with unexpected data formats
    # 2. Always returns same response regardless of prompt
    # 3. Has unusually high number of models
    # 4. Responds too quickly
    
    if suspicious_signs >= args.honeypot_threshold:
        return True
    return False
```

### 7.3 Preservation of Verified Status

```python
# In scanner, preserve verified status when inserting new endpoints
INSERT INTO servers (ip, port, status, scan_date) 
VALUES ($1, $2, $3, NOW()) 
ON CONFLICT (ip, port) DO UPDATE 
SET status = CASE WHEN servers.status = 'verified' THEN servers.status ELSE $3 END,
    scan_date = NOW()
```

## 8. Testing and Validation

### 8.1 Scanner Output Validation

```bash
# After running scanner, check database
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT status, COUNT(*) FROM servers GROUP BY status;"
```

### 8.2 Pruner Output Validation

```bash
# After running pruner, check database
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT status, COUNT(*) FROM servers GROUP BY status;"

# Verify models were added
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT COUNT(*) FROM models;"
```

### 8.3 Discord Bot Compatibility Check

```bash
# Check that bot can read verified servers
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT s.ip, s.port, m.name FROM servers s JOIN models m ON s.id = m.server_id WHERE s.status = 'verified' LIMIT 5;"

# Check that bot cannot see unverified servers
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "SELECT COUNT(*) FROM servers WHERE status != 'verified';"
```

## 9. Additional Optimizations and Features

### 9.1 Database Performance

```sql
-- Add indexes for better query performance
CREATE INDEX idx_servers_status ON servers(status);
CREATE INDEX idx_servers_scan_date ON servers(scan_date);
CREATE INDEX idx_models_name ON models(name);
CREATE INDEX idx_models_server_id ON models(server_id);
```

### 9.2 Structured Logging

```bash
# Add to both scripts for consistent logging
LOG_FILE="${DISCORDBOT_DIR}/logs/$(date +%Y%m%d)_scanner.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Logger function
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Usage
log_message "INFO" "Scanner started with status: ${STATUS}"
log_message "ERROR" "Database connection failed"
```

### 9.3 Endpoint Quality Metrics

```python
async def calculate_endpoint_quality(conn, server_id):
    """Calculate and store quality metrics for endpoint"""
    # 1. Response time test
    start_time = time.time()
    response_success, _ = await verify_endpoint(ip, port)
    response_time = time.time() - start_time
    
    # 2. Model variety score
    models = await conn.fetch("SELECT COUNT(*) FROM models WHERE server_id = $1", server_id)
    model_count = models[0]['count']
    
    # 3. Uptime percentage calculation
    uptime_history = await conn.fetch("""
        SELECT value::jsonb FROM metadata 
        WHERE key = 'endpoint_history_' || $1
    """, server_id)
    
    # Store metrics
    await conn.execute("""
        INSERT INTO metadata (key, value, updated_at)
        VALUES ('endpoint_quality_' || $1, $2, NOW())
        ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
    """, 
    server_id, 
    json.dumps({
        'response_time': response_time,
        'model_count': model_count,
        'uptime_percentage': calculate_uptime(uptime_history),
        'last_check': datetime.now().isoformat()
    }))
```

### 9.4 Enhanced Error Handling

```bash
# Trap different signals
trap cleanup_on_error SIGHUP SIGINT SIGQUIT SIGABRT

cleanup_on_error() {
    log_message "WARNING" "Script interrupted with signal $?"
    
    # Mark any in-progress operations as failed
    if [ "$DATABASE_TYPE" = "postgres" ]; then
        PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
            -c "UPDATE metadata SET value = 'interrupted', updated_at = NOW() WHERE key = 'last_operation_status';"
    fi
    
    exit 1
}

# Function to check if previous run was interrupted
check_previous_run() {
    if [ "$DATABASE_TYPE" = "postgres" ]; then
        LAST_STATUS=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t \
            -c "SELECT value FROM metadata WHERE key = 'last_operation_status';" | xargs)
            
        if [ "$LAST_STATUS" = "interrupted" ]; then
            log_message "WARNING" "Previous run was interrupted. Running recovery procedure..."
            run_recovery_procedure
        fi
    fi
}
```

### 9.5 Security Considerations

```python
async def check_endpoint_security(ip, port):
    """Check if endpoint has security issues"""
    security_concerns = []
    
    # 1. Check for open proxy behavior
    proxy_test = await test_if_proxy(ip, port)
    if proxy_test:
        security_concerns.append("Open proxy detected")
    
    # 2. Check for authentication bypass
    auth_bypass = await test_auth_bypass(ip, port)
    if auth_bypass:
        security_concerns.append("Authentication bypass possible")
        
    # 3. Check for common vulnerabilities
    vulns = await scan_vulnerabilities(ip, port)
    security_concerns.extend(vulns)
    
    return security_concerns

# Log potentially malicious endpoints
if security_concerns:
    await conn.execute("""
        INSERT INTO metadata (key, value, updated_at)
        VALUES ('security_flag_' || $1, $2, NOW())
        ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
    """, f"{ip}:{port}", json.dumps(security_concerns))
```

### 9.6 Automatic Workflow Scheduling

```bash
# Add to crontab examples
cat << EOF > "${DISCORDBOT_DIR}/cron_jobs"
# Run scanner every 6 hours
0 */6 * * * cd ${DISCORDBOT_DIR} && ./run_scanner.sh --limit 1000

# Run pruner 30 minutes after scanner
30 */6 * * * cd ${DISCORDBOT_DIR} && ./run_pruner.sh --input-status scanned

# Daily database maintenance at 3 AM
0 3 * * * cd ${DISCORDBOT_DIR} && ./db_maintenance.sh
EOF

echo "To install cron jobs:"
echo "crontab ${DISCORDBOT_DIR}/cron_jobs"
```

### 9.7 Batch Processing for Large Datasets

```python
async def batch_process_endpoints(conn, status, batch_size=100):
    """Process endpoints in batches to avoid memory issues"""
    total_count = await conn.fetchval(
        "SELECT COUNT(*) FROM servers WHERE status = $1", status)
    
    log_message(f"Processing {total_count} endpoints with status '{status}'")
    
    for offset in range(0, total_count, batch_size):
        batch = await conn.fetch("""
            SELECT id, ip, port FROM servers 
            WHERE status = $1
            ORDER BY scan_date
            LIMIT $2 OFFSET $3
        """, status, batch_size, offset)
        
        log_message(f"Processing batch {offset//batch_size + 1} ({len(batch)} endpoints)")
        
        # Process each endpoint in the batch
        tasks = [process_endpoint(conn, row['id'], row['ip'], row['port']) for row in batch]
        await asyncio.gather(*tasks)
        
        # Commit after each batch
        log_message(f"Batch {offset//batch_size + 1} completed")
```

### 9.8 API Endpoint for Status Monitoring

```python
# Example Flask API for monitoring (run as separate service)
from flask import Flask, jsonify
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=os.environ.get('POSTGRES_PORT', 5432),
        database=os.environ.get('POSTGRES_DB', 'ollama_scanner'),
        user=os.environ.get('POSTGRES_USER', 'ollama'),
        password=os.environ.get('POSTGRES_PASSWORD', '')
    )

@app.route('/api/status')
def get_status():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get counts by status
    cursor.execute("SELECT status, COUNT(*) FROM servers GROUP BY status")
    status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
    
    # Get metadata
    cursor.execute("SELECT key, value, updated_at FROM metadata WHERE key LIKE 'last_%'")
    metadata = {row['key']: {'value': row['value'], 'updated_at': row['updated_at'].isoformat()} 
               for row in cursor.fetchall()}
    
    conn.close()
    
    return jsonify({
        'status_counts': status_counts,
        'metadata': metadata,
        'server_time': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### 9.9 Recovery Procedure

```bash
# Create recovery script (db_recovery.sh)
#!/bin/bash
# This script repairs database after interrupted operations

echo "Running database recovery procedure..."

if [ "$DATABASE_TYPE" = "postgres" ]; then
    # Reset in-progress operations
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "UPDATE servers SET status = 'failed' WHERE status = 'processing';"
    
    # Mark operation as completed
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "UPDATE metadata SET value = 'completed', updated_at = NOW() WHERE key = 'last_operation_status';"
    
    echo "Recovery completed successfully"
fi
```

### 9.10 Support for Model-Specific Verification

```python
async def verify_model_compatibility(ip, port, model_name):
    """Verify specific model compatibility by testing inference"""
    try:
        async with aiohttp.ClientSession() as session:
            # Basic prompt to test model functionality
            payload = {
                "model": model_name,
                "prompt": "Hello, are you working properly?",
                "stream": False
            }
            
            async with session.post(
                f"http://{ip}:{port}/api/generate", 
                json=payload,
                timeout=30
            ) as response:
                if response.status != 200:
                    return False, f"API returned status {response.status}"
                
                result = await response.json()
                if "response" in result and len(result["response"]) > 0:
                    return True, "Model responded correctly"
                return False, "Empty or invalid response"
                
    except Exception as e:
        return False, f"Error testing model: {str(e)}"
``` 