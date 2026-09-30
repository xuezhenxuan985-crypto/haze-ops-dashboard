"""Historical regional analysis: which regions see haze problems most often.

Pure functions over (timestamp, value) series — no pandas, no I/O, so the
layer rule holds (risk/ imports only config + models). The pivoted
DataFrame from the data layer is duck-typed via analysis_from_history.

`ols_fit` is the shared ordinary-least-squares helper; bands.trend_slope
(the 3-h trend) delegates to it, and the 14-day slope per region reuses it
over daily means — the "linear regression" view of history the user asked
for: a slope (µg/m³ per day) plus R² saying how consistent the trend is.
"""
from __future__ import annotations

import statistics
from datetime import datetime

import config
from ..data.models import RegionAnalysis


def ols_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Ordinary least squares: (slope, intercept, r²). Needs >= 2 points."""
    n = len(xs)
    if n < 2:
        raise ValueError("ols_fit needs at least 2 points")
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0, y_mean, 1.0  # all x identical: flat fit through the mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    intercept = y_mean - slope * x_mean
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return slope, intercept, r2


def compute_region_analysis(
    rows_by_region: dict[str, list[tuple[datetime, float]]],
) -> dict[str, RegionAnalysis]:
    """Per-region summary over (timestamp, value) rows.

    Stats: mean / median / peak, hours above each band edge, share of hours
    elevated (>55). Trend: OLS slope over DAILY means (µg/m³ per day) — the
    "is this region getting better or worse" number. Fewer than 3 distinct
    days of data -> slope and r² are None.
    """
    out: dict[str, RegionAnalysis] = {}
    for region in config.REGIONS:
        out[region] = _region_analysis(region, rows_by_region.get(region) or [])
    return out


def _region_analysis(region: str, rows: list[tuple[datetime, float]]) -> RegionAnalysis:
    values = [v for _, v in rows]
    n = len(values)
    if n == 0:
        return RegionAnalysis(
            region=region, hours=0, mean=0.0, median=0.0, max=0.0,
            hours_elevated=0, hours_high=0, hours_vhigh=0,
            pct_elevated=0.0, slope_per_day=None, r2=None,
        )
    mean = sum(values) / n
    peak = max(values)
    hours_elevated = sum(1 for v in values if v > 55)
    hours_high = sum(1 for v in values if v > 150)
    hours_vhigh = sum(1 for v in values if v > 250)
    pct_elevated = hours_elevated / n * 100.0

    # Daily means -> long-window OLS slope.
    daily: dict[datetime, list[float]] = {}
    for ts, v in rows:
        daily.setdefault(ts.astimezone().date(), []).append(v)
    days = sorted(daily)
    slope = r2 = None
    if len(days) >= 3:
        slope, _, r2 = ols_fit(
            [float(i) for i in range(len(days))],
            [sum(daily[d]) / len(daily[d]) for d in days],
        )
        slope = round(slope, 2)
        r2 = round(r2, 3)
    return RegionAnalysis(
        region=region, hours=n, mean=round(mean, 1),
        median=round(statistics.median(values), 1), max=round(peak, 1),
        hours_elevated=hours_elevated, hours_high=hours_high,
        hours_vhigh=hours_vhigh, pct_elevated=round(pct_elevated, 1),
        slope_per_day=slope, r2=r2,
    )


def analysis_from_history(df) -> dict[str, RegionAnalysis]:
    """Convert a pivoted history DataFrame (region columns, hourly index)
    into per-region analysis. Duck-typed so risk/ stays pandas-free."""
    rows_by_region: dict[str, list[tuple[datetime, float]]] = {}
    for region in config.REGIONS:
        if region not in getattr(df, "columns", []):
            continue
        series = df[region].dropna()
        rows_by_region[region] = [
            (ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts, float(v))
            for ts, v in series.items()
        ]
    return compute_region_analysis(rows_by_region)
