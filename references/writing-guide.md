---
性质: 规范
---

# DocStar 文档写作指南

## 目录

- [核心约定](#核心约定)
- [规格模板](#规格模板)
- [记录模板](#记录模板)
- [存量分类](#存量分类)

## 核心约定

1. 一个项目符号只定义一个实体，只加粗实体名。
2. 把实体放在 `## Requirements`、`## 参数`、`## Tasks`、`## Glossary` 等带类型小节下。
3. 用 frontmatter、Markdown link、wikilink 或 `<doc> §N` 写真实关系。
4. 在术语首次定义处标注定义。
5. 文档出生时声明规范性或记述性。
6. 编辑后、提交或交接前运行 `verify --json`。

普通散文中的加粗不会成为实体；没有链接的散文提及不会成为边；`status`、日期等纯标量不会被猜成关系。

## 规格模板

```markdown
---
性质: 规范
upstream:
  - [the doc this one serves](parent.md)
---

# <topic>

## Requirements
- **<verifiable statement, or canonical ID>** — <detail>.

## Tasks
- **<action>** — <scope>; see [design](design.md).

## Glossary
- **<coined term>**: <definition>.
```

## 记录模板

```markdown
---
性质: 记述
upstream:
  - [what this note informs](spec.md)
---

# <what happened or was studied>

Findings reference spec §2 but impose nothing on it.
```

规范文档定义下游必须遵守的义务、标准或裁决；记述文档记录调查、实验、日志或交接，不单独设 gate。需要精确章节关系时用 `<doc> §N`；同 stem 跨目录不唯一时写 `dir/doc §N`。

## 存量分类

运行 `classify --pending --json` 获取带机械证据的工作清单。逐篇裁定规范或记述，低置信度上报；一个分片只改 frontmatter。完成后用：

```bash
python3 <tool-dir>/docstar.py classify --validate \
  --baseline <REV> --manifest <SCOPE>
python3 <tool-dir>/docstar.py check --json
```

直到 `classification_complete` 为真且待办清零。
