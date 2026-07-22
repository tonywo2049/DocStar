---
locale: en
purpose: Define DocStar command forms, exit codes, and the eg-3 JSON surface.
status: approved
type: command-contract
nature: normative
---

# Command and JSON contract

[简体中文](command-contracts.zh-CN.md)

## Paths and common options

Relative paths are resolved from the caller's current directory. The default
corpus is the current directory. `html` and `html-entity` write `graph.html` and
`entity_graph.html` there unless given another path.

- `--json`: emit the stable `eg-3` public JSON contract.
- `--version`: when used by itself, print the release version and exit without
  scanning a corpus or emitting JSON.
- `--lang en|zh-CN`: select human-facing labels; never changes JSON.
- `--corpus DIR`: select the Markdown corpus root.
- `--conventions DIR`: replace automatic convention discovery.
- `--preset NAME`: use a bundled preset such as `gmgn-v1`.
- `--include-archived`: include content excluded by `archive_globs`.
- `--kind K`: project `ids` or `dump` to one kind; accepts eg-3 English tokens.
- `--fields A,B`: project frontmatter; accepts canonical or legacy aliases.
- `--gate key1,key2`: gate named `check` top-level keys; accepts eg-3 keys.
- `--baseline`: make `brief` read an exact Git commit; set the comparison baseline
  for `verify` or `classify`; or select the prior output file for `harvest`.

`--conventions` and `--preset` are mutually exclusive.

## Exit codes

- `0`: command completed. `check` remains advisory unless `--gate` is present.
- `1`: query or kind not found, or a named gate was hit.
- `2`: invalid usage, option, language, preset, gate key, or conventions config.

## Command forms

```text
docstar.py --version
docstar.py graph
docstar.py doc <name>
docstar.py id <ID>
docstar.py id "<doc> §N"
docstar.py ids [--kind K]
docstar.py docs [glob] [--fields A,B]
docstar.py check [--gate key1,key2]
docstar.py dump [--kind K]
docstar.py trace <entity>
docstar.py brief <task> [--mode execute|impact|review] [--budget N] [--baseline REV]
docstar.py verify [--baseline REV] [--migrate]
docstar.py classify --pending
docstar.py classify --validate --baseline REV --manifest SCOPE
docstar.py harvest [--baseline FILE]
docstar.py drift
docstar.py html [output]
docstar.py html-entity [output]
```

Name resolution uses path-qualified suffix, exact stem, alias, prefix, and
substring matching. Multiple matches are listed and exit 1. CI should pass an
explicit `verify --baseline`.

For `brief`, `--baseline REV` must resolve to a commit. DocStar reads tracked
Markdown bytes from that snapshot, ignores tracked and untracked worktree changes,
and writes the resolved full SHA to `context_manifest.corpus_revision`. An invalid
revision exits 2. Omitting the flag preserves worktree behavior and the revision
token `worktree`.

When conventions enable `task_execution`, default/`execute` and `review` briefs include the
validated normative Card and follow through Log only to the validated `latest_event` block.
They never substitute the complete descriptive execution log. `impact` does not follow the
execution chain. Broken pointers appear in both `diagnostics` and `omitted`.

## eg-3 JSON top-level keys

All contract keys and built-in enum tokens are English. Source paths, document
titles, excerpts, IDs, and project-defined kinds remain source data and are not
translated. `golden/*.json` locks nested shapes byte for byte.

| Command | Top-level keys |
|---|---|
| `graph` | `docs_total`, `docs_with_frontmatter`, `chains` |
| `doc` | `doc`, `meta`, `upstream`, `downstream`, optional `frontmatter_relations`, `frontmatter_references_in`, `body_links_out`, `body_links_in`, `section_references_out`, `section_references_in`, `section_count`, `top_id_mentions` |
| `id <ID>` | `id`, `kind`, `total`, `docs` |
| `id "<doc> §N"` | `query`, `target_anchor`, `references` |
| `ids` | `kinds`; each item has `kind`, `unique`, `total`, `note`, `ids` |
| `docs` | `docs` |
| `dump` | `context_manifest`, `schema_version`, `corpus_root`, `classification_complete`, `unknown_documents`, `entities`, `edges`, `reports` |
| `check` | `context_manifest`, document findings, entity verdicts, `schema_version` |
| `trace` | `context_manifest`, `query`, `resolved`, `nature`, `primary`, `candidates`, `attrs`, `edges` |
| `brief` | `context_manifest`, `schema_version`, `mode`, `query`, `resolved`, `nature`, `judgment_status`, `classification_complete`, `truncated`, `deterministic_deduplication`, `segments`, `omitted`, `diagnostics`, `boundary_pointers`, `tainted_by` |
| `verify` | `context_manifest`, `schema_version`, `baseline`, `baseline_source`, `scan_root`, `added_entities`, `removed_entities`, `added_edges`, `removed_edges`, `introduced_findings`, `graph_omissions`, `limitations` |
| `classify --pending` | `context_manifest`, `schema_version`, `mode`, `corpus_root`, `classification_complete`, `total_documents`, `pending_count`, `pending` |
| `harvest` | `context_manifest`, `schema_version`, `algo`, `filtered`, `candidates` |
| `drift` | `context_manifest`, `schema_version`, `drifts` |

Current `check` keys are locked by `tests.py::a_contract_toplevel` and
`golden/check.json`. Use those sources rather than copying a partial list into CI.

## Version boundary

`eg-3` replaces the mixed-language `eg-2` JSON surface. There is no mixed-output
compatibility mode. Input compatibility is preserved: legacy Chinese frontmatter
keys and built-in selectors remain accepted, while every JSON response is eg-3.
