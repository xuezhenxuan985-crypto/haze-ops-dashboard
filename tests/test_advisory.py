"""Decision rules: key mapping, the >300 wording rule, matrix table."""
from src.risk.advisory import (advisory_for_pm25, advisory_for_psi, explain_factors,
                               work_matrix_for_psi)
from src.i18n import STRINGS, tr
from src.data.models import (Reading, RegionPM25, RegionPSI, RegionWeather,
                             TransportRisk)
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))
T0 = datetime(2026, 9, 17, 12, tzinfo=SGT)


def test_pm25_action_keys():
    assert advisory_for_pm25(1) == "pm25_action_1"
    assert advisory_for_pm25(4) == "pm25_action_4"


def test_psi_action_keys():
    assert advisory_for_psi(1) == "psi_action_1"
    assert advisory_for_psi(5) == "psi_action_5"


def test_tier4_never_says_stop():
    for lang in ("en", "zh"):
        for tier in (1, 2, 3, 4, 5):
            text = tr(advisory_for_psi(tier), lang).lower()
            assert "stop" not in text
            assert "全面停" not in text
            assert "停工" not in text


def test_vulnerable_line_exists_for_band2_plus():
    for lang in ("en", "zh"):
        assert tr("vulnerable_line", lang)


def test_matrix_tier1_all_allowed():
    m = work_matrix_for_psi(1)
    assert (m.light, m.moderate, m.strenuous) == ("allowed", "allowed", "allowed")
    assert m.reasons["light"] == "reason_all_allowed"


def test_matrix_tier2():
    m = work_matrix_for_psi(2)
    assert (m.light, m.moderate, m.strenuous) == ("allowed", "caution", "caution")
    assert m.reasons["strenuous"] == "reason_strenuous_caution"


def test_matrix_tier3():
    m = work_matrix_for_psi(3)
    assert (m.light, m.moderate, m.strenuous) == ("allowed", "caution", "restricted")


def test_matrix_tier4_and_5():
    expected = ("caution", "restricted", "restricted")
    assert (work_matrix_for_psi(4).light, work_matrix_for_psi(4).moderate, work_matrix_for_psi(4).strenuous) == expected
    assert (work_matrix_for_psi(5).light, work_matrix_for_psi(5).moderate, work_matrix_for_psi(5).strenuous) == expected


def _pm25(value, trend):
    r = RegionPM25(region="north", pm25_1h=value, band=2,
                   readings_24h=[Reading(T0 - timedelta(hours=2 - i), value + i) for i in range(3)])
    r.trend_3h = trend
    return r


def test_explain_factors_structure():
    pm25 = _pm25(78.0, 6.0)  # >= 5 µg/m³/h -> rising factor
    psi = RegionPSI(region="north", psi_24h=103.0, pm25_24h=55.0, tier=3)
    weather = RegionWeather(region="north", rainfall_mm=0.0, wind_speed_kmh=5.0)
    t = TransportRisk(level=2, score=40.0, upwind_points=25, dominant_source="kalimantan", wind_available=True)
    factors = explain_factors(pm25, psi, weather, t)
    keys = [k for k, _ in factors]
    assert keys[0] == "factor_pm25_band"
    assert "factor_trend_rise" in keys
    assert "factor_psi" in keys
    assert "factor_transport_some" in keys
    assert "factor_transport_note" in keys
    # band_name / tier_name / source args are themselves i18n keys
    band_args = dict(factors[0][1])
    assert band_args["band_name"] == "band_2"
    some_args = dict(factors[keys.index("factor_transport_some")][1])
    assert some_args["source"] == "source_kalimantan"


def test_explain_factors_no_transport_points():
    pm25 = _pm25(30.0, None)
    weather = RegionWeather(region="north", rainfall_mm=0.0, wind_speed_kmh=5.0)
    t = TransportRisk(level=0, score=0.0, upwind_points=0, dominant_source=None, wind_available=True)
    keys = [k for k, _ in explain_factors(pm25, None, weather, t)]
    assert "factor_transport_none" in keys
