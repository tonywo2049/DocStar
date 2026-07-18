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
- the canonical task-table layout `# | task | spec anchor | prerequisite | failing test |
  status` in both English and Chinese prose editions;
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
