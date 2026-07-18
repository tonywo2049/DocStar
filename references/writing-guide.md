---
locale: en
purpose: Define bilingual Markdown metadata, entity syntax, and a layout-free structural checklist.
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

## Content contract without a layout template

DocStar does not prescribe headings, section order, or prose shape. Before authoring, obtain
the content contract from the governing project workflow or stage Skill. It must state:

- the document's authoritative question, `type`, `nature`, and initial `status`;
- required facts or decisions and explicit exclusions;
- real upstream/downstream authorities;
- stable IDs and any parser-facing table headers;
- self-check and verification requirements.

The Author may choose any clear structure that satisfies those requirements. A Critic or
reviewer checks the result against the same content contract, not against a copy-ready
skeleton. Do not turn this guide into a project-document template.

Use `nature: normative` when downstream work must obey the document's obligations,
criteria, or rulings. Use `nature: descriptive` for investigation, experiments, logs,
handoffs, or event records that do not independently establish a gate.

Before handoff, confirm that all seven frontmatter keys are present, every declared edge is
real or explicitly `none`, entity IDs are stable and unique, definitions sit under a typed
section, prose language matches `locale`, and `verify --json` reports no introduced break.

## GMGN parser-facing task header

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
