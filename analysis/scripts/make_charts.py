"""Generate the history-pattern charts (fig01–fig08) into analysis/charts/.

Reproducible offline: reads only analysis/data/pm25_90d.csv and
analysis/data/psi_90d.csv (see fetch_history.py). Run from the repo root:
    .venv/bin/python analysis/scripts/make_charts.py

Design follows the project dataviz method: light surface #fcfcfb, ink
tokens, hairline grids, fixed categorical hues per region, status colors
only for PM2.5 bands (always labelled). Chart text is Chinese (macOS CJK
font when available) so the findings read naturally for the user.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
from matplotlib import font_manager
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

CHECK_LAYOUT = os.environ.get("CHECK_LAYOUT") == "1"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.risk.analysis import ols_fit  # noqa: E402

DATA = ROOT / "analysis" / "data"
OUT = ROOT / "analysis" / "charts"
OUT.mkdir(parents=True, exist_ok=True)


def _cjk_font() -> str:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("PingFang SC", "Hiragino Sans GB", "STHeiti", "Arial Unicode MS"):
        if name in installed:
            return name
    return "DejaVu Sans"


matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [_cjk_font(), "DejaVu Sans"],
    "axes.unicode_minus": False,
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

# Categorical slots, fixed per region (never re-ordered between charts).
REGION_ORDER = ["north", "south", "east", "west", "central"]
REGION_COLORS = {
    "north": "#2a78d6",
    "south": "#eb6834",
    "east": "#1baf7a",
    "west": "#eda100",
    "central": "#e87ba4",
}
REGION_ZH = {"north": "北部", "south": "南部", "east": "东部", "west": "西部", "central": "中部"}

# PM2.5 bands (status colors, always shipped with labels).
BANDS = [(1, "Band 1 正常 ≤55", "#0ca30c"), (2, "Band 2 偏高 56–150", "#fab219"),
         (3, "Band 3 高 151–250", "#ec835a"), (4, "Band 4 非常高 ≥251", "#d03b3b")]
BAND_EDGES = [55, 150, 251]

HAZE_CMAP = LinearSegmentedColormap.from_list(
    "haze", ["#f6efe0", "#f4d178", "#ec835a", "#d03b3b"])

DPI = 150


def band_of(v: float) -> int:
    if v <= 55:
        return 1
    if v <= 150:
        return 2
    if v <= 250:
        return 3
    return 4


BAND_COLORS = {b: c for b, _, c in BANDS}


def bare_ax(ax) -> None:
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


def legend_out(ax, ncol=1, fontsize=8.5, loc="upper left", **kw) -> None:
    ax.legend(frameon=False, fontsize=fontsize, ncol=ncol, loc=loc,
              borderaxespad=0.5, handlelength=1.6, labelcolor=INK, **kw)


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
                    print(f"  [LAYOUT] {name}: texts overlap: {a.get_text()!r} <-> {b.get_text()!r}")
                    issues += 1
    canvas = (fig.bbox.width, fig.bbox.height)
    for a, bb in boxes:
        if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > canvas[0] + 2 or bb.y1 > canvas[1] + 2:
            print(f"  [LAYOUT] {name}: text outside canvas: {a.get_text()!r}")
            issues += 1
    if not issues:
        print(f"  [LAYOUT] {name}: ok")


# ---------------------------------------------------------------------------
# Data (frozen CSVs from fetch_history.py; wall-clock index for plotting)
# ---------------------------------------------------------------------------
def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / name)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Singapore")
    return df.set_index("timestamp")


pm = load("pm25_90d.csv")
psi = load("psi_90d.csv")
island = pm.mean(axis=1)          # island-average hourly PM2.5
island_psi = psi.mean(axis=1)     # island-average hourly PSI
daily = island.resample("D").mean().dropna()
daily.index = daily.index.tz_localize(None)
region_daily = pm.resample("D").mean().dropna(how="all")
region_daily.index = region_daily.index.tz_localize(None)

WINDOW = f"{daily.index[0]:%Y-%m-%d} – {daily.index[-1]:%Y-%m-%d}"


def _ols(series: pd.Series) -> tuple[float, float, float]:
    return ols_fit([float(i) for i in range(len(series))], [float(v) for v in series.values])


# ---------------------------------------------------------------------------
# fig01 — island daily mean + 90-day OLS trend
# ---------------------------------------------------------------------------
slope, intercept, r2 = _ols(daily)
word = "恶化" if slope > 0 else "改善"
fig, ax = plt.subplots(figsize=(9.6, 4.8))
ax.plot(daily.index, daily.values, "o", ms=3.5, mfc=CONTEXT_GRAY, mec="none",
        zorder=3, label="全岛日均 1 小时 PM2.5")
ax.plot(daily.index, daily.values, lw=1.0, color=CONTEXT_GRAY, zorder=2)
roll = daily.rolling(7, center=True).mean()
ax.plot(roll.index, roll.values, lw=2.6, color=INK, zorder=4, label="7 天滚动均值")
xs = np.arange(len(daily))
ax.plot(daily.index, intercept + slope * xs, lw=1.8, ls="--", color="#2a78d6",
        zorder=5, label="OLS 趋势线")
ymax = max(daily.max(), 60) * 1.28
ax.set_ylim(0, ymax)
ax.axhline(55, color=BASE, lw=1.0, zorder=2)
ax.text(daily.index[-1], 55, " Band 1/2 分界（55 µg/m³）", ha="right", va="bottom",
        fontsize=7.5, color=MUTED)
ax.annotate(f"整体趋势 {slope:+.2f} µg/m³/天 · R² {r2:.2f}\n90 天内在持续{word}",
            xy=(daily.index[int(len(daily) * 0.62)], intercept + slope * int(len(daily) * 0.62)),
            xytext=(daily.index[int(len(daily) * 0.05)], ymax * 0.80),
            fontsize=9.5, color=INK, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1))
ax.set_ylabel("1 小时 PM2.5（µg/m³）", fontsize=9)
ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
bare_ax(ax)
legend_out(ax, ncol=3)
header(fig, f"全岛空气整体在{word}——90 天日均趋势",
       f"{WINDOW} · 日均值（灰点）+ 7 天滚动（粗线）+ 最小二乘趋势线（虚线）",
       "analysis/data/pm25_90d.csv")
save(fig, "fig01_island_trend.png")

# ---------------------------------------------------------------------------
# fig02 — diurnal pattern: best / worst time of day
# ---------------------------------------------------------------------------
by_hour_region = pm.groupby(pm.index.hour).mean()
by_hour_island = by_hour_region.mean(axis=1)
fig, ax = plt.subplots(figsize=(9.6, 4.8))
for region in REGION_ORDER:
    ax.plot(by_hour_region.index, by_hour_region[region], lw=1.4,
            color=REGION_COLORS[region], alpha=0.7, label=REGION_ZH[region])
ax.plot(by_hour_island.index, by_hour_island.values, lw=3.0, color=INK,
        zorder=6, label="全岛平均")
peak_h = int(by_hour_island.idxmax())
valley_h = int(by_hour_island.idxmin())
ax.axhline(55, color=BASE, lw=1.0, zorder=2)
ax.text(23, 55, " Band 1/2 分界", ha="right", va="bottom", fontsize=7.5, color=MUTED)
ax.annotate(f"最差时段 {peak_h}:00 前后\n（平均 {by_hour_island[peak_h]:.0f} µg/m³）",
            xy=(peak_h, by_hour_island[peak_h]), xytext=(peak_h - 9.5, by_hour_island[peak_h] + 3.5),
            fontsize=8.5, color=INK2, arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax.annotate(f"最好时段 {valley_h}:00 前后\n（平均 {by_hour_island[valley_h]:.0f} µg/m³）",
            xy=(valley_h, by_hour_island[valley_h]), xytext=(valley_h + 0.8, by_hour_island[valley_h] + 9),
            fontsize=8.5, color=INK2, arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax.set_xlim(0, 23)
ax.set_ylim(0, by_hour_island.max() * 1.32)
ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 23])
ax.set_xlabel("时刻（新加坡时间）", fontsize=9)
ax.set_ylabel("1 小时 PM2.5（µg/m³）", fontsize=9)
bare_ax(ax)
legend_out(ax, ncol=6, loc="upper center", bbox_to_anchor=(0.5, 1.14))
fig.subplots_adjust(top=0.80)
header(fig, "一天之中，空气最好和最差的时段是固定的",
       "90 天按小时平均——各区域（彩色细线）与全岛平均（黑色粗线）的日变化规律",
       "analysis/data/pm25_90d.csv")
save(fig, "fig02_diurnal_pattern.png")

# ---------------------------------------------------------------------------
# fig03 — regional ranking: 90-day mean + share of hours above 55
# ---------------------------------------------------------------------------
mean_by_region = pm.mean()
pct_by_region = (pm > 55).mean() * 100
order = list(mean_by_region.sort_values(ascending=False).index)


def pct_color(p: float) -> str:
    if p <= 10:
        return BAND_COLORS[1]
    if p <= 30:
        return BAND_COLORS[2]
    if p <= 50:
        return BAND_COLORS[3]
    return BAND_COLORS[4]


fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.4))
y = np.arange(len(order))[::-1]

ax = axes[0]
bars = ax.barh(y, [mean_by_region[r] for r in order], height=0.55,
               color=[BAND_COLORS[band_of(mean_by_region[r])] for r in order])
for b in bars:
    ax.annotate(f"{b.get_width():.1f}", (b.get_width() + 1.2, b.get_y() + b.get_height() / 2),
                va="center", fontsize=8.5, color=INK)
ax.axvline(55, color=BASE, lw=1.0)
ax.text(55, len(order) - 0.15, " 55（Band 1/2 分界）", ha="left", va="top", fontsize=7.5, color=MUTED)
ax.set_yticks(y, [REGION_ZH[r] for r in order])
ax.set_xlim(0, max(mean_by_region.max() * 1.22, 70))
ax.set_title("90 天平均 1 小时 PM2.5\n（柱色 = 平均所处的 NEA 波段）", fontsize=9, color=INK2, pad=10)
ax.set_xlabel("µg/m³", fontsize=8.5)
bare_ax(ax)

ax = axes[1]
bars = ax.barh(y, [pct_by_region[r] for r in order], height=0.55,
               color=[pct_color(pct_by_region[r]) for r in order])
for b in bars:
    ax.annotate(f"{b.get_width():.0f}%", (b.get_width() + 1.2, b.get_y() + b.get_height() / 2),
                va="center", fontsize=8.5, color=INK)
ax.set_yticks(y, [REGION_ZH[r] for r in order])
ax.set_xlim(0, 100)
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_title("超标（>55 µg/m³）时间占比\n（柱色 = 占比严重程度）", fontsize=9, color=INK2, pad=10)
ax.set_xlabel("%", fontsize=8.5)
bare_ax(ax)

header(fig, "哪个区域长期最容易出问题——中部、北部最严重",
       "90 天全部小时值：平均浓度与超标时间占比的排序一致，结论互相印证",
       "analysis/data/pm25_90d.csv")
save(fig, "fig03_region_ranking.png")

# ---------------------------------------------------------------------------
# fig04 — episode days: band-hours per day (120 region-hours/day)
# ---------------------------------------------------------------------------
band_df = pm.map(band_of)
flat = band_df.stack().rename("band").reset_index()
flat["timestamp"] = flat["timestamp"].dt.normalize()
daily_band = flat.groupby(["timestamp", "band"]).size().unstack(fill_value=0)
daily_band = daily_band.reindex(columns=[1, 2, 3, 4], fill_value=0)
daily_band.index = daily_band.index.tz_localize(None)
share = daily_band.div(daily_band.sum(axis=1), axis=0) * 100
elevated = share[[2, 3, 4]].sum(axis=1)

fig, ax = plt.subplots(figsize=(10.4, 4.8))
left = np.zeros(len(share))
for band, name, color in BANDS:
    vals = share[band].values
    ax.bar(share.index, vals, bottom=left, width=0.9, color=color,
           edgecolor=SURFACE, linewidth=1.5, label=name)
    left += vals
worst_day = elevated.idxmax()
for d in share.index[elevated > 20]:
    ax.annotate(f"{d:%m-%d}\n{elevated[d]:.0f}% 超标", xy=(d, 103),
                xytext=(d, 116), ha="center", fontsize=7.8, color=INK2,
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.8))
ax.set_ylim(0, 128)
ax.set_yticks([0, 25, 50, 75, 100], ["0", "25%", "50%", "75%", "100%"])
ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax.set_ylabel("120 个区域小时的波段占比\n（5 区域 × 24 小时/天）", fontsize=9)
bare_ax(ax)
legend_out(ax, ncol=4)
header(fig, f"污染集中在少数几天——最严重的是 {worst_day:%m-%d}（{elevated[worst_day]:.0f}% 区域小时超标）",
       "每天 120 个区域小时按 NEA 波段的占比；标注的是超标占比 >20% 的日子",
       "analysis/data/pm25_90d.csv")
save(fig, "fig04_episode_days.png")

# ---------------------------------------------------------------------------
# fig05 — heatmap: hour × day, island-average PM2.5
# ---------------------------------------------------------------------------
hm = pd.DataFrame({"hour": island.index.hour, "date": island.index.normalize(), "v": island.values})
hm = hm.pivot_table(index="hour", columns="date", values="v", aggfunc="mean")
hm.index = hm.index.astype(int)
fig, ax = plt.subplots(figsize=(10.4, 5.0))
dates = list(hm.columns)
im = ax.pcolormesh(np.arange(len(dates) + 1), np.arange(25) - 0.5, hm.values,
                   cmap=HAZE_CMAP, vmin=0, vmax=max(60.0, float(hm.max().max()) * 0.75))
cb = fig.colorbar(im, ax=ax, pad=0.015)
cb.set_label("全岛平均 1 小时 PM2.5（µg/m³）", fontsize=8.5)
cb.outline.set_color(BASE)
cb.ax.tick_params(length=0, colors=MUTED, labelsize=8)
ax.set_yticks([0, 6, 12, 18, 23])
ax.set_ylabel("时刻（新加坡时间）", fontsize=9)
step = 7
ax.set_xticks(np.arange(0, len(dates), step), [d.strftime("%m-%d") for d in dates[::step]])
ax.set_xlim(0, len(dates))
ax.set_ylim(-0.5, 23.5)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.tick_params(length=0)
header(fig, f"污染在一天里如何演变——午后（{peak_h}:00 前后）最重，清晨最轻",
       "行 = 时刻（0–23 点），列 = 日期；颜色 = 全岛平均 1 小时 PM2.5",
       "analysis/data/pm25_90d.csv")
save(fig, "fig05_heatmap.png")

# ---------------------------------------------------------------------------
# fig06 — instant metric vs planning metric: PSI lags PM2.5
# ---------------------------------------------------------------------------
# Cross-correlation on the full series, diurnal removed, to measure the lag.
pm_resid = island - island.groupby(island.index.hour).transform("mean")
psi_resid = island_psi - island_psi.groupby(island_psi.index.hour).transform("mean")
corr = np.correlate(pm_resid.values, psi_resid.values, mode="full")
# np.correlate peak at k<0 means psi(t) ~ pm(t-|k|): PSI trails PM2.5 by |k|.
psi_lag = -int(corr.argmax() - (len(pm_resid) - 1))

center = island.resample("D").mean().idxmax()  # tz-aware
lo, hi = center - pd.Timedelta(days=3), center + pd.Timedelta(days=1)
pm_w = island[(island.index >= lo) & (island.index <= hi)]
pm_w.index = pm_w.index.tz_localize(None)
psi_w = island_psi[(island_psi.index >= lo) & (island_psi.index <= hi)]
psi_w.index = psi_w.index.tz_localize(None)

fig, ax1 = plt.subplots(figsize=(9.6, 4.6))
ax1.plot(pm_w.index, pm_w.values, lw=2.2, color=INK, zorder=5, label="1 小时 PM2.5（即时指标）")
ax1.axhline(55, color=BASE, lw=1.0, zorder=2)
ax1.text(pm_w.index[0], 55, " Band 1/2 分界", ha="left", va="bottom", fontsize=7.5, color=MUTED)
ax1.set_ylim(0, pm_w.max() * 1.32)
ax1.set_ylabel("1 小时 PM2.5（µg/m³）", fontsize=9)
ax2 = ax1.twinx()
ax2.plot(psi_w.index, psi_w.values, lw=2.2, color="#2a78d6", zorder=4,
         label="24 小时 PSI（规划指标）")
ax2.set_ylim(0, psi_w.max() * 1.5)
ax2.set_ylabel("24 小时 PSI", fontsize=9, color="#2a78d6")
ax2.tick_params(axis="y", colors="#2a78d6", length=0)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_color("#2a78d6")
ax2.grid(visible=False)
pm_peak_t = pm_w.idxmax()
psi_peak_t = psi_w.idxmax()
ax1.annotate("PM2.5 先冲顶\n（即时指标先报警）", xy=(pm_peak_t, pm_w.max()),
             xytext=(pm_peak_t - pd.Timedelta(hours=30), pm_w.max() * 1.02),
             fontsize=8.5, color=INK2, arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax1.annotate(f"PSI 随后才到峰值\n（整体滞后约 {psi_lag} 小时）", xy=(psi_peak_t, psi_w.max()),
             xytext=(psi_peak_t + pd.Timedelta(hours=6), psi_w.max() * 0.72),
             fontsize=8.5, color="#2a78d6", arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
ax1.xaxis.set_major_locator(mdates.HourLocator(interval=12))
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
bare_ax(ax1)
handles = [plt.Line2D([0], [0], color=INK, lw=2.2),
           plt.Line2D([0], [0], color="#2a78d6", lw=2.2)]
ax1.legend(handles, ["1 小时 PM2.5（即时指标）", "24 小时 PSI（规划指标）"],
           frameon=False, fontsize=8.5, loc="upper left", labelcolor=INK, handlelength=1.6)
header(fig, f"PSI 是 24 小时滚动平均——它比 PM2.5 晚约 {psi_lag} 小时反应",
       f"最严重的 4 天（{lo:%m-%d} – {hi:%m-%d}）：现场变化先看 1 小时 PM2.5，工作安排看 24 小时 PSI",
       "analysis/data/pm25_90d.csv · analysis/data/psi_90d.csv")
save(fig, "fig06_psi_lag.png")

# ---------------------------------------------------------------------------
# fig07 — per-region daily trends: who is worsening fastest
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(1, 5, figsize=(13.8, 4.0), sharey=True)
for ax, region in zip(axes, REGION_ORDER):
    d = region_daily[region].dropna()
    slope_r, intercept_r, r2_r = _ols(d)
    xs = np.arange(len(d))
    ax.plot(xs, d.values, "o", ms=2.5, mfc=CONTEXT_GRAY, mec="none", zorder=3)
    ax.plot(xs, d.values, lw=0.8, color=CONTEXT_GRAY, zorder=2)
    ax.plot(xs, intercept_r + slope_r * xs, lw=2.0, ls="--",
            color=REGION_COLORS[region], zorder=5)
    ax.axhline(55, color=BASE, lw=0.9, zorder=2)
    ax.text(0.04, 0.88, f"{slope_r:+.2f} µg/m³/天\nR² {r2_r:.2f}",
            transform=ax.transAxes, fontsize=8.5, color=INK, fontweight="bold")
    ax.set_title(f"{REGION_ZH[region]}", fontsize=10.5)
    ax.set_xticks([0, len(d) // 2, len(d) - 1],
                  [d.index[0].strftime("%m-%d"), d.index[len(d) // 2].strftime("%m-%d"),
                   d.index[-1].strftime("%m-%d")])
    bare_ax(ax)
axes[0].set_ylabel("日均 1 小时 PM2.5（µg/m³）", fontsize=9)
axes[0].set_ylim(0, region_daily.max().max() * 1.28)
header(fig, "哪个区域恶化最快——斜率最大的是中部与北部",
       "各区域日均值（灰点）+ 最小二乘趋势线（彩色虚线）；斜率 = 每区域每天的变化量",
       "analysis/data/pm25_90d.csv")
save(fig, "fig07_region_trends.png")

# ---------------------------------------------------------------------------
# fig08 — distribution: mean vs spikes (tail risk)
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.4, 4.8))
data = [pm[r].dropna().values for r in REGION_ORDER]
bp = ax.boxplot(data, tick_labels=[REGION_ZH[r] for r in REGION_ORDER],
                patch_artist=True, widths=0.5, medianprops=dict(color=INK, lw=2.2),
                flierprops=dict(marker=".", ms=2.2, mfc=CONTEXT_GRAY, mec="none", alpha=0.5))
for patch, region in zip(bp["boxes"], REGION_ORDER):
    patch.set_facecolor(REGION_COLORS[region])
    patch.set_alpha(0.55)
means = [pm[r].mean() for r in REGION_ORDER]
ax.scatter(np.arange(1, 6), means, marker="x", s=55, color=INK, zorder=6, label="90 天均值")
for edge, lab in zip(BAND_EDGES, ["Band 1/2 · 55", "Band 2/3 · 150", "Band 3/4 · 251"]):
    ax.axhline(edge, color=BASE, lw=1.0, zorder=2)
    ax.text(5.42, edge, f" {lab}", ha="left", va="center", fontsize=7.2, color=MUTED)
ax.set_ylim(0, 320)
ax.set_ylabel("1 小时 PM2.5（µg/m³）", fontsize=9)
ax.set_xlabel("区域（箱线 = 90 天全部小时值；× = 均值）", fontsize=9)
bare_ax(ax)
legend_out(ax, ncol=1)
header(fig, "平均值之外的尖峰风险——中部不仅平均高，尖峰也最高",
       "箱体 = 中间 50% 的小时值；须线 = 常见波动范围；灰点 = 异常高的小时值",
       "analysis/data/pm25_90d.csv")
save(fig, "fig08_distribution.png")

# ---------------------------------------------------------------------------
# Key numbers for findings.md
# ---------------------------------------------------------------------------
print("\nkey numbers:")
print(f"  island: slope {slope:+.2f} µg/m³/day, R² {r2:.2f}, window {WINDOW}")
for r in sorted(REGION_ORDER, key=lambda r: -mean_by_region[r]):
    sr, _, rr = _ols(region_daily[r].dropna())
    print(f"  {r:8s} mean {mean_by_region[r]:5.1f} · >55 {pct_by_region[r]:4.1f}% · "
          f"slope {sr:+.2f}/day · R² {rr:.2f}")
print(f"  diurnal: peak {peak_h}:00 ({by_hour_island[peak_h]:.1f}), valley {valley_h}:00 "
      f"({by_hour_island[valley_h]:.1f})")
print(f"  worst day: {worst_day:%Y-%m-%d} ({elevated[worst_day]:.0f}% region-hours >55)")
print(f"  top-3 episode days: " + ", ".join(
    f"{d:%m-%d}={elevated[d]:.0f}%" for d in elevated.sort_values(ascending=False).index[:3]))
print(f"  PSI lags PM2.5 by ~{psi_lag} h (diurnal-removed cross-correlation)")
print(f"  spike: {region_daily.max().max():.1f} peak daily mean; "
      f"central max hourly = {pm['central'].max():.1f}")
