"""Collect a frozen 90-day NEA history (1-hr PM2.5 + 24-hr PSI) for the analysis.

Run from the repo root:
    .venv/bin/python analysis/scripts/fetch_history.py

Uses the same NEA ?date= endpoint as the app's 14-day backfill, plus an
equivalent psi loop, respecting the shared 6-calls/10-s rate limiter
(~180 GETs, about 5 minutes). Writes frozen pivoted CSVs to
analysis/data/ and never touches the runtime data/history_pm25.csv.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.data import nea_pm25  # noqa: E402
from src.data.fetcher import NEA_LIMITER, http_get  # noqa: E402

OUT = ROOT / "analysis" / "data"
OUT.mkdir(parents=True, exist_ok=True)

DAYS = 90


def fetch_psi_backfill(days: int) -> list[tuple[str, str, float]]:
    """Hourly 24-hr PSI per region for the past `days` days; bad days skipped."""
    rows: list[tuple[str, str, float]] = []
    today = datetime.now().astimezone()
    for offset in range(days):
        date_str = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            resp = http_get(f"{config.NEA_PSI_URL}?date={date_str}", limiter=NEA_LIMITER)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0 or not payload.get("data", {}).get("items"):
                print(f"skip {date_str} (empty payload)")
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"skip {date_str}: {exc}")
            continue
        for item in payload["data"]["items"]:
            ts = item.get("timestamp")
            readings = (item.get("readings") or {}).get("psi_twenty_four_hourly") or {}
            if not ts:
                continue
            for region in config.REGIONS:
                value = readings.get(region)
                if value is not None:
                    rows.append((ts, region, float(value)))
    return rows


def pivot(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """(timestamp_iso, region, value) rows -> hourly pivoted DataFrame."""
    df = pd.DataFrame(rows, columns=["timestamp", "region", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Singapore")
    df = df.drop_duplicates(subset=["timestamp", "region"], keep="last")
    return df.pivot_table(index="timestamp", columns="region", values="value").sort_index()


if __name__ == "__main__":
    print(f"backfilling {DAYS} days of pm25 + psi (respecting NEA rate limit)…")
    pm = nea_pm25.fetch_pm25_backfill(DAYS)
    print(f"pm25 rows: {len(pm)}")
    pm_piv = pivot(pm)
    print(f"pm25 pivot: {pm_piv.shape[0]} hourly rows, {pm_piv.shape[1]} regions, "
          f"{pm_piv.index[0]:%Y-%m-%d %H:%M} → {pm_piv.index[-1]:%Y-%m-%d %H:%M}")
    pm_piv.to_csv(OUT / "pm25_90d.csv")

    psi = fetch_psi_backfill(DAYS)
    print(f"psi rows: {len(psi)}")
    psi_piv = pivot(psi)
    print(f"psi pivot: {psi_piv.shape[0]} hourly rows, {psi_piv.index[0]:%Y-%m-%d %H:%M} → "
          f"{psi_piv.index[-1]:%Y-%m-%d %H:%M}")
    psi_piv.to_csv(OUT / "psi_90d.csv")
    print("wrote", OUT / "pm25_90d.csv", "and", OUT / "psi_90d.csv")
