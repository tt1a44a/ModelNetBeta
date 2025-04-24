-- SQL script to fix database synchronization issues
-- This will repair the relationship between endpoints and verified_endpoints tables

-- First, show current counts to diagnose the issue
SELECT 'Endpoint counts before fix' AS description;
SELECT 
  (SELECT COUNT(*) FROM endpoints) AS total_endpoints,
  (SELECT COUNT(*) FROM endpoints WHERE verified = 1) AS verified_endpoints_status,
  (SELECT COUNT(*) FROM verified_endpoints) AS verified_endpoints_table,
  (SELECT COUNT(*) FROM servers) AS servers_view;

-- Fix 1: Ensure all endpoints with verified=1 have entries in verified_endpoints table
INSERT INTO verified_endpoints (endpoint_id, verification_date)
SELECT id, COALESCE(verification_date, CURRENT_TIMESTAMP) FROM endpoints 
WHERE verified = 1
AND NOT EXISTS (
    SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = endpoints.id
);

-- Fix 2: Update verification dates for verified endpoints that don't have them
UPDATE endpoints 
SET verification_date = CURRENT_TIMESTAMP
WHERE verified = 1 AND verification_date IS NULL;

-- Fix 3: Make sure endpoints referenced in verified_endpoints have verified=1
UPDATE endpoints
SET verified = 1, verification_date = CURRENT_TIMESTAMP
WHERE verified != 1
AND EXISTS (
    SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = endpoints.id
);

-- Show updated counts after fixes
SELECT 'Endpoint counts after fix' AS description;
SELECT 
  (SELECT COUNT(*) FROM endpoints) AS total_endpoints,
  (SELECT COUNT(*) FROM endpoints WHERE verified = 1) AS verified_endpoints_status,
  (SELECT COUNT(*) FROM verified_endpoints) AS verified_endpoints_table,
  (SELECT COUNT(*) FROM servers) AS servers_view;

-- Analyze the servers view to optimize query performance
ANALYZE servers;

-- Execute simple query to show servers data is accessible
SELECT 'Sample of servers data (should show rows if fix worked):' AS description;
SELECT * FROM servers LIMIT 5; 