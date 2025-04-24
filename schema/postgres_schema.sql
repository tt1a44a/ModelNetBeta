-- PostgreSQL schema for Ollama Scanner
-- This file defines the new database schema for the Scanner-Pruner-Bot Integration

-- Create extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create servers table
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 11434,
    status VARCHAR(50) DEFAULT 'scanned',
    scan_date TIMESTAMP DEFAULT NOW(),
    verified_date TIMESTAMP,
    is_honeypot BOOLEAN DEFAULT FALSE,
    honeypot_reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    inactive_reason TEXT,
    last_check_date TIMESTAMP,
    UNIQUE(ip, port)
);

-- Create models table
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

-- Create metadata table
CREATE TABLE IF NOT EXISTS metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add indexes for better query performance
CREATE INDEX idx_servers_status ON servers(status);
CREATE INDEX idx_servers_scan_date ON servers(scan_date);
CREATE INDEX idx_models_name ON models(name);
CREATE INDEX idx_models_server_id ON models(server_id);
CREATE INDEX idx_servers_honeypot ON servers(is_honeypot);
CREATE INDEX idx_servers_active ON servers(is_active);
CREATE INDEX idx_servers_status_honeypot ON servers(status, is_honeypot);
CREATE INDEX idx_servers_status_active ON servers(status, is_active);

-- Initialize default metadata values
INSERT INTO metadata (key, value, updated_at) 
VALUES 
('last_scan_start', NULL, NOW()),
('last_scan_end', NULL, NOW()),
('last_prune_start', NULL, NOW()),
('last_prune_end', NULL, NOW()),
('scanned_count', '0', NOW()),
('verified_count', '0', NOW()),
('failed_count', '0', NOW())
ON CONFLICT (key) DO NOTHING;

-- Create schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- Insert initial schema version
INSERT INTO schema_version (version) VALUES ('1.0.0');

-- Grant permissions to the database user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ollama;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ollama; 