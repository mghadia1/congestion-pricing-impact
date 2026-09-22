"""Offline tests: zone classification and grouping on hand-built trips, and the
DiD / DDD estimator on synthetic series whose true effect is known."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from congestion import analysis, data, did

ZONES = pd.DataFrame({
    "LocationID": [1, 2, 3, 4, 5, 6, 264],
    "Borough": ["Manhattan", "Manhattan", "Manhattan", "Manhattan", "Queens", "Bronx", "Unknown"],
    "Zone": ["Inside", "Straddle", "North", "Few same-zone", "Queens", "Island", "N/A"],
    "service_zone": ["Yellow Zone"] * 7,
})


def trip(ts, pu, do, fee, payment=1, minutes=10, miles=2.0, fare=12.0):
    start = pd.Timestamp(ts)
    return {
        "tpep_pickup_datetime": start, "tpep_dropoff_datetime": start + pd.Timedelta(minutes=minutes),
        "PULocationID": pu, "DOLocationID": do, "trip_distance": miles, "fare_amount": fare,
        "payment_type": payment, "cbd_congestion_fee": fee,
    }


@pytest.fixture
def con():
    post = "2025-02-03 10:00"
    rows = []
    rows += [trip(post, 1, 1, 0.75) for _ in range(190)] + [trip(post, 1, 1, 0.0) for _ in range(10)]   # 95% -> charged
    rows += [trip(post, 2, 2, 0.75) for _ in range(60)] + [trip(post, 2, 2, 0.0) for _ in range(140)]   # 30% -> boundary
    rows += [trip(post, 3, 3, 0.0) for _ in range(200)]                                                   # 0% -> outside
    rows += [trip(post, 4, 3, 0.75) for _ in range(1000)]                                                 # no same-zone trips, 100% of 1,000 pickups
    rows += [trip(post, 6, 5, 0.75) for _ in range(5)]                                                    # 5 pickups, all charged
    rows += [trip(post, 5, 5, 0.0)]
    rows += [trip(post, 264, 264, 0.75) for _ in range(300)]                                           # "Unknown": mostly charged
    # rows that must be dropped by the sanity rules
    rows += [trip(post, 1, 3, 0.75, minutes=0), trip(post, 1, 3, 0.75, miles=0.0), trip(post, 1, 3, 0.75, fare=-5.0)]
    # a payment_type 0 trip: kept and flagged
    rows += [trip("2024-10-10 09:00", 3, 5, np.nan, payment=0)]
    return analysis.connect(pd.DataFrame(rows), ZONES)


def test_zone_classification(con):
    classes = analysis.zone_classes(con).set_index("zone")["zone_class"].to_dict()
    assert classes["Inside"] == "charged"
    assert classes["Straddle"] == "boundary"
    assert classes["North"] == "outside"
    assert classes["Few same-zone"] == "charged"     # fallback on 1,000 pickups at 100%
    assert classes["Island"] == "outside"            # 5 pickups is below the fallback floor
    assert classes["Queens"] == "outside"
    assert classes["N/A"] == "unknown"               # placeholder location, never charged or control


def test_trip_groups(con):
    groups = con.execute(
        "SELECT pu, do_, trip_group FROM grouped_trips GROUP BY ALL ORDER BY pu, do_"
    ).df().set_index(["pu", "do_"])["trip_group"].to_dict()
    assert groups[(1, 1)] == "treated"
    assert groups[(4, 3)] == "treated"               # starts in the zone, ends outside
    assert groups[(2, 2)] == "excluded"              # boundary trips belong to neither group
    assert groups[(3, 3)] == "control"
    assert groups[(3, 5)] == "control"
    assert groups[(264, 264)] == "excluded"


def test_sanity_rules_and_payment_type_0(con):
    # 200 inside + 200 straddle + 200 north + 1,000 fallback + 5 island + 1 queens + 300 unknown
    # + 1 payment_type 0; the three broken rows are dropped
    assert con.execute("SELECT count(*) FROM trips").fetchone()[0] == 200 + 200 + 200 + 1000 + 5 + 1 + 300 + 1
    counts = analysis.run(con, "daily_counts")
    october = counts[counts["pickup_date"] == pd.Timestamp("2024-10-10")].set_index("trip_group")
    assert october.loc["control", "trips"] == 1
    assert october.loc["control", "trips_excl_pt0"] == 0


def test_fee_by_group(con):
    fee = analysis.run(con, "fee_by_group").set_index("trip_group")
    # the 5 Bronx -> Queens trips were charged: control contamination, the thing this query measures
    assert fee.loc["control", "pct_charged"] == pytest.approx(100 * 5 / 206, abs=0.01)
    assert fee.loc["treated", "pct_charged"] == pytest.approx(100 * 1190 / 1200, abs=0.01)   # SQL rounds to 2 dp


def test_unknown_query_rejected(con):
    with pytest.raises(KeyError):
        analysis.run(con, "zone_class")


# ---- estimator on synthetic gaps -------------------------------------------------

def synthetic_gap(effect: float, drift: float, noise: float = 0.0, seed: int = 0) -> pd.Series:
    """Daily gap series over both years: `drift` added to every post window
    (seasonality, present in both years), `effect` only in the policy year."""
    days = pd.date_range("2023-10-01", "2025-04-01", freq="D")
    rng = np.random.default_rng(seed)
    gap = pd.Series(0.2 + rng.normal(0, noise, len(days)), index=days)
    for window, extra in ((data.STUDY, effect), (data.PLACEBO, 0.0)):
        post = (days >= pd.Timestamp(window.post_start)) & (days <= pd.Timestamp(window.post_end))
        gap[post] += drift + extra
    return gap


def test_ddd_removes_seasonal_drift():
    gap = synthetic_gap(effect=0.10, drift=0.05)
    result = did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=200)
    assert result.did_policy == pytest.approx(0.15)     # plain DiD absorbs the drift
    assert result.did_placebo == pytest.approx(0.05)
    assert result.ddd == pytest.approx(0.10)


def test_no_effect_gives_ci_covering_zero():
    gap = synthetic_gap(effect=0.0, drift=0.03, noise=0.05, seed=3)
    result = did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=2000)
    low, high = result.ci_ddd
    assert low < 0 < high


def test_bootstrap_is_reproducible():
    gap = synthetic_gap(effect=0.08, drift=0.0, noise=0.04, seed=5)
    assert did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=500, seed=11) == \
        did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=500, seed=11)


def test_bootstrap_interval_coverage():
    # A 95% interval should contain the true effect in most repeated datasets.
    # One seed is not a test (the first version of this test used one, and it
    # failed about 5% of the time by design); forty seeds are.
    hits = 0
    for seed in range(40):
        gap = synthetic_gap(effect=0.08, drift=0.02, noise=0.04, seed=seed)
        low, high = did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=400, seed=seed).ci_ddd
        hits += low < 0.08 < high
    # percentile bootstrap over ~10 weeks per window under-covers a little
    assert hits >= 32


def test_excluded_week_is_dropped():
    gap = synthetic_gap(effect=0.0, drift=0.0)
    # a large spike confined to the excluded Thanksgiving week must not move the estimate
    thanksgiving = (gap.index >= pd.Timestamp("2024-11-25")) & (gap.index <= pd.Timestamp("2024-12-01"))
    gap[thanksgiving] -= 1.0
    assert did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=50).ddd == pytest.approx(0.0)
    assert did.estimate(gap, data.STUDY.without_exclusions(), data.PLACEBO.without_exclusions(), n_boot=50).ddd > 0.05


def test_incomplete_window_raises():
    gap = synthetic_gap(effect=0.0, drift=0.0).drop(pd.Timestamp("2025-02-10"))
    with pytest.raises(ValueError, match="complete days"):
        did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=10)


def test_windows_are_whole_weeks_and_weekday_aligned():
    for w in (data.STUDY, data.PLACEBO):
        assert w.pre_start.weekday() == 0 and w.post_start.weekday() == 0      # Mondays
        assert w.pre_end.weekday() == 6 and w.post_end.weekday() == 6          # Sundays
        assert all(d.weekday() == 0 for d in w.exclude_weeks)
    assert data.STUDY.post_start > data.POLICY_START > data.STUDY.pre_end
    assert data.PLACEBO.post_start == date(2024, 1, 8)


def test_event_study_is_centred_on_pre_period():
    gap = synthetic_gap(effect=0.1, drift=0.0, noise=0.02, seed=2)
    frame = did.event_study(gap, data.STUDY)
    pre = frame[frame["week"] < 0]["relative_gap"]
    post = frame[frame["week"] >= 0]["relative_gap"]
    assert pre.mean() == pytest.approx(0.0, abs=1e-12)
    assert post.mean() == pytest.approx(0.1, abs=0.02)


def test_checksum_mismatch(tmp_path):
    path = tmp_path / "bad.parquet"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="checksum mismatch"):
        data.verify(path, next(iter(data.FILES.values())))
