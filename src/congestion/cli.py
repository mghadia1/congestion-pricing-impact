"""Command line: `congestion download | analyze`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from congestion import analysis, charts, data, did

# Each specification: (name, frame key, group column, value column, treated, control)
SPECS = (
    ("trips_all_records", "daily_counts", "trip_group", "trips", "treated", "control"),
    ("trips_excluding_payment_type_0", "daily_counts", "trip_group", "trips_excl_pt0", "treated", "control"),
    ("speed_median_mph", "daily_speed", "speed_group", "median_mph", "inside", "north"),
    ("speed_median_mph_excluding_payment_type_0", "daily_speed", "speed_group", "median_mph_excl_pt0", "inside", "north"),
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="congestion")
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="fetch and checksum 12 months of trips + zone lookup (~700 MB)")
    dl.add_argument("--destination", type=Path, default=Path("data/raw"))
    an = sub.add_parser("analyze", help="classify zones, build daily series, estimate DiD / DDD")
    an.add_argument("--raw", type=Path, default=Path("data/raw"))
    an.add_argument("--out", type=Path, default=Path("outputs"))
    an.add_argument("--n-boot", type=int, default=5_000)
    args = parser.parse_args(argv)

    if args.command == "download":
        for path in data.download(args.destination):
            print(path)
    else:
        print(json.dumps(analyze(args.raw, args.out, args.n_boot), indent=2))


def analyze(raw: Path, out: Path, n_boot: int = 5_000) -> dict:
    for name, expected in data.FILES.items():
        data.verify(raw / name, expected)
    out.mkdir(parents=True, exist_ok=True)
    con = analysis.connect_dir(raw)

    zones = analysis.zone_classes(con)
    frames = {name: analysis.run(con, name) for name in analysis.QUERIES}
    zones.to_csv(out / "zone_classification.csv", index=False)
    for name, frame in frames.items():
        frame.to_csv(out / f"{name}.csv", index=False)

    estimates, events = {}, {}
    for name, key, group, value, treated, control in SPECS:
        gap = did.daily_gap(frames[key], group, value, treated, control)
        result = did.estimate(gap, data.STUDY, data.PLACEBO, n_boot=n_boot)
        with_holidays = did.estimate(gap, data.STUDY.without_exclusions(), data.PLACEBO.without_exclusions(),
                                     n_boot=n_boot)
        estimates[name] = {
            **result.as_percent(),
            "sensitivity_thanksgiving_weeks_kept": with_holidays.as_percent(),
            "pre_trend_log_points_per_week": {
                "policy_year": round(did.pre_trend_slope(gap, data.STUDY), 5),
                "placebo_year": round(did.pre_trend_slope(gap, data.PLACEBO), 5),
            },
        }
        events[name] = (did.event_study(gap, data.STUDY), did.event_study(gap, data.PLACEBO))
        events[name][0].assign(spec=name).to_csv(out / f"event_study_{name}.csv", index=False)

    charts.zone_separation(zones, out / "zone_separation.png")
    charts.event_study(*events["trips_all_records"], "Trips touching the zone vs trips that don't",
                       "Gap vs pre-period (%)", out / "event_study_trips.png")
    charts.event_study(*events["speed_median_mph"], "Median speed inside the zone vs upper Manhattan",
                       "Gap vs pre-period (%)", out / "event_study_speed.png")

    fee = frames["fee_by_group"].set_index("trip_group")
    summary = {
        "zones": zones["zone_class"].value_counts().to_dict(),
        "fee_paid_pct_after_policy": fee["pct_charged"].to_dict(),
        "trips_after_policy_by_group": fee["trips"].to_dict(),
        "windows": {
            "policy_year": [str(data.STUDY.pre_start), str(data.STUDY.pre_end), str(data.STUDY.post_start), str(data.STUDY.post_end)],
            "placebo_year": [str(data.PLACEBO.pre_start), str(data.PLACEBO.pre_end), str(data.PLACEBO.post_start), str(data.PLACEBO.post_end)],
        },
        "estimates": estimates,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
