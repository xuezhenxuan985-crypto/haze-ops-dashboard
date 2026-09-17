"""Band thresholds — official NEA values; Band 4 starts at >=251, not >250."""
from src.risk.bands import pm25_band, psi_band, trend_slope
from src.data.models import Reading
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))


def _readings(values):
    base = datetime(2026, 9, 17, 12, tzinfo=SGT)
    return [Reading(base + timedelta(hours=i), v) for i, v in enumerate(values)]


def test_pm25_band_boundaries():
    assert pm25_band(0) == 1
    assert pm25_band(55) == 1
    assert pm25_band(56) == 2
    assert pm25_band(150) == 2
    assert pm25_band(151) == 3
    assert pm25_band(250) == 3
    assert pm25_band(251) == 4  # the >=251 gotcha
    assert pm25_band(300) == 4


def test_psi_band_boundaries():
    assert psi_band(0) == 1
    assert psi_band(50) == 1
    assert psi_band(51) == 2
    assert psi_band(100) == 2
    assert psi_band(101) == 3
    assert psi_band(200) == 3
    assert psi_band(201) == 4
    assert psi_band(300) == 4
    assert psi_band(301) == 5
    assert psi_band(400) == 5


def test_trend_needs_three_points():
    assert trend_slope([]) is None
    assert trend_slope(_readings([10, 12])) is None


def test_trend_flat():
    assert trend_slope(_readings([10, 10, 10])) == 0.0


def test_trend_rising():
    # +5 per hour
    assert trend_slope(_readings([10, 15, 20])) == 5.0


def test_trend_falling():
    # -3 per hour
    assert trend_slope(_readings([20, 17, 14])) == -3.0


def test_trend_uses_last_points_only():
    readings = _readings([5, 6, 7, 10, 12, 14])  # last three: 10,12,14
    assert trend_slope(readings) == 2.0
