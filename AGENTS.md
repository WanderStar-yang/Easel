# AGENTS.md

# AI Social Operator V1 - Codex Development Instructions

## 1. 项目身份

本项目是基于 **ZJU-REAL/Easel** 二次开发的个人社交媒体 AI 运营助手。

Easel 官方仓库：

https://github.com/ZJU-REAL/Easel

当前 V1.0 **不是通用 SaaS**，也不是全自动养号工具。

V1.0 只服务当前两个真实账号：

1. 抖音宠物账号
   - 当前粉丝：接近 200
   - 历史作品：约 30 条
   - 当前播放：通常数百
   - 当前点赞：多数低于 10
   - 素材主体：一只缅因猫 + 一只布偶猫
   - 现有内容：真实猫咪视频、简单字幕+BGM、少量剪映 AI 视频
   - 核心目标：涨粉、提升流量、建立宠物 IP

2. 小红书独立开发者账号
   - 已发布过历史内容
   - 内容候选方向：独立开发、真实项目、AI Coding、接单、产品开发、前端/小程序/H5 等
   - 核心目标：涨粉、提升流量、建立个人 IP，并长期兼顾开发获客

---

## 2. 唯一产品需求来源

开始任何业务功能开发前，必须完整阅读：

`docs/product-specs/AI_SOCIAL_OPERATOR_V1.md`

该文件是 V1.0 产品范围、业务规则与验收标准的唯一事实来源。

若源码现状与产品文档存在冲突：

1. 不得自行猜测；
2. 不得擅自重构；
3. 先记录冲突；
4. 给出基于现有源码的解决方案；
5. 等待确认后再进行超出原计划的调整。

---

## 3. V1 核心闭环

必须围绕以下闭环开发：

```text
添加账号
  ↓
导入历史内容
  ↓
Initial Diagnosis 首次账号诊断
  ↓
Account Baseline 历史基线
  ↓
Strategy Recommendation 运营策略建议
  ↓
用户确认 Strategy / Content Pillars
  ↓
每日 3 个候选选题
  ↓
自动推荐 1 个主推
  ↓
内容生成
  ↓
用户人工发布
  ↓
录入 24H / 72H / 7D 数据
  ↓
Weekly Review
  ↓
Strategy Memory
  ↓
下一轮选题
```

### 强制约束

未完成以下两项的账号：

- `Initial Diagnosis`
- `Strategy Confirmation`

不得进入正式每日运营状态。

允许生成测试内容，但不得标记为正式运营建议。

---

## 4. 当前 V1 自动化等级

V1 为 **B 级自动化**。

系统负责：

- 历史内容分析
- 账号诊断
- Baseline
- 定位/内容支柱建议
- 每日选题
- TopicScore
- 每日 3 选 1
- 抖音脚本
- 小红书完整图文方案
- 标题
- Hook
- 话题
- 发布时间建议
- 内容日历
- 发布数据记录
- 周复盘
- Strategy Memory

用户负责：

- 最终选题确认
- 拍摄
- 剪辑
- 素材确认
- 手动发布
- 必要的数据录入

---

## 5. V1 禁止提前开发

除非产品文档后续明确修改，否则 V1 不允许开发：

- 自动发布
- 自动点赞
- 自动评论
- 自动关注
- 自动私信
- 自动养号
- 多租户
- 多用户商业权限
- 套餐
- 支付
- 激活码
- 商业管理后台
- 行业模板市场
- 通用 Prompt 配置中心
- 通用 Strategy 可视化配置器
- B站运营
- 视频号运营
- 快手运营
- 知乎运营
- 微信公众号运营

不要为了“以后可能商业化”提前增加复杂抽象。

---

## 6. Easel 二次开发原则

禁止脱离 Easel 现有源码重新实现已存在能力。

任何功能开发前必须：

1. 搜索对应 Easel 现有模块；
2. 理解当前实现；
3. 判断该能力属于：
   - 直接保留
   - 修改复用
   - 新增开发
   - V1 隐藏/删除
4. 优先复用现有架构；
5. 不允许为了实现方便而大规模推翻 Easel 原有结构。

### Phase 0 强制要求

正式编码前必须完成：

`docs/audits/EASEL_V1_SOURCE_AUDIT.md`

该报告至少包含：

- 实际技术栈
- 关键目录
- Agent / Skill / Profile / Calendar / Analytics / Storage 等实现
- V1 可直接复用模块
- V1 需修改模块
- V1 新增模块
- V1 隐藏/删除模块
- 数据模型差异
- 双账号隔离建议
- Account Intelligence Engine 接入建议
- Phase 1～Phase 15 实施建议

Phase 0 未完成前，不进入正式业务编码。

---

## 7. 双账号策略原则

V1 不开发通用行业策略配置器。

允许明确存在：

```text
strategies/
  douyin-pet/
  xhs-developer/
```

Prompt 也允许按账号策略拆分：

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

### 重要

当前对两个账号的定位仅是 **Initial Hypothesis**。

例如：

- 抖音：缅因猫 × 布偶猫双猫家庭内容 IP
- 小红书：独立开发者真实做产品 / AI Coding / 接单成长记录

这些不能直接视为最终策略。

正式 Strategy 必须经过：

`历史数据 → Initial Diagnosis → Baseline → Strategy Recommendation → 用户确认`

后才生效。

---

## 8. 开发方式

整个项目严格分 Phase 执行。

禁止一次性尝试完成整个 V1。

每个 Phase 开始前必须先说明：

- 本阶段目标
- 对应 Easel 现有模块
- 准备直接复用的内容
- 准备修改的内容
- 准备新增的文件
- 数据结构影响
- API 影响
- UI 影响
- 兼容性风险
- 测试方案

每个 Phase 完成后必须：

- Build
- Lint
- Test
- 必要的手动验证
- 检查 git diff
- 更新 CHANGELOG / 执行记录
- 汇报实际修改
- 汇报测试结果
- 汇报未解决问题
- 明确该 Phase 是否达到验收标准

完成一个 Phase 后，不得自动开始下一 Phase。

---

## 9. 执行计划

必须阅读：

`docs/exec-plans/PLANS.md`

正式开发计划存放于：

`docs/exec-plans/ACTIVE_PLAN.md`

若 `ACTIVE_PLAN.md` 不存在：

先根据源码审计结果生成。

不要把聊天记录当作开发计划。

---

## 10. 当前第一任务

当前第一任务固定为：

# Phase 0 - Easel 源码审计

本阶段：

- 不开发正式业务功能；
- 不重构核心代码；
- 不引入未来商业化能力；
- 只允许读取源码，并生成必要的 docs 审计文件。

目标产物：

`docs/audits/EASEL_V1_SOURCE_AUDIT.md`

完成后停止，等待下一步确认。
