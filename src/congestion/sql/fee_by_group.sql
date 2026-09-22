-- After the policy: what share of each group actually paid the fee? Treated
-- should be near 1 and control near 0; control trips that paid are the
-- contamination (e.g. trips passing through the zone without stopping in it).
SELECT
    trip_group,
    count(*)                                             AS trips,
    round(100.0 * avg((cbd_congestion_fee > 0)::INTEGER), 2) AS pct_charged,
    round(avg(cbd_congestion_fee), 3)                     AS mean_fee
FROM grouped_trips
WHERE pickup_ts >= getvariable('classify_start') AND pickup_ts < getvariable('classify_end')
GROUP BY trip_group
ORDER BY trip_group;
