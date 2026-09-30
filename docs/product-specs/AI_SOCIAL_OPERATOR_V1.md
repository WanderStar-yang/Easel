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

CSV/XLSX 与人工录入继续保留。抖音 V1 默认主流程为创作者中心辅助同步；OpenAPI 仅作为次要高级选项，不得作为首次诊断前置条件：

1. 抖音创作者中心辅助同步（Douyin Creator Center Assisted Sync）
2. 抖音官方 OpenAPI（次要选项；用户授权且权限可用时）
3. CSV/XLSX 导入
4. 人工录入

小红书继续使用 CSV/XLSX 与人工录入；本阶段不开发小红书自动采集。

## 6.1 历史数据来源适配器

通过 `HistoricalDataSourceAdapter` 将不同来源映射为统一 `HistoricalPost`。首期适配器包括 `DouyinOpenApiAdapter`、`DouyinCreatorCenterAdapter`、`FileImportAdapter` 和 `ManualInputAdapter`。适配器负责事实字段的标准化，不做 AI 内容分类。人工表单由用户点击保存作为确认后写入；OpenAPI、创作者中心、CSV/XLSX 批量数据须进入统一预览后由用户确认。

抖音 OpenAPI 后续接入 `video.list` 与 `video.data`，支持用户授权、分页和作品指标读取。未配置 `client_key`、`client_secret` 或所需权限时，必须显示“尚未配置抖音开放平台权限”，不得伪造结果；该状态不得阻止创作者中心、CSV/XLSX 或手动录入。

创作者中心辅助同步使用浏览器页面上用户已登录并主动打开的可见 DOM。它不得获取账号密码或 Cookie、自动登录、绕过验证码、调用逆向私有 API、自动发布或互动。不可读取的字段保持空值；真实的零值保留为 `0`，不可将缺失指标填成 `0`。扫描阶段只提取作品 ID、标题、发布时间、时长和页面实际展示的播放/点赞/评论/收藏/分享数据，不推断主体、内容来源、Hook 或 Content Pillar。

Creator Center 每次同步必须执行 Full Snapshot Sync + Snapshot Reconciliation；V1 不采用增量推送、High Water Mark 或 append-only。全量扫描、Session 去重后生成完整账号 Snapshot，再预览并在用户确认后与 `HistoricalPost` 对账。完整快照内平台唯一作品是本次同步的事实集合。用户提前结束扫描时，系统允许预览已保存作品，但该预览必须标记为不完整且只读，不能确认同步，也不能推断或标记数据库记录缺失。

稳定身份优先使用 `accountId + platform + platform_post_id`；缺少平台 ID 时使用规范化 `publish_time + title` 指纹。匹配作品保留 `HistoricalPost.id` 并更新来源可变字段；真实 `0` 可覆盖旧值，页面的 `null` 不覆盖已有非空字段。完整 Snapshot 中缺少而数据库存在的作品标记 `source_presence=MISSING` 并记录 `missing_since`，不能立即删除。

历史重复修复必须经过 Preview → Confirm。平台 ID 优先分组；历史记录缺少 ID/发布时间时才采用经过预览的 Creator Center 标题清理指纹。Canonical 优先级为：有平台 ID、字段完整度高、关联引用多、创建时间早。将其他记录的有效字段合并到 Canonical；动态指标按最新 `source_updated_at` 选取，不取最大值。确认时先将原重复记录归档、把报告等引用改到 Canonical，再删除重复活动行。

抖音卡片发布时间保存原文 `publish_time_raw`，并标准化成含 `+08:00` 的 ISO `publish_time`。只有平台明确显示作品总数且唯一快照数匹配，或页面确认末页且无字段错误时，快照才可确认。扫描原始观测数、唯一数和重复数分别展示。同步或修复改变历史作品后，已有 AccountDiagnosis 标记为 `STALE` 并提示重新诊断。同步不自动运行 Diagnosis。

当用户打开抖音首次诊断且该账号没有 `HistoricalPost` 时，页面必须明确提示先准备历史作品，并以「同步抖音数据」作为主操作；CSV/XLSX 与手动添加作为辅助入口。Chrome 扩展通过短时 account-scoped 同步会话主动回报连接、当前标签页、登录、作品页和扫描状态。浏览器扩展不可由网页直接枚举，因此未收到扩展握手时必须清楚显示“未检测到扩展连接”和安装/连接指引。确认预览写库后显示作品数，并提供主动运行首次诊断的入口，不自动运行。

Douyin 扫描会话按业务账号持久化扫描页检查点，保存原始观测数、唯一作品数、重复数、已扫页和续扫提示。去重优先使用平台作品 ID；缺 ID 时使用规范化发布时间和标题。无法确认翻页时必须保留检查点并暂停等待用户操作，不可误报为已扫到末页。会话支持暂停、继续、结束、取消；刷新或浏览器重启后允许从已有检查点续扫。原始观测数与去重后的作品数需在预览中分开展示。

作品卡片扫描只读取标题字段，忽略卡片中的编辑/权限/删除操作区。若创作者中心当前页面显示作品总数，扫描唯一作品数未达到总数时不得报告完成，需保留检查点并提示核对筛选、未加载作品或续扫位置。

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

首次诊断完成后必须建立：

```text
AccountBaseline
- accountId
- sampleSize
- periodStart
- periodEnd
- viewsMedian
- likesMedian
- commentsMedian
- favoritesMedian
- sharesMedian
- engagementRateMedian
- followersGainMedian
- profileVisitsMedian
- contentTypeBaselines[]
- sourceBaselines[]
- generatedAt
```

Baseline 是以后判断策略是否有效的比较基准。

例如：

```text
历史播放中位数：380
最近10条播放中位数：720
```

比“1000 播放算不算好”更有意义。

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
