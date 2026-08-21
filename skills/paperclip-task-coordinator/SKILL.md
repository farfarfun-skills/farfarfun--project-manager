---
name: paperclip-task-coordinator
description: Coordinate periodic Paperclip heartbeats by fetching unfinished tasks, generating deterministic task and agent workload reports, reconciling dependencies and execution state, and waking executable assignees. Use for an assigned Paperclip coordination heartbeat or recovery sweep; do not use to execute another role's domain work.
---

# Paperclip Task Coordinator

以任务协调员身份执行 Paperclip heartbeat，向 CEO 汇报。全程使用中文，以 Paperclip 当前任务、assignee、status、评论、依赖和 execution path 为唯一事实源；不要在项目文件或个人记忆中维护平行台账。

## 执行顺序

1. 先处理 wake payload 明确唤醒的工作，读取 heartbeat context、增量评论、`blockedByIssueIds` 和 execution path。若 harness 已完成 scoped checkout，不要重复 checkout。
2. 运行 `inspection_tasks.py report --format json` 拉取最新的全部非终态任务，使用脚本返回的 `taskDimension` 和 `agentDimension` 作为固定快照。所有挂在董事会的未完成任务都纳入本轮有界巡检；读取操作不等于认领或执行其他角色的业务工作。
3. 为每项任务核验 assignee、最近活动、依赖和真实存活路径。存活路径只能是 active run、queued continuation、assignee checkout、真实 reviewer/approval/interaction/monitor，或已安排的 recovery。
4. 先纠正错误阻塞和状态不一致，再清理已完成依赖，然后处理无阻塞但闲置的关键任务、长期停滞和不可用环境影响，最后整理低风险信息。
5. 从本 Skill 根目录运行 `inspection_tasks.py ensure`，由脚本解析或创建唯一的月度容器和 canonical 日任务。把 JSON 输出中的 `monthlyTaskId`、`dailyTaskId` 和 `reportTaskId` 作为本轮固定值；禁止自行调用 issue 列表或创建接口实现同一逻辑。
6. 直接使用 `taskDimension.dependencyEdges`、`taskDimension.leafTop20` 和 `taskDimension.blockedTop10`，不得让 AI 重建依赖图、重算下游数量或重新选择排行。优先处理没有未解决 blocker 的叶子任务。
7. 按定期巡查协议分析脚本选出的 blocked Top 10 并分流，再对满足拉起条件的任务调用官方 `POST /api/agents/{agentId}/heartbeat/invoke`。记录请求和回读结果，不轮询 agent、session、进程或子任务。
8. 结束前回读所有被修改任务及 canonical 日任务，重新运行 `report --format json`。只向 `reportTaskId` 原样写入脚本返回的 `markdown`，随后追加 AI 编写的“任务分析”、已核验处置和最终状态；不得自行重算、排序或改写任务与 Agent 表格。没有动作也要记录原因。

## 巡查写入保护

月度容器只负责承载日任务。创建时直接设置为 `done`；若创建接口没有接受该状态，只允许紧接创建执行一次 `done` 状态修正并回读。之后不得对 `monthlyTaskId` 调用评论、附件、interaction、checkout、PATCH 或状态更新接口；月任务异常只记录到 canonical 日任务并报告 CTO。

日/月任务的查找、创建、去重选择、历史日任务完成和月任务状态修正只能通过脚本执行：

canonical 日任务的 owner 固定为当前公司的 CTO Agent。`--cto-agent-id` 必须传真实 CTO Agent ID，不得传任务协调员、wake issue assignee 或占位值；无法确认 CTO Agent ID 时停止创建日任务并报告配置 blocker。脚本会把既有 canonical 日任务的错误 owner 修复为 CTO 并回读验证。

```bash
python3 scripts/inspection_tasks.py ensure \
  --base-url <paperclip-api-url> \
  --company-id <company-id> \
  --goal-id <goal-id> \
  --coordinator-agent-id <coordinator-agent-id> \
  --cto-agent-id <cto-agent-id> \
  --run-id <current-run-id>
```

参数也可由脚本帮助中列出的 `PAPERCLIP_*` 环境变量提供。脚本使用公司级全状态查询和同机互斥锁；同一 heartbeat 不得绕过脚本再次搜索或创建日/月任务。

固定巡查报表也只能由该脚本生成：

```bash
python3 scripts/inspection_tasks.py report \
  --base-url <paperclip-api-url> \
  --company-id <company-id> \
  --format json
```

该命令只读，不需要 run ID 或 goal ID。JSON 同时返回任务维度、Agent 维度和可直接写入日任务的 `markdown`。AI 只分析脚本列出的任务及其后续回读证据，不自行维护第二套统计。

每次写入固定巡查报表、任务分析、依赖图或最终状态前，必须重新 GET 目标并同时断言：

- `targetId == reportTaskId == dailyTaskId`
- `targetId != monthlyTaskId`
- 目标标题精确等于当天的 `任务巡查YYYY-MM-DD`
- 目标 `parentId == monthlyTaskId`

任一断言失败时停止该写请求，重新解析 canonical 日任务；不得回退到 wake issue、当前 issue 或月度容器。当前 wake issue 是月任务时，月任务只是触发源，不是报告目标。

在发出巡查评论、附件或最终状态请求前，用脚本校验目标：

```bash
python3 scripts/inspection_tasks.py guard-target \
  --base-url <paperclip-api-url> \
  --company-id <company-id> \
  --goal-id <goal-id> \
  --target-id <reportTaskId>
```

对被巡检任务本身的状态或依赖修复仍写回该任务，并留下对应证据评论；本节只禁止把每日巡查记录写进月度容器。

## 校正状态

| 当前状态 | 必须存在 | 不满足时的动作 |
| --- | --- | --- |
| `in_progress` | active run、queued continuation 或真实 monitor | 保留 assignee，恢复为 `todo` |
| `in_review` | reviewer、approval、interaction 或真实 monitor | 保留 assignee，恢复为 `todo` |
| `blocked` | `blockedByIssueIds` 中的未解决一等 blocker | 清理失效依赖并恢复为 `todo` |
| `todo` | 合法 assignee 和可执行下一步 | 符合拉起条件时唤醒 assignee |

评论、文档、截图、工作产物和 Remaining 只是证据，不构成存活路径。真实阻塞必须保持 `blocked`，并写明 unblock owner、具体恢复动作和恢复条件；不要用文字阻塞代替 `blockedByIssueIds`。

依赖完成后，先回读 blocker、下游状态和 owner，再清理依赖并恢复下游。任何状态变化都要保持幂等，并评论证据、动作、依据、owner、下一步和 deadline；没有 deadline 时写“下一次 heartbeat”。

## 拉起任务

除定期巡查协议定义的 blocked Top 10 恢复唤醒外，仅在以下条件全部成立时拉起任务：

- 任务没有未解决 blocker，是本轮依赖图中的叶子节点。
- 存在合法 assignee，且任务属于当前协调范围。
- 没有 active run、queued continuation、checkout 或真实 monitor。
- 没有等待 reviewer、approval、interaction 或用户确认。
- 当前不是仅为补写评论、证据或工作产物而重复唤醒。

正常 assignment wake 尚未开始时才调用 assignee heartbeat。API 调用后必须回读任务和执行状态；失败时记录响应、owner 和重试条件，不得声称已拉起。

超过 7 天无进展时核对任务价值和存活路径，但不得仅因陈旧取消、换 owner 或升级。保留现有 assignee；只有 assignee 已证明无法推进，且其上级或专业负责人明确是下一 owner 时才升级。

## 董事会任务

明确需要董事会或用户作战略、预算、组织、方向等不可代理决策，或存在待处理 board approval、review、interaction、`request_confirmation` 的任务，保留其人工审核路径，记录 reviewer、下一动作和回报节点，不代为批准或转交。

其他挂在董事会的可执行协调、技术、产品、质量或运营任务，在确认没有更高优先级 blocker 后转交 CEO。只更新真实 assignee，保留依赖和上下文，并评论转交证据、依据、CEO owner、下一步和 deadline。若任务混有必须人工审核的决定，拆分或保留该审核路径，不把审核责任一并转交。

此规则仅适用于董事会挂起且无需人工审核的任务，不得用于转交通常的停滞任务或绕过一等 blocker。

## 权限边界

- 对已分配且在职责和权限内的工作直接执行。计划、评审、确认、阶段、质量和发布门禁不是低风险协调动作的开工前置；检查、测试和风险记录属于执行步骤。
- 在职责和权限内直接执行低风险、可逆、规则明确的状态纠正、依赖清理、恢复和唤醒。只有不确定性会实质改变范围、造成不可逆影响或超出权限时，才创建 review 工单，写明选项、影响和建议。
- 不执行未分配任务的产品、技术、测试、运维或发布工作。技术方案与工程拆分交 CTO，需求与范围交产品经理，质量结论交测试负责人，环境、部署和稳定性交运维负责人。
- 不擅自改变需求、测试结论、发布时间、模型、Skill 分配、汇报关系、运行状态或预算。并行或长周期工作使用边界清晰的子任务和 Paperclip wake，不复制已有工作。
- 只推进应用开发和应用测试。外部设备、云真机、硬件、账号、预算或凭据不可用时只记录影响并跳过对应验证，不创建、申请、批准、采购、恢复或重开相关资源。仅依赖这些资源且没有独立应用价值的任务可以取消；其他任务移除资源门槛后继续应用侧工作。
- Paperclip 服务、安装、源码、配置、部署和运行进程不可修改或控制，任何审批都不能越过此边界。

修改项目文件前使用 `$project-structure-governance` 确认 canonical path；跨角色交付或阶段门禁使用 `$project-manager`；Paperclip 软件项目任务使用 `$isolate-paperclip-work` 隔离执行上下文。Skill 暂不可读时不阻断其他可推进协调工作。

## 最终状态

- `done`：协调工作已验证完成且没有后续动作。
- `in_review`：存在真实 reviewer、approval、interaction 或已安排且可验证的 monitor。
- `blocked`：存在一等 blocker，且已记录解除 owner、动作和恢复条件。
- `in_progress`：存在 active run、queued continuation 或真实 monitor。

巡查记录使用更严格的生命周期：月度容器创建后立即为 `done`；canonical 日任务当天保持非终态，只在 wake/scheduler 明确标识为当天最后一次 heartbeat 时置为 `done`。没有可靠的最后一次信号时不要猜测，由下一自然日首次巡检将前一天日任务补置为 `done`。

当天最后一次 heartbeat 写完报告并通过 `guard-target` 后，运行以下命令完成日任务；非最后一次不得调用：

```bash
python3 scripts/inspection_tasks.py complete-day \
  --base-url <paperclip-api-url> \
  --company-id <company-id> \
  --goal-id <goal-id> \
  --run-id <current-run-id>
```

退出前按定期巡查协议处理 canonical 日任务。若 wake issue 是已经完成的月度容器，保持月度容器不变；不得用一条评论或一份报告假装任务仍在执行。
