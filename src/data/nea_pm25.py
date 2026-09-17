"""NEA 1-hr PM2.5 loader (api-open.data.gov.sg v2 realtime, no auth).

The readings dict key order is NOT stable — always index by region name.
Appends each hourly reading to the local history CSV (see history.py).
"""
from __future__ import annotations

from datetime import datetime

import requests

import config
from . import history
from .fetcher import NEA_LIMITER, http_get
from .models import Reading, RegionPM25


def fetch_pm25(session: requests.Session | None = None) -> tuple[dict[str, RegionPM25], datetime]:
    """Return {region: RegionPM25} and the update timestamp (tz-aware)."""
    resp = http_get(config.NEA_PM25_URL, session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
        raise ValueError(f"Unexpected pm25 payload: {str(payload)[:200]}")
    item = payload["data"]["items"][0]
    updated = datetime.fromisoformat(item["updatedTimestamp"])
    hourly = item["readings"]["pm25_one_hourly"]

    regions: dict[str, RegionPM25] = {}
    for region in config.REGIONS:
        value = hourly.get(region)
        if value is None:
            continue
        timestamp_iso = item["timestamp"]
        history.append_pm25_row(region, timestamp_iso, float(value))
        regions[region] = RegionPM25(
            region=region,
            pm25_1h=float(value),
            band=0,  # filled by the risk layer via pipeline
            readings_24h=[Reading(datetime.fromisoformat(timestamp_iso), float(value))],
        )
    if not regions:
        raise ValueError("pm25 payload contained no regional readings")
    return regions, updated
