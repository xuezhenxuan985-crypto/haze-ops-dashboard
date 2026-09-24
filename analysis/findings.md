# Data Investigation — Haze Ops Dashboard

Brief findings from investigating the project's data (1-hr PM2.5, 24-hr PSI, weather,
ASMC hotspots, and the demo scenarios) with visualisations. Charts are in `analysis/charts/`,
raw data snapshots in `analysis/data/`, and the code that produces both in `analysis/scripts/`.

## Findings

### 1. The history CSV is 88% duplicate rows — and grows with every fetch (fig01)

`data/history_pm25.csv` held 200 rows for only **25 unique (timestamp, region) readings**.
Every call to `nea_pm25.fetch_pm25()` appends one row per region
([src/data/nea_pm25.py:35](../../src/data/nea_pm25.py#L35)), and every running session
refetches after the 5-minute TTL — so append volume in the snapshot window grew
**10 → 15 → 60 → 110 rows per hour** as more sessions were open. `load_pm25_history()`
deduplicates on read, but the file is written far more than it needs to be.

### 2. Only 4 hourly snapshots exist across 2 days, with a 3-hour gap (fig02)

`HISTORY_HOURS = 48` means old history self-deletes. The 24-h trend chart therefore depends
on someone having the app open: the snapshot contains four hourly points over two days and
nothing between 20:00 and 23:00 on 17 Sep (the app was closed). Any "trend over 24 h"
feature is actually operating on a handful of points.

### 3. Central spiked into Band 2 on the evening of 17 Sep; the worst region flips (fig02, fig03)

At 19:00 on 17 Sep, **central hit 101 µg/m³ — the only Band 2 reading on file** — then fell
to 30 by midnight. On the live morning of 24 Sep, central was the *lowest* region (13).
The worst-region ranking flips between days:

| Region  | 17 Sep 19:00 | 24 Sep 11:45 (live) |
|---------|-------------:|--------------------:|
| north   | 59           | 17                  |
| south   | 40           | 19                  |
| east    | 63           | 24                  |
| west    | 77           | 22                  |
| central | **101**      | **13**              |

Per-region advice is the whole point of the dashboard, so this volatility matters.

### 4. 1-hr PM2.5 and 24-hr PSI tell different stories (fig04)

On live data, 1-hr PM2.5 puts **every region in Band 1 (Normal ≤ 55)**, while 24-hr PSI puts
**every region in Tier 2 (Moderate 51–100)** — and they disagree on the worst region
(east 24 on PM2.5, west 82 on PSI). The risk score combines both, so a user can be told
"Normal" by one metric and "Moderate" by the other.

### 5. The demo scenarios never reach Band 4, and one scenario has a risk inversion (fig05, fig06)

- `haze_episode` peaks at **244.8 µg/m³ — 6.2 below the Band 4 threshold (≥ 251)**.
  Band-hours: clear_day is 100% Band 1, moderate_haze 100% Band 2, haze_episode 79.2% Band 3
  + 20.8% Band 2. The app's most severe state (Band 4, risk level 4) is never exercised.
- `moderate_haze`: central's 1-hr PM2.5 (111.9) exceeds north's (99.8), yet risk scores are
  **north 3.5 > central 3.0** — the 3-h trend term outweighs the PM2.5 band, an inversion a
  user would find hard to explain.

### 6. The 3-h trend slope assumes 1-hour spacing the data does not have (fig07)

`trend_slope()` in [src/risk/bands.py](../../src/risk/bands.py) fits the last 3 readings against
step indices 0, 1, 2, ignoring timestamps. On the real central series (19:00 = 101, 23:00 = 50,
00:00 = 30) the computed slope is **−35.5 µg/m³/h** versus the true −13.8 µg/m³/h — 2.6×
overstated. The trend term (−1.0) happens to match today; with sparse data a flipped term is
only a gap away.

### 7. The RSS banner can pair a stale alert with a fresh headline (components, fig08 data)

`hotspots.fetch_rss()` takes the highest "Alert Level N" from *any* RSS item and pairs it with
the *first* (latest) item's title, with no date check. Live, an **"Alert Level 3" from an
26 Aug item** was displayed beside the 17 Sep "Review of Regional Weather" headline, rendering
the critical banner in [src/ui/components.py:91](../../src/ui/components.py#L91). A 3-week-old
alert reads as current.

### 8. Transport risk: 796 fires in Kalimantan, but sumatra dominates the score (fig08)

The latest NOAA-20 pass (23 Sep 16:23) reported 796 Kalimantan hotspots vs 75 in Sumatra —
but the wind sector (S–SE/S–SW) puts Sumatra upwind of Singapore, so the transport engine
returns **level 3 (+1.5) with dominant source sumatra**. On this day that single adder lifts
all five regions from Band 1 to risk level 2: transport alone decides the advisory. Note the
hotspot data is ~20 hours old at fetch time.

## Data

Snapshots used by the charts (frozen copies in `analysis/data/`):

| File | Contents |
|------|----------|
| `history_pm25_raw.csv` | runtime history CSV as of 24 Sep (200 rows, 25 unique) |
| `live_pm25.csv`, `live_psi.csv`, `live_weather.csv` | live NEA readings, 24 Sep 11:45 |
| `live_hotspots.csv`, `live_hotspot_points.csv`, `live_transport.csv` | ASMC hotspots + transport engine output |
| `demo_pm25_24h.csv`, `demo_advisories.csv` | the 3 demo scenarios, full 24-h series + risk output |
