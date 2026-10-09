-- A small warehouse with the real marts column names, for the integration tests.
DROP SCHEMA IF EXISTS marts CASCADE;
CREATE SCHEMA marts;
DROP TABLE IF EXISTS public.secrets;
CREATE TABLE public.secrets (v text);
INSERT INTO public.secrets VALUES ('not for the reader role');

CREATE TABLE marts.dim_date AS
SELECT to_char(d, 'YYYYMMDD')::int AS date_key, d::date AS date_day, extract(year FROM d)::int AS year,
       extract(quarter FROM d)::int AS quarter, extract(month FROM d)::int AS month, to_char(d, 'Mon') AS month_abbr,
       date_trunc('month', d)::date AS month_start, extract(isodow FROM d)::int AS iso_day_of_week,
       to_char(d, 'Dy') AS day_abbr, extract(isodow FROM d) >= 6 AS is_weekend
FROM generate_series('2020-01-01'::date, '2025-06-30'::date, '1 day') AS d;

CREATE TABLE marts.dim_neighbourhood (
    neighbourhood_id int, neighbourhood_name text, tsns_classification text, is_improvement_area boolean,
    population_2021 int, median_income_2020 int, households_2021 int, geometry_geojson text);
INSERT INTO marts.dim_neighbourhood VALUES
    (1, 'Yonge-Bay Corridor', 'Not an NIA', false, 10000, 70000, 6000, '{}'),
    (2, 'High Park North', 'Not an NIA', false, 20000, 80000, 9000, '{}'),
    (3, 'High Park-Swansea', 'Not an NIA', false, 30000, 90000, 12000, '{}');

CREATE TABLE marts.agg_crime_monthly_neighbourhood (
    month_start date, neighbourhood_id int, neighbourhood_name text, is_improvement_area boolean,
    mci_category text, incidents bigint, population_2021 int, incidents_per_1000 numeric);
INSERT INTO marts.agg_crime_monthly_neighbourhood VALUES
    ('2024-01-01', 1, 'Yonge-Bay Corridor', false, 'Assault', 30, 10000, 3.0),
    ('2024-02-01', 1, 'Yonge-Bay Corridor', false, 'Assault', 20, 10000, 2.0),
    ('2024-01-01', 1, 'Yonge-Bay Corridor', false, 'Robbery', 5, 10000, 0.5),
    ('2024-01-01', 2, 'High Park North', false, 'Assault', 10, 20000, 0.5),
    ('2023-01-01', 1, 'Yonge-Bay Corridor', false, 'Assault', 99, 10000, 9.9);

CREATE TABLE marts.fct_crime_incidents (
    crime_incident_key bigint, event_id text, occurrence_date_key int, occurrence_date date, occurrence_hour int,
    report_date_key int, report_date date, days_to_report int, neighbourhood_id int, police_division text,
    mci_category text, offence text, location_type text, premises_type text, longitude float8, latitude float8);
INSERT INTO marts.fct_crime_incidents
SELECT i, 'GO-' || i, 20240101, '2024-01-01', i % 24, 20240101, '2024-01-01', 0, 1 + i % 3, 'D52',
       'Assault', 'Assault', 'Street', 'Outside', -79.38, 43.65
FROM generate_series(1, 500) AS i;

CREATE TABLE marts.dim_ttc_delay_code (delay_code varchar, delay_description text, system text, code_family_hint text);
INSERT INTO marts.dim_ttc_delay_code VALUES ('MUPAA', 'Passenger Assistance Alarm Activated - No Trouble Found', 'subway', 'MU'),
                                            ('SUDP', 'Disorderly Patron', 'subway', 'SU');

CREATE TABLE marts.fct_ttc_delays (
    ttc_delay_key bigint, delay_date_key int, delay_date date, delay_at timestamp, delay_hour int, station text,
    line text, line_group text, bound text, delay_code text, delay_description text, delay_minutes int,
    gap_minutes int, vehicle text);
INSERT INTO marts.fct_ttc_delays VALUES
    (1, 20250601, '2025-06-01', '2025-06-01 08:00', 8, 'UNION STATION', 'YU', 'YU', 'N', 'SUDP', null, 4, 8, '5001'),
    (2, 20250602, '2025-06-02', '2025-06-02 09:00', 9, 'UNION STATION', 'YU', 'YU', 'S', 'SUDP', null, 6, 10, '5002'),
    (3, 20250603, '2025-06-03', '2025-06-03 10:00', 10, 'UNION STATION', 'YU', 'YU', 'S', 'MUPAA', null, 0, 0, '5003'),
    (4, 20230101, '2023-01-01', '2023-01-01 10:00', 10, 'UNION STATION', 'YU', 'YU', 'S', 'MUPAA', null, 3, 5, '5004');

CREATE TABLE marts.agg_ttc_delays_station_month (
    month_start date, station text, line text, delay_events bigint, total_delay_minutes bigint,
    avg_delay_minutes numeric, max_delay_minutes int, delays_10min_plus bigint);
INSERT INTO marts.agg_ttc_delays_station_month VALUES ('2025-06-01', 'UNION STATION', 'YU', 3, 10, 3.33, 6, 0);
ANALYZE;
