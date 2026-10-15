"""SQLite persistence for the runtime 1-hr PM2.5 history.

Replaces the old append-only CSV: writes dedupe at write time
(INSERT ... ON CONFLICT keeps the last value), reads filter with WHERE and
aggregate with GROUP BY. sqlite3 is stdlib — no new dependency — and the
single file lives in config.DATA_DIR (gitignored, wiped on cloud redeploys,
then re-backfilled exactly like the CSV was).

Concurrent browser sessions are handled with WAL journaling and a busy
timeout. Every write is best-effort: a read-only cloud filesystem must
never break the pipeline.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pm25_history (
    ts     TEXT    NOT NULL,   -- ISO 8601, +08:00 (lexicographic == chronological)
    region TEXT    NOT NULL,
    value  REAL    NOT NULL,
    PRIMARY KEY (ts, region)
);
CREATE INDEX IF NOT EXISTS idx_pm25_history_ts ON pm25_history (ts);
"""

_UPSERT = (
    "INSERT INTO pm25_history (ts, region, value) VALUES (?, ?, ?) "
    "ON CONFLICT(ts, region) DO UPDATE SET value = excluded.value"
)


@contextmanager
def _conn(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")   # readers don't block the writer
        conn.execute("PRAGMA busy_timeout=5000")  # writers wait, not fail
        conn.executescript(SCHEMA)                # idempotent, cheap
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_pm25_rows(path: Path, rows: list[tuple[str, str, float]]) -> int:
    """Insert (ts, region, value); a duplicate key keeps the LAST value.

    Dedupe happens here, at write time — the read path no longer needs it.
    """
    if not rows:
        return 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _conn(path) as conn:
            conn.executemany(_UPSERT, rows)
        return len(rows)
    except (OSError, sqlite3.Error) as exc:  # read-only FS must never break the app
        log.warning("pm25_history upsert failed: %s", exc)
        return 0


def query_pm25_window(path: Path, cutoff_iso: str) -> list[tuple[str, str, float]]:
    """All (ts, region, value) rows at or after cutoff, oldest first."""
    if not path.exists():
        return []
    try:
        with _conn(path) as conn:
            cur = conn.execute(
                "SELECT ts, region, value FROM pm25_history "
                "WHERE ts >= ? ORDER BY ts, region",
                (cutoff_iso,),
            )
            return cur.fetchall()
    except (OSError, sqlite3.Error) as exc:
        log.warning("pm25_history query failed: %s", exc)
        return []


def region_stats(path: Path, cutoff_iso: str) -> dict[str, dict[str, float]]:
    """Per-region aggregates since cutoff — the SQL GROUP BY path.

    Powers the 14-day analysis coverage check. COUNT/AVG/MAX are native;
    band-hour counts use SUM(value > threshold) (1 when true in SQLite).
    """
    if not path.exists():
        return {}
    try:
        with _conn(path) as conn:
            cur = conn.execute(
                "SELECT region, COUNT(*) AS hours, AVG(value) AS mean, MAX(value) AS max, "
                "       SUM(value > 55) AS hours_el, SUM(value > 150) AS hours_hi, "
                "       SUM(value > 250) AS hours_vhi "
                "FROM pm25_history WHERE ts >= ? GROUP BY region",
                (cutoff_iso,),
            )
            return {
                row[0]: {
                    "hours": row[1], "mean": row[2], "max": row[3],
                    "hours_el": row[4] or 0, "hours_hi": row[5] or 0, "hours_vhi": row[6] or 0,
                }
                for row in cur.fetchall()
            }
    except (OSError, sqlite3.Error) as exc:
        log.warning("pm25_history region_stats failed: %s", exc)
        return {}


def count_rows(path: Path) -> int:
    """Total rows; 0 also when the file is absent."""
    if not path.exists():
        return 0
    try:
        with _conn(path) as conn:
            return conn.execute("SELECT COUNT(*) FROM pm25_history").fetchone()[0]
    except (OSError, sqlite3.Error) as exc:
        log.warning("pm25_history count failed: %s", exc)
        return 0
