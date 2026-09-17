"""Append-only CSV history for 1-hr PM2.5 so the 24-h trend survives restarts.

Writes happen inside the cached pm25 loader (at most once per TTL); reads
dedupe (concurrent browser sessions), prune to the last 48 h and resample
to hourly. Demo mode never writes history.
"""
from __future__ import annotations

import pandas as pd

import config


def append_pm25_row(region: str, timestamp_iso: str, value: float) -> None:
    # Best-effort: a read-only filesystem (e.g. cloud hosting) must never
    # break the data pipeline — the 24-h chart simply shows "collecting…".
    try:
        config.DATA_DIR.mkdir(exist_ok=True)
        with open(config.HISTORY_CSV, "a", encoding="utf-8") as f:
            f.write(f"{timestamp_iso},{region},{value:.1f}\n")
    except OSError:
        pass


def load_pm25_history() -> pd.DataFrame | None:
    """Return pivoted hourly history (region columns) or None when absent/empty."""
    if not config.HISTORY_CSV.exists():
        return None
    try:
        df = pd.read_csv(config.HISTORY_CSV, names=["timestamp", "region", "pm25"])
    except pd.errors.EmptyDataError:
        return None
    if df.empty:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return None
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Singapore")
    df = df.drop_duplicates(subset=["timestamp", "region"], keep="last")
    cutoff = pd.Timestamp.now(tz="Asia/Singapore") - pd.Timedelta(hours=config.HISTORY_HOURS)
    df = df[df["timestamp"] >= cutoff]
    piv = df.pivot_table(index="timestamp", columns="region", values="pm25")
    piv = piv.reindex(columns=[r for r in config.REGIONS if r in piv.columns])
    if piv.empty:
        return None
    # Concurrent browser sessions can append slightly out of order; resample
    # requires a monotonic index.
    return piv.sort_index().resample("h").mean()
