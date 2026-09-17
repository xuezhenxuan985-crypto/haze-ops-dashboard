"""Haze Ops Dashboard — entry point. Run with: streamlit run app.py

Sidebar (outside the auto-refresh fragment): mode, demo scenario, FIRMS key,
language, manual refresh, region filter. The main body re-renders every
config.FRAGMENT_REFRESH_S seconds via @st.fragment(run_every=...).
"""
from __future__ import annotations

import streamlit as st

import config
from src.i18n import tr
from src.data.pipeline import get_snapshot
from src.ui import charts, components, map_view, theme

st.set_page_config(page_title="Haze Ops Dashboard", page_icon="🌫️", layout="wide")
theme.inject_css()

st.session_state.setdefault("lang_control", "EN")
st.session_state.setdefault("firms_key", "")
st.session_state.setdefault("force_version", 0)


def _lang() -> str:
    return "en" if st.session_state.get("lang_control") == "EN" else "zh"


lang = _lang()

# ---------------------------------------------------------------------------
# Sidebar — outside the fragment, so it does not rerun every 5 min
# ---------------------------------------------------------------------------
with st.sidebar:
    mode = st.radio(
        tr("sidebar_mode", lang), ["live", "demo"], key="mode",
        format_func=lambda m: tr(f"sidebar_mode_{m}", lang),
    )
    scenario = config.DEMO_SCENARIOS[0]
    if mode == "demo":
        scenario = st.selectbox(
            tr("sidebar_scenario", lang), config.DEMO_SCENARIOS, key="scenario",
            format_func=lambda s: tr(f"scenario_{s}", lang),
        )
    if mode == "live":
        st.text_input(
            tr("sidebar_firms_key", lang), type="password", key="firms_key",
            help=tr("sidebar_firms_help", lang),
        )
    st.segmented_control(
        tr("sidebar_language", lang), ["EN", "中文"], key="lang_control",
        label_visibility="collapsed",
    )
    lang = _lang()
    if st.button(tr("sidebar_refresh", lang), use_container_width=True):
        st.session_state.force_version += 1
    selected = st.multiselect(
        tr("sidebar_regions", lang), config.REGIONS, default=config.REGIONS,
        key="selected_regions",
        format_func=lambda r: tr(f"region_{r}", lang),
    )
    with st.expander(tr("sidebar_sources_title", lang)):
        st.write(tr("sidebar_sources_body", lang))


# ---------------------------------------------------------------------------
# Main body — auto-refreshing fragment
# ---------------------------------------------------------------------------
@st.fragment(run_every=config.FRAGMENT_REFRESH_S)
def main() -> None:
    lang = _lang()
    snapshot = get_snapshot(
        mode, scenario, st.session_state.force_version,
        st.session_state.get("firms_key", ""),
    )
    if snapshot is None:
        st.error(f"{tr('flag_stale_pm25', lang)} / {tr('flag_stale_weather', lang)}")
        st.markdown(f"*{tr('demo_data_note', lang)}*")
        return

    regions = [r for r in config.REGIONS if r in selected and r in snapshot.pm25]
    components.render_header(snapshot, lang)
    components.render_flags(snapshot, lang)
    components.render_rss_banner(snapshot, lang)
    components.render_kpi_row(snapshot, lang)

    st.markdown("---")
    card_cols = st.columns(len(regions) or 1)
    for col, region in zip(card_cols, regions):
        with col:
            components.render_region_card(region, snapshot, lang)

    tab_aq, tab_hs, tab_dec = st.tabs([
        tr("tab_air_quality", lang), tr("tab_hotspots", lang), tr("tab_decisions", lang),
    ])

    with tab_aq:
        st.plotly_chart(charts.pm25_24h_chart(snapshot, regions, lang),
                        width="stretch", config={"displayModeBar": False})
        st.plotly_chart(charts.psi_chart(snapshot, regions, lang),
                        width="stretch", config={"displayModeBar": False})
        components.render_weather_strip(snapshot, regions, lang)
        with st.expander(tr("view_table", lang)):
            rows = []
            for region in regions:
                r = snapshot.pm25[region]
                rows.extend({"region": tr(f"region_{region}", lang),
                             "time": rd.timestamp.strftime("%H:%M"),
                             "pm25": rd.value} for rd in r.readings_24h)
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)
            else:
                st.caption(tr("chart_history_empty", lang))

    with tab_hs:
        map_col, side_col = st.columns([3, 1])
        with map_col:
            st.iframe(map_view.build_map(snapshot, lang), height=520)
        with side_col:
            components.render_hotspot_summary(snapshot, lang)
            st.markdown(f"<span class='haze-kpi-note'>{tr('hs_map_hint', lang)}</span>",
                        unsafe_allow_html=True)
            st.plotly_chart(charts.sector_chart(snapshot, lang),
                            width="stretch", config={"displayModeBar": False})

    with tab_dec:
        for region in regions:
            components.render_region_decision(region, snapshot, lang)

    components.render_footer(lang)


main()
