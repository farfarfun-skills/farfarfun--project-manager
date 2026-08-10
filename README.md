# FarFarFun Project Governance

面向 Codex 的项目治理 Skill 集合，将仓库结构、研发产物、Agent 执行边界和服务发布条件转化为可执行门禁。

## Skills

| Skill | 能力 |
| --- | --- |
| [`project-manager`](skills/project-manager/SKILL.md) | 检查 PRD、设计、技术方案、测试、发布和复盘产物，聚合生命周期门禁 |
| [`project-structure-governance`](skills/project-structure-governance/SKILL.md) | 初始化并审计仓库目录、应用边界、文件命名和项目文档布局 |
| [`isolate-paperclip-work`](skills/isolate-paperclip-work/SKILL.md) | 隔离 Paperclip 上下文，日常操作直接执行，仅将核心门禁交由董事会审批 |
| [`service-release-governance`](skills/service-release-governance/SKILL.md) | 约束服务通过正式包发布、仓库安装和生产启动 |
| [`bash-service-guide`](skills/bash-service-guide/SKILL.md) | 统一 Bash 服务生命周期脚本及开发、生产运行边界 |

检查器统一输出 `allow`、`revise` 或 `block`。这些结果代表结构化产物是否达到对应门禁，不代替产品、技术、测试或发布负责人作最终业务决策。

## Requirements

- Codex
- Python 3.12
- Git
- PyYAML 6.x，仅 `project-manager` 的 YAML 检查器需要

## Install

```bash
git clone https://gitee.com/farfarfun-skills/farfarfun--project-manager.git
cd farfarfun--project-manager
python3 -m pip install -r skills/project-manager/requirements.txt

mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
for skill in skills/*; do
  ln -s "$(pwd)/$skill" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")"
done
```

链接命令在同名 Skill 已存在时会失败，不会覆盖现有安装。更新仓库后，符号链接会继续指向最新工作树。

## Quick Start

在 Codex 中直接说明要使用的 Skill：

```text
Use $project-structure-governance to audit this repository and return exact repair paths.
Use $project-manager to check feature payment-confirmation at the development stage.
Use $isolate-paperclip-work before changing files for this Paperclip assignment.
```

也可以直接运行确定性检查器：

```bash
python3 skills/project-structure-governance/scripts/project_structure_checker.py \
  --workspace /path/to/project \
  --fail-on revise

cd skills/project-manager
python3 scripts/feature_governance_check.py \
  --workspace /path/to/project \
  --feature payment-confirmation \
  --stage development \
  --format json \
  --fail-on block
```

Paperclip 内部 Agent 应先使用 `isolate-paperclip-work` 建立执行边界，再使用 `project-structure-governance` 检查仓库结构，最后由 `project-manager` 检查当前生命周期阶段的产物质量。

## Validation

```bash
python3 -m pip install -r skills/project-manager/requirements.txt

(cd skills/project-manager && python3 -m unittest discover -s tests -v)
(cd skills/project-structure-governance && python3 -m unittest discover -s tests -v)
(cd skills/isolate-paperclip-work && python3 -m unittest discover -s tests -v)

python3 skills/project-structure-governance/scripts/project_structure_checker.py \
  --workspace . \
  --fail-on revise
```

完整项目背景见 [`docs/project/project-overview.md`](docs/project/project-overview.md)。
