"""MCP server for the Toronto open data warehouse.

Tools: list_tables, describe_table, query (checked, read-only SQL), neighbourhood_crime and
station_delays (fixed, parameterised questions that need no SQL at all).
Resource: toronto://guide, the schema and the traps in the data.

    TORONTO_DSN="host=localhost port=5435 dbname=toronto user=mcp_reader password=..." toronto-mcp
"""

from __future__ import annotations

import psycopg
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from toronto_mcp import db, guard
from toronto_mcp.catalog import GUIDE, TABLES

server = MCPServer(
    "toronto-data",
    instructions="Read-only access to City of Toronto crime and TTC subway delay data. "
    "Read toronto://guide first; prefer neighbourhood_crime and station_delays over raw SQL.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
MAX_ROWS = 200


def _run(sql: str, params: dict | None = None, max_rows: int = MAX_ROWS) -> str:
    try:
        return db.markdown(db.run(sql, params, max_rows))
    except psycopg.errors.QueryCanceled as e:
        raise ToolError(f"query exceeded {db.TIMEOUT_MS / 1000:.0f}s; aggregate or filter more") from e
    except psycopg.Error as e:
        raise ToolError(f"database error: {str(e).splitlines()[0]}") from e


@server.resource("toronto://guide", mime_type="text/markdown", description="Schema overview and data caveats.")
def guide() -> str:
    return GUIDE


@server.tool(annotations=READ_ONLY)
def list_tables() -> str:
    """The warehouse tables, what one row means, and row counts."""
    counts = db.run("SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'marts'", max_rows=100).rows
    n = dict(counts)
    return "\n".join(
        f"- marts.{t}" + (f" (~{n[t]:,} rows)" if t in n else "") + f": {meta['grain']}" for t, meta in TABLES.items()
    )


@server.tool(annotations=READ_ONLY)
def describe_table(table: str) -> str:
    """Columns, types and meanings for one table, plus three example rows."""
    table = table.removeprefix("marts.").lower()
    if table not in TABLES:
        raise ToolError(f"unknown table {table}; available: {', '.join(TABLES)}")
    cols = db.run(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'marts' AND table_name = %(t)s ORDER BY ordinal_position",
        {"t": table},
    ).rows
    notes = TABLES[table]["columns"]
    lines = [f"marts.{table}: {TABLES[table]['grain']}", ""]
    lines += [f"- {c} ({t})" + (f": {notes[c]}" if c in notes else "") for c, t in cols]
    shown = [c for c, _ in cols if c != "geometry_geojson"]
    sample = _run(f"SELECT {', '.join(shown)} FROM marts.{table} LIMIT 3", max_rows=3)
    return "\n".join(lines) + "\n\nExample rows:\n\n" + sample


@server.tool(annotations=READ_ONLY)
def query(sql: str) -> str:
    """Run one read-only PostgreSQL SELECT against the marts tables. At most 200 rows come back; aggregate
    in SQL rather than fetching detail. Tables must be marts.* (see list_tables)."""
    try:
        tree = guard.check(sql)
    except guard.Rejected as e:
        raise ToolError(f"query rejected: {e}") from e
    return _run(guard.limited(tree, MAX_ROWS))


@server.tool(annotations=READ_ONLY)
def neighbourhood_crime(neighbourhood: str, year: int) -> str:
    """Incidents and rate per 1,000 residents by crime category for one neighbourhood and year, with the
    city-wide rate for comparison. Neighbourhood names match partially ("bay" finds Yonge-Bay Corridor)."""
    matches = db.run(
        "SELECT neighbourhood_id, neighbourhood_name FROM marts.dim_neighbourhood "
        "WHERE neighbourhood_name ILIKE %(p)s ORDER BY neighbourhood_name",
        {"p": f"%{neighbourhood}%"},
    ).rows
    if not matches:
        raise ToolError(f"no neighbourhood matches '{neighbourhood}'")
    if len(matches) > 1:
        names = ", ".join(m[1] for m in matches[:10])
        raise ToolError(f"'{neighbourhood}' matches {len(matches)} neighbourhoods ({names}); be more specific")
    nid, name = matches[0]
    table = _run(
        """
        WITH hood AS (
            SELECT mci_category, sum(incidents) AS incidents, max(population_2021) AS population
            FROM marts.agg_crime_monthly_neighbourhood
            WHERE neighbourhood_id = %(nid)s AND extract(year FROM month_start) = %(year)s
            GROUP BY 1
        ), city AS (
            SELECT a.mci_category, sum(a.incidents) AS incidents,
                   (SELECT sum(population_2021) FROM marts.dim_neighbourhood) AS population
            FROM marts.agg_crime_monthly_neighbourhood a
            WHERE extract(year FROM a.month_start) = %(year)s
            GROUP BY 1
        )
        SELECT c.mci_category AS category, coalesce(h.incidents, 0) AS incidents,
               round(1000.0 * coalesce(h.incidents, 0) / h2.population, 2) AS per_1000,
               round(1000.0 * c.incidents / c.population, 2) AS city_per_1000
        FROM city c
        CROSS JOIN (SELECT max(population_2021) AS population FROM marts.dim_neighbourhood
                    WHERE neighbourhood_id = %(nid)s) h2
        LEFT JOIN hood h USING (mci_category)
        ORDER BY incidents DESC
        """,
        {"nid": nid, "year": year},
    )
    return f"{name}, {year} (rates per 1,000 residents, 2021 census population):\n\n{table}"


@server.tool(annotations=READ_ONLY)
def station_delays(station: str, months: int = 12) -> str:
    """The most common delay causes at a subway station over the last N months of data, with minutes lost.
    Station names match partially ("bloor" finds BLOOR STATION and BLOOR-YONGE)."""
    return _run(
        """
        SELECT d.station, coalesce(c.delay_description, d.delay_code) AS cause,
               count(*) AS delays, sum(d.delay_minutes) AS minutes_lost
        FROM marts.fct_ttc_delays d
        LEFT JOIN marts.dim_ttc_delay_code c USING (delay_code)
        WHERE d.station ILIKE %(p)s
          AND d.delay_date > (SELECT max(delay_date) FROM marts.fct_ttc_delays) - make_interval(months => %(m)s)
        GROUP BY 1, 2
        ORDER BY delays DESC
        LIMIT 15
        """,
        {"p": f"%{station}%", "m": max(1, min(months, 60))},
    )


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
