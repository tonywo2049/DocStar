---
性质: 规范
name: docstar
description: Treat a corpus of cross-referenced Markdown docs (specs, requirements, RFCs, design notes) as a queryable graph instead of reading files linearly. Use it to find where an identifier or term is defined and everywhere it is referenced, to check a docs tree for broken links, dangling section references, and one-way dependency edges before or after editing, and to pull the exact set of documents a task depends on so an agent starts with the right context. Reach for this whenever a question is about relationships ACROSS documents, when the corpus is big enough that grepping is slow or misses cross-references, or when onboarding onto work that spans several documents.
---

# DocStar

DocStar is a **compiler front-end for a documentation corpus**: a symbol table (where every identifier, term, and section lives), a reference checker (broken links, dangling references, one-way edges), and a dependency resolver (what a piece of work depends on). It exists to fix two recurring problems with a living docs tree: reference integrity decays as documents are edited, and the cost of re-deriving "where is X / what depends on Y" by reading files never amortizes. Both become a single fast command.

It is zero-dependency (Python 3.9+ stdlib), keeps no persistent index, and re-scans the whole corpus on every run — so there is no stale cache to synchronize. On a few hundred documents this is sub-second.

Everything runs through **one entry point** — `docstar.py` (full invocation contract in *Invocation details* below):

```
python3 <tool-dir>/docstar.py <command> [args] [--json] [--corpus DIR] [--conventions DIR]
```

The other `.py` files are internal modules; `tests.py` is the test harness, not part of daily use.

## Two layers — know which one you're using

The dividing principle: **relationships are wildcard, entities need a grammar.** A link or a frontmatter reference between two documents is universal — any Markdown corpus has them, so the graph builds with zero configuration. But "this line *defines* a requirement" can't be recognized without knowing the project's forms, so typed entities are opt-in.

- **Document layer** — builds the **relationship graph** on **any** Markdown corpus, zero configuration. Relationships are wildcard: **every** frontmatter key whose value resolves to another document becomes an edge (the key name *is* the edge type), and every inline `[link](to.md)`, `[[wikilink]]`, and cross-document section reference is followed. Frontmatter values that are plain scalars (a date, a status word) are ignored, not guessed at. Declared directional key-pairs (e.g. `upstream`/`downstream`) additionally get ↑/↓ orientation and a reciprocity check; every other key is an undirected keyed edge. The ID **symbol index** (`id`/`ids`, and the unregistered-parameter check) reads whatever ID grammar the conventions supply — generic `REQ-N`/`TASK-N` out of the box, your own forms when configured. Commands: `graph`, `doc`, `id`, `ids`, `check` (the structural half).
- **Entity layer** — recognizes domain entities (requirements, acceptance criteria, parameters, tasks, defined terms, and typed edges between them) and runs consistency checks over them. It recognizes an entity two ways. **Config-free, from a typed section**: because agents write the docs, the tool keys on what they naturally write — put items under a `## Requirements` / `## 参数` / `## Tasks` heading and bold each name (`- **the name** — …`), and they're extracted with zero configuration. The heading declares the type; confining recognition to that section is what keeps ordinary bold prose from flooding in (the same section-scoping that makes glossary terms safe). Or **via a convention config**: when a corpus already has canonical identifiers (`R7-AC1`), a small grammar indexes them precisely and retrofits an existing corpus with zero edits — an accelerator, not a prerequisite. Commands: `dump`, `trace`, `brief`, `verify`, `check` (the entity half), `classify`, `harvest`. The shipped entity kinds target **specification / requirements-style corpora**; a very different domain may extend the type vocabulary (and, for genuinely new kinds, the kind set).

## Commands

| You want to know | Command |
|---|---|
| Where an identifier or `Doc §N` section reference lives, and every place it's used | `id <ID>` |
| A single document's frontmatter, up/down links, in/out references, headings, ID summary | `doc <name>` |
| The global frontmatter up/down-stream chains | `graph` |
| The catalog of identifiers by kind, with counts | `ids [--kind K]` |
| A batch frontmatter projection across many documents (e.g. status/type of a whole link-chain in one table) | `docs [glob] [--fields A,B]` |
| Consistency: broken links, dangling section refs, one-way edges, plus entity-layer checks | `check [--gate key1,key2]` |
| The full context a task depends on (its criteria, prerequisites, referenced sections, tests) + pointers to un-expanded neighbors | `brief <task>` |
| What entities/edges/defects **my** current edits introduced vs a baseline | `verify [--baseline REV]` |
| The complete entity+edge export (byte-stable, the golden authority) | `dump [--kind K]` |
| One entity's definition block plus all its typed edges | `trace <entity>` |
| High-frequency terms that are used but never defined (candidates to annotate) | `harvest` |
| Which documents haven't declared their nature yet (a migration worklist) | `classify --pending` |

Add `--json` to any command for machine-readable output.

## Invocation details — paths, flags, exit codes

**Where paths resolve.** Standard CLI semantics — DocStar makes no assumption about where it sits relative to your corpus. Every relative path (`--corpus`, `--conventions`, output files) resolves against your **cwd**, and the default corpus **is** the cwd. So the normal invocation is `cd <your-docs-repo> && python3 /path/to/DocStar/docstar.py check`. DocStar's own bundled fixtures are never mixed into a corpus you scan.

**Command forms** (behavior contracts an agent can rely on):

```
docstar.py graph                              # relationship chains; add --json for machine shape
docstar.py doc <name>                         # name resolution: exact stem > alias > prefix > substring;
                                               #   multiple hits -> lists candidates, exit 1; a dir-qualified
                                               #   name (M1/Requirement — path-suffix match) narrows same-stem docs
docstar.py id <ID>                            # every occurrence, file:line; miss -> near-matches, exit 1
docstar.py id "<doc> §3"                      # section-reference query — quote it (space + §); <doc> may be
                                               #   dir-qualified: id "M1/Requirement §3"
docstar.py ids [--kind <K>]                   # identifier catalog by kind
docstar.py docs [glob] [--fields A,B]         # batch frontmatter projection (EG-31); glob = fnmatch over
                                               #   the full rel path (* spans /); empty match -> exit 0
docstar.py check                              # all checks; per-check verdict objects in --json
docstar.py check --gate <key1,key2>           # keys = top-level keys of `check --json`;
                                               #   exit 0 clean / 1 non-empty|tainted|broken / 2 unknown key
docstar.py dump [--kind K] --json             # full entity+edge export (byte-stable); --kind projects
                                               #   entities to key[0]==K + touch-edges (corpus-level keys unchanged)
docstar.py trace <entity>                     # one entity: definition block + typed edges
docstar.py brief <task>                       # task closure + boundary pointers
docstar.py verify [--baseline <REV>]          # needs the corpus under git; default baseline is
                                               #   merge-base(HEAD,@{u}) falling back to HEAD — pin
                                               #   --baseline explicitly in CI/goldens (env-independent)
docstar.py classify --pending                 # nature-backfill worklist with evidence
docstar.py classify --validate --baseline <REV> --manifest <SCOPE>
docstar.py harvest [--baseline <FILE>]        # undefined high-frequency terms; delta view vs a saved run
docstar.py html [out] / html-entity [out]     # self-contained HTML pages (default: written next to the
                                               #   tool; open via file://)
```

**Flags.** `--json` machine output (agents: use it by default) · `--corpus DIR` corpus root (default: whole repo) · `--conventions DIR` explicit conventions (overrides discovery) · `--kind K` (dump/ids: project a single kind) · `--fields A,B` (docs: comma-separated frontmatter fields, order-preserved) · `--gate` (check) · `--baseline` (verify/classify/harvest) · `--manifest` (classify) · `--include-archived` (any command; a project's conventions may declare `archive_globs` so archived subtrees stay out of the graph by default — pass this to scan them back in for forensic id/trace queries).

**Exit codes.** `0` success/clean · `1` query miss or gate hit · `2` usage or config error, fail-closed (bad conventions config, misspelled gate key — never silently ignored).

**Self-check after install or a conventions change:** `python3 <tool-dir>/tests.py --skip-slow` — ships with its own fixture corpora and must pass green.

## JSON output contract

Every command below takes `--json`. The table pins each command's **top-level keys**, the value shape, and the **key language** (`zh`/`en`/`mixed`) — the graph is bilingual, so a machine consumer must treat keys as opaque as-written strings, not assume one language. Shapes are what the engine actually emits on `fixtures/corpus`; a drift-lock test (`tests.py`, layer A, `contract/top_*`) asserts the top-level key set per command against this table, so it can't silently rot. (Unifying key language to English is deferred to a future breaking release; this table records today's reality.)

| Command (`--json`) | Top-level keys | Value shape | Key lang |
|---|---|---|---|
| `graph` | `docs_total`, `docs_with_frontmatter`, `chains` | first two `int`; `chains` = `{rel: {上游:[rel], 下游:[rel], 关联?:{key:[rel]}}}` | en (chain sub-keys zh) |
| `doc <name>` | `doc`, `meta`, `上游`, `下游`, `关联`*(only if keyed edges)*, `被引用frontmatter`, `正文引出`, `被正文引用`, `引出节引用`, `被节引用`, `节标题数`, `ID提及TOP` | one document's frontmatter + in/out edges + heading & ID summary | mixed |
| `id <ID>` | `id`, `kind`, `total`, `docs` | `docs` = `{rel: [line]}` | en |
| `id "<doc> §N"` | `query`, `目标锚点`, `引用处` | `目标锚点` = `{line,title}` or `null`; `引用处` = `[{doc,line}]` | mixed |
| `ids [--kind K]` | **keys = the kind values** (open vocabulary, corpus-dependent) | each `{unique:int, total:int, note:str, ids:{id:count}}` | keys = kind values (`as-written`; zh in this corpus) |
| `docs [glob] [--fields A,B]` | `docs` | `[{doc:rel, has_fm:bool, <field>:[values]\|null}]` — fields are your `--fields`, missing = `null` (EG-31) | en (+ your field names) |
| `dump [--kind K]` | `context_manifest`, `schema_version`, `corpus_root`, `classification_complete`, `unknown_documents`, `entities`, `edges`, `reports` | **shape authority = the byte-locked golden baseline** (`golden/dump.json`, verified byte-for-byte by the test suite). `--kind` projects `entities` to `key[0]==K` and `edges` to touch (`src[0]==K ∨ dst[0]==K`); corpus-level keys unchanged. With --kind, edges are the incident set: an edge may reference an entity outside the projected entities list (not a closed graph — by design, for adjacency queries). | en (`reports` sub-keys zh) |
| `check [--gate]` | `context_manifest`, `schema_version`, doc-layer keys (`fm_断链`, `正文死链`, `缺frontmatter`, …), entity-layer keys (`CHK-2覆盖缺口`, `unresolved_reference`, …), `classification_complete`, … | Top-level keys come in **three shapes**: scalar meta (`schema_version` = str), list report (`fm_断链` = `[...]`), and **verdict object** (`CHK-*` = `{result, judgment_status, findings, tainted_by, blocked_by}`). Discriminant = `isinstance(v, dict) and "judgment_status" in v`. **These top-level keys are exactly the addresses `--gate` takes.** `judgment_status` ∈ {`structurally_complete`, `tainted`, `broken`, `dormant`} (DG-63; `dormant` = policy not declared, never armed — read the verdict, don't treat red as green) | mixed |
| `trace <entity>` | `context_manifest`, `query`, `resolved`, `性质`, `primary`, `candidates`, `attrs`, `edges` | one entity's definition block + grouped typed edges | mixed |
| `brief <task>` | `context_manifest`, `schema_version`, `mode`, `query`, `resolved`, `性质`, `judgment_status`, `classification_complete`, `truncated`, `去重稳定排序`, `segments`, `omitted`, `diagnostics`, `boundary_pointers`, `tainted_by` | bundle contract (verbatim segments + omitted + diagnostics + manifest) | mixed |
| `verify [--baseline REV]` | `context_manifest`, `schema_version`, `baseline`, `baseline_来源`, `scan_root`, `引入实体`, `删除实体`, `引入边`, `删除边`, `引入缺陷`, `进图缺失`, `局限说明` | incremental diff vs baseline (what my edits introduced/removed) | mixed |
| `classify --pending` | `context_manifest`, `schema_version`, `mode`, `corpus_root`, `classification_complete`, `total_documents`, `pending_count`, `pending` | pending worklist + per-doc mechanical evidence | en (`pending` items mixed) |
| `harvest [--baseline F]` | `context_manifest`, `schema_version`, `algo`, `filtered`, `candidates` | undefined high-frequency term candidates | en |

Every entity-layer command (`dump`/`check`/`trace`/`brief`/`verify`/`classify`/`harvest`) carries a `context_manifest` (corpus revision + tool version + conventions hash + mode, for reproducibility); the document-layer commands (`graph`/`doc`/`id`/`ids`/`docs`) do not.

## Using it from the main session (pull)

There is no one to hand the main agent a brief — so the main session **pulls on demand**. When a question about the corpus comes up, run the matching command instead of opening and skimming files:

- "Where is `<ID>` defined, and who references it?" → `id <ID>`
- "What does this document depend on / feed into?" → `doc <name>`
- "Did my edits break any references?" → `verify` (run it after editing, before committing)
- "Is the tree self-consistent right now?" → `check`
- "I'm about to work on `<task>` — what do I actually need to read?" → `brief <task>`

Treat these as reflexes, the way you'd reach for `grep` — but they answer relationship questions grep can't, and they cost one command instead of many file reads.

## Feeding a subagent (push)

When you dispatch a subagent to work on a specific task, run `brief <task> --json` and paste the result into its prompt. That gives it the right starting context (the task's criteria, prerequisites, and referenced sections) without it having to discover them. It complements the subagent pulling more detail with `id`/`doc` mid-task — push the starting line, let it pull the rest.

## Read the verdict, don't treat red as green

`check` returns a verdict per check, not a bare pass/fail:

- `structurally_complete` — the result rests on fully resolved, fully classified input.
- `tainted` — the conclusion depends on documents whose nature isn't declared yet; it is not a clean pass (the offending docs are listed).
- `broken` — a required input hasn't been resolved, so no conclusion was reached (what's blocking is listed).
- `dormant` — the policy for this check is not declared in conventions — never armed, never gates. Not a pass; the 说明 field says what is undeclared.

`--gate key1,key2` exits non-zero when a named check is failing, tainted, or broken — it will not report a clean green over incomplete input. Before using `check` as a release gate, make sure the corpus is fully classified (see `classify`), or the entity-layer conclusions will read as `tainted`/`broken` rather than `structurally_complete`.

## Conventions — how it adapts to your project

The engine is project-agnostic. The **conventions** are per-project. Every field is optional with a generic default, so a corpus with **no** config still gets the full wildcard relationship graph **and** config-free entities from typed sections; you add config only to index an existing ID scheme precisely, or to arm one of the optional policy checks. The configuration keys group into families (validated where applicable on load, and all folded into the conventions hash, so any config change is explainable):

- **Edge config (`edges.*`)** — `edges.directed_pairs` (which key-pairs are directional and reciprocity-checked), `edges.section_ref_marker` (the section token, default `§`), `edges.self_words` (words that may precede a `§N` and shouldn't resolve to another document, so bare `见`/`本文` prefixes don't mint cross-document edges), `edges.self_ref_words` (which of those additionally get an in-document anchor-existence check), `edges.nonlink_prefixes` (prefixes that declare a directional-key entry *intentionally* unlinked, so `check` routes it to `fm_有意非链接条目` rather than the missing-link bucket).
- **Entity recognition** — `type_sections` (config-free typed sections), `def_forms` + `doc_id_kinds` (definition grammar and the symbol index), `task_columns` (task-table column names; all four roles `spec/prereq/red/status` required when declared), `id_occ_kinds` / `cooccur_kinds` / `ac_prefix_kinds` (which ID grammars also mint entities, join the co-occurrence index, and how bare table-cell ACs are typed), plus several specialized extraction-form keys for unusual corpora (`option_rows`, `review_item`, `prov_form` — see the loader).
- **Nature mapping** — `nature_source` `{field, map}` derives a document's nature from a project's own frontmatter field when it carries no explicit `性质`; optional `normalize: "bracket-base"` retries a value shaped `基值（附注）` (base + full-width-bracket annotation) by its bracket-stripped base.
- **Cross-type / check policy** — `required_edges` (an entity kind must carry a named edge; severity `report` or `gate`), `managed_values` (owner-bound values watched for drift), `revision_target_kinds` / `cooccur_mapping_kinds` (the kind domains the transitive-revision and co-occurrence-completeness checks range over — absent means that check sleeps, not that it passes).
- **Corpus membership** — `archive_globs` (path-segment patterns, one segment each with no `/`; matching subtrees stay out of the corpus unless `--include-archived`).
- Plus `aliases`, and the `namespaces` anchors that disambiguate bare identifiers.

A ready-made preset that exercises many of these keys against a realistic corpus — and documents each choice — ships in `fixtures/methodology/`; single-feature fixtures (`fixtures/nonlink`, `drift`, `reqedge`, `archived`, …) isolate one key each. Resolution order:

1. `--conventions DIR` (explicit) — highest.
2. `<corpus>/.docstar/conventions/conventions.json` — your project's config, auto-discovered.
3. Ancestor directories, walking up from the corpus root's parent to the git boundary — the first directory containing `.git`, file or directory; nearest wins; without a git boundary ancestors are not used.
4. The bundled default set — lowest.

To adopt DocStar in a new project, drop a `conventions.json` under `<corpus>/.docstar/conventions/` (the loader validates it and reports exactly what's wrong on a bad config). Keep three roots distinct: the **repo root** (git boundary), the **corpus root** (`--corpus`, which files get scanned), and the **config dir** (`--conventions`, which conventions apply).

## Doc-authoring conventions (put these in your project's standing instructions)

The graph is only ever a projection of what's written, so a handful of writing habits keep documents queryable. Add these four to your project instructions (e.g. `CLAUDE.md`) or your doc-style guide, so every author and agent follows them. Minimum required = a document's **nature** plus its normative up/down links; the rest is optional but pays off.

1. **Put each entity under a typed section and bold its name.** Under a `## Requirements` / `## Parameters` / `## Tasks` heading (the heading names the type), write each item as `- **the name** — …`. The bold text becomes the entity's identity — a canonical ID if you have one, the phrase itself if you don't. This needs no configuration, and it's how agents already write, so the "discipline" is nearly free. (If a corpus already uses canonical IDs like `R7-AC1`, a one-time grammar indexes them precisely and retrofits it with zero edits — an accelerator on top, not a replacement.)
2. **Carry relationships as links, not prose.** A dependency written as a frontmatter reference (`upstream: [[other-doc]]`, `depends_on: sub/spec.md`), an inline `[link](to.md)`, or a `[[wikilink]]` becomes a real edge; the same dependency mentioned only in a sentence does not. Any frontmatter key works — use a declared directional pair (`upstream`/`downstream`) when you want ↑/↓ orientation and a both-ends-must-agree reciprocity check, any other key name for a plain typed edge. For the entity layer, also put criteria/mappings in the forms the conventions expect (a task table's dependency column, a mapping table).
3. **Annotate a term where it's defined.** Mark a coined term at its definition site (an in-place definition marker, or a glossary section) so "defined here" is unambiguous and "used but never defined" is detectable.
4. **Declare each new document's nature at birth.** Add a frontmatter field stating whether the document is **normative** (defines obligations/criteria that others depend on and whose changes must propagate) or **descriptive** (a record/log/investigation that no gate depends on). A document with no declaration is treated as unknown and surfaces in `classify --pending` until resolved — the tool never assumes a default and never silently "clears" the backlog.

## Worked example — write this, get that

The conventions above, applied. A small spec document (`spec.md`) in a corpus that also contains `overview.md`, `design.md`, `guide.md`, `research.md`:

```markdown
---
性质: 规范
upstream: "[[overview]]"
depends_on: research.md
related: guide.md
---

# Widget spec

## Requirements
- **Users can create widgets offline** — creation works without a network; sync happens later.
- **REQ-9** — a delete can be undone within 5 seconds.

## Parameters
- **sync retry limit** — how many times a failed sync is retried.

## Tasks
- **Wire up the sync gateway** — connect the local write queue to the gateway.

## Glossary
- **write queue**: the local buffer that holds not-yet-synced operations.

Rationale lives in [design](design.md); background in [[research]].
```

What the graph extracts, line by line:

| You wrote | The graph now knows |
|---|---|
| `upstream: "[[overview]]"` | a directed edge (this doc's upstream is `overview`), plus a reciprocity check — `overview` gets flagged if it doesn't list this doc back |
| `depends_on: research.md` | same — `depends_on`/`required_by` is a built-in directional pair |
| `related: guide.md` | an undirected edge typed `related` (**any** frontmatter key whose value resolves to a document behaves like this; the key name is the edge type) |
| `## Requirements` + a bold-name bullet | a requirement entity named `Users can create widgets offline` — the phrase **is** the identity, no ID scheme needed |
| `- **REQ-9**` | a requirement keyed `REQ-9`, also indexed corpus-wide by the symbol table |
| `## Parameters` / `## Tasks` bullets | a parameter and a task entity, same mechanism |
| `## Glossary` + `**write queue**: …` | a defined term — "used elsewhere but never defined" becomes detectable |
| `[design](design.md)`, `[[research]]` | reference edges into those documents |
| `性质: 规范` | this document's entities participate in gate checks; a `记述` (record/note) doc's entities are graphed but don't gate |

Equally important, what deliberately does **not** become a graph fact:

- "This builds on the design doc" said only in prose — no link, no edge. Relationships must be written as links.
- A bold phrase in ordinary prose, outside any typed section — stays prose. Section scoping is the flood gate that keeps ordinary emphasis out of the entity set.
- `title: Widget Spec` or `status: draft` — plain scalars under non-directional keys are ignored, never guessed at.

Query it back:

```
python3 <tool-dir>/docstar.py doc spec       # this doc's meta, in/out edges, headings
python3 <tool-dir>/docstar.py id REQ-9       # every mention, with file:line
python3 <tool-dir>/docstar.py check          # dead links, one-way edges, dangling refs
```

The heading vocabulary is bilingual out of the box (`Requirements`/`需求`/`验收标准`, `Parameters`/`参数`, `Tasks`/`任务`/`待办`, `Glossary`/`术语表`/`名词解释`), and headings don't need numbering. `性质: 规范|记述` are currently fixed tokens — treat them as keywords. A runnable copy of this corpus ships in `fixtures/generic/` and is held green by the test suite.

## Templates

Spec/requirements document:

```markdown
---
性质: 规范
upstream:
  - [the doc this one serves](parent.md)
---

# <topic>

## Requirements
- **<verifiable statement, or canonical ID>** — <detail>.

## Tasks
- **<action>** — <scope>; see [design](design.md).

## Glossary
- **<coined term>**: <definition>.
```

Note/record document (investigation, log, experiment record):

```markdown
---
性质: 记述
upstream:
  - [what this note informs](spec.md)
---

# <what happened / what was studied>

Findings reference spec §2 but impose nothing on it.
```

Habits that keep the graph faithful: one entity per bullet, and bold exactly the name (nothing else on the line bolded); put every real dependency in frontmatter or an inline link at the moment you rely on it; declare `性质` at birth; reference precise targets as `<doc> §N` when a section matters (if that stem is non-unique across directories, a bare `<doc> §N` resolves by the citing document's own directory; write `dir/doc §N` to pin it); run `verify` after editing, before handing off.

## Backfilling nature on an existing corpus

Classifying every legacy document is a deliberate, authorizable, shardable task — its own worklist, not something a passing session should do wholesale. `classify --pending` emits the worklist with mechanical evidence per document (how many entities it defines, whether it's referenced by normative docs, its title/type); an agent decides `normative` vs `descriptive` per document (low-confidence cases escalated), editing only frontmatter. `classify --validate --baseline REV --manifest SCOPE` checks a shard: everything in scope is classified, nothing outside scope had its body changed. `check` keeps reporting the backlog until it's actually gone.

## Setup

The tool is a directory of Python files plus a `conventions/` package; copy it into your project (commonly under `tools/`) and run `docstar.py` from your repo root. To make the commands a reflex for agents, register this `SKILL.md` as a skill and add the four authoring conventions above to your standing instructions.
