# Toronto Data MCP Server

[![CI](https://github.com/prhoguns/toronto-data-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/prhoguns/toronto-data-mcp/actions/workflows/ci.yml)

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets an AI assistant answer
questions from the Toronto open data warehouse built by
[toronto-open-data-pipeline](https://github.com/prhoguns/toronto-open-data-pipeline): 451,229 police-reported
offences and 45,475 TTC subway delays in a PostgreSQL star schema. The assistant can look up tables, call
ready-made tools, or write its own SQL, which is checked before it runs and can only read.

**Stack:** Python 3.14 · MCP Python SDK 2.3 · PostgreSQL 18 · sqlglot · pytest.

## Tools

| Tool | For |
|---|---|
| `list_tables` | Tables, what one row means, row counts |
| `describe_table` | Columns, types, meanings and three example rows |
| `neighbourhood_crime(neighbourhood, year)` | Incidents and rate per 1,000 residents by category, against the city-wide rate. No SQL needed |
| `station_delays(station, months)` | Most common subway delay causes at a station, with minutes lost |
| `query(sql)` | One checked, read-only SELECT; at most 200 rows |
| `toronto://guide` (resource) | The schema and the traps: offences vs events, census denominators, partial years |

All tools carry MCP's `readOnlyHint` annotation, telling clients they change nothing.

From a real session against the full warehouse:

```
neighbourhood_crime("yonge-bay", 2024)
Yonge-Bay Corridor, 2024 (rates per 1,000 residents, 2021 census population):
| category | incidents | per_1000 | city_per_1000 |
| Assault | 549 | 43.42 | 8.90 |
| Break and Enter | 94 | 7.43 | 2.47 |
...

neighbourhood_crime("park", 2024)
error: 'park' matches 20 neighbourhoods (Bedford Park-Nortown, Clanton Park, ...); be more specific

query("select count(*) from marts.fct_crime_incidents a, marts.fct_crime_incidents b")
error: query exceeded 10s; aggregate or filter more
```

## Three layers between the model and the data

An assistant that writes SQL will eventually write a bad query, by mistake or because something in its
input told it to. Each layer below holds on its own; the tests check each one separately.

1. **The SQL guard** ([`guard.py`](toronto_mcp/guard.py)) parses the query with sqlglot. It accepts exactly
   one SELECT over the seven `marts` tables, and rejects:
   - writes, including a DELETE hidden in a CTE, and SELECT INTO
   - locking reads
   - system catalogs
   - table functions
   - functions that read files, sleep, run nested SQL (`query_to_xml`), change settings or reach other servers
   It then executes its own re-rendering of the parsed query, without comments, wrapped in a row limit.
   A rejection says why, so the model can fix its query.
2. **The database role** ([`readonly_role.sql`](sql/readonly_role.sql)): `SELECT` on `marts.*` and nothing else,
   read-only by default, five connections at most. A test bypasses the guard and shows the role alone still
   refuses a DELETE and cannot see other schemas.
3. **The transaction**: every query runs in a `READ ONLY` transaction with a 10-second statement timeout,
   whatever the role allows.

## Run it

```bash
pip install -e .
psql -v reader_password="'choose-a-password'" -f sql/readonly_role.sql     # once, as the warehouse owner
export TORONTO_DSN="host=localhost port=5433 dbname=toronto user=mcp_reader password=choose-a-password"
toronto-mcp                                                                 # speaks MCP over stdio
```

Claude Code:

```bash
claude mcp add toronto-data --env TORONTO_DSN="host=localhost port=5433 dbname=toronto user=mcp_reader password=..." -- toronto-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{"mcpServers": {"toronto-data": {"command": "toronto-mcp",
  "env": {"TORONTO_DSN": "host=localhost port=5433 dbname=toronto user=mcp_reader password=..."}}}}
```

## Tests

`pytest` runs 37 tests in CI:

- **29 guard tests:** allowed and rejected queries, CTE names, and that comments never reach the database.
- **8 end-to-end tests:** the server is driven through the MCP client against PostgreSQL 18, connected
  as the read-only role, using a fixture with the real column names. They cover rate arithmetic,
  ambiguous names, the delay-window filter, rejections, row caps, timeouts, and the role blocking writes
  without the guard.
