-- PostgreSQL type fix script
-- This script fixes the type mismatch issues between boolean and integer columns

BEGIN;

-- Show current state
SELECT 'Current column types:' as message;
SELECT 
    column_name, 
    data_type 
FROM 
    information_schema.columns 
WHERE 
    table_name = 'endpoints' 
    AND column_name IN ('verified', 'is_honeypot', 'is_active');

-- Create the honeypot_classifications table if it doesn't exist
CREATE TABLE IF NOT EXISTS honeypot_classifications (
    id SERIAL PRIMARY KEY,
    endpoint_id INTEGER NOT NULL,
    detection_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detection_reason TEXT NOT NULL,
    confidence_score FLOAT NOT NULL,
    detection_method TEXT NOT NULL,
    FOREIGN KEY (endpoint_id) REFERENCES endpoints(id)
);

-- Fix the query issues by ensuring type consistency
-- Option 1: Cast the Boolean TRUE/FALSE to INTEGER for verified column
CREATE OR REPLACE FUNCTION cast_bool_to_int(boolean) RETURNS INTEGER AS $$
BEGIN
    RETURN CASE WHEN $1 THEN 1 ELSE 0 END;
END;
$$ LANGUAGE plpgsql;

-- Ensure no honeypots are marked as verified
UPDATE endpoints SET verified = 0 WHERE is_honeypot = TRUE;

-- Remove any honeypots from verified_endpoints table
DELETE FROM verified_endpoints 
WHERE endpoint_id IN (SELECT id FROM endpoints WHERE is_honeypot = TRUE);

-- Check for any inconsistencies
SELECT 'Checking for inconsistencies:' as message;
SELECT * FROM verified_endpoints ve 
LEFT JOIN endpoints e ON ve.endpoint_id = e.id 
WHERE e.is_honeypot = TRUE OR e.verified = 0
LIMIT 10;

-- Show statistics before commit
SELECT 'Current statistics:' as message;
SELECT 
    (SELECT COUNT(*) FROM endpoints WHERE verified = 1) as verified_endpoints,
    (SELECT COUNT(*) FROM endpoints WHERE is_honeypot = TRUE) as honeypot_endpoints,
    (SELECT COUNT(*) FROM verified_endpoints) as verified_endpoints_table;

COMMIT;

-- Instructions for the prune_bad_endpoints.py file:
/*
To fix the prune_bad_endpoints.py file, make these changes:

1. Update the get_db_boolean function to handle verified column type correctly:
   ```python
   def get_db_boolean(value, as_string=True):
       """
       Get the proper boolean value for the current database type
       Args:
           value (bool): Python boolean value
           as_string (bool): Whether to return the value as a string
       
       Returns:
           String or integer representation of the boolean value for SQL
       """
       if DATABASE_TYPE == "postgres":
           # For TRUE/FALSE boolean columns (is_honeypot, is_active)
           if as_string:
               return "TRUE" if value else "FALSE"
           else:
               return True if value else False
       else:
           # SQLite
           return "1" if value else "0" if as_string else 1 if value else 0
   ```

2. For verified column comparisons, always cast boolean to integer:
   ```python
   # Example:
   # Change:
   # WHERE verified = {get_db_boolean(True)}
   # To:
   # WHERE verified = CAST({get_db_boolean(True)} AS INTEGER)
   # Or:
   # WHERE verified = {1 if value else 0}
   ```
*/ 