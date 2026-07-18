---
name: docstar
description: 'Use when a question spans Markdown documents: find where an ID is defined and referenced, inspect document dependencies, detect broken links or section references after edits, validate a documentation tree before handoff, or retrieve exact task context. Prefer DocStar over ad-hoc grep when a .docstar/ directory is present. 当问题跨越多篇 Markdown 文档时使用：查定义与引用、查看上下游依赖、检查编辑后的断链或断锚、交接前验证文档树，或取得任务的精确上下文；看到 .docstar/ 时优先使用本工具。'
---

# DocStar

Treat a Markdown corpus as a queryable document graph, entity index, and
structural-check target. DocStar is read-only, uses Python 3.9+ stdlib, calls no
model, and rebuilds its view on every run.

Resolve `<tool-dir>` to the directory containing this `SKILL.md`, then call:

```bash
python3 <tool-dir>/docstar.py <command> [args] --json --corpus <docs-root>
```

`--corpus` is the governed Markdown root, not necessarily the repository root.
Pass it explicitly when DocStar is installed inside another project.

## Language contract

- JSON is always the stable English `eg-3` contract. Never translate its keys or
  built-in tokens in a consumer.
- Use `--lang en|zh-CN` only for human CLI or HTML output.
- Answer and write prose in the user's language, or the project's declared
  `locale` when the user did not choose one.
- When authoring documents, keep frontmatter keys, enum tokens, filenames, IDs,
  commands, placeholders, and fixed task-table headers in English.
- Legacy Chinese metadata is readable input, not the form for new output.

## Choose a command

| Goal | Command |
|---|---|
| Find an ID or `Doc §N` and its references | `id <query>` |
| Inspect one document and its incoming/outgoing relationships | `doc <name>` |
| See the global document graph | `graph` |
| Project frontmatter fields | `docs [glob] [--fields A,B]` |
| Check links, anchors, reciprocity, and declared entity rules | `check [--gate key1,key2]` |
| Compile deterministic task context | `brief <task> [--mode execute|impact|review]` |
| Inspect the current edit against a baseline | `verify [--baseline REV]` |
| Export or trace the entity graph | `dump [--kind K]` / `trace <entity>` |
| Classify document nature or find undefined terms | `classify --pending` / `harvest` |
| Find managed-value drift | `drift` |

Read [references/command-contracts.md](references/command-contracts.md) only when
writing a consumer, configuring CI gates, or diagnosing invocation behavior.

## Pull context on demand

- “Where is `<ID>` defined and referenced?” → `id <ID> --json`
- “What does this document depend on?” → `doc <name> --json`
- “Is the corpus structurally consistent?” → `check --json`
- “I need to work on `<task>`.” → `brief <task> --json`
- After editing and before commit or handoff → `verify --json`

Do not read the whole corpus and reconstruct relationships by hand. Start with the
smallest DocStar query, then follow returned `file:line` pointers when more source
text is needed.

Before delegating a concrete task, run `brief <task> --json` and pass that bundle as
the starting context. The recipient may use `id`, `doc`, or `trace` to expand it.

## Interpret verdicts

`judgment_status` is one of:

- `structurally_complete`: the structural inputs were complete;
- `tainted`: unclassified documents influenced the result;
- `broken`: a required input did not resolve;
- `dormant`: the corresponding policy was not declared.

These are not semantic approval states. Before putting `check --gate` in CI, clear
`classify --pending` and gate only policies the project has declared.

## Configure a corpus

Zero configuration provides document relationships and generic entity syntax. For
project IDs, directed keys, archive filters, or cross-kind policies, read
[references/conventions.md](references/conventions.md) and create
`<corpus>/.docstar/conventions/conventions.json`.

For a GMGN document chain, use `--preset gmgn-v1`; a project-local copy of the same
preset enables automatic discovery.

## Author documents

Apply these rules:

1. Define one entity per list item and bold only its name or ID.
2. Put entities under typed sections.
3. Express dependencies with real links, not prose hints.
4. Mark terms where they are defined.
5. Declare `nature` at document birth; do not guess missing values.
6. Run `verify` before commit or handoff.

For copyable English and Chinese templates, read
[references/writing-guide.md](references/writing-guide.md) or
[references/writing-guide.zh-CN.md](references/writing-guide.zh-CN.md), matching the
project language.

## Self-check

```bash
python3 <tool-dir>/tests.py --skip-slow
python3 <tool-dir>/internal/corpus.py --selftest
python3 <tool-dir>/conventions/__init__.py --selftest
```

All three commands must exit 0.
