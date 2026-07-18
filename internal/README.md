---
locale: en
purpose: Explain DocStar internal modules to maintainers.
status: approved
type: maintainer-guide
nature: descriptive
---

# DocStar internals

These are implementation modules and rendering templates for the root `docstar.py`
entry point. They are not separate user commands.

- `corpus.py` — filesystem and Git corpus sources.
- `entity_*.py` — extraction, checks, trace, brief, verify, classify, harvest, model,
  and HTML rendering.
- `*_template.html` — self-contained document and entity graph pages.

`docstar.py` adds this directory to `sys.path`, so internal modules use top-level imports.
Modules with a self-test can be run with `python3 internal/<module>.py --selftest`.

中文版本：[README.zh-CN.md](README.zh-CN.md)
