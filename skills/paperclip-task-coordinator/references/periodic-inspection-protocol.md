# 定期巡查协议

在每次 Paperclip 周期性 heartbeat 创建或更新日/月巡查记录、依赖图和叶子任务表时读取本协议。日/月任务控制面由 `scripts/inspection_tasks.py` 唯一实现；本节是脚本行为契约，不授权 agent 重新实现同一流程。

## 日月任务

按当前日期计算 `YYYY-MM` 和 `YYYY-MM-DD`。日/月任务解析必须使用公司级 issue 列表，覆盖包括 `done`、`cancelled` 在内的全部状态，并使用完整标题精确匹配。不得携带当前协调员的 `assigneeAgentId` 过滤条件，因为日任务 owner 是 CTO；按 assignee 查询会漏掉已存在的日任务并导致重复创建。

- 月度容器标题：`任务巡查YYYY-MM`
- 日度任务标题：`任务巡查YYYY-MM-DD`

写权限矩阵固定如下：

| 任务 | Owner | 用途 | 任务协调员可写内容 |
| --- | --- | --- | --- |
| 月度容器 | 任务协调员 | 当月容器和日任务父任务 | 创建即 `done`；随后只读，不得写评论、附件、日常状态或巡查结论 |
| 日度任务 | CTO | 当日巡查和技术执行 | 当天写巡查结果；当天最后一次 heartbeat 或下一自然日置为 `done` |

每次 heartbeat 只运行一次 `inspection_tasks.py ensure`。脚本必须满足：

1. 公司级精确搜索当月容器。存在多个时按 `createdAt` 升序、任务 ID 升序选择第一个作为 canonical 月任务，记录其他 ID，不创建平行月任务；不存在时创建一次，owner 为任务协调员、status 为 `done`，并回读 goal、owner 和状态。若创建接口未接受 `done`，只允许紧接创建执行一次状态 PATCH 到 `done` 并再次回读；此后月任务冻结。
2. 固定 `monthlyTaskId` 后，公司级精确搜索当天标题，不限定 assignee，不排除终态。先选择 `parentId == monthlyTaskId` 且 `goalId` 正确的候选，再按 `createdAt` 升序、任务 ID 升序选第一个作为 canonical 日任务。只要存在任一精确标题候选，本轮就不得 POST 新日任务。
3. 没有任何精确标题候选时，脚本在同机互斥锁内最多调用一次创建接口，设置 `parentId=monthlyTaskId`、正确 `goalId`、owner=CTO、初始状态=`todo`。
4. 创建成功后立即重新执行公司级全状态精确搜索，再按上一步规则确定 `dailyTaskId`。即使创建响应已经返回 ID，也不得跳过复查后直接写评论。
5. 创建复查或后续巡检发现多个候选时，始终只使用同一排序规则选出的 canonical 日任务。不要继续创建，也不要向其他重复任务写巡查结果；在 canonical 日任务中记录重复 ID 并报告 CTO。不要自动删除已有重复任务。
6. 设置 `reportTaskId=dailyTaskId`。当前 wake issue 是月度容器时，月任务只作为触发源；禁止向它 POST 评论、附件、interaction、checkout、PATCH 或状态更新。
7. 日任务的 `parentId`、owner 或 goal 不符合契约时，先回读并记录旧值，再对 canonical 日任务执行最小、低风险、可逆 PATCH，并回读验证。初始创建后的 status 不属于结构修复，不得仅为巡查而重开已经 `done` 或 `cancelled` 的日任务。已有 canonical 月任务若不是 `done`，只允许一次状态修正为 `done` 并回读；其他结构或字段异常只在日任务报告 CTO，不 PATCH 月任务。
8. 日任务不存在或创建失败时不伪造日任务评论，也不得改写月任务作为替代。记录 API 响应、owner 和下一次重试条件；同类控制面写入连续失败两次后本轮停止重试。

## 写入目标断言

在每一次日常评论、依赖图附件、叶子表或最终状态写请求前重新 GET `reportTaskId`，并验证：

```text
reportTaskId == dailyTaskId
reportTaskId != monthlyTaskId
title == 任务巡查YYYY-MM-DD
parentId == monthlyTaskId
```

每次写入前调用 `inspection_tasks.py guard-target`。验证失败时停止写入并重新运行 `ensure`；不得使用 `PAPERCLIP_TASK_ID`、wake issue ID、“当前任务”或最近创建响应中的 ID 作为隐式回退目标。只有被巡检任务自身的状态和依赖修复可以写回该被巡检任务。

## 日任务完成时机

日任务按其标题中的日期归档，完成条件只能是以下两种之一：

1. **当天最后一次 heartbeat**：wake payload 或 scheduler context 明确声明这是该日期最后一次计划执行。写完当次评论、依赖图和叶子表并回读成功后，运行 `inspection_tasks.py complete-day`。
2. **下一自然日补完成**：`inspection_tasks.py ensure` 会在处理当天任务前，将所有日期早于当前公司日期且尚未终态的 canonical 日任务置为 `done`，并在输出的 `completedPastDailyTaskIds` 中返回这些 ID。

没有明确的最后一次调度信号时，不得根据当前小时、执行次数或个人判断猜测“最后一次”。当天的日任务保持现有非终态；最迟由下一自然日首次巡检补完成。已经 `done` 或 `cancelled` 的日任务不得重开。

历史日任务的收口写入也必须先验证其精确日期标题、canonical 身份和正确月度 `parentId`；不得把收口评论写到月度容器。

## 巡检快照

从 Paperclip 最新快照读取所有非终态任务，并至少保留以下字段用于本轮判断：

- 带公司前缀的可点击任务链接
- status、assignee、最近活动时间
- `blockedBy`、`blocks` 和 `blockedByIssueIds`
- active run、queued continuation、checkout 和 monitor
- reviewer、approval、interaction 和 scheduled recovery

不要把快照另存为项目台账。下一次 heartbeat 必须重新从 Paperclip 拉取。

## 依赖图和叶子任务

对任务和边去重，省略终态任务。边方向固定为：

```text
被 block 的任务 -> blocker 任务
```

没有未解决 blocker，也就是没有出边的非终态任务，是叶子节点。沿反向边统计每个叶子的下游非终态任务数，按下游任务数降序、任务 ID 升序取前 20 个。

叶子已在执行、等待真实审核或没有合法唤起路径时仍可列入表，但动作必须写“观察”或“交 owner”，不能声称已拉起。每日评论只保留一张依赖图和一张叶子 Top 20 表，不再维护依赖清单或第二张叶子表。

## 阻塞任务 Top 10

每轮从最新快照中的 `blocked` 任务按未完成下游任务数降序、任务 ID 升序取前 10 个，核对评论、依赖和 execution path 后分流：

- 公网 IP、云真机、外部设备等外部资源导致的阻塞：评论说明本轮不考虑该外部资源，仅以本地跑通为交付标准；移除仅由该资源造成的 blocker，恢复为 `todo` 并拉起原 owner。
- 需要董事会确认业务逻辑、范围或方向：保留 `blocked`，交由董事会，并在评论中写清待确认问题、可选项和影响。
- 其他阻塞：评论要求优先完成可在本地跑通的部分、尽量不阻塞其他任务，并直接拉起原 owner。真实依赖仍保留；此次恢复唤醒不代表 blocker 已解除。

第三类恢复唤醒是“无未解决 blocker 才能拉起”规则的唯一例外。仍需核对合法 assignee，且不得重复唤醒已有 active run、queued continuation、checkout 或真实 monitor 的任务。

## 依赖图输出

在运行临时目录生成 `.drawio` 源文件，将任务链接、status、owner 和边替换为本次 API 快照数据，只把导出的 PNG 上传到当日日任务评论。上传确认后删除临时源文件。没有依赖边时，绘制一个“当前无未解决依赖”的叶子节点。

画布必须根据本次内容计算：

1. autolayout 后遍历所有顶层和嵌套节点、容器及边的 waypoint，计算完整边界。
2. 边界四周至少扩展 80px；存在负坐标时整体平移为非负。
3. `pageWidth` 和 `pageHeight` 向上取整到 10px，保持 `pageScale=1`。不要使用固定 A4、固定 850x1100 页面或上次巡查的尺寸。
4. PNG 导出只限制预览宽度 `--width 2000`，不设置固定高度或截图框。
5. 导出前后验证所有节点、容器和边折点均在页面内。发现越界时重新计算后再导出。

若 draw.io CLI 不可用，至少完成 XML 边界验证，并在日任务中记录 PNG 未生成；不得伪造上传成功。

## 日任务评论

评论只写已经回读的事实，不包含密钥、cookie、个人敏感信息或完整运行日志。所有修改 issue 的请求携带当前 run ID。

```markdown
## 任务巡查 YYYY-MM-DD HH:mm

- 范围：todo N / in_progress N / in_review N / blocked N
- 结果：恢复 N / 唤起 N / 清理依赖 N / 取消 N / 阻塞 N / 升级 N
- 证据：<关键 API 回读、任务链接和依赖图附件>
- 风险：<风险或“无新增风险”>
- Owner：<当前回报 owner>
- 下一步：<下一动作>
- Deadline：<明确时间或“下一次 heartbeat”>

| 叶子任务 | Status | Owner | 下游任务数 | 动作 |
| --- | --- | --- | ---: | --- |
| <任务链接> | <status> | <owner> | <count> | <唤起/观察/交 owner> |
```

退出前回读 canonical 日任务的最终状态、评论和关键 API 结果。当天非最后一次 heartbeat 时保留其非终态；当天最后一次或日期切换收口时，最后一条日任务状态更新必须包含 `done`、已完成、证据、风险、owner 和收口时间。月度容器保持 `done` 且不再更新。
