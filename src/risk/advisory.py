"""Work decision rules.

Immediate actions key off the 1-hr PM2.5 band (NEA health advice); work
planning keys off the official rolling 24-hr PSI (MOM employer measures).
Wording rule: at PSI > 300 the guidance is "minimise outdoor work / defer
non-essential work" — it must NEVER say work stops (unit-tested).
"""
from __future__ import annotations

import config
from ..data.models import RegionPM25, RegionPSI, RegionWeather, TransportRisk, WorkMatrix


def advisory_for_pm25(band: int) -> str:
    return f"pm25_action_{band}"


def advisory_for_psi(tier: int) -> str:
    return f"psi_action_{tier}"


# (light, moderate, strenuous) per PSI tier 1-5. Tier 5 (>400) tightens
# light work to caution; the matrix is otherwise identical to tier 4.
_MATRIX = {
    1: ("allowed", "allowed", "allowed"),
    2: ("allowed", "caution", "caution"),
    3: ("allowed", "caution", "restricted"),
    4: ("caution", "restricted", "restricted"),
    5: ("caution", "restricted", "restricted"),
}

_REASONS = {
    ("light", "caution"): "reason_light_caution",
    ("moderate", "caution"): "reason_moderate_caution",
    ("moderate", "restricted"): "reason_moderate_restricted",
    ("strenuous", "caution"): "reason_strenuous_caution",
    ("strenuous", "restricted"): "reason_strenuous_restricted",
}


def work_matrix_for_psi(tier: int) -> WorkMatrix:
    light, moderate, strenuous = _MATRIX[tier]
    if light == moderate == strenuous == "allowed":
        reasons = {"light": "reason_all_allowed", "moderate": "reason_all_allowed", "strenuous": "reason_all_allowed"}
    else:
        reasons = {
            "light": _REASONS.get(("light", light), "reason_all_allowed"),
            "moderate": _REASONS.get(("moderate", moderate), "reason_all_allowed"),
            "strenuous": _REASONS.get(("strenuous", strenuous), "reason_all_allowed"),
        }
    return WorkMatrix(light=light, moderate=moderate, strenuous=strenuous, reasons=reasons)


def explain_factors(
    pm25: RegionPM25,
    psi: RegionPSI | None,
    weather: RegionWeather,
    transport: TransportRisk | None,
) -> list[tuple[str, dict]]:
    """Ordered (i18n template key, format args) bullets explaining the risk.

    Args that are themselves i18n keys ("band_name", "tier_name", "source")
    are translated by the UI's render_factor helper before formatting.
    """
    factors: list[tuple[str, dict]] = [
        ("factor_pm25_band", {"value": pm25.pm25_1h, "band": pm25.band, "band_name": f"band_{pm25.band}"}),
    ]
    t = pm25.trend_3h
    if t is None:
        factors.append(("factor_trend_none", {}))
    elif t >= config.TREND_MILD_RISE:
        factors.append(("factor_trend_rise", {"slope": abs(round(t, 1))}))
    elif t <= config.TREND_MILD_FALL:
        factors.append(("factor_trend_fall", {"slope": abs(round(t, 1))}))
    else:
        factors.append(("factor_trend_flat", {}))
    if psi is not None:
        factors.append(("factor_psi", {"value": psi.psi_24h, "tier_name": f"psi_tier_{psi.tier}"}))
    if transport is not None:
        if not transport.wind_available and transport.total_points:
            factors.append(("factor_transport_nowind", {"points": transport.total_points}))
        elif transport.upwind_points == 0:
            factors.append(("factor_transport_none", {}))
        else:
            factors.append(("factor_transport_some", {
                "upwind": transport.upwind_points,
                "source": f"source_{transport.dominant_source}" if transport.dominant_source else "source_sumatra",
            }))
        factors.append(("factor_transport_note", {}))
    if weather.rainfall_mm >= config.RAIN_SUPPRESSION_MM:
        factors.append(("factor_rain", {"value": weather.rainfall_mm}))
    if weather.wind_speed_kmh is not None and weather.wind_speed_kmh >= config.WIND_DISPERSION_KMH:
        factors.append(("factor_wind_disp", {"value": weather.wind_speed_kmh}))
    return factors
