---
locale: en
purpose: Define the tests, compatibility rules, and review process for DocStar contributions.
status: approved
type: contribution-guide
nature: normative
---

# Contributing to DocStar

[简体中文](CONTRIBUTING.zh-CN.md)

`AGENTS.md` tells coding agents how to work in this repository. This guide defines
the public contribution contract for humans, pull requests, compatibility, and
golden files.

DocStar has no runtime dependencies beyond Python 3.9+.

## Required checks

Run before opening a pull request:

```bash
python3 tests.py --skip-slow
python3 internal/corpus.py --selftest
python3 conventions/__init__.py --selftest
python3 docstar.py verify --json
```

All commands must exit 0. Maintainers also run `python3 tests.py` locally; its
performance assertions are intentionally excluded from shared CI runners.

CI covers Python 3.9 through 3.13. JSON output must be byte-stable across those
versions.

## Engine changes are test-first

For parser, graph, check, or output behavior:

1. Add a fixture and an assertion that fails for the missing behavior.
2. Implement the smallest coherent change.
3. Add negative and compatibility cases.
4. Run the required checks.

Explain externally observable behavior in the pull request. Internal historical
`EG-*` and `DG-*` references are not required from outside contributors.

## Golden files

`golden/*.json` lock the public JSON contract byte for byte. Contributors and
agents must not edit or regenerate them just to make a test green.

When an approved schema change intentionally changes output:

1. The contributor lists affected commands and fields.
2. A maintainer reviews the structured old/new difference.
3. The maintainer runs the guarded generator:

   ```bash
   python3 scripts/update_golden.py --schema <expected-schema>
   ```

4. The maintainer reviews the generated diff and reruns the full test suite.

The script refuses a schema argument that does not match the engine and prints
top-level additions and removals for every golden.

## English and Chinese parity

Public prose has paired files:

- English primary: `README.md`, `CONTRIBUTING.md`, and `references/*.md`.
- Simplified Chinese: `*.zh-CN.md` with the same basename.

Both editions must preserve commands, IDs, placeholders, code blocks, allowed
token sets, warnings, and link targets. Prose may be translated naturally. New
machine fields and values stay English in both editions.

`SKILL.md` is a single executable skill, not two language-specific copies. Its
trigger description covers both languages and its runtime instructions follow the
project or user language.

## Conventions compatibility rules

New conventions keys must be:

1. additive and optional;
2. dormant when absent, with no change to existing golden output;
3. fail-closed when malformed.

Add loader self-tests, end-to-end positive and negative cases, and a conventions
hash assertion in the same change.

## Review scope

Substantive code changes need an independent code review focused on untested
surfaces, assertion strength, and unnecessary complexity. Substantive normative
documentation changes need one independent falsification-oriented review for
facts, completeness, internal consistency, upstream/downstream consistency,
over-design, modality, and testability. Typos and formatting-only changes are
exempt.
