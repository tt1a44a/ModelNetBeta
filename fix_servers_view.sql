-- SQL script to implement INSTEAD OF triggers for the servers view
-- This makes the servers view updatable, ensuring changes to the view propagate to the underlying tables

-- First, drop the existing servers view
DROP VIEW IF EXISTS servers;

-- Create a new version of the servers view with the same definition
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

-- Create INSTEAD OF INSERT trigger
CREATE OR REPLACE FUNCTION servers_insert_trigger()
RETURNS TRIGGER AS $$
DECLARE
    inserted_endpoint_id INTEGER;
BEGIN
    -- First, insert into endpoints table
    INSERT INTO endpoints (ip, port, scan_date, verified)
    VALUES (NEW.ip, NEW.port, COALESCE(NEW.scan_date, CURRENT_TIMESTAMP), 1)
    ON CONFLICT (ip, port) 
    DO UPDATE SET 
        scan_date = EXCLUDED.scan_date,
        verified = 1
    RETURNING id INTO inserted_endpoint_id;
    
    -- Then, insert into verified_endpoints table - using the local variable to avoid ambiguity
    INSERT INTO verified_endpoints (endpoint_id, verification_date)
    VALUES (inserted_endpoint_id, CURRENT_TIMESTAMP)
    ON CONFLICT (endpoint_id) DO NOTHING;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER servers_insert_instead
INSTEAD OF INSERT ON servers
FOR EACH ROW
EXECUTE FUNCTION servers_insert_trigger();

-- Create INSTEAD OF UPDATE trigger
CREATE OR REPLACE FUNCTION servers_update_trigger()
RETURNS TRIGGER AS $$
BEGIN
    -- Update the endpoints table
    UPDATE endpoints
    SET 
        ip = NEW.ip,
        port = NEW.port,
        scan_date = COALESCE(NEW.scan_date, CURRENT_TIMESTAMP)
    WHERE id = OLD.id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER servers_update_instead
INSTEAD OF UPDATE ON servers
FOR EACH ROW
EXECUTE FUNCTION servers_update_trigger();

-- Create INSTEAD OF DELETE trigger
CREATE OR REPLACE FUNCTION servers_delete_trigger()
RETURNS TRIGGER AS $$
BEGIN
    -- Delete from endpoints table (will cascade to verified_endpoints)
    DELETE FROM endpoints WHERE id = OLD.id;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER servers_delete_instead
INSTEAD OF DELETE ON servers
FOR EACH ROW
EXECUTE FUNCTION servers_delete_trigger();

-- Analyze the servers view to optimize query performance
ANALYZE servers;

-- Show current counts to verify the view still works
SELECT 'Server counts after applying INSTEAD OF triggers:' AS description;
SELECT COUNT(*) AS server_count FROM servers; 