"""Matplotlib figures for the README and results document."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

INK = "#1f2937"
ACCENT = "#0e6a70"
MUTED = "#9ca3af"
WARN = "#b45309"


def _finish(fig, ax, path: Path) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def event_study(policy: pd.DataFrame, placebo: pd.DataFrame, title: str, ylabel: str, path: Path) -> None:
    """Weekly gap relative to the pre-period mean, policy year vs placebo year, in percent."""
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for frame, color, label in ((placebo, MUTED, "Placebo year (2023-24, no policy)"),
                                (policy, ACCENT, "Policy year (2024-25)")):
        ax.plot(frame["week"], 100 * np.expm1(frame["relative_gap"]), marker="o", markersize=4,
                color=color, label=label)
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.axvline(-0.5, color=WARN, linestyle="--", linewidth=1)
    ax.text(-0.3, ax.get_ylim()[1], "5 Jan 2025 (holiday weeks omitted)", color=WARN, fontsize=8, va="top")
    ax.set_xlabel("Weeks relative to the first full post-policy week")
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    _finish(fig, ax, path)


def zone_separation(zones: pd.DataFrame, path: Path) -> None:
    """Same-zone charged share for Manhattan zones, coloured by the class assigned."""
    frame = zones[(zones["borough"] == "Manhattan") & (zones["intra_n"] >= 200)].sort_values("intra_charged")
    colors = {"charged": ACCENT, "boundary": WARN, "outside": MUTED}
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.bar(range(len(frame)), 100 * frame["intra_charged"], color=[colors[c] for c in frame["zone_class"]])
    ax.set_xticks([])
    ax.set_xlabel("Manhattan taxi zones with at least 200 same-zone trips, sorted")
    ax.set_ylabel("% of same-zone trips charged")
    ax.set_title("Which zones are inside? Charged (teal), boundary (amber, excluded), outside (grey)",
                 loc="left", color=INK, fontsize=10)
    _finish(fig, ax, path)
