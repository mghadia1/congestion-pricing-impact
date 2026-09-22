"""Download and verify the TLC files, and define the study windows.

Two six-month stretches are needed: October-March around the policy start
(5 January 2025) and the same stretch one year earlier, which serves as a
placebo. If the method finds an "effect" in the year with no policy, it is
picking up seasonality rather than the policy.
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

BASE = "https://d37ci6vzurychx.cloudfront.net"

# SHA-256 recorded 2026-09-22. TLC occasionally republishes a month; if a hash
# stops matching, re-run and re-record the results, never the hash alone.
FILES = {
    "yellow_tripdata_2023-10.parquet": "dc5f069476d350df802ed8120f3b39ec321c34cfa905381e87f608c78ca0c645",
    "yellow_tripdata_2023-11.parquet": "af203de0e73a92d640121f02a34326f25037d62380fc406237c87c2a4231ae58",
    "yellow_tripdata_2023-12.parquet": "ab4f4db11cb31484747f62eb507c13fcfaff290aaf59c13e6465dea0b1166b9c",
    "yellow_tripdata_2024-01.parquet": "c4d59da7bbc8abaeeeb1727947ee93d9891a71acb42854bd80db1571b2030510",
    "yellow_tripdata_2024-02.parquet": "c76c43c18c6c6664080dd920baab4928988d5786a6b65980792ca7cd796f9f20",
    "yellow_tripdata_2024-03.parquet": "2d4cdc8fb96726cdd3803b13b02d2e61e71d45720aff0ebc693a8bdd1f249823",
    "yellow_tripdata_2024-10.parquet": "d19fe05aa0b259af24eb47051735293287f1e6dc263ba04030ec1ab4c6ec2650",
    "yellow_tripdata_2024-11.parquet": "5ef321876de5007a7c147a347389133fc94fd7ac28f82eb1d57d8f2cf05cfd3b",
    "yellow_tripdata_2024-12.parquet": "41ebf7db80bebde60c58e5143c14cdf38ad04a0f3e3ff44215b3e240d55f6c78",
    "yellow_tripdata_2025-01.parquet": "9af277e4c0d3f9deb30644da822981e1e7df6af58313170fd3aa8a474485488a",
    "yellow_tripdata_2025-02.parquet": "037cba555a73663f3a51a2c27816e40e3feb364769942bdf122b9da31e377bd3",
    "yellow_tripdata_2025-03.parquet": "20c4b77cce457b7cfdae77c5069ca7dc91c167f876a41467f4502ab69487a186",
    "taxi_zone_lookup.csv": "1a99e105092230f8620f301edcca7f80d3080642ff404d28ed957d3fa222c8ed",
}

POLICY_START = date(2025, 1, 5)
SHIFT = timedelta(days=364)   # 52 weeks: the placebo year keeps every weekday aligned


@dataclass(frozen=True)
class Windows:
    """Pre and post windows, each a run of whole Monday-to-Sunday weeks.

    The two weeks around New Year (23 Dec - 5 Jan) are left out: they mix the
    holidays with the policy's first day, and would dominate any estimate.
    """

    label: str
    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    # Mondays of weeks to leave out of the estimate (not the event-study plot).
    exclude_weeks: tuple[date, ...] = ()

    def shifted(self, label: str, exclude_weeks: tuple[date, ...] = ()) -> "Windows":
        return Windows(label, self.pre_start - SHIFT, self.pre_end - SHIFT,
                       self.post_start - SHIFT, self.post_end - SHIFT, exclude_weeks)

    def without_exclusions(self) -> "Windows":
        return Windows(self.label, self.pre_start, self.pre_end, self.post_start, self.post_end)


# Thanksgiving moves: 28 Nov 2024 but 23 Nov 2023, so the 52-week shift puts the
# two holiday weeks in different places and each shows up as a spurious dip in
# the other year's comparison. Each year's Thanksgiving week is left out of its
# own pre-period. This was decided after seeing the dips in the event-study
# chart, so the estimate without the exclusion is reported alongside.
STUDY = Windows("policy year", date(2024, 10, 7), date(2024, 12, 22), date(2025, 1, 6), date(2025, 3, 30),
                exclude_weeks=(date(2024, 11, 25),))
PLACEBO = STUDY.shifted("placebo year", exclude_weeks=(date(2023, 11, 20),))


def url_for(name: str) -> str:
    folder = "misc" if name.endswith(".csv") else "trip-data"
    return f"{BASE}/{folder}/{name}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> None:
    actual = sha256_of(path)
    if actual != expected:
        raise ValueError(f"checksum mismatch for {path.name}: {actual}")


def download(destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, expected in FILES.items():
        path = destination / name
        if not path.exists():
            urllib.request.urlretrieve(url_for(name), path)
        verify(path, expected)
        paths.append(path)
    return paths
