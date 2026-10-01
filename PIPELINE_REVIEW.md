# 管道工程实践简报 — Haze Ops Dashboard

面向团队展示：管道如何组织与模块化、加了哪些测试与日志、这些变化如何让流程更可靠。

---

## 1. 如何组织与模块化管道

### 四层单向依赖 + 唯一组合根

```
app.py ──────── Streamlit 入口（sidebar、自动刷新 fragment）
   │
src/ui/ ─────── 纯渲染层：theme / components / charts / map_view（只读 Snapshot，零网络、零计算）
   ▲
src/risk/ ───── 纯函数风险层：bands / transport / engine / advisory / analysis（只依赖 config + models）
   ▲
src/data/ ───── 数据层：fetcher / nea_pm25 / hotspots / weather / history / demo（只做获取与组装）
   ▲
config.py ───── 全部常量：端点、TTL、阈值、站点映射、权重（一处改，全局生效）
```

**三条硬规则（靠目录边界强制执行）**：

1. `src/risk/` 不 import 任何网络/Streamlit 模块——风险计算是纯函数，输入相同输出必相同；
2. `src/data/` 不 import `risk/` 和 Streamlit——数据层不知道"被谁消费"；
3. `src/pipeline.py` 是**唯一组合根**：data 层取数 → `Snapshot` dataclass 组装 → risk 层计算 → ui 层渲染，
   并持有全部 `@st.cache_data` 缓存。任何模块之间没有第二条通路。

### 数据流 = 一条流水线，接口是 dataclass

```
NEA 5 端点 + ASMC + FIRMS  ──(限流/重试/缓存)──▶  Snapshot  ──▶  risk 计算 ──▶  ui 渲染
```

- `models.py` 定义 `Snapshot`、`RegionAnalysis` 等 dataclass——层与层之间**只传数据，不传对象引用**，
  任何一层都可以单独替换/测试（例如 demo 模式直接构造 `Snapshot`，绕开全部网络）。
- 所有可调参数（PM2.5 波段边界、传输风险距离权重、缓存 TTL、站点→区域映射）集中在 `config.py`，
  调参不需要翻代码。
- **双模式**：Live（真实 NEA/ASMC 数据）与 Demo（确定性种子合成数据）走同一条管道，
  演示、截图、测试都复用了同一条路径——不是两套代码。

---

## 2. 测试与日志

### 测试：87 项，全绿，22.8 秒跑完（`pytest -q`）

| 文件 | 覆盖 | 为什么重要 |
|---|---|---|
| `test_bands.py` / `test_transport.py` / `test_engine.py` / `test_advisory.py` | 风险层全部纯函数 | 核心决策逻辑可离线验证 |
| `test_parsers.py` | ASMC/NEA 各端点解析（含多过境文件合并、去重） | 上游格式变了能第一时间发现 |
| `test_analysis.py` | OLS 拟合、区域分析、14 天回填 | 新功能全量覆盖 |
| `test_history.py` | 历史 CSV 追加/窗口裁剪/去重 | 持久化正确性 |
| `test_i18n.py` | EN/中文键集相等 + **全部模板可格式化** | 双语切换不会崩 |
| `test_app_smoke.py` | **Streamlit `AppTest` 全应用冒烟**：demo 模式整页渲染、双语切换 | 端到端回归，不用开浏览器 |

**两个具体例子**：

① **把合规红线变成测试**（`test_advisory.py`）：MOM 官方对 PSI >300 的表述是"尽量减少户外作业"，
**绝不**是"全面停工"。我们写了一条测试，断言所有 PSI >300 的建议文案里不出现
`"stop work" / "全面停止"`。任何一次措辞修改，一旦踩线测试立即红——合规风险被自动化管住。

② **把容错变成测试**（`test_analysis.py`）：回填接口对单日失败必须"跳过该天、继续下一天、绝不抛异常"。
测试用 FakeSession 构造"第 2 天返回 404"的场景，断言行数正确、无异常、其余天数数据完整。
网络故障路径和正常路径一样可回归。

### 日志：每个数据模块自带 `logging.getLogger(__name__)`，故障可追溯

日志只记录**可恢复的异常**，不记录敏感数据。几个关键点：

```python
# fetcher.py —— 每次重试都留痕（含第几次尝试、原因）
log.warning("GET %s attempt %d failed: %s", url, attempt + 1, exc)
log.warning("GET %s rate-limited (429); waiting %.1fs", url, delay)

# nea_pm25.py —— 回填逐日报告，静默失败被消灭
log.warning("pm25 backfill %s: empty payload", date_str)

# pipeline.py —— 每个上游源独立报告，单一源挂掉不影响整体
log.warning("pm25 fetch failed: %s", exc)
```

配合 Streamlit 界面的**横幅降级提示**（如"火点数据部分可用"），生产上出问题时，
日志定位到具体源、界面明示到用户，两层都透明。

---

## 3. 这些变化如何让流程更可靠：降低的编码风险

| 编码风险 | 我们的措施 |
|---|---|
| **上游 API 限流封禁** | 全局共享 `RateLimiter`（6 次/10s），所有请求统一排队 |
| **瞬时网络抖动导致整页崩溃** | fetcher 内置重试 + 退避；各数据源**独立** try/except，单源失败走降级而非抛异常 |
| **重复拉取 / 启动慢** | `@st.cache_data` 按 TTL 缓存（实时数据 5 分钟、回填 6 小时）；刷新不再打 API |
| **历史数据重复写入** | 读取时按 (时间, 区域) 去重；回填与实时采集写同一 CSV 天然幂等 |
| **分析脚本污染运行时数据** | 分析回填写 `analysis/data/` 冻结 CSV，**永远不碰**运行时的 `data/history_pm25.csv` |
| **逻辑错误混进展示层** | 风险计算是纯函数层，87 项单测离线全覆盖；UI 只做渲染 |
| **合规措辞 / 单位混用** | 铁律写成测试：PSI >300 文案无"停工"表述、PSI 绝不与 US AQI 混排 |
| **敏感信息泄露** | NASA FIRMS key 只存浏览器 session_state，**不落盘、不入日志** |
| **全应用回归没人跑** | AppTest 冒烟测试每次提交都跑，覆盖整页渲染 + 双语 |
| **中文文案半缺失** | i18n 测试断言 EN/中文键集完全相等 + 模板全部可格式化 |

**一句话总结**：把"容易出错的地方"从人的纪律改成了**结构**（分层 + 纯函数 + 单一组合根）
和**自动化**（87 项测试 + 逐源日志 + 降级横幅）——管道不再依赖"记得检查"，而是
"错不了"或"错了立刻知道错在哪"。
