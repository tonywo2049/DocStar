---
性质: 规范
---

# DocStar 命令与 JSON 合同

## 目录

- [路径和旗标](#路径和旗标)
- [退出码](#退出码)
- [命令形式](#命令形式)
- [JSON output contract](#json-output-contract)

## 路径和旗标

相对路径全部相对调用者的当前工作目录解析。默认语料根是当前工作目录；工具不假设自己位于语料仓内。`html` 和 `html-entity` 未给输出路径时分别写到当前工作目录的 `graph.html` 和 `entity_graph.html`。

通用旗标：

- `--json`：机器可读输出，agent 默认使用。
- `--corpus DIR`：语料根；工具位于项目内时应显式指定。
- `--conventions DIR`：显式 conventions，覆盖自动发现。
- `--include-archived`：临时把 `archive_globs` 排除的归档内容扫回来。
- `--kind K`：`ids`/`dump` 的 kind 投影。
- `--fields A,B`：`docs` 的 frontmatter 字段投影。
- `--gate key1,key2`：以 `check --json` 顶层键为地址执行门禁。
- `--baseline`：`verify`、`classify`、`harvest` 的比较基线。

## 退出码

- `0`：命令成功；`check` 只有显式 `--gate` 才按检查结果改退出码。
- `1`：查询未命中、kind 未命中，或 gate 命中。
- `2`：用法、旗标或配置错误；必须 fail-closed。

## 命令形式

```text
docstar.py graph
docstar.py doc <name>
docstar.py id <ID>
docstar.py id "<doc> §3"
docstar.py ids [--kind K]
docstar.py docs [glob] [--fields A,B]
docstar.py check [--gate key1,key2]
docstar.py dump [--kind K]
docstar.py trace <entity>
docstar.py brief <task> [--mode execute|impact|review] [--budget N]
docstar.py verify [--baseline REV] [--migrate]
docstar.py classify --pending
docstar.py classify --validate --baseline REV --manifest SCOPE
docstar.py harvest [--baseline FILE]
docstar.py drift
docstar.py html [out]
docstar.py html-entity [out]
```

`html` 和 `html-entity` 始终写 HTML 文件；`--json` 不适用于这两个命令。

名称解析顺序是精确 stem、alias、前缀、子串；多命中列候选并退出 1。目录限定名使用路径后缀匹配。`verify` 默认 baseline 为 `merge-base(HEAD,@{u})`，没有 upstream 时回退到 `HEAD`；CI 必须显式指定 baseline。

## JSON output contract

键语言可能是 `zh`、`en` 或混合。消费方必须把键作为不透明字符串。`tests.py` 的 `contract/top_*` 锁定下表的顶层键集，实体层完整值形由 `golden/*.json` 逐字节锁定。

| 命令（`--json`） | 顶层键 | 值形态 | 键语言 |
|---|---|---|---|
| `graph` | `docs_total`, `docs_with_frontmatter`, `chains` | `chains={rel:{上游,下游,关联?}}` | en，`chains` 子键 zh |
| `doc <name>` | `doc`, `meta`, `上游`, `下游`, `关联?`, `被引用frontmatter`, `正文引出`, `被正文引用`, `引出节引用`, `被节引用`, `节标题数`, `ID提及TOP` | 单篇文档全景 | mixed |
| `id <ID>` | `id`, `kind`, `total`, `docs` | `docs={rel:[line]}` | en |
| `id "<doc> §N"` | `query`, `目标锚点`, `引用处` | 锚点或 `null`，以及引用坐标 | mixed |
| `ids [--kind K]` | 语料实际 kind 值 | 每个 kind 为 `{unique,total,note,ids}` | kind 原文；本 fixture 为 zh |
| `docs [glob] [--fields A,B]` | `docs` | `[{doc,has_fm,<field>:[values]\|null}]` | en + 调用者字段名 |
| `dump [--kind K]` | `context_manifest`, `schema_version`, `corpus_root`, `classification_complete`, `unknown_documents`, `entities`, `edges`, `reports` | 完整实体图；`--kind` 保留该 kind 实体和触及边，不保证闭图 | en，`reports` 子键 zh |
| `check [--gate]` | `context_manifest`, `fm_断链`, `fm_无链接条目`, `fm_有意非链接条目`, `单向边_我列它为下游_它未列我为上游`, `单向边_我列它为上游_它未列我为下游`, `正文死链`, `未登记参数_出现≥3次`, `节引用前缀未解析TOP`, `节引用断锚`, `缺frontmatter`, `schema_version`, `专名定义断锚`, `CHK-2覆盖缺口`, `CHK-2映射缺口`, `CHK-3传导断裂`, `CHK-环检测`, `unresolved_reference`, `ambiguous_reference`, `共现完备性`, `缺必需边`, `未覆盖kind`, `classification_complete`, `实体_schema_孤儿consumer` | 标量、列表报告、或 `{result,judgment_status,findings,tainted_by,blocked_by}` | mixed |
| `trace <entity>` | `context_manifest`, `query`, `resolved`, `性质`, `primary`, `candidates`, `attrs`, `edges` | 定义块和全部带类型边 | mixed |
| `brief <task>` | `context_manifest`, `schema_version`, `mode`, `query`, `resolved`, `性质`, `judgment_status`, `classification_complete`, `truncated`, `去重稳定排序`, `segments`, `omitted`, `diagnostics`, `boundary_pointers`, `tainted_by` | 原文段、遗漏、诊断和边界指针 | mixed |
| `verify [--baseline REV]` | `context_manifest`, `schema_version`, `baseline`, `baseline_来源`, `scan_root`, `引入实体`, `删除实体`, `引入边`, `删除边`, `引入缺陷`, `进图缺失`, `局限说明` | 相对 baseline 的增量差分 | mixed |
| `classify --pending` | `context_manifest`, `schema_version`, `mode`, `corpus_root`, `classification_complete`, `total_documents`, `pending_count`, `pending` | 待分类清单和机械证据 | en，`pending` 项 mixed |
| `harvest [--baseline F]` | `context_manifest`, `schema_version`, `algo`, `filtered`, `candidates` | 未定义高频术语候选 | en |
| `drift` | `context_manifest`, `schema_version`, `drifts` | 受管值不一致清单 | en，清单项 mixed |

实体层命令带 `context_manifest`，包含语料版本、工具版本、conventions 哈希、mode 和输出哈希。文档层导航命令不带该字段。
