"""Difference-in-differences on a daily gap series, with a placebo year.

The unit of analysis is the daily *gap* between two groups:

    gap_d = log(treated_d) - log(control_d)

Taking logs turns "treated fell 8% more than control" into a difference of
gaps. Then

    DiD = mean(gap, post weeks) - mean(gap, pre weeks)

measures how much the gap moved when the policy began. This only identifies
the policy's effect if the gap would otherwise have stayed flat ("parallel
trends"). It will not stay flat if the two groups have different seasonal
patterns: Midtown in December is not the Bronx in December. So the same DiD is
computed on the year before, over the same weekday-aligned weeks, when no
policy happened. That placebo DiD is the seasonal drift, and

    DDD = DiD(policy year) - DiD(placebo year)

is the estimate that survives it.

Uncertainty: days within a week are strongly correlated, so resampling single
days would give falsely narrow intervals. The bootstrap resamples whole
Monday-to-Sunday weeks instead, separately within each of the four windows.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from congestion.data import Windows


def daily_gap(frame: pd.DataFrame, group_col: str, value_col: str, treated: str, control: str) -> pd.Series:
    """log(treated) - log(control) per day, indexed by date."""
    wide = frame.pivot(index="pickup_date", columns=group_col, values=value_col)
    wide.index = pd.to_datetime(wide.index)
    return np.log(wide[treated]) - np.log(wide[control])


def _window(gap: pd.Series, start, end) -> pd.Series:
    part = gap[(gap.index >= pd.Timestamp(start)) & (gap.index <= pd.Timestamp(end))]
    expected_days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    if len(part) != expected_days or part.isna().any():
        raise ValueError(f"window {start}..{end}: expected {expected_days} complete days, got {part.notna().sum()}")
    return part


def _weeks(series: pd.Series, exclude: tuple = ()) -> np.ndarray:
    """Reshape a whole-weeks daily series into (n_weeks, 7), dropping excluded weeks."""
    if exclude:
        mondays = series.index - pd.to_timedelta(series.index.weekday, unit="D")
        series = series[~mondays.isin(pd.to_datetime(list(exclude)))]
    values = series.to_numpy()
    if len(values) % 7:
        raise ValueError("window must be a whole number of weeks")
    return values.reshape(-1, 7)


def did(gap: pd.Series, windows: Windows) -> float:
    pre = _weeks(_window(gap, windows.pre_start, windows.pre_end), windows.exclude_weeks)
    post = _weeks(_window(gap, windows.post_start, windows.post_end), windows.exclude_weeks)
    return float(post.mean() - pre.mean())


@dataclass(frozen=True)
class Estimate:
    did_policy: float
    did_placebo: float
    ddd: float
    ci_did_policy: tuple[float, float]
    ci_did_placebo: tuple[float, float]
    ci_ddd: tuple[float, float]
    n_boot: int

    def as_percent(self) -> dict:
        """Log differences converted to percent changes: exp(x) - 1."""
        pct = lambda x: round(100 * float(np.expm1(x)), 2)  # noqa: E731
        return {
            "did_policy_pct": pct(self.did_policy),
            "did_policy_ci_pct": [pct(v) for v in self.ci_did_policy],
            "did_placebo_pct": pct(self.did_placebo),
            "did_placebo_ci_pct": [pct(v) for v in self.ci_did_placebo],
            "ddd_pct": pct(self.ddd),
            "ddd_ci_pct": [pct(v) for v in self.ci_ddd],
            "n_boot": self.n_boot,
        }


def estimate(gap: pd.Series, study: Windows, placebo: Windows, n_boot: int = 5_000, seed: int = 0) -> Estimate:
    blocks = {
        name: _weeks(_window(gap, start, end), exclude)
        for name, (start, end, exclude) in {
            "study_pre": (study.pre_start, study.pre_end, study.exclude_weeks),
            "study_post": (study.post_start, study.post_end, study.exclude_weeks),
            "placebo_pre": (placebo.pre_start, placebo.pre_end, placebo.exclude_weeks),
            "placebo_post": (placebo.post_start, placebo.post_end, placebo.exclude_weeks),
        }.items()
    }
    week_means = {name: weeks.mean(axis=1) for name, weeks in blocks.items()}

    def point(means: dict) -> tuple[float, float]:
        d_study = means["study_post"].mean() - means["study_pre"].mean()
        d_placebo = means["placebo_post"].mean() - means["placebo_pre"].mean()
        return d_study, d_placebo

    d_study, d_placebo = point(week_means)

    rng = np.random.default_rng(seed)
    draws = np.empty((n_boot, 2))
    for b in range(n_boot):
        resampled = {
            name: means[rng.integers(0, len(means), len(means))] for name, means in week_means.items()
        }
        draws[b] = point(resampled)
    ddd_draws = draws[:, 0] - draws[:, 1]

    def ci(values: np.ndarray) -> tuple[float, float]:
        return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))

    return Estimate(
        did_policy=float(d_study),
        did_placebo=float(d_placebo),
        ddd=float(d_study - d_placebo),
        ci_did_policy=ci(draws[:, 0]),
        ci_did_placebo=ci(draws[:, 1]),
        ci_ddd=ci(ddd_draws),
        n_boot=n_boot,
    )


def event_study(gap: pd.Series, windows: Windows) -> pd.DataFrame:
    """Weekly mean gap relative to the pre-period mean, for plotting.

    Week 0 is the first post week. Pre weeks hovering around zero is what
    parallel trends looks like; a pre-period drift is a warning sign.
    """
    pre = _window(gap, windows.pre_start, windows.pre_end)
    post = _window(gap, windows.post_start, windows.post_end)
    baseline = pre.mean()
    pre_weeks = _weeks(pre).mean(axis=1) - baseline
    post_weeks = _weeks(post).mean(axis=1) - baseline
    return pd.DataFrame({
        "week": list(range(-len(pre_weeks), 0)) + list(range(len(post_weeks))),
        "relative_gap": np.concatenate([pre_weeks, post_weeks]),
        "window": windows.label,
    })


def pre_trend_slope(gap: pd.Series, windows: Windows) -> float:
    """Least-squares slope of the weekly pre-period gap, in log points per week."""
    weekly = _weeks(_window(gap, windows.pre_start, windows.pre_end), windows.exclude_weeks).mean(axis=1)
    x = np.arange(len(weekly))
    return float(np.polyfit(x, weekly, 1)[0])
