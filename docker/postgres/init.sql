-- ======================================================================
-- QuantX — PostgreSQL Initialization Script
-- Runs on first container start when data volume is empty
-- ======================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schemas for logical separation
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS analytics;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA market TO quantx;
GRANT ALL PRIVILEGES ON SCHEMA trading TO quantx;
GRANT ALL PRIVILEGES ON SCHEMA analytics TO quantx;
