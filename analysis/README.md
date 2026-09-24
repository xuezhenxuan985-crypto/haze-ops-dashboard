# Data Investigation — Reproduction

Homework deliverable: investigate the Haze Ops Dashboard's project data with
visualisations, save the code, charts, and brief findings (see `findings.md`).

## Layout

```
analysis/
  scripts/
    fetch_snapshot.py   collect a reproducible data snapshot into analysis/data/
    make_charts.py      render fig01–fig08 PNGs into analysis/charts/
  data/                 frozen CSV snapshots the charts read from
  charts/               the 8 figure PNGs
  findings.md           the findings, with figure references
```

## Reproduce

From the repo root, with the project venv:

```sh
.venv/bin/python analysis/scripts/fetch_snapshot.py   # fetch live data + demo series
.venv/bin/python analysis/scripts/make_charts.py      # regenerate fig01–fig08
```

Notes:

- `fetch_snapshot.py` calls the app's own fetch functions. Because
  `nea_pm25.fetch_pm25()` **appends** to `data/history_pm25.csv` (that is how the app
  persists history), running the snapshot script appends 5 rows to the runtime file;
  the analysis freezes a copy (`analysis/data/history_pm25_raw.csv`) *before* fetching,
  so the charts are deterministic even if the runtime file changes.
- `make_charts.py` reads only `analysis/data/` — no network, no mutation of app data.
  Set `CHECK_LAYOUT=1` to run its programmatic text-collision check.

## Charts

| Figure | Question | Finding |
|--------|----------|---------|
| fig01 | How much of the history file is real data? | 88% duplicate rows; append volume ×11 in 6 h |
| fig02 | What does the real history timeline look like? | 4 snapshots in 2 days, central 101 spike, 3-h gap |
| fig03 | Is the worst region stable? | central highest (101) → lowest (13) across days |
| fig04 | Do the two headline metrics agree? | 1-h PM2.5: all Normal; 24-h PSI: all Moderate |
| fig05 | What do the demos actually exercise? | central always worst; Band 4 never reached |
| fig06 | Band-hours per demo scenario | episode = 79% Band 3, 0% Band 4 |
| fig07 | Is the 3-h trend slope time-aware? | step indexing overstates the slope 2.6× |
| fig08 | Do the fires explain the transport risk? | 796 Kalimantan fires, sumatra dominates upwind |
