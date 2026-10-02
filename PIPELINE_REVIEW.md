# 管道工程实践问答 — Haze Ops Dashboard

# Pipeline Engineering Q&A — Haze Ops Dashboard

按五个问题组织 / Organized around five questions.

---

## 1. 我们把什么拆成了函数/模块？ What did we separate into functions/modules?

**模块（按层）/ Modules (by layer)**：

| 模块 Module | 职责 Responsibility |
|---|---|
| `config.py` | 全部常量：端点、TTL、波段阈值、距离权重、站点→区域映射 / all constants: endpoints, TTLs, band thresholds, distance weights, station→region map |
| `src/data/fetcher.py` | 统一 HTTP：共享 `RateLimiter`（6次/10s）、重试+退避 / shared HTTP: one `RateLimiter`, retry + backoff |
| `src/data/nea_pm25.py` / `nea_weather.py` | NEA 各端点的获取与解析（实时 + `?date=` 回填）/ per-endpoint fetch & parse |
| `src/data/hotspots.py` | ASMC 火点（多过境合并去重）+ FIRMS 富化 / hotspot sources + FIRMS enrichment |
| `src/data/history.py` | 运行时历史 CSV：追加、窗口裁剪、去重 / runtime history CSV: append, window, dedupe |
| `src/data/pipeline.py` | 唯一组合根：组装 `Snapshot` + 全部缓存 / the only composition root: builds `Snapshot`, owns all caches |
| `src/risk/bands.py` / `transport.py` / `engine.py` / `advisory.py` / `analysis.py` | 纯函数：波段分级、趋势斜率、传输风险、工作决策、区域分析 / pure functions: bands, trend, transport risk, work decisions, regional analysis |
| `src/ui/` | 纯渲染：theme / components / charts / map_view / pure rendering only |
| `app.py` | Streamlit 入口：sidebar、语言、自动刷新 fragment / entry: sidebar, language, auto-refresh |

**函数级拆分 / Function-level splits**：
- `http_get()` 与解析逻辑分开——网络容错和业务解析各自独立可测 / `http_get()` separated from parsing — network tolerance and business parsing testable independently
- `fetch_pm25()`（实时）与 `fetch_pm25_backfill()`（历史）共用同一个 `_parse_payload()` / live and backfill fetches share one `_parse_payload()`
- 决策逻辑拆成小纯函数：`band_of()`、`trend_slope()`（OLS）、`advisory_for_psi()`、`work_matrix_for_psi()`、`compute_region_analysis()`，每个函数只做一件事 / decision logic as small pure functions, each doing one thing

## 2. 为什么选这些边界？ Why did we choose those boundaries?

- **副作用与纯函数分开**：网络/Streamlit 只存在于 data 层与 pipeline；risk 层是纯函数——相同输入必得相同输出，可以离线、批量、确定性测试 / **side effects separated from pure logic**: network/Streamlit live only in the data layer; the risk layer is pure — same inputs give the same outputs, so it can be tested offline, in bulk, deterministically.
- **单一职责**：取数、计算、展示三层各只干一件事；一个端点改了格式，只可能波及 `nea_*.py` 和 `test_parsers.py`，不会传染到决策逻辑 / **single responsibility**: fetch / compute / render each do one thing; if an endpoint changes format, only `nea_*.py` and its parser tests are affected — the decision logic is untouched.
- **组合根模式**：所有依赖只朝一个方向（config → data → risk → ui），`pipeline.py` 是唯一的组装点——从结构上消灭循环依赖，也消灭"绕过缓存的第二条通路" / **composition-root pattern**: dependencies flow one way only (config → data → risk → ui) and `pipeline.py` is the single assembly point — circular imports are structurally impossible, and there is no second path that could bypass the caches.
- **层间接口是 dataclass**：传数据不传对象，任何一层都能单独替换（demo 模式直接构造 `Snapshot` 就绕开了全部网络）/ **dataclasses as layer interfaces**: layers exchange plain data, so any layer can be swapped — demo mode builds a `Snapshot` directly and bypasses all network.
- **常量全部集中**：调参（阈值、权重、TTL）只改 `config.py`，不用翻业务代码 / **constants centralized**: tuning thresholds, weights or TTLs means editing `config.py` only, never business code.

## 3. 展示一个测试和一条有用的日志 / Show one test and one useful log message

**测试 / The test**（`tests/test_advisory.py` — 把合规红线自动化 / automating a compliance red-line）：

```python
def test_tier4_never_says_stop():
    for lang in ("en", "zh"):
        for tier in (1, 2, 3, 4, 5):
            text = tr(advisory_for_psi(tier), lang).lower()
            assert "stop" not in text
            assert "全面停" not in text
            assert "停工" not in text
```

MOM 官方对 PSI >300 的表述是"尽量减少户外作业"，**绝不**是"全面停工"。这条测试遍历全部 PSI 档位和两种语言，
断言文案绝不含"stop / 停工"——任何人改措辞踩线，测试立刻红。
MOM's official wording above PSI 300 is "minimise outdoor work", never "stop all work". This test sweeps
all PSI tiers and both languages and asserts the copy never contains "stop / 停工" — any wording slip turns it red instantly.

**日志 / The log message**（`src/data/fetcher.py` — 每次重试都留痕 / every retry is traceable）：

```python
log.warning("GET %s attempt %d failed: %s", url, attempt + 1, exc)
log.warning("GET %s rate-limited (429); waiting %.1fs", url, delay)
```

为什么有用：它带 URL、第几次尝试和原因（异常/429）。生产上 NEA 突然限流时，日志能直接回答
"哪个端点、重试了几次、等了多久"——而不是只有一句笼统的 "fetch failed"。
Why it's useful: it carries the URL, the attempt number and the reason (exception / 429). When NEA suddenly
rate-limits us in production, the log answers "which endpoint, how many retries, how long we waited" —
instead of a generic "fetch failed".

## 4. 降低了哪些编码风险？ What coding risks have we reduced?

| 风险 Risk | 措施 Mitigation |
|---|---|
| 上游 API 限流封禁 / upstream API ban | 全局共享 `RateLimiter`，所有请求统一排队 / one shared RateLimiter for all requests |
| 瞬时抖动崩掉整页 / a blip crashes the page | 重试+退避；各数据源独立 try/except，单源失败走降级横幅 / retry + backoff; per-source failure degrades gracefully with a banner |
| 历史数据重复/不一致 / duplicate history rows | 按 (时间, 区域) 去重；回填与实时采集写同一 CSV 天然幂等 / dedupe on (time, region); backfill + live append are idempotent |
| 分析污染运行时数据 / analysis polluting runtime data | 回填写 `analysis/data/` 冻结 CSV，不碰运行时 CSV / frozen CSVs under analysis/data/, runtime CSV untouched |
| 敏感信息泄露 / leaking secrets | FIRMS key 只存 session_state，不落盘、不入日志 / FIRMS key in session_state only — never on disk, never logged |
| 合规措辞/单位混用 / wrong wording or unit mixing | 铁律写成测试（>300 无"停工"；PSI 不与 US AQI 混排）/ red-lines as tests |
| 逻辑错误混进展示层 / logic bugs in the UI | 风险层纯函数 + 87 项离线单测 / pure risk layer with 87 offline unit tests |
| 静默失败没人知道 / silent failures | 逐源日志 + 界面降级横幅 / per-source logging + on-screen banners |
| 全应用回归没人跑 / no full-app regression | AppTest 全应用冒烟测试（整页渲染 + 双语）/ AppTest full-app smoke |
| 中文文案半缺失 / half-missing Chinese copy | i18n 测试断言 EN/中文键集相等 + 全部模板可格式化 / equal key sets + all templates formattable |

## 5. 还有什么风险仍在？ What risks still remain?

诚实地说，仍有五类 / Five, honestly:

1. **数据本身的滞后与缺失 / stale or missing upstream data**：NEA 整点值偶尔延迟；ASMC 火点每天只随卫星过境更新约 2 次，其 RSS 接口经常滞后。我们的降级横幅能"明示问题"，但无法"造出数据"——极端情况下可能基于滞后数据做决策。
   NEA hourly values occasionally arrive late; ASMC hotspots update only ~2×/day with satellite passes and its RSS often lags. Our banners make the problem visible but cannot invent data — decisions could occasionally rest on stale numbers.
2. **传输风险是启发式而非因果预测 / transport risk is heuristic, not causal**：距离权重、风向扇区匹配是经验规则，会有误报（虚惊）和漏报（真来了没预警）。
   Distance weights and wind-sector matching are empirical rules — there will be false alarms and misses.
3. **云端重部署清空历史 / redeploys wipe runtime history**：Streamlit Community Cloud 重部署会清空临时文件系统，`data/history_pm25.csv` 只能重新回填 14 天——更早的运行时历史会丢失（分析用的 90 天冻结 CSV 在仓库里，不受影响）。
   Redeploys wipe the ephemeral filesystem; the runtime CSV can only be re-backfilled 14 days — older runtime history is lost (the frozen 90-day analysis CSVs live in the repo, so they're safe).
4. **没有 CI 和线上监控 / no CI and no monitoring**：87 项测试只在本地手动跑，忘记跑测试的提交没人拦；应用或数据源出故障，只有有人打开页面才会发现。
   The 87 tests run only locally and manually — a commit pushed without running them slips through; if the app or a source breaks, nobody knows until someone opens the page.
5. **冷启动回填延迟 / cold-start backfill latency**：首次加载要回填 14 天历史（约 20–30 秒），首次体验偏慢。
   First load backfills 14 days (~20–30 s) — slow first impression.

**后续打算 / Planned next steps**：给仓库加 GitHub Actions 跑测试（风险 4）；把运行时历史挪到持久化存储或定期把 CSV 提交回仓库（风险 3）。
Add GitHub Actions to run the suite on every push (risk 4); move runtime history to persistent storage or archive the CSV back into the repo periodically (risk 3).
