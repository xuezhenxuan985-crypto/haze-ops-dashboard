"""Generate the analysis charts (fig01–fig08) into analysis/charts/.

Reproducible offline: reads only analysis/data/*.csv (see fetch_snapshot.py).
Run from the repo root:
    .venv/bin/python analysis/scripts/make_charts.py

Design follows the project dataviz method: light surface #fcfcfb, ink tokens,
hairline grids, thin marks, one axis per panel, fixed categorical hues per
region/source, status colors only for PM2.5 bands (always labelled).
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CHECK_LAYOUT = os.environ.get("CHECK_LAYOUT") == "1"

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "analysis" / "data"
OUT = ROOT / "analysis" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "figure.facecolor": "#fcfcfb",
    "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": "#c3c2b7",
    "axes.linewidth": 1.0,
    "axes.labelcolor": "#0b0b0b",
    "text.color": "#0b0b0b",
    "xtick.color": "#898781",
    "ytick.color": "#898781",
    "axes.grid": True,
    "grid.color": "#e1e0d9",
    "grid.linewidth": 1.0,
    "grid.alpha": 1.0,
    "axes.axisbelow": True,
    "savefig.facecolor": "#fcfcfb",
})

# Tokens.
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"
CONTEXT_GRAY = "#b9b7ae"

# Categorical slots, fixed per entity (never re-ordered between charts).
REGION_ORDER = ["north", "south", "east", "west", "central"]
REGION_COLORS = {
    "north": "#2a78d6",    # slot 1 blue
    "south": "#eb6834",    # slot 2 orange
    "east": "#1baf7a",     # slot 3 aqua
    "west": "#eda100",     # slot 4 yellow
    "central": "#e87ba4",  # slot 5 magenta
}
SOURCE_COLORS = {"kalimantan": "#2a78d6", "sumatra": "#eb6834", "p_malaysia": "#1baf7a"}

# PM2.5 bands (status, fixed — always shipped with labels).
BANDS = [(1, "Band 1 Normal", "#0ca30c"), (2, "Band 2 Elevated", "#fab219"),
         (3, "Band 3 High", "#ec835a"), (4, "Band 4 Very High", "#d03b3b")]
BAND_EDGES = [55, 150, 251]

DPI = 150


def band_of(v: float) -> int:
    if v <= 55:
        return 1
    if v <= 150:
        return 2
    if v <= 250:
        return 3
    return 4


def bare_ax(ax) -> None:
    """Hairline spines, y-only grid, recessive ticks."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.grid(axis="y", color=GRID, lw=1.0)
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)


def header(fig, title: str, subtitle: str, source: str) -> None:
    fig.suptitle(title, x=0.01, y=1.02, ha="left", fontsize=13, fontweight="bold")
    fig.text(0.01, 0.94, subtitle, ha="left", fontsize=9.5, color=INK2)
    fig.text(0.99, 0.005, f"source: {source}", ha="right", fontsize=7.5, color=MUTED)


def legend_out(ax, handles, labels, ncol=1, fontsize=8.5) -> None:
    ax.legend(handles, labels, frameon=False, fontsize=fontsize, ncol=ncol,
              loc="upper left", borderaxespad=0.5, handlelength=1.6, labelcolor=INK)


def bar_tip_labels(ax, bars, fmt="{:g}", dy=1, fontsize=8) -> None:
    top = ax.get_ylim()[1]
    for b in bars:
        h = b.get_height()
        if h > 0:
            ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, min(h + dy, top * 0.995)),
                        ha="center", va="bottom", fontsize=fontsize, color=INK)


def threshold_lines(ax, edges, xmax, labels, fontsize=7.5) -> None:
    for y, lab in zip(edges, labels):
        ax.axhline(y, color=BASE, lw=1.0, zorder=2)
        ax.text(xmax, y, f"  {lab}", ha="left", va="center", fontsize=fontsize, color=MUTED)


def save(fig, name: str) -> None:
    if CHECK_LAYOUT:
        check_layout(fig, name)
    fig.savefig(OUT / name, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / name)


def check_layout(fig, name: str) -> None:
    """Cheap programmatic eyeball: user-added texts that overlap or leave the canvas."""
    fig.canvas.draw()
    fig_texts = set(id(t) for t in fig.texts)
    texts = [a for a in fig.findobj(matplotlib.text.Text)
             if a.get_text().strip() and (a.axes is not None or id(a) in fig_texts)]
    # Annotation.get_window_extent() unions in the arrow patch; measure the text
    # alone (Text.get_window_extent) so leader lines don't count as text overlap.
    boxes = [(a, (matplotlib.text.Text.get_window_extent(a)
                  if isinstance(a, matplotlib.text.Annotation)
                  else a.get_window_extent()))
             for a in texts]
    issues = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, ba = boxes[i]
            b, bb = boxes[j]
            if ba.overlaps(bb):
                inter = (min(ba.x1, bb.x1) - max(ba.x0, bb.x0)) * (min(ba.y1, bb.y1) - max(ba.y0, bb.y0))
                small = min(ba.width * ba.height, bb.width * bb.height)
                if inter > 0.35 * small and a.get_text() != b.get_text():
                    print(f"  [LAYOUT] {name}: texts overlap: {a.get_text()!r} {ba} <-> {b.get_text()!r} {bb}")
                    issues += 1
    canvas = (fig.bbox.width, fig.bbox.height)
    for a, bb in boxes:
        if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > canvas[0] + 2 or bb.y1 > canvas[1] + 2:
            print(f"  [LAYOUT] {name}: text outside canvas: {a.get_text()!r} {bb}")
            issues += 1
    if not issues:
        print(f"  [LAYOUT] {name}: ok")


# ---------------------------------------------------------------------------
# fig01 — the history file is mostly duplicates
# ---------------------------------------------------------------------------
raw = pd.read_csv(DATA / "history_pm25_raw.csv", names=["ts", "region", "pm25"])
raw["ts"] = pd.to_datetime(raw["ts"], format="ISO8601", utc=True).dt.tz_convert("Asia/Singapore")
n_unique = raw.groupby("ts").size()
n_total = raw.groupby("ts").size()  # same grouping; computed per hour below
rows_per_ts = raw.groupby("ts").size()
labels = [t.strftime("%d %b, %H:%M") for t in rows_per_ts.index]

fig, ax = plt.subplots(figsize=(8.2, 4.4))
x = np.arange(len(rows_per_ts))
ax.bar(x, 5, width=0.55, color="#2a78d6", label="unique (timestamp, region) pairs")
ax.bar(x, rows_per_ts.values - 5, width=0.55, bottom=5, color="#eb6834",
       edgecolor=SURFACE, linewidth=2, label="duplicate rows")
for i, total in enumerate(rows_per_ts.values):
    ax.text(x[i], total + 3, f"{total} rows", ha="center", fontsize=8.5, color=INK)
    ax.text(x[i], 2.5, "5", ha="center", fontsize=7.5, color=SURFACE)
ax.set_xticks(x, labels)
ax.set_ylim(-36, 132)
ax.set_ylabel("rows appended to CSV per hour", fontsize=9)
ax.text(2, -28, "append volume ×11 in 6 hours — every 5-min TTL refetch per session appends again",
        ha="center", fontsize=8, color=INK2)
bare_ax(ax)
legend_out(ax, *ax.get_legend_handles_labels())
n_dup = len(raw) - raw.groupby(["ts", "region"]).ngroups
header(fig,
       f"The history CSV is {n_dup / len(raw) * 100:.0f}% duplicate rows",
       f"data/history_pm25.csv: {len(raw)} rows, {raw.groupby(['ts', 'region']).ngroups} unique readings — "
       "each fetch appends a fresh copy of every hourly value",
       "analysis/data/history_pm25_raw.csv")
save(fig, "fig01_history_duplication.png")

# ---------------------------------------------------------------------------
# fig02 — real Sep 17–18 timeline, central evening spike, data gap
# ---------------------------------------------------------------------------
window = raw[raw.ts < pd.Timestamp("2026-09-19", tz="Asia/Singapore")]
piv = window.pivot_table(index="ts", columns="region", values="pm25", aggfunc="last")
piv.index = piv.index.tz_localize(None)  # plot in SGT wall-clock (matplotlib would use UTC)
fig, ax = plt.subplots(figsize=(9.2, 4.6))
for region in REGION_ORDER:
    s = piv[region]
    ax.plot(s.index, s.values, lw=2, color=REGION_COLORS[region], label=region,
            marker="o", ms=5, mfc=REGION_COLORS[region], mec=SURFACE, mew=2, zorder=5)
gap_lo, gap_hi = pd.Timestamp("2026-09-17 20:00"), pd.Timestamp("2026-09-17 23:00")
ax.axvspan(gap_lo, gap_hi, color=GRID, zorder=0)
ax.text(gap_lo + (gap_hi - gap_lo) / 2, 108, "no data collected\n(app closed, 20:00–22:00)",
        ha="center", va="top", fontsize=8, color=INK2)
ax.axhspan(56, 110, color="#fab219", alpha=0.08, zorder=0)
ax.axhline(55, color=BASE, lw=1.0, zorder=2)
ax.text(piv.index[-1], 55, "  Band 1/2 boundary (55 µg/m³)", ha="left", va="center",
        fontsize=7.5, color=MUTED)
# End labels: direct where the line separates, leader lines for the converged
# cluster at the right edge (22/22/21/18 all end within 4 µg/m³ of each other).
end_vals = sorted(((piv[r].iloc[-1], r) for r in REGION_ORDER), reverse=True)
stacked, direct = [], []
prev = None
for v, r in end_vals:
    if prev is not None and prev - v <= 8:
        stacked.append((v, r))
    else:
        direct.append((v, r))
    prev = v
for v, r in direct:
    ax.text(piv.index[-1], v, f" {v:g}", ha="left", va="center", fontsize=8, color=INK)
y_fracs = np.linspace(0.035, 0.26, len(stacked))[::-1]
for (v, r), y_frac in zip(stacked, y_fracs):
    ax.annotate(f"{v:g}", xy=(piv.index[-1], v), xycoords="data",
                xytext=(1.012, y_frac), textcoords="axes fraction",
                ha="left", va="center", fontsize=8, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax.annotate("central 101 → the only Band 2 reading on file",
            xy=(pd.Timestamp("2026-09-17 19:00"), 101),
            xytext=(pd.Timestamp("2026-09-17 17:55"), 106.5),
            fontsize=8, color=INK2, arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax.set_ylim(0, 120)
ax.set_ylabel("1-hr PM2.5 (µg/m³)", fontsize=9)
ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M\n%d %b"))
bare_ax(ax)
ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.07),
          ncol=5, handlelength=1.4, labelcolor=INK)
header(fig,
       "Central spiked into Band 2 on the evening of 17 Sep; three hours went unrecorded",
       "Only 4 hourly snapshots exist across 2 days — the 24-h trend chart depends on someone running the app",
       "analysis/data/history_pm25_raw.csv")
save(fig, "fig02_history_timeline.png")

# ---------------------------------------------------------------------------
# fig03 — the worst region is not the same region
# ---------------------------------------------------------------------------
evening = piv.loc[pd.Timestamp("2026-09-17 19:00")]
live_pm = pd.read_csv(DATA / "live_pm25.csv").set_index("region")["pm25_1h"]

fig, ax = plt.subplots(figsize=(8.2, 4.6))
x = np.arange(2)
w = 0.14
for i, region in enumerate(REGION_ORDER):
    vals = [evening[region], live_pm[region]]
    bars = ax.bar(x + (i - 2) * (w + 0.02), vals, width=w, color=REGION_COLORS[region],
                  label=region)
    for b in bars:
        ax.annotate(f"{b.get_height():g}", (b.get_x() + b.get_width() / 2, b.get_height() + 2),
                    ha="center", fontsize=7.5, color=INK)
ax.axhline(55, color=BASE, lw=1.0)
ax.text(1.42, 55, " Band 1/2 boundary", ha="left", va="center", fontsize=7.5, color=MUTED)
ax.set_xticks(x, ["17 Sep, 19:00\n(hazy evening)", "24 Sep, 11:45\n(clear midday)"])
ax.set_xlim(-0.45, 1.55)
ax.set_ylim(0, 118)
ax.set_ylabel("1-hr PM2.5 (µg/m³)", fontsize=9)
bare_ax(ax)
ax.legend(frameon=False, fontsize=8.5, ncol=5, loc="upper right", bbox_to_anchor=(1.0, 1.02),
          handlelength=1.2, labelcolor=INK, columnspacing=0.9)
ax.annotate("central: highest (101) → lowest (13)\nranking flips between days",
            xy=(0.32, 101), xytext=(0.62, 92), fontsize=8, color=INK2,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
header(fig,
       "The worst region flips between days",
       "Per-region advice is the whole point of the dashboard — no region is consistently worst",
       "analysis/data/history_pm25_raw.csv · analysis/data/live_pm25.csv (24 Sep 2026)")
save(fig, "fig03_region_ranking.png")

# ---------------------------------------------------------------------------
# fig04 — 1-hr PM2.5 and 24-hr PSI tell different stories
# ---------------------------------------------------------------------------
live_psi = pd.read_csv(DATA / "live_psi.csv").set_index("region")

fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2))
panels = [
    (axes[0], live_pm, "1-hr PM2.5 (µg/m³)", "all Band 1 — Normal", "immediate-action metric", "east highest (24)"),
    (axes[1], live_psi["psi_24h"], "24-hr PSI", "all Tier 2 — Moderate", "work-planning metric", "west highest (82)"),
]
for ax, series, ylab, tag, role, note in panels:
    bars = ax.bar(REGION_ORDER, [series[r] for r in REGION_ORDER], width=0.55,
                  color=[REGION_COLORS[r] for r in REGION_ORDER])
    for b in bars:
        ax.annotate(f"{b.get_height():g}", (b.get_x() + b.get_width() / 2, b.get_height() + 1.2),
                    ha="center", fontsize=8, color=INK)
    ax.set_ylim(0, 95)
    ax.set_ylabel(ylab, fontsize=9)
    ax.set_title(f"{tag} — {note}\n({role})", fontsize=9, color=INK2, loc="center", pad=8)
    bare_ax(ax)
fig.subplots_adjust(top=0.75)  # keep the two-line panel titles clear of the subtitle
header(fig,
       "Two metrics, two different regional pictures (live, 24 Sep 11:45)",
       "1-hr PM2.5 says Normal everywhere while 24-hr PSI says Moderate — and they disagree on which region is worst",
       "analysis/data/live_pm25.csv · analysis/data/live_psi.csv")
save(fig, "fig04_metric_divergence.png")

# ---------------------------------------------------------------------------
# fig05 — demo scenarios: central dominates; peak at 15:00; Band 4 unreached
# ---------------------------------------------------------------------------
demo = pd.read_csv(DATA / "demo_pm25_24h.csv", parse_dates=["timestamp"])
demo["hour"] = demo["timestamp"].dt.hour
SCEN_TITLES = {
    "clear_day": "clear_day — all Band 1, peak 15:00 (synthetic diurnal sine)",
    "moderate_haze": "moderate_haze — all Band 2 for the full 24 h",
    "haze_episode": "haze_episode — central tops at 244.8; Band 4 (≥251) never reached",
}
fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.3), sharey=False)
for ax, (scen, sub) in zip(axes, SCEN_TITLES.items()):
    d = demo[demo.scenario == scen]
    for region in ["south", "east", "west"]:
        s = d[d.region == region].sort_values("hour")
        ax.plot(s.hour, s.pm25, lw=1.4, color=CONTEXT_GRAY, zorder=2)
    for region in ["north", "central"]:
        s = d[d.region == region].sort_values("hour")
        lw = 2.8 if region == "central" else 1.8
        ax.plot(s.hour, s.pm25, lw=lw, color=REGION_COLORS[region], zorder=4)
    end_central = d[(d.region == "central") & (d.hour == 11)].pm25.iloc[0]
    ax.plot(11, end_central, "o", ms=6, mfc=REGION_COLORS["central"], mec=SURFACE, mew=2, zorder=5)
    ax.text(11, end_central, f"  central {end_central:g}", ha="left", va="center",
            fontsize=8, color=INK)
    ymax = d.pm25.max()
    for edge, lab in zip([55, 150, 251], ["Band 1/2 · 55", "Band 2/3 · 150", "Band 3/4 · 251"]):
        if edge < ymax * 1.18:
            ax.axhline(edge, color=BASE, lw=1.0, zorder=2)
            ax.text(0.3, edge, f"{lab}", ha="left", va="center", fontsize=6.8, color=MUTED)
    ax.set_xlim(0, 24)
    ax.set_ylim(0, ymax * 1.18)
    ax.set_xticks([0, 6, 12, 15, 18, 23])
    ax.set_xlabel("hour of day (SGT)", fontsize=8)
    ax.set_title(sub, fontsize=8.6, color=INK2, pad=8)
    bare_ax(ax)
axes[0].set_ylabel("1-hr PM2.5 (µg/m³)", fontsize=9)
axes[0].annotate("sine peak 15:00 — real Singapore haze\npeaks are typically evening/morning",
                 xy=(15, 34.5), xytext=(14.9, 39.5), ha="center", fontsize=7.5, color=INK2,
                 arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
axes[1].annotate("central offset +18; north\n+4 — but risk score order\nstill differs (trend term)",
                 xy=(11, 111.9), xytext=(0.3, 74), fontsize=7.5, color=INK2,
                 arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
fig.legend(
    handles=[plt.Line2D([0], [0], color=REGION_COLORS["central"], lw=2.8),
             plt.Line2D([0], [0], color=REGION_COLORS["north"], lw=1.8),
             plt.Line2D([0], [0], color=CONTEXT_GRAY, lw=1.4)],
    labels=["central", "north", "south / east / west"],
    loc="upper right", bbox_to_anchor=(1.0, 0.995), frameon=False, fontsize=8.5,
    handlelength=1.6, labelcolor=INK, ncol=3, columnspacing=1.2)
header(fig,
       "Demo scenarios: central always worst, and the worst case never reaches Band 4",
       "Synthetic 24-h series (deterministic seeds). Central offset +8/+18/+38 µg/m³; band thresholds as lines",
       "analysis/data/demo_pm25_24h.csv")
save(fig, "fig05_demo_scenarios.png")

# ---------------------------------------------------------------------------
# fig06 — band-hours share per scenario (status colors, labelled)
# ---------------------------------------------------------------------------
rows = []
for scen, g in demo.groupby("scenario"):
    for band, _, _ in BANDS:
        n = sum(band_of(v) == band for v in g.pm25)
        rows.append({"scenario": scen, "band": band, "hours": n})
share = pd.DataFrame(rows).pivot(index="scenario", columns="band", values="hours")
share = share.div(share.sum(axis=1), axis=0) * 100

fig, ax = plt.subplots(figsize=(8.2, 3.9))
scen_order = list(SCEN_TITLES)
y = np.arange(len(scen_order))[::-1]
left = np.zeros(len(scen_order))
for band, name, color in BANDS:
    vals = [share.loc[s, band] if band in share.columns else 0 for s in scen_order]
    bars = ax.barh(y, vals, left=left, height=0.5, color=color, edgecolor=SURFACE,
                   linewidth=2, label=name)
    for i, (b, v) in enumerate(zip(bars, vals)):
        if v > 0:
            # Ink or surface text by fill luminance (white on green/red, ink on
            # yellow/serious where white would be <3:1).
            txt_color = SURFACE if band in (1, 4) else INK
            if v >= 9:
                ax.text(left[i] + v / 2, y[i], f"{v:.0f}%", ha="center", va="center",
                        fontsize=8, color=txt_color, fontweight="bold")
            else:
                ax.text(left[i] + v + 1.2, y[i], f"{v:.0f}%", ha="left", va="center",
                        fontsize=8, color=INK)
    left += vals
ax.set_yticks(y, scen_order)
ax.set_xlim(0, 112)
ax.set_xticks([0, 25, 50, 75, 100], ["0", "25%", "50%", "75%", "100%"])
ax.set_xlabel("share of 120 region-hours per scenario", fontsize=9)
bare_ax(ax)
ax.legend(frameon=False, fontsize=8.5, loc="lower right", labelcolor=INK, handlelength=1.4)
ax.annotate("no Band 4 (≥251) in any demo scenario —\nthe app's most severe state is never exercised",
            xy=(102, 2.2), xytext=(66, 1.62), fontsize=8, color=INK2,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
header(fig,
       "Band coverage of the demo scenarios",
       "3 scenarios × 5 regions × 24 h = 120 region-hours each; status colors follow the NEA band scale",
       "analysis/data/demo_pm25_24h.csv")
save(fig, "fig06_demo_band_hours.png")

# ---------------------------------------------------------------------------
# fig07 — 3-h trend slope: step index vs real hour spacing
# ---------------------------------------------------------------------------
# The last 3 central readings the engine would actually see (all within the
# 48-h prune window): 19:00, 23:00, 00:00 — with a real 4-hour gap inside.
central = raw[raw.region == "central"].drop_duplicates(subset=["ts"], keep="last").sort_values("ts")
last3 = central.iloc[-4:-1]  # 19:00, 23:00, 00:00 — the last 3 pre-overnight points
y = last3.pm25.values
gaps = ((last3.ts - last3.ts.iloc[0]).dt.total_seconds() / 3600).values
step = np.arange(3)
step_slope = np.polyfit(step, y, 1)[0]
hour_slope = np.polyfit(gaps, y, 1)[0]


def trend_term(slope: float) -> float:
    if slope >= 10:
        return 1.0
    if slope >= 5:
        return 0.5
    if slope <= -10:
        return -1.0
    if slope <= -5:
        return -0.5
    return 0.0


fig, ax = plt.subplots(figsize=(8.2, 4.5))
ax.plot(step, y, "o", ms=7, mfc=REGION_COLORS["central"], mec=SURFACE, mew=2, zorder=5)
ax.plot(step, y, lw=1.5, color=REGION_COLORS["central"], alpha=0.5, zorder=3)
for i, (s, v) in enumerate(zip(step, y)):
    dy = 6 if v > 55 else -7  # label above the point, except under the Band line
    ax.text(s, v + dy, f"{v:g}", ha="center", va="bottom" if dy > 0 else "top",
            fontsize=8, color=INK)
    gap_lab = f"Δt {gaps[i]:g} h" if gaps[i] > 0 else "start of window"
    ax.text(s, 8, gap_lab, ha="center", fontsize=7.5, color=MUTED)
ax.set_xticks(step, [t.strftime("%H:%M") for t in last3.ts])
ax.set_xlim(-0.45, 2.45)
ax.set_ylim(0, 125)
ax.set_ylabel("central 1-hr PM2.5 (µg/m³)", fontsize=9)
ax.axhline(55, color=BASE, lw=1.0)
ax.text(2.45, 55, " Band 1/2", ha="right", va="center", fontsize=7.5, color=MUTED)
bare_ax(ax)
ax.annotate(
    f"engine: slope over steps 0,1,2 = {step_slope:.1f} µg/m³/h → trend term {trend_term(step_slope):+.1f}\n"
    f"reality: slope over 0 h, {gaps[1]:g} h, {gaps[2]:g} h = {hour_slope:.1f} µg/m³/h → trend term {trend_term(hour_slope):+.1f}\n"
    "same term today, 2.6× overstated — larger gaps can flip the term (see findings)",
    xy=(1, 53), xytext=(0.55, 103), fontsize=8.5, color=INK2,
    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
header(fig,
       "The 3-h trend slope assumes 1-hour spacing the data does not have",
       "trend_slope() indexes the last 3 readings 0,1,2 — the real 4-hour gap is counted as one hour (2.6× overstated)",
       "analysis/data/history_pm25_raw.csv · src/risk/bands.py")
save(fig, "fig07_trend_spacing.png")

# ---------------------------------------------------------------------------
# fig08 — transport risk: 796 Kalimantan fires, sumatra dominates upwind
# ---------------------------------------------------------------------------
hs = pd.read_csv(DATA / "live_hotspots.csv").set_index("source")
pts = pd.read_csv(DATA / "live_hotspot_points.csv")

fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), gridspec_kw={"width_ratios": [1, 1.35]})

ax = axes[0]
sources = ["kalimantan", "sumatra", "p_malaysia"]
bars = ax.bar(sources, [hs.loc[s, "count"] for s in sources], width=0.5,
              color=[SOURCE_COLORS[s] for s in sources])
for b in bars:
    ax.annotate(f"{b.get_height():g}", (b.get_x() + b.get_width() / 2, b.get_height() + 18),
                ha="center", fontsize=8, color=INK)
ax.set_ylim(0, 880)
ax.set_ylabel("hotspots in latest NOAA-20 pass (23 Sep 16:23)", fontsize=8.5)
ax.text(2, 28, "0", ha="center", fontsize=8, color=INK)
bare_ax(ax)
ax.annotate("transport engine: level 3 (+1.5 risk score)\nupwind points 71 · dominant source: sumatra",
            xy=(1, 55), xytext=(0.95, 560), fontsize=8.5, color=INK2,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))

ax = axes[1]
for source in ["kalimantan", "sumatra"]:
    p = pts[pts.source == source]
    ax.scatter(p.lon, p.lat, s=3, alpha=0.45, color=SOURCE_COLORS[source], label=source,
               linewidths=0)
ax.plot(103.82, 1.35, "o", ms=8, mfc=INK, mec=SURFACE, mew=2, zorder=6)
ax.text(103.82, 0.0, "Singapore", ha="center", va="center", fontsize=8.5, color=INK)
for bearing, lab in [(154, "wind from S–SE"), (223, "wind from S–SW")]:
    rad = np.radians(bearing)
    ax.annotate("", xy=(103.82 + 7.2 * np.sin(rad), 1.35 + 7.2 * np.cos(rad)),
                xytext=(103.82, 1.35),
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.2))
    ax.text(103.82 + 7.9 * np.sin(rad), 1.35 + 7.9 * np.cos(rad), lab,
            fontsize=7.2, color=MUTED, ha="center")
ax.set_xlabel("longitude", fontsize=8.5)
ax.set_ylabel("latitude", fontsize=8.5)
ax.legend(frameon=False, fontsize=8.5, loc="lower left", labelcolor=INK,
          markerscale=4, handlelength=0.8)
bare_ax(ax)

header(fig,
       "796 fires in Kalimantan — but the engine's upwind story is sumatra",
       "Live, 24 Sep: transport risk level 3 adds +1.5 to every region's score, lifting all five from Band 1 to risk level 2",
       "analysis/data/live_hotspots.csv · live_hotspot_points.csv · live_transport.csv")
save(fig, "fig08_transport_dominance.png")

print("\nkey numbers:")
print("  raw rows:", len(raw), "| unique pairs:", raw.groupby(["ts", "region"]).ngroups)
print("  step slope:", round(step_slope, 2), "| hour slope:", round(hour_slope, 2))
print("  band-hours:", share.to_dict())
