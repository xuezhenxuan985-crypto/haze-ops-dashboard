"""Folium map for the hotspot tab, rendered via st.components.v1.html.

Circles = source-region totals (ASMC); clusters = individual NASA FIRMS
detections (only when a key is provided). No streamlit-folium dependency
(abandoned) and no Mapbox token needed — OSM tiles are free.
"""
from __future__ import annotations

import folium
from folium.plugins import MarkerCluster

from ..i18n import tr
from ..data.models import Snapshot
from . import theme

# Display centroids for the source-region summary circles.
_SOURCE_CENTROIDS = {
    "sumatra": (0.5, 102.0),
    "kalimantan": (0.0, 113.5),
    "p_malaysia": (4.0, 102.0),
}


def build_map(snapshot: Snapshot, lang: str) -> str:
    m = folium.Map(
        location=[0.8, 104.5], zoom_start=6,
        tiles="OpenStreetMap", control_scale=True,
    )

    # Source-region totals as sized circles.
    for source, s in snapshot.hotspots.items():
        if not s.count:
            continue
        lat, lon = _SOURCE_CENTROIDS.get(source, (0.0, 104.0))
        color = theme.SOURCE_COLORS.get(source, theme.INK["muted"])
        label = tr(f"source_{source}", lang)
        folium.CircleMarker(
            location=[lat, lon],
            radius=min(30, 8 + s.count ** 0.5 * 1.4),
            color=color, weight=2, fill=True, fill_opacity=0.4,
            popup=folium.Popup(f"{label}: {s.count} {tr('hs_points', lang)}", max_width=240),
            tooltip=f"{label}: {s.count}",
        ).add_to(m)

    # Singapore reference marker.
    folium.Marker(
        location=[1.35, 103.82],  # (lat, lon)
        popup="Singapore",
        icon=folium.Icon(color="blue", icon="star"),
    ).add_to(m)

    # FIRMS individual detections in a marker cluster (display only).
    if snapshot.firms_points:
        cluster = MarkerCluster(name="FIRMS").add_to(m)
        for p in snapshot.firms_points:
            color = theme.SOURCE_COLORS.get(p.get("source", ""), "#888")
            folium.CircleMarker(
                location=[p["lat"], p["lon"]],
                radius=5, color=color, weight=1, fill=True, fill_opacity=0.6,
                popup=folium.Popup(
                    f"{p.get('lat'):.3f}, {p.get('lon'):.3f}<br>"
                    f"confidence: {p.get('confidence', '—')}<br>"
                    f"bright_ti4: {p.get('bright_ti4', '—')} K<br>"
                    f"FRP: {p.get('frp', '—')} MW",
                    max_width=260,
                ),
            ).add_to(cluster)
        folium.LayerControl().add_to(m)

    return m.get_root().render()
