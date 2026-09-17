"""Transport risk: hotspot activity weighted by distance and wind sector.

Meteorological wind direction is the direction the wind comes FROM, so a
hotspot's smoke travels toward Singapore when the wind direction matches
the bearing FROM Singapore TO the hotspot (within ±45°). This is an
early-warning factor, NOT a PM2.5 forecast.
"""
from __future__ import annotations

import math

import config
from ..data.models import SourceHotspots, TransportRisk


def angle_diff(a: float, b: float) -> float:
    """Smallest angle between two bearings in degrees (handles 0/360 wrap)."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_from_sg(lon: float, lat: float) -> float:
    """Initial bearing FROM Singapore TO the given point, degrees 0-360."""
    lat1, lon1 = config.SINGAPORE_POINT
    p1, p2 = math.radians(lat1), math.radians(lat)
    dl = math.radians(lon - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _distance_weight(km: float) -> float:
    if km < config.DISTANCE_BANDS_KM[0][0]:
        return config.DISTANCE_BANDS_KM[0][1]
    if km < config.DISTANCE_BANDS_KM[1][0]:
        return config.DISTANCE_BANDS_KM[1][1]
    return 0.3


def compute_transport_risk(
    hotspots: dict[str, SourceHotspots],
    wind_dir_deg: float | None,
    wind_speed_kmh: float | None = None,
) -> TransportRisk:
    """Score every hotspot point; sector-match points are the early-warning signal."""
    score = 0.0
    upwind = 0
    total = 0
    upwind_by_source: dict[str, int] = {}
    for src in hotspots.values():
        for lon, lat in src.points:
            total += 1
            # SINGAPORE_POINT is (lat, lon); haversine_km takes (lon, lat).
            d = haversine_km(lon, lat, config.SINGAPORE_POINT[1], config.SINGAPORE_POINT[0])
            w_d = _distance_weight(d)
            b = bearing_from_sg(lon, lat)
            if wind_dir_deg is None:
                w = config.WEIGHT_NO_WIND
            elif angle_diff(wind_dir_deg, b) <= config.SECTOR_HALF_WIDTH_DEG:
                w = config.WEIGHT_SECTOR_MATCH
                upwind += 1
                upwind_by_source[src.source] = upwind_by_source.get(src.source, 0) + 1
            else:
                w = config.WEIGHT_SECTOR_MISMATCH
            score += w_d * w
    # Surge: today's count at least double yesterday's for any source.
    for src in hotspots.values():
        if src.yesterday_count and src.count >= config.HOTSPOT_SURGE_RATIO * src.yesterday_count:
            score *= config.HOTSPOT_SURGE_FACTOR
            break
    # Levels: 0 none, 1 (0, 20), 2 [20, 80), 3 [80, 200), 4 [200, ∞).
    # TRANSPORT_THRESHOLDS holds the entry score for levels 2..4.
    level = 0
    if score > 0:
        level = 1
        for i, threshold in enumerate(config.TRANSPORT_THRESHOLDS):
            if score >= threshold:
                level = i + 2
    dominant = max(upwind_by_source, key=upwind_by_source.get) if upwind_by_source else None
    return TransportRisk(
        level=level,
        score=round(score, 1),
        upwind_points=upwind,
        dominant_source=dominant,
        wind_available=wind_dir_deg is not None,
        total_points=total,
    )
