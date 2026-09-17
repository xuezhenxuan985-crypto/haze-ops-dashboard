"""Reusable UI pieces: header, KPI row, region cards, RSS banner, decisions.

Pure rendering of the Snapshot — no fetching, no risk math here.
render_factor handles the nested i18n args (band_name / tier_name / source)
produced by advisory.explain_factors.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

import config
from ..i18n import tr
from ..data.models import RegionAdvisory, RegionPM25, RegionPSI, RegionWeather, Snapshot
from . import charts, theme

SGT = timezone(timedelta(hours=8))


def render_factor(key: str, args: dict, lang: str) -> str:
    """Format one explanation factor, translating nested i18n args first."""
    fmt = dict(args)
    for nested in ("band_name", "tier_name", "source"):
        v = fmt.get(nested)
        if isinstance(v, str) and v:
            fmt[nested] = tr(v, lang)
    return tr(key, lang, **fmt)


# ---------------------------------------------------------------------------
# Header + freshness
# ---------------------------------------------------------------------------
def _worst_region(snapshot: Snapshot) -> str | None:
    def key(region: str) -> tuple:
        a = snapshot.advisories.get(region)
        r = snapshot.pm25.get(region)
        return (a.risk_level if a else 0, r.pm25_1h if r else 0.0)
    if not snapshot.pm25:
        return None
    return max(snapshot.pm25, key=key)


def _fresh_badge(label: str, ts: datetime | None, ttl: int, lang: str) -> str:
    if ts is None:
        return theme.chip_html(f"{label}: {tr('freshness_stale', lang)}", "critical")
    age = datetime.now(SGT) - ts.astimezone(SGT)
    kind = "good" if age <= timedelta(seconds=ttl) else "warning"
    text = tr("freshness_ok", lang) if kind == "good" else tr("freshness_stale", lang)
    return theme.chip_html(f"{label} {ts.astimezone(SGT):%H:%M} · {text}", kind)


def render_header(snapshot: Snapshot, lang: str) -> None:
    left, right = st.columns([5, 2])
    with left:
        st.markdown(f"# {tr('app_title', lang)}")
        st.caption(tr("app_subtitle", lang))
    with right:
        mode_kind = "neutral" if snapshot.mode == "live" else "warning"
        mode_text = tr("mode_live", lang) if snapshot.mode == "live" else tr("mode_demo", lang)
        st.markdown(theme.badge_html(mode_text, mode_kind), unsafe_allow_html=True)
        worst = _worst_region(snapshot)
        if worst:
            a = snapshot.advisories.get(worst)
            r = snapshot.pm25.get(worst)
            risk = a.risk_level if a else r.band if r else 1
            st.markdown(
                f'{tr("overall_worst", lang)}: {tr(f"region_{worst}", lang)} '
                + theme.chip_html(tr(f"risk_{risk}", lang), theme.status_kind(risk)),
                unsafe_allow_html=True,
            )
    # Freshness strip
    fresh = snapshot.freshness
    ttl = {"pm25": config.TTL_PM25, "psi": config.TTL_PSI, "weather": config.TTL_WEATHER,
           "hotspots": config.TTL_HOTSPOTS, "rss": config.TTL_RSS}
    parts = [
        _fresh_badge(tr(f"freshness_{k}", lang), fresh.get(k), ttl.get(k, 900), lang)
        for k in ("pm25", "psi", "weather", "hotspots", "rss")
    ]
    st.markdown("&nbsp;&nbsp;".join(parts), unsafe_allow_html=True)


def render_flags(snapshot: Snapshot, lang: str) -> None:
    for flag in snapshot.flags:
        if flag == "demo_data_note":
            st.info(tr(flag, lang), icon="🎭")
        else:
            st.warning(tr(flag, lang), icon="⚠️")


def render_rss_banner(snapshot: Snapshot, lang: str) -> None:
    rss = snapshot.rss
    if rss.level:
        kind = theme.status_kind(min(rss.level + 1, 4))  # 1->warning, 2->serious, 3->critical
        text = tr("rss_alert_active", lang, level=rss.level)
        if rss.title:
            text += f" · {rss.title}"
        st.markdown(theme.badge_html(text, kind), unsafe_allow_html=True)
    else:
        st.markdown(theme.chip_html(tr("rss_no_alert", lang), "good"), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
def render_kpi_row(snapshot: Snapshot, lang: str) -> None:
    cols = st.columns(5)

    # 1. Peak 1-hr PM2.5 + its region, delta = 3-h trend.
    peak_r = max(snapshot.pm25, key=lambda r: snapshot.pm25[r].pm25_1h) if snapshot.pm25 else None
    with cols[0]:
        if peak_r:
            r = snapshot.pm25[peak_r]
            delta = f"{r.trend_3h:+.1f} µg/m³/h" if r.trend_3h is not None else None
            st.metric(tr("kpi_pm25", lang), f"{r.pm25_1h:.0f} µg/m³",
                      delta=delta, help=tr(f"region_{peak_r}", lang))
            st.caption(tr(f"region_{peak_r}", lang))
        else:
            st.metric(tr("kpi_pm25", lang), "—")

    # 2. Peak 24-hr PSI + region.
    peak_p = max(snapshot.psi, key=lambda r: snapshot.psi[r].psi_24h) if snapshot.psi else None
    with cols[1]:
        if peak_p:
            p = snapshot.psi[peak_p]
            st.metric(tr("kpi_psi", lang), f"{p.psi_24h:.0f}")
            st.caption(f'{tr(f"region_{peak_p}", lang)} · {tr(f"psi_tier_{p.tier}", lang)}')
        else:
            st.metric(tr("kpi_psi", lang), "—")

    # 3. Active hotspots (all sources) + yesterday delta.
    total = sum(s.count for s in snapshot.hotspots.values())
    ytotal = sum(s.yesterday_count or 0 for s in snapshot.hotspots.values())
    with cols[2]:
        delta = None
        if ytotal:
            diff = total - ytotal
            delta = f"{diff:+d} {tr('hs_yesterday', lang)}" if diff else None
        st.metric(tr("kpi_hotspots", lang), f"{total}", delta=delta)

    # 4. Transport risk level + upwind points.
    with cols[3]:
        t = snapshot.transport
        if t is not None:
            st.metric(tr("kpi_transport", lang), tr(f"transport_{t.level}", lang))
            st.caption(tr("kpi_upwind", lang, n=t.upwind_points))
        else:
            st.metric(tr("kpi_transport", lang), "—")

    # 5. ASMC alert level.
    with cols[4]:
        rss = snapshot.rss
        if rss.level:
            st.metric(tr("kpi_alert", lang), tr("rss_alert_active", lang, level=rss.level))
        else:
            st.metric(tr("kpi_alert", lang), tr("kpi_alert_off", lang))


# ---------------------------------------------------------------------------
# Region cards
# ---------------------------------------------------------------------------
def _trend_html(trend: float | None, lang: str) -> str:
    if trend is None:
        return theme.chip_html(tr("trend_flat", lang), "neutral")
    if trend >= config.TREND_MILD_RISE:
        return theme.chip_html(f"▲ {tr('trend_rising', lang)} {trend:+.1f}", "serious")
    if trend <= config.TREND_MILD_FALL:
        return theme.chip_html(f"▼ {tr('trend_falling', lang)} {trend:+.1f}", "good")
    return theme.chip_html(tr("trend_flat", lang), "neutral")


def render_region_card(region: str, snapshot: Snapshot, lang: str) -> None:
    r = snapshot.pm25.get(region)
    p = snapshot.psi.get(region)
    w = snapshot.weather.get(region)
    a = snapshot.advisories.get(region)
    with st.container(border=True):
        title_col, badge_col = st.columns([3, 2])
        with title_col:
            st.markdown(f"**{tr(f'region_{region}', lang)}**")
        with badge_col:
            if a:
                st.markdown(
                    theme.chip_html(tr(f"risk_{a.risk_level}", lang), theme.status_kind(a.risk_level)),
                    unsafe_allow_html=True,
                )
        if r is None:
            st.caption("—")
            return
        num_col, chip_col = st.columns([2, 1])
        with num_col:
            st.markdown(f"<span style='font-size:2rem;font-weight:700;color:{theme.INK['primary']};'>"
                        f"{r.pm25_1h:.0f}</span>"
                        f"<span style='color:{theme.INK['muted']};font-size:.85rem;'> µg/m³</span>",
                        unsafe_allow_html=True)
        with chip_col:
            st.markdown(theme.chip_html(tr(f"band_{r.band}", lang), theme.status_kind(r.band)),
                        unsafe_allow_html=True)
        st.markdown(_trend_html(r.trend_3h, lang), unsafe_allow_html=True)
        if len(r.readings_24h) >= 2:
            st.plotly_chart(charts.sparkline(r, region), width="stretch",
                            config={"displayModeBar": False})
        meta = []
        if p:
            meta.append(f"**{tr('card_psi', lang)}** {p.psi_24h:.0f} · "
                        + theme.chip_html(tr(f"psi_tier_{p.tier}", lang), theme.status_kind(p.tier)))
        if w:
            if w.temp_c is not None:
                meta.append(f"{tr('card_temp', lang)} {w.temp_c:.0f}°")
            if w.wind_speed_kmh is not None:
                arrow = (f"<span class='haze-arrow' style='transform:rotate({w.wind_dir_deg or 0:.0f}deg)'>"
                         f"↑</span>")
                meta.append(tr("card_wind", lang, dir=f"{w.wind_dir_deg or 0:.0f}",
                               speed=f"{w.wind_speed_kmh:.0f}") + f" {arrow}")
            if w.rainfall_mm > 0:
                meta.append(tr("card_rain_v", lang, value=f"{w.rainfall_mm:.1f}"))
        if meta:
            st.markdown(" · ".join(meta), unsafe_allow_html=True)


def render_weather_strip(snapshot: Snapshot, regions: list[str], lang: str) -> None:
    st.markdown(f"**{tr('weather_strip_title', lang)}**")
    cols = st.columns(len(regions) or 1)
    for col, region in zip(cols, regions):
        w = snapshot.weather.get(region)
        with col:
            lines = [f"**{tr(f'region_{region}', lang)}**"]
            if w:
                if w.temp_c is not None:
                    lines.append(f"{tr('label_temperature', lang)} {w.temp_c:.0f}°")
                if w.humidity_pct is not None:
                    lines.append(f"{tr('label_humidity', lang)} {w.humidity_pct:.0f}%")
                if w.wind_speed_kmh is not None:
                    lines.append(f"{tr('label_wind', lang)} {w.wind_dir_deg or 0:.0f}{tr('unit_deg', lang)} · "
                                 f"{w.wind_speed_kmh:.0f} {tr('unit_kmh', lang)}")
                if w.rainfall_mm > 0:
                    lines.append(f"{tr('label_rain', lang)} {w.rainfall_mm:.1f} {tr('unit_mm', lang)}")
            st.markdown("<br>".join(lines), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Decisions tab
# ---------------------------------------------------------------------------
_MATRIX_KIND = {"allowed": "good", "caution": "warning", "restricted": "critical"}


def render_matrix(advisory: RegionAdvisory, lang: str) -> None:
    m = advisory.matrix
    if m is None:
        return
    st.markdown(f"**{tr('matrix_title', lang)}**")
    header = (
        f"<tr><th>{tr('matrix_light', lang)}<br><span style='font-weight:400'>"
        f"{tr('matrix_light_ex', lang)}</span></th>"
        f"<th>{tr('matrix_moderate', lang)}<br><span style='font-weight:400'>"
        f"{tr('matrix_moderate_ex', lang)}</span></th>"
        f"<th>{tr('matrix_strenuous', lang)}<br><span style='font-weight:400'>"
        f"{tr('matrix_strenuous_ex', lang)}</span></th></tr>"
    )
    cells = []
    for state in (m.light, m.moderate, m.strenuous):
        kind = _MATRIX_KIND[state]
        bg, fg = theme.CHIPS[kind]
        cells.append(f"<td style='background:{bg};color:{fg};'>{tr(f'cell_{state}', lang)}</td>")
    st.markdown(
        f"<table class='haze-matrix'>{header}<tr>{''.join(cells)}</tr></table>",
        unsafe_allow_html=True,
    )
    for cell in ("light", "moderate", "strenuous"):
        reason_key = m.reasons.get(cell)
        if reason_key:
            st.markdown(f"<span class='haze-kpi-note'>{tr(f'matrix_{cell}', lang)}: "
                        f"{tr(reason_key, lang)}</span>", unsafe_allow_html=True)


def render_region_decision(region: str, snapshot: Snapshot, lang: str) -> None:
    a = snapshot.advisories.get(region)
    r = snapshot.pm25.get(region)
    if a is None or r is None:
        return
    st.markdown(f"### {tr('decisions_region_title', lang, region=tr(f'region_{region}', lang))}")
    st.markdown(
        f"{tr('risk_level_label', lang)} "
        + theme.chip_html(tr(f"risk_{a.risk_level}", lang), theme.status_kind(a.risk_level))
        + f" · {tr('risk_score_label', lang)} **{a.risk_score:.1f}** / 4",
        unsafe_allow_html=True,
    )

    st.markdown(f"**{tr('factors_title', lang)}**")
    for key, args in a.factors:
        st.markdown(f"- {render_factor(key, args, lang)}")

    left, right = st.columns(2)
    with left:
        st.info(f"**{tr('advice_nea_title', lang)}**\n\n"
                f"{tr(a.pm25_action_key, lang)}\n\n"
                + (f"*{tr('vulnerable_line', lang)}*" if r.band >= 2 else ""))
    with right:
        p = snapshot.psi.get(region)
        if p and a.psi_action_key:
            st.info(f"**{tr('advice_mom_title', lang)}**\n\n"
                    f"{tr(a.psi_action_key, lang)}\n\n"
                    f"*{tr('advice_psi_planning_note', lang)}*")
        else:
            st.info(f"**{tr('advice_mom_title', lang)}**\n\n{tr('flag_stale_psi', lang)}")

    render_matrix(a, lang)
    st.divider()


def render_hotspot_summary(snapshot: Snapshot, lang: str) -> None:
    if not snapshot.hotspots:
        st.markdown(f"*{tr('hs_no_data', lang)}*")
        return
    st.markdown(f"**{tr('hs_sources_title', lang)}**")
    cols = st.columns(len(snapshot.hotspots))
    for col, source in zip(cols, snapshot.hotspots):
        s = snapshot.hotspots[source]
        with col:
            st.markdown(f"**{tr(f'source_{source}', lang)}**")
            st.markdown(
                f"{tr('hs_today', lang)}: <b>{s.count}</b> {tr('hs_points', lang)}<br>"
                f"{tr('hs_yesterday', lang)}: "
                f"<b>{s.yesterday_count if s.yesterday_count is not None else '—'}</b>",
                unsafe_allow_html=True,
            )


def render_footer(lang: str) -> None:
    st.divider()
    st.markdown(
        f"<div class='haze-footer'>⚠️ {tr('footer_disclaimer', lang)}<br>"
        f"{tr('footer_sources', lang)} · "
        f"{tr('footer_cadence', lang, refresh=config.FRAGMENT_REFRESH_S)}</div>",
        unsafe_allow_html=True,
    )
