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

**站点→区域映射**：官方不存在，本项目使用自建策展表（19 站，基于官方坐标与 NEA 城镇分区）；
降雨 88 站按最近区域锚点自动归类（近似值，见 `config.STATION_REGION` / `REGION_ANCHORS` 注释）。

**ASMC 文件多过境合并**：`DailyJP1NOAA20` 文件可能拼接同一次过境的多个 VIIRS 条带（各自带
`***** Hotspot Count Report *****` 头与计数），解析器按段求和计数、按 3 位小数坐标去重，
保证"计数 == 点数"。因此本面板的 Sumatra 计数可能比 ASMC 官网显示的"主条带计数"多出
第二/第三条带的少数火点（例如 223 + 9 = 232）。

## 风险模型（全部常量在 `config.py`，可直接校准）

| 模块 | 规则 |
|---|---|
| 1-hr PM2.5 波段 | 0–55 → 1 Normal；56–150 → 2 Elevated；151–250 → 3 High；**≥251 → 4 Very High**（注意 251 边界） |
| 24-hr PSI 分级 | 0–50 → 1；51–100 → 2；101–200 → 3；201–300 → 4；>300 → 5 |
| 趋势 | 最近 3 个小时点 OLS 斜率（µg/m³/h）；≥+10 → +1.0，≥+5 → +0.5，≤−5 → −0.5，≤−10 → −1.0 |
| 传输风险 | 逐火点：距离权重 d<400 km → 1.0、d<700 → 0.6、其余 0.3；风向来向与"新加坡→火点"方位角差 ≤45° 扇区匹配 → 1.0，不匹配 0.35，无风 0.5；今日点数 ≥ 2× 昨日 → ×1.2；等级 0 / <20 / <80 / <200 / ≥200 |
| 区域风险分 | `band + 趋势项 + 传输等级加值{0,0.5,1,1.5,1.5} − 降雨(≥1mm→0.5) − 风速(≥20km/h→0.5)`，clamp[1,4]，分界 1.5/2.5/3.5 |
| 工作决策 | 即时行动键控 1-hr PM2.5 波段（NEA 健康建议措辞）；工作规划键控 24-hr PSI（MOM 雇主措施措辞）；工作强度矩阵：≤100 全允许；101–200 中度/高强度谨慎；201–300 高强度受限；>300 轻度谨慎、中度/高强度受限 |

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
src/data/              # 获取与组装（fetcher/nea_*/hotspots/demo/history/pipeline）
src/risk/              # 纯函数风险层（bands/transport/engine/advisory）
src/i18n.py            # EN/中文 全部文案
src/ui/                # 纯渲染层（theme/components/charts/map_view）
tests/                 # pytest（含 AppTest 全应用冒烟）
data/history_pm25.csv  # 运行时 1-hr PM2.5 历史（重启后 24h 图延续）
```

分层约束：`ui/` 只渲染 Snapshot；`risk/` 只依赖 `config` 与 `models`；`data/` 不依赖 `risk/` 与 Streamlit；
`pipeline.py` 是唯一的组合根（同时 import data/ 与 risk/，并持有全部 `st.cache_data`）。
