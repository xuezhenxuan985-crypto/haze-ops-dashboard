"""Plotly figures: 24-hr PM2.5, PSI bars, sparklines, upwind sector polar.

Palette rules: region lines use the fixed categorical series in fixed
order; band/tier zones use the status colors at low opacity; chart ground
is CHART_BG with CHART_GRID gridlines; text is ink, never series colors.
"""
from __future__ import annotations

import plotly.graph_objects as go

import config
from ..i18n import tr
from ..data.models import RegionPM25, Snapshot
from . import theme

_BAND_ZONES = (
    (56, 150, "warning", "chart_band_zone_2"),
    (151, 250, "serious", "chart_band_zone_3"),
    (251, 500, "critical", "chart_band_zone_4"),
)
_PSI_ZONES = (
    (101, 200, "serious", "chart_psi_zone_3"),
    (201, 300, "critical", "chart_psi_zone_4"),
    (301, 500, "critical", "chart_psi_zone_5"),
)


def _base_layout(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        template="none",
        paper_bgcolor=theme.CHART_BG,
        plot_bgcolor=theme.CHART_BG,
        font=dict(color=theme.INK["secondary"], size=12),
        margin=dict(l=8, r=8, t=44, b=8),
        hovermode="x unified",
        height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(gridcolor=theme.CHART_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=theme.CHART_GRID, zeroline=False)
    return fig


def pm25_24h_chart(snapshot: Snapshot, regions: list[str], lang: str) -> go.Figure:
    fig = go.Figure()
    max_v = 0.0
    for region in regions:
        r = snapshot.pm25.get(region)
        if r is None or not r.readings_24h:
            continue
        xs = [rd.timestamp for rd in r.readings_24h]
        ys = [rd.value for rd in r.readings_24h]
        max_v = max(max_v, *ys)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            name=tr(f"region_{region}", lang),
            line=dict(color=theme.REGION_COLORS[region], width=2),
        ))
    for lo, hi, kind, label_key in _BAND_ZONES:
        fig.add_hrect(
            y0=lo, y1=hi, fillcolor=theme.STATUS[kind], opacity=0.06,
            line_width=0, layer="below",
            annotation_text=tr(label_key, lang),
            annotation_position="top right",
            annotation_font=dict(color=theme.INK["muted"], size=10),
        )
    for edge in (55, 150, 250):
        fig.add_hline(
            y=edge, line=dict(color=theme.INK["muted"], width=1, dash="dot"),
            opacity=0.5,
        )
    fig.update_layout(title=tr("chart_pm25_title", lang))
    fig.update_yaxes(title=tr("unit_ugm3", lang), range=[0, max(max_v * 1.15, 300)])
    fig.update_xaxes(title="")
    return _base_layout(fig)


def psi_chart(snapshot: Snapshot, regions: list[str], lang: str) -> go.Figure:
    fig = go.Figure()
    names, values, colors = [], [], []
    for region in regions:
        p = snapshot.psi.get(region)
        if p is None:
            continue
        names.append(tr(f"region_{region}", lang))
        values.append(p.psi_24h)
        colors.append(theme.STATUS[theme.status_kind(p.tier)])
    fig.add_trace(go.Bar(
        x=names, y=values, marker_color=colors,
        text=[f"{v:.0f}" for v in values], textposition="outside",
        textfont=dict(color=theme.INK["primary"], size=12),
    ))
    for lo, hi, kind, label_key in _PSI_ZONES:
        fig.add_hrect(
            y0=lo, y1=hi, fillcolor=theme.STATUS[kind], opacity=0.06,
            line_width=0, layer="below",
            annotation_text=tr(label_key, lang),
            annotation_position="top right",
            annotation_font=dict(color=theme.INK["muted"], size=10),
        )
    fig.update_layout(title=tr("chart_psi_title", lang))
    fig.update_yaxes(title="PSI", range=[0, 400])
    return _base_layout(fig)


def sparkline(r: RegionPM25, region: str) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=[rd.timestamp for rd in r.readings_24h],
        y=[rd.value for rd in r.readings_24h],
        mode="lines",
        line=dict(color=theme.REGION_COLORS[region], width=1.5),
        hoverinfo="skip",
    ))
    fig.update_layout(
        template="none",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=40,
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def sector_chart(snapshot: Snapshot, lang: str) -> go.Figure:
    """Polar view: island wind direction and the ±45° upwind match sector."""
    t = snapshot.transport
    wind_dir = None
    for w in snapshot.weather.values():
        if w.wind_dir_deg is not None:
            wind_dir = w.wind_dir_deg
            break
    fig = go.Figure()
    if t is None or wind_dir is None:
        fig.add_annotation(text=tr("factor_transport_nowind", lang, points=0),
                           showarrow=False)
        fig.update_layout(
            template="none", height=280, paper_bgcolor=theme.CHART_BG,
            plot_bgcolor=theme.CHART_BG, margin=dict(l=8, r=8, t=44, b=8),
        )
        return fig
    kind = "neutral" if not t.level else theme.status_kind(t.level)
    sector_color = theme.STATUS.get(kind, theme.INK["muted"])
    theta = [(wind_dir - config.SECTOR_HALF_WIDTH_DEG) % 360,
             (wind_dir - config.SECTOR_HALF_WIDTH_DEG) % 360,
             (wind_dir + config.SECTOR_HALF_WIDTH_DEG) % 360,
             (wind_dir + config.SECTOR_HALF_WIDTH_DEG) % 360]
    fig.add_trace(go.Scatterpolar(
        r=[0, 1, 1, 0], theta=theta, fill="toself",
        fillcolor=sector_color, opacity=0.22,
        line=dict(color=sector_color, width=1),
        name=tr("kpi_transport", lang),
    ))
    fig.add_trace(go.Scatterpolar(
        r=[0.55], theta=[wind_dir],
        mode="markers+text",
        marker=dict(color=theme.INK["primary"], size=9),
        text=[f"{tr('label_wind', lang)} {wind_dir:.0f}{tr('unit_deg', lang)}"],
        textfont=dict(color=theme.INK["primary"], size=12),
        textposition="top center",
        showlegend=False,
    ))
    fig.update_layout(
        title=tr("chart_sector_title", lang),
        template="none",
        paper_bgcolor=theme.CHART_BG,
        plot_bgcolor=theme.CHART_BG,
        font=dict(color=theme.INK["secondary"], size=12),
        margin=dict(l=8, r=8, t=44, b=8),
        height=280,
        polar=dict(
            radialaxis=dict(visible=False, range=[0, 1]),
            angularaxis=dict(
                direction="clockwise", rotation=90,
                tickfont=dict(color=theme.INK["muted"], size=10),
                gridcolor=theme.CHART_GRID,
            ),
        ),
    )
    return fig
