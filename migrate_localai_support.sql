-- Migration script to add LocalAI support to the database
-- Run this script to update the database schema for LocalAI integration

-- Check if columns exist before adding them
DO $$
BEGIN
    -- Add api_type column to endpoints table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'endpoints' AND column_name = 'api_type') THEN
        ALTER TABLE endpoints ADD COLUMN api_type VARCHAR(10) DEFAULT 'ollama';
    END IF;

    -- Add api_version column to endpoints table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'endpoints' AND column_name = 'api_version') THEN
        ALTER TABLE endpoints ADD COLUMN api_version VARCHAR(20);
    END IF;

    -- Add auth_required column to endpoints table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'endpoints' AND column_name = 'auth_required') THEN
        ALTER TABLE endpoints ADD COLUMN auth_required BOOLEAN DEFAULT FALSE;
    END IF;

    -- Add model_type column to models table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'models' AND column_name = 'model_type') THEN
        ALTER TABLE models ADD COLUMN model_type VARCHAR(20);
    END IF;

    -- Add capabilities column to models table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'models' AND column_name = 'capabilities') THEN
        ALTER TABLE models ADD COLUMN capabilities JSONB;
    END IF;
END $$;

-- Create index for faster filtering if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes 
                  WHERE indexname = 'idx_endpoints_api_type') THEN
        CREATE INDEX idx_endpoints_api_type ON endpoints(api_type);
    END IF;
END $$;

-- Update existing endpoints to have 'ollama' as api_type
UPDATE endpoints SET api_type = 'ollama' WHERE api_type IS NULL;

-- Add constraint to ensure api_type is either 'ollama' or 'localai'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'endpoints_api_type_check') THEN
        ALTER TABLE endpoints ADD CONSTRAINT endpoints_api_type_check 
        CHECK (api_type IN ('ollama', 'localai'));
    END IF;
END $$;

-- Log migration completion
INSERT INTO metadata (key, value, updated_at) 
VALUES ('localai_migration', 'completed', NOW()) 
ON CONFLICT (key) DO UPDATE SET value = 'completed', updated_at = NOW();

-- Print completion message
DO $$
BEGIN
    RAISE NOTICE 'LocalAI migration completed successfully';
END $$; 