"""End to end through the MCP protocol against a real PostgreSQL, connected as the read-only role.

Needs TORONTO_TEST_ADMIN_DSN (an owner connection to an empty test database); skipped without it.
"""

import asyncio
import os
from pathlib import Path

import psycopg
import pytest

ADMIN = os.getenv("TORONTO_TEST_ADMIN_DSN")
pytestmark = pytest.mark.skipif(not ADMIN, reason="set TORONTO_TEST_ADMIN_DSN to run against PostgreSQL")
ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "test-only-password"


@pytest.fixture(scope="module")
def server():
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute((ROOT / "tests/fixture.sql").read_text())
        dbname = conn.info.dbname
        role_sql = (ROOT / "sql/readonly_role.sql").read_text().replace(":reader_password", f"'{PASSWORD}'")
        code = "\n".join(line for line in role_sql.splitlines() if not line.lstrip().startswith("--"))
        for body in [s.strip() for s in code.split(";") if s.strip()]:
            try:
                conn.execute(body)
            except psycopg.errors.DuplicateObject:  # role left from an earlier run
                conn.execute(f"ALTER ROLE mcp_reader PASSWORD '{PASSWORD}'")
        conn.execute(f"GRANT CONNECT ON DATABASE {dbname} TO mcp_reader")
    info = psycopg.conninfo.conninfo_to_dict(ADMIN)
    os.environ["TORONTO_DSN"] = psycopg.conninfo.make_conninfo(ADMIN, user="mcp_reader", password=PASSWORD)
    os.environ["TORONTO_STATEMENT_TIMEOUT_MS"] = "500"
    import importlib

    from toronto_mcp import db
    from toronto_mcp import server as srv

    importlib.reload(db)
    importlib.reload(srv)
    assert info["dbname"] == dbname
    return srv.server


def call(server, tool, **args):
    from mcp.client import Client

    async def go():
        async with Client(server) as c:
            r = await c.call_tool(tool, args)
            return r.is_error, r.content[0].text

    return asyncio.run(go())


def test_every_tool_is_marked_read_only(server):
    from mcp.client import Client

    async def go():
        async with Client(server) as c:
            return (await c.list_tools()).tools

    tools = asyncio.run(go())
    assert {t.name for t in tools} == {
        "list_tables",
        "describe_table",
        "query",
        "neighbourhood_crime",
        "station_delays",
    }
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)


def test_neighbourhood_crime_rates(server):
    err, text = call(server, "neighbourhood_crime", neighbourhood="yonge-bay", year=2024)
    assert not err
    # 50 assaults in 2024 for 10,000 residents; the 2023 row must not leak in.
    assert "| Assault | 50 | 5.00 |" in text
    # City: 60 assaults across 60,000 residents.
    assert "| 1.00 |" in text


def test_ambiguous_neighbourhood_asks_for_more(server):
    err, text = call(server, "neighbourhood_crime", neighbourhood="high park", year=2024)
    assert err and "matches 2 neighbourhoods" in text


def test_station_delays_window(server):
    err, text = call(server, "station_delays", station="union", months=12)
    assert not err and "| UNION STATION | Disorderly Patron | 2 | 10 |" in text
    assert "| 1 | 0 |" in text  # the 2023 alarm is outside the window; only the 2025 one counts


def test_query_rejects_writes_with_a_reason(server):
    err, text = call(server, "query", sql="drop table marts.dim_date")
    assert err and "query rejected: only SELECT" in text


def test_query_caps_rows(server):
    err, text = call(server, "query", sql="select * from marts.fct_crime_incidents")
    assert not err and text.endswith("200 rows (truncated; add filters or aggregate)")


def test_query_times_out(server):
    sql = "select count(*) from marts.dim_date a, marts.dim_date b, marts.dim_date c"
    err, text = call(server, "query", sql=sql)
    assert err and "exceeded" in text


def test_database_role_blocks_writes_even_without_the_guard(server):
    from toronto_mcp import db

    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        db.run("delete from marts.dim_date")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.run("select * from public.secrets")
