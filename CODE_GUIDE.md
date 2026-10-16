# 代码导读 — 5 分钟看懂这个项目

> 演示/答辩前复习用。看完这篇，老师问任何关于代码的问题，你都能答上"是什么 + 在哪"。

## 0. 一句话版本（先背这句）

**Haze Ops 是一个给新加坡建筑工地经理用的雾霾风险看板**：从新加坡官方环境局（NEA）和东盟气象中心（ASMC）的免费接口抓实时数据 → 按官方标准（MOM 工作指引）算出每个区域的风险等级 → 用中英双语给出"今天户外工作怎么办"的建议。**数据、计算、界面三层完全分开，110 项测试兜底，其中一条自动化测试保证"PSI>300 时绝不写'停工'"（MOM 官方措辞是"尽量减少户外作业"）。**

## 1. 数据怎么流动（最重要的一张图）

```
NEA 官方接口(免key)          ASMC 卫星火点(免key)        可选: NASA FIRMS / Claude AI
 PM2.5 · PSI · 天气           火点计数 · 警报                (key 填在侧边栏)
        │                          │                              │
        ▼                          ▼                              ▼
   src/data/ 抓取+解析  ──►  src/data/pipeline.py 总装 ──►  一份完整"快照" Snapshot
（限速6次/10秒、重试、超时）   （管缓存、出错降级）              │
                                                    ┌─────────────┴─────────────┐
                                                    ▼                           ▼
                                         src/risk/ 纯函数算风险          src/ui/ 渲染成网页
                                         波段·趋势·传输·决策            卡片·图表·地图·AI简报
                                                                                    │
                                                                                    ▼
                                                                              app.py 入口
                                                                        （侧边栏 + 每5分钟自动刷新）
```

**记住三个词**：
- **抓（data）**：把网上的原始数据拿回来、洗干净
- **算（risk）**：纯数学函数，同样输入永远同样输出，可以离线测试
- **画（ui）**：把结果变成网页

演示模式（demo）不走网络，由 `demo_data.py` 直接"造"数据——所以断网也能演示。

## 2. 每个文件一句话

### 根目录（就 5 个代码文件 + 3 篇文档）

| 文件 | 一句话 |
|---|---|
| [app.py](app.py) | 网页入口：侧边栏（语言/模式/key）、5 个标签页、每 5 分钟自动刷新 |
| [config.py](config.py) | **所有"数字和开关"的集中地**：接口网址、PM2.5/PSI 阈值、权重、缓存时长、AI 模型名 |
| [conftest.py](conftest.py) | 测试公用道具：假网络（FakeSession，测试时不真上网） |
| [requirements.txt](requirements.txt) | 需要安装的第三方库清单 |
| [README.md](README.md) | 项目说明书：运行方式、数据源、风险模型表、SQL 用法 |
| [CODE_GUIDE.md](CODE_GUIDE.md) | 就是本文：代码导读 |
| [PIPELINE_REVIEW.md](PIPELINE_REVIEW.md) | 课程作业：管道工程的 5 个问题（模块怎么分、测试日志、风险） |
| [AI_FEATURE.md](AI_FEATURE.md) | 课程作业：AI 功能的 5 个问题（目的/集成/输入/输出/可靠性） |

### src/data/ — 抓数据（第 1 层）

| 文件 | 一句话 |
|---|---|
| [fetcher.py](src/data/fetcher.py) | 统一 HTTP 客户端：**限速 6 次/10 秒**（NEA 官方配额）、失败重试、超时 |
| [nea_pm25.py](src/data/nea_pm25.py) | 从 NEA 抓 1 小时 PM2.5（实时 + 按天回填 14 天历史） |
| [nea_psi.py](src/data/nea_psi.py) | 从 NEA 抓 24 小时 PSI |
| [nea_weather.py](src/data/nea_weather.py) | 从 NEA 抓 5 种天气（雨/温/湿度/风向/风速） |
| [hotspots.py](src/data/hotspots.py) | ASMC 卫星火点（多段文件合并去重）+ 可选 NASA FIRMS 富化 |
| [db.py](src/data/db.py) | **SQLite 数据库读写**：UPSERT 写时去重、时间窗口查询、GROUP BY 统计 |
| [history.py](src/data/history.py) | 历史数据管家：写入 SQLite、读窗口、旧 CSV 一次性迁移进数据库 |
| [demo_data.py](src/data/demo_data.py) | 演示模式的合成数据（三场景、固定随机种子、离线可跑） |
| [models.py](src/data/models.py) | 数据"集装箱"（dataclass）：Snapshot 快照、RegionPM25 区域读数等 |
| [pipeline.py](src/data/pipeline.py) | **总装车间**：把各数据源组装成 Snapshot；管全部缓存；单源失败降级不崩页 |
| [ai_brief.py](src/data/ai_brief.py) | AI 简报：拼提示词（只喂面板数据）、调 Claude API、输出"防停工"护栏 |

### src/risk/ — 算风险（第 2 层，纯函数，不联网）

| 文件 | 一句话 |
|---|---|
| [bands.py](src/risk/bands.py) | 官方分级：PM2.5 波段、PSI 档位、3 小时趋势斜率（**OLS 线性回归**） |
| [transport.py](src/risk/transport.py) | 传输风险：每个火点 × 距离权重 × 风向扇区匹配（±45°） |
| [engine.py](src/risk/engine.py) | 区域风险总分：波段 + 趋势 + 传输 − 降雨/大风，压到 1–4 级 |
| [advisory.py](src/risk/advisory.py) | 把分数"翻译"成工作建议（MOM 官方措辞）和工作强度矩阵 |
| [analysis.py](src/risk/analysis.py) | 14 天历史统计：均值/峰值/超标占比/日均趋势（OLS+R²） |

### src/ui/ — 画界面（第 3 层）

| 文件 | 一句话 |
|---|---|
| [components.py](src/ui/components.py) | 页面组件：数据卡片、警示横幅、工作决策表、AI 简报页 |
| [charts.py](src/ui/charts.py) | Plotly 图表（24 小时曲线、历史分析图） |
| [map_view.py](src/ui/map_view.py) | 火点地图（folium） |
| [theme.py](src/ui/theme.py) | 颜色样式（绿/黄/橙/红对应严重度） |

### tests/ — 110 项测试（每个源文件都有对应用测试）

### analysis/ — 90 天历史数据研究（独立小项目）

| 文件 | 一句话 |
|---|---|
| [analysis/findings.md](analysis/findings.md) | 发现报告：6 条有现实意义的规律（如"午后最重、清晨最轻"） |
| [analysis/scripts/](analysis/scripts/) | 两个可复现脚本：fetch_history.py（回填 90 天数据）、make_charts.py（生成 8 张图） |
| [analysis/data/](analysis/data/) | 冻结的 90 天 CSV（重跑脚本可复现全部结果） |

## 3. 老师可能问的问题（照着答）

| 老师问 | 口语化回答 | 代码在哪 |
|---|---|---|
| 项目解决什么问题？ | 工地经理不能只靠感觉安排户外工作。这个看板把官方数据变成 1–4 级风险和一句话行动建议 | 全部 |
| 数据从哪来？要钱吗？ | NEA 官方开放接口（免 key、匿名限速）+ ASMC 卫星火点（免 key）；NASA FIRMS 和 Claude AI 是可选增强，key 由用户自己申请 | [config.py](config.py) 端点段 |
| 为什么分这么多文件夹？ | 抓数据/算风险/画界面三层分开，`pipeline.py` 是唯一"总装"点——好处：改一个数据源不会弄坏计算逻辑，风险层纯函数可以离线测 | [PIPELINE_REVIEW.md](PIPELINE_REVIEW.md) 问题 1、2 |
| 某个数据源挂了，页面会崩吗？ | 不会。每个源独立 try/except，失败就用上次成功的数据（last-good），并在页面顶部亮黄色横幅；**横幅会写明失败原因** | [pipeline.py](src/data/pipeline.py) 的 `_load_*` |
| SQL 用在哪？为什么用？ | 每小时 PM2.5 存 SQLite（`data/history.db`）。写入用 UPSERT（主键冲突就覆盖，天然去重）；读 14 天窗口用 WHERE；区域统计用 GROUP BY。不用 CSV 是因为并发写入会互相覆盖 | [db.py](src/data/db.py) + README"SQL 使用"节 |
| 风险等级怎么算的？ | 三加两减：PM2.5 波段 + 3 小时趋势 + 传输风险等级，减去降雨（≥1mm）和大风（≥20km/h）的缓解，结果压在 1–4 级 | [engine.py](src/risk/engine.py) + README 风险模型表 |
| 趋势怎么算？ | **OLS 线性回归**：对最近 3 个小时点拟合直线，斜率就是趋势（>+10 算明显上升）。14 天分析用日均值拟合，还给出 R² | [bands.py](src/risk/bands.py) `trend_slope`、[analysis.py](src/risk/analysis.py) `ols_fit` |
| "24–72 小时到达"怎么算的？ | **274 个上游火点是算的**（距离权重 × 风向扇区）；**24–72 小时不是算的**，是写进 config 的经验常数（跨海烟霾通常 1–3 天，NEA/ASMC 通告同口径），文案用"可能"并注明"预警因子，不是预报" | [transport.py](src/risk/transport.py) + [config.py](config.py) `TRANSPORT_ARRIVAL_H` |
| 为什么 PSI>300 绝不写"停工"？ | MOM 官方指引是"尽量减少户外作业并推迟非必要作业"，写"停工"会误导工地方。一条测试遍历全部档位×两种语言断言文案不含 stop/停工，谁改错谁红灯 | [tests/test_advisory.py](tests/test_advisory.py) `test_tier4_never_says_stop` |
| AI 简报怎么保证不乱说？ | 三道保险：①提示词硬规则（只准用给的数据、禁止编造、禁止"停工"措辞）②输出后再过滤一遍（sanitize_brief 自动替换违禁词）③结尾强制一行免责声明。失败只影响 AI 标签页 | [ai_brief.py](src/data/ai_brief.py) + [tests/test_ai_brief.py](tests/test_ai_brief.py) |
| API key 怎么防止泄露？ | key 只存在浏览器会话（session_state），不落盘、不进日志；缓存键用 key 的 SHA-256 哈希而不是 key 本身 | [pipeline.py](src/data/pipeline.py) `fetch_ai_brief` |
| 有多少测试？ | 110 项，约 23 秒跑完，一条命令：`.venv/bin/python -m pytest -q`。含一个"整页冒烟测试"（模拟用户渲染全页面） | [tests/](tests/) |
| 怎么更新线上版本？ | 本地改完 → push 到 GitHub main 分支 → Streamlit Cloud 自动重新部署，1–2 分钟生效 | — |
| 90 天历史数据哪来的？ | 用 NEA 接口的 `?date=` 参数按天回填后**冻结成 CSV** 存在 analysis/data，两个脚本可一键复现全部图表 | [analysis/README.md](analysis/README.md) |
| 演示模式有什么用？ | 合成数据、固定种子，断网也能演示和截图；三场景（晴天/中度/雾霾事件） | [demo_data.py](src/data/demo_data.py) |
| 中英文怎么做到不缺字？ | 两套字典放 [i18n.py](src/i18n.py)，测试自动断言 EN 和中文的键**完全相等**、每个模板都能正常填参数 | [tests/test_i18n.py](tests/test_i18n.py) |

## 4. 关键词速查（答不上来先查这里）

| 词 | 大白话 |
|---|---|
| PSI / PM2.5 | 新加坡官方两种雾霾指标：PSI 是 24 小时滚动综合值（工作规划用），PM2.5 是 1 小时细颗粒物（即时行动用） |
| 波段 / tier | 官方把数值分档（如 PM2.5 0–55 正常、56–150 偏高……），决策只认档位 |
| 上游火点 | 处在"风吹向新加坡"扇区里的火点——风向是从哪吹来，不是往哪吹去 |
| OLS | 最小二乘线性回归：给一串点画"最贴"的直线，斜率=趋势 |
| dataclass | 数据集装箱：一个对象装一组相关字段，层与层之间传它 |
| 缓存 / TTL | 结果存一段时间不重算（如 PM2.5 存 15 分钟），省请求、页面快 |
| UPSERT | 数据库写法：有这条记录就更新，没有就插入——写入时自动去重 |
| last-good | "上次成功的结果"：数据源挂了就用它顶着，同时亮横幅告诉用户 |
| 限速器 | NEA 匿名接口只允许 6 次/10 秒，所有请求排队遵守，否则会被封 IP |
| sanitize（护栏） | AI 输出后再过滤一遍：发现"停工"类违禁词就自动替换成 MOM 官方措辞 |
| 冒烟测试 | 模拟用户完整打开页面渲染一遍，保证"能开机" |

## 5. 遇到"XX 数据延迟"横幅怎么办（运维小抄）

1. 看横幅下方新加的"原因（Cause）"一行——现在会写明具体错误（如 `403 Forbidden` / `Connection timed out`）。
2. `403/429`：NEA 临时限流或封了云端 IP → 一般等 10–30 分钟自愈，点"Refresh now"重试。
3. `Connection …`：网络抖动 → 同上。
4. 持续超过 1 天 → 把横幅文字截图发给我（或查 Streamlit Cloud 控制台的 Logs）。
5. 这期间其他标签页照常工作；真的没数据时页面会明确说"数据不可用"而不是静默空着。
