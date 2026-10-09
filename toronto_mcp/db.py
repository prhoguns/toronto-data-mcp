"""Running a checked query: read-only transaction, time limit, row cap."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg

DSN = os.getenv("TORONTO_DSN", "host=localhost port=5435 dbname=toronto user=mcp_reader")
TIMEOUT_MS = int(os.getenv("TORONTO_STATEMENT_TIMEOUT_MS", "10000"))


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple]
    truncated: bool


def run(sql: str, params: dict | None = None, max_rows: int = 200) -> Result:
    """Execute in a READ ONLY transaction with a statement timeout, whatever the role allows."""
    with psycopg.connect(DSN, autocommit=False) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            # Transaction-local, like SET LOCAL (which cannot take a bound parameter).
            cur.execute("SELECT set_config('statement_timeout', %s, true)", [f"{TIMEOUT_MS}ms"])
            cur.execute(sql, params)
            rows = cur.fetchmany(max_rows + 1)
            columns = [d.name for d in cur.description] if cur.description else []
        conn.rollback()
    return Result(columns, rows[:max_rows], len(rows) > max_rows)


def markdown(result: Result) -> str:
    if not result.columns:
        return "(no columns)"
    fmt = lambda v: "NULL" if v is None else str(v).replace("|", "\\|")  # noqa: E731
    lines = ["| " + " | ".join(result.columns) + " |", "|" + "---|" * len(result.columns)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in result.rows]
    note = f"\n\n{len(result.rows)} rows" + (" (truncated; add filters or aggregate)" if result.truncated else "")
    return "\n".join(lines) + note
