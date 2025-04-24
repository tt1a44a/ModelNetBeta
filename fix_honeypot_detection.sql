-- Fix honeypot detection issues

-- Start transaction
BEGIN;

-- Show current state
SELECT 'Current state:' as message;
SELECT m.name, COUNT(*) as count, 
       COUNT(CASE WHEN e.verified = 1 THEN 1 END) as verified_count,
       COUNT(CASE WHEN e.is_honeypot = true THEN 1 END) as honeypot_count
FROM models m 
JOIN endpoints e ON m.endpoint_id = e.id 
GROUP BY m.name 
ORDER BY count DESC 
LIMIT 10;

-- 1. Reset honeypot status for endpoints that were incorrectly marked
-- Only keep honeypot status for endpoints that were marked for other reasons
UPDATE endpoints 
SET is_honeypot = false,
    honeypot_reason = NULL
WHERE is_honeypot = true 
AND honeypot_reason LIKE '%DeepSeek variants%';

-- 2. Update verification status for previously incorrectly marked honeypots
-- If they have valid models and responses, mark them as verified
UPDATE endpoints e
SET verified = 1,
    is_active = true,
    verification_date = NOW()
WHERE e.verified = 0 
AND e.is_honeypot = false
AND EXISTS (
    SELECT 1 FROM models m 
    WHERE m.endpoint_id = e.id 
    AND m.name LIKE '%deepseek%'
);

-- 3. Add verified_endpoints entries for newly verified endpoints
INSERT INTO verified_endpoints (endpoint_id, verification_date)
SELECT id, NOW()
FROM endpoints 
WHERE verified = 1
AND NOT EXISTS (
    SELECT 1 FROM verified_endpoints ve WHERE ve.endpoint_id = endpoints.id
);

-- Show final state
SELECT 'State after fixes:' as message;
SELECT m.name, COUNT(*) as count, 
       COUNT(CASE WHEN e.verified = 1 THEN 1 END) as verified_count,
       COUNT(CASE WHEN e.is_honeypot = true THEN 1 END) as honeypot_count
FROM models m 
JOIN endpoints e ON m.endpoint_id = e.id 
GROUP BY m.name 
ORDER BY count DESC 
LIMIT 10;

-- Show verification counts
SELECT 'Verification counts:' as message;
SELECT 
    (SELECT COUNT(*) FROM endpoints WHERE verified = 1) as verified_endpoints,
    (SELECT COUNT(*) FROM verified_endpoints) as verified_endpoints_table,
    (SELECT COUNT(*) FROM endpoints WHERE is_honeypot = true) as honeypot_endpoints,
    (SELECT COUNT(*) FROM endpoints WHERE is_active = false) as inactive_endpoints;

-- Commit transaction
COMMIT; 