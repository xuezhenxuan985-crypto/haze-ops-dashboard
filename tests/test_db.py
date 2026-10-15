"""SQLite layer: UPSERT dedupe, WHERE window, GROUP BY aggregates, WAL."""
import sqlite3
from datetime import datetime, timedelta, timezone

import config
from src.data import db

SGT = timezone(timedelta(hours=8))


def _iso(hours_ago: int) -> str:
    base = datetime.now(SGT).replace(minute=0, second=0, microsecond=0)
    return (base - timedelta(hours=hours_ago)).isoformat()


def _cutoff(hours: float) -> str:
    base = datetime.now(SGT).replace(minute=0, second=0, microsecond=0)
    return (base - timedelta(hours=hours)).isoformat()


def test_upsert_inserts_and_dedupes_keep_last():
    db.upsert_pm25_rows(config.HISTORY_DB, [
        (_iso(3), "north", 46.0),
        (_iso(2), "north", 50.0),
        (_iso(2), "north", 52.0),  # same (ts, region) — must keep 52
    ])
    rows = db.query_pm25_window(config.HISTORY_DB, _cutoff(48))
    assert len(rows) == 2
    values = {r[0]: r[2] for r in rows}
    assert values[_iso(3)] == 46.0
    assert values[_iso(2)] == 52.0


def test_window_where_filters_old_rows():
    db.upsert_pm25_rows(config.HISTORY_DB, [
        (_iso(49), "north", 99.0),  # outside a 48-h window
        (_iso(1), "north", 40.0),
    ])
    rows = db.query_pm25_window(config.HISTORY_DB, _cutoff(48))
    assert [r[2] for r in rows] == [40.0]


def test_region_stats_group_by_aggregates():
    db.upsert_pm25_rows(config.HISTORY_DB, [
        (_iso(3), "north", 20.0),
        (_iso(2), "north", 60.0),   # >55
        (_iso(1), "north", 160.0),  # >150
        (_iso(2), "central", 40.0),
        (_iso(1), "central", 50.0),
    ])
    stats = db.region_stats(config.HISTORY_DB, _cutoff(48))
    assert set(stats) == {"north", "central"}
    n = stats["north"]
    assert n["hours"] == 3
    assert n["mean"] == 80.0
    assert n["max"] == 160.0
    assert n["hours_el"] == 2    # 60 and 160
    assert n["hours_hi"] == 1    # 160 only
    assert n["hours_vhi"] == 0
    c = stats["central"]
    assert c["hours"] == 2 and c["mean"] == 45.0 and c["max"] == 50.0
    assert c["hours_el"] == 0


def test_missing_db_returns_empty():
    assert db.query_pm25_window(config.HISTORY_DB, _cutoff(48)) == []
    assert db.region_stats(config.HISTORY_DB, _cutoff(48)) == {}
    assert db.count_rows(config.HISTORY_DB) == 0


def test_concurrent_connections_do_not_conflict():
    """Two 'browser sessions' upserting the same table must both succeed (WAL)."""
    conn2 = sqlite3.connect(config.HISTORY_DB, timeout=5.0)
    try:
        conn2.execute("PRAGMA busy_timeout=5000")
        db.upsert_pm25_rows(config.HISTORY_DB, [(_iso(1), "east", 30.0)])
        conn2.execute(
            "INSERT INTO pm25_history (ts, region, value) VALUES (?, ?, ?) "
            "ON CONFLICT(ts, region) DO UPDATE SET value = excluded.value",
            (_iso(2), "east", 31.0))
        conn2.commit()
    finally:
        conn2.close()
    rows = db.query_pm25_window(config.HISTORY_DB, _cutoff(48))
    assert len(rows) == 2


def test_write_to_missing_parent_dir_is_created():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "sub" / "history.db"
        assert db.upsert_pm25_rows(target, [(_iso(0), "west", 44.0)]) == 1
        assert db.count_rows(target) == 1
