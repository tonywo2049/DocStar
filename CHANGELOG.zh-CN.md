---
locale: zh-CN
purpose: 记录 DocStar 对用户可见的版本变化。
status: approved
type: changelog
nature: descriptive
---

# 更新记录

格式尽量遵循 [Keep a Changelog](https://keepachangelog.com/)，发布版本使用语义化版本。
JSON 中的 `tool_version` 是独立的 schema 契约版本。

English: [CHANGELOG.md](CHANGELOG.md)

## v0.2.0 — 未发布

### 双语界面

- 增加 `--lang en|zh-CN`，覆盖帮助、人读 CLI 输出和两种 HTML 页面。
- 公共文档采用英文主文件与 `.zh-CN.md` 中文镜像。
- 增加 GMGN 中英文镜像语料，要求两者生成相同的图语义。

### eg-3 机器契约

- 用稳定英文键和值替换 `eg-2` 的中英混合 JSON。
- 旧中文 frontmatter、查询选择器和约定值继续作为输入别名。
- `--gate`、`--kind`、`--fields` 接受英文别名；`--lang` 不改变 `--json` 输出。

### GMGN 兼容

- 增加内置 `gmgn-v1` 约定预设。
- 统一 GMGN 元数据、文档类型、工作状态、任务表头，以及
  Goal → Requirement → Design → Task 抽取链。
- 删除可复制的文档章节骨架，改用不限制版式的结构契约与检查清单；GMGN 各阶段 Skill 继续作为
  必备内容权威。
- 排除 Claude Code 仓库根的 `agents/` 控制目录，但保留 `docs/agents/` 这类业务文档目录。

### 维护

- 增加受保护的 `scripts/update_golden.py --schema eg-3` 更新流程。
- 删除失效的设计过程引用，改由公共契约和可执行测试说明行为。

## v0.1.1 — 2026-07-18

- 增加 Codex 与 Claude Code 技能入口及控制文件排除规则。
- 将详细命令、约定和写作规则拆到渐进展开的参考文档。
- 让 HTML 输出兼容只读技能安装，并收紧 CI 失败判定。

## v0.1.0 — 2026-07-17

首次公开发布，包含文档/实体图查询、结构检查、项目约定、确定性 JSON、自包含 HTML，
以及 Python 3.9–3.13 测试矩阵。
