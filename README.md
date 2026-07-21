---
locale: en
purpose: Introduce DocStar, its contracts, and its primary usage paths.
status: approved
type: guide
nature: descriptive
---

# DocStar

[简体中文](README.zh-CN.md)

DocStar turns a Markdown corpus into a queryable document graph, an entity index,
and a structural checker. It is read-only, uses only the Python 3.9+ standard
library, stores no index, and never calls a model.

Use it when a question spans documents:

- Where is an ID defined, and who references it?
- What does this document depend on, and what depends on it?
- Did an edit break a link, section reference, or declared policy?
- What exact context does a task need?
- Is a documentation set structurally ready for handoff?

## Quick start

```bash
git clone https://github.com/tonywo2049/DocStar.git
cd DocStar
python3 docstar.py graph --lang en --corpus /path/to/docs
python3 docstar.py check --json --corpus /path/to/docs
```

There is nothing to install with `pip`. Relative paths are resolved from the
caller's current directory.

## Install

### Codex marketplace (recommended)

```bash
codex plugin marketplace add tonywo2049/DocStar
codex plugin add docstar@DocStar
codex plugin list
```

Start a new Codex task after installation. Do not also place a manual `docstar`
copy under `~/.codex/skills`; marketplace and manual installations must not coexist
because they produce duplicate triggers.

### Manual Skill installation (optional)

### Git clone with symbolic links

Use this only when the marketplace installation is not present. Clone DocStar to
a stable absolute path, then link that checkout into Codex or Claude Code. Replace
`/absolute/path/to/DocStar` with the checkout path you chose.

```bash
git clone https://github.com/tonywo2049/DocStar.git /absolute/path/to/DocStar
mkdir -p ~/.codex/skills ~/.claude/skills
ln -s /absolute/path/to/DocStar ~/.codex/skills/docstar
ln -s /absolute/path/to/DocStar ~/.claude/skills/docstar
```

### Release ZIP or copied directory

Download `Source code (zip)` from the
[latest release](https://github.com/tonywo2049/DocStar/releases/latest), extract
it, and place the complete extracted directory at `~/.codex/skills/docstar` or
`~/.claude/skills/docstar`.

Do not overlay a new release onto an existing copied directory. Replace the
complete installed `docstar` directory so files removed or renamed by the new
release cannot survive from the old version.

## Upgrade

### Codex marketplace installation

Refresh the marketplace and check the installed version:

```bash
codex plugin marketplace upgrade DocStar
codex plugin list
```

If the old version is still listed, reinstall from the refreshed marketplace:

```bash
codex plugin remove docstar@DocStar
codex plugin add docstar@DocStar
codex plugin list
```

### Manual ZIP or source installation

For a Git clone used through symbolic links, update the shared checkout. The
links do not need to be recreated.

```bash
git -C /absolute/path/to/DocStar pull --ff-only
```

For a ZIP or copied installation, download the latest release and fully replace
each installed `docstar` directory. Move the old directory aside first if you
need a backup; never merge the new files over it.

Verify the checkout or installed directory, replacing the placeholder with its
actual absolute path. The final output line shows the installed release version:

```bash
python3 /absolute/path/to/DocStar/docstar.py
```

Manual installations are optional and must not coexist with the Codex marketplace
plugin. After either upgrade method, start a new Codex task or Claude Code session so
the client reloads the Skill instructions.

## Uninstall

For a Codex marketplace installation:

```bash
codex plugin remove docstar@DocStar
codex plugin marketplace remove DocStar
```

For a manual installation, remove only the `docstar` directory or symbolic link
you created. Do not leave both installation forms present.

## Commands

| Question | Command |
|---|---|
| Show the document graph | `graph` |
| Inspect one document | `doc <name>` |
| Find an ID or `Document §N` | `id <query>` |
| List IDs | `ids [--kind K]` |
| Project frontmatter fields | `docs [glob] [--fields A,B]` |
| Run structural checks | `check [--gate key1,key2]` |
| Export or trace the entity graph | `dump [--kind K]` / `trace <entity>` |
| Build a deterministic task context | `brief <task>` |
| Inspect changes against a baseline | `verify [--baseline REV]` |
| Classify document nature | `classify --pending` / `classify --validate` |
| Find undefined recurring terms | `harvest` |
| Find managed-value drift | `drift` |
| Generate interactive views | `html` / `html-entity` |

Add `--json` to query and analysis commands. The complete flag and exit-code
contract is in [references/command-contracts.md](references/command-contracts.md).

## Language model

DocStar separates human language from machine contracts:

- `--lang en|zh-CN` selects human-facing help, CLI labels, and HTML labels.
- `--json` always emits the `eg-3` English schema. `--lang` never changes JSON.
- New graph-governed project documents use stable English frontmatter keys and tokens;
  prose and headings may be English or Chinese.
- Legacy Chinese keys such as `性质`, `上游`, and `下游` remain accepted as migration
  input, but new documents use the canonical keys.

The shared project-document metadata contract is:

```yaml
locale: en # or zh-CN
purpose: <one sentence>
upstream: [<label>](<relative-path>.md)
downstream: [<label>](<relative-path>.md)
status: draft # draft | pending-approval | approved | closed
type: requirement # see the writing guide
nature: normative # normative | descriptive
```

See [references/writing-guide.md](references/writing-guide.md) for bilingual structural
rules and a content checklist. DocStar does not prescribe document headings or layout;
the governing workflow or Skill defines required content.

Platform control files are outside the document corpus: `AGENTS.md`, `CLAUDE.md`,
`SKILL.md`, hidden agent configuration directories, and the repository-root `agents/`
directory. A domain-document directory such as `docs/agents/` remains in the corpus.

## Zero configuration and conventions

Without configuration, DocStar recognizes Markdown links, wikilinks, common
frontmatter relationships, numbered sections, and generic requirement/task
sections. Project-specific IDs and policies live in:

```text
<corpus>/.docstar/conventions/conventions.json
```

Configuration discovery is explicit `--conventions`, corpus-local config, nearest
ancestor config up to the Git boundary, then the built-in default. Invalid config
fails closed with exit code 2.

Bundled presets can be selected without copying a config:

```bash
python3 docstar.py check --preset gmgn-v1 --json --corpus /path/to/project
```

The GMGN preset understands the stable `Goal.md → Requirement.md → Design.md →
Task.md` chain, `Rn-ACn` acceptance criteria, GMGN task IDs, and the shared metadata
contract. Details are in [references/conventions.md](references/conventions.md).

## Reading check results

Entity checks use four structural states:

- `structurally_complete`: all required structural inputs were available.
- `tainted`: an unclassified document influenced the result.
- `broken`: a required input could not be resolved.
- `dormant`: the policy was not declared and therefore did not run.

These states are structural, not semantic approval. `check` changes its exit code
only when `--gate` names one or more check keys. Unknown gate keys exit 2.

## Agent workflow

The repository root is also a Codex and Claude Code skill. Resolve the tool path
from `SKILL.md`, query with JSON first, and fetch source text only through returned
`file:line` pointers. Before delegating a task, use:

```bash
python3 /path/to/DocStar/docstar.py brief <task> --json --corpus /path/to/docs
```

## Development

```bash
python3 tests.py --skip-slow
python3 internal/corpus.py --selftest
python3 conventions/__init__.py --selftest
```

Contributor rules, including the maintainer-only golden workflow, are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
