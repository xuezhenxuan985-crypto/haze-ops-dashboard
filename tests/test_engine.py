"""Regional risk engine: determinism, clamping, exact level cutoffs."""
from src.risk.engine import compute_region_risk
from src.risk.transport import compute_transport_risk
from src.data.models import RegionWeather, SourceHotspots, TransportRisk


def _weather(rain=0.0, wind_kmh=5.0):
    return RegionWeather(region="north", rainfall_mm=rain, wind_speed_kmh=wind_kmh, station_count=3)


def _transport(level):
    return TransportRisk(level=level, score=0.0, upwind_points=0, dominant_source=None, wind_available=True)


def test_baseline_band1_is_level1():
    level, score = compute_region_risk(1, None, None, _weather())
    assert (level, score) == (1, 1.0)


def test_band_drives_score():
    level, score = compute_region_risk(3, None, None, _weather())
    assert level == 3
    assert score == 3.0


def test_trend_boundaries():
    assert compute_region_risk(1, 5.0, None, _weather())[0] == 1   # 1.5 cutoff inclusive
    assert compute_region_risk(1, 10.0, None, _weather())[0] == 2  # 2.0
    assert compute_region_risk(1, -5.0, None, _weather())[0] == 1  # clamped
    assert compute_region_risk(2, -10.0, None, _weather())[1] == 1.0


def test_transport_adder_boundary():
    # band 2 + transport level 4 (1.5) = 3.5 -> level 3 (cutoff inclusive)
    level, score = compute_region_risk(2, None, _transport(4), _weather())
    assert (level, score) == (3, 3.5)


def test_rain_and_wind_modifiers():
    level, score = compute_region_risk(1, None, None, _weather(rain=1.0))
    assert score == 1.0  # 1.0 - 0.5 clamped back to 1.0
    level, score = compute_region_risk(1, None, None, _weather(wind_kmh=20.0))
    assert score == 1.0  # clamped


def test_clamp_at_4():
    level, score = compute_region_risk(4, 10.0, _transport(4), _weather())
    assert score == 4.0
    assert level == 4


def test_determinism():
    args = (2, 3.2, _transport(2), _weather(rain=0.2, wind_kmh=8.0))
    assert compute_region_risk(*args) == compute_region_risk(*args)


def test_boundary_scores():
    # Exact cutoff values: 1.5 -> level 1, 2.5 -> 2, 3.5 -> 3 (inclusive),
    # 4.0 -> level 4. Adders move in 0.5 steps so these are reachable.
    assert compute_region_risk(1, None, None, _weather()) == (1, 1.0)
    assert compute_region_risk(1, 5.0, None, _weather()) == (1, 1.5)
    assert compute_region_risk(2, 5.0, None, _weather()) == (2, 2.5)
    assert compute_region_risk(3, 5.0, None, _weather()) == (3, 3.5)
    assert compute_region_risk(3, 10.0, None, _weather()) == (4, 4.0)
