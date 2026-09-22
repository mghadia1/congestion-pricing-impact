# How it works

```
12 TLC monthly parquet files (Oct–Mar, two winters) + zone lookup
        │  SHA-256 verified
        ▼
DuckDB  trips (sanity rules; payment_type 0 kept and flagged)
        │
        ├─ zone_class      ← same-zone fee share, post-policy
        ├─ grouped_trips   treated / control / excluded
        │
        ├─ daily_counts    trips per day per group (with / without payment_type 0)
        ├─ daily_speed     median mph per day: inside the zone vs upper Manhattan
        └─ fee_by_group    did each group actually pay?
        ▼
did.py  daily log gap → DiD per year → DDD = policy − placebo → week-block bootstrap
        ▼
outputs/  CSVs, event-study charts, summary.json
```

## The design, in one paragraph

Comparing the zone before and after 5 January mixes the policy with everything else that changes in January. Comparing it with the rest of the city removes city-wide changes, but only if the zone and the rest of the city would otherwise have moved together ("parallel trends"). They don't: downtown traffic lightens more in January than uptown traffic does, every year. So the same comparison is run on the winter before, when there was no policy. Its result is the normal seasonal gap, and subtracting it leaves the policy effect. That is a **difference-in-differences-in-differences (DDD)**: treated vs control, before vs after, policy year vs placebo year.

## Choices I would defend

| Choice | Why | What it costs |
|---|---|---|
| Classify zones from the fee column, using same-zone trips | It reads the boundary from the policy itself instead of guessing from a map. Same-zone trips separate cleanly: 93–100% charged inside, at most 3.8% outside | It depends on the fee being recorded correctly. Zones crossing 60th St are dropped rather than split |
| Exclude boundary zones from **both** groups | A half-charged zone would put partly-treated trips in either group | 2.5M post-policy trips excluded |
| Compare speed inside the zone with *upper Manhattan*, not the whole city | Same borough, similar street grid, taxi-dense | Upper Manhattan may itself be affected by diverted traffic |
| Placebo year shifted exactly 364 days | Keeps every weekday aligned. Weekday mix matters a lot for taxis | Moving holidays (Thanksgiving) misalign, so they are excluded and reported both ways |
| Bootstrap by whole weeks | Days in a week are correlated. Resampling days would understate uncertainty | With only 11–12 weeks per window, coverage is a little under 95% (measured at 92.5%) |
| Keep `payment_type 0` rows, and report both ways | They look like real trips, and their share changes over time differently by group | The volume result depends on this choice, which is why no volume claim is made |

## Mistakes the project caught in itself

1. **Rikers Island was "inside" the zone.** The fallback rule (pickup share ≥ 85%) had no minimum, and 5 pickups, all charged, were enough. There is now a floor of 1,000 pickups and a test for it.
2. **"Unknown" location 264 was classified as charged**, because 58% of its same-zone trips paid. Placeholder IDs 264 and 265 now get their own class and are excluded.
3. **Thanksgiving misalignment.** It was spotted in the event-study chart and handled by excluding those weeks, with the sensitivity reported, since the decision came after looking.
4. **A one-seed coverage test.** The first bootstrap test checked one synthetic dataset and failed, which a 95% interval is expected to do 5% of the time. It now checks coverage over 40 datasets.

## Tests (14)

The tests cover:
- zone classification, including the fallback floor and the unknown-location class;
- trip grouping and the sanity rules;
- `payment_type 0` counted both ways;
- control contamination in the fee query;
- on synthetic series with a known answer: DDD removes a seasonal drift that plain DiD absorbs; a null effect gives an interval covering 0; the bootstrap is reproducible, and its coverage is at least 32 of 40;
- excluded weeks really are excluded, and an incomplete window raises an error;
- windows are whole, weekday-aligned weeks, and the event study is centred on the pre-period;
- checksum rejection and query allow-listing.

## Things to be able to explain

- What is the parallel-trends assumption, and how does the placebo year weaken what it has to carry?
- Why is the plain DiD (+10.2%) the wrong headline for speed?
- Why is there no conclusion about trip volume, when one specification has an interval that excludes zero?
- What would make the +3.8% speed result wrong? (Diversion into upper Manhattan, trip composition, a one-off January event.)
- Why resample weeks rather than days?
