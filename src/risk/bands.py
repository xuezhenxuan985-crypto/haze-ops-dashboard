"""Official NEA banding + trend slope (own OLS — no scipy dependency).

Band thresholds verified against haze.gov.sg (2026-09-17). NOTE: 1-hr
PM2.5 Band 4 starts at >=251, not >250.
"""
from __future__ import annotations

import config
from ..data.models import Reading


def pm25_band(value: float) -> int:
    """1-hr PM2.5 band: 1 Normal, 2 Elevated, 3 High, 4 Very High."""
    v = float(value)
    if v <= 55:
        return 1
    if v <= 150:
        return 2
    if v <= 250:
        return 3
    return 4  # >= 251


def psi_band(value: float) -> int:
    """24-hr PSI tier: 1 Good, 2 Moderate, 3 Unhealthy, 4 Very unhealthy, 5 Hazardous."""
    v = float(value)
    if v <= 50:
        return 1
    if v <= 100:
        return 2
    if v <= 200:
        return 3
    if v <= 300:
        return 4
    return 5  # > 300


def trend_slope(readings: list[Reading]) -> float | None:
    """OLS slope over the last hourly points, µg/m³ per hour. None if <3 points."""
    if len(readings) < 3:
        return None
    readings = readings[-config.TREND_WINDOW_POINTS:]
    xs = list(range(len(readings)))
    ys = [r.value for r in readings]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
