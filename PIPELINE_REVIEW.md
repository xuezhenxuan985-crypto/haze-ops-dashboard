# 管道工程实践简报 — Haze Ops Dashboard

# Pipeline Engineering Review — Haze Ops Dashboard

面向团队展示：管道如何组织与模块化、加了哪些测试与日志、这些变化如何让流程更可靠。
For the team presentation: how the pipeline is organized and modularized, what tests and logging were added, and how these changes made it more reliable.

---

## 1. 如何组织与模块化管道 / How the pipeline is organized and modularized

### 四层单向依赖 + 唯一组合根 / Four one-way layers + a single composition root

```
app.py ──────── Streamlit 入口（sidebar、自动刷新 fragment）
                Streamlit entry point (sidebar, auto-refresh fragment)
   │
src/ui/ ─────── 纯渲染层：theme / components / charts / map_view（只读 Snapshot，零网络、零计算）
                Pure rendering: reads Snapshot only — no network, no logic
   ▲
src/risk/ ───── 纯函数风险层：bands / transport / engine / advisory / analysis（只依赖 config + models）
                Pure-function risk layer (depends only on config + models)
   ▲
src/data/ ───── 数据层：fetcher / nea_pm25 / hotspots / weather / history / demo（只做获取与组装）
                Data layer: fetching and assembly only
   ▲
config.py ───── 全部常量：端点、TTL、阈值、站点映射、权重（一处改，全局生效）
                All constants: endpoints, TTLs, thresholds, station mapping, weights
```

**三条硬规则（靠目录边界强制执行）/ Three hard rules (enforced by directory boundaries)**:

1. `src/risk/` 不 import 任何网络/Streamlit 模块——风险计算是纯函数，输入相同输出必相同。
   `src/risk/` imports no network/Streamlit code — risk math is pure: same inputs, same outputs.
2. `src/data/` 不 import `risk/` 和 Streamlit——数据层不知道"被谁消费"。
   `src/data/` imports neither `risk/` nor Streamlit — the data layer doesn't know its consumers.
3. `src/pipeline.py` 是**唯一组合根**：data 层取数 → `Snapshot` dataclass 组装 → risk 层计算 → ui 层渲染，
   并持有全部 `@st.cache_data` 缓存。任何模块之间没有第二条通路。
   `src/pipeline.py` is the **only composition root**: fetch → assemble `Snapshot` → compute risk → render,
   and it owns all `@st.cache_data` caches. No module talks to any other behind its back.

### 数据流 = 一条流水线，接口是 dataclass / One pipeline; the interface is a dataclass

```
NEA 5 endpoints + ASMC + FIRMS  ──(rate limit / retry / cache)──▶  Snapshot  ──▶  risk  ──▶  ui
```

- `models.py` 定义 `Snapshot`、`RegionAnalysis` 等 dataclass——层与层之间**只传数据，不传对象引用**，
  任何一层都可以单独替换/测试（例如 demo 模式直接构造 `Snapshot`，绕开全部网络）。
  `models.py` defines dataclasses (`Snapshot`, `RegionAnalysis`, …) — layers exchange plain data, never live objects,
  so any layer can be swapped or tested in isolation (demo mode builds a `Snapshot` directly, bypassing all network).
- 所有可调参数（PM2.5 波段边界、传输风险距离权重、缓存 TTL、站点→区域映射）集中在 `config.py`。
  Every tunable (band thresholds, transport-risk weights, cache TTLs, station→region map) lives in `config.py`.
- **双模式**：Live（真实 NEA/ASMC 数据）与 Demo（确定性种子合成数据）走同一条管道——
  演示、截图、测试复用同一条路径，不是两套代码。
  **Dual mode**: Live (real NEA/ASMC data) and Demo (deterministic seeded synthetic data) share the same pipeline —
  demos, screenshots and tests exercise the same code path, not a second one.

---

## 2. 测试与日志 / Tests and logging

### 测试：87 项，全绿，22.8 秒跑完 / Tests: 87 passing in 22.8 s (`pytest -q`)

| 文件 File | 覆盖 Covers | 为什么重要 Why it matters |
|---|---|---|
| `test_bands.py` / `test_transport.py` / `test_engine.py` / `test_advisory.py` | 风险层全部纯函数 / all risk-layer pure functions | 核心决策逻辑可离线验证 / core decision logic verified offline |
| `test_parsers.py` | ASMC/NEA 各端点解析（含多过境合并、去重）/ all endpoint parsers | 上游格式变了能第一时间发现 / catches upstream format changes |
| `test_analysis.py` | OLS 拟合、区域分析、14 天回填 / OLS, regional analysis, backfill | 新功能全量覆盖 / new features fully covered |
| `test_history.py` | 历史 CSV 追加/裁剪/去重 / CSV append, windowing, dedupe | 持久化正确性 / persistence correctness |
| `test_i18n.py` | EN/中文键集相等 + 全部模板可格式化 / equal key sets + all templates formattable | 双语切换不会崩 / language switch can't break |
| `test_app_smoke.py` | **Streamlit `AppTest` 全应用冒烟**（整页渲染 + 双语切换）/ full-app smoke via Streamlit `AppTest` | 端到端回归，不用开浏览器 / end-to-end regression, no browser needed |

**两个具体例子 / Two concrete examples**:

① **把合规红线变成测试 / Turning a compliance red-line into a test** (`test_advisory.py`)：
MOM 官方对 PSI >300 的表述是"尽量减少户外作业"，**绝不**是"全面停工"。测试断言所有 PSI >300 建议文案
不出现 `"stop work" / "全面停止"`——措辞一旦踩线，测试立即变红，合规风险被自动化管住。
MOM's official wording above PSI 300 is "minimise outdoor work", never "stop all work". A test asserts that
no PSI>300 advisory ever contains "stop work / 全面停止" — one wording slip and the test goes red;
the compliance risk is automated.

② **把容错变成测试 / Turning fault-tolerance into a test** (`test_analysis.py`)：
回填对单日失败必须"跳过该天、继续下一天、绝不抛异常"。测试用 FakeSession 构造"第 2 天返回 404"的场景，
断言行数正确、无异常、其余天数数据完整——网络故障路径和正常路径一样可回归。
The 14-day backfill must skip a failed day and continue, never raise. A test fakes "day 2 returns 404"
and asserts the remaining days are intact with no exception — the failure path regresses like the happy path.

### 日志：每个数据模块自带 `logging.getLogger(__name__)` / Logging: every data module has its own logger

日志只记录**可恢复的异常**，不记录敏感数据 / Logs record recoverable failures only, never sensitive data:

```python
# fetcher.py — every retry is traceable (attempt number + reason)
log.warning("GET %s attempt %d failed: %s", url, attempt + 1, exc)
log.warning("GET %s rate-limited (429); waiting %.1fs", url, delay)

# nea_pm25.py — backfill reports per-day; silent failures are eliminated
log.warning("pm25 backfill %s: empty payload", date_str)

# pipeline.py — each upstream source fails independently; one down ≠ app down
log.warning("pm25 fetch failed: %s", exc)
```

配合 Streamlit 界面的**降级横幅**（如"火点数据部分可用"）：出问题时，日志定位到具体源、界面明示到用户，两层都透明。
Together with on-screen **degradation banners** ("hotspot data partially available"): logs pinpoint the source,
the UI tells the user — both layers stay transparent.

---

## 3. 可靠性与编码风险 / Reliability and the coding risks reduced

| 编码风险 Coding risk | 我们的措施 Our mitigation |
|---|---|
| 上游 API 限流封禁 / upstream API ban | 全局共享 `RateLimiter`（6 次/10s），所有请求统一排队 / one shared `RateLimiter` (6 calls / 10 s) for all requests |
| 瞬时网络抖动导致整页崩溃 / a blip crashes the whole page | fetcher 内置重试 + 退避；各数据源独立 try/except，单源失败走降级 / retry + backoff; each source fails independently into a degraded state |
| 重复拉取 / 启动慢 / refetching; slow startup | `@st.cache_data` 按 TTL 缓存（实时 5 分钟、回填 6 小时）/ TTL-based caching (5 min live, 6 h backfill) |
| 历史数据重复写入 / duplicate history rows | 读取时按 (时间, 区域) 去重；回填与实时采集写同一 CSV 天然幂等 / dedupe on (time, region); backfill + live append are idempotent |
| 分析脚本污染运行时数据 / analysis polluting runtime data | 回填写 `analysis/data/` 冻结 CSV，**永远不碰**运行时 CSV / frozen CSVs under `analysis/data/`, runtime CSV untouched |
| 逻辑错误混进展示层 / logic bugs hiding in the UI | 风险计算是纯函数层，87 项单测离线全覆盖 / risk logic is a pure layer with 87 offline unit tests |
| 合规措辞 / 单位混用 / wrong wording or unit mixing | 铁律写成测试：>300 无"停工"表述、PSI 绝不与 US AQI 混排 / red-lines as tests: no "stop work" wording, PSI never mixed with US AQI |
| 敏感信息泄露 / leaking secrets | FIRMS key 只存浏览器 session_state，**不落盘、不入日志** / FIRMS key lives in session_state only — never on disk, never logged |
| 全应用回归没人跑 / no full-app regression | AppTest 冒烟测试每次提交都跑 / AppTest smoke runs on every suite run |
| 中文文案半缺失 / half-missing Chinese copy | i18n 测试断言 EN/中文键集完全相等 + 模板全部可格式化 / i18n tests assert equal key sets and formattable templates |

**一句话总结 / One-line summary**：把"容易出错的地方"从人的纪律改成了**结构**（分层 + 纯函数 + 单一组合根）
和**自动化**（87 项测试 + 逐源日志 + 降级横幅）——管道不再依赖"记得检查"，而是"错不了，或错了立刻知道错在哪"。

We moved "easy to get wrong" from human discipline into **structure** (layering + pure functions + one composition root)
and **automation** (87 tests + per-source logging + degradation banners) — the pipeline no longer relies on
"remember to check"; it either can't go wrong, or tells you exactly where it did.
