# Haze Ops — 新加坡区域雾霾风险与户外工作决策 Dashboard

面向新加坡建筑承包商的 Operations / EHS Manager：实时监测 1 小时 PM2.5 与 24 小时 PSI、
结合 ASMC 卫星火点与站点天气计算区域风险，并给出键控 MOM 指引的户外工作决策。

**运行方式**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

- **Live 模式**：直接使用 NEA data.gov.sg 实时 API（免 key）与 ASMC 火点数据（免 key），无需任何配置。
- **Demo 模式**：合成数据（晴天 / 中度雾霾 / 雾霾事件三场景），确定性种子，可用于演示与截图。
- **NASA FIRMS（可选富化）**：在 [firms.modaps.eosdis.nasa.gov/api/map_key/](https://firms.modaps.eosdis.nasa.gov/api/map_key/) 免费注册，
  将 key 粘贴到 sidebar（仅保存在浏览器会话中，不落盘、不入日志）。ASMC 数据正常时不参与计数，仅在地图上做逐点展示与交叉校验；
  ASMC 完全不可用时自动降级为计数来源并显示横幅。
- **AI 简报（可选）**：在 [console.anthropic.com](https://console.anthropic.com/) 获取 Anthropic API key 并粘贴到 sidebar
  （同样只存浏览器会话），即可在 "AI brief" 标签页一键生成当天的运营简报——由 Claude 阅读面板同一份数据（PM2.5/PSI/风/雨/火点/14 天历史）
  写成中/英文大白话。没有 key 时该页显示引导说明，其余标签页不受任何影响。模型输出带双保险：提示词禁止"全面停工"类措辞 +
  输出后自动替换（`sanitize_brief`），文案永远带"非官方 NEA/MOM 指示"免责声明。
- **语言**：sidebar 可切换 EN / 中文（数字保持西文，新加坡惯例）。
- 测试：`.venv/bin/python -m pytest -q`（含 `streamlit.testing` 全应用冒烟测试）。

## 数据源

| 数据 | 来源 | 更新频率 | 说明 |
|---|---|---|---|
| 1-hr PM2.5（5 区域） | NEA v2 realtime API `pm25` | 整点值，约 15 分钟重发 | 即时决策指标 |
| 24-hr PSI / 24-hr PM2.5（5 区域） | NEA v2 realtime API `psi` | 同上 | MOM 工作指引键控指标 |
| 站点天气（雨/温/湿度/风向/风速） | NEA v2 realtime API 5 端点 | 1–5 分钟 | 聚合到 5 区域；风速 knots→km/h |
| 火点（Sumatra / Kalimantan / P. Malaysia） | ASMC `DailyJP1NOAA20.{region}.txt` | 每次 NOAA-20 过境（约 2 次/天） | 主干，免 key |
| 7 日火点计数 / 警报 | ASMC AJAX / RSS | 约 1 天 / 实时 | 仅作昨日对比（该接口经常滞后/为零）与 Alert Level 展示 |
| FIRMS 逐点火点 | NASA FIRMS CSV | 约 3 小时近实时 | 可选富化（需 key） |
| 历史回填（过去 14 天每小时 PM2.5） | NEA v2 realtime API `pm25?date=` | 覆盖不足时一次性回填（6h 缓存） | 支撑"历史分析"页的区域排行与趋势；与实时采集写入同一张 SQLite 表，写入时按主键 (时间, 区域) UPSERT 去重。云端临时文件系统在重部署后会清空，自动重新回填 |

**站点→区域映射**：官方不存在，本项目使用自建策展表（19 站，基于官方坐标与 NEA 城镇分区）；
降雨 88 站按最近区域锚点自动归类（近似值，见 `config.STATION_REGION` / `REGION_ANCHORS` 注释）。

**ASMC 文件多过境合并**：`DailyJP1NOAA20` 文件可能拼接同一次过境的多个 VIIRS 条带（各自带
`***** Hotspot Count Report *****` 头与计数），解析器按段求和计数、按 3 位小数坐标去重，
保证"计数 == 点数"。因此本面板的 Sumatra 计数可能比 ASMC 官网显示的"主条带计数"多出
第二/第三条带的少数火点（例如 223 + 9 = 232）。

## SQL 使用（SQLite）

运行时 PM2.5 历史存储在 `data/history.db`（SQLite，Python 标准库 `sqlite3`，零新依赖）。
WAL 日志模式 + busy timeout 让多个浏览器会话可并发写入；所有写入都是尽力而为（云端只读文件系统时静默降级）。

```sql
-- 表结构（src/data/db.py 中的 SCHEMA）
CREATE TABLE IF NOT EXISTS pm25_history (
    ts     TEXT    NOT NULL,   -- ISO 8601, +08:00（字典序 == 时间序）
    region TEXT    NOT NULL,
    value  REAL    NOT NULL,
    PRIMARY KEY (ts, region)
);
CREATE INDEX IF NOT EXISTS idx_pm25_history_ts ON pm25_history (ts);

-- 写入：主键冲突时保留最后写入值（写入时去重，替代旧的读时去重）
INSERT INTO pm25_history (ts, region, value) VALUES (?, ?, ?)
ON CONFLICT(ts, region) DO UPDATE SET value = excluded.value;

-- 读取：窗口过滤（替代 pandas 裁剪）
SELECT ts, region, value FROM pm25_history
WHERE ts >= ? ORDER BY ts, region;

-- 聚合：区域统计（14 天分析页的覆盖检查）
SELECT region, COUNT(*) AS hours, AVG(value) AS mean, MAX(value) AS max,
       SUM(value > 55) AS hours_el, SUM(value > 150) AS hours_hi, SUM(value > 250) AS hours_vhi
FROM pm25_history WHERE ts >= ? GROUP BY region;
```

旧版 `data/history_pm25.csv` 会在首次加载时一次性迁移进 SQLite 并归档为 `.csv.legacy`。
SQL 负责存储、窗口过滤与 GROUP BY 聚合；中位数/OLS 趋势等统计仍在 pandas（`src/risk/analysis.py`）——
各用其所长。

## 风险模型（全部常量在 `config.py`，可直接校准）

| 模块 | 规则 |
|---|---|
| 1-hr PM2.5 波段 | 0–55 → 1 Normal；56–150 → 2 Elevated；151–250 → 3 High；**≥251 → 4 Very High**（注意 251 边界） |
| 24-hr PSI 分级 | 0–50 → 1；51–100 → 2；101–200 → 3；201–300 → 4；>300 → 5 |
| 趋势 | 最近 3 个小时点 OLS 斜率（µg/m³/h）；≥+10 → +1.0，≥+5 → +0.5，≤−5 → −0.5，≤−10 → −1.0 |
| 传输风险 | 逐火点：距离权重 d<400 km → 1.0、d<700 → 0.6、其余 0.3；风向来向与"新加坡→火点"方位角差 ≤45° 扇区匹配 → 1.0，不匹配 0.35，无风 0.5；今日点数 ≥ 2× 昨日 → ×1.2；等级 0 / <20 / <80 / <200 / ≥200。文案中"24–72 小时抵达"是经验时间尺度（`TRANSPORT_ARRIVAL_H`，跨海烟霾传输通常 1–3 天，与 NEA/ASMC 通告口径一致），**不是**用风速实时计算出的预报值 |
| 区域风险分 | `band + 趋势项 + 传输等级加值{0,0.5,1,1.5,1.5} − 降雨(≥1mm→0.5) − 风速(≥20km/h→0.5)`，clamp[1,4]，分界 1.5/2.5/3.5 |
| 工作决策 | 即时行动键控 1-hr PM2.5 波段（NEA 健康建议措辞）；工作规划键控 24-hr PSI（MOM 雇主措施措辞）；工作强度矩阵：≤100 全允许；101–200 中度/高强度谨慎；201–300 高强度受限；>300 轻度谨慎、中度/高强度受限 |
| 历史区域分析 | 每区域 14 天窗口统计：均值/中位/峰值、>55 小时数与占比、日均值 OLS 拟合斜率（µg/m³/天）+ R²；不足 3 天时趋势为空 |

> **措辞铁律**：PSI >300 的指引是"尽量减少户外作业并推迟非必要作业"，**绝不表述为全面停工**
> （MOM 官方表述，>400 才强调推迟非必要作业）。单元测试断言文案中不含 "stop work / 全面停止"。

## 免责声明

本工具是面向建筑工地团队的**运营规划辅助**，不是 NEA / MOM 官方建议或指示的替代品。
请以 [haze.gov.sg](https://www.haze.gov.sg)、[nea.gov.sg](https://www.nea.gov.sg)、
[mom.gov.sg](https://www.mom.gov.sg) 官方信息为准。传输风险是基于火点与风场的**预警因子**，
不是 PM2.5 预测。PSI 与 US AQI / IQAir 标度不可直接比较，本工具不做混排对比。

## 项目结构

```
app.py                 # Streamlit 入口（sidebar + @st.fragment(run_every=300)）
config.py              # 全部常量：端点、TTL、阈值、站点映射、权重
src/data/              # 获取与组装（fetcher/nea_*/hotspots/demo/history/db/pipeline）
src/risk/              # 纯函数风险层（bands/transport/engine/advisory/analysis）
src/i18n.py            # EN/中文 全部文案
src/ui/                # 纯渲染层（theme/components/charts/map_view）
tests/                 # pytest（含 AppTest 全应用冒烟）
data/history.db        # SQLite：运行时 1-hr PM2.5 历史（重启后 24h 图延续）
data/history_pm25.csv.legacy  # 迁移归档的旧 CSV（首次加载时生成）
```

分层约束：`ui/` 只渲染 Snapshot；`risk/` 只依赖 `config` 与 `models`；`data/` 不依赖 `risk/` 与 Streamlit；
`pipeline.py` 是唯一的组合根（同时 import data/ 与 risk/，并持有全部 `st.cache_data`）。
