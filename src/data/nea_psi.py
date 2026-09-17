"""NEA 24-hr PSI loader (api-open.data.gov.sg v2 realtime, no auth).

This is the official rolling 24-hr PSI per region — the metric MOM work
guidelines key off. Also carries 24-hr PM2.5 and pollutant sub-indices.
"""
from __future__ import annotations

from datetime import datetime

import requests

import config
from .fetcher import NEA_LIMITER, http_get
from .models import RegionPSI


def fetch_psi(session: requests.Session | None = None) -> tuple[dict[str, RegionPSI], datetime]:
    """Return {region: RegionPSI} and the update timestamp (tz-aware)."""
    resp = http_get(config.NEA_PSI_URL, session=session, limiter=NEA_LIMITER)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
        raise ValueError(f"Unexpected psi payload: {str(payload)[:200]}")
    item = payload["data"]["items"][0]
    updated = datetime.fromisoformat(item["updatedTimestamp"])
    readings = item["readings"]

    regions: dict[str, RegionPSI] = {}
    for region in config.REGIONS:
        psi = readings.get("psi_twenty_four_hourly", {}).get(region)
        if psi is None:
            continue
        pm25_24h = readings.get("pm25_twenty_four_hourly", {}).get(region)
        regions[region] = RegionPSI(
            region=region,
            psi_24h=float(psi),
            pm25_24h=float(pm25_24h) if pm25_24h is not None else float("nan"),
            tier=0,  # filled by the risk layer via pipeline
        )
    if not regions:
        raise ValueError("psi payload contained no regional readings")
    return regions, updated
