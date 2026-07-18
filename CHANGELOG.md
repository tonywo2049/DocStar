---
locale: en
purpose: Record user-visible DocStar release changes.
status: approved
type: changelog
nature: descriptive
---

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/) where practical;
release versions follow semantic versioning. The JSON `tool_version` is a separate
schema-contract stamp.

中文版本：[CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)

## v0.2.0 — 2026-07-19

### Bilingual interface

- Added `--lang en|zh-CN` for help, human-readable CLI output, and both HTML views.
- Made public documentation available as English-primary and `.zh-CN.md` pairs.
- Added English and Chinese GMGN fixtures that must produce the same graph semantics.

### eg-3 machine contract

- Replaced the mixed-language `eg-2` JSON surface with stable English keys and tokens.
- Kept legacy Chinese frontmatter, selectors, and convention values as input aliases.
- Added English aliases for `--gate`, `--kind`, and `--fields`; `--lang` never changes
  `--json` output.

### GMGN compatibility

- Added the bundled `gmgn-v1` conventions preset.
- Standardized GMGN metadata, document types, work status, task-table headers, and
  Goal → Requirement → Design → Task extraction.
- Replaced copy-ready document skeletons with a layout-free structural contract and
  checklist; GMGN stage Skills remain the content authorities.
- Excluded Claude Code's repository-root `agents/` control directory without excluding
  domain documentation such as `docs/agents/`.

### Maintenance

- Added the guarded `scripts/update_golden.py --schema eg-3` workflow.
- Replaced obsolete design-process references with public contracts and executable tests.

## v0.1.1 — 2026-07-18

- Added Codex and Claude Code skill entry points and control-file exclusions.
- Moved detailed command, conventions, and writing rules into progressive-disclosure
  references.
- Made HTML output safe for read-only skill installations and tightened CI failure rules.

## v0.1.0 — 2026-07-17

Initial public release with document/entity graph queries, structural checks, project
conventions, deterministic JSON, self-contained HTML, and a Python 3.9–3.13 test matrix.
