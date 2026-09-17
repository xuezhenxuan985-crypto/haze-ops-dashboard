"""NEA station-level weather loader: rainfall, temperature, humidity, wind.

Five endpoints (rainfall 88 stations / 5-min; temperature & RH 18 stations /
~1-min; wind direction & speed 16 stations, 10-min means). There is NO
official station→region mapping: the 18-station temp/RH network and the
16-station wind network use the curated config.STATION_REGION table (based
on official coordinates + NEA town lists); unknown station IDs fall back to
the nearest region anchor. Rainfall's 88 estate gauges are auto-assigned to
the nearest anchor (approximation, noted in README).

Aggregation per region: temp/RH = mean, rainfall = sum of 5-min totals,
wind speed = mean × knots→km/h, wind direction = circular mean (unit
vectors) — reported as the direction the wind comes FROM.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime

import requests

import config
from .fetcher import NEA_LIMITER, http_get
from .models import RegionWeather

log = logging.getLogger(__name__)

_logged_unknown: set[str] = set()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_region(lat: float, lon: float) -> str:
    return min(
        config.REGION_ANCHORS,
        key=lambda r: _haversine_km(lat, lon, *config.REGION_ANCHORS[r]),
    )


def _station_region(station_id: str, lat: float, lon: float) -> str:
    region = config.STATION_REGION.get(station_id)
    if region is None:
        if station_id not in _logged_unknown:
            _logged_unknown.add(station_id)
            log.info("Station %s not in curated table; assigning nearest region", station_id)
        region = _nearest_region(lat, lon)
    return region


def _circular_mean(angles_deg: list[float]) -> float:
    xs = sum(math.cos(math.radians(a)) for a in angles_deg)
    ys = sum(math.sin(math.radians(a)) for a in angles_deg)
    return math.degrees(math.atan2(ys, xs)) % 360.0


def _parse_station_payload(payload: dict) -> tuple[dict[str, tuple[float, float]], dict[str, float], datetime]:
    """Return ({station_id: (lat, lon)}, {station_id: value}, latest timestamp)."""
    data = payload["data"]
    stations = {s["id"]: (s["location"]["latitude"], s["location"]["longitude"]) for s in data["stations"]}
    readings = data["readings"]
    if not readings:
        raise ValueError("weather payload had no readings")
    latest = readings[0]
    values = {r["stationId"]: float(r["value"]) for r in latest["data"] if r.get("value") is not None}
    ts = datetime.fromisoformat(latest["timestamp"])
    return stations, values, ts


def fetch_weather(session: requests.Session | None = None) -> tuple[dict[str, RegionWeather], datetime]:
    """Fetch all five endpoints; return {region: RegionWeather} + latest timestamp."""
    out = {r: RegionWeather(region=r) for r in config.REGIONS}
    latest_ts: datetime | None = None

    def note_ts(ts: datetime) -> None:
        nonlocal latest_ts
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts

    # Rainfall: sum 5-min totals per region (stations auto-assigned).
    resp = http_get(config.NEA_WEATHER_URLS["rainfall"], session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    stations, values, ts = _parse_station_payload(resp.json())
    note_ts(ts)
    for sid, value in values.items():
        loc = stations.get(sid)
        if loc is None:
            continue
        out[_station_region(sid, *loc)].rainfall_mm += value

    # Temperature: mean per region.
    resp = http_get(config.NEA_WEATHER_URLS["air_temperature"], session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    stations, values, ts = _parse_station_payload(resp.json())
    note_ts(ts)
    temps: dict[str, list[float]] = {r: [] for r in config.REGIONS}
    for sid, value in values.items():
        loc = stations.get(sid)
        if loc is None:
            continue
        temps[_station_region(sid, *loc)].append(value)
    for region, vals in temps.items():
        if vals:
            out[region].temp_c = round(sum(vals) / len(vals), 1)
            out[region].station_count = len(vals)

    # Relative humidity: mean per region.
    resp = http_get(config.NEA_WEATHER_URLS["relative_humidity"], session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    stations, values, ts = _parse_station_payload(resp.json())
    note_ts(ts)
    hums: dict[str, list[float]] = {r: [] for r in config.REGIONS}
    for sid, value in values.items():
        loc = stations.get(sid)
        if loc is None:
            continue
        hums[_station_region(sid, *loc)].append(value)
    for region, vals in hums.items():
        if vals:
            out[region].humidity_pct = round(sum(vals) / len(vals), 1)

    # Wind speed: mean (knots → km/h) per region.
    resp = http_get(config.NEA_WEATHER_URLS["wind_speed"], session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    stations, values, ts = _parse_station_payload(resp.json())
    note_ts(ts)
    speeds: dict[str, list[float]] = {r: [] for r in config.REGIONS}
    for sid, value in values.items():
        loc = stations.get(sid)
        if loc is None:
            continue
        speeds[_station_region(sid, *loc)].append(value)
    for region, vals in speeds.items():
        if vals:
            out[region].wind_speed_kmh = round(sum(vals) / len(vals) * config.KNOTS_TO_KMH, 1)

    # Wind direction: circular mean per region (direction wind comes FROM).
    resp = http_get(config.NEA_WEATHER_URLS["wind_direction"], session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    stations, values, ts = _parse_station_payload(resp.json())
    note_ts(ts)
    dirs: dict[str, list[float]] = {r: [] for r in config.REGIONS}
    for sid, value in values.items():
        loc = stations.get(sid)
        if loc is None:
            continue
        dirs[_station_region(sid, *loc)].append(value)
    for region, vals in dirs.items():
        if vals:
            out[region].wind_dir_deg = round(_circular_mean(vals), 0)

    return out, latest_ts or datetime.now().astimezone()
