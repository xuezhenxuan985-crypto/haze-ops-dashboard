# AI 功能问答 — Haze Ops Dashboard（AI 简报）

# AI Feature Q&A — Haze Ops Dashboard (AI Brief)

围绕五个问题 / Organized around five questions.

---

## 1. 目的：AI 解决了什么问题？为什么 AI 适合这项任务？
## Purpose: What problem does the AI solve? Why is AI the right tool?

**问题 / The problem**：面板有 4 个标签页、几十个数字、图表和表格；工地 Ops/EHS 经理要在几分钟内
判断"今天该怎么办"。规则引擎的文案是逐块拼起来的（每个区域一张卡片、每张卡片一句建议），
没有把"PM2.5 涨了 + 西南风 + 苏门答腊火点 180 个"串成一个连贯判断。
The dashboard has 4 tabs and dozens of numbers; an Ops/EHS manager needs to decide "what do we do
today" in minutes. The rule engine produces per-tile text, never a connected story like
"PM2.5 rising + SW wind + 180 Sumatra hotspots".

**AI 做的事 / What the AI does**：把当天的 Snapshot 写成一段 <200 字的自然语言简报（中/英），
分"今日概况 / 行动建议 / 未来 24 小时展望"三节。一分钟读完，可直接用于晨会或与工人沟通。
It turns the day's Snapshot into a <200-word plain-language briefing (EN/中文) in three sections —
today / actions / next 24 h. One-minute read, usable in morning briefings or with workers.

**为什么适合 AI / Why AI fits**：
- 输入是**结构化数据**——没有开放网页、没有需要外部知识的问题，幻觉面最小；
  模型只做"把数字讲成人话"这一件事。
- 输出是**每天组合各不相同的自然语言**（5 区域 × 波段 × 风 × 火点 × 历史趋势），
  规则模板要枚举所有组合是不现实的；LLM 天然擅长组合表达。
- **AI 不做决策**：波段、风险分、工作矩阵全部留在确定性规则代码里；LLM 只负责解释层。
  AI 适合"解释"，规则适合"裁决"——我们让各自干各自擅长的。
- Input is structured data — no open web, no external-knowledge questions, minimal hallucination
  surface; the model does one job: turn numbers into words.
- Output is natural language with a different combination every day (5 regions × bands × wind ×
  fires × trends) — enumerating all combinations in templates is impractical; composing is what
  LLMs are good at.
- The AI makes no decisions: bands, risk scores, and the work matrix stay in deterministic rule
  code. AI explains, rules decide.

## 2. 集成：如何把 LLM API 集成进应用？
## Integration: How is the LLM API integrated?

- **直接 HTTP 调用** DeepSeek 的 OpenAI 兼容接口（`api.deepseek.com/chat/completions`，模型
  `deepseek-chat`，`max_tokens=700`，超时 30s），用已有的 `requests`——不引入新依赖。
  Direct HTTP call to the DeepSeek OpenAI-compatible API (`deepseek-chat`, `max_tokens=700`,
  30 s timeout) with the existing `requests` library — no new dependency.
- **Key 处理照搬 FIRMS 模式**：sidebar 输入 → 只存 `session_state`；缓存键用
  `sha256(key)` 的哈希，**原始 key 不进缓存参数、不落盘、不入日志**。
  Key handling copies the FIRMS pattern: sidebar input → session_state only; the cache key uses
  a sha256 hash of the key, so the raw key never enters cache args, disk, or logs.
- **分层不变**：`src/data/ai_brief.py`（纯函数组 prompt、HTTP 调用、措辞护栏），
  `pipeline.py` 仍是唯一组合根并持有唯一的 `st.cache_data`（TTL 30 分钟）。
  Same layering: `src/data/ai_brief.py` (pure prompt builder, HTTP call, wording guardrail);
  `pipeline.py` remains the only composition root holding the only `st.cache_data` (30 min TTL).
- **触发方式**：第 5 个标签页 "AI brief" 里的按钮——按需调用，绝不自动循环；
  没配 key 时该页只显示引导说明，**零调用**。
  Triggered by a button in the fifth tab, "AI brief" — on-demand only, never automatic loops;
  with no key configured the tab shows guidance and makes zero calls.

## 3. 输入：传给模型什么数据/上下文？
## Input: What data/context goes to the model?

**System prompt（规则与角色）**：角色定义 + 硬规则——只准使用提供的数据、不得编造读数/火点数；
禁止"全面停工"类表述并给出 MOM 官方措辞；<200 字；固定三节标题；结尾必须带"非官方 NEA/MOM 指示"；
用指定语言回答。
System prompt: role + hard rules — use only the provided data, never invent readings or hotspot
counts; never say "stop all work" (MOM phrasing given instead); <200 words; three fixed section
headings; mandatory non-official disclaimer line; respond in the requested language.

**User message（当天 Snapshot 的序列化）**：模式与数据时间戳；每区域 1 小时 PM2.5（数值+波段）、
24 小时 PSI（数值+档位）、风速风向+降雨；各火点源今日/昨日数量；传输风险等级/得分/上风火点数/主导来源；
ASMC 警报等级；14 天历史最差区域 + 超标占比 + 趋势斜率；数据缺失标志。
User message (serialized Snapshot): mode and data timestamp; per region — 1-hr PM2.5 (value + band),
24-hr PSI (value + tier), wind speed/direction + rain; hotspots per source today/yesterday;
transport risk level/score/upwind points/dominant source; ASMC alert level; 14-day worst region +
% above 55 + trend; data flags.

**不传什么 / What never goes in**：API key、用户任何个人信息、任何外部网页内容。
The API key, any personal information, any external web content.

## 4. 输出：AI 产出什么？对用户有什么用？
## Output: What does the AI produce, and how does it help?

- 一段 <200 字简报，严格三节：**今日概况 → 行动建议 → 未来 24 小时展望**，结尾带免责声明，
  语言跟随面板（EN/中文）。
  A <200-word briefing in exactly three sections — today / actions / next 24 h — ending with the
  disclaimer, in the panel's language (EN/中文).
- **用途**：① 晨会一分钟读完"今天什么情况、该做什么"；② 与工人/分包沟通的大白话版本
  （数字解释不动，话讲得明白）；③ 把分散在 4 个标签页的信息串成一个连贯判断。
  Uses: ① one-minute morning read of "what's happening and what to do today"; ② plain-language
  version for talking to workers/subcontractors; ③ connects the four tabs into one coherent judgment.
- 面板在简报下方固定渲染免责声明行（不是只靠模型自觉）；如果护栏改过措辞，会显示
  "已自动修正"提示。
  The panel always renders its own disclaimer line under the brief (not just the model's word);
  if the guardrail corrected wording, a "correction applied" note is shown.

## 5. 可靠性：发现了哪些限制/风险？如何应对不可靠或意外的响应？
## Reliability: What limits/risks were found, and how are unreliable responses handled?

| 风险 Risk | 应对 Mitigation |
|---|---|
| 模型编造读数（幻觉）/ hallucinated readings | 提示词硬规则"只准用所给数据"；输入全部结构化、无开放网页；简报只是解释层，数字以规则标签页为准 / prompt hard rule "only the provided data"; fully structured input; the numbers on rule tabs remain the source of truth |
| 说出"全面停工"违反 MOM 措辞 / "stop all work" violates MOM wording | **双保险**：① 提示词禁止并给出官方措辞；② `sanitize_brief` 输出后替换被禁措辞（英文大小写不敏感 + 中文变体）并在界面提示"已修正"；有单元测试 / two lines of defence: ① the prompt forbids it and supplies MOM phrasing; ② `sanitize_brief` post-processing replaces banned phrasing (case-insensitive EN + ZH variants) with a visible note; unit-tested |
| API 失败/超时/响应无法解析 / API failure, timeout, unparseable response | `AiBriefError` → 该页显示警告"生成失败，其余标签页不受影响"；规则版内容永远是兜底 / raises AiBriefError → warning banner on that tab only; the rule-based tabs are always the fallback |
| 费用失控 / runaway cost | 只按钮触发（不自动、不轮询）；30 分钟缓存按 (prompt, key) 复用；max_tokens 700 / button-triggered only; 30-min cache per (prompt, key); 700-token cap |
| 没 key / key 无效 / no or invalid key | 该页显示引导说明、零调用；整个应用是可选增强，没有 AI 也完整可用 / guidance text, zero calls; the feature is optional — the app is complete without it |
| 模型漏写免责声明 / model omits the disclaimer | 面板用固定 i18n 文案**总是**渲染免责声明行 / the panel always renders its own fixed disclaimer line |
| 语言质量波动 / variable language quality | 简报定位为"辅助沟通"而非权威文书；官方口径始终指向 haze.gov.sg / positioned as communication aid, not an authoritative document; official guidance always points to haze.gov.sg |

**仍然存在的诚实限制 / Honest remaining limits**：
- 护栏只覆盖已知的禁词清单——提示词遵循是概率性的，极端情况仍可能出现未被覆盖的不当措辞，
  因此"非官方"声明永远在。The guardrail covers a known phrase list — prompt adherence is
  probabilistic, so wording outside the list could slip through; hence the permanent disclaimer.
- 模型不能"看见"未来：简报的"展望"只是基于当前风/火点数据的常识性推测，不是预测模型。
  The model cannot see the future: the "next 24 h" section is common-sense inference from current
  wind/hotspot data, not a forecast model.
