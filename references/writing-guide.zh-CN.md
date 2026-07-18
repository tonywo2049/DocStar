---
locale: zh-CN
purpose: 定义双语 Markdown 元信息、实体写法和可复用模板。
status: approved
type: writing-guide
nature: normative
---

# 双语文档写作指南

[English](writing-guide.md)

## 一份机器契约，两种正文语言

正文和标题可以自然使用英文或简体中文。所有机器字段、枚举值、文件名、ID、命令和固定表头保持
不变。这样两版文档会产生相同的 DocStar 图，agent 切换语言时也不需要切换工作流。

新建且纳入文档图管理的项目文档使用以下 frontmatter 键：

| 键 | 含义 |
|---|---|
| `locale` | `en` 或 `zh-CN` |
| `purpose` | 一句话说明本文回答什么 |
| `upstream` | 指向本文所消费来源的真实 Markdown 链接 |
| `downstream` | 指向本文所服务消费者的真实 Markdown 链接 |
| `status` | `draft`、`pending-approval`、`approved` 或 `closed` |
| `type` | 项目文档类型 |
| `nature` | `normative` 或 `descriptive` |

GMGN profile 把 `type` 固定为 `whitepaper`、`roadmap`、`goal`、`requirement`、`design`、
`task`、`research`、`decision`、`retrospective` 或 `handoff`。普通 DocStar 项目可以声明其他类型。

文档 `status` 和工作项状态不是一回事。GMGN 工作项使用
`not-started → initiated → in-progress → closed`。

旧的 `目标/上游/下游/状态/类型/性质` 和 `规范/记述` 仍可读，只用于迁移；新文档不要再写。

## 结构写作规则

1. 一个列表项只定义一个实体，只加粗实体编号或名称。
2. 定义放在 `Requirements`、`Acceptance Criteria`、`Parameters`、`Tasks` 或对应中文标题下。
3. 关系用 frontmatter 链接、Markdown 链接、wikilink 或 `<document> §N` 表达，不靠散文暗示。
4. 术语第一次定义时明确标注。
5. 文档出生时声明 `nature`；缺失或冲突都按 `unknown`。
6. 编辑后、提交或交接前运行 `verify --json`。

普通散文中的加粗不是实体；日期、状态等纯标量不会被猜成关系。

## 规范文档模板——英文正文

```markdown
---
locale: en
purpose: <what this document decides or requires>
upstream:
  - [<source>](<source>.md)
downstream:
  - [<consumer>](<consumer>.md)
status: draft
type: requirement
nature: normative
---

# <Title>

## Requirements

- **R1** — <verifiable requirement>.

## Acceptance Criteria

- **R1-AC1** — <deterministic acceptance condition>.
```

## 规范文档模板——中文正文

```markdown
---
locale: zh-CN
purpose: <本文决定或要求什么>
upstream:
  - [<上游显示名>](<source>.md)
downstream:
  - [<下游显示名>](<consumer>.md)
status: draft
type: requirement
nature: normative
---

# <标题>

## 需求

- **R1** — <可验证需求>。

## 验收标准

- **R1-AC1** — <确定性验收条件>。
```

两者只改变正文；键、枚举、文件名和 ID 不变。

## 记述文档模板

英文：

```markdown
---
locale: en
purpose: Record <investigation, experiment, handoff, or event>.
upstream: [<subject>](<spec>.md)
downstream: none (record only)
status: approved
type: research
nature: descriptive
---

# <What happened or was studied>

The findings reference <spec> §2 but impose no requirement on it.
```

中文：

```markdown
---
locale: zh-CN
purpose: 记录<调研、实验、交接或事件>。
upstream: [<对象>](<spec>.md)
downstream: none (record only)
status: approved
type: research
nature: descriptive
---

# <发生了什么或研究了什么>

本文引用 <spec> §2，但不对它新增要求。
```

## GMGN 任务表

表头属于机器接口，中英文正文都保持英文：

```markdown
| # | task | spec anchor | prerequisite | failing test | status |
|---|---|---|---|---|---|
| **M1-T1** | <本地化目标> | R1-AC1 | none | `test_name` | not-started |
```

运行时使用 `--preset gmgn-v1`；需要自动发现时，把内置 preset 复制到项目的
`.docstar/conventions/conventions.json`。

## 给存量语料分类

```bash
python3 <tool-dir>/docstar.py classify --pending --json --corpus <docs>
python3 <tool-dir>/docstar.py classify --validate \
  --baseline <REV> --manifest <SCOPE> --json --corpus <docs>
python3 <tool-dir>/docstar.py check --json --corpus <docs>
```

每次只裁定一篇文档，该批只改 frontmatter；低置信度决策上报。直到
`classification_complete` 为真。
