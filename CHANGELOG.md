---
性质: 记述
---

# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/); versions follow semver.
The `tool_version` field inside `context_manifest` JSON output is a schema-contract stamp
(currently `eg-2`), independent of these release versions.

## v0.1.0 — 2026-07-17

Initial public release.

### Graph & query layer
- `graph` / `doc` / `id` / `ids` — frontmatter relationship chains (upstream/downstream +
  wildcard keyed relations), per-document panorama, identifier occurrence index with
  open, corpus-defined kinds.
- `docs [glob] [--fields A,B]` — batch frontmatter projection: one call turns N documents'
  selected fields into one table (fields missing on a document project as `null`).
- Name resolution understands same-directory disambiguation and path-qualified references,
  so corpora using one standard filename set per directory (`Goal.md`, `Requirement.md`, …)
  resolve correctly.

### Entity layer
- `dump` — full entity+edge export, byte-stable against the golden baseline.
  `--kind K` projects to one kind: entities filtered to `key[0]==K`, edges to the incident
  set (`src[0]==K ∨ dst[0]==K`; the projection is deliberately not a closed graph —
  edges may reference entities outside the projected list). Corpus-level diagnostics are
  never filtered.
- `trace` / `brief` / `verify` / `classify` / `harvest` / `drift` — entity definition
  lookup, task-closure context bundles with explicit budgets, incremental diff
  verification, nature classification workflow, table harvesting, value-drift detection.

### Consistency checking
- `check` — dead links, broken frontmatter references, one-way dependency edges,
  dangling section anchors, unregistered parameters, entity-level checks; every finding
  carries file:line provenance.
- Verdict objects expose a four-state `judgment_status`:
  `structurally_complete` / `tainted` / `broken` / `dormant` — `dormant` means the policy
  for that check is not declared in conventions (never armed; not a pass, and never
  mistakable for one from the data alone).
- `--gate key1,key2` for CI gating: exits non-zero on failing / tainted / broken checks,
  exit 2 on unknown keys and unknown flags (fail-closed CLI).

### Machine-readable contract (agent-first)
- Every command supports `--json`. The command → top-level-key contract is documented in
  `SKILL.md` ("JSON output contract") and drift-locked by the test suite against the
  fixtures corpus.
- `context_manifest` on analysis commands: corpus revision, conventions hash, output hash —
  reproducible provenance for machine consumers.

### Conventions (per-project adaptation, zero-config default)
- Optional `conventions.json` per corpus: entity extraction forms, nature mapping
  (`nature_source` with bracket-note normalization), archive-subtree exclusion
  (`archive_globs` + `--include-archived` forensic switch), intentional non-link
  declarations (`edges.nonlink_prefixes`), task-table column names, required-edge rules.
- Three iron rules for every key: additive-optional, absent-dormant with zero ripple,
  fail-closed validation.

### Rendering
- `html` / `html-entity` — self-contained interactive graph pages (no external assets),
  with archive filtering honored at the data layer and fail-visible JS defenses.

### Quality baseline
- Zero dependencies, Python 3.9–3.13 (CI matrix runs all five; `--json` output is
  byte-identical across versions).
- Test suite: logic assertions + byte-locked golden baselines + optional slow layer;
  contributors run `python3 tests.py --skip-slow`.
