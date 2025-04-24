-- Fix inactive endpoints that are still marked as verified

-- Start transaction
BEGIN;

-- Show current state
SELECT 'Current state:' as message;
SELECT is_active, verified, COUNT(*) 
FROM endpoints 
GROUP BY is_active, verified 
ORDER BY is_active, verified;

-- 1. Find inactive endpoints that are still marked as verified
SELECT 'Inactive but verified endpoints:' as message;
SELECT id, ip, port, inactive_reason, last_check_date
FROM endpoints
WHERE is_active = FALSE AND verified = 1
LIMIT 10;

-- 2. Update all inactive endpoints to be unverified
UPDATE endpoints 
SET verified = 0
WHERE is_active = FALSE AND verified = 1;

-- 3. Remove inactive endpoints from verified_endpoints table
DELETE FROM verified_endpoints 
WHERE endpoint_id IN (
    SELECT id FROM endpoints WHERE is_active = FALSE
);

-- Show final state
SELECT 'State after fixes:' as message;
SELECT is_active, verified, COUNT(*) 
FROM endpoints 
GROUP BY is_active, verified 
ORDER BY is_active, verified;

-- Show verification counts
SELECT 'Verification counts:' as message;
SELECT 
    (SELECT COUNT(*) FROM endpoints WHERE verified = 1) as verified_endpoints,
    (SELECT COUNT(*) FROM verified_endpoints) as verified_endpoints_table,
    (SELECT COUNT(*) FROM endpoints WHERE is_honeypot = TRUE) as honeypot_endpoints,
    (SELECT COUNT(*) FROM endpoints WHERE is_active = FALSE) as inactive_endpoints;

-- Commit transaction
COMMIT; 