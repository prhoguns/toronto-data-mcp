"""Checks a model-written query before it reaches the database.

This is the second of three layers. The first is the database role (SELECT on marts.* and nothing
else); the third is the read-only transaction with a statement timeout. The guard exists so a bad
query is refused with a reason the model can act on, instead of a permission error, and so the
server stays safe even if it is pointed at a connection with more privileges than it should have.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from toronto_mcp.catalog import TABLES

# Functions that read files, run nested SQL, sleep, change settings or reach other servers.
DENIED_FUNCTION_PREFIXES = (
    "pg_",
    "lo_",
    "dblink",
    "query_to_",
    "table_to_",
    "cursor_to_",
    "database_to_",
    "schema_to_",
)
DENIED_FUNCTIONS = {
    "set_config",
    "current_setting",
    "txid_current",
    "nextval",
    "setval",
    "currval",
    "version",
    "inet_server_addr",
    "inet_client_addr",
}
WRITE_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Copy,
    exp.Command,
    exp.Grant,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Into,
    exp.Lock,
)


class Rejected(ValueError):
    """The query is not allowed; the message says why, for the model to fix it."""


def check(sql: str) -> exp.Query:
    """Return the parsed query if it is a single read of allowed tables, else raise Rejected."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise Rejected(f"could not parse the query: {str(e).splitlines()[0]}") from e
    if len(statements) != 1:
        raise Rejected("send exactly one statement")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise Rejected(f"only SELECT queries are allowed, not {tree.key.upper()}")

    for node in tree.walk():
        if isinstance(node, WRITE_NODES):
            raise Rejected(f"{node.key.upper()} is not allowed; this connection is read-only")
        if isinstance(node, exp.Lock) or (isinstance(node, exp.Select) and node.args.get("locks")):
            raise Rejected("locking reads (FOR UPDATE / FOR SHARE) are not allowed")
        if isinstance(node, exp.Func):
            name = (node.sql_name() if not isinstance(node, exp.Anonymous) else node.name).lower()
            if name in DENIED_FUNCTIONS or name.startswith(DENIED_FUNCTION_PREFIXES):
                raise Rejected(f"function {name}() is not allowed")

    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if not name and isinstance(table.this, exp.Func):
            raise Rejected("table functions are not allowed; query the marts tables")
        if not schema and name in ctes:
            continue
        if schema not in ("", "marts") or name not in TABLES:
            shown = f"{schema}.{name}" if schema else name
            raise Rejected(f"unknown table {shown}; available: {', '.join(sorted(TABLES))} (schema marts)")
    return tree


def limited(tree: exp.Query, max_rows: int) -> str:
    """Wrap the query so the database never returns more than max_rows + 1 rows (+1 detects truncation)."""
    return f"SELECT * FROM ({tree.sql(dialect='postgres', comments=False)}) AS q LIMIT {max_rows + 1}"
