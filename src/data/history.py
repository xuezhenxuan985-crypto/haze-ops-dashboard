"""SQLite history for 1-hr PM2.5 so the 24-h trend survives restarts.

Writes happen inside the cached pm25 loader (at most once per TTL) and
dedupe at write time via UPSERT (ON CONFLICT keeps the last value).
Reads run a WHERE window query, then pivot/resample to hourly — the
median/OLS statistics stay in risk.analysis (pandas is the right tool
there). Demo mode never writes history. The 14-day analysis tab reads a
longer window than the 24-h chart; both come from the same table, so the
NEA ?date= backfill and the live appends dedupe naturally.

The pre-SQLite CSV is imported once on first load (migration), then left
untouched.
"""
from __future__ import annotations

import logging
import sqlite3

import pandas as pd

import config
from . import db

log = logging.getLogger(__name__)


def append_pm25_row(region: str, timestamp_iso: str, value: float) -> None:
    # Best-effort: a read-only filesystem (e.g. cloud hosting) must never
    # break the data pipeline — the 24-h chart simply shows "collecting…".
    db.upsert_pm25_rows(config.HISTORY_DB, [(timestamp_iso, region, value)])


def append_pm25_rows(rows: list[tuple[str, str, float]]) -> None:
    """Batch-upsert (timestamp_iso, region, value) rows — best effort."""
    if not rows:
        return
    db.upsert_pm25_rows(config.HISTORY_DB, rows)


def _migrate_csv_if_needed() -> None:
    """One-time import of the legacy CSV into SQLite, then archive the CSV.

    Runs whenever the CSV exists (not "when the DB is empty"): a live app
    refresh can create the DB with one fresh hour before this ever runs,
    and the UPSERT dedupe makes re-migration harmless. After a successful
    import the CSV is renamed to *.legacy, so the migration self-terminates.
    Garbage timestamps are dropped (same tolerance the old loader had);
    duplicates keep the last value, matching the old read-time dedupe.
    """
    if not config.HISTORY_CSV.exists():
        return
    try:
        df = pd.read_csv(config.HISTORY_CSV, names=["timestamp", "region", "pm25"])
    except (OSError, pd.errors.EmptyDataError):
        return
    if df.empty:
        return
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="ISO8601", errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Singapore")
    rows = [(ts.isoformat(), region, float(pm25))
            for ts, region, pm25 in zip(df["timestamp"], df["region"], df["pm25"])]
    if not rows:
        return
    n = db.upsert_pm25_rows(config.HISTORY_DB, rows)
    if not n:
        return
    log.info("migrated %d rows from history CSV into SQLite", n)
    try:
        config.HISTORY_CSV.rename(config.HISTORY_CSV.with_suffix(".csv.legacy"))
    except OSError as exc:
        log.warning("could not archive legacy CSV: %s", exc)


def load_pm25_history() -> pd.DataFrame | None:
    """Pivoted hourly history (region columns) for the 24-h chart, or None."""
    return load_pm25_history_window(config.HISTORY_HOURS / 24.0)


def load_pm25_history_window(days: float) -> pd.DataFrame | None:
    """Pivoted hourly history (region columns) for the last `days` (fractional
    OK), or None when absent/empty. The window filter runs in SQL; the pivot
    and hourly resample stay in pandas."""
    _migrate_csv_if_needed()
    cutoff = pd.Timestamp.now(tz="Asia/Singapore") - pd.Timedelta(hours=days * 24.0)
    rows = db.query_pm25_window(config.HISTORY_DB, cutoff.isoformat())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["timestamp", "region", "pm25"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return None
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Singapore")
    piv = df.pivot_table(index="timestamp", columns="region", values="pm25")
    piv = piv.reindex(columns=[r for r in config.REGIONS if r in piv.columns])
    if piv.empty:
        return None
    # Concurrent browser sessions can upsert slightly out of order; resample
    # requires a monotonic index.
    return piv.sort_index().resample("h").mean()
