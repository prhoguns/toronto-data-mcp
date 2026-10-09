-- The role the MCP server connects as: SELECT on the marts tables, nothing else.
-- Run once as the warehouse owner:
--   psql -v reader_password="'choose-a-password'" -f sql/readonly_role.sql
-- Even a query that got past the server's checks could only read marts.* within the time limit.

CREATE ROLE mcp_reader LOGIN PASSWORD :reader_password
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5;

REVOKE ALL ON SCHEMA public FROM mcp_reader;
GRANT USAGE ON SCHEMA marts TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO mcp_reader;
-- dbt rebuilds tables; keep the grant on the replacements.
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO mcp_reader;

ALTER ROLE mcp_reader SET default_transaction_read_only = on;
ALTER ROLE mcp_reader SET statement_timeout = '10s';
ALTER ROLE mcp_reader SET idle_in_transaction_session_timeout = '30s';
