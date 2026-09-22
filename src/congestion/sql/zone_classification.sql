-- Classify every taxi zone as inside the congestion relief zone ("charged"),
-- straddling its edge ("boundary"), or "outside", using the fee itself.
--
-- The deciding evidence is trips that START AND END in the same zone: such a
-- trip is charged only if the zone lies inside the charged area, so the share
-- charged is ~0.9 inside, ~0 outside, and in between for zones cut by the
-- 60th Street line. Pickup share alone is unreliable, because a zone just
-- north of 60th Street sends many trips downtown and looks half-charged.
-- Zones with too few same-zone trips (< 200) fall back to the pickup share, but
-- only with at least 1,000 pickups: the first version had no floor and put
-- Rikers Island (5 pickups, all charged) inside the zone.
CREATE OR REPLACE TABLE zone_class AS
WITH post AS (
    SELECT * FROM trips
    WHERE pickup_ts >= getvariable('classify_start') AND pickup_ts < getvariable('classify_end')
),
by_pickup AS (
    SELECT pu AS location_id, count(*) AS pickup_n, avg((cbd_congestion_fee > 0)::INTEGER) AS pickup_charged
    FROM post GROUP BY pu
),
same_zone AS (
    SELECT pu AS location_id, count(*) AS intra_n, avg((cbd_congestion_fee > 0)::INTEGER) AS intra_charged
    FROM post WHERE pu = do_ GROUP BY pu
)
SELECT
    z.location_id, z.borough, z.zone,
    coalesce(p.pickup_n, 0)  AS pickup_n,
    p.pickup_charged,
    coalesce(s.intra_n, 0)   AS intra_n,
    s.intra_charged,
    CASE
        -- 264 "Unknown" and 265 "Outside of NYC" are placeholders, not places.
        -- The first version classified 264 as charged (58% of its same-zone
        -- trips paid); an unknown location cannot be put on either side.
        WHEN z.location_id IN (264, 265)                                  THEN 'unknown'
        WHEN coalesce(s.intra_n, 0) >= 200 AND s.intra_charged >= 0.50 THEN 'charged'
        WHEN coalesce(s.intra_n, 0) >= 200 AND s.intra_charged >= 0.05 THEN 'boundary'
        WHEN coalesce(s.intra_n, 0) <  200 AND p.pickup_n >= 1000 AND p.pickup_charged >= 0.85 THEN 'charged'
        ELSE 'outside'
    END AS zone_class
FROM zones AS z
LEFT JOIN by_pickup AS p USING (location_id)
LEFT JOIN same_zone AS s USING (location_id);

-- Treated: touches the charged zone at either end, and no boundary or unknown zone.
-- Control: neither end in a charged or boundary zone.
CREATE OR REPLACE VIEW grouped_trips AS
SELECT
    t.*,
    pz.zone_class AS pu_class,
    dz.zone_class AS do_class,
    pz.borough    AS pu_borough,
    dz.borough    AS do_borough,
    CASE
        WHEN 'boundary' IN (pz.zone_class, dz.zone_class)
          OR 'unknown'  IN (pz.zone_class, dz.zone_class) THEN 'excluded'
        WHEN 'charged'  IN (pz.zone_class, dz.zone_class) THEN 'treated'
        ELSE 'control'
    END AS trip_group
FROM trips AS t
JOIN zone_class AS pz ON pz.location_id = t.pu
JOIN zone_class AS dz ON dz.location_id = t.do_;
