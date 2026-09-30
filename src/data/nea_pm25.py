"""NEA 1-hr PM2.5 loader (api-open.data.gov.sg v2 realtime, no auth).

The readings dict key order is NOT stable — always index by region name.
Appends each hourly reading to the local history CSV (see history.py).
The same endpoint supports ?date=YYYY-MM-DD, which powers the 14-day
history backfill used by the History analysis tab.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

import config
from . import history
from .fetcher import NEA_LIMITER, RateLimiter, http_get
from .models import Reading, RegionPM25

log = logging.getLogger(__name__)


def _parse_payload(payload: dict) -> tuple[dict[str, float], datetime]:
    """Extract {region: pm25_1h} and the update timestamp from a v2 payload."""
    if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
        raise ValueError(f"Unexpected pm25 payload: {str(payload)[:200]}")
    item = payload["data"]["items"][0]
    updated = datetime.fromisoformat(item["updatedTimestamp"])
    hourly = item["readings"]["pm25_one_hourly"]
    values: dict[str, float] = {}
    for region in config.REGIONS:
        value = hourly.get(region)
        if value is not None:
            values[region] = float(value)
    if not values:
        raise ValueError("pm25 payload contained no regional readings")
    return values, updated


def fetch_pm25(session: requests.Session | None = None) -> tuple[dict[str, RegionPM25], datetime]:
    """Return {region: RegionPM25} and the update timestamp (tz-aware)."""
    resp = http_get(config.NEA_PM25_URL, session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    payload = resp.json()
    values, updated = _parse_payload(payload)
    timestamp_iso = payload["data"]["items"][0]["timestamp"]

    regions: dict[str, RegionPM25] = {}
    for region, value in values.items():
        history.append_pm25_row(region, timestamp_iso, value)
        regions[region] = RegionPM25(
            region=region,
            pm25_1h=value,
            band=0,  # filled by the risk layer via pipeline
            readings_24h=[Reading(datetime.fromisoformat(timestamp_iso), value)],
        )
    return regions, updated


def fetch_pm25_backfill(
    days: int,
    *,
    session: requests.Session | None = None,
    limiter: RateLimiter | None = None,
) -> list[tuple[str, str, float]]:
    """Pull the past `days` days of hourly 1-hr PM2.5 from the NEA date
    endpoint (one GET per day, ~24 items each). Returns (timestamp_iso,
    region, value) rows; a failed day is skipped — never raises.
    """
    limiter = limiter if limiter is not None else NEA_LIMITER
    rows: list[tuple[str, str, float]] = []
    today = datetime.now().astimezone()
    for offset in range(days):
        date_str = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        url = f"{config.NEA_PM25_URL}?date={date_str}"
        try:
            resp = http_get(url, session=session, limiter=limiter)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
                log.warning("pm25 backfill %s: empty payload", date_str)
                continue
        except Exception as exc:  # noqa: BLE001 — one bad day must not kill the backfill
            log.warning("pm25 backfill %s failed: %s", date_str, exc)
            continue
        for item in payload["data"]["items"]:
            ts = item.get("timestamp")
            readings = (item.get("readings") or {}).get("pm25_one_hourly") or {}
            if not ts:
                continue
            for region in config.REGIONS:
                value = readings.get(region)
                if value is not None:
                    rows.append((ts, region, float(value)))
    return rows
