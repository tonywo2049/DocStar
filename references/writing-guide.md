---
locale: en
purpose: Define bilingual Markdown metadata, entity syntax, and reusable templates.
status: approved
type: writing-guide
nature: normative
---

# Bilingual writing guide

[简体中文](writing-guide.zh-CN.md)

## One machine contract, two prose languages

Write prose and headings naturally in English or Simplified Chinese. Keep every
machine-facing field, enum, filename, ID, command, and fixed table header unchanged.
This lets both editions produce the same DocStar graph and lets agents switch
language without switching workflow.

New graph-governed project documents use these frontmatter keys:

| Key | Meaning |
|---|---|
| `locale` | `en` or `zh-CN` |
| `purpose` | One sentence stating what the document answers |
| `upstream` | Real Markdown links to sources this document consumes |
| `downstream` | Real Markdown links to consumers this document serves |
| `status` | `draft`, `pending-approval`, `approved`, or `closed` |
| `type` | Project document type |
| `nature` | `normative` or `descriptive` |

The GMGN profile fixes `type` to `whitepaper`, `roadmap`, `goal`, `requirement`,
`design`, `task`, `research`, `decision`, `retrospective`, or `handoff`. Generic
DocStar projects may declare other types.

Document `status` is not work-item status. GMGN work items use
`not-started → initiated → in-progress → closed`.

Legacy `目标/上游/下游/状态/类型/性质` and `规范/记述` remain readable migration
aliases. Do not use them in new files.

## Structural writing rules

1. Define one entity per list item and bold only its identifier or name.
2. Put definitions under typed headings such as `Requirements`, `Acceptance
   Criteria`, `Parameters`, `Tasks`, or their Chinese translations.
3. Express relationships with frontmatter links, Markdown links, wikilinks, or
   `<document> §N`; do not rely on prose hints.
4. Mark a term where it is first defined.
5. Declare `nature` at birth. Missing or conflicting declarations are `unknown`.
6. Run `verify --json` after editing and before commit or handoff.

Ordinary bold prose is not an entity. Plain scalar metadata such as dates or status
is not guessed to be a relationship.

## Normative template — English prose

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

## Normative template — Chinese prose

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

The prose differs; keys, enums, filenames, and IDs do not.

## Descriptive templates

English:

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

## GMGN task table

The table header is a machine surface and stays English in both prose editions:

```markdown
| # | task | spec anchor | prerequisite | failing test | status |
|---|---|---|---|---|---|
| **M1-T1** | <localized goal> | R1-AC1 | none | `test_name` | not-started |
```

Use `--preset gmgn-v1`, or copy the bundled preset into the project's
`.docstar/conventions/conventions.json` for automatic discovery.

## Classifying an existing corpus

```bash
python3 <tool-dir>/docstar.py classify --pending --json --corpus <docs>
python3 <tool-dir>/docstar.py classify --validate \
  --baseline <REV> --manifest <SCOPE> --json --corpus <docs>
python3 <tool-dir>/docstar.py check --json --corpus <docs>
```

Classify one document at a time, change only frontmatter in that batch, and escalate
low-confidence decisions. Finish when `classification_complete` is true.
