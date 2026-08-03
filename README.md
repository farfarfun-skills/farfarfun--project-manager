# tauskills project governance

面向 Codex 的项目治理 Skill 集合，覆盖仓库结构和研发全生命周期门禁。

## Skills

- [`project-manager`](skills/project-manager/SKILL.md)：检查 PRD、设计、技术方案、测试、发布和复盘产物，并聚合生命周期门禁。
- [`project-structure-governance`](skills/project-structure-governance/SKILL.md)：初始化并审计仓库目录、应用边界、文件命名和项目文档布局。
- [`isolate-paperclip-work`](skills/isolate-paperclip-work/SKILL.md)：隔离 Paperclip 执行上下文，约束 agent 的 Git 变更范围、命名、TODO、证据、验证和自动清理，并检查项目资产泄漏。
- [`service-release-governance`](skills/service-release-governance/SKILL.md)：区分开发与生产运行模式，约束服务通过正式包发布、仓库安装和启动，并优先使用私域仓库。
- [`bash-service-guide`](skills/bash-service-guide/SKILL.md)：统一 Bash 服务生命周期脚本，并联动正式包发布、仓库安装与生产启动门禁。

Paperclip 内部 agent 先使用 `isolate-paperclip-work` 建立执行边界，再使用 `project-structure-governance` 检查仓库结构，并由 `project-manager` 检查各阶段产物质量。

## Validation

```bash
python3 -m pip install -r skills/project-manager/requirements.txt

(cd skills/project-manager && python3 -m unittest discover -s tests -v)
(cd skills/project-structure-governance && python3 -m unittest discover -s tests -v)
(cd skills/isolate-paperclip-work && python3 -m unittest discover -s tests -v)
```
