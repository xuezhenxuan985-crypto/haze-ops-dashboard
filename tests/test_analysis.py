"""History analysis: OLS fit, per-region 14-day summaries, NEA date backfill."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import config
from conftest import FakeResponse, FakeSession
from src.data import history, nea_pm25
from src.risk.analysis import analysis_from_history, compute_region_analysis, ols_fit

SGT = timezone(timedelta(hours=8))


def _hourly(days: int, value: float) -> list[tuple[datetime, float]]:
    """`days` × 24 hourly rows all at the same value, starting 2026-09-16."""
    base = datetime(2026, 9, 16, 0, 0, tzinfo=SGT)
    return [(base + timedelta(hours=h), value) for h in range(days * 24)]


def _hour_ago_ts(hours_ago: int) -> str:
    base = pd.Timestamp.now(tz="Asia/Singapore").floor("h")
    return (base - pd.Timedelta(hours=hours_ago)).isoformat()


# ---------------------------------------------------------------------------
# ols_fit
# ---------------------------------------------------------------------------
def test_ols_fit_known_line():
    slope, intercept, r2 = ols_fit([0, 1, 2, 3], [3.0, 5.0, 7.0, 9.0])
    assert slope == 2.0
    assert intercept == 3.0
    assert r2 == 1.0


def test_ols_fit_flat_line():
    slope, intercept, r2 = ols_fit([1, 2, 3], [5.0, 5.0, 5.0])
    assert slope == 0.0
    assert intercept == 5.0
    assert r2 == 1.0


def test_ols_fit_needs_two_points():
    with pytest.raises(ValueError):
        ols_fit([1], [2.0])


def test_ols_fit_noisy_r2_below_one():
    slope, intercept, r2 = ols_fit([0, 1, 2, 3], [0.0, 3.0, 1.0, 4.0])
    assert slope == 1.0  # still +1/day on average
    assert 0.0 < r2 < 1.0


# ---------------------------------------------------------------------------
# compute_region_analysis
# ---------------------------------------------------------------------------
def test_region_analysis_stats():
    rows_by_region = {
        "central": _hourly(14, 100.0),
        "north": _hourly(14, 20.0),
    }
    out = compute_region_analysis(rows_by_region)

    c = out["central"]
    assert c.hours == 336
    assert c.mean == 100.0
    assert c.median == 100.0
    assert c.max == 100.0
    assert c.hours_elevated == 336  # >55 every hour
    assert c.hours_high == 0
    assert c.hours_vhigh == 0
    assert c.pct_elevated == 100.0
    assert c.slope_per_day == 0.0
    assert c.r2 == 1.0

    n = out["north"]
    assert n.mean == 20.0
    assert n.hours_elevated == 0
    assert n.pct_elevated == 0.0


def test_band_hour_counts():
    out = compute_region_analysis({
        "north": _hourly(14, 160.0),   # >150 all hours
        "south": _hourly(14, 260.0),   # >250 all hours
    })
    assert out["north"].hours_high == 336
    assert out["north"].hours_vhigh == 0
    assert out["south"].hours_vhigh == 336


def test_slope_per_day_exact():
    # Daily mean rises exactly +2 µg/m³ per day over 14 days.
    rows = []
    for day in range(14):
        base = datetime(2026, 9, 16, 0, 0, tzinfo=SGT) + timedelta(days=day)
        rows.extend((base + timedelta(hours=h), 30.0 + 2.0 * day) for h in range(24))
    out = compute_region_analysis({"west": rows})
    assert out["west"].slope_per_day == 2.0
    assert out["west"].r2 == 1.0


def test_slope_none_with_few_days():
    out = compute_region_analysis({"east": _hourly(2, 50.0)})  # 2 distinct days
    assert out["east"].slope_per_day is None
    assert out["east"].r2 is None


def test_empty_region_is_zeroed():
    out = compute_region_analysis({})
    a = out["south"]  # absent input -> empty summary, no crash
    assert a.hours == 0
    assert a.slope_per_day is None


def test_analysis_from_history_df():
    idx = pd.date_range("2026-09-16", periods=14 * 24, freq="h", tz=SGT)
    df = pd.DataFrame(index=idx)
    df["central"] = 100.0
    df["north"] = 20.0
    out = analysis_from_history(df)
    assert out["central"].mean == 100.0
    assert out["north"].hours_elevated == 0
    assert out["south"].hours == 0  # column absent -> empty summary


# ---------------------------------------------------------------------------
# fetch_pm25_backfill (FakeSession routes keyed by full URL incl. ?date=)
# ---------------------------------------------------------------------------
def _date(offset_days: int) -> str:
    return (datetime.now().astimezone() - timedelta(days=offset_days)).strftime("%Y-%m-%d")


def _day_payload(date: str, values: dict[str, float], hours: int = 24) -> dict:
    items = [
        {
            "updatedTimestamp": f"{date}T{h:02d}:15:55+08:00",
            "timestamp": f"{date}T{h:02d}:00:00+08:00",
            "readings": {"pm25_one_hourly": values},
        }
        for h in range(hours)
    ]
    return {"code": 0, "data": {"regionMetadata": [], "items": items}, "errorMsg": ""}


def test_backfill_returns_rows_per_day():
    d1, d0 = _date(1), _date(0)
    session = FakeSession({
        f"{config.NEA_PM25_URL}?date={d0}": FakeResponse(
            json_data=_day_payload(d0, {"north": 40.0, "south": 50.0})),
        f"{config.NEA_PM25_URL}?date={d1}": FakeResponse(
            json_data=_day_payload(d1, {"north": 41.0, "south": 51.0})),
    })
    rows = nea_pm25.fetch_pm25_backfill(2, session=session)
    assert len(rows) == 2 * 24 * 2  # 2 days × 24 h × 2 regions
    assert rows[0] == (f"{d0}T00:00:00+08:00", "north", 40.0)
    assert rows[-1] == (f"{d1}T23:00:00+08:00", "south", 51.0)
    # One GET per day, rate limiter respected (no sleeps — patched in conftest).
    assert len(session.calls) == 2


def test_backfill_skips_missing_day():
    d1 = _date(1)
    session = FakeSession({
        f"{config.NEA_PM25_URL}?date={d1}": FakeResponse(
            json_data=_day_payload(d1, {"north": 40.0})),
    })  # today's URL absent -> 404 -> skipped, never raises
    rows = nea_pm25.fetch_pm25_backfill(2, session=session)
    assert len(rows) == 24


def test_backfill_skips_bad_payload():
    d0 = _date(0)
    session = FakeSession({
        f"{config.NEA_PM25_URL}?date={d0}": FakeResponse(
            json_data={"code": 1, "data": {}, "errorMsg": "boom"}),
    })
    assert nea_pm25.fetch_pm25_backfill(1, session=session) == []


def test_backfill_rows_land_in_history_and_dedupe():
    d0 = _date(0)
    ts = f"{d0}T05:00:00+08:00"
    session = FakeSession({
        f"{config.NEA_PM25_URL}?date={d0}": FakeResponse(
            json_data=_day_payload(d0, {"north": 40.0})),
    })
    rows = nea_pm25.fetch_pm25_backfill(1, session=session)
    history.append_pm25_rows(rows)
    history.append_pm25_row("north", ts, 45.0)  # newer live value, same hour

    piv = history.load_pm25_history_window(14.0)
    assert piv is not None
    hour = pd.Timestamp(ts).tz_convert("Asia/Singapore").floor("h")
    assert piv.loc[hour, "north"] == 45.0  # dedupe keeps the last write
    assert len(piv) == 24


def test_analysis_window_prunes_older_rows():
    history.append_pm25_row("north", _hour_ago_ts(15 * 24), 99.0)  # 15 days ago
    history.append_pm25_row("north", _hour_ago_ts(1), 40.0)
    piv = history.load_pm25_history_window(14.0)
    assert piv is not None
    assert len(piv) == 1
