---
locale: en
purpose: Explain convention discovery, bundled presets, and compatibility rules.
status: approved
type: conventions-guide
nature: normative
---

# Conventions

[简体中文](conventions.zh-CN.md)

Conventions adapt DocStar's generic parser to project-specific IDs, tables, and
policies. They change extraction and checks, not the eg-3 public JSON language.

## Resolution order

1. `--conventions DIR`
2. `--preset NAME`
3. `<corpus>/.docstar/conventions/conventions.json`
4. nearest ancestor config up to and including the Git boundary
5. the built-in generic default

`--conventions` and `--preset` are mutually exclusive. An explicit config is a
complete replacement, not a per-key overlay. Invalid config exits 2.

## Bundled GMGN preset

```bash
python3 docstar.py check --preset gmgn-v1 --json --corpus <project>
```

`gmgn-v1` recognizes:

- `Goal.md → Requirement.md → Design.md → Task.md`;
- stable `upstream` and `downstream` links;
- `Rn-ACn` acceptance criteria and `(Mn-)Tn` task IDs;
- the canonical task-table layout `# | task | spec anchor | prerequisite | status |
  execution` in both English and Chinese prose editions;
- task entities only from that canonical task table, not repeated bold field labels or
  other tables;
- the Task `execution` link to `execution/<card_id>/Card.md`, the Card `execution_log`
  link to sibling `Log.md`, and the Log `latest_event` link to an event anchor, producing
  `task → task-card → execution-log → latest-event`;
- `none`, `external:`, `无`, and `外部：` as declared non-link prefixes;
- the policy that every requirement AC needs an incoming task declaration.

The preset file is [conventions/presets/gmgn-v1.json](../conventions/presets/gmgn-v1.json).
Projects that need automatic discovery may copy that file to
`.docstar/conventions/conventions.json`; keep it byte-identical unless the project
intentionally forks the contract.

## Configuration groups

- `edges.*`: directed key pairs, section marker, self-reference words, and declared
  non-link prefixes.
- `type_sections`, `def_forms`, `doc_id_kinds`: typed sections and project ID forms.
- `task_columns`, `id_occ_kinds`, `cooccur_kinds`, `ac_prefix_kinds`: task-table and
  ID participation rules.
- `task_execution`: optional Card/Log field aliases and the
  `canonical_task_table_only` switch. When absent, execution extraction is dormant.
  When present, `task_columns.execution` must exist. Links must be relative Markdown
  links; Card must be `execution/<card_id>/Card.md` with `type: task-card` and
  `nature: normative`; Log must be its sibling `Log.md` with `type: execution-log` and
  `nature: descriptive`; `latest_event` must resolve inside Log. Field names accept `=`,
  ASCII `:`, or full-width `：`. Links inside code examples or HTML comments do not count.
  Invalid declarations appear in `execution_log_diagnostics` and `brief` omissions.
- `nature_source`: migration mapping from an existing metadata field to
  `normative` or `descriptive`; explicit `nature`/`性质` wins.
- `required_edges`: cross-kind policies and report/gate severity.
- `uncovered_kind_exclusions`: generic or support kinds intentionally outside those
  policies; do not use it to hide a spelling alias of a policy subject.
- `managed_values`: managed values for `drift`.
- `revision_target_kinds`, `cooccur_mapping_kinds`: check domains; absent means
  `dormant`.
- `archive_globs`: path-segment archive filters.
- `aliases`, `namespaces`: document aliases and bare-ID disambiguation anchors.

The full stress fixture is under
`fixtures/corpus/.docstar/conventions/conventions.json`. Focused examples live in
`fixtures/gmgn`, `fixtures/methodology`, `fixtures/nonlink`, `fixtures/reqedge`, and
`fixtures/archived`.

## Compatibility rules

Every new key must be optional and additive, preserve existing output when absent,
and fail closed when malformed. Add loader self-tests, end-to-end positive and
negative cases, and a conventions-hash assertion in the same change.
