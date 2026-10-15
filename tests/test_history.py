"""History CSV: append → load roundtrip, dedupe (keep last), 48-h prune."""
import pandas as pd

import config
from src.data import history


def _ts(hours_ago: int) -> str:
    """An ISO timestamp exactly N hours before the current hour (+08:00)."""
    base = pd.Timestamp.now(tz="Asia/Singapore").floor("h")
    return (base - pd.Timedelta(hours=hours_ago)).isoformat()


def test_missing_file_returns_none():
    assert not config.HISTORY_CSV.exists()  # redirected to fresh tmp_path
    assert history.load_pm25_history() is None


def test_empty_file_returns_none():
    config.HISTORY_CSV.write_text("", encoding="utf-8")
    assert history.load_pm25_history() is None


def test_append_load_roundtrip():
    history.append_pm25_row("north", _ts(3), 46.0)
    history.append_pm25_row("north", _ts(2), 50.0)
    history.append_pm25_row("south", _ts(2), 55.0)

    piv = history.load_pm25_history()
    assert piv is not None
    assert list(piv.columns) == ["north", "south"]
    assert piv.loc[base_hour(2), "north"] == 50.0
    assert piv.loc[base_hour(3), "north"] == 46.0
    assert piv.loc[base_hour(2), "south"] == 55.0


def base_hour(hours_ago: int) -> pd.Timestamp:
    base = pd.Timestamp.now(tz="Asia/Singapore").floor("h")
    return base - pd.Timedelta(hours=hours_ago)


def test_dedupe_keeps_last():
    history.append_pm25_row("north", _ts(2), 50.0)
    history.append_pm25_row("north", _ts(2), 52.0)  # concurrent session rewrite
    piv = history.load_pm25_history()
    assert len(piv) == 1
    assert piv.loc[base_hour(2), "north"] == 52.0


def test_48h_pruning():
    history.append_pm25_row("north", _ts(49), 99.0)  # older than the window
    history.append_pm25_row("north", _ts(1), 40.0)
    piv = history.load_pm25_history()
    assert piv is not None
    assert len(piv) == 1
    assert piv.loc[base_hour(1), "north"] == 40.0


def test_garbage_rows_dropped():
    config.HISTORY_CSV.write_text(
        f"not-a-date,north,12.0\n{_ts(1)},north,40.0\n", encoding="utf-8")
    piv = history.load_pm25_history()
    assert piv is not None
    assert len(piv) == 1
    assert piv.loc[base_hour(1), "north"] == 40.0


def test_legacy_csv_migrates_into_sqlite_once():
    from src.data import db
    # Legacy CSV: a duplicate hour and a garbage line.
    config.HISTORY_CSV.write_text(
        f"{_ts(2)},north,50.0\n{_ts(2)},north,52.0\n"
        f"not-a-date,north,12.0\n{_ts(1)},south,40.0\n", encoding="utf-8")
    piv = history.load_pm25_history()
    assert piv is not None
    # Duplicate keeps the last value; garbage dropped.
    assert piv.loc[base_hour(2), "north"] == 52.0
    assert piv.loc[base_hour(1), "south"] == 40.0
    assert len(piv) == 2
    # The rows now live in SQLite; the CSV is archived (migration is one-shot).
    assert db.count_rows(config.HISTORY_DB) == 2
    assert not config.HISTORY_CSV.exists()
    assert config.HISTORY_CSV.with_suffix(".csv.legacy").exists()
    # A second load neither duplicates rows nor re-archives anything.
    history.load_pm25_history()
    assert db.count_rows(config.HISTORY_DB) == 2


def test_migration_runs_even_when_live_app_wrote_first():
    """A live refresh can create the DB with one fresh hour before migration
    ever runs — the CSV history must still be imported, not skipped."""
    from src.data import db
    history.append_pm25_row("west", _ts(1), 33.0)  # the "live app" write
    config.HISTORY_CSV.write_text(
        f"{_ts(3)},north,20.0\n{_ts(2)},north,25.0\n", encoding="utf-8")
    piv = history.load_pm25_history()
    assert piv is not None
    assert len(piv) == 3  # 3 distinct hours, dedupe + merge
    assert db.count_rows(config.HISTORY_DB) == 3
    assert not config.HISTORY_CSV.exists()
