"""Collect a reproducible snapshot of all project data for the analysis.

Run from the repo root:
    .venv/bin/python analysis/scripts/fetch_snapshot.py

Writes analysis/data/:
  history_pm25_raw.csv   raw runtime history file as of today (before appends)
  live_*.csv             live NEA PM2.5 / PSI / weather / hotspots / transport
  live_advisories.csv    risk engine output per region on live data
  demo_pm25_24h.csv      synthetic 24-h series for the 3 demo scenarios
  demo_advisories.csv    risk engine output per region per demo scenario

NOTE: nea_pm25.fetch_pm25() appends one row per region to data/history_pm25.csv
(that is how the app persists history), so running this script appends 5 rows.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.data import history, hotspots, nea_pm25, nea_psi, nea_weather  # noqa: E402
from src.data.pipeline import _demo_inputs, assemble_snapshot  # noqa: E402

OUT = ROOT / "analysis" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# 1. Freeze the runtime history file before any new appends happen.
shutil.copyfile(config.HISTORY_CSV, OUT / "history_pm25_raw.csv")

# 2. Live NEA fetches + ASMC hotspots + RSS alert.
pm25, pm25_ts = nea_pm25.fetch_pm25()
psi, psi_ts = nea_psi.fetch_psi()
weather, weather_ts = nea_weather.fetch_weather()
sources = hotspots.fetch_asmc_hotspots()
daily = hotspots.fetch_asmc_daily_counts()
if daily:
    import datetime as dt
    yesterday = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    row = daily.get(yesterday) or {}
    for s, src in sources.items():
        if src.yesterday_count is None and row.get(s):
            src.yesterday_count = row[s]
rss = hotspots.fetch_rss()
history_df = history.load_pm25_history()

snap = assemble_snapshot(
    mode="live", pm25=pm25, psi=psi, weather=weather, hotspots_=sources,
    rss=rss, history_df=history_df, firms_points=[], flags=[],
    freshness={"pm25": pm25_ts, "psi": psi_ts, "weather": weather_ts,
               "hotspots": max((s.fetched_at for s in sources.values() if s.fetched_at), default=None),
               "rss": rss.fetched_at},
)

pd.DataFrame([
    {"region": r, "pm25_1h": d.pm25_1h, "band": d.band, "trend_3h": d.trend_3h,
     "n_readings": len(d.readings_24h)}
    for r, d in snap.pm25.items()
]).to_csv(OUT / "live_pm25.csv", index=False)

pd.DataFrame([
    {"region": r, "psi_24h": d.psi_24h, "pm25_24h": d.pm25_24h, "tier": d.tier}
    for r, d in snap.psi.items()
]).to_csv(OUT / "live_psi.csv", index=False)

pd.DataFrame([
    {"region": r, "temp_c": w.temp_c, "humidity_pct": w.humidity_pct,
     "wind_speed_kmh": w.wind_speed_kmh, "wind_dir_deg": w.wind_dir_deg,
     "rainfall_mm": w.rainfall_mm, "station_count": w.station_count}
    for r, w in snap.weather.items()
]).to_csv(OUT / "live_weather.csv", index=False)

pd.DataFrame([
    {"source": s, "count": d.count, "yesterday_count": d.yesterday_count,
     "fetched_at": d.fetched_at, "n_points": len(d.points)}
    for s, d in snap.hotspots.items()
]).to_csv(OUT / "live_hotspots.csv", index=False)

t = snap.transport
pd.DataFrame([{
    "level": t.level if t else None, "score": t.score if t else None,
    "upwind_points": t.upwind_points if t else None,
    "dominant_source": t.dominant_source if t else None,
    "wind_available": t.wind_available if t else None,
    "total_points": t.total_points if t else None,
}]).to_csv(OUT / "live_transport.csv", index=False)

# Per-region hotspot points (for maps / spatial checks).
pd.DataFrame([
    {"source": s, "lon": lon, "lat": lat}
    for s, d in snap.hotspots.items() for lon, lat in d.points
]).to_csv(OUT / "live_hotspot_points.csv", index=False)

pd.DataFrame([
    {"region": r, "risk_level": a.risk_level, "risk_score": a.risk_score,
     "pm25_band": snap.pm25[r].band, "trend_3h": snap.pm25[r].trend_3h,
     "psi_tier": snap.psi[r].tier if r in snap.psi else None}
    for r, a in snap.advisories.items()
]).to_csv(OUT / "live_advisories.csv", index=False)

# 3. Demo scenarios: full 24-h series + advisory table.
demo_rows, demo_adv = [], []
for scenario in config.DEMO_SCENARIOS:
    inputs = _demo_inputs(scenario)
    dsnap = assemble_snapshot(**inputs)
    for region, r in dsnap.pm25.items():
        for rd in r.readings_24h:
            demo_rows.append({"scenario": scenario, "timestamp": rd.timestamp,
                              "region": region, "pm25": rd.value})
    for region, a in dsnap.advisories.items():
        demo_adv.append({
            "scenario": scenario, "region": region,
            "risk_level": a.risk_level, "risk_score": a.risk_score,
            "pm25_1h": dsnap.pm25[region].pm25_1h, "band": dsnap.pm25[region].band,
            "trend_3h": dsnap.pm25[region].trend_3h,
            "psi_24h": dsnap.psi[region].psi_24h if region in dsnap.psi else None,
            "transport_level": dsnap.transport.level if dsnap.transport else None,
            "upwind_points": dsnap.transport.upwind_points if dsnap.transport else None,
        })
pd.DataFrame(demo_rows).to_csv(OUT / "demo_pm25_24h.csv", index=False)
pd.DataFrame(demo_adv).to_csv(OUT / "demo_advisories.csv", index=False)

print("snapshot saved to", OUT)
print("live fetched at:", snap.fetched_at, "| rss:", rss.level, rss.title)
print("history rows in app view (48h prune):", len(history_df) if history_df is not None else None)
