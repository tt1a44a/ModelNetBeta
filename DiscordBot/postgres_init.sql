-- PostgreSQL schema for Ollama Scanner
-- This file defines the database schema for the Ollama Scanner application

-- Create extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Drop existing tables if they exist (for clean initialization)
DROP TABLE IF EXISTS models CASCADE;
DROP TABLE IF EXISTS verified_endpoints CASCADE;
DROP TABLE IF EXISTS endpoints CASCADE;
DROP TABLE IF EXISTS benchmark_results CASCADE;
DROP VIEW IF EXISTS servers CASCADE;

-- Create endpoints table (main table for discovered endpoints)
CREATE TABLE endpoints (
    id SERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    scan_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    verified INTEGER DEFAULT 0,  -- 0 = unverified, 1 = verified, 2 = invalid/pruned
    verification_date TIMESTAMP WITH TIME ZONE,
    is_honeypot BOOLEAN DEFAULT FALSE,
    honeypot_reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    inactive_reason TEXT,
    last_check_date TIMESTAMP WITH TIME ZONE,
    UNIQUE(ip, port)
);

-- Create index on IP for faster searching
CREATE INDEX endpoints_ip_idx ON endpoints(ip);
CREATE INDEX endpoints_verified_idx ON endpoints(verified);
CREATE INDEX idx_endpoints_honeypot ON endpoints(is_honeypot);
CREATE INDEX idx_endpoints_active ON endpoints(is_active);
CREATE INDEX idx_endpoints_verified_honeypot ON endpoints(verified, is_honeypot);
CREATE INDEX idx_endpoints_verified_active ON endpoints(verified, is_active);

-- Create verified_endpoints table for valid endpoints
CREATE TABLE verified_endpoints (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    verification_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    UNIQUE(endpoint_id)
);

-- Create index on endpoint_id for faster joins
CREATE INDEX verified_endpoints_endpoint_id_idx ON verified_endpoints(endpoint_id);

-- Create models table
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    parameter_size TEXT,
    quantization_level TEXT,
    size_mb NUMERIC(12, 2),
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    UNIQUE(endpoint_id, name)
);

-- Create index on endpoint_id and model name
CREATE INDEX models_endpoint_id_idx ON models(endpoint_id);
CREATE INDEX models_name_idx ON models(name);

-- Create benchmark_results table
CREATE TABLE benchmark_results (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    model_id INTEGER,
    test_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    avg_response_time NUMERIC(10, 4),
    tokens_per_second NUMERIC(10, 4),
    first_token_latency NUMERIC(10, 4),
    throughput_tokens NUMERIC(10, 4),
    throughput_time NUMERIC(10, 4),
    context_500_tps NUMERIC(10, 4),
    context_1000_tps NUMERIC(10, 4),
    context_2000_tps NUMERIC(10, 4),
    max_concurrent_requests INTEGER,
    concurrency_success_rate NUMERIC(5, 4),
    concurrency_avg_time NUMERIC(10, 4),
    success_rate NUMERIC(5, 4),
    FOREIGN KEY (endpoint_id) REFERENCES endpoints (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models (id) ON DELETE SET NULL
);

-- Create view for backward compatibility with existing code
CREATE VIEW servers AS
SELECT 
    e.id, 
    e.ip, 
    e.port, 
    e.scan_date
FROM 
    endpoints e
JOIN
    verified_endpoints ve ON e.id = ve.endpoint_id;

-- Create function to automatically update scan_date when updating endpoints
CREATE OR REPLACE FUNCTION update_scan_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.scan_date = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update scan_date
CREATE TRIGGER update_endpoint_scan_date
BEFORE UPDATE ON endpoints
FOR EACH ROW
WHEN (OLD.ip IS DISTINCT FROM NEW.ip OR OLD.port IS DISTINCT FROM NEW.port)
EXECUTE FUNCTION update_scan_date();

-- Create function to automatically update verification_date
CREATE OR REPLACE FUNCTION update_verification_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.verification_date = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update verification_date
CREATE TRIGGER update_endpoint_verification_date
BEFORE UPDATE ON endpoints
FOR EACH ROW
WHEN (OLD.verified IS DISTINCT FROM NEW.verified)
EXECUTE FUNCTION update_verification_date();

-- Create indexes for performance optimization
CREATE INDEX benchmark_results_endpoint_id_idx ON benchmark_results(endpoint_id);
CREATE INDEX benchmark_results_model_id_idx ON benchmark_results(model_id);
CREATE INDEX benchmark_results_test_date_idx ON benchmark_results(test_date);

-- Create metadata table for storing configuration values and statistics
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on metadata key for faster lookups
CREATE INDEX metadata_key_idx ON metadata(key);

-- Initialize default metadata values
INSERT INTO metadata (key, value, updated_at) 
VALUES 
('server_count', '0', CURRENT_TIMESTAMP),
('model_count', '0', CURRENT_TIMESTAMP),
('verified_server_count', '0', CURRENT_TIMESTAMP),
('last_sync', CURRENT_TIMESTAMP::text, CURRENT_TIMESTAMP)
ON CONFLICT (key) DO NOTHING;

-- Create schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial schema version
INSERT INTO schema_version (version) VALUES ('1.0.0');

-- Grant permissions to the ollama user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ollama;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ollama; 