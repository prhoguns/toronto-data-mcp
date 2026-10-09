import pytest

from toronto_mcp.guard import Rejected, check, limited

ALLOWED = [
    "select mci_category, count(*) from marts.fct_crime_incidents group by 1",
    "select count(*) from fct_crime_incidents",  # unqualified marts table
    "with x as (select * from marts.fct_ttc_delays) select line_group, count(*) from x group by 1",
    "select n.neighbourhood_name, sum(a.incidents) from marts.agg_crime_monthly_neighbourhood a "
    "join marts.dim_neighbourhood n using (neighbourhood_id) group by 1 order by 2 desc limit 5",
    "select 1 union all select count(*) from marts.dim_date",
    "select date_trunc('month', delay_at), percentile_cont(0.9) within group (order by delay_minutes) "
    "from marts.fct_ttc_delays group by 1",
]

REJECTED = {
    "drop table marts.fct_crime_incidents": "only SELECT",
    "select 1; delete from marts.dim_date": "exactly one statement",
    "delete from marts.dim_date": "only SELECT",
    "update marts.dim_date set year = 1": "only SELECT",
    "with d as (delete from marts.dim_date returning *) select * from d": "DELETE",
    "select * into marts.copy from marts.dim_date": "INTO",
    "select * from marts.dim_date for update": "locking",
    "select pg_sleep(100)": "pg_sleep",
    "select pg_read_file('/etc/passwd')": "pg_read_file",
    "select query_to_xml('delete from marts.dim_date', true, true, '')": "query_to_xml",
    "select set_config('statement_timeout', '0', false)": "set_config",
    "select current_setting('data_directory')": "current_setting",
    "select * from dblink('host=evil', 'select 1') as t(x int)": "dblink|table functions",
    "select * from information_schema.tables": "unknown table",
    "select * from pg_catalog.pg_authid": "unknown table",
    "select * from public.secrets": "unknown table",
    "select * from generate_series(1, 1000000000)": "table functions",
    "copy marts.dim_date to '/tmp/x'": "only SELECT",
    "set statement_timeout = 0": "only SELECT",
    "this is not sql": "parse|only SELECT",
}


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed(sql):
    check(sql)


@pytest.mark.parametrize("sql, reason", REJECTED.items())
def test_rejected(sql, reason):
    with pytest.raises(Rejected, match=reason):
        check(sql)


def test_cte_names_are_not_mistaken_for_tables():
    check("with fct as (select 1 as x) select x from fct")


def test_limit_wraps_and_caps():
    sql = limited(check("select * from marts.dim_date"), 200)
    assert sql.startswith("SELECT * FROM (") and sql.endswith("LIMIT 201")


def test_executes_the_parsed_query_not_the_raw_text():
    # A trailing comment hiding a second statement never reaches the database: the query is re-rendered.
    sql = limited(check("select 1 as x /* ; drop table marts.dim_date */"), 5)
    assert "drop" not in sql.lower()
