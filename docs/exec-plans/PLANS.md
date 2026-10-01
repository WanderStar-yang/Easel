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

建议需要按账号保存版本，并把生成时引用的 Baseline/Diagnosis 版本作为证据快照。Baseline 或 Diagnosis stale 时不得沿用旧依据；无历史数据时只允许生成显式标记为 LOW 置信度的实验假设。

## 输出

- 定位建议
- Audience 建议
- Content Pillars
- 各 Pillar 建议占比
- 主要问题
- 机会方向
- 第一阶段实验计划

每个 Content Pillar 应包含名称、说明、初始测试资源比例、证据等级、来源证据、实验目标和四周实验问题。总比例为 100%，仅代表测试资源分配。整体统计、Segment 指标、样本数、覆盖率、阈值、证据等级和置信度由代码确定；模型只整理文字，模型不可用时必须有安全的确定性回退。

## 原则

当前预设定位只是 Initial Hypothesis。

AI 必须优先读取真实诊断结果。

## 验收

- 抖音与小红书分别生成不同建议
- 推荐理由引用真实历史数据
- 分组样本 n≥5 才标记 SUPPORTED，n=3–4 标记 EXPERIMENTAL，n<3 不展示
- 不将历史相关性描述为因果；不补造受众人口统计
- Pillar 测试比例合计 100%，建议版本可回溯
- Baseline/Diagnosis 发生变化后旧建议标记 STALE
- 未确认策略的账号状态保持原值，operator_strategies 不被激活或覆盖
- 不直接自动激活 Strategy

---

# 10.5. Phase 5.1 - Strategy Evidence Strengthening

## 目标

补强真实历史作品中的主体和内容类型分类证据；重新生成 Baseline 与 Strategy Recommendation 版本。Phase 5.1 不进入 Phase 6。

## 执行约束

- 只针对 `subjects` / `content_type` 未分类作品重新请求 AI 建议；确认过的字段不得被重试覆盖。AI 仅看作品编辑文本，不接收 views / likes / comments 等表现数据。
- 先抽样审核至少 20 条建议。置信度低时不得自动确认；只对文本明确支持的字段人工或按高置信度批量确认。UNKNOWN 允许保留。
- 目标覆盖率：主体 ≥75%，内容类型 ≥70%。目标未达到时记录真实阻塞和剩余 UNKNOWN，不得猜测补齐。内容来源覆盖不构成阻塞，不生成 REAL vs AI 正式结论。
- 分类确认后更新 Diagnosis，再显式预览并生成 Baseline V3；总体样本仍为 canonical unique HistoricalPost。旧 Baseline / Strategy 保留历史版本。
- Segment n≥3 才展示，n=3–4 为初步描述，n≥5 才可正式比较。每组提供播放与互动率中位数及相对 Overall Baseline 的差异；不得解释为因果。
- 基于最新 Baseline V3、Diagnosis 和分类数据显式生成新 Strategy Recommendation 版本。比例必须通过确定性规则综合历史表现、样本量、互动表现、账号目标和探索价值；显示每个 Pillar 的“为什么”、主要数据依据和下一阶段验证问题。
- 如果分类质量门槛未满足，策略整体置信度必须为 LOW，并显示“历史内容分类仍不足，本策略主要作为测试方案”。不生成 Phase 6 确认、Topic Engine、每日 3 选 1 或内容。

## 验收

- 真实账号 UI 完成未知项建议、人工审核/确认、覆盖率、Diagnosis 更新、Baseline V3、分组差异和策略新版本。
- 人工检查主要主体和内容类型分组、每个 Pillar 的实际数据、比例来源、REAL/AI 结论约束与 LOW 置信提示。
- 运行 Python tests、前端 build/lint、`git diff --check`，并记录真实页面验收。完成后停在 Phase 5.1，单独等待 Phase 6 授权。

### 真实账号验收记录（2026-09-30）

- Qwen 实际返回 43 条作品的 58 项未分类字段建议。20 项抽样中，16 项 UNKNOWN 判断有文本依据，2 项部分支持，1 项正向分类证据不足，1 项无法判定；只通过 UI 人工确认明确有证据的建议。
- 最终覆盖：subjects 45/82（55%，低于 75% 目标）；content_type 62/82（76%，达到 70% 目标）；content_source 1/82（不作为阻塞，也未生成 REAL/AI Segment 结论）。主体不覆盖的项继续 UNKNOWN。
- Baseline V3 ACTIVE，82 条 canonical unique posts，播放 median 578.5；Diagnosis 重新生成后，真实页面重新生成 Strategy V5。V4 保留为 STALE。
- 策略测试资源比例：日常陪伴 36%、双猫互动 31%、趣味记录 33%；每个 Pillar 展示数据依据、描述性差异、比例计算因素和四周验证问题。整体置信度 LOW，主体分类覆盖不足；未开始 Phase 6。
- Python tests 424 passed / 6 skipped；前端 build 通过；lint 通过、2 条既有 warning；diff check 通过。

---

# 10.6. Phase 5.2 - Subject Evidence Completion

## 目标与约束

Phase 5.2 只补足出镜主体证据，不扩大内容来源、内容类型或 Hook 分类，不开始 Phase 6、Topic Engine、每日 3 选 1 或内容生成。

- 为分类服务增加 subjects-only 输入/结构化输出；文本证据不足必须 UNKNOWN，“其他”需有明确的非已知主体证据。AI 仅生成建议，不更新/覆盖内容来源、内容类型或人工标签。
- 历史分类 UI 增加主体未分类过滤、主体专属 AI 建议、多选快速设置缅因/布偶/双猫/其他，以及覆盖参考提示；批量接受只接受 subjects。
- Strategy Evidence Gate 同时检查主体覆盖率、缅因/布偶/双猫每组至少 5 条、内容类型覆盖/正式分组和 UNKNOWN bias。UNKNOWN 若可能改变主要分组比较，Confidence 保持 LOW 并显示不确定性提示；不为提升置信度降低标准。
- 确认 subjects 后重新诊断、建立下一版 Baseline、生成下一版 Strategy。Overall 与 Segment 统计从 canonical unique HistoricalPost 确定性计算；支柱说明须展示播放/互动表现、样本、证据等级、比例形成依据和下一阶段验证问题。双猫互动若播放低、互动高，须解释其作为账号 IP 相关实验方向的依据，不作因果推断。
- 验收记录主体覆盖、UNKNOWN 数、主要主体表现、Baseline/Strategy 版本、比例与 Confidence、与上一版策略差异、自动测试和真实 UI。不能可靠判断的项目继续 UNKNOWN；完成后停下等待 Phase 6 的单独授权。

---

# 11. Phase 6 - Strategy Confirmation

## 目标与进入规则

将用户确认的当前有效 Strategy Recommendation 转换为独立版本化的 ActiveStrategy 和 ACTIVE Content Pillars，并通过账号状态门禁正式激活业务账号。Strategy Confidence=LOW 不阻止进入第一阶段实验运营；LOW 必须留在页面和审计记录中，说明未来四周会继续验证。

进入确认流程需满足：

1. 有历史作品的账号有当前 ACTIVE Baseline 与 CURRENT Diagnosis；无历史数据的小红书账号可按 Profile 起步假设生成 LOW Strategy，无需伪造 Diagnosis/Baseline。
2. 至少有一条 CURRENT StrategyRecommendation，且依据未过期。
3. 主要 Pillars 有可读理由，策略明确为第一阶段实验。
4. 用户明确确认。LOW 不作为阻塞条件。

## 必须支持

- 查看建议定位、受众假设、分类未知数量、Confidence、Pillar 原因和只读历史数据依据。
- 编辑推荐定位、Pillar 名称、说明及未来四周的测试资源比例；不得编辑历史数据和证据。
- 实时合计比例；非 100% 时前端禁用确认，服务端拒绝无效请求。
- 确认前展示账号、策略版本 V1、测试周期、Pillar 数量/最终比例、Confidence、历史样本数和启用影响。
- 明确确认后原子创建 ActiveStrategy、ACTIVE ContentPillars、audit event，并将账号状态改为 ACTIVE。保留 Recommendation 原 JSON 和 ID，不覆盖、不改写。
- ActiveStrategy 至少保存 id/account/source recommendation/version/status/positioning/target audience/content pillars/experiment plan/confirmation confidence/confirmed_at/confirmed_by/created_at/updated_at。
- 每个 ContentPillar 保存 id、strategy_id、名称、说明、比例、目标、实验问题、证据摘要和 ACTIVE 状态。同一账号最多一个 ACTIVE Strategy。
- 确认成功显示四周实验计划：缅因高播放是否持续、双猫互动是否持续高于整体、趣味高播放/偏低互动是否稳定（有数据时同时观察涨粉）。不生成具体 Topic。
- 账号页显示 ACTIVE、Strategy V1、确认时间、四周周期和较低/相应 Confidence；确认后不可原位改比例。
- `require_active_account` 继续作为正式运营门禁；未确认账号仍被拒绝。XHS 无历史账号允许用户主动确认 Profile 假设作为起步实验策略。

## 验收

- Python tests 覆盖 LOW 确认、错误比例拒绝、用户修改持久化、Recommendation 不变、ActiveStrategy/Pillars 激活、Account ACTIVE、唯一 ACTIVE、门禁、版本、账号隔离、XHS 无历史、重启持久化及 Phase 5 回归。
- 真实抖音页面按“查看建议和证据 → 调整（可不改）→ 确认摘要 → 确认并启用”走完；检查 V7 保留、ActiveStrategy V1、三个 Pillars ACTIVE、比例合计 100%、LOW 提示、Account ACTIVE 且未创建 Topic/内容。
- 更新产品文档、执行计划和 CHANGELOG；Phase 6 验收后停止，不开始 Phase 7。

### Phase 6 真实账号验收结果（2026-10-01）

- 用户在真实 Douyin 页面查看 V7 及只读证据、确认 37/82（45%）主体 UNKNOWN、浏览确认摘要并明确启用。V7 保持 CURRENT，Baseline V4 仍为 82 条历史作品的有效基准。
- ActiveStrategy V1 状态 ACTIVE，Confidence=LOW，定位“缅因猫与布偶猫的双猫家庭内容方向（初始假设）”。Pillars：日常陪伴 36%、双猫互动 31%、趣味记录 33%；每组均保留历史证据摘要，合计 100%。业务账号状态为 ACTIVE。
- UI 展示四周验证问题：缅因历史较高播放能否持续；双猫互动能否持续获得高于整体基准的互动率；趣味内容较高播放、偏低互动是否稳定（有数据时观察涨粉）。V7 未被修改，确认及实验计划更正均有审计记录；更正仅修复持久化实验问题与已确认摘要不一致，不改变用户确认的比例或历史证据。
- 全量 Python tests：438 passed、6 skipped；前端 build 成功；lint 成功并保留两条既有 warning；`git diff --check` 通过。真实 UI 已核对 ACTIVE V1、V7、Pillar、LOW、UNKNOWN 和实验问题。未创建 Topic/内容，Phase 7 不在本轮范围。

---

# 12. R1 交付 Sprint 计划（替代 Phase 7–15 的逐 Phase 排期）

R1 的目标是交付真实账号运营闭环。原 Phase 编号保留为映射/历史语义；开发和验收以 R1 Sprint 为准。

## R1-A — Daily Topic Recommendation（本轮）

映射原 Phase 7 Topic Engine、Phase 8 TopicScore、Phase 9 Daily 3 选 1。

- 首页第一屏显示“今日运营”，每个 ACTIVE 账号每天保存 3 个候选、1 个主推；未 ACTIVE 的账号明确提示“尚未确认运营策略”，服务端阻止正式候选生成。
- 读取当前 ActiveStrategy、ACTIVE Content Pillars、四周实验问题、有效 Baseline/Segment、Diagnosis Top/Low、可用 Strategy Memory、Account Profile 和 AI 创意。不依赖实时热点；缺失的 Memory/历史数据使用空值，不编造。
- 抖音分数固定权重：策略匹配30、历史支持25、实验价值20、执行可行性15、新鲜度10。小红书固定：定位匹配30、受众价值25、真实经历20、IP价值15、可行性10。每个维度保存 0–100 规则分、权重、贡献和理由；Score 不表示成功概率。
- LLM 只生成标题、角度、可执行说明与轻量材料需求。代码拥有策略绑定、历史指标、实验问题、分项评分、总分和 Pillar 比例。模型失败时允许本地模板降级并明确标记来源。
- 七天内高度相似的 Topic 降低 Freshness；主推选择兼顾 TopicScore、重复控制和滚动周度 Pillar 资源平衡。换一批保留旧候选为 SKIPPED；选择操作保存 SELECTED 与审计事件。
- Douyin LOW 不阻止生成，但页面标为实验验证期。XHS 没有 Baseline 时只按已确认定位和真实项目经验假设生成，不显示/生成虚构的历史依据；没有 ActiveStrategy 必须保持门禁。
- Topic 至少持久化：id、account、strategy、pillar、title、angle、description、score/breakdown、recommendation_reason、historical_evidence、experiment_question、production_difficulty、material_requirements、status、generated_at，以及每日 batch/local_date/generation_mode。
- 真实验收两账号：抖音需三个可拍候选、一主推和真实 Baseline/Segment 依据；小红书需真实定位/项目经验约束和三选一，不伪造历史数据。无法满足 ACTIVE 条件时验证正确门禁，并由账号负责人先完成策略确认后再执行正式账号验收。
- 自动测试覆盖 ACTIVE/未 ACTIVE、3 候选/1 主推、固定权重、历史证据/无历史、小红书定位假设、Pillar 分配、七天重复降分、AI 不可用模板兜底、账号隔离、策略版本绑定、选择/换批和数据库重启持久化。

## R1-B — Content Generation（已实现）

映射原 Phase 10。只从用户明确选择的 Topic 进入内容草稿；未选择的候选或主推不得绕过用户进入生成。抖音生成脚本/镜头/字幕/标题等结构化短视频方案；XHS 生成 5 个标题、封面文字、结构、完整正文和配图/截图建议等结构化图文方案。草稿按平台分型并绑定 account、ActiveStrategy 版本和 Topic；重新生成保留版本，人工修改留审计记录。模型输出格式不全、包含虚构个人经历/量化保证或不安全宠物拍摄建议时，不保存；结构错误允许一次有界修复。页面提供审核与编辑；用户负责核实素材、拍摄与人工发布。

- 复用 Easel `ConfiguredAIService`、R1-A 当前 Dashboard 与已选 Topic；新增草稿服务、SQLite 持久化和 `/api/operator/accounts/{account_id}/topics/{topic_id}/content-draft` 读写入口。
- 账号需 ACTIVE；Topic 必须为同账号当前 ACTIVE Strategy 下明确 `SELECTED` 状态。策略变更后旧 Topic 不得继续生成内容。
- 不自动发布、不创建日历/发布记录/表现指标，不在此 Sprint 建素材库，不进入 R1-C/R1-D。
- 自动验证双平台字段结构、生成仅基于选中 Topic、账号隔离、策略绑定、版本与持久化、编辑审计、AI 失败和事实/安全边界；真实验收由用户选择 Topic 后完成真实模型生成与 UI 检查。

## R1-C — Content Calendar + Published Data（已实现）

合并原 Phase 12 与 Phase 13。用户可把当前已选择的 Topic/草稿放入账号隔离的月历，修改计划时间、标记待发布、取消及登记实际发布。发布记录与账号、策略版本和 Topic 绑定，并直接成为 R1-D 复盘数据源；24H/72H/7D 指标录入由 R1-D 管理。日历状态变化保留审计。不得调用自动发布、点赞、评论、关注、私信或平台发布 API。

## R1-D — Weekly Review + Strategy Feedback Loop（已实现）

合并原 Phase 14 与 Phase 15。Weekly Review 只能读取已记录的真实发布/指标并对照 Baseline；经用户审核确认后写入可追溯 Strategy Memory。下一轮 Topic 显示 Memory 如何影响推荐，不直接改写历史或用户确认的 Strategy。工程验收通过不代表已有真实运营样本；当账号尚未发布并补录数据时，真实复盘、Memory 审核和下一轮 Topic 联动仍待实际数据到来，不得使用测试样本冒充账号事实。

### R1-C / R1-D 工程验收记录（2026-10-01）

- SQLite schema 已升至 `user_version=16`。当前抖音宠物账号与小红书开发者账号的日历排期、发布记录、表现指标、Weekly Review 和 Strategy Memory 均为 0；真实账号没有写入合成发布或表现数据。
- 本机 `http://127.0.0.1:7873/` 已重启并真实打开“运营日历”与“周复盘”。日历显示当前账号、已选 Topic、月份网格和 0 条计划；周复盘显示 Baseline V4、0 条实际发布并禁用空数据复盘。
- 全量 Python tests：464 passed、6 skipped；前端 build 通过（主 chunk 超过 500 kB 有 Vite 提示）；lint 通过，有两条既有 warning；`git diff --check` 通过。
- 真实发布后的 24H/72H/7D 复盘、Memory 人工确认和后续 Topic 联动仍需真实运营数据；这属于运营样本验证，不代表 R1-C/R1-D 工程未完成。

## R1-RC — Release Candidate Integration & Acceptance（已完成集成验收）

本 Sprint 只做现有链路集成、阻塞修复、真实账号 UI 冒烟和发布准备，不新增产品范围。禁止自动发布、AI 视频理解、素材库、新平台、SaaS、多用户、支付、OpenAPI、浏览器采集和 V1.1 能力。

- 首页第一屏为“今日运营”，展示账号、当前策略、每日三选一、所选内容草稿入口、本周真实发布执行占比和当天日历计划状态。周度实际进度只读真实 PublishedPost，不得将生成/选择的 Topic 数当成发布量；其它 Easel 工作区收起到次级区域。
- 已选 Topic 的草稿页提供明确的“采用这个方案，安排发布时间”入口。日历计划绑定账号、策略、方向、Topic 和草稿；计划时间属于计划事实。只有用户登记真实发布时才生成 PublishedPost、实际时间、链接或平台作品 ID。
- 24H/72H/7D 未到时间时，界面显示“等待数据”，不写 0。真实发布记录可保存平台作品 ID；按账号去重，缺失 ID 保持 NULL。
- 周复盘只在当周至少 3 条真实发布作品已有实际指标时生成；否则显示“当前发布样本不足，暂无法形成有效周复盘。”统计数字由代码计算；现有 AIService 仅解释已计算的汇总事实，失败时保留确定性说明，不改变统计值。Memory 保持用户确认门槛。
- R1 集成测试以隔离 SQLite 和 mock AI 穿过 Account/Strategy→Topics→选择→草稿→Calendar→发布 fixture→Metrics→Review→用户接受经验→下一批选题。测试 fixture 不进入真实账号库。
- 真实抖音验收复用已存在的今日 AI Topic、用户已选择 Topic 和草稿，不生成重复候选；到日历计划阶段，不登记虚假发布。小红书无历史账号走定位实验模式，页面明确无历史表现数据。
- 对照 `docs/releases/R1_RELEASE_CHECKLIST.md` 分别记录代码验收与真实运营状态。版本准备 R1 / V1.0.0-rc1；Checklist 未全部满足前不得标记 V1.0.0。
- Vite 主 bundle >500 kB 和两条既有 lint warning 不做大规模重构，记录为 V1.1 技术债。

## 延期至 V1.1

原 Phase 11 素材库整体延期。R1 仅在 Topic 上显示 `material_requirements`，由用户自行准备素材；不开发上传库、缩略图、AI视频理解、抽帧、复杂素材匹配。

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
