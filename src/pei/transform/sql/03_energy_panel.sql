-- State-by-year energy panel for the 50 states and DC, from EIA. Region rows are excluded.

CREATE OR REPLACE TABLE retail_sales_annual AS
SELECT
    period::INT AS year,
    stateid AS state,
    sectorid AS sector,
    TRY_CAST(price AS DOUBLE) AS price_cents_kwh,
    TRY_CAST(sales AS DOUBLE) AS sales_gwh,
    TRY_CAST(revenue AS DOUBLE) AS revenue_musd,
    TRY_CAST(customers AS DOUBLE) AS customers
FROM raw_retail_annual
WHERE stateid IN (SELECT state FROM ref_states);

CREATE OR REPLACE TABLE state_year_panel AS
WITH wide AS (
    SELECT
        state,
        year,
        max(price_cents_kwh) FILTER (sector = 'RES') AS res_price,
        max(sales_gwh) FILTER (sector = 'RES') AS res_sales,
        max(revenue_musd) FILTER (sector = 'RES') AS res_revenue,
        nullif(max(customers) FILTER (sector = 'RES'), 0) AS res_customers,
        max(price_cents_kwh) FILTER (sector = 'COM') AS com_price,
        max(sales_gwh) FILTER (sector = 'COM') AS com_sales,
        max(sales_gwh) FILTER (sector = 'IND') AS ind_sales,
        max(sales_gwh) FILTER (sector = 'ALL') AS total_sales
    FROM retail_sales_annual
    GROUP BY state, year
),
ops AS (
    SELECT
        location AS state,
        period::INT AS year,
        max(TRY_CAST("cost-per-btu" AS DOUBLE)) FILTER (fueltypeid = 'NG') AS gas_cost_mmbtu,
        max(TRY_CAST("cost-per-btu" AS DOUBLE)) FILTER (fueltypeid = 'COW') AS coal_cost_mmbtu,
        max(TRY_CAST(generation AS DOUBLE)) FILTER (fueltypeid = 'ALL') AS gen_total,
        max(TRY_CAST(generation AS DOUBLE)) FILTER (fueltypeid = 'NGO') AS gen_gas,
        max(TRY_CAST(generation AS DOUBLE)) FILTER (fueltypeid = 'COW') AS gen_coal,
        max(TRY_CAST(generation AS DOUBLE)) FILTER (fueltypeid = 'AOR') AS gen_renewable
    FROM raw_operational_annual
    GROUP BY location, period
)
SELECT
    w.state,
    r.census_division AS division,
    w.year,
    w.res_price,
    w.res_sales,
    w.res_revenue,
    w.res_customers,
    w.com_price,
    w.com_sales,
    w.ind_sales,
    w.com_sales + w.ind_sales AS ci_sales,
    w.total_sales,
    o.gas_cost_mmbtu,
    o.coal_cost_mmbtu,
    o.gen_gas / nullif(o.gen_total, 0) AS gas_share,
    o.gen_coal / nullif(o.gen_total, 0) AS coal_share,
    o.gen_renewable / nullif(o.gen_total, 0) AS renewable_share
FROM wide AS w
JOIN ref_states AS r USING (state)
LEFT JOIN ops AS o USING (state, year);

-- Data center presence by state, from the IM3 Atlas. Campus and building layers overlap, so
-- footprint uses the building layer only, and facility counts use the record id.
CREATE OR REPLACE TABLE atlas_state AS
WITH by_state AS (
    SELECT
        state_abb AS state,
        count(DISTINCT id) AS atlas_records,
        coalesce(sum(sqft) FILTER (type = 'building'), 0) AS building_sqft
    FROM (SELECT DISTINCT id, state_abb, sqft, type FROM raw_atlas)
    GROUP BY state_abb
)
SELECT
    s.state,
    coalesce(b.atlas_records, 0) AS atlas_records,
    coalesce(b.building_sqft, 0) AS building_sqft
FROM ref_states AS s
LEFT JOIN by_state AS b USING (state);

-- US AI data centers tracked by Epoch, by state parsed from the street address.
CREATE OR REPLACE TABLE epoch_us_sites AS
SELECT
    "Name" AS name,
    regexp_extract("Address", ',\s*([A-Z]{2})\s+\d{5}', 1) AS state,
    "Current power (MW)"::DOUBLE AS current_power_mw,
    "Owner" AS owner
FROM raw_epoch
WHERE "Country" = 'United States';

CREATE OR REPLACE TABLE aei_state AS
SELECT
    geo_id,
    replace(geo_id, 'US-', '') AS state,
    date_start::DATE AS period_start,
    date_end::DATE AS period_end,
    metric_id,
    value::DOUBLE AS value
FROM raw_aei
WHERE geo_level = 'subregion';

CREATE OR REPLACE TABLE aei_job_exposure AS
SELECT occ_code, title, observed_exposure::DOUBLE AS observed_exposure
FROM raw_job_exposure;
