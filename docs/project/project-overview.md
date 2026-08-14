# 项目说明

> 固定路径：`docs/project/project-overview.md`

## 基本信息

- 项目名称：FarFarFun Project Governance
- 项目简介：面向 Codex 的项目结构与研发全生命周期治理 Skill 集合
- 项目负责人：FarFarFun
- 代码仓库：https://gitee.com/farfarfun-skills/farfarfun--project-manager

## 应用清单

<!-- project-structure:applications:start -->
| 应用 | 路径 | 技术 Profile | Owner | 用途 |
| --- | --- | --- | --- | --- |
| 无（单应用仓库） | - | - | - | - |
<!-- project-structure:applications:end -->

## 项目目标

- 将项目结构、研发产物、Agent 执行边界和服务发布条件转化为可复用的 Codex Skills 与确定性检查器。
- 为生命周期门禁统一提供 `allow`、`revise`、`block` 决策协议和可执行修复建议。

## 项目范围

### 范围内

- Codex Skill 指令、参考规范、模板、检查器和自动化测试。
- PRD、设计、开发、测试、发布、复盘和仓库结构治理。
- Paperclip 执行隔离、服务不可变、低风险操作直行、核心门禁董事会审批与 Agent 后续操作，以及生产服务发布和 Bash 生命周期约束。

### 范围外

- 代替产品、技术、测试或发布负责人作最终业务决策。
- 提供项目管理 SaaS、可视化控制台或在线文档托管服务。

## 重要约定

- `skills/` 是本仓库的核心交付区域，每个直接子目录对应一个独立 Skill。
- Skill 指令保持精简；详细规则、模板和确定性工具分别放在 `references/`、`assets/` 和 `scripts/`。
- Python 检查器使用标准库实现，OpenAPI 和 YAML 台账解析仅依赖 PyYAML。
- 所有变更必须通过单元测试、仓库结构自检、Markdown 链接检查和 Skill 元数据校验。

## 技术与运行环境

- 主要技术栈：Markdown、Python 3.12、YAML、GitHub Actions
- 开发环境：支持 Python 3.12 和 Git 的本地环境
- 测试环境：Python `unittest`
- 生产环境：由 Codex 从已安装的 Skill 目录读取并执行

## 相关文档

- 项目入口：`README.md`
- 项目结构索引：`.project-structure.json`
- 生命周期治理：`skills/project-manager/SKILL.md`
- 仓库结构治理：`skills/project-structure-governance/SKILL.md`
- Agent 工作隔离：`skills/isolate-paperclip-work/SKILL.md`

## 更新记录

| 日期 | 修改人 | 变更摘要 |
| --- | --- | --- |
| 2026-08-10 | FarFarFun | 补齐仓库自身结构治理和项目说明 |
