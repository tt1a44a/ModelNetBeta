-- Fix database inconsistencies

-- Start transaction
BEGIN;

-- Show current state
SELECT 'Current state:' as message;
SELECT verified, is_honeypot, is_active, COUNT(*) 
FROM endpoints 
GROUP BY verified, is_honeypot, is_active 
ORDER BY verified, is_honeypot, is_active;

-- 1. Fix verified but inactive endpoints
-- These should be active if they're verified
UPDATE endpoints 
SET is_active = true 
WHERE verified = 1 AND is_active = false;

-- 2. Fix honeypot endpoints
-- These should be unverified and inactive
UPDATE endpoints 
SET verified = 0, 
    is_active = false 
WHERE is_honeypot = true;

-- 3. Remove verified_endpoints entries for unverified endpoints
DELETE FROM verified_endpoints 
WHERE endpoint_id IN (
    SELECT id FROM endpoints WHERE verified = 0
);

-- 4. Add verified_endpoints entries for any verified endpoints missing them
INSERT INTO verified_endpoints (endpoint_id, verification_date)
SELECT id, COALESCE(verification_date, NOW())
FROM endpoints 
WHERE verified = 1
AND NOT EXISTS (
    SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = endpoints.id
);

-- Show final state
SELECT 'State after fixes:' as message;
SELECT verified, is_honeypot, is_active, COUNT(*) 
FROM endpoints 
GROUP BY verified, is_honeypot, is_active 
ORDER BY verified, is_honeypot, is_active;

-- Show verification counts
SELECT 'Verification counts:' as message;
SELECT 
    (SELECT COUNT(*) FROM endpoints WHERE verified = 1) as verified_endpoints,
    (SELECT COUNT(*) FROM verified_endpoints) as verified_endpoints_table,
    (SELECT COUNT(*) FROM endpoints WHERE is_honeypot = true) as honeypot_endpoints,
    (SELECT COUNT(*) FROM endpoints WHERE is_active = false) as inactive_endpoints;

-- Commit transaction
COMMIT; 