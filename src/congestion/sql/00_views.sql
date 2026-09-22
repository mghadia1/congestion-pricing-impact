-- Inputs: raw_trips (TLC yellow-taxi schema; cbd_congestion_fee exists only from
-- 2025) and raw_zones (taxi_zone_lookup). Session variables set by analysis.connect:
--   data_start, data_end       - timestamps bounding the downloaded months
--   classify_start, classify_end - post-policy window used to classify zones

CREATE OR REPLACE VIEW zones AS
SELECT LocationID AS location_id, Borough AS borough, Zone AS zone FROM raw_zones;

-- Sanity rules only. Unlike the tip analysis in nyc-taxi-sql-analytics,
-- payment_type 0 rows are KEPT here and flagged: this study counts trips, and
-- the share of payment_type 0 rows grew from ~4% (Oct 2023) to ~22% (Feb 2025),
-- so dropping them would manufacture a trend. Results are reported both ways.
CREATE OR REPLACE VIEW trips AS
WITH base AS (
    SELECT
        tpep_pickup_datetime                                                   AS pickup_ts,
        tpep_pickup_datetime::DATE                                             AS pickup_date,
        PULocationID                                                           AS pu,
        DOLocationID                                                           AS do_,
        trip_distance                                                          AS miles,
        date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0 AS minutes,
        fare_amount,
        payment_type = 0                                                       AS is_payment_type_0,
        cbd_congestion_fee
    FROM raw_trips
)
SELECT *, miles / (minutes / 60.0) AS mph
FROM base
WHERE pickup_ts >= getvariable('data_start')
  AND pickup_ts <  getvariable('data_end')
  AND minutes > 0 AND minutes <= 180
  AND miles   > 0 AND miles   <= 100
  AND fare_amount > 0
  AND miles / (minutes / 60.0) <= 80;
