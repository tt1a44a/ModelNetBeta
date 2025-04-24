-- SQL Script to fix database maintenance issues
-- Based on findings from the database schema review (db_schema_issues_report.md)

-- 1. Update NULL verification_date values
UPDATE endpoints 
SET verification_date = CURRENT_TIMESTAMP
WHERE verification_date IS NULL
  AND verified = 1;

-- 2. Update NULL last_check_date values
UPDATE endpoints
SET last_check_date = CURRENT_TIMESTAMP
WHERE last_check_date IS NULL;

-- 3. Fix the benchmark_results_model_id_fkey foreign key constraint to use CASCADE
ALTER TABLE benchmark_results 
DROP CONSTRAINT IF EXISTS benchmark_results_model_id_fkey;

ALTER TABLE benchmark_results
ADD CONSTRAINT benchmark_results_model_id_fkey
FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE;

-- 4. Vacuum and analyze tables with high dead tuple ratios
VACUUM ANALYZE metadata;
VACUUM ANALYZE endpoints;
VACUUM ANALYZE models;
VACUUM ANALYZE verified_endpoints;
VACUUM ANALYZE benchmark_results;

-- 5. Analyze all tables and update statistics
ANALYZE; 