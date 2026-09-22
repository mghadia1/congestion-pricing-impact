-- Median door-to-door speed per day for two comparable street networks:
--   inside  - both ends in the charged zone (Manhattan below 60th Street)
--   north   - both ends in Manhattan zones outside it (above the boundary zones)
-- Speed includes stops and signals, so it is a congestion proxy, not a sensor.
SELECT
    pickup_date,
    CASE WHEN pu_class = 'charged' THEN 'inside' ELSE 'north' END AS speed_group,
    count(*)                              AS trips,
    quantile_cont(mph, 0.5)               AS median_mph,
    quantile_cont(minutes / miles, 0.5)   AS median_minutes_per_mile,
    quantile_cont(mph, 0.5) FILTER (WHERE NOT is_payment_type_0) AS median_mph_excl_pt0
FROM grouped_trips
WHERE (pu_class = 'charged' AND do_class = 'charged')
   OR (pu_class = 'outside' AND do_class = 'outside' AND pu_borough = 'Manhattan' AND do_borough = 'Manhattan')
GROUP BY ALL
ORDER BY pickup_date, speed_group;
