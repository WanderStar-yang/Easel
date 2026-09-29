# Easel V1 源码审计（Phase 0）

- 审计日期：2026-09-29
- 审计对象：当前工作区根目录（Easel 仓库根目录）
- 审计版本：`0cab7ca6f6e8286635d25fe2435dda11a975ffec`（分支 `main`；审计时工作区干净）
- 产品依据：`docs/product-specs/AI_SOCIAL_OPERATOR_V1.md`；执行规则：`docs/exec-plans/PLANS.md`、`AGENTS.md`
- 范围：只读源码与文档，新增本报告；未实现业务功能、未改 Easel 源码

> 本次 Phase 0 原始审计时，Easel 源码位于父工作区的 `Easel/` 子目录，产品文件也位于父目录。整理后，源码仓库根目录成为工作区根目录；Phase 0.5 将本报告中的旧 `Easel/` 源码前缀校正为仓库根相对路径。当前产品规则文档已整理到规范路径 `AGENTS.md`、`docs/product-specs/AI_SOCIAL_OPERATOR_V1.md`、`docs/exec-plans/PLANS.md`。

## 1. 摘要结论

Easel 是本地运行的社媒内容工作流与创作整合层。其 Web 由 FastAPI 提供 API、React 19 + TypeScript + Vite 提供界面；Agent 本身运行在 OpenClaw Gateway 中，Easel 通过 CLI、HTTP/SSE 与文件接口编排。多数业务资料保存在 Markdown、JSON/JSONL 和 `outputs/` 文件树中，没有面向 V1 业务对象的关系数据库或 ORM。

可复用基础包括 Profile 文件机制、OpenClaw Agent/Skill 路由、素材与产物管理、热点展示、选题 CRUD、内容日历、发布记录、账号数据抓取、快照统计及复盘计算脚本。源码里还存在账号诊断、策略顾问等 Skill。但这些是通用的提示词工作流，依赖 Profile 和用户/Agent 提供数据；没有组成 V1 所要求的、以两个业务账号为边界、可追溯历史样本、具有 Baseline 与策略确认门禁的确定性闭环。

关键差异：Easel 当前的“账号”主要是平台登录凭证/登录状态；`Profile` 是跨任务的创作者人设，不等同于绑定一个平台的运营账号。日历和选题记录均没有 `accountId`；选题目前只有轻量任务字段，没有 TopicScore/支柱等关系。数据分析偏向抓取平台创作者中心概览和通用复盘，缺少统一的历史作品导入、按样本建立 Baseline、24H/72H/7D 指标记录及复盘到选题的可追溯反馈链。

建议保留 Easel 作为应用、Agent 和内容工作流底座；增加薄的 V1 业务域层，对 Profile、Skill、Calendar、发布与分析基础做适配，不另造 Agent 框架。自动发布能力不应接入 V1 的用户流程，应在 V1 导航/路由能力层隐藏或禁用，底层代码暂时保留以减少对 Easel 上游能力的破坏。

## 2. 实际技术架构

| 层 | 源码确认的实现 | 证据 |
|---|---|---|
| Web 服务 | Python 3.10+；FastAPI、Uvicorn、SSE；单体 API 与文件系统读写、外部脚本子进程编排 | `pyproject.toml`、`web/app.py` |
| 前端 | React 19、TypeScript 6、Vite 8；页面组件与 `lib/api.ts` 中的 API 客户端 | `web/frontend/package.json`、`web/frontend/src/` |
| Agent | OpenClaw Gateway 承载 Agent、工具和会话；Easel CLI/Web 通过 OpenClaw 命令或 Gateway OpenAI 兼容 HTTP/SSE 接入 | `openclaw/`、`easel/cli.py`、`web/app.py` |
| 扩展/工作流 | Markdown Skills（含 YAML 元数据）、Python/Node 脚本、共享脚本及引用资料；Agent 依 Workspace `AGENTS.md` 路由 | `skills/openclaw/`、`skills/shared/`、`openclaw/workspace/AGENTS.md` |
| 持久化 | Profile 与 Skill 配置以 Markdown/YAML 为主；日历、选题、发布日志和指标以 JSON/JSONL 文件保存；会话另存 OpenClaw state/SQLite | `profiles/`、`outputs/`、`skills/shared/scripts/`、`easel/gateway_questions.py` |
| 构建与质量 | `pytest`；前端 `tsc -b && vite build` 和 `oxlint`；项目还提供 skill 校验脚本 | `pytest.ini`、`tests/`、`web/frontend/package.json`、`scripts/validate_skills.py` |

前端导航包含工作台、对话、技能库、内容库、账号、画像；工作台子页包括趋势、选题、日历、发布和数据分析。它是本地单用户应用，没有 SaaS 多租户/用户权限模型，这与 V1 的个人工具定位相符。

## 3. 关键目录与职责

| 目录/文件 | 当前职责 | 与 V1 的关系 |
|---|---|---|
| `easel/` | CLI、Profile 注入、OpenClaw Gateway 管理/连接、会话问答桥接 | 继续作为应用与 Agent 接入层；无需重建 Agent 基础 |
| `web/app.py` | FastAPI 单体入口；页面/API、文件数据、登录/发布/分析子进程 | 复用现有 API/服务入口；新业务逻辑应拆薄服务模块，避免继续堆入单文件 |
| `web/frontend/src/components/` | 工作台、账号、画像、日历、选题、发布等页面 | 复用现有导航、日历与内容库交互模式；V1 页面需增加诊断/确认状态 |
| `profiles/` | 每个 Profile 一组 identity/style/audience/platforms/preferences/memory Markdown | 复用为表达风格/受众/长期经验的素材；不能单独充当业务账号/策略数据库 |
| `skills/openclaw/` | Agent 可调用的社媒 Skill，包括诊断、策略、选题、创作、发布、数据、复盘 | 复用相关 Skill 的提示词、参考文档与计算脚本；需限定双账号语境并接入结构化业务数据 |
| `skills/shared/scripts/` | 日历、统计、账号抓取、模型注册、输出路径、发布等共享脚本 | 复用确定性统计和日历能力；新业务聚合逻辑应调用或提取共享函数 |
| `openclaw/` | OpenClaw 配置同步与运行 Workspace 指令 | 保持 Agent 运行约定；注意 Workspace 的 Profile 路径说明存在别名/历史差异 |
| `outputs/` | 用户创作产物、临时状态及分析数据文件 | 继续保存产物；V1 结构化运营记录宜单独版本化、加账号键并原子写 |
| `tests/` | CLI、API 安全、数据追踪、Gateway、输出保护等 pytest 测试 | 新增业务对象/隔离/状态门禁时扩充覆盖 |

## 4. 相关现有能力审计

| 能力 | 已有实现（源码事实） | 与 V1 的差距/判断 |
|---|---|---|
| Agent/Skill | Agent 由 OpenClaw 提供；Skill 通过 Markdown 工作流、脚本和引用资料扩展；有 `skill-account-diagnosis`、`skill-strategy-advisor`、`skill-content-strategy`、`skill-topic-evaluator` 等 | 可复用为模型推理与工作流，不是已完成的 V1 诊断引擎/Topic Engine；诊断 Skill 明确要求 Profile 和近期数据，信息不足时会追问，不会自行加载统一历史数据集 |
| Profile | `profiles/<name>/` 文件组；CLI/Web 注入 Profile 名并提示 Agent 读取对应文件；Profile 有 memory | 作为创作者画像/风格记忆复用。V1 需新增 `Account` 与 `Profile` 的显式关联和账号级策略确认状态；不得把两个账号数据只放在 Profile 文本里 |
| 平台账号 | `/api/accounts` 返回平台能力与本地登录态；`LOGIN_RUNNERS` 按平台映射平台名、浏览器 Profile 或发布后端；可扫码/凭证登录、校验 whoami、登出 | 是平台登录连接，不是业务账号实体；登录态不代表 Initial Diagnosis 或 Strategy Confirmation 已完成。不要直接以平台字符串作为唯一业务账号主键 |
| 日历 | `/api/schedule` CRUD + 前端月历；共享脚本 `calendar_ops.py` 读写 `outputs/_schedule.json`，记录排期/活动/已发布事项 | 时间线能力可复用；记录没有 `accountId`、topic/draft 外键，状态为 `idea/draft/scheduled/published`，并非产品定义的内容全生命周期，也无 24H/72H/7D 归因关联 |
| 选题池 | `/api/ideas` 对 `outputs/_ideas.json` 做 CRUD；前端 Ideas 页面 | 可复用轻量列表 UI/文件读写模式；不是每日 3 选 1 Topic 数据模型，尚无推荐理由、分数、支柱、素材、实验标签、账号归属、主推标记 |
| Trend/Research | `/api/trends` 聚合热点；`skill-trending-topics`、`skill-trend-rider`、竞品/搜索类 Skill 提供研究流程 | 可作为可选 Topic 来源；产品不要求所有来源实时联网。趋势数据应标注来源/时间，不得替代历史数据诊断 |
| 内容生成 | 丰富的文案、图文、视频脚本、封面和媒体制作 Skill；Agent 将产物放入 `outputs/` | 复用生成/媒体能力；需增加平台/账号专属模板和结构化保存，尤其小红书完整图文与抖音脚本输出字段 |
| Analytics | `/api/analytics/{platform}` 通过 Playwright/专用脚本抓取创作者中心概览；`account_stats.py` 记录平台增长快照；有 `social_stats.py` 中位数、互动率、聚合、样本提示等纯函数；有发布分析/复盘 Skill 脚本 | 可复用抓取器和统计函数。它不提供手工/CSV/XLSX 历史作品标准化导入，不足以生成产品要求的逐账号历史作品 Baseline；不能假设所有指标均可抓取 |
| 发布记录 | `skill-publish-log` 按 Profile/平台记录事件与初始指标；数据在 `outputs/_analytics/publish-log.json`；日历脚本可联动记录 | 事件表可借鉴/复用，但要将归属键升级到明确 `accountId`；事件初始数据不等于多 checkpoint 的 PostMetric |
| 指标快照 | `skill-data-tracker` 保存账号级粉丝/互动快照和帖子生命周期快照，目录有 profile/platform/date 维度 | 可借鉴时序快照与确定性计算；尚无统一发布 Post 外键和固定 24H/72H/7D 节点约束，也不能代替 V1 的单条作品历史库 |
| 周/月复盘 | `skill-social-performance-review/scripts/review.py` 计算逐帖互动率、中位数、Top/Bottom、支柱/格式聚合等，LLM 写洞察；其他脚本分析时间、标签、类型、增长 | 统计层可复用；当前输入需先整理为 JSON，由 Agent 解释；未发现复盘结论经审核写入 Strategy Memory 并可追踪地改变下一轮 Topic 的端到端实现 |
| Storage | 工作流文件存储为主，原子写入由不同脚本各自实现；Gateway 问答桥接读取 OpenClaw SQLite | 无统一迁移/事务/跨对象约束。Phase 1 应选定最小持久化方案，并设计文件到业务库或版本化 JSON 的一致性与备份策略；不要把 Gateway 会话库当业务数据库 |
| Model Provider | `model_registry.py` 与 Web Settings 管理文本/媒体 Provider；Agent 主模型由 OpenClaw 配置路由 | 复用配置和调用路径；业务诊断、推荐应使用现有 Agent/Provider，不再创建通用 Prompt 管理平台 |
| 平台适配/发布 | 小红书、抖音等发布脚本可真实执行；发布 API 调用带 `--exec`，并有扫码、验证码和发布状态处理 | 与 V1 明确“人工发布”约束冲突；V1 界面和正式流不得触发发布脚本，也不得新增自动互动/自动养号。可以保留登录状态读取/分析能力是否使用需按平台条款核实 |

## 5. 四类改造清单

### 5.1 直接保留

- OpenClaw Gateway、Easel CLI/Web 壳、会话流式交互、Skill 路由与技能展示。
- Profile 的 Markdown 文件组织与 memory 沉淀机制，作为人设/风格/经验输入。
- `outputs/` 内容产物管理、上传/附件入口、内容安全和输出路径保护。
- `calendar_ops.py` 的日历读写、上下文摘要与活动导入能力（增加账号关联适配后使用）。
- `social_stats.py` 的确定性统计原语，以及现有复盘脚本里可复用的指标计算。
- Model Provider 配置、已有内容生成和媒体制作 Skills。

### 5.2 修改复用

- **Profile/Account**：新增业务 `Account`；将平台、Profile、Strategy、状态及隔离键显式绑定。现有平台登录项只作为凭证连接，不作为业务账号记录。
- **日历/发布事件**：给日历项与发布记录增加 `accountId`、`topicId`/`draftId` 可选引用；保留 Easel 的格式和 UI 交互。发布状态由用户录入，V1 不从发布 API 自动创建。
- **Analytics/Review**：统一历史作品与新发布数据字段映射；复用中位数/互动率脚本；报告记录样本量、时间范围、数据覆盖率与置信提示。
- **Ideas/Topic**：将轻量 Ideas 升级/迁移为 Topic 列表，补充来源、支柱、可执行性、TopicScore 明细、账号键、候选/主推关系与实验标记。
- **Skill/Prompt**：复用诊断、策略、选题、脚本、复盘 Skill 的相关指令和参考资料，拆出双账号专用约束与明确结构化输入/输出。
- **前端工作台**：沿用现有页面与组件风格，增加账号状态门禁、历史导入、诊断报告、策略确认、每日候选、数据录入和周复盘的流程入口。

### 5.3 必须新增开发（业务能力，不在本阶段实现）

- 双账号业务实体及账号数据隔离；生命周期状态：`NEW` → `IMPORTING` → `DIAGNOSING` → `STRATEGY_PENDING_CONFIRMATION` → `ACTIVE` → `REVIEWING`。
- HistoricalPost 人工录入、CSV/XLSX 导入、字段校验、编辑/删除和数据完整度提示。
- Initial Diagnosis、AccountBaseline、Strategy Recommendation 和 Strategy/ContentPillars 用户确认门禁。
- 抖音/小红书分别的 Strategy、Topic 候选生成与每日 3 选 1；可解释 TopicScore 及主推标记。
- 双平台结构化内容草稿；抖音脚本、小红书完整图文方案；素材标签/描述及 Topic 关联。
- 发布后 24H/72H/7D `PostMetric` 数据录入、Weekly Review、经用户确认/可追溯的 Strategy Memory 更新与反馈链。
- 初始化迁移、账号归属校验、状态门禁、样本质量/缺失数据提示以及对应审计记录。

### 5.4 V1 隐藏/禁用

- 自动发布入口/API 对 V1 运营工作流禁用；保留 Easel 通用能力代码，不直接删除上游模块。
- 自动点赞、评论、关注、私信、养号：当前未发现这些为 V1 业务闭环所需；若有通用 Skill/UI 暴露，应从 V1 工作台隐藏且不可由新增流程调用。
- V1 首期之外的平台（B站、视频号、快手、知乎、公众号等）不出现在 V1 账号开通和每日运营流程；底层 Easel 能力保留。
- 多租户、付费、激活码、行业模板市场、通用 Prompt/Strategy 配置器不开发。

## 6. 数据模型差异与建议

当前未发现 Easel 统一的业务 ORM/数据库模型。业务事实分散在以下文件：

| 当前存储 | 当前粒度 | V1 目标差异 |
|---|---|---|
| `profiles/<name>/*.md` | 人设资料和记忆 | V1 需要独立 Account、Profile 关系及 Strategy 版本/确认信息 |
| `outputs/_schedule.json` | 日期、平台、标题、状态、备注、来源、事件类型等时间线项 | 需 `accountId`、Topic/Draft/PublishedPost 关系和实际发布时间等可追踪字段 |
| `outputs/_ideas.json` | 轻量待办选题 | 需候选生成批次、3 个候选、主推、分维度得分、支柱、素材与实验关系 |
| `outputs/_analytics/publish-log.json` | 发布事件、平台、Profile、初始数据、标签等 | 需绑定 Account，并关联 PostMetric 多个 checkpoint |
| `outputs/_analytics/snapshots/{profile}/{platform}/{date}.json` | Profile/平台/日期的账号或帖子快照 | 可作辅助时序数据；需与单条发布 Post 及 24H/72H/7D 采样模型衔接 |
| `outputs/_login/`、浏览器 Profile | 平台登录状态/凭证连接 | 凭证引用要关联业务 Account，但密钥和 Cookie 不能复制进业务记录或报告 |

建议的业务关系：`Account 1—1 AccountProfile/Strategy（版本化）`；`Account 1—N HistoricalPost/Material/Topic/PublishedPost/Review/Memory`；`PublishedPost 1—N PostMetric`；`Topic 1—0..1 ContentDraft/PublishedPost`。所有读取和写入均以 `accountId` 限定。Profile 文件继续存适合自然语言维护的偏好/风格/经验，结构化指标、策略确认状态和外键应存入业务数据层，不要把 JSON 业务事实与 Markdown 长期记忆混成单一来源。

审计未在现有业务端点发现 accountId 级访问控制；当前是单用户本地产品，文件名里出现 platform 或 profile 不构成双账号数据隔离。Phase 1 应新增服务层统一做归属检查，并增加跨账号读写隔离验收。

## 7. Initial Diagnosis 与 Account Intelligence Engine 接入

### Initial Diagnosis

将诊断接在 HistoricalPost 导入与校验之后、账号进入 ACTIVE 之前。实现建议：

1. 导入层校验平台字段、发布时间、指标类型和缺失值，保留原始导入记录/错误行及来源，不把未知值伪装成 0。
2. 确定性分析层复用 `social_stats.py` 计算中位数、互动率、分组统计、样本覆盖率和样本警告；平台差异放在 Douyin/XHS 适配器。
3. Agent/Skill 层基于可追溯的统计结果、Top/Bottom 样本和 Profile 生成诊断解释、定位/支柱建议与实验计划；输出保存为结构化 Diagnosis/Recommendation 版本，并标注依据样本。
4. 用户确认 Strategy 和 ContentPillars 后才置 Account 为 ACTIVE；未确认账号可以做测试生成，但不能进入正式每日推荐。

现有 `skill-account-diagnosis` 是通用诊断指导，前置要求 Profile 六维完善且数据由用户/上下文提供；因此建议复用诊断框架和表达，不把它直接当作系统诊断 API。

### Account Intelligence Engine

在结构化数据访问层上建立共享的确定性分析服务，供首次诊断和 Weekly Review 调用；输入为指定 account 的历史作品/发布指标/Strategy 版本，输出为 Baseline、内容支柱/来源分组统计、样本完整度和分析快照。LLM 只负责对这些结果作解释、推荐与文字呈现，不能覆盖原始记录或凭空补齐缺失数据。每个输出保存计算时间、样本范围、输入记录版本/标识、算法版本和引用记录，以便复核。

发布数据检查点使用 `24H`、`72H`、`7D` 枚举，并允许因未录入而缺失；不可把账号每日快照与帖子生命周期观测混为同一事实。Strategy Memory 应保留来源 Review、确认状态和创建时间，并由 Topic Engine 显式读取。

## 8. 双账号隔离与 Strategy/Prompt 布局建议

产品账号建议固定为两条明确配置：`douyin-pet`、`xhs-developer`，平台作为不可随意混淆的枚举/校验字段。业务服务对每个查询、写入、生成任务、文件路径、缓存和会话上下文都携带 `accountId`；禁止只靠当前选中的全局 Profile 或 UI 过滤实现隔离。账号登录凭证另用 Easel 平台连接并映射到 Account。

建议在 Easel 业务目录建立显式策略模块（不是通用策略编辑器）：

```text
strategies/
  douyin-pet/
    strategy.yaml
  xhs-developer/
    strategy.yaml
prompts/
  douyin-pet/{diagnosis,topic,script,review}/
  xhs-developer/{diagnosis,topic,article,review}/
```

Profile 文件可继续放用户确认的风格与长期记忆；strategy 配置需记录 Hypothesis/Recommended/Confirmed 等阶段，不能把产品文档给的账号方向直接写成已激活策略。Prompt/策略配置由源码管理并仅针对这两个账号，避免通用配置中心扩张。

## 9. 风险、冲突与待确认事实

1. **文档路径差异（已解决）**：Phase 0.5 文档整理已将 AGENTS、产品规格和 Phase 计划移动到约定路径，并修正引用；没有复制源文档。
2. **Account 语义冲突（已确认）**：Easel 的 Accounts 页面管理平台登录连接，而产品的 Account 是业务运营对象。必须新增明确模型，避免登录状态被误当成账号生命周期。
3. **Profile 路径描述差异（已确认）**：`easel/persona.py`、Web API 使用 `profiles/`；Workspace 指令有 `easel-profiles/` 的表述。新增业务读取应调用现有 Profile 服务或统一路径，不直接复制 Workspace 文字假设。
4. **发布行为冲突（已确认）**：Easel 发布中心可真实执行发布；V1 明确用户手工发布。需将 V1 入口/调用门禁落在界面和服务两层，防止误触真实发布。
5. **历史数据可用性（推测，待业务阶段确认）**：现有账号抓取可能受登录、平台界面变化、权限及平台政策影响；产品已允许手工和 CSV/XLSX 导入，应确保诊断不依赖实时抓取。
6. **文件存储并发/一致性风险（已确认）**：多个业务数据由 JSON 原子替换或脚本各自实现；结构关系、并发写入、迁移、备份尚无统一业务层。需 Phase 1 决定最小持久化契约后再建实体，避免 `accountId` 只在 UI 层存在。
7. **现有 Analytics 范围差异（已确认）**：创作者中心抓取面向账号快照/近期作品，不等价于用户可控、可重复导入的完整历史作品数据集。诊断报告须有数据完整度和置信提示。

## 10. Phase 1～15 源码导向实施建议

以下仅为基于当前源码的实施顺序建议，不是本轮授权开始的工作。业务验收仍以 `docs/product-specs/AI_SOCIAL_OPERATOR_V1.md` 与 `docs/exec-plans/PLANS.md` 为准。

| Phase | 建议实施重点 | Easel 复用/需处理 |
|---|---|---|
| 1 双账号基础模型 | Account、Profile/Strategy 关联、状态机、统一 `accountId` 服务边界 | 复用 Profile 与本地配置模式；补业务仓储和跨账号隔离测试；平台登录连接与 Account 分开 |
| 2 历史数据导入 | 手工录入、CSV/XLSX 解析、字段校验、错误报告、数据完整度 | 复用现有上传/附件和 pandas 能力；新增历史作品服务/UI，不依赖抓取 |
| 3 Intelligence Engine / Initial Diagnosis | 按平台计算内容表现、结构、Top/Bottom，生成可追溯诊断 | 复用 `social_stats.py` 和账号诊断 Skill 框架；新增标准化数据输入、统计结果模型与 Diagnosis API |
| 4 Account Baseline | 保存样本范围、中位数、分组基线和版本 | 复用中位数/覆盖率统计；新增 AccountBaseline 持久化与展示 |
| 5 Strategy Recommendation | 诊断与 Baseline 生成账号专属定位、支柱比例、实验方向建议 | 复用策略顾问/内容策略 Skill；新增双账号专属策略模板和证据引用 |
| 6 Strategy Confirmation | 查看、编辑、确认/退回；确认后激活 Account | 复用现有表单/Modal 模式；实现服务端状态转换与强制门禁 |
| 7 Topic Engine | 读取 Active Strategy、Memory、素材和可选趋势，生成账号专属候选 | 复用趋势/选题 Skill、素材库、Profile；新增统一 Topic 服务/来源字段 |
| 8 TopicScore | 双平台权重分别打分、保存分维度证据和解释 | 复用 `social_stats.weighted_score` 原语；权重按产品文档实现，不将通用 scorer 扩成配置器 |
| 9 Daily 3 选 1 | 每账号固定候选批次与主推，未 ACTIVE 时拒绝正式推荐 | 复用 Ideas 页交互；新增批次模型、主推选择和账号状态/API 门禁 |
| 10 Content Generation | 抖音脚本与小红书图文方案结构化草稿 | 复用创作 Skills、输出目录与内容安全；新增两个专用提示与 Draft 持久化 |
| 11 素材库 | 上传后人工标签/描述、摘要建议、支柱/Topic 关联 | 复用 Outputs 上传/预览/路径安全；新增 Material 元数据/Account 归属，不开发复杂视觉识别 |
| 12 Content Calendar | 关联 Topic/Draft/Account，支持 IDEA→REVIEWED 生命周期 | 复用 `calendar_ops.py` 和 CalendarPage；新增字段迁移/状态适配 |
| 13 Published Data | 人工录入发布信息和 24H/72H/7D Metrics | 复用 publish-log/数据快照概念；V1 不调用 `api_publish` |
| 14 Weekly Review | 与 Baseline 对比，分支柱、选题、Hook 和平台内容表现 | 复用复盘脚本统计层；新增 Review 数据输入与账户级报告保存 |
| 15 Strategy Feedback Loop | Review 经确认沉淀 Memory，Topic 读取并展示影响依据 | 复用 Profile memory/Strategy Memory 思路；新增可追溯引用链与回归验收 |

## 11. Phase 0 验收记录

- Phase 0 原审计时已阅读当时工作区的 `AGENTS.md`、`AI_SOCIAL_OPERATOR_V1.md`、`PLANS.md`；Phase 0.5 完整重读规范位置下的 `AGENTS.md`、`docs/product-specs/AI_SOCIAL_OPERATOR_V1.md`、`docs/exec-plans/PLANS.md` 与本报告，并核对源码目录及这些文档的路径引用。
- 本次新增文件：`docs/audits/EASEL_V1_SOURCE_AUDIT.md`。
- 未修改 Easel 核心业务代码、配置、数据文件；未开始 Phase 1。
- 已尝试按计划执行基线检查：pytest 因当前 Python 环境未安装 `pytest` 而无法启动；前端 build/Lint 因未安装项目依赖（`tsc`、`oxlint` 不存在）而无法启动。为遵守 Phase 0 仅读取源码并新增审计文档的限制，未安装依赖。检查未能完成，不代表通过。
- Phase 0 产物已具备进入人工审阅的源码证据、复用边界、差距、风险和 Phase 1～15 顺序建议。按阶段约束，完成本阶段后停止。
