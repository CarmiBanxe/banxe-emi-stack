-- pgaudit.sql — pgAudit bootstrap for banxe_compliance
-- Run ONCE after PostgreSQL restart with pgaudit in shared_preload_libraries
-- FCA CASS 15 / FA-04 | banxe-emi-stack

-- Step 1: Enable extension (requires pgaudit in shared_preload_libraries)
CREATE EXTENSION IF NOT EXISTS pgaudit;

-- Step 2: Configure audit scope for banxe_compliance
-- Log all WRITE operations (INSERT/UPDATE/DELETE) + DDL
ALTER SYSTEM SET pgaudit.log = 'write, ddl';
ALTER SYSTEM SET pgaudit.log_relation = on;
ALTER SYSTEM SET pgaudit.log_parameter = on;
ALTER SYSTEM SET log_destination = 'csvlog';
ALTER SYSTEM SET logging_collector = on;
ALTER SYSTEM SET log_directory = '/var/log/postgresql';
ALTER SYSTEM SET log_filename = 'postgresql-%Y-%m-%d.log';

-- Step 3: Apply config (no restart needed for these params after ALTER SYSTEM)
SELECT pg_reload_conf();

-- Verify
SELECT name, setting FROM pg_settings
WHERE name IN ('pgaudit.log', 'pgaudit.log_relation', 'log_destination', 'logging_collector');
