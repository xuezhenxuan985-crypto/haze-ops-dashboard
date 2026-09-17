"""Visual theme: palette constants, CSS injection, chip/badge HTML helpers.

Palette discipline (from the plan, adopted in place of the dataviz skill's
palette): status colors are used ONLY for bands / risk / PSI tiers — never as
data series colors. Region lines use the fixed categorical series in fixed
order (the order itself is a colorblind-safe signal). Chips are light-bg /
dark-fg with >= 4.5:1 contrast. Text uses ink colors. No color is ever the
sole state carrier — every chip and badge carries text.
"""
from __future__ import annotations

import streamlit as st

# Status colors: band 1..4 / risk level 1..4 / PSI tier gradient.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
_STATUS_ORDER = ("good", "warning", "serious", "critical")

# Region series colors, fixed order (north..central).
REGION_COLORS = {
    "north": "#2a78d6",
    "south": "#eb6834",
    "east": "#1baf7a",
    "west": "#eda100",
    "central": "#e87ba4",
}

# Source-region map colors (categorical; roles differ from SG region lines).
SOURCE_COLORS = {
    "sumatra": "#e87ba4",
    "kalimantan": "#1baf7a",
    "p_malaysia": "#eb6834",
}

# Chip pairs (background, foreground) — light bg / dark fg, >= 4.5:1.
CHIPS = {
    "good": ("#D3F9D8", "#1B4332"),
    "warning": ("#FFF0C2", "#6B4E00"),
    "serious": ("#FBDCCB", "#7A3412"),
    "critical": ("#F9D6D6", "#7A1F1F"),
    "neutral": ("#E9E9E4", "#41413B"),
}

# Ink (text) colors — never series colors for text.
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781"}

CHART_BG = "#fcfcfb"
CHART_GRID = "#e1e0d9"

_CSS = """
<style>
.haze-footer { color: #898781; font-size: .78rem; }
.haze-kpi-note { color: #52514e; font-size: .8rem; }
.haze-arrow { display: inline-block; font-size: 1rem; }
div[data-testid="stMetric"] {
    background: #fcfcfb;
    border: 1px solid #e1e0d9;
    border-radius: 10px;
    padding: .6rem .8rem;
}
div[data-testid="stMetricLabel"] p { color: #52514e !important; }
table.haze-matrix { border-collapse: separate; border-spacing: 5px; }
table.haze-matrix th, table.haze-matrix td { border-radius: 8px; padding: 8px 14px; text-align: center; }
table.haze-matrix th { background: #f2f1ec; color: #41413B; font-size: .8rem; font-weight: 700; }
table.haze-matrix td { font-weight: 600; white-space: nowrap; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def status_kind(level: int) -> str:
    """Map a 1..4 band/risk level (or 1..5 PSI tier) onto a status color."""
    if level <= 1:
        return "good"
    if level == 2:
        return "warning"
    if level == 3:
        return "serious"
    return "critical"


def chip_html(text: str, kind: str) -> str:
    bg, fg = CHIPS.get(kind, CHIPS["neutral"])
    return (
        f'<span style="background:{bg};color:{fg};font-weight:600;'
        f'border-radius:10px;padding:2px 10px;font-size:.82rem;'
        f'white-space:nowrap;border:1px solid {fg}26;">{text}</span>'
    )


def badge_html(text: str, kind: str) -> str:
    """Mode badges (LIVE/DEMO) and RSS banners — chip with a status dot."""
    bg, fg = CHIPS.get(kind, CHIPS["neutral"])
    dot = STATUS.get(kind, INK["muted"])
    return (
        f'<span style="background:{bg};color:{fg};font-weight:700;'
        f'border-radius:12px;padding:3px 12px;font-size:.85rem;'
        f'white-space:nowrap;border:1px solid {fg}2e;">'
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
        f'background:{dot};margin-right:6px;"></span>{text}</span>'
    )
