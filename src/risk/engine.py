"""Regional risk score: PM2.5 band + 3-h trend + transport + weather modifiers.

Deterministic and unit-tested at exact boundaries. Score is clamped to
[1, 4]; level cutoffs are 1.5 / 2.5 / 3.5.
"""
from __future__ import annotations

import config
from ..data.models import RegionWeather, TransportRisk


def compute_region_risk(
    pm25_band: int,
    trend_3h: float | None,
    transport: TransportRisk | None,
    weather: RegionWeather,
) -> tuple[int, float]:
    score = float(pm25_band)
    if trend_3h is not None:
        if trend_3h >= config.TREND_STRONG_RISE:
            score += 1.0
        elif trend_3h >= config.TREND_MILD_RISE:
            score += 0.5
        elif trend_3h <= config.TREND_STRONG_FALL:
            score -= 1.0
        elif trend_3h <= config.TREND_MILD_FALL:
            score -= 0.5
    if transport is not None:
        score += config.TRANSPORT_LEVEL_ADDERS.get(transport.level, 0.0)
    if weather.rainfall_mm >= config.RAIN_SUPPRESSION_MM:
        score += config.RAIN_SUPPRESSION_ADDER
    if weather.wind_speed_kmh is not None and weather.wind_speed_kmh >= config.WIND_DISPERSION_KMH:
        score += config.WIND_DISPERSION_ADDER
    score = min(4.0, max(1.0, score))
    level = 1 if score <= 1.5 else 2 if score <= 2.5 else 3 if score <= 3.5 else 4
    return level, round(score, 1)
