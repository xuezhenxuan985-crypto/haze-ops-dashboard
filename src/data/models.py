"""Shared dataclasses. The Snapshot is the single object the UI consumes;
data layers build it, risk layers annotate it, UI layers only render it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Reading:
    timestamp: datetime  # tz-aware (+08:00)
    value: float


@dataclass
class RegionPM25:
    region: str
    pm25_1h: float
    band: int  # 1-4
    readings_24h: list[Reading] = field(default_factory=list)
    trend_3h: float | None = None  # µg/m³ per hour


@dataclass
class RegionPSI:
    region: str
    psi_24h: float
    pm25_24h: float
    tier: int  # 1-5


@dataclass
class RegionWeather:
    region: str
    temp_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    wind_dir_deg: float | None = None  # direction the wind comes FROM
    rainfall_mm: float = 0.0
    station_count: int = 0


@dataclass
class SourceHotspots:
    source: str  # "sumatra" | "kalimantan" | "p_malaysia"
    count: int
    points: list[tuple[float, float]] = field(default_factory=list)
    yesterday_count: int | None = None
    fetched_at: datetime | None = None


@dataclass
class RSSStatus:
    level: int | None  # ASMC Alert Level 1-3; None = no active alert
    title: str = ""
    link: str = ""
    fetched_at: datetime | None = None


@dataclass
class TransportRisk:
    level: int  # 0-4 (0 = none)
    score: float
    upwind_points: int
    dominant_source: str | None
    wind_available: bool
    total_points: int = 0


@dataclass
class WorkMatrix:
    light: str  # "allowed" | "caution" | "restricted"
    moderate: str
    strenuous: str
    reasons: dict[str, str] = field(default_factory=dict)  # cell -> i18n key


@dataclass
class RegionAdvisory:
    region: str
    risk_level: int  # 1-4
    risk_score: float
    pm25_action_key: str  # i18n key
    psi_action_key: str
    matrix: WorkMatrix
    factors: list[tuple[str, dict]] = field(default_factory=list)  # (i18n key, fmt args)


@dataclass
class Snapshot:
    mode: str  # "live" | "demo"
    fetched_at: datetime
    freshness: dict[str, datetime]  # source label -> last successful fetch
    pm25: dict[str, RegionPM25]
    psi: dict[str, RegionPSI]
    weather: dict[str, RegionWeather]
    hotspots: dict[str, SourceHotspots]
    transport: TransportRisk | None
    advisories: dict[str, RegionAdvisory]
    rss: RSSStatus
    history_df: Any = None  # pivoted DataFrame (region columns, hourly index)
    firms_points: list[dict] = field(default_factory=list)  # display-only FIRMS detections
    flags: list[str] = field(default_factory=list)
