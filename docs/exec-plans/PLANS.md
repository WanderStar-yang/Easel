# PLANS.md
# AI Social Operator V1 - Codex Execution Plan Rules

## 1. 目的

本文件规定 V1 的开发顺序、每阶段输出要求与验收方式。

详细产品需求：

`docs/product-specs/AI_SOCIAL_OPERATOR_V1.md`

仓库级开发约束：

`AGENTS.md`

Easel 官方源码：

https://github.com/ZJU-REAL/Easel

---

# 2. 执行原则

## 2.1 必须分阶段执行

禁止一次性开发整个 V1。

每次只允许执行一个 Phase。

当前 Phase 完成并经过人工确认后，才进入下一 Phase。

## 2.2 不允许跳过源码审计

Phase 0 是强制阶段。

未完成：

`docs/audits/EASEL_V1_SOURCE_AUDIT.md`

不得开始 Phase 1。

## 2.3 ACTIVE_PLAN

Phase 0 完成后，Codex 必须根据真实 Easel 源码生成：

`docs/exec-plans/ACTIVE_PLAN.md`

ACTIVE_PLAN 是实际开发计划。

本文件中的 Phase 是业务顺序基线。

若真实源码需要调整技术顺序，可以调整，但必须：

- 保持业务依赖正确
- 说明原因
- 不得删除产品验收项

---

# 3. 每个 Phase 开始前必须输出

开始编码前必须明确：

1. 本阶段目标
2. 对应的产品需求章节
3. Easel 现有相关模块
4. 直接复用内容
5. 修改复用内容
6. 新增文件
7. 删除/隐藏内容
8. 数据模型变化
9. API 变化
10. UI 变化
11. 兼容性风险
12. 测试方案
13. 验收标准

若现有源码与预期不一致，先报告，不得直接强行实现。

---

# 4. 每个 Phase 完成后必须执行

根据项目实际能力运行适用的：

```text
Build
Lint
Unit Test
Integration Test
必要的手动测试
```

然后必须检查：

```text
git status
git diff
```

并汇报：

- 实际修改文件
- 新增文件
- 核心实现
- 测试结果
- 未解决问题
- 是否存在技术债
- 本阶段验收项是否全部通过
- 是否可以进入下一阶段

完成后停止，不自动执行下一 Phase。

---

# 5. Phase 0 - Easel 源码审计

## 目标

理解当前 clone / fork 的真实 Easel 源码，而不是根据文档猜测。

## 禁止

本阶段禁止：

- 正式业务功能开发
- 大规模重构
- 数据库迁移
- 删除现有模块
- 提前实现 V1 功能

## 必须检查

至少检查：

- 根目录结构
- 技术栈
- 前端
- 后端/服务层
- Agent
- Skills
- Profile
- Account
- Storage
- Model Provider
- Content Calendar
- Trend / Research
- Topic Planning
- Content Generation
- Analytics
- Long-term Memory
- 平台适配
- 发布相关能力
- 测试体系
- 构建体系

## 产物

创建：

`docs/audits/EASEL_V1_SOURCE_AUDIT.md`

报告至少包含：

1. 当前实际技术架构
2. 关键目录及职责
3. V1 已存在能力
4. 直接保留清单
5. 修改复用清单
6. 新增开发清单
7. V1 隐藏/删除清单
8. 数据模型差异
9. Initial Diagnosis 接入方案
10. Account Intelligence Engine 接入方案
11. 双账号隔离方案
12. Strategy / Prompt 目录方案
13. 风险
14. Phase 1～15 技术实施建议

## 验收

- 未修改核心业务代码
- 审计报告完整
- 所有结论基于真实源码
- 能明确说明下一阶段如何开始

---

# 6. Phase 1 - 双账号基础模型

## 目标

支持两个独立账号：

- Douyin Pet Account
- Xiaohongshu Developer Account

## 必须实现

- Account 基础模型
- Platform 字段
- Profile 独立
- Strategy 独立
- 数据隔离
- 状态字段

建议状态：

```text
NEW
IMPORTING
DIAGNOSING
STRATEGY_PENDING_CONFIRMATION
ACTIVE
REVIEWING
```

## 验收

- 可创建两个账号
- 两账号数据不串
- Profile 不串
- Strategy 不串
- 未 ACTIVE 账号不能进入正式运营

---

# 7. Phase 2 - 历史数据导入

## 目标

为首次诊断提供历史作品数据。

## 必须实现

至少支持：

- 人工录入
- CSV / Excel 导入
- 历史作品列表
- 编辑
- 删除
- 数据完整度提示

## 抖音至少支持字段

- publishTime
- title
- duration
- contentSource
- contentType
- subjects
- views
- likes
- comments
- favorites
- shares
- followersGain

## 小红书至少支持字段

- publishTime
- title
- contentType
- views/exposure
- likes
- favorites
- comments
- shares
- followersGain
- profileVisits
- inquiries

## 验收

- 两个平台历史数据可正常导入
- 错误数据有提示
- 数据归属正确
- 诊断引擎可读取历史数据

---

# 8. Phase 3 - Account Intelligence Engine / Initial Diagnosis

## 目标

实现首次账号诊断。

## 必须分析

### 抖音

- 内容结构
- 播放中位数
- 点赞中位数
- 评论中位数
- 互动率
- REAL / AI
- 单猫 / 双猫
- 内容类型
- Hook
- 时长
- 高低表现作品

### 小红书

- 内容类型
- 曝光/浏览
- 点赞
- 收藏
- 评论
- 分享
- 涨粉
- 主页访问
- 咨询
- 高低表现主题

## 输出

`AccountDiagnosis`

包含：

- 当前状态
- 优势
- 问题
- 高表现模式
- 低表现模式
- 可验证方向
- 初步定位建议
- 数据完整度

## 验收

- 两账号均可完成诊断
- 诊断结果来源可追溯
- 不使用固定结论覆盖真实数据
- 当前初始定位只作为参考假设

---

# 8.5 Phase 3.5 - Douyin Official Export Import Compatibility

## 目标与范围

V1 抖音历史数据以 PC 端抖音创作者中心官方导出的作品列表 XLSX 为主数据来源。本阶段只完成官方文件识别、字段适配、导入预览、确认后的 Snapshot Reconciliation、旧历史重复修复和诊断过期联动；不开发账号基线或后续运营能力。

浏览器辅助扩展、DOM 扫描、Creator Center Sync Session、会话 API、翻页/续扫、OpenAPI 占位界面均已退出 V1。Easel 原有平台登录和发布、Social Operator Account Diagnosis、HistoricalPost、通用 CSV/XLSX 导入及人工录入继续保留。

## 实施依据与数据规则

- 复用 `HistoricalPost`、Phase 2 CSV/XLSX 读取与人工录入能力，以及 Phase 3 Account Diagnosis；仅为官方 XLSX 增加 `DouyinCreatorExportParser` 和 `SnapshotReconciliationManager`。
- 官方列映射包括作品名称、发布时间、作品 ID/内容 ID、播放量/曝光量、点赞量、评论量、收藏量、分享量、粉丝增量；体裁存入 `content_type_raw`。新出现的未支持列展示为暂未纳入 V1 诊断的字段，不阻止导入。
- 每次上传按 Snapshot 预览。平台作品 ID 优先作为身份；没有 ID 时使用规范化发布时间+标题。低置信度匹配会在预览中提示；缺失发布时间不报错、不填当前时间。
- 新文件更新非空平台事实，空值不覆盖已有值，真实 `0` 可覆盖。新增/更新作品和确认合并修复会使已有 Diagnosis 标记为 `STALE`；新快照确认更新已有行时也会提示重新诊断。
- 历史数据修复支持稳定键自动合并和弱键人工复核；确认时执行自动合并项及用户明确勾选的人工确认组，Canonical ID 保留，诊断引用映射后归档重复项。

## API / UI

- 保留账号隔离的 HistoricalPost CRUD、通用文件预览/确认、完整度、诊断及修复 Preview/Confirm API。
- 官方 XLSX 从现有 `/posts/imports/preview` 自动识别；快照通过 `/posts/imports/snapshot-confirm` 明确确认。
- 抖音历史页主按钮为「导入抖音作品数据」，说明用户先从 PC 创作者中心导出作品列表 XLSX；同时保留手动添加及折叠的其他 CSV/XLSX 入口。
- 预览展示识别平台、文件记录、可识别、新增/更新/重复/错误、缺失字段、低置信度提示、暂未纳入 V1 的列和样例行。

## 验收

覆盖真实格式 XLSX 表头、字段映射、未知列、空值、数字/日期、重复上传、第二次指标更新、真实零值、null 保留、诊断 stale、账号隔离和旧浏览器同步代码移除。确认 Easel 原有平台登录/发布路由与小红书历史内容流程仍可用。完成 Phase 3.5 后停止，Phase 4 仍需用户单独确认。

---

# 8.6 Phase 3.6 - Diagnosis UX & Data Integrity

## 范围

只修复 Initial Diagnosis 的数据可信度与用户体验；不建立 Account Baseline，不进入 Phase 4。

## 必须完成

- 所有诊断统计使用 account-scoped canonical unique HistoricalPost；Top/Low、样本量、中位数、内容分布和比较不得重复计数。
- 对官方 Douyin XLSX 和旧浏览器数据执行预览确认式修复；官方记录优先，旧扫描记录保留归档载荷；不稳定身份的记录需明确提示人工复核。
- 区分 raw、有效唯一作品和诊断样本数量；普通页面显示有效作品数，raw/source/阈值/算法字段折叠到技术详情。
- Stale 诊断顶部显示过期提示并折叠旧正文；缺失数据以未知/未分析/暂无数据展示，不得伪装为 Hook 不存在或指标为 0。
- 诊断页以用户语言展示一句话诊断、账号基准、高/低表现、优势/问题/机会、数据不足及下一步 CTA；统计事实由确定性逻辑生成，LLM 不能覆盖。
- 提供批量设置 content_source（REAL/AI/MIXED）、subjects、content_type 的账号级能力，并在分类后使旧诊断过期。
- 修复旧创作者中心控件文案对 title 的污染；官方 XLSX 的作品标题不得被清洗规则改写。

## 验收

覆盖重复记录、Top/Low、stale、缺失 Hook/时长、title cleanup、raw/unique/sample 计数、LOW/MEDIUM/HIGH 文案、数据缺口、LLM 降级与事实边界、账号隔离和修复后真实账号重诊断。页面由普通用户可以在 30 秒内理解现状、强弱内容、发现和下一步。完成后停止，Phase 4 等待单独确认。

---

# 9. Phase 4 - Account Baseline

## 目标

建立可追溯版本的账号历史表现基准。Diagnosis 是描述性分析报告；Baseline 只保存历史典型表现，不输出策略、定位、内容建议或选题。

## 数据来源与持久化

- 输入为 account-scoped canonical unique HistoricalPost；排除归档重复和完整快照标记为 MISSING 的行。整体样本数为有效唯一作品数，指标样本数各自统计。
- 新增 SQLite `account_baselines`，保留 version、period、生成时间、source_updated_at、historical_data_version、status 和完整指标/分组快照；同账号仅允许一个 ACTIVE 版本，重生成将旧版本转为 STALE 并递增版本号。
- 通过存储写入时的 stale 标记及读取时的历史数据版本核对，覆盖 HistoricalPost 新增、删除、修复、指标和分类修改。

## 指标和分组

- 指标包括 views、likes、comments、favorites、shares、engagement_rate、followers_gain、profile_visits、inquiries；当前 HistoricalPost 未保存的 completion_rate、two_sec_bounce_rate、avg_watch_duration 保持 null，并记录后续解析 TODO。
- 指标保存 median、P25、P75、sample_count 和 coverage。P25/P75 使用 nearest-rank 百分位数；Median 是主要统计值。
- 互动率沿用 Phase 3 的逐帖公式：已存在互动数之和 / views，仅对 views > 0 且至少有一个互动字段的作品计算；再对有效逐帖比率取中位数。
- 内容分组覆盖 content_source、content_type、subjects、hook_type、duration_bucket、publish_period。UNKNOWN/空分类不生成组；group sample ≥3 显示初步基准，≥5 标记为可供未来正式比较。
- Diagnosis 当前有效是建立入口前置。预览给出样本数、日期范围、指标和分类覆盖；用户显式确认后保存。

## API / UI / 比较接口

- 新增 `/api/operator/accounts/{account_id}/baseline` 读取当前版本、显式生成新版本；`/preview` 生成确认前快照；`/history` 读取版本历史；`/compare` 提供 views、likes、engagement_rate 相对中位数及 P25/P75 区间比较。
- Diagnosis 页面显示 Baseline 状态和建立/查看/重新生成入口。普通用户页面展示典型中位数、逐项样本和覆盖率、时间范围、分组基准和分类不足入口，不暴露 UNKNOWN 分组。
- Baseline stale 时提示“历史数据已发生变化，请重新生成基准。”新内容的比较由服务层复用，不在本 Phase 实现 Weekly Review。

## 必须包含

- viewsMedian
- likesMedian
- commentsMedian
- engagementRateMedian
- contentTypeBaselines
- sourceBaselines

有数据则加入：

- favorites
- shares
- followersGain
- profileVisits
- inquiries

## 验收

- 测试 canonical 唯一作品、Median/P25/P75、missing 与真实 0、互动率、样本数/覆盖率、整体与分组门槛、V1/V2/唯一 ACTIVE、stale、账号隔离、异常值、重启持久化和 Phase 3 Diagnosis 回归。
- 用真实抖音账号在 UI 预览并建立基准；有效样本应为 82，与 Diagnosis 播放中位数一致，未分类数据不生成 UNKNOWN 分组，693000 级真实高播放不扭曲 Median。
- 完成后停止，不开始 Phase 5 Strategy Recommendation。

---

# 9.5. Phase 4.5 - Historical Content Enrichment

## 目标与边界

在 Phase 4 与 Phase 5 之间，以 AI 文本建议和用户批量确认补充历史作品分类。只处理内容来源、出镜主体和内容类型；不生成 Hook、策略、Content Pillars 或选题。

## 分类取值

- 内容来源：REAL、AI、MIXED、UNKNOWN；用户端显示真实拍摄、AI 生成、真人/AI 混合、暂无法判断。文本证据不足必须 UNKNOWN。
- 出镜主体：缅因、布偶、双猫、其他、UNKNOWN；无法从标题/已有文本可靠判断时 UNKNOWN。
- 内容类型：单猫日常、双猫互动、双猫反差、搞笑/趣味、养猫经验、情绪/陪伴、AI创意、其他；不扩展 V1 标签集合。
- Hook 保持未分析状态。

## AI 与标签来源

- Prompt 只接收 title、source_content_type、已有 tags 和 description/note；不得传入任何播放或互动表现指标。
- 输出每字段结构化 `{value, confidence, reason?}`；置信度 HIGH/MEDIUM/LOW。值缺失、无效、模型输出不完整或证据不足时回退 UNKNOWN/LOW。
- AI 结果独立保存为 SUGGESTED，不改写历史作品字段。人工确认优先；保存来源 IMPORT / AI_CONFIRMED / MANUAL_CONFIRMED、当前值、字段置信度与确认时间。
- 提供 AI 建议、未分类、低置信度过滤，所选建议接受和有计数预览的“全部接受高置信度建议”。

## 批量审核和 Baseline

- 历史页以表格批量显示标题、播放、三个当前分类、AI 建议和置信度；支持多选并批量设置三个固定字段。
- 分类完成度按有效 canonical unique posts 分母分别统计。
- 用户确认分类后使旧 Diagnosis 和 ACTIVE Baseline stale；Diagnosis 更新后，用户重新预览并生成 Baseline V2。整体指标仍使用原有 Phase 4 统计方式；分组样本 <3 不展示，3–4 只作为初步数据，≥5 才可供 Phase 5 正式比较。

## 验收

- 自动测试覆盖模型结构与 UNKNOWN 回退、置信度、人工覆盖 AI、批量设置与过滤数据、全部接受高置信度、账号隔离、覆盖率、Baseline stale/V2/分组门槛、Phase 4 整体 Median 回归。
- 先在真实 Easel UI 配置 OpenAI-compatible Provider，并通过实际 Chat Completion 连通性测试；若失败，记录完整 HTTP 状态和原因，在连通前不发送历史作品分类请求。
- 使用当前 82 条抖音作品抽查至少 20 条 AI 建议，统计完全正确、部分正确、明显错误、无法判断；若明显错误率不可接受，优化保守 Prompt 后重抽样。
- 抽样达到可接受水平后以每批不超过 20 条处理剩余作品；逐项人工修正并确认，分别记录内容来源、主体、内容类型的 AI 建议数、人工确认数与 UNKNOWN 数。
- 确认 V1 Baseline stale 后，更新 Diagnosis 并显式重新生成 V2；确认 Overall Median 与 V1 基本一致，记录 REAL/AI、缅因/布偶/双猫和 Content Type 分组数据及样本门槛。
- 完成后停止，不开始 Phase 5。

### 真实账号验收记录（2026-09-30）

- Qwen OpenAI-compatible Provider 经现有 AIService 完成真实模型连通测试和 82 条作品分类；20 条随机样本中 19 条建议有标题依据、1 条存在过度推断，收紧 Prompt 后将该项及两条 `#ai` 弱证据来源建议改为 UNKNOWN。所有 82 条均有三字段建议，失败的 5 条经增量重试完成；模型请求不含表现指标。
- 真实 UI 确认 46 条作品中的 64 个高置信度字段建议，并人工确认两条有明确双猫互动标题证据的记录。当前有效确认数：来源 1 条 AI、主体 38 条 AI + 2 条人工、内容类型 25 条 AI + 2 条人工。UNKNOWN 建议数：来源 81、主体 42、内容类型 19；中低置信度的非 UNKNOWN 建议保持待审。分类覆盖分别为 1/82、40/82、27/82。
- 重新运行 Diagnosis 后显式预览并建立 ACTIVE Baseline V2；V1 保留为 STALE。V2 sample_size=82、周期 2025-06-24～2026-09-28，播放 Median 578.5、互动率 Median 2.02%，均与 V1 一致。692,689 播放真实作品保留。
- 分组结果：主体双猫 n=8、布偶 n=15、缅因 n=16；内容类型单猫日常 n=11、搞笑/趣味 n=9 可供后续正式比较，双猫互动和情绪/陪伴各 n=3 仅为初步基准。AI 来源 n=1，来源分组不展示；REAL/MIXED 无充分证据。未分类 UNKNOWN 不形成分组。完播率、2 秒跳出率和平均播放时长未由当前官方 XLSX Parser 可靠解析，基准值为空。
- 完成真实页面闭环。最终自动化验证与 Git 状态见本阶段提交记录。Phase 4.5 验收通过，停止于 Phase 4.5，不代表授权开始 Phase 5。

---

# 9.6. Phase 4.5.1 - Model Provider / AI Classification Runtime Fix

## 目标与边界

修复 Phase 4.5 历史作品预分类的模型调用链；仅解决 AI Runtime、Provider 解耦、运行状态提示、批次隔离与结构化逐条解析。禁止开始 Phase 5，不安装全局 OpenClaw。

## Provider 与调用约定

- 分类只依赖 `AIService` 抽象；集中解析现有 Easel 模型配置并按可用 Provider 调用，不在分类业务中硬编码厂商名称或 Gateway URL。
- 复用当前 `.env` 模型槽位、设置面板和仓库已有 `httpx` 依赖；不增加独立 AI SDK。兼容 Chat Completions 与当前 Anthropic-compatible 配置；OpenClaw Gateway 仅作为可选回退。
- UI runtime 状态为 AVAILABLE / NOT_CONFIGURED / UNAVAILABLE / ERROR，并提供模型设置入口；AI 不可用时手动分类仍可用。
- 每批最多 20 条；输入仅包含作品 ID、标题、原始作品类型、标签和描述。逐条校验结构，失败作品独立记数、其它有效响应保留。

## 验收

- 测试 Provider 配置/可用状态、OpenClaw 缺失时的兼容模型调用、无配置提示、白名单输入、20 条批次限制、单条解析失败和跨批次继续。
- 真实 UI 确认普通用户可看到 AI 模型状态，并能从分类页打开现有模型设置；只有真实 Provider 显示 AVAILABLE 才执行真实 AI 分类验收。
- 记录真实账号 Provider 状态。Phase 4.5.1 完成后停止，等待用户确认后再进入 Phase 5。

---

# 10. Phase 5 - Strategy Recommendation

## 目标

根据 Diagnosis + Baseline 生成第一阶段运营建议。

## 输出

- 定位建议
- Audience 建议
- Content Pillars
- 各 Pillar 建议占比
- 主要问题
- 机会方向
- 第一阶段实验计划

## 原则

当前预设定位只是 Initial Hypothesis。

AI 必须优先读取真实诊断结果。

## 验收

- 抖音与小红书分别生成不同建议
- 推荐理由引用真实历史数据
- 不直接自动激活 Strategy

---

# 11. Phase 6 - Strategy Confirmation

## 目标

用户确认第一阶段运营策略。

## 必须支持

- 查看 Strategy Recommendation
- 修改 Content Pillar 比例
- 确认
- 退回修改
- 激活 Strategy

确认后：

```text
ContentPillarsStatus = ACTIVE
Account.status = ACTIVE
```

## 验收

未确认 Strategy 的账号：

不得生成正式 Daily Recommendation。

---

# 12. Phase 7 - Topic Engine

## 目标

建立选题生成能力。

## Topic 来源

- Account Strategy
- Content Pillars
- Historical Performance
- Strategy Memory
- Existing Materials
- Trend
- Successful Pattern Variants
- AI Original

## 验收

- 每账号能独立生成 Topic
- Topic 能追踪来源
- Topic 能关联 Content Pillar
- 两个账号选题风格明显不同

---

# 13. Phase 8 - TopicScore

## 抖音初始建议

```text
Strategy Match        25%
Historical Support    20%
Material Feasibility  20%
Interaction Potential 15%
Freshness             10%
Series Potential       5%
Production Cost        5%
```

## 小红书初始建议

```text
Audience Demand        25%
Account Positioning    20%
Real Experience        20%
IP / Trust Value       15%
Historical Support     10%
Search Value            5%
Production Cost         5%
```

## 验收

- 两账号评分逻辑独立
- Score 可解释
- Score 不是随机数字
- 能追踪各维度得分

---

# 14. Phase 9 - Daily 3选1

## 目标

每账号每日输出：

- 3 个候选
- 1 个主推

## 每个候选显示

- Topic
- TopicScore
- 推荐原因
- Content Pillar
- 目标
- 制作成本
- 是否已有素材
- 是否实验内容

## 验收

- ACTIVE 账号才生成正式推荐
- 每账号独立 3 选 1
- 主推有清晰推荐理由

---

# 15. Phase 10 - Content Generation

## 抖音

生成：

- Hook
- 前 3 秒
- 视频结构
- 镜头建议
- 字幕
- 建议时长
- 标题
- BGM 类型
- 话题
- 评论互动
- 发布时间建议
- 素材建议

## 小红书

生成：

- 标题 × 5
- 封面文字
- Hook
- 正文结构
- 完整正文
- 配图结构
- 截图建议
- CTA
- 评论互动
- 话题
- 发布时间建议

## 验收

两账号输出模板不能混用。

---

# 16. Phase 11 - 素材库

## V1 目标

不做复杂 AI 视频识别。

实现：

- 上传
- 缩略图
- 标签
- 描述
- AI 辅助摘要
- Content Pillar 匹配
- Topic 匹配

## 宠物标签示例

```text
缅因
布偶
双猫
吃饭
睡觉
打闹
抢位置
搞笑
粘人
反差
日常
```

## 验收

- 素材可以关联账号
- 素材可以关联 Topic
- Topic Engine 能判断素材可执行性

---

# 17. Phase 12 - Content Calendar

## 状态

```text
IDEA
SELECTED
DRAFT
READY
PUBLISHED
REVIEWED
```

## 必须支持

- 计划发布时间
- 实际发布时间
- 平台
- 账号
- Topic
- Draft
- 发布链接
- Review 状态

## 验收

内容生命周期可完整追踪。

---

# 18. Phase 13 - Published Data

## 目标

发布后记录真实数据。

## 时间点

- 24H
- 72H
- 7D

## 指标

按平台支持情况记录：

- views
- likes
- comments
- favorites
- shares
- followersGain
- profileVisits
- inquiries

## 验收

- 数据归属正确
- 同一 Post 支持多个 checkpoint
- Weekly Review 能读取

---

# 19. Phase 14 - Weekly Review

## 输出

- 本周内容数量
- 与 Baseline 对比
- Content Pillar 表现
- Topic 表现
- Hook 表现
- 时长表现
- 发布时间表现
- REAL / AI 表现
- 高表现共性
- 低表现共性
- 下周建议

## 验收

Review 必须基于真实数据，不得只生成通用鸡汤式建议。

---

# 20. Phase 15 - Strategy Feedback Loop

## 目标

形成完整闭环：

```text
Published Data
  ↓
Weekly Review
  ↓
Strategy Memory
  ↓
Topic Engine
  ↓
新的 Daily Recommendation
```

## 必须实现

- Weekly Review 写入 Strategy Memory
- Topic Engine 读取相关 Memory
- 新选题能反映近期复盘结果
- 不直接永久覆盖原始历史数据

## 验收

至少能展示一条：

“本周复盘结论如何影响下一轮推荐”

V1 到此才视为真正闭环。

---

# 21. V1 最终验收

整个 V1 必须同时满足：

## 账号

- 两账号独立
- Profile 独立
- Strategy 独立
- 数据独立

## 诊断

- 历史数据导入
- Initial Diagnosis
- Baseline
- Strategy Recommendation
- Strategy Confirmation

## 日常运营

- 每账号每日 3 个候选
- 1 个主推
- 抖音脚本
- 小红书完整图文

## 素材

- 管理
- 标签
- 描述
- Topic 关联

## 数据

- 24H / 72H / 7D
- Weekly Review
- Strategy Memory

## 闭环

```text
诊断
→ 策略
→ 选题
→ 内容
→ 发布
→ 数据
→ 复盘
→ 下一轮推荐
```

任一关键链路缺失：

V1 不视为完成。

---

# 22. 推荐给 Codex 的首次执行 Prompt

将以下内容作为打开仓库后的第一条任务：

```text
请先阅读项目根目录 `AGENTS.md`。

然后完整阅读：

docs/product-specs/AI_SOCIAL_OPERATOR_V1.md
docs/exec-plans/PLANS.md

本轮禁止开始正式业务功能开发。

当前只执行 Phase 0：Easel 源码审计。

请检查当前 Easel 仓库真实源码，包括但不限于：

- 项目整体目录结构
- 前端架构
- 后端/服务层
- Agent 工作流
- Skills
- Profile / Account
- Storage
- Content Calendar
- Trend / Research
- Topic Planning
- Content Generation
- Analytics
- Long-term Memory
- Model Provider
- 平台适配
- 发布相关能力
- 测试与构建体系

然后创建：

docs/audits/EASEL_V1_SOURCE_AUDIT.md

要求报告包含：

1. 当前 Easel 实际技术架构
2. 关键目录和模块作用
3. 与 V1 已经重合的能力
4. 直接保留模块
5. 修改复用模块
6. 必须新增模块
7. V1 应隐藏/移除模块
8. 当前数据模型与 V1 数据模型差异
9. Initial Diagnosis 应该接在哪一层
10. Account Intelligence Engine 接入方式
11. 双账号数据隔离方案
12. Strategy / Prompt 合理目录
13. 开发风险
14. Phase 1～Phase 15 建议实施顺序

特别要求：

- 不要凭文档猜测 Easel 结构，必须以当前源码为准。
- 不要重新实现 Easel 已存在的能力。
- 不要修改核心业务代码。
- 本阶段只允许新增必要的 docs 审计文件。
- 完成后停止，不要继续 Phase 1。
```
