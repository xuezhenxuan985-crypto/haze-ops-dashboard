"""Synthetic but realistic data for offline demos / fallback.

Deterministic per scenario (seeded RNG, timestamps anchored to now) so
screenshots are reproducible while freshness UI still works. Returns the
same shapes as the live loaders.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import config
from .models import Reading, RegionPM25, RegionPSI, RegionWeather, RSSStatus, SourceHotspots

SGT = timezone(timedelta(hours=8))

# Scenario knobs. pm25_rise is the total drift over the 24-h window.
SCENARIOS: dict[str, dict] = {
    "clear_day": dict(
        pm25_base=22.0, pm25_amp=8.0, pm25_rise=0.0,
        region_offsets={"north": 2.0, "south": 5.0, "east": 0.0, "west": 4.0, "central": 8.0},
        hotspots={"sumatra": 8, "kalimantan": 3, "p_malaysia": 1},
        yesterday={"sumatra": 6, "kalimantan": 5, "p_malaysia": 0},
        wind_dir=90.0, wind_speed=12.0, rain=0.4, temp=29.5, humidity=75.0,
        alert=None, title="Demo: clear conditions",
    ),
    "moderate_haze": dict(
        pm25_base=60.0, pm25_amp=12.0, pm25_rise=30.0,
        region_offsets={"north": 4.0, "south": 8.0, "east": 2.0, "west": 6.0, "central": 18.0},
        hotspots={"sumatra": 120, "kalimantan": 65, "p_malaysia": 4},
        yesterday={"sumatra": 90, "kalimantan": 60, "p_malaysia": 3},
        wind_dir=135.0, wind_speed=9.0, rain=0.1, temp=31.0, humidity=68.0,
        alert=2, title="Demo: moderate transboundary haze",
    ),
    "haze_episode": dict(
        pm25_base=105.0, pm25_amp=25.0, pm25_rise=90.0,
        region_offsets={"north": 10.0, "south": 22.0, "east": 6.0, "west": 16.0, "central": 38.0},
        hotspots={"sumatra": 224, "kalimantan": 143, "p_malaysia": 9},
        yesterday={"sumatra": 98, "kalimantan": 130, "p_malaysia": 2},
        wind_dir=245.0, wind_speed=7.0, rain=0.0, temp=32.0, humidity=62.0,
        alert=3, title="Demo: active haze episode",
    ),
}

# Point-generation boxes per source (lon/lat ranges).
_POINT_BOXES = {
    "sumatra": ((99.0, 106.0), (-5.0, 3.0)),
    "kalimantan": ((108.5, 118.0), (-4.5, 4.0)),
    "p_malaysia": ((100.0, 104.5), (1.0, 6.5)),
}


def _hourly_stamps() -> list[datetime]:
    now = datetime.now(SGT).replace(minute=0, second=0, microsecond=0)
    return [now - timedelta(hours=23 - h) for h in range(24)]


def _psi_from_pm25(pm: float) -> float:
    """Approximate NEA piecewise 24-hr PSI sub-index for a 24-hr PM2.5 value."""
    if pm <= 55:
        return pm / 55.0 * 100.0
    if pm <= 150:
        return 100.0 + (pm - 55.0) * 100.0 / 95.0
    if pm <= 250:
        return 200.0 + (pm - 150.0)
    return 300.0 + (pm - 250.0)


def demo_fetch_pm25(scenario: str) -> tuple[dict[str, RegionPM25], datetime]:
    cfg = SCENARIOS[scenario]
    rng = np.random.default_rng(config.DEMO_SEEDS[scenario])
    stamps = _hourly_stamps()
    now = datetime.now(SGT)
    out: dict[str, RegionPM25] = {}
    for region in config.REGIONS:
        values = []
        for h, ts in enumerate(stamps):
            hour_of_day = ts.hour
            v = (
                cfg["pm25_base"]
                + cfg["region_offsets"][region]
                + cfg["pm25_amp"] * math.sin(2 * math.pi * (hour_of_day - 9) / 24)
                + cfg["pm25_rise"] * h / 23.0
                + rng.normal(0.0, 2.0)
            )
            values.append(max(3.0, round(v, 1)))
        readings = [Reading(ts, v) for ts, v in zip(stamps, values)]
        out[region] = RegionPM25(region=region, pm25_1h=values[-1], band=0, readings_24h=readings)
    return out, now


def demo_fetch_psi(scenario: str, pm25: dict[str, RegionPM25]) -> tuple[dict[str, RegionPSI], datetime]:
    cfg = SCENARIOS[scenario]
    out: dict[str, RegionPSI] = {}
    for region, r in pm25.items():
        pm24 = sum(x.value for x in r.readings_24h) / max(1, len(r.readings_24h))
        out[region] = RegionPSI(
            region=region,
            psi_24h=round(_psi_from_pm25(pm24), 1),
            pm25_24h=round(pm24, 1),
            tier=0,
        )
    return out, datetime.now(SGT)


def demo_fetch_weather(scenario: str) -> tuple[dict[str, RegionWeather], datetime]:
    cfg = SCENARIOS[scenario]
    rng = np.random.default_rng(config.DEMO_SEEDS[scenario] + 1)
    out: dict[str, RegionWeather] = {}
    dir_spread = {"north": -15.0, "south": 0.0, "east": 10.0, "west": -5.0, "central": 5.0}
    for region in config.REGIONS:
        out[region] = RegionWeather(
            region=region,
            temp_c=round(cfg["temp"] + rng.normal(0, 0.8), 1),
            humidity_pct=round(cfg["humidity"] + rng.normal(0, 4), 1),
            wind_speed_kmh=round(max(1.0, cfg["wind_speed"] + rng.normal(0, 1.5)), 1),
            wind_dir_deg=round((cfg["wind_dir"] + dir_spread[region] + rng.normal(0, 12)) % 360, 0),
            rainfall_mm=round(max(0.0, cfg["rain"] + rng.normal(0, 0.15)), 2),
            station_count=3,
        )
    return out, datetime.now(SGT)


def demo_fetch_hotspots(scenario: str) -> tuple[dict[str, SourceHotspots], datetime]:
    cfg = SCENARIOS[scenario]
    rng = np.random.default_rng(config.DEMO_SEEDS[scenario] + 2)
    now = datetime.now(SGT)
    out: dict[str, SourceHotspots] = {}
    for source in config.ASMC_HOTSPOT_REGIONS:
        n = cfg["hotspots"][source]
        (lon_lo, lon_hi), (lat_lo, lat_hi) = _POINT_BOXES[source]
        points = [(round(rng.uniform(lon_lo, lon_hi), 4), round(rng.uniform(lat_lo, lat_hi), 4)) for _ in range(n)]
        out[source] = SourceHotspots(
            source=source, count=n, points=points,
            yesterday_count=cfg["yesterday"][source], fetched_at=now,
        )
    return out, now


def demo_fetch_rss(scenario: str) -> RSSStatus:
    cfg = SCENARIOS[scenario]
    return RSSStatus(level=cfg["alert"], title=cfg["title"], link="", fetched_at=datetime.now(SGT))


def demo_history_df(pm25: dict[str, RegionPM25]) -> pd.DataFrame:
    """Pivot the demo 24-h series into the same shape as live history."""
    rows = [
        {"timestamp": r.timestamp, "region": region, "pm25": r.value}
        for region, data in pm25.items()
        for r in data.readings_24h
    ]
    df = pd.DataFrame(rows)
    return df.pivot_table(index="timestamp", columns="region", values="pm25")
