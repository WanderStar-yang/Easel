# AI Social Operator V1 — Active Implementation Plan

- 状态：Phase 0、Phase 0.5、Phase 1、Phase 2、Phase 3、Phase 3.5、Phase 3.6、Phase 4 已完成；未开始 Phase 5
- 更新日期：2026-09-30
- 源码基线：Easel `main` at `0cab7ca6f6e8286635d25fe2435dda11a975ffec`
- 本计划依据：`../../AGENTS.md`、`../product-specs/AI_SOCIAL_OPERATOR_V1.md`、`PLANS.md`、`../audits/EASEL_V1_SOURCE_AUDIT.md` 及当前仓库源码
- 本轮边界：只执行 Phase 4 Account Baseline；不开始 Phase 5 Strategy Recommendation 或后续运营能力

## 1. 文档与路径核对

当前 Workspace 根目录是 Easel 仓库根目录。按用户给出的四个规范路径检查结果：

| 规范路径 | 结果 | 当前实际文件 / 处理 |
|---|---|---|
| `AGENTS.md` | 存在 | 仓库根目录项目规则 |
| `docs/product-specs/AI_SOCIAL_OPERATOR_V1.md` | 存在 | 产品规格 |
| `docs/exec-plans/PLANS.md` | 存在 | Phase 执行规则 |
| `docs/audits/EASEL_V1_SOURCE_AUDIT.md` | 存在 | 源码审计报告 |

四份基础文档均位于约定路径。Phase 0.5 将它们移动到规范目录，并修正本文档与其它 Markdown 中因移动产生的相对引用；没有复制文档。本文档头部来源链接相对于 `docs/exec-plans/` 解析，正文中 `docs/...` 引用均相对于仓库根目录。

## 2. 产品边界与源代码约束

- 首期只服务抖音宠物账号与小红书独立开发者账号；两者当前定位仍是 Hypothesis，只有经历史数据、诊断、建议和用户确认后才成为正式策略。
- Initial Diagnosis 与 Strategy Confirmation 未完成的账号不能生成正式每日建议。测试生成必须与正式建议区分。
- 用户最终选择选题、拍摄、剪辑、确认素材、人工发布并补录必要数据。V1 不得调用 Easel 的真实发布接口；也不开发自动互动、养号、多租户、商业化、通用策略/Prompt 配置器或首期外平台运营。
- Easel 已有能力优先复用：OpenClaw Agent/Skills、Profile 文件、`web/app.py` API 入口、React 页面、`calendar_ops.py`、`social_stats.py`、发布/分析记录脚本和 Outputs 管理。
- Easel 的 `/api/accounts` 是平台凭证/登录状态接口，不是 V1 业务 Account；V1 业务 API 必须采用独立路由，避免与其冲突。
- Agent 与现有网页 API 不提供 V1 业务账号隔离。每一项新业务读写都必须在服务端按 `accountId` 校验，不能只靠前端筛选。

## 3. 实施顺序相对 PLANS.md 的实际调整

`docs/exec-plans/PLANS.md` 是业务验收基线，Phase 1–15 的要求继续保留。本计划基于源码调整技术依赖，不删除验收项：

1. **将原 Phase 11（素材库）提前到 Phase 6 之后、Phase 7（Topic Engine）之前。** Phase 7 的 Topic 来源明确包含 Existing Materials，Phase 8 抖音评分中素材可执行性占 20%；素材若到 Phase 10 后才有结构化数据，会导致选题引擎和评分先依赖不存在的能力。编号保持不变，执行顺序为 `…Phase 6 → Phase 11 → Phase 7…`。
2. **Phase 1 区分业务 Account 与平台登录连接。** Easel 当前账号页和 `/api/accounts` 管理平台登录，业务模型另建，不覆盖原有接口。
3. **Phase 1 为新增业务实体设独立持久化边界。** 使用独立 SQLite 文件与 Python 标准库 `sqlite3`，不复用 OpenClaw Gateway 私有数据库，也不把 Account 状态散落进 Profile Markdown、`_schedule.json` 或 `_ideas.json`。SQLite 选择是基于 Easel 现有文件记录缺少跨对象约束、V1 模型存在稳定关系的实施建议；不增加 ORM 或第三方运行依赖。
4. **状态门禁放在服务端。** Strategy Confirmation 与 Active 状态必须由 API/service 校验，Dashboard 隐藏正式推荐只是表现层，不构成安全门禁。
5. **现有发布中心与 V1 发布人工步骤隔离。** Phase 1 不改发布脚本；后续接入 V1 日历/流程时不得回调 `/api/publish/{platform}`。
6. **补齐标准文档路径核验。** 当前规则、产品与 Phase 计划位于 `docs/` 平铺目录，且文件正文仍引用不存在的位置。这是文档问题，须在 Phase 1 开始前修正或明确映射；不改变产品需求语义。

### 建议执行顺序

`0 → 0.5 → 1 → 2 → 3 → 4 → 5 → 6 → 11 → 7 → 8 → 9 → 10 → 12 → 13 → 14 → 15`

Phase 11 提前只表示素材元数据/账号隔离和 UI 在选题工作流之前交付。它仍遵守产品范围：用户选择标签和描述，AI 只辅助摘要/匹配，不做复杂视频视觉识别。

## 4. Phase 1 计划卡：双账号基础模型

本节是 Phase 1 实际实施依据与执行记录。用户已明确授权 Phase 1；执行前重新读取了基础文档并检查源码、环境和工作区。Phase 1 已完成，Phase 2 尚未开始。

### 目标与需求

按产品规格 §3、§25–27 和 `docs/exec-plans/PLANS.md` Phase 1，建立两个独立业务账号、Profile/Strategy 关联、状态字段和服务端隔离；未 ACTIVE 的账号不得进入正式运营。

### 当前 Easel 模块与复用方式

- 复用 `profiles/` 的 Profile 文件机制和 `easel/persona.py` 的路径/读取逻辑；不把 Profile 文本当业务 Account 记录。
- 复用 `web/app.py` 的 FastAPI 应用注册与 `web/frontend/src/lib/api.ts` 请求封装模式，但业务端点另设 `/api/operator/accounts` 命名空间。
- 复用 `AccountsPage.tsx` 的现有界面样式时，明确区分业务账号与 Easel 的登录连接；不改变其旧 `/api/accounts` 语义。
- 复用现有 `pytest`、Vite build 与 oxlint 的项目质量体系。

### 预计新增文件

- `easel/social_operator/__init__.py`
- `easel/social_operator/models.py`：Account、AccountStatus、ProfileRef、StrategyRef 等最小业务类型与校验
- `easel/social_operator/repository.py`：独立 SQLite schema 初始化、版本迁移、原子事务与账号范围查询
- `easel/social_operator/service.py`：创建/读取/更新账号和服务端归属、状态转换规则
- `web/routers/operator_accounts.py`：V1 业务账号 API router
- `tests/test_social_operator_accounts.py`：实体、状态转换、API 与账号隔离测试

按计划新增独立 router；业务逻辑没有塞入 `web/app.py`。

### 预计修改文件

- `web/app.py`：只注册 V1 router/服务入口；不得改坏原平台登录 API。
- `web/frontend/src/lib/api.ts`：添加独立业务 Account 类型与请求。
- `web/frontend/src/components/AccountsPage.tsx`：展示/创建两个业务账号及其状态，和平台登录连接分区。
- `web/frontend/src/App.tsx` 或 Dashboard 相关组件：本 Phase 不需要修改；正式建议入口属于后续阶段，复用已实现的服务端 ACTIVE 门禁。
- `pyproject.toml`：预计无需新运行依赖；若包发现配置需调整，先证明必要性。

### 数据、API 与 UI 影响

- 新库：`outputs/_social_operator.sqlite3`，与 OpenClaw state、已有 Easel JSON 文件完全分离；通过 schema version 管理。Phase 1 不迁移日历、选题或发布日志，后续阶段逐项增加关联。
- Account 最小字段建议：`id`（稳定业务 ID）、`platform`、`display_name`、`profile_ref`、`strategy_ref`、`status`、`created_at`、`updated_at`。
- 首期允许平台限定为 `douyin` 与 `xiaohongshu`；同一平台最多一个 V1 运营账号。Profile/Strategy 未配置时状态不得进入 ACTIVE。
- 初始状态采用 `NEW`。合法状态转换按产品定义：`NEW → IMPORTING → DIAGNOSING → STRATEGY_PENDING_CONFIRMATION → ACTIVE → REVIEWING`。Phase 1 可以定义和验证状态机，但不得伪造后续阶段尚未完成的 Diagnosis/Confirmation。
- 业务 API：`GET /api/operator/accounts`、`POST /api/operator/accounts`、`GET /api/operator/accounts/{account_id}`、`PATCH /api/operator/accounts/{account_id}`。任何状态变更由 service 校验；Phase 1 不新增通用用户/租户权限层。
- UI 继续本地 Easel 页面风格；展示两个业务账号的身份、平台、Profile/Strategy 引用和生命周期状态。未 ACTIVE 时清楚呈现下一步需要诊断/确认，不能呈现正式每日推荐。

### 兼容性风险与处置

- 原 `/api/accounts` 已表示平台登录信息；路由独立并加测试，防止命名重叠或旧界面行为变化。
- 现有数据文件没有 Account ID，Phase 1 不做隐式归属推断、不迁移旧数据。后续迁移必须保留原记录并有回滚/备份方案。
- `profiles/` 与 Workspace 指令中的 `easel-profiles/` 表述不一致。通过 `easel.persona` 实际路径服务解析，新增代码不复制硬编码路径。
- SQLite 文件在 `outputs/` 下需加入删除保护；不得被内容库目录删除 API 暴露/删除。
- Profile 或 Strategy 引用应按账号独立校验，禁止一个账号更新另一个账号的记录。

### Phase 1 验收

- 可创建并列出恰好支持的抖音宠物与小红书开发者业务账号，重复平台/无效平台请求有明确响应。
- 账号、Profile 引用、Strategy 引用和状态相互独立；跨账号 ID 读写被拒绝或返回未找到，不泄漏数据。
- 服务端拒绝未满足诊断与策略确认条件的 ACTIVE 转换；正式每日建议 API/入口不能绕过状态门禁（即便推荐逻辑在后续 Phase 才实现，也须先提供可复用的门禁函数并测试）。
- 旧平台登录 `/api/accounts`、Easel Profile 读写和既有页面合同保持兼容。
- 完成针对测试、后端检查、前端 build/Lint、手动 UI 和 git diff 的 Phase 验收；结果如实汇报。未满足任一项则不进入 Phase 2。

## 5. Phase 0～15 实施计划

产品要求与原 `PLANS.md` 验收标准全部保留。下表采用建议执行顺序；原 Phase 编号保留，Phase 11 按上文提前。

| 执行序 | 原 Phase | 目标/主要产物 | 基于源码的实现边界 |
|---:|---|---|---|
| 1 | 1 双账号基础模型 | Account、Profile/Strategy 关联、状态与隔离 | 使用 `easel/social_operator/` 业务服务、独立数据仓库、V1 API router；不复用登录账户模型 |
| 2 | 2 历史数据导入 | 手工/CSV/XLSX 历史内容、校验和完整度 | 复用 `python-multipart`、上传/Outputs 与 pandas；新增 HistoricalPost 存储/API/UI；平台抓取不得成为前置依赖 |
| 3 | 3 Intelligence Engine / Initial Diagnosis | 逐帖/分组分析和可追溯诊断报告 | 复用 `skills/shared/scripts/social_stats.py` 与 `skill-account-diagnosis` 框架；结构化样本、来源与置信度由业务服务提供 |
| 3.5 | Douyin Official Export Import Compatibility | 官方导出 XLSX 识别、Preview → Confirm → Snapshot Reconciliation 与旧数据修复 | 复用 HistoricalPost、通用导入、诊断；移除扫描扩展/session/OpenAPI 占位流程 |
| 4 | 4 Account Baseline | 账号级历史中位数/分组基线 | 复用 `social_stats.py`；存储 sampleSize、日期范围和快照版本 |
| 5 | 5 Strategy Recommendation | 双账号独立定位、支柱、比例、实验建议 | 复用 `skill-strategy-advisor`/`skill-content-strategy` 的方法；定位仍为建议，不自动激活 |
| 6 | 6 Strategy Confirmation | 修改、确认/退回、激活 Strategy | 独立策略版本、确认人/时间和服务端状态转换；未确认不 ACTIVE |
| 7 | 11 素材库（前置） | Material、人工标签/描述、摘要/Topic 关联 | 复用 Outputs 上传/路径安全与缩略图；不做自动视觉视频理解 |
| 8 | 7 Topic Engine | 基于账号策略、Baseline、Memory、素材和可选趋势出题 | 复用 Ideas/Trends UI、相关 Skills；结构化 Topic 需要 accountId/source/pillar |
| 9 | 8 TopicScore | 双平台独立、可解释的维度分数 | 复用 `social_stats.weighted_score` 统计原语；权重按产品规格，不做运行时策略编辑器 |
| 10 | 9 Daily 3 选 1 | 每账号三候选、一主推 | 复用 Ideas 页面表现层；持久化候选批次和主推；ACTIVE 服务端门禁 |
| 11 | 10 Content Generation | 抖音脚本、小红书完整图文 Draft | 复用现有文案/脚本 Skills、Profile、Outputs 与内容安全；新增账号专用模板与 Draft 关联 |
| 12 | 12 Content Calendar | `IDEA→SELECTED→DRAFT→READY→PUBLISHED→REVIEWED` 跟踪 | 复用 `calendar_ops.py`/CalendarPage；增加 account/topic/draft/post 关联与迁移测试 |
| 13 | 13 Published Data | 人工登记发布与 24H/72H/7D 指标 | 参考 `skill-publish-log`、`skill-data-tracker`；禁止从 V1 流程调用 `/api/publish` |
| 14 | 14 Weekly Review | Baseline 对照、主题/支柱表现与建议 | 复用复盘 `review.py`/`social_stats.py`；输出绑定账号和实际记录 |
| 15 | 15 Strategy Feedback Loop | Review→经确认的 Memory→Topic 影响证据 | 复用 Profile memory 概念；保留来源 Review 与采用证据，不覆盖历史记录 |

## 6. 跨阶段技术决策

1. **业务数据不写入 OpenClaw 数据库。** 会话数据库归 Gateway 管理；V1 使用独立 SQLite 文件、schema 版本和服务层仓储。
2. **不在 Phase 1 做大迁移。** 现有 `_ideas.json`、`_schedule.json`、发布日志和指标继续由 Easel 旧功能管理。需要业务关联的阶段设计逐步迁移，并备份、可回滚、保留旧字段/数据。
3. **结构化事实与生成文本分开。** 历史指标、状态、评分、关系存业务库；长文案和成品文件可继续保存 `outputs/` 并用路径引用。
4. **LLM 结论需要证据。** Agent 使用服务生成的账号限定统计与源记录引用；缺失数据保留为空并显示数据完整度。
5. **账号假设不是已确认策略。** 初始宠物/开发者定位应标为假设，策略激活只由用户确认操作产生。

## 7. 阶段执行与停点

- 每个 Phase 启动时须输出该 Phase 的目标、产品章节、复用/修改/新增模块、数据/API/UI 影响、风险、测试与验收标准；检查当前工作区和未提交变更。
- 每个 Phase 只做本阶段工作。按项目文档要求运行适用的 build、lint、tests、手动验证，检查 git status/diff，更新必要的执行记录并报告问题。
- 每阶段验收后停止，等待用户人工确认再进入下一阶段。Phase 1 和 Phase 2 均按此规则停止；此计划不授权自动进入后续阶段。
- Phase 0.5 文档整理、Phase 1 双账号模型、Phase 2 历史数据管理均分别记录实际实现与验证结果。

## 8. Phase 1 执行记录与启动条件核验

### 启动条件

1. 四份基础文档均在规范路径并于 Phase 1 启动前重新读取：已满足。
2. 用户明确授权 Phase 1：已满足。
3. 源码、依赖管理、原有登录账号 API、Profile 机制、Outputs 删除路径及账号页均已复核；编码前已向用户汇报实施摘要：已满足。

### 实际实现与验证

- 按 `pyproject.toml` 使用 Python 3.12 隔离环境与 `pip install -e . pytest`；按前端 lockfile 执行 `npm ci`。未全局安装工具或修改依赖版本。
- 新增 `easel/social_operator/` SQLite 模型、仓储和服务、`web/routers/operator_accounts.py`、业务账号 API 类型与页面分区、Phase 1 测试。修改 `web/app.py` 注册 API 并保护业务库、Outputs 删除保护测试，以及本计划和 CHANGELOG。
- 新 SQLite 数据库包含 `operator_accounts`、`operator_profiles`、`operator_strategies` 三张表；启动时建立抖音宠物和小红书独立开发者业务账号。相关记录经 accountId 外键限定；Easel 平台登录账号模型保持独立。
- 服务端状态机验证合法迁移；无诊断完成与策略确认记录时不能进入 ACTIVE，并提供后续正式运营接口可复用的 `require_active_account` 门禁。
- `python -m pytest -v`：326 passed、6 skipped。前端 `npm run build`（包含 `tsc -b`）通过；`npm run lint` 通过，有两条 lint warning。项目没有独立的前端 test script。Phase 1 API、隔离、状态、持久化与 Outputs 保护测试通过。
- 本 Phase 未改发布脚本、发布 API、旧 `/api/accounts` 语义或 Dashboard；Phase 2 及之后尚未开始。

## 9. Phase 2 执行记录：历史数据导入

### 启动条件与边界

- Phase 2 开始前重新读取 `AGENTS.md`、产品规格、`PLANS.md`、本计划和源码审计，并检查 Phase 1 实现及工作区状态。
- 为 Phase 0 + Phase 1 建立 Git checkpoint：`d7f4980`（`Checkpoint social operator Phase 0 and 1`）。Phase 2 变更保留为未提交工作区改动。
- 仅完成 HistoricalPost 人工 CRUD、CSV/XLSX 预览与确认导入、字段校验、重复跳过、数据完整度和账号隔离；未实现 Initial Diagnosis、Baseline、策略建议或后续功能。

### 数据模型与服务

- 复用 `operator_accounts`、Phase 1 SQLite 数据库与仓储；新增 `historical_posts` 表并将 schema version 升至 2。
- HistoricalPost 字段：`id`、`account_id`、`platform`、`publish_time`、`title`、`content_type`、`content_source`、`tags`、`note`、`duration`、`subjects`、`hook_type`、`views`、`likes`、`comments`、`favorites`、`shares`、`followers_gain`、`profile_visits`、`inquiries`、`platform_post_id`、`created_at`、`updated_at`。历史指标可为空；互动计数不得为负数，涨粉允许负值。
- `easel/social_operator/historical.py` 负责规范化、校验、CRUD 和完整度；每次读写、删除和导入都由服务端限定 `account_id`。平台由业务账号确定，不接受客户端另行指定。
- 抖音与小红书共用结构；导入的 `exposure` 映射为 `views`，响应提供 `exposure` 别名。平台专属字段允许为空。
- 完整度按诊断可用数据加权：存在样本 20 分、发布时间覆盖 20 分、内容类型覆盖 20 分、播放/曝光覆盖 25 分、至少两类互动指标覆盖 15 分；覆盖率按账号内记录计算。Phase 3 可复用 `HistoricalPostService.completeness()`。

### API、导入与 UI

- 新增 `/api/operator/accounts/{account_id}/posts` 下的列表、创建、单条读取、更新、删除、完整度、`imports/preview` 和 `imports/confirm` API；字段错误返回 422，明确重复返回 409，跨账号单条查询返回 404。
- CSV 使用 pandas 读取 UTF-8 BOM 或 GB18030；XLSX 使用 pandas + `openpyxl`。`pyproject.toml` 增加 `openpyxl>=3.1,<4`，因为原隔离环境缺少 XLSX 引擎。限制 10 MB、5000 行；预览暂存内存 30 分钟，必须显式确认才写入数据库。
- 预览返回总行数、可导入/错误/重复数量、缺失字段及逐行校验结果。重复优先按账号范围 `platform_post_id`，否则按账号、平台、发布时间及忽略大小写和标题首尾空白的标题组合检测；重复标记并跳过，不覆盖。
- `AccountsPage.tsx` 的业务账号卡片新增历史内容入口；`HistoricalPostsPanel.tsx` 展示所选账号名、列表、人工表单、完整度及 CSV/XLSX 两步导入预览。未增加诊断、Dashboard 或每日运营页面。

### 测试与兼容性

- 新增 `tests/test_social_operator_historical_posts.py`，覆盖 CRUD、双账号隔离、CSV/XLSX、曝光别名、缺失字段、非法数字/日期、空文件、部分错误行、重复、预览隔离和确认、重启持久化及旧 `/api/accounts` 可用。
- 全量 Python Test：336 passed、6 skipped。前端 `npm run build`（含 TypeScript）通过；`npm run lint` 通过，保留两条现有 warning（`linkifyOutputs.ts` 转义字符和 `AccountsPage.tsx` hook 依赖）。项目没有独立前端测试脚本。
- Easel 登录、发布能力和旧 `/api/accounts` 接口未修改。Phase 2 提供了 Phase 3 所需的历史记录和完整度服务；开始 Phase 3 仍须用户明确确认，本计划不授权自动进入。

## 10. Phase 3 执行记录：Account Intelligence Engine / Initial Diagnosis

### 启动检查点与范围

- Phase 3 前完整重读了 `AGENTS.md`、产品规格、`PLANS.md`、本计划和源码审计，并检查 Phase 1/2 当前实现。
- Phase 2 独立 checkpoint：`76d12b4`（`Checkpoint social operator Phase 2 historical posts`）。Phase 3 修改与 checkpoint 分开，保留为工作区改动。
- 仅实现描述性 Initial Diagnosis 和可复用确定性 Intelligence Engine；未建立 Account Baseline、未生成正式 Strategy Recommendation/Content Pillars，也未启动 Topic Engine。
- 沿用既有状态枚举；首次诊断会按允许迁移将 `NEW → IMPORTING → DIAGNOSING`，成功后设置 `diagnosis_completed_at` 并保持 `DIAGNOSING`。报告自身标记 COMPLETED；不会新增 `DIAGNOSED`，不会进入 `STRATEGY_PENDING_CONFIRMATION` 或 `ACTIVE`。

### Intelligence Engine、数据与统计规则

- 新增 `easel/social_operator/intelligence.py`，复用 Easel `skills/shared/scripts/social_stats.py` 的中位数和互动率纯函数。统计逻辑不依赖 LLM；Initial Diagnosis 调用它，未来 Review 可重用确定性统计层。
- 新增结构化 `AccountDiagnosis` 记录和 SQLite `account_diagnoses` 表，schema version 升至 3。每条报告保存账号归属、报告 JSON、生成时间、算法版本；报告也保存 HistoricalPost ID/更新时间作为输入证据。诊断记录与 `diagnosis_completed_at` 在同一事务中持久化。
- 报告包含 overview、data quality、content distribution、metric summary、Top/Low、结构化 pattern findings、strengths、problems、opportunities、insufficient data、confidence、account/profile/strategy 上下文、证据 ID 与解释器状态。Strategy/Profile 仅作为上下文，明确 `used_as_conclusion_source=false`。
- 指标中位数只对非空值计算。抖音摘要包含 views、likes、comments、favorites、shares、followers gain；小红书还包含 profile visits、inquiries。小红书曝光字段沿用 Phase 2 映射的 views。
- 互动率逐帖按 `sum(available likes, comments, favorites, shares) / views` 计算；仅当 views > 0 且至少一个互动指标存在时计算。缺失互动项被省略并记录 partial 行数，不假装为 0。报告包含公式、单位和覆盖率。
- 抖音内容分布/比较涵盖 REAL/AI/MIXED、单猫/双猫/缅因/布偶组合、content type、Hook、时长区间、发布时间时段；小红书涵盖 content type 及其 views、收藏、互动、涨粉、主页访问、咨询等指标。比较每组至少 2 条才生成，Finding 保存分组样本数、指标中位数、差异、置信度和来源作品 ID；只有 1 条的分组列为不足项。
- 排名依据明确：抖音按 views；小红书有收藏数据时按 favorites，无收藏数据则按 views。缺排名指标的记录不参与排序。小红书收藏/曝光信号至少需 3 条双指标样本；主页访问/咨询仅作为后续分析输入。
- Overall Confidence 规则：HIGH 要求样本 ≥20、Phase 2 完整度 ≥80、所需指标平均覆盖率 ≥70%；MEDIUM 要求样本 ≥8、完整度 ≥50、指标覆盖率 ≥40%；其余 LOW。分组置信度还会按较小组样本数下调（HIGH ≥15、MEDIUM ≥5，否则 LOW）。规则以 `confidence_rules` 返回。

### API、LLM 与 UI

- 新增 `/api/operator/accounts/{account_id}/diagnosis` 的 POST 运行、GET 最新结果，以及 `/history` 查询；所有请求先校验业务 Account，并按 account_id 查询和保存。0 条作品返回 `INSUFFICIENT_DATA`，不写报告、不推进状态。
- `OpenClawDiagnosisExplainer` 复用 Easel 已有 OpenClaw Gateway Chat Completions，不新增 Model Provider。LLM 仅收到已经计算的结构化证据，单独返回 `ai_explanation`；统计、排行、发现和置信度由代码保存，不由 LLM 覆写。Gateway/模型不可用时解释状态为 unavailable，规则摘要、统计和持久化诊断仍正常完成。
- `AccountDiagnosisPanel.tsx` 从业务账号卡片进入，显示账号、状态、作品数、完整度、置信度、关键指标、内容分布、Top/Low 排名依据、模式证据、优势/问题/可验证机会和数据不足项；没有策略确认控件。

### 测试与 Phase 4 前置条件

- 新增 `tests/test_social_operator_diagnosis.py`：覆盖两平台、双账号隔离、0/1/2 条小样本、完整样本、部分缺失指标、Median、互动率公式、REAL/AI 与 content type 比较、Top/Low、置信度、低完整度、重启持久化、无解释模型降级、账号状态和 API；并验证 Phase 2 历史 API 与旧 Easel `/api/accounts` 仍可用。
- 全量 Python Test：348 passed、6 skipped。`npm run build` 通过；诊断面板按需拆分为独立 chunk，主 chunk 低于 500 kB。`npm run lint` 通过，有两条既有 warning。`git diff --check` 和 Python compile 检查通过。无独立前端测试脚本。
- Phase 3 输出具备进入 Phase 4 所需的真实历史统计和诊断证据；Baseline 不在本轮实现。Phase 4 仍等待用户确认，本记录不授权继续。

## 11. Phase 3.5 执行记录：Douyin Official Export Import Compatibility

### 方向调整

- 用户通过真实使用确认 PC 端抖音创作者中心支持直接导出作品列表 XLSX。V1 数据源因此调整为官方文件导入，不再依赖 DOM/浏览器扫描。
- 变更前已提交当前工作区检查点：`85518e3 Checkpoint before Douyin export import refactor`。该检查点保留在 Git 历史中，可用于回看重构前状态。
- 本轮仅重整 Phase 3.5；不新增 Account Baseline、Topic Engine 或其他 Phase 4+ 能力。

### 当前实现方案

- `DouyinCreatorExportParser` 通过平台特征表头识别官方 XLSX，映射标题、作品 ID、发布时间、体裁原文和播放/互动指标；未知列仅列入预览说明。
- 每份官方 XLSX 先生成快照预览。以平台作品 ID 为主键；无 ID 时用规范化发布时间+标题；缺少稳定键时显示低置信度提示且不推断数据库作品缺失。确认后按非空事实更新、空值保留、真实 0 覆盖的规则写入 HistoricalPost。
- SQLite 为 HistoricalPost 增加 `content_type_raw`；`data_source` 使用 `DOUYIN_OFFICIAL_EXPORT`。确认快照包含新增或更新作品时旧诊断转为 `STALE`；修复合并重复记录同样会过期诊断。
- 历史重复修复预览显示估算唯一作品、可自动合并及需人工确认记录；只自动处理可稳定匹配的组，并保留 Canonical ID、合并非空字段、按最新来源观测刷新动态指标及重映射诊断引用。
- 抖音历史页主操作变更为「导入抖音作品数据」，说明先从 PC 创作者中心导出；通用 CSV/XLSX 和手工录入作为辅助能力保留。
- 清理 Social Operator 专属扩展目录、DOM 扫描脚本、同步会话服务/API、扩展 CORS 放行、扫描向导和 OpenAPI 占位 UI。Easel 原有平台登录与发布、通用 HistoricalPost/导入、人工录入、Initial Diagnosis 保留。

### 验收与停点

- 使用与用户提供的真实抖音导出格式一致的 XLSX regression fixture 验证表头识别、指标映射、体裁原文、未知列、数字/日期和空值行为；另对用户提供的真实文件执行只读预览，82 条全部可识别、0 错误，6 个未知指标列在预览中说明。
- 回归重复上传、第二次指标更新、零值覆盖、null 保留、Diagnosis stale、账号隔离、重复修复预览及旧浏览器代码不存在。
- 最终全量 Python 测试：363 passed、6 skipped。`npm run build` 通过；`npm run lint` 通过并保留两条既有 warning（`linkifyOutputs.ts` 无用转义、`AccountsPage.tsx` hook 依赖）。`git diff --check` 通过。
- Phase 4 尚未开始。解析、重复更新、诊断 stale、双账号隔离、重复修复和旧同步代码移除均有自动化验证；Phase 3.5 完成后具备提交 Phase 4 评估的技术前置，但是否开始仍等待用户确认。

## 12. Phase 3.6 执行记录：Diagnosis UX & Data Integrity

### 实际根因与数据修复

- 当前数据库曾有 284 条抖音记录：82 条官方 XLSX、202 条旧浏览器扫描记录。旧数据的作品 ID 与发布时间缺失，且标题夹带创作者中心按钮文案；其扫描结果与后续诊断直接读取原始行的做法造成总量及 Top/Low 重复。
- 官方 82 条标题在规范化空白、剥离旧扫描按钮文案后均唯一，并能覆盖匹配全部 202 条旧扫描记录。修复预览据此把 82 条官方作品保留为 canonical，归档 202 条旧记录，0 条待人工确认。官方 XLSX 指标优先，旧扫描值不覆盖其非空事实；归档保留原始载荷。
- Repair 清理了归档旧扫描数据中的 102 个标题控件后缀；官方 XLSX canonical 标题保持原样，修复后有效作品标题没有控件文案。
- 修复后 SQLite 当前作品为 82 条，归档 202 条；重新运行诊断的有效唯一作品数与样本数均为 82。Top 与 Low 各 5 条且 ID 唯一。当前抖音 Top/Low 标题无创作者中心控件污染。
- 旧诊断正文曾是在导入官方 XLSX 前生成，导入后已有 stale 标记；新版页面对过期报告默认收起并提供“重新诊断”。

### 数据、统计、服务与 UI

- 新增 `canonical.py`：按 platform_post_id 或发布时间+清洗后标题构造稳定身份；统计前排除最新完整快照已标记缺失的记录并去重。无稳定身份的记录不会只凭普通标题静默合并。
- 历史列表和完整度使用有效唯一作品；报告分别保存原始行数、有效唯一作品数、诊断样本数、排除的过期快照数、疑似重复数及归档旧扫描数。
- Overview、优势、问题、机会、数据不足和可信度说明由结构化统计规则生成。LLM 解释保留在技术详情，不决定普通用户看到的事实。未标注 Hook 表示“Hook 信息未分析”，UNKNOWN、缺失时长与数值 0 分开处理。
- 重排 Diagnosis 首页为一句话诊断、账号基准表现、Top/Low、当前发现、数据不足、下一步建议；旧诊断折叠，计算公式与 raw 字段移入详情。
- 新增账号范围内的批量分类 API `PATCH /api/operator/accounts/{account_id}/posts/batch-classify`，支持 REAL/AI/MIXED、subjects、content_type；历史页提供多选分类入口，更新后使旧诊断过期。

### 验收与停点

- 新增 `tests/test_social_operator_diagnosis_ux.py`，覆盖唯一视图、Top/Low 去重、stale 语义、Hook/时长缺失、标题清洗、原始/有效数量、可信度文案、数据缺口、无 LLM 和 LLM 事实分离、批量分类账号隔离及 82+202 记录修复后诊断。
- 当前全量 Python 测试：374 passed、6 skipped；前端 `npm run build` 通过；Lint 通过，保留两条既有 warning；无独立前端测试脚本。
- 真实数据库完成 Repair 与重诊断：82 条有效作品，202 条旧记录归档。通过重启后的真实应用和用户已打开的 Chrome Easel 标签验收：82 条、80%完整度、可信度“中等”、Top/Low 各 5 条、旧文案无污染；普通页面未显示 UNKNOWN / content_source / threshold 等内部字段。手动标记过期后，页面显示“历史数据已更新，当前诊断已过期”，旧报告折叠，重新诊断后恢复最新正文。历史页批量分类入口也已在真实 UI 看到；批量接口通过账号隔离测试。
- Phase 4 未开始。Baseline、Strategy Recommendation 等后续能力仍等待单独确认。

## 13. Phase 4 执行记录：Account Baseline

### 启动检查与范围

- 开始前重新完整读取 `AGENTS.md`、产品规格、`PLANS.md`、本计划和源码审计；核对 Phase 1–3.6 实现及 `git status` / `git diff`。
- Phase 3.6 独立 checkpoint：`79e6f43`（`Checkpoint social operator Phase 3.6 diagnosis UX and data integrity`）。Phase 4 改动单独保留在工作区。
- 本轮只实现历史基准、显式预览/建立/重生成、版本追踪、陈旧标记、展示和比较服务接口；不开始 Phase 5 Strategy Recommendation、Phase 6 Strategy Confirmation、Topic Engine、每日 3 选 1 或内容生成。

### 数据模型与计算

- 新增 SQLite `account_baselines`（schema version 9），保存 id、account_id、version、sample_size、period_start/end、generated_at、source_updated_at、historical_data_version、ACTIVE/STALE 状态及完整指标/分组快照。唯一部分索引确保每账号最多一个 ACTIVE 版本。
- 计算输入为 Phase 3.6 `canonical_unique_posts()` 输出。活动唯一作品作为 sample_size；稳定键重复记录只取 canonical 行，`source_presence=MISSING` 与归档记录排除。整体计算不要求已有内容分类。
- 指标采用 Median；另外保存 nearest-rank P25/P75、样本数、coverage。互动率逐帖沿用 `available interactions / views`：只累加非空互动字段，views 必须大于 0，真实 0 保留，missing 不补 0；账号中位数只取有效逐帖率。
- 字段范围包含播放、点赞、评论、收藏、分享、互动率、涨粉、主页访问和咨询。官方 XLSX parser 当前未映射完播率、2 秒跳出率、平均播放时长，这三项保存 null/0 样本并列入 TODO；没有把作品长度当作平均观看时长。
- 分组支持 content_source、content_type、subjects、hook_type、duration_bucket、publish_period。未知/未分类不创建分组；样本 ≥3 展示初步基准，≥5 标记为可供未来正式比较。
- 每账号首次生成 V1，重生成递增版本；历史版本保留。历史数据变更入口沿用仓储统一 stale helper，新增、更新、分类、删除、重复修复、快照对账都会令 ACTIVE Baseline 变为 STALE；GET 同时校验历史数据版本以发现遗漏变更。
- `compare_to_baseline()` 为未来的新发布指标提供 views、likes、engagement_rate 相对中位数和 P25/P75 区间能力。此处不生成 Weekly Review。

### API 与 UI

- 新增 `/api/operator/accounts/{account_id}/baseline`（当前版本/显式生成）、`/preview`、`/history` 和 `/compare`，所有访问均按 account_id 隔离。
- Diagnosis 有效时展示“建立历史基准”；已建立时展示“查看历史基准”；数据变动后显示 stale 提示及重新生成入口。建立前 UI 展示作品数、时间范围、播放/互动率/分类覆盖，必须点击确认后持久化。
- 普通用户页面说明 Baseline 用途，展示典型中位数、每项样本与覆盖率、P25/P75、分类基准及未完成分类入口；不显示 UNKNOWN/未分类基准。

### 自动测试与验收

- 新增 `tests/test_social_operator_baseline.py`，覆盖 canonical 去重、重复行忽略、Median/P25/P75、极端值、missing/zero、互动率和 views=0 排除、覆盖率、整体无分类可建、分组门槛、版本 1/2、单 ACTIVE、stale（新增/修改/分类/删除/Repair）、账号隔离、比较接口、重启持久化、过期 Diagnosis 门禁和 API 预览确认。
- 真实抖音账号 UI 验收使用独立端口运行当前版本，未中断用户原有 7860 实例。真实数据库为 82 条活动作品、0 条 MISSING；预览并确认生成 V1。周期 2025-06-24～2026-09-28；播放覆盖 82/82；互动率覆盖 82/82；内容类型覆盖 0%。
- 真实 Baseline：播放中位数 578.5（P25 308，P75 988）；点赞 8；评论 0.5；收藏 0；分享 1；互动率 2.02%；涨粉 0；主页访问 3；咨询为空。播放中位数与 Diagnosis 一致；692,689 播放作品保留在历史样本，但没有扭曲中位数。未分类字段未生成 UNKNOWN 分组；发布时间段因真实发布时间存在，作为独立维度生成分组。
- UI 实际确认后 SQLite 已保存 ACTIVE Baseline V1，sample_size 82；服务重启持久化由自动化测试覆盖。完播率、2 秒跳出率和平均播放时长仍是解析 TODO。
- 最终 `.venv/bin/python -m pytest -q`：388 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning；前端 `npm run build` 通过；`npm run lint` 通过，保留两条既有 warning（`linkifyOutputs.ts` 无用转义、`AccountsPage.tsx` Hook 依赖）；`git diff --check` 通过。
- 真实 UI 已重新载入验证 Diagnosis 显示“历史基准已建立”与“查看历史基准”。Phase 4 验收项通过；Phase 5 未开始，等待用户确认。
