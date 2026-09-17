"""Hotspot data — ASMC primary (no auth, verified 2026-09-17), FIRMS optional.

ASMC publishes one fixed-width text file per source region per NOAA-20
VIIRS pass (~2/day). Each file carries the total count and a lon/lat point
list. A 7-day count JSON gives yesterday's totals for surge detection. The
KML endpoint is a fallback when a text file is missing. NASA FIRMS (~3 h
NRT, per-point confidence/FRP) is display-only enrichment unless ASMC is
fully down. The ASMC RSS feed provides Alert Level 1-3 status.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

import config
from .fetcher import http_get, http_post_form
from .models import RSSStatus, SourceHotspots

log = logging.getLogger(__name__)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_asmc_text(text: str) -> tuple[int, list[tuple[float, float]], datetime | None]:
    """Parse an ASMC hotspot fixed-width file. Tolerant of header drift.

    Returns (count, points, created_at). A file may concatenate several
    VIIRS granules of the same pass, each delimited by its own
    "***** Hotspot Count Report *****" header — counts then SUM across
    sections so count == len(points). Without any header count, count falls
    back to len(points). Malformed rows are skipped; rows must land inside a
    loose SE-Asia box; duplicate coordinates across sections are dropped.
    """
    count = 0
    points: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    created: datetime | None = None
    for section in text.split("***** Hotspot Count Report *****"):
        sec_count, sec_points, sec_created = _parse_asmc_section(section)
        count += sec_count
        for lon, lat in sec_points:
            key = (round(lon, 3), round(lat, 3))
            if key not in seen:
                seen.add(key)
                points.append((lon, lat))
        if created is None:
            created = sec_created
    if count == 0 and points:
        count = len(points)
    return count, points, created


def _parse_asmc_section(section: str) -> tuple[int, list[tuple[float, float]], datetime | None]:
    count = 0
    points: list[tuple[float, float]] = []
    created: datetime | None = None
    for raw in section.splitlines():
        line = raw.strip().lstrip("﻿")  # strip BOM
        if not line:
            continue
        if line.startswith("Total Hotspot Count"):
            m = re.search(r"(\d+)", line)
            if m:
                count = int(m.group(1))
            continue
        if line.startswith("Created On:"):
            m = re.search(r"(\d{4}),\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{1,2}):(\d{2}):(\d{2})", line)
            if m:
                month = _MONTHS.get(m.group(2).lower())
                if month:
                    created = datetime(int(m.group(1)), month, int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6)))
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            int(parts[0])
            lon, lat = float(parts[1]), float(parts[2])
        except ValueError:
            continue  # separator/header lines
        if 90.0 <= lon <= 140.0 and -20.0 <= lat <= 30.0:
            points.append((lon, lat))
    if count == 0 and points:
        count = len(points)
    return count, points, created


def parse_asmc_kml(kml_text: str) -> dict[str, list[tuple[float, float]]]:
    """Parse the ASMC hotspot KML into {region: [(lon, lat), ...]}."""
    out: dict[str, list[tuple[float, float]]] = {}
    root = ET.fromstring(kml_text)
    ns = "{http://www.opengis.net/kml/2.2}"
    for pm in root.iter(f"{ns}Placemark"):
        coords_el = pm.find(f"{ns}Point/{ns}coordinates")
        if coords_el is None or not coords_el.text:
            continue
        region = None
        for data in pm.iter(f"{ns}Data"):
            if data.get("name") == "region":
                value = data.find(f"{ns}value")
                region = value.text if value is not None else None
                break
        try:
            lon, lat, *_ = [float(x) for x in coords_el.text.strip().split(",")]
        except ValueError:
            continue
        key = (region or "").strip().lower()
        out.setdefault(key, []).append((lon, lat))
    return out


def fetch_asmc_hotspots(session: requests.Session | None = None) -> dict[str, SourceHotspots]:
    """Fetch point-level hotspot files for all source regions (best effort)."""
    out: dict[str, SourceHotspots] = {}
    for source in config.ASMC_HOTSPOT_REGIONS:
        url = config.ASMC_HOTSPOT_TEXT_URL.format(region=source)
        try:
            resp = http_get(url, session=session, limiter=None)
            resp.raise_for_status()
            count, points, created = parse_asmc_text(resp.text)
        except Exception as exc:  # noqa: BLE001 — one bad region must not sink the rest
            log.warning("ASMC hotspot file %s failed: %s", source, exc)
            continue
        out[source] = SourceHotspots(source=source, count=count, points=points, fetched_at=created)
    return out


def _asmc_date_format(dt: datetime) -> str:
    return f"{dt.day} {dt.strftime('%b, %Y')}"


def fetch_asmc_daily_counts(session: requests.Session | None = None) -> dict[str, dict[str, int]] | None:
    """7-day daily hotspot counts from the ASMC AJAX endpoint.

    Returns {YYYY-MM-DD: {"sumatra": n, ...}}. This endpoint can lag the
    text files — used only for yesterday-count context. None on any failure.
    """
    now = datetime.now().astimezone()
    try:
        resp = http_post_form(
            config.ASMC_DAILY_COUNT_URL,
            {"date": _asmc_date_format(now), "pastDays": "7",
             "regions[]": ["Sumatra", "Kalimantan", "P_Malaysia"]},
            session=session,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("ASMC daily counts failed: %s", exc)
        return None
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        date = row.get("date")
        if not date:
            continue
        out[date] = {
            "sumatra": int(row.get("Sumatra") or 0),
            "kalimantan": int(row.get("Kalimantan") or 0),
            "p_malaysia": int(row.get("P_Malaysia") or 0),
        }
    return out


def fetch_asmc_kml(session: requests.Session | None = None) -> dict[str, list[tuple[float, float]]] | None:
    """Discover and fetch the latest ASMC hotspot KML (fallback source)."""
    now = datetime.now().astimezone()
    try:
        resp = http_post_form(config.ASMC_KML_DISCOVERY_URL, {"date": _asmc_date_format(now)}, session=session)
        resp.raise_for_status()
        kml_url = resp.text.strip()
        if not kml_url.startswith("http"):
            return None
        resp2 = http_get(kml_url, session=session, limiter=None)
        resp2.raise_for_status()
        return parse_asmc_kml(resp2.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("ASMC KML fetch failed: %s", exc)
        return None


def _classify_firms_point(lon: float, lat: float) -> str | None:
    for source, (w, s, e, n) in config.SOURCE_BBOXES.items():
        if w <= lon <= e and s <= lat <= n:
            return source
    return None


def fetch_firms(firms_key: str, session: requests.Session | None = None) -> tuple[list[dict] | None, str | None]:
    """FIRMS VIIRS 1-day CSV for the SE-Asia bbox.

    Returns (points, flag) where flag is None (ok), "invalid_key" or
    "error". Points are display-only: {lat, lon, confidence, frp,
    acq_date, acq_time, source}. Never raises.
    """
    if not firms_key:
        return None, None
    url = config.FIRMS_CSV_URL_TEMPLATE.format(key=firms_key)
    try:
        resp = http_get(url, session=session, limiter=None, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        log.warning("FIRMS request failed: %s", exc)
        return None, "error"
    if resp.status_code == 400 and "Invalid MAP_KEY" in resp.text:
        return None, "invalid_key"
    if resp.status_code != 200:
        return None, "error"
    points: list[dict] = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        try:
            lon, lat = float(row["longitude"]), float(row["latitude"])
        except (KeyError, ValueError):
            continue
        source = _classify_firms_point(lon, lat)
        if source is None:
            continue
        points.append({
            "lat": lat, "lon": lon,
            "confidence": row.get("confidence", ""),
            "frp": row.get("frp", ""),
            "bright_ti4": row.get("bright_ti4", ""),
            "acq_date": row.get("acq_date", ""),
            "acq_time": row.get("acq_time", ""),
            "source": source,
        })
    return points, None


def fetch_rss(session: requests.Session | None = None) -> RSSStatus:
    """ASMC RSS: Alert Level 1-3 status + latest bulletin title/link. Never raises."""
    try:
        resp = http_get(config.ASMC_RSS_URL, session=session, limiter=None)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("ASMC RSS failed: %s", exc)
        return RSSStatus(level=None)
    level: int | None = None
    latest_title = ""
    latest_link = ""
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not latest_title:
            latest_title, latest_link = title, link
        if "alert" in title.lower():
            m = re.search(r"Alert Level\s*(\d)", title, re.IGNORECASE)
            if m:
                level = max(level or 0, int(m.group(1)))
    return RSSStatus(level=level, title=latest_title, link=latest_link, fetched_at=datetime.now().astimezone())
