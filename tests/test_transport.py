"""Transport risk geometry and scoring.

Regression fixture: Pekanbaru (~101.45E, 0.50N) sits ~WSW of Singapore, so
the bearing FROM Singapore is ~250°; a wind coming FROM 250° matches the
sector, a wind from 70° does not. (Earlier designs compared the reversed
bearing — this test locks the fix in.)
"""
from src.risk.transport import (_distance_weight, angle_diff, bearing_from_sg,
                                compute_transport_risk, haversine_km)
from src.data.models import SourceHotspots

PEKANBARU = (101.45, 0.50)  # lon, lat
PONTIANAK = (109.33, -0.02)


def _hs(source, n, point=PEKANBARU, yesterday=None):
    return {source: SourceHotspots(source=source, count=n, points=[point] * n, yesterday_count=yesterday)}


def test_angle_diff_wraparound():
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == 20
    assert angle_diff(0, 180) == 180
    assert angle_diff(45, 45) == 0


def test_bearing_from_sg():
    # Pekanbaru is WSW of Singapore: bearing ~240-265.
    b = bearing_from_sg(*PEKANBARU)
    assert 235.0 <= b <= 270.0
    # Pontianak is ESE of Singapore: bearing ~95-125.
    b2 = bearing_from_sg(*PONTIANAK)
    assert 90.0 <= b2 <= 130.0


def test_haversine_known_pair():
    # ~0.18° of longitude at the equator is ~20 km.
    d = haversine_km(103.82, 1.35, 104.0, 1.35)
    assert 19.0 <= d <= 21.5


def test_distance_weight_boundaries():
    assert _distance_weight(399) == 1.0
    assert _distance_weight(400) == 0.6
    assert _distance_weight(699) == 0.6
    assert _distance_weight(700) == 0.3


def test_sector_match_pekambaru_wind_from_250():
    risk = compute_transport_risk(_hs("sumatra", 10), wind_dir_deg=250.0)
    assert risk.upwind_points == 10
    assert risk.wind_available is True
    assert risk.dominant_source == "sumatra"
    assert risk.score == 10.0  # 10 x 1.0 distance x 1.0 match


def test_sector_mismatch_wind_from_70():
    risk = compute_transport_risk(_hs("sumatra", 10), wind_dir_deg=70.0)
    assert risk.upwind_points == 0
    assert risk.score == 10 * 0.35


def test_sector_boundary_at_45():
    b = bearing_from_sg(*PEKANBARU)
    inside = compute_transport_risk(_hs("sumatra", 5), wind_dir_deg=(b + 45) % 360)
    outside = compute_transport_risk(_hs("sumatra", 5), wind_dir_deg=(b + 46) % 360)
    assert inside.upwind_points == 5
    assert outside.upwind_points == 0


def test_no_wind_data():
    risk = compute_transport_risk(_hs("sumatra", 10), wind_dir_deg=None)
    assert risk.wind_available is False
    assert risk.upwind_points == 0
    assert risk.score == 10 * 0.5


def test_level_thresholds():
    # Matched points at distance <400 km: score == count.
    assert compute_transport_risk(_hs("sumatra", 19), 250.0).level == 1
    assert compute_transport_risk(_hs("sumatra", 20), 250.0).level == 2
    assert compute_transport_risk(_hs("sumatra", 80), 250.0).level == 3
    assert compute_transport_risk(_hs("sumatra", 200), 250.0).level == 4
    assert compute_transport_risk(_hs("sumatra", 0), 250.0).level == 0


def test_surge_factor():
    base = compute_transport_risk(_hs("sumatra", 10, yesterday=4), 250.0)  # 10 >= 2*4
    assert base.score == 12.0  # 10 x 1.2


def test_no_surge_when_yesterday_high():
    risk = compute_transport_risk(_hs("sumatra", 10, yesterday=9), 250.0)
    assert risk.score == 10.0


def test_total_points_counted():
    risk = compute_transport_risk(_hs("sumatra", 7), 70.0)
    assert risk.total_points == 7
