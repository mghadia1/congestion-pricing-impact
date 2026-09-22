"""DuckDB over the twelve monthly parquet files."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import duckdb
import pandas as pd

from congestion import data

QUERIES = ("daily_counts", "daily_speed", "fee_by_group")


def _sql(name: str) -> str:
    return resources.files("congestion").joinpath("sql", f"{name}.sql").read_text()


def connect(
    trips: list[Path] | pd.DataFrame,
    zones: Path | pd.DataFrame,
    data_window: tuple[str, str] = ("2023-10-01", "2025-04-01"),
    classify_window: tuple[str, str] = ("2025-01-06", "2025-03-31"),
):
    con = duckdb.connect()
    for name, value in (("data_start", data_window[0]), ("data_end", data_window[1]),
                        ("classify_start", classify_window[0]), ("classify_end", classify_window[1])):
        con.execute(f"SET VARIABLE {name} = ?::TIMESTAMP", [value])
    if isinstance(trips, pd.DataFrame):
        con.register("raw_trips", trips)
    else:
        # union_by_name: cbd_congestion_fee exists only in the 2025 files
        con.read_parquet([str(p) for p in trips], union_by_name=True).create_view("raw_trips")
    if isinstance(zones, pd.DataFrame):
        con.register("raw_zones", zones)
    else:
        con.read_csv(str(zones)).create_view("raw_zones")
    con.execute(_sql("00_views"))
    con.execute(_sql("zone_classification"))
    return con


def connect_dir(raw: Path):
    trips = sorted(raw / name for name in data.FILES if name.endswith(".parquet"))
    return connect(trips, raw / "taxi_zone_lookup.csv")


def run(con, name: str) -> pd.DataFrame:
    if name not in QUERIES:
        raise KeyError(f"unknown query {name!r}; choose from {QUERIES}")
    return con.execute(_sql(name)).df()


def zone_classes(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM zone_class ORDER BY zone_class, location_id").df()
