"""What the model is told about the warehouse: tables, what a row means, and the traps in the data."""

TABLES = {
    "fct_crime_incidents": {
        "grain": "One row per offence per police event (an event with an assault and a robbery is two rows), 2014 on.",
        "columns": {
            "event_id": "Police event number. Count DISTINCT event_id for events, count rows for offences.",
            "occurrence_date": "When it happened.",
            "report_date": "When it was reported. days_to_report = report_date - occurrence_date.",
            "occurrence_hour": "0-23, local time.",
            "neighbourhood_id": "Joins dim_neighbourhood. NULL when police recorded no neighbourhood (NSA).",
            "mci_category": "Assault, Auto Theft, Break and Enter, Robbery, Theft Over.",
            "premises_type": "House, Apartment, Commercial, Outside, Transit, Educational, Other.",
            "longitude": "Offset to the nearest intersection for privacy; 0 when withheld.",
        },
    },
    "agg_crime_monthly_neighbourhood": {
        "grain": "One row per month x neighbourhood x crime category, with the rate per 1,000 residents.",
        "columns": {
            "incidents": "Offence rows that month.",
            "incidents_per_1000": "incidents / population_2021 * 1000. Downtown areas look high because many people "
            "visit but few live there.",
            "is_improvement_area": "City-designated Neighbourhood Improvement Area.",
        },
    },
    "dim_neighbourhood": {
        "grain": "One row per neighbourhood (City 158-neighbourhood model), with 2021 census figures.",
        "columns": {
            "tsns_classification": "Toronto Strong Neighbourhoods Strategy class.",
            "median_income_2020": "Median total household income, 2020 (census 2021), in dollars.",
            "geometry_geojson": "Boundary polygon as GeoJSON text; large, avoid selecting it.",
        },
    },
    "dim_date": {"grain": "One row per calendar day. date_key is YYYYMMDD.", "columns": {}},
    "fct_ttc_delays": {
        "grain": "One row per TTC subway delay incident.",
        "columns": {
            "delay_at": "Local timestamp of the delay.",
            "line": "Line as recorded (YU, BD, SHP, and variants); line_group normalises it.",
            "line_group": "YU (Line 1), BD (Line 2), SHP (Line 4), or OTHER.",
            "delay_minutes": "Minutes of delay; 0 when service was not held.",
            "gap_minutes": "Minutes between trains caused by the delay.",
            "delay_code": "Joins dim_ttc_delay_code.",
        },
    },
    "agg_ttc_delays_station_month": {
        "grain": "One row per station x line x month.",
        "columns": {"delays_10min_plus": "Delays of 10 minutes or more."},
    },
    "dim_ttc_delay_code": {
        "grain": "One row per TTC delay code.",
        "columns": {"delay_description": "What the code means, e.g. passenger assistance alarm."},
    },
}

GUIDE = """# Toronto open data warehouse

PostgreSQL star schema in the `marts` schema, built by dbt from City of Toronto open data
(https://github.com/prhoguns/toronto-open-data-pipeline). Read-only.

- Crime: `fct_crime_incidents` (offence-level facts) joins `dim_neighbourhood` and `dim_date`;
  `agg_crime_monthly_neighbourhood` is the ready-made monthly rollup with rates per 1,000 residents.
- Subway delays: `fct_ttc_delays` joins `dim_ttc_delay_code`; `agg_ttc_delays_station_month` is the rollup.

Before answering:
1. Offences are not events. One police event can hold several offences; say which you counted.
2. Rates use 2021 census population. Downtown neighbourhoods have small resident populations and large
   daytime populations, so per-resident rates overstate risk there.
3. The latest year is partial; do not compare it with full years without saying so.
4. Some incidents have no neighbourhood (NULL neighbourhood_id); per-neighbourhood totals exclude them.
5. Coordinates are offset to the nearest intersection by the police for privacy.
"""
