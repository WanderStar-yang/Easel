# AI Social Operator V1 — Active Implementation Plan

- 状态：Phase 0、Phase 0.5、Phase 1 与 Phase 2 已完成；等待用户确认后再进入 Phase 3
- 更新日期：2026-09-29
- 源码基线：Easel `main` at `0cab7ca6f6e8286635d25fe2435dda11a975ffec`
- 本计划依据：`../../AGENTS.md`、`../product-specs/AI_SOCIAL_OPERATOR_V1.md`、`PLANS.md`、`../audits/EASEL_V1_SOURCE_AUDIT.md` 及当前仓库源码
- 本轮边界：Phase 2 历史数据管理已实现；未开始 Phase 3 Initial Diagnosis

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
