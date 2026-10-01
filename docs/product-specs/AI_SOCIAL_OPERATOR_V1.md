# AI 小红书 / 抖音双账号运营助手 V1.0
## 产品需求与开发执行文档

- 版本：V1.0
- 阶段：个人真实账号运营验证版
- 开发基线：ZJU-REAL/Easel
- Easel 官方源码：https://github.com/ZJU-REAL/Easel
- 自动化等级：B
- 首期平台：抖音 + 小红书
- 未来可能扩展：B站等
- 当前目标：先验证 AI 运营方法是否真正改善现有账号数据，再考虑 C/D 级自动化与商业化

---

# 1. 项目背景

本项目首先只服务用户自己的两个真实账号，不按通用 SaaS 产品开发。

## 1.1 抖音宠物账号

当前已知情况：

- 粉丝接近 200
- 已发布约 30 条作品
- 单条播放通常为数百
- 大多数作品点赞低于 10
- 家中有一只缅因猫和一只布偶猫
- 当前主要内容形式：
  - 实拍猫咪视频
  - 简单字幕
  - BGM
  - 少量剪映 AI 生成视频

核心目标：

- 涨粉
- 提升播放与互动
- 形成清晰账号记忆点
- 建立长期宠物 IP

## 1.2 小红书独立开发者账号

当前已发布过部分内容。

可用真实内容资产包括：

- 独立开发
- 项目开发
- AI Coding
- 小程序
- H5
- Web
- 前端
- Node
- 接单
- 报价
- 产品思考
- 开发踩坑
- 开发过程
- 项目复盘

核心目标：

- 涨粉
- 提升流量
- 建立独立开发者 IP
- 提升专业可信度
- 长期辅助开发获客

---

# 2. 产品定位

V1.0 不是：

- 通用社交媒体 SaaS
- 自动养号机器人
- 自动刷互动工具
- 全自动发布系统

V1.0 定位为：

> 针对当前两个已有账号进行真实运营实验的 AI 个人运营助手。

核心业务闭环：

```text
添加账号
  ↓
导入历史内容
  ↓
首次账号诊断
  ↓
建立 Baseline
  ↓
发现问题与优势
  ↓
生成 Strategy Recommendation
  ↓
用户确认 Strategy / Content Pillars
  ↓
每日 3 个候选选题
  ↓
1 个今日主推
  ↓
AI 生成内容
  ↓
用户人工发布
  ↓
发布数据回收
  ↓
Weekly Review
  ↓
Strategy Memory
  ↓
下一轮推荐
```

---

# 3. 核心产品原则

## 3.1 诊断优先

账号不能在没有完成历史分析的情况下直接进入正式运营。

首次使用必须：

```text
NEW
  ↓
IMPORTING
  ↓
DIAGNOSING
  ↓
STRATEGY_PENDING_CONFIRMATION
  ↓
ACTIVE
  ↓
REVIEWING
```

只有 `ACTIVE` 状态账号允许生成正式每日运营任务。

## 3.2 当前账号定位仅是初始假设

当前预设：

### 抖音

> 缅因猫 × 布偶猫双猫家庭内容 IP

### 小红书

> 独立开发者真实做产品 / 项目 / AI Coding / 接单成长记录

以上都属于：

`Initial Hypothesis`

不能直接写死为最终运营策略。

正式定位必须经过：

`历史数据 → 诊断 → Baseline → 策略建议 → 用户确认`

## 3.3 业务针对个人，底层不过度写死

V1 允许存在：

```text
DouyinPetStrategy
XiaohongshuDeveloperStrategy
```

不要求第一版就抽象成通用行业系统。

但基础模型仍应保持：

```text
Account
Profile
Strategy
ContentPillar
Topic
Content
Metrics
Review
Memory
```

避免未来扩展时完全重写。

---

# 4. V1 自动化等级

V1 为 B 级自动化。

## 4.1 系统负责

- 历史内容管理
- 历史作品分类
- 首次账号诊断
- Account Baseline
- 定位建议
- Content Pillars 建议
- Topic 生成
- TopicScore
- 每日 3 个候选
- 1 个主推
- 抖音视频脚本
- 小红书完整图文方案
- 标题
- Hook
- 封面文案
- 话题
- 发布时机建议
- 内容日历
- 数据录入
- 24H / 72H / 7D 指标管理
- Weekly Review
- Strategy Memory

## 4.2 用户负责

- 确认第一阶段 Strategy
- 选择是否采用主推
- 拍摄
- 素材选择
- 剪辑
- 最终人工发布
- 必要的平台数据补录

---

# 5. 首次账号诊断

首次账号诊断是 V1 的强制前置能力。

流程：

```text
添加账号
  ↓
导入历史作品
  ↓
内容分类
  ↓
指标分析
  ↓
内容模式分析
  ↓
生成 Account Diagnosis
  ↓
建立 Baseline
  ↓
推荐账号定位
  ↓
推荐 Content Pillars
  ↓
推荐第一阶段实验方向
  ↓
用户确认
  ↓
正式运营
```

---

# 6. 历史数据导入

历史内容统一转换为 `HistoricalPost`，分析引擎不得依赖某一种来源。批量采集与文件导入必须经过：

```text
读取 → 标准化 → Preview → 用户确认 → Persist
```

抖音 V1 历史数据统一以 PC 端抖音创作者中心导出的作品列表 XLSX 为主要来源：用户导出文件并上传，系统识别官方列名、生成导入预览，用户确认后执行 Snapshot Reconciliation 并写入 `HistoricalPost`。CSV/XLSX 通用导入和人工录入仍可使用；小红书使用通用 CSV/XLSX 与人工录入，本阶段不开发小红书自动采集。

抖音主要操作为「导入抖音作品数据」，页面提示用户在 PC 端创作者中心的内容管理/作品管理中导出作品列表。上传后自动识别抖音官方 XLSX 格式；其他文件按通用 CSV/XLSX 规则预览。未知列作为暂未纳入 V1 诊断的字段展示，不阻塞已识别数据导入。

`DouyinCreatorExportParser` 负责官方表头标准化与别名映射。作品名称、发布时间、作品 ID/内容 ID、播放量/曝光量、点赞量、评论量、收藏量、分享量、粉丝增量映射到统一历史作品字段；体裁保留在 `content_type_raw`，不预先强行分类。缺少发布时间时显示“导出文件未提供”，保持空值，不使用当前时间替代。

每份官方导出视为完整 Snapshot，而非追加文件。身份优先使用平台作品 ID；没有 ID 时使用规范化的发布时间与标题。发布时间也缺失时使用标题/原始体裁的低置信度指纹，并明确提示匹配置信度较低，不据此标记库中其他作品缺失。匹配记录更新平台事实；新值为空时保留已有非空值，真实数值 `0` 可覆盖旧值。确认导入时若新增或更新作品，或确认重复修复，既有 AccountDiagnosis 标记为 `STALE`，包括同一作品指标无变化但由新官方快照确认更新的情形。

历史重复修复必须经过 Preview → Confirm，显示当前记录数、唯一作品估算、重复数、自动合并数和需人工确认数。稳定作品 ID 或发布时间+标题可用于自动合并；仅凭旧扫描数据标题等弱身份的重复只展示人工确认候选，不自动修改。合并时保留 Canonical ID，补入有效非空字段，动态指标按最新 `source_updated_at` 选择，重映射诊断引用后归档重复行。

数据来源标记为 `DOUYIN_OFFICIAL_EXPORT`、`FILE_IMPORT` 或 `MANUAL`。`HistoricalPost` 仍是 Account Diagnosis 的唯一历史作品事实来源，完整度按可用于诊断的字段计算；导入不自动运行诊断。
---

# 7. 历史内容模型

建议核心历史内容结构：

```text
HistoricalPost
- id
- accountId
- platform
- publishTime
- title
- duration
- contentSource
- contentType
- subjects
- topic
- hookType
- tags
- views
- likes
- comments
- favorites
- shares
- followersGain
- profileVisits
- inquiries
- note
```

## 7.1 contentSource

```text
REAL
AI
MIXED
UNKNOWN
```

用于区分真实拍摄与 AI 生成内容。

## 7.2 抖音 subjects 示例

```text
缅因
布偶
缅因+布偶
主人+猫
其他
```

## 7.3 抖音 contentType 示例

```text
单猫日常
双猫互动
双猫反差
打闹
睡觉
喂食
搞笑
养猫经验
主人吐槽
AI创意
其他
```

## 7.4 小红书 contentType 示例

```text
技术教程
AI Coding
AI工具
项目展示
项目过程
独立开发
接单
报价
程序员经历
产品思考
经验分享
其他
```

---

# 8. 抖音首次诊断

系统至少分析：

- 历史作品数量
- 播放中位数
- 点赞中位数
- 评论中位数
- 互动率中位数
- 高表现作品
- 低表现作品
- 内容结构占比
- 真实视频 VS AI 视频
- 单猫 VS 双猫
- 缅因 VS 布偶
- 有 Hook VS 无 Hook
- 有关系剧情 VS 普通记录
- 视频时长差异
- 发布时间差异
- 系列化内容表现
- 可重复验证的内容方向

重点使用：

`Median / 中位数`

避免单条异常数据扭曲判断。

---

# 9. 小红书首次诊断

系统尽可能分析：

- 曝光/浏览
- 点赞
- 收藏
- 评论
- 分享
- 涨粉
- 主页访问
- 私信/咨询
- 内容主题
- 标题类型
- 封面类型
- 是否有真实项目支撑
- 是否有搜索价值
- 不同内容支柱表现

分析逻辑不能只看点赞。

例如：

- 点赞：认同感
- 收藏：实用价值
- 评论：讨论/需求
- 主页访问：作者兴趣
- 私信/咨询：业务价值

---

# 10. Account Baseline

首次诊断完成后由用户预览并确认建立 `AccountBaseline`。Diagnosis 回答“历史账号有什么特点”，Baseline 只回答“历史账号的典型表现是多少”；Baseline 不生成定位、内容建议、选题或运营策略。两者都直接读取 account-scoped canonical unique `HistoricalPost`，不从 Diagnosis 自然语言报告反推。

Overall Baseline 必须可在作品分类尚未完成时建立。统计样本只包含未被完整快照标记缺失的 canonical unique 历史作品；原始重复行、已归档记录和旧扫描污染行均不计入 `sampleSize`。有效作品即使缺少某个指标，仍计入整体作品样本数，但该指标的样本数与覆盖率单独计算。

持久化记录需要保留生成版本和输入版本，至少包括：

```text
AccountBaseline
- id
- accountId
- version
- sampleSize
- periodStart
- periodEnd
- generatedAt
- sourceUpdatedAt
- historicalDataVersion
- status: ACTIVE | STALE
- metrics: median, p25, p75, sampleCount, coverage
- segments[]
```

每个指标均需保存 `sampleCount` 和 `coverage = sampleCount / sampleSize`。数据缺失保存 `null`，不能填 0；真实 0 是有效观测。单条作品互动率沿用 Phase 3 的透明公式：可用的点赞、评论、收藏、分享之和除以 `views`；缺失互动项不补 0，且 `views` 必须大于 0。账号级互动率使用有效单条互动率的中位数，不使用总互动数除以总播放数替代。

中位数是核心值；可附 P25/P75 表示历史通常区间。分组维度为 `content_source`、`content_type`、`subjects`、`hook_type`、`duration_bucket` 和 `publish_period`。分组必须有真实非空分类，不能生成 UNKNOWN/未分类组；分组样本至少 3 条才展示初步基准，至少 5 条才标为可用于后续正式比较。分类不完整不得阻止 Overall Baseline。

首次生成是 V1。重新生成创建 V2、V3 等新记录，旧版本保留；每个账号只有一个 ACTIVE Baseline。HistoricalPost 新增、删除、修复、更新关键指标或分类时，活动 Baseline 转为 STALE，页面提示“历史数据已发生变化，请重新生成基准。”建立前需预览有效作品数、日期范围、指标覆盖和分类覆盖，再由用户确认写入。

Baseline 是后续判断新内容相对历史表现的比较基准。Phase 4 仅提供 compare-to-baseline 服务能力，不实现 Weekly Review、Strategy Recommendation 或内容生成。

例如：

```text
历史播放中位数：380
最近10条播放中位数：720
```

比“1000 播放算不算好”更有意义。

## Phase 4.5 - Historical Content Enrichment

Phase 4.5 位于 Account Baseline 与 Strategy Recommendation 之间。目标是通过 AI 文本预分类和用户批量确认补足分组 Baseline 所需的历史标签，不在本阶段生成策略、Content Pillars、选题或内容。

首版只补三个分类字段：

- 内容来源：`REAL`（真实拍摄）、`AI`（AI 生成）、`MIXED`（真人/AI 混合）、`UNKNOWN`（暂无法判断）。只凭标题无法可靠判断来源时必须是 `UNKNOWN`。
- 出镜主体：缅因、布偶、双猫、其他、无法判断。明确出现缅因与布偶或“两只猫/双猫”才建议双猫；不从外观或账号假设推断品种。
- 内容类型：单猫日常、双猫互动、双猫反差、搞笑/趣味、养猫经验、情绪/陪伴、AI创意、其他。使用固定 V1 分类，不临时扩展大量标签。

AI Prompt 仅可使用作品标题、平台原始作品类型、已有标签和描述/备注。播放、点赞、评论、收藏、分享、互动率等表现数据不得进入分类 Prompt。模型按字段返回 `value`、`confidence`（HIGH/MEDIUM/LOW）和可选的简短 `reason`；无法判断、无效值或结构错误均保守回退为 `UNKNOWN/LOW`。Hook 继续保持“未分析”，不凭标题推断视频开头。

AI 结果持久化为 `SUGGESTED`，不会自动写入作品最终标签。分类值仍由 HistoricalPost 保存；字段来源元数据保存当前值快照、来源（`IMPORT`、`AI_CONFIRMED`、`MANUAL_CONFIRMED`）、置信度和确认时间。人工确认优先，AI 不能覆盖人工确认的字段。

历史作品页面提供批量表格、多选、三个字段的批量设置，以及“只看未分类 / 只看低置信度 / 只看 AI 建议”筛选。用户可以单独接受所选建议；“全部接受高置信度建议”必须先显示将确认的作品数和字段数，再由用户确认。分类进度按有效唯一作品分母分别展示内容来源、出镜主体、内容类型覆盖率。

确认分类会使当前 Baseline stale。用户更新 Diagnosis 后显式重新生成新 Baseline 版本：Overall 统计仍直接计算 canonical unique HistoricalPost，维持 Phase 4 的中位数、样本数和覆盖率规则；内容分组样本 <3 不展示，3–4 只展示为初步数据，≥5 才允许 Phase 5 做正式比较。

### Phase 4.5.1 - Model Provider / AI Classification Runtime

历史分类只依赖 provider-neutral `AIService` 接口。分类业务层不得依赖具体模型厂商、OpenClaw CLI 或 Gateway 地址。运行时优先尝试 Easel 当前模型设置中已配置且可连接的 Provider；支持现有 OpenAI-compatible Chat Completions 与 Anthropic-compatible 消息端点，OpenClaw Gateway 作为可选回退通道。无模型、服务不可用和配置/响应错误须分别报告 `NOT_CONFIGURED`、`UNAVAILABLE`、`ERROR`；页面应提供打开现有模型设置的入口，手动批量分类始终可用。

预分类按每批最多 20 条调用。发送内容限定为作品 ID、标题、原始作品类型、标签和描述，不发送任何表现指标。结构化响应逐条校验；单条缺失、重复、格式错误或标签越界只标记该作品失败，保留其它有效作品建议。Gateway 是 Easel Agent/聊天工作流的运行时依赖，但不是历史分类业务的唯一模型接入方式；Phase 4.5.1 不安装全局 OpenClaw，也不启用 Phase 5 能力。

### 真实账号验收记录（2026-09-30）

当前抖音账号通过 Qwen OpenAI-compatible Provider 完成 82 条作品预分类和 Baseline V2 更新。20 条随机样本中，19 条建议有标题依据、1 条最初有过度推断；Prompt 收紧后该条改为 UNKNOWN。每条内容来源、出镜主体、内容类型均生成建议；表现数据未进入模型输入。高置信度建议由用户在页面确认，另外两条具有明确标题证据的双猫互动记录经人工确认；中低置信度和 UNKNOWN 保持建议状态。

Baseline V2 仍基于 82 条 canonical unique HistoricalPost，播放中位数 578.5、互动率中位数 2.02%，与 V1 一致。主体分组：双猫 n=8、布偶 n=15、缅因 n=16；内容类型分组：单猫日常 n=11、搞笑/趣味 n=9 可用于后续正式比较，双猫互动与情绪/陪伴 n=3 仅作初步基准。来源分类目前仅有 AI n=1，因此 REAL/AI Segment 尚未达到展示门槛；不使用 UNKNOWN 形成虚假分组。Phase 4.5 验收完成后停止，未开始 Phase 5。

## Phase 5 - Strategy Recommendation

Phase 5 将历史数据、Diagnosis、Account Baseline 与账号 Profile/Hypothesis 整理为有版本的策略建议。生成建议不会确认或激活策略，不改变业务账号状态，也不写入 Phase 6 的 `operator_strategies` 确认字段。

- Overall 与 Segment Baseline 仅读取 canonical unique HistoricalPost 所生成的当前有效快照。若 Baseline stale 或 Diagnosis stale，拒绝生成，直到用户更新相应数据；没有历史数据的账号可生成 LOW 置信度、无历史证据的实验假设。
- 证据等级由服务端确定：分组样本 `>=5` 为 `SUPPORTED`，`3–4` 为 `EXPERIMENTAL`，`<3` 不展示。分类覆盖稀疏时，整体策略置信度保持 LOW。证据记录保留维度、组别、样本数、中位数和 Baseline/Diagnosis 来源。
- 模型只可润色短支柱名称；说明、目标、问题、指标、证据、标签、样本阈值、比例和整体置信度均由代码确定。模型不可用或输出不合规时使用确定性名称与文案。不得用相关性表达因果，不得补造人口属性或统计值。
- 建议输出 3–5 个 Content Pillars，带初始测试资源比例（总和 100%）、证据等级、依据、目标和四周实验问题。比例仅是实验分配，不是长期发布配比。Phase 5 不生成具体选题、日历、每日 3 选 1 或内容。
- 推荐按账号保存 V1/V2 历史版本；同一账号只有一个 `CURRENT`，旧版本为 `SUPERSEDED`，引用依据变化时标为 `STALE`。页面允许显式生成、查看历史版本和展开数据依据；不提供确认/激活操作。

### Phase 5 自动验收记录

- `StrategyRecommendationService` 复用统一 `AIService`；新增 account-scoped 版本存储、latest/history/generate API 和 Accounts 页面建议卡片。生成不会改动 `operator_strategies`、账号状态或创建 Topic。
- 自动测试覆盖分组 3/5 样本门槛、未分类/来源稀疏、模型失败与越界文字回退、比例总和、Baseline/Diagnosis/Profile stale、版本历史、账号隔离和重启持久化。全量 Python 测试 419 passed、6 skipped；前端 build 与 lint 通过（仅有两条既有 lint warning），diff check 通过。
- 当前抖音账号真实生成 V4（ACTIVE Baseline V2、82 条、整体 LOW 置信度），内容来源/类型/主体分类覆盖分别为 1%/33%/49%。三项支柱比例 40/30/30；n=3 的内容组仍标作 EXPERIMENTAL，未引用 AI 来源 n=1 分组。当前 Qwen OpenAI-compatible / Qwen3.7-Plus 实际文字调用成功。
- 小红书账号无历史数据，真实生成 V3，0 条、无 Baseline/Diagnosis、LOW 置信度，仅有 Profile 起步假设和四个实验 Pillars；未补造人口统计数据。真实 UI 已分别打开两个账号查看版本和内容；两个账号状态及 hypothesis Strategy 均未改变。
- 用户验收停点：Phase 5 完成；未进入 Phase 6 Strategy Confirmation、Topic Engine、每日 3 选 1 或内容生成。

## Phase 5.1 - Strategy Evidence Strengthening

Phase 5.1 补强真实历史作品的主体和内容类型证据，并基于更新后的 Diagnosis 与 Baseline 重新生成有版本的 Strategy Recommendation。该阶段不实现 Phase 6、不创建 Topic、不生成内容，也不要求内容来源 REAL/AI 分类覆盖率达标。

- 对 AI 重试仅选择尚未分类的字段；重新建议不得覆盖已人工确认的字段或给已分类字段制造冲突建议。模型仍只接收作品 ID、标题、原始作品类型、标签、描述，不接收表现指标。
- 用户或显式高置信度确认后，人工分类优先；UNKNOWN 保持可接受。主体和内容类型覆盖率分别以 canonical unique HistoricalPost 为分母，分类建议本身不计入最终覆盖。
- Baseline V3 继续基于相同 canonical unique HistoricalPost 集合计算总体中位数、P25/P75、每指标样本数和覆盖率。Segment 最小展示样本为 3，样本 3–4 仅作初步描述，样本 ≥5 才能进入正式比较。每个 Segment 记录相对 Overall Median 的描述性差异，不解释为因果。
- 内容来源覆盖低时，不生成 REAL/AI Segment 结论，也不以内容来源覆盖作为 Phase 5.1 的质量门槛。策略置信度至少受主体覆盖、内容类型覆盖和有效 Segment 数量约束；不足时显示 LOW 和“历史内容分类仍不足，本策略主要作为测试方案”。
- Pillar 测试比例由确定性规则结合历史播放、互动率、样本可靠度、账号目标匹配、探索价值计算；每个 Pillar 同时展示推荐原因、主要分组数据、证据等级和下一阶段待验证问题。比例仅是实验资源分配，不是因果结论或固定发布配比。
- 每账号保留 Strategy Recommendation 历史版本。基于新 Baseline / Diagnosis 显式生成下一版本；旧版本保留并转为历史状态。

验收时应记录主体与内容类型最终覆盖、Baseline V3 的 Overall 与主要 Segment 指标、策略新版本及 Pillar 比例依据、模型抽样审核、自动测试和真实 UI 流程。若覆盖目标无法在不猜测的前提下达到，应保留 UNKNOWN、维持 LOW，不得将其当成进入 Phase 6 的充分条件。

## Phase 5.2 - Subject Evidence Completion

Phase 5.2 只补充出镜主体证据；不扩大内容来源、内容类型或 Hook 分类，不开始 Phase 6、Topic Engine、每日 3 选 1 或内容生成。模型调用必须请求 subjects-only 结构化结果，输入只含作品 ID 与标题、原始作品类型、标签、描述，不含表现指标。仅文本明确支持缅因、布偶或双猫时才建议具体主体；“其他”也必须有明确的非上述主体证据。无法可靠判断就保留 UNKNOWN。

历史分类页面应有“只看出镜主体未分类”筛选、主体专属 AI 建议与多选快速人工设置主体入口。AI 结果保持建议状态；本轮高置信度批量确认只接受 subjects，不触碰其它字段。覆盖进度可以展示距离 75% 的参考数量，但不能强迫补齐或将推测写为人工确认。

Strategy Evidence Gate 除总体 subjects 覆盖和 content_type 覆盖外，还检查缅因、布偶、双猫各至少 5 条，以及未知作品是否足以改变主要比较。对于 unknown bias 采用保守上界：UNKNOWN 数量须小于最小主要分组样本且不超过总体样本 20%；该规则是比较充分性筛查，不意味着 UNKNOWN 可以推断为任一分组。未满足时 Confidence 保持 LOW，并显示“剩余未分类作品较多，主体间比较仍存在较大不确定性。”不得为提高 Confidence 降低门槛或隐藏 UNKNOWN。

主体人工确认后重新生成 Baseline 和 Strategy 新版本；Baseline Overall 直接重算 canonical unique HistoricalPost，segment 继续使用中位数和相对 Overall 的描述性差异。每个 Pillar 需展示推荐比例、历史依据、播放和互动表现、样本量、证据强度及下一阶段验证问题；双猫互动可因互动表现与账号 IP 实验价值保留测试资源，即使其历史播放低于整体，也不得将差异说成因果。

Phase 5.2 验收需记录 subjects 覆盖、UNKNOWN 数、主要主体 Baseline、Strategy 版本/比例/Confidence、与上一版本差异、测试与真实 UI 结果。是否具备 Phase 6 条件由真实证据决定；本阶段验收后停止。

### 2026-09-30 真实账号验收结果

- 当前抖音账号的 82 条 canonical unique HistoricalPost 经真实 Qwen 建议和人工审核后，主体覆盖 45/82（55%），内容类型 62/82（76%）；内容来源 1/82（1%）。主体未达 75% 目标，因为标题和标签不足以确认其余作品品种/多猫关系。未知项保留 UNKNOWN，不能据此提高策略置信度。
- Baseline V3 ACTIVE，时间范围 2025-06-24 至 2026-09-28。播放 median 578.5（n=82，100%）；点赞 8、评论 0.5、收藏 0、分享 1、互动率 2.02%（各 n=82，100%）。完播率、2 秒跳出率及平均播放时长没有可靠导入字段，保持 null。
- V3 主体分组：缅因 n=17，播放 median 975、互动率 2.27%、相对整体播放 +69%；布偶 n=17，680、2.33%、+18%；双猫 n=10，508、2.34%、-12%。内容类型分组：单猫日常 n=22，620.5、2.24%、+7%；双猫互动 n=3，491、2.58%、-15%（初步）；情绪/陪伴 n=7，742、3.79%、+28%；搞笑/趣味 n=26，753、1.56%、+30%。差异只作描述，不代表因果。
- Strategy V5 基于当前 Diagnosis 和 Baseline V3，V4 保留为 STALE 历史版本。测试比例为日常陪伴 36%、双猫互动 31%、趣味记录 33%，由播放、互动、样本可靠性、账号资料匹配和探索价值加权计算；REAL/AI 来源覆盖不进入正式结论。策略置信度 LOW，主要因主体覆盖目标未达。
- Python tests 424 passed、6 skipped；前端构建通过；lint 通过但有两条既有 warning；真实 UI 已完成 AI 建议抽样、人工确认、Diagnosis、Baseline V3 与 Strategy V5 流程。本阶段结束，不进入 Phase 6。

---

# 11. Account Diagnosis Report

首次诊断报告至少包含：

1. 账号当前状态
2. 历史数据 Baseline
3. 内容结构
4. 高表现内容
5. 低表现内容
6. 当前主要问题
7. 当前内容优势
8. 可继续验证方向
9. 建议账号定位
10. 建议 Content Pillars
11. 建议第一阶段实验计划
12. 数据完整度
13. 分析置信提示

---

# 12. Content Pillars

首次导入账号时：

```text
ContentPillarsStatus = UNCONFIRMED
```

诊断后生成 AI 建议。

例如抖音可能建议：

```text
双猫关系：35%
双猫反差：30%
养猫经验：20%
主人视角：15%
```

但必须由用户确认。

确认后：

```text
ContentPillarsStatus = ACTIVE
```

之后正式 Topic Engine 才读取该配置。

---

# 13. Topic Engine

每个 ACTIVE 账号每天生成：

```text
3 个候选选题
+
1 个今日主推
```

Topic 来源包含：

- 历史表现
- 当前 Content Pillars
- Strategy Memory
- 现有素材
- 近期热点
- 平台趋势
- 用户目标
- 已有成功内容变体
- AI 原创方向

V1 不要求所有来源都必须实时联网。

---

# 14. 抖音 TopicScore

建议初始权重：

```text
当前策略匹配度：25%
历史内容表现支持：20%
素材可执行性：20%
互动潜力：15%
内容新鲜度：10%
系列化能力：5%
制作成本：5%
```

权重后续允许根据真实账号数据调整。

---

# 15. 小红书 TopicScore

建议初始权重：

```text
目标用户需求：25%
当前账号定位：20%
真实经历支撑：20%
IP / 信任价值：15%
历史数据支持：10%
搜索价值：5%
制作成本：5%
```

---

# 16. 每日运营输出

每个账号每天：

```text
主推 Topic A
备选 Topic B
备选 Topic C
```

每个 Topic 至少展示：

- 选题
- 选题来源
- 推荐理由
- TopicScore
- 对应 Content Pillar
- 目标
- 制作难度
- 是否已有素材
- 是否属于实验内容

---

# 17. 抖音内容生成

选择 Topic 后生成：

- 内容主题
- 推荐理由
- 内容目标
- Hook
- 前 3 秒设计
- 视频结构
- 镜头建议
- 字幕
- 建议时长
- 标题候选
- BGM 类型
- 话题
- 评论区互动设计
- 发布时间建议
- 可使用的已有素材
- 实验标签

---

# 18. 小红书内容生成

生成：

- 标题 × 5
- 封面文字
- 开头 Hook
- 内容结构
- 完整正文
- 配图结构
- 截图建议
- 项目素材建议
- CTA
- 评论区互动问题
- 推荐话题
- 发布时间建议

---

# 19. 宠物素材系统

V1 原“AI 理解宠物素材”调整为：

> 宠物素材管理、标签与选题匹配

V1 不要求复杂的视频视觉模型识别。

## 19.1 V1 支持

上传视频/图片后：

- 生成缩略图
- 用户选择标签
- 用户填写一句描述
- AI 根据标签+描述生成素材摘要
- AI 判断适合 Content Pillar
- AI 推荐可用选题方向
- Topic Engine 可以匹配现有素材

宠物素材标签示例：

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

## 19.2 V1.1 再考虑

AI 自动视频理解：

```text
视频
  ↓
关键帧
  ↓
视觉模型
  ↓
主体/动作/场景
  ↓
自动标签
  ↓
人工确认
```

不纳入 V1 强制验收。

---

# 20. 内容日历

内容状态：

```text
IDEA
  ↓
SELECTED
  ↓
DRAFT
  ↓
READY
  ↓
PUBLISHED
  ↓
REVIEWED
```

记录：

- accountId
- topicId
- draftId
- platform
- status
- plannedPublishTime
- actualPublishTime
- publishedUrl
- reviewStatus

---

# 21. 发布数据

发布后支持：

- 24H
- 72H
- 7D

三个关键节点。

建议：

```text
PostMetric
- postId
- checkpoint
- views
- likes
- comments
- favorites
- shares
- followersGain
- profileVisits
- inquiries
- recordedAt
```

---

# 22. Account Intelligence Engine

首次诊断与后续复盘共用同一分析引擎。

首次：

```text
历史数据
  ↓
Initial Diagnosis
```

每周：

```text
近期数据
  ↓
Weekly Review
```

阶段性：

```text
历史 + 新数据
  ↓
Strategy Review
```

输出持续更新：

- AccountProfile
- AccountBaseline
- ContentPillars
- StrategyMemory

---

# 23. Weekly Review

每周至少输出：

- 本周发布数量
- 与 Baseline 对比
- 各 Content Pillar 表现
- 主推选题表现
- Hook 表现
- 视频时长表现
- 发布时间表现
- REAL / AI 内容表现
- 高表现内容共性
- 低表现内容共性
- 本周实验结论
- 下周调整建议

---

# 24. Strategy Memory

每账号独立保存长期经验。

例如：

```text
双猫互动连续两周高于Baseline
AI宠物视频低于真实视频
15-20秒内容近期表现更好
带关系冲突的标题表现较好
项目复盘类小红书收藏率较高
接单报价类内容带来更多主页访问
```

Topic Engine 和 Content Generation 必须读取相关 Strategy Memory。

---

# 25. 页面结构

V1 页面：

1. 今日运营
2. 账号管理
3. 首次诊断 / 账号报告
4. 选题雷达
5. 内容创作
6. 素材库
7. 内容日历
8. 数据分析
9. 周复盘

---

# 26. 首页状态

## 26.1 未完成诊断

显示：

- 账号名称
- 历史作品数量
- 数据完整度
- 当前状态
- `开始账号诊断`

不展示正式每日运营建议。

## 26.2 已完成诊断并确认策略

展示：

### 抖音

- 今日主推
- 备选 1
- 备选 2

### 小红书

- 今日主推
- 备选 1
- 备选 2

---

# 27. 核心数据模型

至少需要：

```text
Account
AccountProfile
AccountDiagnosis
AccountBaseline
ContentPillar
HistoricalPost
Material
MaterialTag
Topic
TopicScore
ContentDraft
ContentCalendar
PublishedPost
PostMetric
WeeklyReview
StrategyMemory
Experiment
```

具体字段必须结合 Easel 现有数据结构设计，不允许脱离源码另起一套完全不兼容模型。

---

# 28. 当前 Strategy

V1 允许明确存在：

```text
DouyinPetStrategy
XiaohongshuDeveloperStrategy
```

建议结构：

```text
strategies/
  douyin-pet/
  xhs-developer/
```

Prompt 可拆：

```text
prompts/
  douyin-pet/
    diagnosis/
    topic/
    script/
    review/

  xhs-developer/
    diagnosis/
    topic/
    article/
    review/
```

---

# 29. Easel 基线

官方源码：

https://github.com/ZJU-REAL/Easel

原则：

```text
阅读 Easel
  ↓
源码审计
  ↓
确认可复用模块
  ↓
二次开发
```

不是：

```text
参考 Easel
  ↓
重新写一套
```

---

# 30. Easel 四类改造清单

Phase 0 必须以真实源码为准生成四张清单。

## 30.1 直接保留

预计可能包括：

- Agent 基础框架
- Profile 能力
- Skills
- Web 工作区
- 长期记忆
- Content Calendar 基础能力

最终以审计结果为准。

## 30.2 修改复用

预计可能包括：

- Account/Profile
- Trend
- Topic Planning
- Content Generation
- Analytics
- Calendar

## 30.3 新增开发

至少包括：

- 双账号隔离
- 历史数据导入
- Initial Diagnosis
- Account Baseline
- Strategy Recommendation
- Content Pillars Confirmation
- 双 Strategy
- 3选1
- TopicScore
- 宠物素材标签
- 数据回收
- Weekly Review
- Strategy Memory
- 素材与选题关联

## 30.4 V1 隐藏/删除

包括：

- 自动发布
- 自动评论
- 自动点赞
- 自动关注
- 自动私信
- 多用户 SaaS
- 支付
- 激活码
- B站
- 视频号
- 快手
- 知乎
- 公众号

---

# 31. V1 不做范围

禁止为了未来商业化提前开发：

- 行业选择器
- 通用模板市场
- 通用 Prompt 配置中心
- 动态 Strategy 编辑器
- 多租户
- 用户套餐
- 商业后台
- 自动养号
- 自动互动
- 自动发布

---

# 32. 开发顺序

完整 Phase：

```text
Phase 0  Easel 源码审计
Phase 1  双账号基础模型
Phase 2  历史数据导入
Phase 3  Account Intelligence Engine / Initial Diagnosis
Phase 3.5  Douyin Historical Data Acquisition
Phase 4  Account Baseline
Phase 5  Strategy Recommendation
Phase 6  Strategy Confirmation
Phase 7  Topic Engine
Phase 8  TopicScore
Phase 9  Daily 3选1
Phase 10 Content Generation
Phase 11 素材库
Phase 12 Content Calendar
Phase 13 Published Data
Phase 14 Weekly Review
Phase 15 Strategy Feedback Loop
```

详细执行规则见：

`docs/exec-plans/PLANS.md`

---

# 33. V1 验收标准

## 33.1 账号

必须：

- 同时管理当前两个账号
- 两账号 Profile 独立
- 两账号 Strategy 独立
- 两账号数据隔离

## 33.2 首次诊断

必须：

- 导入历史内容
- 分类历史内容
- 分析历史数据
- 建立 Baseline
- 输出诊断报告
- 推荐 Strategy
- 推荐 Content Pillars

## 33.3 状态控制

必须保证：

未完成 `Initial Diagnosis + Strategy Confirmation` 的账号，不进入正式每日运营。

## 33.4 日常运营

每账号每天：

- 3 个候选 Topic
- 1 个主推

## 33.5 抖音内容

必须生成：

- Hook
- 视频结构
- 镜头/字幕建议
- 标题
- 话题
- 素材建议
- 发布时间建议

## 33.6 小红书内容

必须生成：

- 标题
- 封面文字
- Hook
- 完整正文
- 配图建议
- CTA
- 话题
- 发布时间建议

## 33.7 素材

必须：

- 上传
- 标签
- 描述
- 分类
- 选题关联

不强制 AI 自动视频视觉识别。

## 33.8 数据闭环

必须完整支持：

```text
发布
  ↓
24H / 72H / 7D 数据
  ↓
Weekly Review
  ↓
Strategy Memory
  ↓
下一轮 Topic
```

闭环不完整，V1 不视为完成。

---

# 34. 4 周真实运营验证

V1 开发完成后进入 4 周验证期。

## 抖音

建议：

每周 4～5 条。

## 小红书

建议：

每周约 3 篇。

V1 不要求 4 周内出现爆款。

---

# 35. V1 成功标准

主要判断：

1. 新内容是否持续跑赢历史 Baseline
2. 是否找到至少 1～2 个明显优于历史数据的内容模型
3. 互动率是否改善
4. 涨粉效率是否改善
5. 系统是否明显降低“今天发什么”的决策成本
6. Weekly Review 是否真正影响下一轮推荐
7. Strategy Memory 是否能够被后续选题调用

---

# 36. 后续版本

## V1.1

优先考虑：

- 宠物视频 AI 自动理解
- 更完善趋势数据
- 更智能素材匹配
- TopicScore 调优
- Prompt 调优
- 自动数据同步

## V2

效果验证后考虑：

- C 级自动化
- 用户确认后自动发布
- B站
- 更多账号

## 后续商业化

只有：

```text
真实账号有效
  ↓
运营方法稳定
  ↓
能够复现
```

之后再考虑：

- 通用 AccountStrategy
- 行业模板
- 多用户
- SaaS
- 订阅
- 收费

---

# 37. 最终闭环

```text
添加账号
  ↓
导入历史内容
  ↓
首次账号诊断
  ↓
Baseline
  ↓
发现问题 / 优势
  ↓
Strategy Recommendation
  ↓
用户确认
  ↓
每日 3 个候选
  ↓
1 个主推
  ↓
AI 内容生成
  ↓
人工发布
  ↓
发布数据回收
  ↓
Weekly Review
  ↓
Strategy Memory
  ↓
下一轮 Topic
  ↺
```
