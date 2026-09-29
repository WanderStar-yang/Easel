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

# 8.5 Phase 3.5 - Douyin Historical Data Acquisition

## 目标

低成本、可审阅地将用户本人抖音账号的历史作品事实数据同步到 `HistoricalPost`，同时保持数据来源可替换。只处理历史作品和平台实际展示的指标，不执行内容分类。

## 复用与架构

- Phase 2 `HistoricalImportService` 的行标准化、校验、重复检查、预览与确认写库；OpenAPI、Creator Center、CSV/XLSX 批量来源统一走 Preview → Confirm → Persist。手工表单在用户点击保存时确认后写入。
- Phase 3 Intelligence Engine 继续只读取 `HistoricalPost`，不得直接耦合抖音 API 或浏览器。
- 新增 `HistoricalDataSourceAdapter` 接口与 `DouyinOpenApiAdapter`、`DouyinCreatorCenterAdapter`、`FileImportAdapter`、`ManualInputAdapter`。OpenAPI 适配器以配置/授权占位接入 `video.list` 和 `video.data`；无正式密钥或权限时显示“尚未配置抖音开放平台权限”，不得返回伪造作品。
- 现有 Easel 有 Playwright 登录态抓取，但未提供创作者中心用户主动查看页面的 DOM 读取通道。Creator Center 使用最小 Chrome Manifest V3 Browser Helper：仅响应用户在 `creator.douyin.com` 上的主动扫描操作，读取当前渲染的可见 DOM；用户翻页后可继续扫描并累计。扩展不得读凭证/Cookie、自动登录、绕过验证码或调用私有 API。若页面结构不匹配，显示无法识别并允许用户改用 CSV/人工录入。

## 同步与数据规则

- 业务 UI 先为指定 `douyin-pet` 创建一个限时同步会话；扩展检查当前标签页域名、会话状态并发送扫描结果。不得仅凭客户端 accountId 接受跨账号或过期会话。
- 采集字段限于 platform_post_id、title、publish_time、duration、views/play_count、likes、comments、favorites、shares。不可见字段为 `null`；指标数值 `0` 保留为真实零值。
- 采集过程不推断 REAL/AI、猫主体、Hook、Content Pillar、话题或其他分类；已有用户标签在更新时保留。
- 抖音作品来源记录 `DOUYIN_OPEN_API`、`DOUYIN_CREATOR_CENTER`、`FILE_IMPORT` 或 `MANUAL`；同时记录 `source_updated_at`，账号级保存 `last_sync_at`。
- 有 `platform_post_id` 时按账号范围 upsert 可变化的指标，不产生重复帖子；无作品 ID 时复用 Phase 2 (account_id, platform, publish_time, title) 去重。导入预览分别汇总扫描、新增、将更新、重复、缺字段及错误行。只有明确确认后才写库。既有 CSV/XLSX 手工导入重复仍可跳过，不覆盖。
- 最近同步完成只显示数量并提供“重新运行首次诊断”；不自动执行 Phase 3 Diagnosis。完整度继续由 `HistoricalPostService.completeness()` 依据实际字段计算，不与来源绑定。

## API / UI

- 在现有历史帖子路由下增加开始同步会话、查询会话预览和 OpenAPI 配置状态端点；扩展上送可见 DOM 记录。预览结果最终通过同一 HistoricalImportService 和既有确认写入合同保存。
- 抖音账号历史页主操作为“从抖音同步”，显示登录指引、扫描状态和最后同步来源/时间、新增/更新/重复计数；辅助保留 CSV/XLSX 导入和手动新增。确认预览后显示“历史数据已同步，共 XX 条”并链接主动重跑诊断。
- 小红书 UI、数据入口和导入逻辑不变。Easel 的原有 `/api/accounts`、登录、发布能力与页面合同保持兼容。

## 验收与测试

- Creator Center 未登录、已登录、空列表、多页累计、缺失指标、实际零指标、错误 DOM 与扫描失败。
- 同步来源、过期/跨账号会话隔离、平台作品 ID upsert、无 ID 重复规则、第二次同步的插入/更新、last_sync_at/source_updated_at。
- Preview 阶段不写业务数据库；确认后原子持久化；Phase 3 可读取同步数据；小红书隔离。
- CSV/XLSX 和人工 CRUD 回归，旧 `/api/accounts` 保持可用。
- OpenAPI 无凭据/权限时只返回未配置状态。无授权环境时使用合成 DOM 样本测试适配器，不写死真实用户数据。

---

# 9. Phase 4 - Account Baseline

## 目标

建立账号历史基线。

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

- Baseline 基于真实历史样本
- 显示样本数
- 显示时间范围
- 可作为后续 Weekly Review 对照

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
