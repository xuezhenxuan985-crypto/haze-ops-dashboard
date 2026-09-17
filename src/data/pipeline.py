"""Composition root: fetch (live or demo), enrich, compute risk, assemble.

Layering note: pipeline is the ONE module that imports both data/ and
risk/ — fetchers stay free of risk logic, risk stays pure, the UI renders.
All Streamlit caching lives here so data/ and risk/ never import Streamlit.

Cache policy: loaders are keyed by force_version so "Refresh now" actually
refetches; on failure each loader falls back to the last good result
(module-level store, survives reruns within the server process). Staleness
is surfaced via freshness timestamps and flags, never silently.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import config
from ..risk import advisory, bands, engine, transport
from . import demo_data, history, hotspots, nea_pm25, nea_psi, nea_weather
from .models import (Reading, RegionAdvisory, RegionPM25, RegionPSI, RegionWeather,
                     RSSStatus, Snapshot, SourceHotspots)

log = logging.getLogger(__name__)

SGT = timezone(timedelta(hours=8))
_last_good: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Cached live loaders (guarded with last-good fallback)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=config.TTL_PM25, show_spinner=False)
def _load_pm25(force_version: int) -> tuple[dict[str, RegionPM25] | None, datetime | None]:
    try:
        result = nea_pm25.fetch_pm25()
        _last_good["pm25"] = result
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("pm25 fetch failed: %s", exc)
        return _last_good.get("pm25") or (None, None)


@st.cache_data(ttl=config.TTL_PSI, show_spinner=False)
def _load_psi(force_version: int) -> tuple[dict[str, RegionPSI] | None, datetime | None]:
    try:
        result = nea_psi.fetch_psi()
        _last_good["psi"] = result
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("psi fetch failed: %s", exc)
        return _last_good.get("psi") or (None, None)


@st.cache_data(ttl=config.TTL_WEATHER, show_spinner=False)
def _load_weather(force_version: int) -> tuple[dict[str, RegionWeather] | None, datetime | None]:
    try:
        result = nea_weather.fetch_weather()
        _last_good["weather"] = result
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("weather fetch failed: %s", exc)
        return _last_good.get("weather") or (None, None)


@st.cache_data(ttl=config.TTL_HOTSPOTS, show_spinner=False)
def _load_hotspots(force_version: int) -> dict[str, SourceHotspots]:
    """ASMC text files first; KML fallback; yesterday counts best-effort."""
    try:
        sources = hotspots.fetch_asmc_hotspots()
        if not sources:
            kml = hotspots.fetch_asmc_kml()
            if kml:
                now = datetime.now(SGT)
                for source in config.ASMC_HOTSPOT_REGIONS:
                    pts = kml.get(source)
                    if pts:
                        sources[source] = SourceHotspots(source=source, count=len(pts), points=pts, fetched_at=now)
        daily = hotspots.fetch_asmc_daily_counts()
        if daily:
            yesterday = (datetime.now(SGT) - timedelta(days=1)).strftime("%Y-%m-%d")
            row = daily.get(yesterday) or {}
            for source, s in sources.items():
                if s.yesterday_count is None and row.get(source):
                    s.yesterday_count = row[source]
        _last_good["hotspots"] = sources
        return sources
    except Exception as exc:  # noqa: BLE001
        log.warning("hotspot fetch failed: %s", exc)
        return _last_good.get("hotspots") or {}


@st.cache_data(ttl=config.TTL_FIRMS, show_spinner=False)
def _load_firms(firms_key: str) -> tuple[list[dict] | None, str | None]:
    if not firms_key:
        return None, None
    return hotspots.fetch_firms(firms_key)


@st.cache_data(ttl=config.TTL_RSS, show_spinner=False)
def _load_rss(force_version: int) -> RSSStatus:
    return hotspots.fetch_rss()


@st.cache_data(ttl=config.TTL_HISTORY, show_spinner=False)
def _load_history(force_version: int) -> pd.DataFrame | None:
    return history.load_pm25_history()


# ---------------------------------------------------------------------------
# Shared assembly
# ---------------------------------------------------------------------------
def _island_wind(weather: dict[str, RegionWeather]) -> tuple[float | None, float | None]:
    """Island-wide wind: station-weighted circular mean direction, mean speed."""
    xs = ys = wsum = 0.0
    speeds: list[float] = []
    for w in weather.values():
        n = max(1, w.station_count)
        if w.wind_dir_deg is not None:
            rad = math.radians(w.wind_dir_deg)
            xs += n * math.cos(rad)
            ys += n * math.sin(rad)
            wsum += n
        if w.wind_speed_kmh is not None:
            speeds.append(w.wind_speed_kmh)
    direction = (math.degrees(math.atan2(ys, xs)) + 360.0) % 360.0 if wsum else None
    speed = round(sum(speeds) / len(speeds), 1) if speeds else None
    return direction, speed


def assemble_snapshot(
    *,
    mode: str,
    pm25: dict[str, RegionPM25],
    psi: dict[str, RegionPSI],
    weather: dict[str, RegionWeather],
    hotspots_: dict[str, SourceHotspots],
    rss: RSSStatus,
    history_df: pd.DataFrame | None,
    firms_points: list[dict],
    flags: list[str],
    freshness: dict[str, datetime | None],
) -> Snapshot:
    now = datetime.now(SGT)
    for r in pm25.values():
        r.band = bands.pm25_band(r.pm25_1h)
    for r in psi.values():
        r.tier = bands.psi_band(r.psi_24h)
    # Merge persisted history into each region's 24-h series (live mode only;
    # demo series are generated complete). Dedupe by timestamp.
    if mode == "live" and history_df is not None:
        for region in config.REGIONS:
            r = pm25.get(region)
            if r is None or region not in history_df.columns:
                continue
            merged = {rd.timestamp: rd for rd in r.readings_24h}
            for ts, v in history_df[region].dropna().items():
                merged[ts.to_pydatetime()] = Reading(ts.to_pydatetime(), float(v))
            r.readings_24h = sorted(merged.values(), key=lambda x: x.timestamp)
    for r in pm25.values():
        r.trend_3h = bands.trend_slope(r.readings_24h[-config.TREND_WINDOW_POINTS:])

    wind_dir, wind_speed = _island_wind(weather)
    transport_risk = transport.compute_transport_risk(hotspots_, wind_dir, wind_speed)

    advisories: dict[str, RegionAdvisory] = {}
    for region in config.REGIONS:
        r = pm25.get(region)
        w = weather.get(region)
        if r is None or w is None:
            continue
        p = psi.get(region)
        level, score = engine.compute_region_risk(r.band, r.trend_3h, transport_risk, w)
        advisories[region] = RegionAdvisory(
            region=region,
            risk_level=level,
            risk_score=score,
            pm25_action_key=advisory.advisory_for_pm25(r.band),
            psi_action_key=advisory.advisory_for_psi(p.tier) if p else "",
            matrix=advisory.work_matrix_for_psi(p.tier) if p else None,
            factors=advisory.explain_factors(r, p, w, transport_risk),
        )
    return Snapshot(
        mode=mode,
        fetched_at=now,
        freshness=freshness,
        pm25=pm25,
        psi=psi,
        weather=weather,
        hotspots=hotspots_,
        transport=transport_risk,
        advisories=advisories,
        rss=rss,
        history_df=history_df,
        firms_points=firms_points,
        flags=flags,
    )


def _demo_inputs(scenario: str):
    pm25, t1 = demo_data.demo_fetch_pm25(scenario)
    psi, t2 = demo_data.demo_fetch_psi(scenario, pm25)
    weather, t3 = demo_data.demo_fetch_weather(scenario)
    sources, t4 = demo_data.demo_fetch_hotspots(scenario)
    rss = demo_data.demo_fetch_rss(scenario)
    return dict(
        mode="demo", pm25=pm25, psi=psi, weather=weather, hotspots_=sources, rss=rss,
        history_df=demo_data.demo_history_df(pm25), firms_points=[],
        flags=["demo_data_note"],
        freshness={"pm25": t1, "psi": t2, "weather": t3, "hotspots": t4, "rss": rss.fetched_at},
    )


# ---------------------------------------------------------------------------
# Public entry point (cached)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=config.TTL_SNAPSHOT, show_spinner=False)
def get_snapshot(mode: str, scenario: str, force_version: int, firms_key: str) -> Snapshot | None:
    """Fetch + assemble. Returns None when nothing renderable exists."""
    if mode == "demo":
        if scenario not in config.DEMO_SCENARIOS:
            scenario = config.DEMO_SCENARIOS[0]
        return assemble_snapshot(**_demo_inputs(scenario))

    flags: list[str] = []
    pm25, pm25_ts = _load_pm25(force_version)
    if pm25 is None:
        flags.append("flag_stale_pm25")
    psi, psi_ts = _load_psi(force_version)
    if psi is None:
        flags.append("flag_stale_psi")
    weather, weather_ts = _load_weather(force_version)
    if weather is None:
        flags.append("flag_stale_weather")
    if pm25 is None or weather is None:
        return None  # nothing renderable — UI shows the unavailable state

    sources = _load_hotspots(force_version)
    if not sources:
        flags.append("flag_stale_hotspots")
    rss = _load_rss(force_version)
    history_df = _load_history(force_version)

    # FIRMS enrichment (optional key) + fallback when ASMC is fully down.
    firms_points: list[dict] = []
    if firms_key:
        fpts, fflag = _load_firms(firms_key)
        if fflag in ("invalid_key", "error"):
            flags.append("flag_firms_disabled")
        if fpts:
            firms_points = fpts
    if not sources and firms_points:
        from collections import Counter

        counts = Counter(p["source"] for p in firms_points)
        now = datetime.now(SGT)
        sources = {
            s: SourceHotspots(
                source=s, count=counts.get(s, 0),
                points=[(p["lon"], p["lat"]) for p in firms_points if p["source"] == s],
                fetched_at=now,
            )
            for s in config.ASMC_HOTSPOT_REGIONS
            if counts.get(s)
        }
        flags.append("flag_hotspots_approximate_firms")

    hs_ts = max((s.fetched_at for s in sources.values() if s.fetched_at), default=None)
    freshness = {
        "pm25": pm25_ts,
        "psi": psi_ts,
        "weather": weather_ts,
        "hotspots": hs_ts,
        "rss": rss.fetched_at,
    }
    return assemble_snapshot(
        mode="live", pm25=pm25, psi=psi, weather=weather, hotspots_=sources,
        rss=rss, history_df=history_df, firms_points=firms_points,
        flags=flags, freshness=freshness,
    )
