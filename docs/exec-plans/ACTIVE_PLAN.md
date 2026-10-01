# AI Social Operator V1 — Active Implementation Plan

- 状态：Phase 0～6、R1-A～R1-D 工程实现已完成；R1-RC 集成、自动检查和两平台真实 UI 冒烟已完成。真实发布及平台表现闭环仍待账号实际运营数据，不得伪造。
- 更新日期：2026-10-01
- 源码基线：Easel `main` at `0cab7ca6f6e8286635d25fe2435dda11a975ffec`
- 本计划依据：`../../AGENTS.md`、`../product-specs/AI_SOCIAL_OPERATOR_V1.md`、`PLANS.md`、`../audits/EASEL_V1_SOURCE_AUDIT.md` 及当前仓库源码
- 本轮边界：R1-RC 集成、修复、真实账号 UI 验收和发布候选准备已完成；不自动发布、不增加范围外能力、不开始后续 Phase。

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

## 14. Phase 4.5 执行记录：Historical Content Enrichment

### 启动检查与 checkpoint

- 开始前重新检查了 Phase 4 的 `git status`、完整 `git diff` 和缓存差异；Phase 4 实现、文档和测试均在独立工作区改动中，没有 Phase 5 内容。
- Phase 4 独立 checkpoint：`3646ba8`（`Checkpoint social operator Phase 4 account baseline`）。Phase 4.5 改动尚未提交。
- 本轮范围只包括三个历史分类字段、AI 文本建议、用户确认、覆盖率、Segment Baseline 更新；Hook 保持未分析。

### 已实现

- 新增 `historical_post_classification_metadata`，按作品/字段保留 `value_json`、来源（IMPORT / AI_CONFIRMED / MANUAL_CONFIRMED）、confidence 和 confirmed_at；新增独立 `historical_post_classification_suggestions` 保存 SUGGESTED/CONFIRMED 建议。
- 新增 `HistoricalClassificationService` 和 Easel OpenClaw 网关适配。Prompt 只传作品标题、原始作品类型、已有 tags、描述/备注，不传播放、点赞或其他表现字段。输出受控于固定枚举；无效/缺失字段回退 UNKNOWN/LOW。
- AI 建议与最终标签分离；仅接受时更新 HistoricalPost，MANUAL_CONFIRMED 字段不被 AI 覆盖。人工批量标签限制在 V1 内容类型/主体枚举。
- 新增分类建议/进度/行项目 API。历史页面改为批量审核表格，提供全部、未分类、低置信度、AI 建议过滤；按三个字段展示 AI 置信度；支持批量人工设置、接受所选建议和有确认数量提示的全部接受高置信度建议。
- 分类确认复用仓储的数据变更 stale 标记，使 AccountBaseline stale；重新运行 Diagnosis 后可按现有 Baseline 确认流程生成 V2，并由 Phase 4 规则生成 REAL/AI、主体和内容类型分组。
- 测试覆盖 AI 输入不含表现指标、UNKNOWN fallback、置信度规范、人工优先、批量分类元数据、未分类/低置信度/建议结果、全部接受高置信度、账号隔离、进度、Baseline stale/V2/分组和 Phase 4 Overall Median 回归。

### 尚待验收 / 当前环境限制

- 自动测试：398 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning；前端 `npm run build` 通过；`npm run lint` 通过，保留两条既有 warning；`git diff --check` 通过。
- 在独立端口 7871 的真实 UI 中打开当前账号批量分类页，确认有效作品 82 条、三类覆盖均为 0%，表格显示标题/播放/标签/置信度列；点击 AI 预分类后页面正确显示模型网关不可用提示。没有写入 AI 结果或改动用户作品。
- 真实账号仍为 82 条 canonical unique 作品，当前 V1 分类覆盖为 0%。因本机模型网关不可用，真实 AI 预分类尚未运行，因此未抽查 20 条、未做人工校正/批量确认，也未生成 Baseline V2。
- 当前机器没有 `openclaw` 可执行文件、Easel `easel` profile 配置或可用模型网关。`scripts/gateway.sh status` 显示 profile easel / port 37289 未运行；尝试 `start` 后日志为 `openclaw: No such file or directory`。应用的 AI 预分类 API 已实现并能在网关恢复后调用，但不能把测试替身或 UNKNOWN 默认值冒充真实分类结果。
- 因上述限制，Phase 4.5 代码和自动测试可验收，真实 AI/账号闭环验收未完成。Phase 5 未开始。

## 15. Phase 4.5.1 执行记录：Model Provider / AI Classification Runtime Fix

### 源码确认的根因

- 原 `OpenClawHistoricalClassifier` 在分类业务模块内直接请求 Easel Gateway health 与 Chat Completions URL，并硬编码 `openclaw/default`；因此即使 `.env` 已存在 API 兼容模型配置，分类仍完全依赖 Gateway。
- Easel 的模型配置由现有 `.env` 与 Web「设置 → 模型配置」管理；当前槽位包含 OpenAI-compatible (`OPENAI_*`)、Anthropic-compatible (`EASEL_LLM_*`) 和 Anthropic (`ANTHROPIC_API_KEY`)，模型连通性自测在 `web/app.py`。当前核心聊天/Agent 同时依赖 OpenClaw；项目 `setup.sh` / `setup.ps1` 安装 `openclaw@latest`，`easel doctor` 也将其列为 Easel 运行环境依赖。因此 OpenClaw 对整个 Easel Agent 工作流是项目依赖，但它不是历史分类功能唯一可用的模型 API。
- 修复复用仓库已有 `httpx` 运行依赖和模型设置，不另加 AI SDK，不做全局安装。

### 已实现

- 新增 provider-neutral `easel/ai_service.py`，集中解析已有 `.env` 模型配置、发起 Chat Completions / Anthropic-compatible 请求，并将 Gateway 留作可选回退。分类模块只依赖 AIService 抽象，不直接知道厂商或 Gateway 路径。
- 新增分类 Runtime 状态接口与页面状态提示：AVAILABLE / NOT_CONFIGURED / UNAVAILABLE / ERROR；模型未配置或不可用时提供现有模型设置入口，手动批量分类仍然可用。
- 保持每批最多 20 条和作品编辑信息白名单；模型响应按 post_id 独立验证，单条损坏不丢弃同批其它有效建议，批次错误不会中止后续批次。
- 测试覆盖无配置、兼容 Provider 请求路径、模型状态、字段白名单、每批 20 条、逐条失败以及后续批次继续。

### 验证与限制

- 全量 `.venv/bin/python -m pytest -q`：407 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning。前端 `npm run build` 通过；`npm run lint` 通过并保留两条既有 warning；`git diff --check` 通过。
- 用户已在 Easel 现有 Chat 模型设置中保存 Qwen OpenAI-compatible Provider（界面模型名为 Qwen3.7-Plus）。密钥保存在被 Git 忽略的本机 `.env`；提交内容不包含 `.env` 或真实密钥。
- 用户提供的工作空间专属 Base URL 符合阿里云文档格式。用户关闭 VPN 时截图显示“模型请求…”错误，但 HTTP 状态码被界面列宽截断；之后的本机探测发生在用户重新打开 VPN 后，DNS/SSRF 拦截结果不能解释此前截图。本次改动为模型自测失败状态增加完整悬停详情，待在目标网络状态下复测并记录 HTTP 状态码。
- 当前证据不足以确认模型连接成功。真实 AI 预分类、20 条抽样质量统计、人工审核/确认、分类覆盖率以及 Baseline V2/Segment Baseline 均尚未完成。Phase 5 未开始。

## 16. Phase 4.5 真实验收工作计划

本节是当前待执行清单。必须按顺序完成并记录结果；模型连接失败时停止后续真实分类，不用测试替身代替真实结果。

1. **确认 Provider 连通**：在用户指定的目标网络状态下重试 Easel「测试连接」，读取完整错误详情；核对工作空间专属 Base URL、模型 ID 与同一工作空间的 API Key。确认实际 Chat Completion 成功后才进入下一步。
2. **20 条抽样**：从 82 条 canonical unique 历史作品中抽取至少 20 条；检查标题、AI 三字段建议和各字段 confidence，统计完全正确、部分正确、明显错误、无法判断。若明显错误率不可接受，先调整保守 Prompt 并重新抽样。
3. **其余作品建议**：抽样达到可接受水平后，按每批不超过 20 条完成其余作品建议。逐字段保留 SUGGESTED，人工确认优先；记录内容来源、出镜主体、内容类型各自的 AI 建议数、人工确认数和 UNKNOWN 数，不为追求覆盖强行分类。
4. **人工审核与确认**：在真实页面过滤 AI 建议、低置信度和未分类作品，人工修正后确认；批量接受前检查界面显示的作品/字段数量。确认后核对 V1 Baseline 已变为 STALE。
5. **Baseline V2**：按既有流程更新 Diagnosis 并显式预览、生成 V2。确认 sample_size 仍基于 82 条有效唯一作品、Overall Median 与 V1 基本一致；记录 REAL/AI、缅因/布偶/双猫和 content_type 分组，样本 <3 不展示，3–4 仅初步展示，≥5 标记可供后续比较。
6. **收尾验收**：运行 Python tests、前端 build/lint、`git diff --check`；完成真实 UI 流程检查并更新本计划与 CHANGELOG。只汇报 Phase 4.5 是否满足进入 Phase 5 的条件，等待用户确认，不开始 Phase 5。

## 17. Phase 4.5 真实验收完成记录

### 模型调用与真实分类

- Easel 设置页配置的 Qwen OpenAI-compatible Provider 在当前 VPN/系统代理网络下完成真实 Chat Completion 自测（约 2312 ms）；使用现有 AIService 与 `.env` 本地密钥，不安装 OpenClaw、不增加 AI SDK。历史分类调用成功，OpenClaw 不在该调用链上。
- 从当前抖音账号 82 条 canonical unique HistoricalPost 随机抽查 20 条。标题证据复核为 19 条支持建议、1 条建议过度推断（部分正确），无结构化调用失败；收紧 Prompt 后该条已重新建议为 UNKNOWN。完整分类中又发现两条仅带 `#ai`/剪映的标题被猜成 AI 来源，收紧规则并重跑后改为 UNKNOWN/LOW。Prompt 现在要求明确的“AI生成/AI视频/AI创作”证据；两只猫互动也要求标题明确显示双猫和互动，证据不足保留 UNKNOWN。
- 82 条均有每字段 AI 建议（共 246 条字段建议），逐批完成；失败的 5 条通过增量重试成功。模型仅接收作品 ID、标题、原始作品类型、标签和描述；请求不包含播放或互动指标。
- 用户在真实 UI 确认高置信度建议：46 条作品、64 个字段。另人工确认标题明确提及“兄妹俩”和“抢你哥的”两条为双猫及双猫互动。最终 metadata：内容来源 AI_CONFIRMED 1；主体 AI_CONFIRMED 38、MANUAL_CONFIRMED 2；内容类型 AI_CONFIRMED 25、MANUAL_CONFIRMED 2。保守 UNKNOWN 建议分别为来源 81、主体 42、内容类型 19；其余中低置信度建议保留待后续人工审阅，没有强行确认。
- 最终字段覆盖：来源 1/82（1%），主体 40/82（49%），内容类型 27/82（33%）。AI 来源目前只有 1 条明确作品，REAL/MIXED 无足够文本证据；没有生成虚假的来源 Segment Baseline。

### Diagnosis 与 Baseline V2

- 人工/AI 确认分类使 Diagnosis 与 Baseline V1 stale。经真实 UI 重新运行 Diagnosis 后状态为 CURRENT，再通过明确预览确认生成 Baseline V2；V1 保留为 STALE 历史版本，V2 为唯一 ACTIVE 版本。
- V2 使用 82 条 canonical unique 作品，时间范围 2025-06-24～2026-09-28。Overall 与 V1 相同：播放中位数 578.5（P25 308/P75 988），点赞 8，评论 0.5，收藏 0，分享 1，互动率 2.02%（P25 1.27%/P75 2.87%）；各指标样本数、覆盖率保留。692,689 播放真实作品未剔除，Median 保持稳健。完播率、2 秒跳出率、平均播放时长均为 null/0 样本，因为当前官方 XLSX parser 没有可靠映射字段。
- Segment Baseline：主体双猫 n=8（播放 median 625.5、互动率 2.34%）、布偶 n=15（742、1.78%）、缅因 n=16（977.5、2.29%）；内容类型单猫日常 n=11（486、1.78%）、搞笑/趣味 n=9（539、1.60%）可供未来正式比较，双猫互动 n=3（491、2.58%）与情绪/陪伴 n=3（780、3.94%）只作初步基准。其余标签样本不足不展示；REAL/AI 组不满足 n≥3。以上仅为历史表现，不代表因果或策略结论。

### 验收与停点

- 真实 UI 完成设置模型/连通、82 条批量预分类、查看建议、人工确认、覆盖进度、Baseline 预览确认、V2 与分组查看。页面显示普通用户可读的“账号历史基准”说明；未分类标签不显示 UNKNOWN 分组。
- 最终 `.venv/bin/python -m pytest -q`：411 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning；前端 `npm run build` 通过；`npm run lint` 通过并保留两条既有 warning（linkifyOutputs.ts 无用转义、AccountsPage.tsx Hook 依赖）；`git diff --check` 通过。
- 已用 SQLite online backup API 创建 `backups/social_operator_2026-09-30_phase4-5.sqlite3`，完整性检查为 `ok`；快照含 82 条活动唯一作品、202 条归档旧记录、82 条建议、确认分类元数据、V1 STALE 和 V2 ACTIVE。旧的同日快照保留为分类前状态。
- Phase 4.5 闭环已通过；不自动开始 Phase 5，等待用户确认。

## 18. Phase 5 执行记录：Strategy Recommendation

### 本轮范围与实现

- 本轮只完成 Strategy Recommendation；未实现策略确认、ACTIVE 策略切换、Topic Engine、每日 3 选 1、内容生成或 Weekly Review。
- 新增 `strategy_recommendations` SQLite 表和 account-scoped latest/history/generate API。按账号递增版本，引用 Baseline、Diagnosis 与 Profile 快照；数据依据或 Profile 变动后 latest 会标记 STALE。生成新版本不覆盖旧记录。
- `StrategyRecommendationService` 读取 AccountBaseline 服务提供的 ACTIVE canonical 唯一数据快照和当前 Diagnosis。Baseline / Diagnosis stale 时拒绝生成；没有历史作品的账号允许仅基于现有 Profile Hypothesis 生成 LOW 置信度假设。
- 服务端计算证据组；样本 n≥5 为 SUPPORTED，n=3–4 为 EXPERIMENTAL，n<3 不纳入证据。空来源分组不展示；来源分类稀少不会阻止整体建议，但会将整体置信度压为 LOW。显示播放和互动率中位数及 P25/P75。
- 内容 Pillar 说明、目标、实验问题、比例、证据等级和证据引用由确定性逻辑生成。已配置 Qwen3.7-Plus 通过现有 OpenAI-compatible `AIService` 实际完成文字整理调用；模型只允许润色短名称，禁止改变统计、比例、等级、实验内容或受众属性。调用失败或输出越界会退回本地确定性文案。
- 账户页面增加定位/兴趣假设、数据限制、可验证分组、3 个或以上内容 Pillars、证据与历史版本面板。没有人口统计受众数据时只显示内容兴趣假设；不提供策略确认/启用按钮。

### 当前真实账号结果与人工页面验收

- 抖音宠物账号生成当前建议 V4，引用 ACTIVE Baseline V2 与当前 Diagnosis；规范样本 82 条，整体置信度 LOW（内容来源覆盖 1%、类型 33%、主体 49%）。三项 Pillars：猫咪日常与陪伴 40%、双猫共同生活与互动 30%、轻松趣味记录 30%，比例合计 100%。证据保持逐组门槛：主体双猫 n=8、布偶 n=15、缅因 n=16；单猫日常 n=11、搞笑/趣味 n=9 标记可用于正式比较；双猫互动 n=3 和情绪/陪伴 n=3 只显示为初步证据，不被混入 SUPPORTED Pillar 的正式证据引用；AI 来源 n=1 不显示分组。数据依据次序是 Segment、Diagnosis、Overall Baseline、Top/Low。
- 小红书独立开发账号无历史作品 / Diagnosis / Baseline，生成当前建议 V3，仅有 Profile 假设：LOW 置信度、4 个实验 Pillars、各 20%–30% 分配合计 100%，没有引用历史指标或人口统计；空历史数据 hash 也纳入 stale 检查。
- 两账号实际模型文字整理均成功，Provider 为 Qwen OpenAI-compatible / Qwen3.7-Plus；未调用 OpenClaw。模型输出的描述性/因果措辞风险曾在真实 UI 抽查中被发现，因此收紧为模型只改短名称，其余文案由确定性服务输出，并重新生成抖音 V4 与小红书 V3。两账号状态仍分别为 DIAGNOSING / NEW，原 `operator_strategies` 仍为 hypothesis。
- 独立端口 7872 的真实 Easel UI 检查确认：业务账号列表出现“策略建议”；抖音显示 V4、82 条、LOW、定位/受众假设、数据限制、分组证据和实验分配；小红书显示 V3、0 条、无历史数据的 LOW 假设与四周实验说明。页面提示“不会自动启用”且无确认/激活动作。

### 验证与停点

- 新增 Phase 5 测试覆盖分组 n=3/n≥5 标签、来源 n=1 排除、MEDIAN 基准引用、比例合计、因果/越界输出回退、AI 不可用回退、stale 拦截、Profile stale、V1/V2 历史、账号隔离、显式 API 与重启持久化。
- 全量 `.venv/bin/python -m pytest -q`：419 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning。前端 `npm run build` 通过；`npm run lint` 通过，保留两条既有 warning（`linkifyOutputs.ts` 无用转义、`AccountsPage.tsx` Hook 依赖）；`git diff --check` 通过。
- Phase 5 已完成并停在策略建议。Phase 6 及后续 Topic/内容能力未开始，等待用户验收确认。

## 19. Phase 5.1 执行记录：Strategy Evidence Strengthening

### 当前范围

- 本轮只补强 HistoricalPost 的 `subjects` / `content_type` 证据、更新 Diagnosis 与 Baseline、重新生成 Strategy Recommendation。内容来源 REAL/AI 不作为覆盖门槛；不生成 Phase 6 确认、Topic、每日 3 选 1 或内容。
- 已修复 AI 重试候选条件：只请求当前仍未分类的字段，并允许指定字段；人工确认字段与已有分类不因重试创建冲突建议。策略质量门槛已改为主体/内容类型覆盖与正式 Segment 数量；来源稀疏时不生成 REAL/AI Segment 结论。
- Baseline Segment 输出新增相对 Overall 中位数的描述性差异；策略 Pillar 保存确定性比例分数输入，并展示原因、数据引用和下一阶段验证问题。
- 系统代理/VPN 合成 DNS 路由已修复，Easel 子进程沿用 macOS 系统代理；真实 Social Operator 页面 Runtime 显示 Qwen 可用。Qwen 仅收到作品编辑文本，不接收表现指标。
- AI 对 43 条仍有未分类字段的作品返回 58 项建议，2 项 HIGH。对随机/分层 20 项建议抽样后，明确支持 16 项 UNKNOWN 判断、2 项部分支持、1 项分类证据不足、1 项无法判定；不因 HIGH 标签自动接受可疑的“单猫日常”。
- 页面人工审核/批量确认后，主体 45/82（55%），内容类型 62/82（76%），来源 1/82（1%）。主体目标 75% 未达；标题/标签不能可靠确认其余作品具体品种或多猫关系，继续保留 UNKNOWN。内容类型目标 70% 达成。AI 建议计入最终覆盖前必须经 UI 确认。
- 重新诊断后显式预览并建立 Baseline V3 ACTIVE：canonical sample 82，周期 2025-06-24～2026-09-28；播放中位数 578.5、点赞 8、评论 0.5、收藏 0、分享 1、互动率 2.02%，主要指标覆盖 100%。完播率、2 秒跳出率、平均播放时长当前官方导入结构没有可靠字段，保持 null。
- Segment V3：缅因 n=17 / views median 975 / ER 2.27%（views +69%）；布偶 n=17 / 680 / 2.33%（+18%）；双猫 n=10 / 508 / 2.34%（-12%）。内容类型：单猫日常 n=22 / 620.5 / 2.24%（+7%）；双猫互动 n=3 / 491 / 2.58%（-15%，仅初步）；情绪/陪伴 n=7 / 742 / 3.79%（+28%）；搞笑/趣味 n=26 / 753 / 1.56%（+30%）。均为描述性差异，不解释为因果；除 n=3 组外，展示组满足 n≥5 正式比较门槛。
- 真实页面生成 Strategy V5，引用 Diagnosis 与 Baseline V3；V4 保留为 STALE 历史版本。三项 Pillar 测试分配为日常陪伴 36%、双猫互动 31%、趣味记录 33%；比例由历史播放（30%）、互动（20%）、样本可靠度（20%）、账号目标（15%）、探索价值（15%）的确定性权重计算，并在页面展示原因、数据和四周验证问题。策略置信度为 LOW，未输出 REAL/AI 结论；主体分类覆盖不足是未通过 Phase 5.1 覆盖目标的原因。
- 策略页面发现并修复过期推荐会禁用“重新生成建议”的 UI 阻断；V5 已通过真实 UI 生成。自动测试 424 passed、6 skipped；前端 build 通过；lint 通过并保留两条既有 warning；`git diff --check` 通过。

### 当前验收状态

- 全量 Python tests：424 passed、6 skipped；前端 build 通过；lint 通过并保留两条既有 warning；`git diff --check` 通过。真实 UI 已完成分类审核、Diagnosis 重跑、Baseline V3 预览/生成和 Strategy V5 生成。
- 内容类型覆盖达到 76%，主体覆盖 55% 未达 75% 目标。基于标题的剩余 UNKNOWN 无法安全提升；策略质量门槛保持 LOW，而不是用猜测提高覆盖率。
- Phase 5.1 工程与真实闭环已完成，但 Phase 6 前置数据证据目标未全部满足。Phase 6 及后续能力未开始，当前停在等待用户验收/授权状态。

## 20. Phase 5.2 执行记录：Subject Evidence Completion

### 分类复核

- 本轮只对 82 条 canonical unique HistoricalPost 中 37 条主体未确认作品执行 subjects-only Qwen 建议；提示词与结构化输出仅包含主体，不请求内容来源、内容类型或 Hook。模型输入为作品编辑文本，不包含播放和互动指标。
- 真实 UI 的“只看出镜主体未分类”筛选显示 37/82 条。建议结果为 36 条 UNKNOWN/LOW、1 条“其他”/HIGH；“其他”标题为程序员/厨艺内容，无法证明其为宠物主体或其它可分类对象，因此该建议未接受。没有任何新主体标签得到足够证据可安全确认；未执行人工批量改标，原 subjects 45/82（54.88%，页面取整 55%）不变，UNKNOWN 37 条。
- 明确的猫咪泛称、普通日常标题、剪辑软件标签不能确定品种或同框猫只数量。文本中缺少账号既有名字到品种映射；无法判断的条目继续 UNKNOWN，没有为覆盖率强猜。内容来源和内容类型也未重新分类或更改。

### Baseline V4 与 Strategy

- 真实 UI 显式预览并生成 Baseline V4 ACTIVE，82 条唯一作品，周期 2025-06-24～2026-09-28。因为未有可安全确认的新主体，V4 的 Overall 与 V3 一致：播放 median 578.5（n=82）；点赞 8、评论 0.5、收藏 0、分享 1；互动率 median 2.02%（n=82）。Baseline V3 保留并转为 STALE；分类不足没有阻止 Overall Baseline 重算。
- V4 主体 Segment：缅因 n=17，播放 median 975，互动率 median 2.27%，相对整体播放 +68.5%；布偶 n=17，680，2.33%，+17.5%；双猫 n=10，508，2.34%，-12.2%。比较样本不变，差异为描述性统计，不推断因果。
- Strategy V6 曾在真实 UI 生成；人工验收发现 V6 的两条 Pillar 理由未正确对应其引用组样本/指标。修复确定性解释后，在同一范围和 Baseline V4 上重新生成 Strategy V7 CURRENT，V6 保留为 SUPERSEDED 历史版本。此为纠正展示证据关联的版本，不是进入新阶段。V7 比例为日常陪伴 36%、双猫互动 31%、趣味记录 33%，与 V5 分配相同；Pillar 理由现分别引用缅因 n=17 (975 views / 2.27% ER)、双猫 n=10 (508 / 2.34%) 和搞笑/趣味 n=26 (753 / 1.56%)，并保留下一阶段验证问题及分配因素。
- 双猫互动解释显示其历史播放低于整体（508 vs 578.5），互动率高于整体（2.34% vs 2.02%）；仍保留 31% 作为账号双猫 IP 关系价值下的测试资源，而非因为播放历史最佳。明确说明这是待验证方向，不是因果结论。

### 证据门槛、验收与停点

- Strategy V7 Confidence 为 LOW。证据检查：subjects 覆盖 45/82（54.88%），缅因/布偶/双猫组各 n=17/17/10，三组均达到最低 n=5；但 UNKNOWN=37，超过最小主体组且占总样本 45.1%，可能改变主体间排序。coverage 与 UNKNOWN-bias 条件不满足，所以 LOW，页面提示“剩余未分类作品较多，主体间比较仍存在较大不确定性。”没有降低阈值、隐藏 UNKNOWN 或调高 Confidence。
- 真实 UI 检查了 82 条账号样本、主体覆盖提示、37 条未确认过滤、AI suggestions 未自动确认、Baseline V4 Overall/segments、策略 Pillar 证据与比例、双猫低播放/高互动解释及 LOW 证据提示。未开始 Strategy Confirmation、Phase 6、Topic Engine、每日 3 选 1 或内容生成。
- 全量 `.venv/bin/python -m pytest -q`：427 passed、6 skipped、1 条既有 Starlette/httpx deprecation warning。Phase 5.2 定向分类/策略测试 29 passed；前端 `npm run build`、`npm run lint` 已通过（lint 保留两条既有 warning）；最终 `git diff --check` 通过。
- Phase 5.2 工程与真实页面流程已完成，但主体证据充分性 Gate 未通过。当前不具备进入 Phase 6 的真实证据条件；停在本阶段，等待用户验收确认。

### Phase 6 进入规则修订（用户验收授权，2026-10-01）

- 用户确认 Phase 5.2 验收通过，并基于真实复核指出剩余 37 条 subjects UNKNOWN 的原因是历史文字字段缺乏主体证据；继续强制 AI 分类或要求逐条重看视频收益不足。
- 用户明确修订 Phase 6 进入条件：Strategy Confidence=LOW 本身不阻止确认。LOW 在此表示第一阶段实验策略需后续以真实运营数据继续验证。Baseline 有效、至少一条 CURRENT Recommendation、主要 Pillar 有可解释依据、策略明确为实验方案且用户明确确认，才允许激活。
- 抖音真实账号确认依据：82 条有效作品；Baseline V4；Strategy V7 CURRENT、LOW；主体 UNKNOWN 37/82（45.1%）；缅因/布偶/双猫组 n=17/17/10；建议比例日常陪伴36%、双猫互动31%、趣味记录33%。

## 21. Phase 6 执行计划：Strategy Confirmation

### 代码路径与复用

- 复用 `operator_accounts` 生命周期、`OperatorAccountService.require_active_account` 门禁、`strategy_recommendations` 历史版本、SQLite 仓储、FastAPI 账号路由与现有策略建议面板。
- 不覆盖 Recommendation JSON；新增 ActiveStrategy、ACTIVE ContentPillar 和确认审计事件的 SQLite 数据结构与账户隔离 API。用户调整仅可写未来定位、Pillar 名称/说明/分配比例。
- UI 流程：查看 V7 和只读证据 → 编辑未来策略 → 显示实时总比例 → 确认摘要 → 用户主动确认并启用 → 显示 ActiveStrategy 与 4 周实验问题。
- 确认事务要求：当前有效 Recommendation；有历史作品时 Baseline ACTIVE、Diagnosis CURRENT；无历史例外只允许小红书 Profile 起步实验。服务端再次验证比例合计100%，确认后将账户设 ACTIVE、所有 Pillars 设 ACTIVE，并记录 audit event。
- LOW 可以确认，但保留 37/82 UNKNOWN 数量与第一阶段测试说明。Confirmation 页面不编辑 Baseline/历史样本。成功页不触发 Topic API，不生成选题、素材推荐、日历/发布计划或内容。

### 验证方案

- Python 测试：LOW 确认、非100%拒绝、比例/名字/说明调整、Recommendation 保持不变、ActiveStrategy V1、Pillars ACTIVE、Account ACTIVE 与 `require_active_account`、重复确认拦截、账号隔离、XHS无历史、过期推荐/Baseline/Diagnosis拒绝、审计和重启持久化、Phase 5 回归。
- 前端 build/lint，完整 Python tests 与 `git diff --check`。
- 本机真实 UI：对抖音账号 V7 查看数据依据和 UNKNOWN 提示；保持36/31/33比例；打开摘要并明确确认；验证 Recommendation V7 历史、ActiveStrategy V1、账号状态和 Pillars 均 ACTIVE，且无 Phase7 输出。
- 完成后更新产品规格、计划与 CHANGELOG；Phase 6 完成后停下等待确认。

## 22. Phase 6 执行结果：Strategy Confirmation

- 工作区进入 Phase 6 前先创建 Phase 5.2 checkpoint：`6f6ce87 Checkpoint social operator Phase 5.2 subject evidence completion`。本轮 Phase 6 修改未混入 checkpoint，也未提交或推送。
- 真实 Douyin 宠物账号在本地 UI 完成“查看 V7 与证据 → 编辑/检查策略 → 确认摘要 → 确认并启用”。用户保留推荐定位及 36%/31%/33% 比例；确认摘要呈现 82 条有效历史作品、LOW 和策略为第一阶段实验。
- 数据库验证：账号 `douyin-pet` 为 ACTIVE；Baseline V4 仍 ACTIVE；Recommendation V7（`e1ad4895-aa5b-41f4-8006-365597e8f2bc`）仍 CURRENT 且未改写；ActiveStrategy V1 `active-strategy-b7a32653005540f7a8e436d4b09afecc` 为 ACTIVE，Confidence LOW，绑定来源推荐，确认者 `local_user`，确认时间 `2026-10-01T01:26:33.354885+00:00`。一个确认审计事件记录账号、推荐、策略、时间和比例 `[36,31,33]`；三个 ContentPillar 均 ACTIVE。
- 用户可读策略：定位“缅因猫与布偶猫的双猫家庭内容方向（初始假设）”；日常陪伴 36%（缅因 n=17，播放 median 975；另保存单猫日常与情绪/陪伴依据）、双猫互动 31%（n=10，播放 median 508、互动率 2.34%，高于整体 2.02%）、趣味记录 33%（搞笑/趣味 n=26，播放 median 753、互动率 1.56%）。这些是描述性差异，不作因果结论。
- 页面显示 subjects UNKNOWN 37/82（45%）、Confidence LOW、未来四周实验说明。持久化实验问题已通过带审计记录的修正与用户确认摘要保持一致：缅因较高播放是否持续；双猫互动能否持续高于整体互动率；趣味内容较高播放/偏低互动是否稳定并观察有数据时的涨粉表现。
- 验证：全量 Python tests 438 passed、6 skipped；前端 `npm run build` 成功；`npm run lint` 成功，保留两条既有 warning；`git diff --check` 通过。真实页面已核对 ACTIVE V1、V7 保留、比例、证据摘要、UNKNOWN、Confidence 和四周实验问题。未创建 Topic、选题、素材建议、发布计划或内容；Phase 7 未开始。
- 本轮结束于 Phase 6。Phase 7 不在本轮范围，等待用户后续确认。

## 23. R1-A 执行结果：Daily Topic Recommendation

### 实现范围

- 将原 Phase 7、8、9 合并为 R1-A：首页第一屏为“今日运营”，按 ACTIVE 业务账号显示当天 3 个候选、1 个主推。账号必须有 ACTIVE ActiveStrategy 和至少 3 个 ACTIVE ContentPillar；服务层与 SQLite 写入路径都校验账号、策略和 Pillar 绑定。未确认策略的账号显示门槛说明，不生成正式 Topic。
- 新增 `operator_topic_batches`、`operator_topics`、`operator_topic_events` 持久化；Topic 记录策略/Pillar 版本、创意字段、解释性评分分项、历史证据、实验问题、制作难度、材料需求、重复相似度和状态；换批保留旧批次并将未选候选标记为 SKIPPED，选择操作写入事件且同一账号本地日期仅能选择一次。
- `TopicRecommendationService` 复用 Easel 统一 `AIService`。模型只产生创意字段；账户门禁、策略绑定、历史证据、固定权重计分、实验问题、主推选择与重复控制由代码完成。模型失败时使用明确标记的本地模板。TopicScore 是 0–100 规则分，不是成功概率；LOW 策略继续明确显示为实验验证期。
- 抖音权重固定为：策略匹配30、历史支持25、实验价值20、执行可行性15、新鲜度10；小红书为：定位匹配30、受众价值25、真实经历20、IP价值15、可行性10。七天内相似候选扣减新鲜度，主推优先考虑比例缺口和分数接近度。
- R1-A 不新增账号策略确认，也不替用户激活 XHS。初次验收时 XHS 仍为 NEW，页面和服务端均正确阻止正式 Topic 生成；用户随后在账号策略确认页面明确确认并启用 XHS Strategy V1，之后才继续正式验收。第一次提交因本地服务未配置允许的端口来源而被 403 拦截；将本地服务按项目现有 `EASEL_PORT` 配置重启后，原确认操作成功，没有关闭来源校验或修改安全逻辑。

### 真实账号验收

- 本地独立验收端口 7873 的真实 Easel 页面已核对：抖音宠物账号日期为 2026-10-01，ACTIVE Strategy V1，LOW 实验提示，82 条有效历史作品，三个 ACTIVE Pillars 与 36%/31%/33% 周度目标；当日 AI 批次已从数据库读取并显示 3 个候选、1 个主推。
- 当日主推为“当缅因猫尝试进入较小的纸箱时，布偶猫在旁边会有什么反应？”，TopicScore 85，绑定“趣味记录”，引用搞笑/趣味 n=26、播放中位数753、互动率中位数1.56%。日常陪伴备选引用单猫日常 n=22 及主体等证据；双猫互动备选引用双猫 n=10、播放中位数508、互动率2.34%。所有差异均展示为描述性历史，不作因果承诺。
- Easel `ConfiguredAIService` 的真实运行状态为 AVAILABLE/Qwen；Douyin 与 XHS 的真实调用均得到结构化 AI 选题，批次持久化标记 `generation_mode=AI`。解析兼容 Qwen 将材料清单作为字符串返回的结构；异常仅降级到本地模板，不输出原始模型响应或密钥。
- XHS 用户确认前，账号页显示 Strategy Recommendation V3（CURRENT、LOW、0 条历史、定位假设和四个 Pillars：30/25/25/20）及 ActiveStrategy V1 确认摘要。用户明确确认并启用后，数据库验证账号 ACTIVE、ActiveStrategy V1 ACTIVE/LOW，四个 Pillars 为项目实战30%、AI实践25%、开发复盘25%、独立开发20%。
- XHS 第一次 AI 批次含有无依据的第一人称项目经历和量化成效，因此没有作为可用结果保留：该批次标记 SUPERSEDED，三个候选均 SKIPPED。针对这一真实模型输出收紧提示词并增加保守内容校验；如果模型继续编造个人经历/结果，服务改用显式标记的本地模板。之后真实 AI 批次 #2 成为 CURRENT，含 3 个候选、1 个主推，三个标题均为中性问题式表达，不声称账号本人已做过某项目或取得特定结果；每条均提示只能填写真实经历。XHS 无历史作品，因此历史证据为空，没有伪造 Baseline 或历史数据。
- 两账号当前批次均已持久化并在真实 UI 显示；XHS 日批次 `topic-batch-3ae0a9f5a127408b922f7882b489c219` 的主推是“独立开发小功能时，先写测试用例还是先写业务逻辑更合理？”，分数 74，绑定“开发复盘”；另两条分别绑定“独立开发”（74）与“AI 实践”（71）。

### 验证与阶段停点

- 自动测试覆盖 ACTIVE/未 ACTIVE、三候选一主推、两平台权重、真实/空历史证据、LOW 策略、AI 模板降级、重复降分、换批跳过、单次选择、审计、跨账号隔离、策略版本绑定和重启后批次读取。新增的日常 Topic 测试 fixture 不再导入另一个测试模块，确保全量收集稳定。
- 全量 `.venv/bin/python -m pytest -q`：448 passed、6 skipped，1 条既有 Starlette/httpx deprecation warning；前端 `npm run build` 成功；`npm run lint` 成功，保留 `linkifyOutputs.ts` 无用转义与 `AccountsPage.tsx` Hook 依赖两条 warning；`git diff --check` 通过。
- R1-A 的双账号真实流程已完成并通过用户确认。其实现与验收细节见本节前文；当前按用户“继续执行”进入 R1-B。

## 24. R1-B 执行结果：Content Generation

### 实现范围

- 复用 `ConfiguredAIService`、`operator_topics` 已选状态、ACTIVE 账号/策略以及当前 Dashboard“今日运营”；AI 仅为用户已经选择的 Topic 生成草稿，不从推荐主推或未选择候选绕过选择动作。
- 新增 `operator_content_drafts` 与 `operator_content_draft_events`。草稿保存 account、selected Topic、ActiveStrategy ID/version、平台、AI 生成模式、独立版本、CURRENT/SUPERSEDED 状态、结构化内容和时间；重新生成新增版本并保留旧版本，人工修改保留当前版本并写入 EDITED 审计事件。
- 新增双平台 `ContentGenerationService` 和 API：读取当前所选 Topic 草稿、生成/重新生成、保存用户编辑。服务端重新校验账号 ACTIVE、Topic 属于该账号且状态 SELECTED、Topic 的策略仍是当前 ACTIVE Strategy；数据库写入再次校验归属和策略版本。
- 抖音草稿包含主题、推荐理由、内容目标、Hook、前 3 秒、视频结构、镜头、字幕、时长、5 个标题、BGM、话题、评论互动、发布时间建议、待用户核实的已有素材和实验标签。
- 小红书草稿包含 5 个标题、封面文字、开头 Hook、结构、完整正文、配图结构、截图建议、待核实项目素材、CTA、评论互动、推荐话题、发布时间建议和实验标签。文本字段明确提示不得伪造项目经历；结构化输出不完整时不保存。
- UI 仅在 Topic 成为 `SELECTED` 后显示“生成内容草稿”，展示按平台组织的草稿，支持编辑标题及核心正文/字幕并保存；重新生成会创建新版本。页面明确“仅供审核和修改，系统不会自动发布”。
- 对小红书生成输出校验无依据的第一人称经历、具体量化结果；对两平台拦截保证涨粉/爆款/提升等表述。抖音限制宠物拍摄建议不得诱导宠物挤入过小/不安全道具或受困；对模型结构错误提供一次有界重试，重试仍不合格则不保存草稿。
- R1-B 不接入 Easel 发布 API，不创建日历项、发布时间事件、发布记录或表现数据；不开发素材上传/素材库。

### 验收与待完成项

- 自动测试已覆盖：抖音与小红书字段结构、严格五标题、模型结构错误的一次修复重试、不安全宠物拍摄方式拦截、小红书虚构经历/量化结果拦截、未选 Topic 拒绝、账号隔离、版本保留、编辑审计和重启持久化。
- 用户在今日运营页面选择了抖音主推 Topic“当缅因猫尝试进入较小的纸箱时，布偶猫在旁边会有什么反应？”。真实运行状态为 `AVAILABLE / qwen`；模型调用通过 Easel `ConfiguredAIService` 成功，生成内容草稿 V3，HTTP 201，绑定当前 ACTIVE Strategy V1 和所选 Topic。首次输出标题候选数量不合格，触发一次修复重试；后续输出含不安全纸箱建议，被提示约束修正后才通过安全校验并保存。
- 已在本地 SQLite 验证草稿版本 1/2 为 `SUPERSEDED`，版本 3 为 `CURRENT`，事件依次为 `GENERATED`、`REGENERATED`、`REGENERATED`；重启本机服务后真实页面显示 V3、编辑和重新生成入口，明确草稿不会自动发布。脚本中的具体猫咪行为和素材仍需账号负责人按实际拍摄情况核实后修改。
- 本轮变更新增/调整的自动测试：`.venv/bin/python -m pytest -q tests/test_social_operator_content_generation.py`：9 passed，1 条既有 Starlette/httpx deprecation warning；`git diff --check` 通过。先前 R1-B 全量 Python 455 passed/6 skipped、前端 build/lint 均成功；本轮仅变更生成服务提示/校验和测试，未重跑前端构建。
- R1-B 真实模型生成与 UI 保存检查已完成。R1-C 内容日历/发布数据与 R1-D Weekly Review 均未开始。

## 25. R1-C / R1-D 执行结果：运营日历与周复盘闭环

### 实现范围

- 新增 account-scoped 运营日历、实际发布登记、指标、周复盘和 Strategy Memory 表。数据库迁移升级到 `user_version=16`；保留计划变更事件、复盘版本、来源数据版本、Baseline 版本、Memory 版本及确认/忽略/替代/失效事件。用户修改记录不覆盖历史复盘。
- 日历只允许将当前 ACTIVE Strategy 下用户已选择的 Topic（可选绑定当前 CURRENT 草稿）加入计划；支持月视图、调整时间、标记待发布、取消和人工登记已发布。发布登记记录真实发布时间、标题、内容来源及可选作品链接/Hook/时长，并直接接入指标录入。日历状态均有事件审计；旧策略下未发布计划不能继续推进。
- 24H/72H/7D 可分节点录入播放、互动、涨粉、主页访问和咨询。页面和服务均不调用平台发布接口或执行自动发布。
- `WeeklyReviewService` 按 Asia/Shanghai 周一至周日筛选实际发布作品；NULL 保持未知，真实 0 保留；分节点统计各指标 median、P25/P75、sample count、coverage，并对照 ACTIVE Baseline。对整体及 Pillar、Topic、内容来源、Hook、时长、发布时间分组给出描述性统计；分别保留每节点结果和每条作品最新可用指标摘要。
- Strategy Memory 只对 ACTIVE Baseline 下 7D Pillar 组提出候选：至少 3 条作品，播放或互动率中位数相对 Baseline 绝对差异至少 20%。建议先保持 PROPOSED；用户可编辑后确认或忽略。只有 ACTIVE Memory 会进入下一轮 Topic AI 上下文和相应 Pillar 推荐理由；Memory 不改写策略。发布/指标更新会使当前复盘和来源 Memory 失效。
- 增加“运营日历”和“周复盘”普通用户页面：日历可安排已选 Topic 并登记真实发布；周复盘可选择账号和周、查看 Baseline 状态、从日历或手动入口登记实际作品、录入分节点指标、生成和查看复盘历史、检查/确认/忽略经验，并查看已确认 Memory。未有实际发布时显示明确空状态，禁止生成空复盘。

### 验收和停点

- 自动验证：全量 `.venv/bin/python -m pytest -q` 为 464 passed、6 skipped，1 条既有 Starlette/httpx deprecation warning；前端 `npm run build` 通过（Vite 提示主 bundle 略超 500 kB）；`npm run lint` 通过并保留两条既有 warning；`git diff --check` 通过。
- 覆盖真实指标和真实 0、缺失值、账号隔离、Baseline 比较、复盘版本、发布/指标更新后 stale、Memory 最小样本与差异门槛、用户确认后下一轮 Topic 读取 Memory、用户忽略、重启持久化，以及 R1-A/R1-B Topic 和草稿回归。
- 本地 7873 应用已重启并在真实浏览器验收“运营日历”与“周复盘”空状态；当前抖音账号显示 Baseline V4、尚无登记发布作品。日历没有虚构排期，周复盘禁用空数据生成。数据库确认发布作品、指标、复盘、Memory 均为 0 条；本轮没有写入合成账号数据。
- 工程与空状态真实 UI 验收通过。真实周复盘、Memory 人工确认及后续 Topic 对 Memory 的实际影响，需在账号真实发布并录入平台数据后继续验证；这不影响 R1-C/R1-D 工程实现完成。本轮到此结束，不进入其它阶段。

## 26. R1-RC 执行结果：Release Candidate Integration & Acceptance

### 集成修复

- 首页以“今日运营”为主入口，进度仅按真实登记的 PublishedPost 计算；今日计划读取运营日历。抖音和小红书无历史状态分别按账号数据显示，小红书明确提示当前依据账号定位且无历史表现。
- 草稿提供直达运营日历的排期入口。日历切换账号时清空上一个账号的 selected-topic ID，避免新账号虽有已选 Topic，表单仍误将“加入日历”禁用。
- 对兼容模型偶发的空 `comment_interaction` 文本字段补充中性、可编辑的提问句；其它必需字段仍严格校验。真实请求错误在界面保持用户可读，不保存不完整草稿。
- 侧栏对话连接状态不再把底层 Gateway 术语暴露给普通用户，也避免与已配置的模型 Provider 状态混淆。
- 添加 82 条历史作品的真实 SQLite v16→v17 迁移验证与 R1 全流程隔离数据库集成测试。数据库预迁移备份在 `backups/social_operator_2026-10-01_r1-rc.sqlite3`；迁移后 `integrity_check=ok`，82 条历史作品保留。

### 真实账号 UI 冒烟

- 抖音：复用现有真实选题与 V3 草稿，将计划加入日历，计划时间为 2026-10-02 20:00（Asia/Shanghai）。
- 小红书：无历史表现模式下，当前已选择的开发复盘选题通过已配置的 Qwen-compatible AIService 真实生成并保存 V1 草稿；因模型返回空评论互动字段，经中性默认句规范化后通过其余校验。随后将选题及 V1 草稿排入 2026-10-02 20:00（Asia/Shanghai）。正文保留真实项目细节占位提示，未声称用户本人已有相关经历或素材。
- 两项均为未来运营计划。SQLite 当前发布作品 0、表现指标 0、周复盘 0、Strategy Memory 0；未写入虚构发布或指标。真实模型请求有一次成功响应，但本地助手状态仍为不可用（对今日运营的 AI 生成链路无影响）。
- `outputs/_social_operator.sqlite3` 当前 `user_version=17`、`integrity_check=ok`，历史作品仍为 82 条。两个账号各有一项 DRAFT 状态的计划；抖音绑定草稿 V3，小红书绑定草稿 V1。

### 验证与发布状态

- 完整 Python 测试为 468 passed、6 skipped；前端 production build 通过（主 bundle 535.01 kB）；lint 通过并保留两条 warning；`git diff --check` 通过。另有既有 Starlette/httpx 弃用提示；这些非阻塞维护项保留在 RC Checklist。
- 自动发布、人工登记真实发布后指标/复盘/Memory 的闭环没有在验收中伪造；真实账号尚无发布记录，因此这部分运营样本验证仍待账号主人实际发布并录入数据。
- 本阶段只完成 R1-RC 集成与发布候选检查；不进入 Phase 5 或新增范围。Checklist 可以标注代码和真实 UI 冒烟通过，但不得宣称已有真实发布数据闭环，也不得把 V1.0.0 标为正式发布。
