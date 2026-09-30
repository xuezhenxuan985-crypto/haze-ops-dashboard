# Analysis — 90 天历史雾霾规律分析

用 **NEA 官方 90 天历史数据**（2026-07-03 – 2026-09-30，5 区域 × 每小时 PM2.5/PSI）
找有现实意义的规律：整体趋势、区域排行、日变化、事件集中度、PM2.5 与 PSI 的滞后关系。
结论见 **[findings.md](findings.md)**，图表在 `charts/`，全部可复现。

## 目录

```
analysis/
├── findings.md          # 规律 + 每条的"现实意义"（面向工地 Ops/EHS）
├── charts/              # fig01–fig08，findings.md 内引用
├── data/                # 冻结的 90 天历史（pm25_90d.csv / psi_90d.csv）
└── scripts/
    ├── fetch_history.py # 回填 90 天 NEA 数据 → data/（一次性，约 5 分钟）
    └── make_charts.py   # data/ → charts/ 全部 8 张图 + 关键数字打印
```

## 复现步骤

```bash
# 1) 回填 90 天历史（尊重 NEA 限流，约 180 个请求 / 5 分钟；单日失败自动跳过）
.venv/bin/python analysis/scripts/fetch_history.py

# 2) 从冻结数据生成全部图表 + 关键数字
.venv/bin/python analysis/scripts/make_charts.py
```

`fetch_history.py` 写 `analysis/data/` 的冻结 CSV，**不会**碰 dashboard 运行时使用的
`data/history_pm25.csv`。数据已在 2026-09-30 回填完毕，除非要延长窗口，否则只跑第 2 步。

## 每张图回答的问题

| 图 | 问题 | 结论（详见 findings.md） |
|---|---|---|
| fig01_island_trend | 90 天内整体在变好还是变差？ | 持续恶化，+0.36 µg/m³/天，R² 0.52（规律 1） |
| fig02_diurnal_pattern | 一天里什么时段最差？ | 15:00 峰值 / 07:00 谷值，形态稳定（规律 3） |
| fig03_region_ranking | 哪个区域最容易出问题？ | 中部最差（均值 34.7，11.5% 超标小时），北部最好（规律 2） |
| fig04_episode_days | 污染是均匀分布还是集中爆发？ | 脉冲式：9/14、9/29–30 两轮事件，9/29 当天 79% 区域小时超标（规律 4） |
| fig05_heatmap | 90 天 × 24 小时全貌 | 9 月下旬整体抬升 + 午后重于清晨（规律 1+3） |
| fig06_psi_lag | 1 小时 PM2.5 和 24 小时 PSI 谁先动？ | PM2.5 领先 PSI 约 11 小时（规律 5） |
| fig07_region_trends | 五区域的恶化速度一样吗？ | 中部恶化最快 +0.46/天，区域差距随时间放大（规律 6） |
| fig08_distribution | 各区域小时值分布 | 中部分布最右且拖尾最长（峰值 165）（规律 2） |

## 数据说明

- 来源：NEA data.gov.sg v2 realtime API 的 `pm25` / `psi` 端点 `?date=` 参数
  （已实测可回查 5 个月以上）。天气端点无历史，故本分析不含风/雨。
- 指标：1-hr PM2.5（即时性指标，键控现场行动）与 24-hr PSI（官方键控指标，键控工作规划）。
- "超标"指 1 小时 PM2.5 > 55 µg/m³（本项目波段 Elevated 起点，与 dashboard 一致）。
- 趋势 = 日均值 OLS 拟合斜率（µg/m³/天），R² 为拟合优度；滞后 = 去除日变化后的互相关峰值。

## 免责声明

本分析是运营规划辅助，不是 NEA / MOM 官方指示。官方信息以 [haze.gov.sg](https://www.haze.gov.sg) 为准。
