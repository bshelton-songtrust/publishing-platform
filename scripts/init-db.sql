-- Initial database setup script for PostgreSQL
-- This script is run during Docker container initialization

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create application database user and role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'catalog_service_role') THEN
        CREATE ROLE catalog_service_role;
    END IF;
END
$$;

-- Grant necessary permissions to the catalog user
GRANT CONNECT ON DATABASE catalog_management TO catalog_user;
GRANT USAGE ON SCHEMA public TO catalog_user;
GRANT CREATE ON SCHEMA public TO catalog_user;

-- Grant permissions for the service role
GRANT catalog_service_role TO catalog_user;

-- Set up default search path
ALTER USER catalog_user SET search_path = public;

-- Configure Row-Level Security settings
ALTER DATABASE catalog_management SET row_security = on;