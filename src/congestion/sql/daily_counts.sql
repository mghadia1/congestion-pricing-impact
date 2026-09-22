-- Trips per day per group, with and without payment_type 0 rows.
SELECT
    pickup_date,
    trip_group,
    count(*)                                        AS trips,
    count(*) FILTER (WHERE NOT is_payment_type_0)   AS trips_excl_pt0
FROM grouped_trips
WHERE trip_group IN ('treated', 'control')
GROUP BY ALL
ORDER BY pickup_date, trip_group;
