# Haze Ops — Singapore Regional Haze Risk & Outdoor Work Decision Dashboard

A live monitoring dashboard for construction contractors' Operations / EHS managers in Singapore.
It tracks 1-hr PM2.5 and 24-hr PSI across the five NEA reporting regions, combines ASMC satellite
hotspots with station weather, computes a regional risk level, and gives outdoor-work guidance
worded to match official MOM measures. Bilingual EN / 中文.

## Getting Started

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Then open the printed URL (default http://localhost:8501).

- **Live mode** (default): pulls from the NEA data.gov.sg realtime API and ASMC hotspot files —
  both free and keyless. No configuration needed.
- **Demo mode**: synthetic data with three deterministic scenarios (clear / moderate haze /
  haze episode). Works fully offline — useful for demos and screenshots.
- **NASA FIRMS (optional enrichment)**: register for a free key at
  [firms.modaps.eosdis.nasa.gov/api/map_key/](https://firms.modaps.eosdis.nasa.gov/api/map_key/)
  and paste it into the sidebar. The key lives in the browser session only — never saved to disk,
  never logged. FIRMS points are shown on the map for cross-checking while ASMC data is available,
  and automatically become the count source (with a banner) if ASMC is fully down.
- **AI brief (optional)**: get a DeepSeek API key at
  [platform.deepseek.com](https://platform.deepseek.com/) and paste it into the sidebar (also
  session-only). The "AI brief" tab then generates a short operations briefing from the same
  snapshot the dashboard displays (PM2.5 / PSI / wind / rain / hotspots / 14-day history).
  Without a key the tab shows instructions and every other tab is unaffected. The output is
  double-guarded: the prompt forbids "stop all work" phrasing and a post-processing filter
  (`sanitize_brief`) replaces any banned wording with MOM-compliant phrasing; the brief always
  ends with a "not official NEA/MOM guidance" disclaimer.
- **Language**: switch EN / 中文 in the sidebar.
- **Tests**: `.venv/bin/python -m pytest -q` (110 tests, including a full-app `streamlit.testing`
  smoke test).

## Data Sources

| Data | Source | Update cadence | Notes |
|---|---|---|---|
| 1-hr PM2.5 (5 regions) | NEA v2 realtime API `pm25` | hourly, republished ~every 15 min | immediate-action metric |
| 24-hr PSI / 24-hr PM2.5 (5 regions) | NEA v2 realtime API `psi` | same | keyed to MOM work guidance |
| Station weather (rain / temp / humidity / wind) | NEA v2 realtime API, 5 endpoints | 1–5 min | aggregated to the 5 regions; wind knots→km/h |
| Hotspots (Sumatra / Kalimantan / P. Malaysia) | ASMC `DailyJP1NOAA20.{region}.txt` | per NOAA-20 pass (~2×/day) | primary source, keyless |
| 7-day hotspot counts / alert level | ASMC AJAX / RSS | ~daily / realtime | yesterday-count comparison and alert display |
| FIRMS point-level hotspots | NASA FIRMS CSV | ~3 h near-realtime | optional enrichment (needs key) |
| History backfill (14 days of hourly PM2.5) | NEA v2 realtime API `pm25?date=` | one-shot backfill when coverage is low (6-h cache) | powers the History analysis tab; written to the same SQLite table with UPSERT dedupe |

**Station → region mapping**: no official mapping exists, so this project uses a curated table
(19 stations, based on official coordinates and NEA town divisions; the 88 rainfall stations are
assigned to the nearest region anchor — an approximation, see `config.STATION_REGION` /
`REGION_ANCHORS`).

**ASMC multi-pass merge**: a `DailyJP1NOAA20` file may concatenate several VIIRS strips from the
same overpass, each with its own `***** Hotspot Count Report *****` header. The parser sums counts
per strip and dedupes by 3-decimal coordinates, so the count always equals the number of points.
Counts may therefore be slightly higher than the "main strip" count shown on the ASMC website
(e.g. 223 + 9 = 232).

## SQL (SQLite)

Runtime PM2.5 history is stored in `data/history.db` (SQLite via the Python standard library —
zero new dependencies). WAL journal mode + busy timeout allow concurrent browser sessions to
write; all writes are best-effort (they degrade silently if the filesystem is read-only, e.g. on
the cloud).

```sql
-- Schema (SCHEMA in src/data/db.py)
CREATE TABLE IF NOT EXISTS pm25_history (
    ts     TEXT    NOT NULL,   -- ISO 8601, +08:00 (lexicographic order == chronological order)
    region TEXT    NOT NULL,
    value  REAL    NOT NULL,
    PRIMARY KEY (ts, region)
);
CREATE INDEX IF NOT EXISTS idx_pm25_history_ts ON pm25_history (ts);

-- Write: last value wins on key conflict (dedupe at write time)
INSERT INTO pm25_history (ts, region, value) VALUES (?, ?, ?)
ON CONFLICT(ts, region) DO UPDATE SET value = excluded.value;

-- Read: window filter
SELECT ts, region, value FROM pm25_history
WHERE ts >= ? ORDER BY ts, region;

-- Aggregate: per-region stats (coverage check for the 14-day analysis tab)
SELECT region, COUNT(*) AS hours, AVG(value) AS mean, MAX(value) AS max,
       SUM(value > 55) AS hours_el, SUM(value > 150) AS hours_hi, SUM(value > 250) AS hours_vhi
FROM pm25_history WHERE ts >= ? GROUP BY region;
```

The legacy `data/history_pm25.csv` is migrated into SQLite once on first load and archived as
`.csv.legacy`. SQL handles storage, window filtering and GROUP BY aggregation; medians and OLS
trends remain in pandas (`src/risk/analysis.py`) — each doing what it is best at.

## Risk Model

All constants live in `config.py` and can be recalibrated there.

| Module | Rules |
|---|---|
| 1-hr PM2.5 bands | 0–55 → 1 Normal; 56–150 → 2 Elevated; 151–250 → 3 High; **≥251 → 4 Very High** (note the 251 boundary) |
| 24-hr PSI tiers | 0–50 → 1; 51–100 → 2; 101–200 → 3; 201–300 → 4; >300 → 5 |
| Trend | OLS slope over the last 3 hourly points (µg/m³/h); ≥+10 → +1.0, ≥+5 → +0.5, ≤−5 → −0.5, ≤−10 → −1.0 |
| Transport risk | Per hotspot: distance weight d<400 km → 1.0, d<700 → 0.6, else 0.3; wind-direction match with the bearing Singapore→hotspot within ±45° → 1.0, mismatch → 0.35, no wind → 0.5; today's count ≥ 2× yesterday's → ×1.2; levels 0 / <20 / <80 / <200 / ≥200. The "may arrive in 24–72 h" wording is an expert-judgment timescale for cross-boundary haze (`TRANSPORT_ARRIVAL_H`), not a live computed forecast |
| Regional risk score | `band + trend + transport add-on {0, 0.5, 1, 1.5, 1.5} − rain (≥1mm → 0.5) − wind (≥20 km/h → 0.5)`, clamped to [1, 4], cutoffs 1.5 / 2.5 / 3.5 |
| Work decisions | Immediate actions keyed to the 1-hr PM2.5 band (NEA health-advice wording); work planning keyed to the 24-hr PSI (MOM employer-measures wording); intensity matrix: ≤100 all allowed; 101–200 moderate/strenuous with caution; 201–300 strenuous restricted; >300 light with caution, moderate/strenuous restricted |
| Regional history analysis | Per region over the 14-day window: mean / median / peak, hours above 55 and share, OLS slope of daily means (µg/m³/day) + R²; trend hidden when fewer than 3 days of data |

> **Wording red line**: above PSI 300 the official MOM guidance is to *minimise outdoor work and
> postpone non-essential work* — never "stop all work". A unit test sweeps all PSI tiers and both
> languages and asserts the copy never contains "stop" / "停工".

## Project Structure

```
app.py                 # Streamlit entry (sidebar + auto-refresh fragment, 5 tabs)
config.py              # all constants: endpoints, TTLs, thresholds, station mapping, weights
src/data/              # fetch & assembly (fetcher / nea_* / hotspots / demo / history / db / ai_brief / pipeline)
src/risk/              # pure risk layer (bands / transport / engine / advisory / analysis)
src/i18n.py            # all EN / 中文 copy
src/ui/                # rendering only (theme / components / charts / map_view)
tests/                 # pytest (incl. AppTest full-app smoke test)
data/history.db        # SQLite runtime history (gitignored; recreated automatically)
```

Layering rules: `ui/` renders snapshots only; `risk/` depends only on `config` and `models`;
`data/` never imports `risk/` or Streamlit; `pipeline.py` is the single composition root
(imports both `data/` and `risk/`, holds all `st.cache_data`).

## Disclaimer

This tool is an **operations planning aid** for construction site teams, not a replacement for
official NEA / MOM advice. Always check [haze.gov.sg](https://www.haze.gov.sg),
[nea.gov.sg](https://www.nea.gov.sg) and [mom.gov.sg](https://www.mom.gov.sg). Transport risk is
an early-warning factor based on hotspots and wind fields, not a PM2.5 forecast. PSI is not
comparable to US AQI / IQAir scales and is never mixed with them in this tool.
