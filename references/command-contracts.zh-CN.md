---
locale: zh-CN
purpose: 定义 DocStar 命令形式、退出码和 eg-3 JSON 输出面。
status: approved
type: command-contract
nature: normative
---

# 命令与 JSON 合同

[English](command-contracts.md)

## 路径与通用旗标

相对路径从调用者当前目录解析。默认语料根是当前目录。`html` 和 `html-entity` 未指定路径时，
分别写入当前目录的 `graph.html` 和 `entity_graph.html`。

- `--json`：输出稳定的 `eg-3` 公开 JSON 合同。
- `--lang en|zh-CN`：切换人类可读标签，不改变 JSON。
- `--corpus DIR`：指定 Markdown 语料根。
- `--conventions DIR`：覆盖自动发现的 conventions。
- `--preset NAME`：使用 `gmgn-v1` 等内置 preset。
- `--include-archived`：扫回被 `archive_globs` 排除的内容。
- `--kind K`：投影 `ids` 或 `dump`，接受 eg-3 英文 token。
- `--fields A,B`：投影 frontmatter，接受正式键或旧别名。
- `--gate key1,key2`：按 `check` 顶层键设门禁，接受 eg-3 英文键。
- `--baseline`：设置 `verify`、`classify` 或 `harvest` 的比较基线。

`--conventions` 与 `--preset` 互斥。

## 退出码

- `0`：命令完成；未传 `--gate` 时，`check` 保持 advisory。
- `1`：查询或 kind 未命中，或指定 gate 命中。
- `2`：用法、旗标、语言、preset、gate 键或 conventions 配置非法。

## 命令形式

```text
docstar.py graph
docstar.py doc <name>
docstar.py id <ID>
docstar.py id "<doc> §N"
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
docstar.py html [output]
docstar.py html-entity [output]
```

名称解析依次使用路径限定后缀、精确 stem、alias、前缀和子串。多命中时列出候选并退出 1。
CI 应显式传 `verify --baseline`。

## eg-3 JSON 顶层键

所有合同键和内置枚举 token 都是英文。源路径、文档标题、原文、ID 和项目自定义 kind 属于源数据，
不会被翻译。嵌套结构由 `golden/*.json` 逐字节锁定。

| 命令 | 顶层键 |
|---|---|
| `graph` | `docs_total`, `docs_with_frontmatter`, `chains` |
| `doc` | `doc`, `meta`, `upstream`, `downstream`, 可选 `frontmatter_relations`, `frontmatter_references_in`, `body_links_out`, `body_links_in`, `section_references_out`, `section_references_in`, `section_count`, `top_id_mentions` |
| `id <ID>` | `id`, `kind`, `total`, `docs` |
| `id "<doc> §N"` | `query`, `target_anchor`, `references` |
| `ids` | `kinds`；每项含 `kind`, `unique`, `total`, `note`, `ids` |
| `docs` | `docs` |
| `dump` | `context_manifest`, `schema_version`, `corpus_root`, `classification_complete`, `unknown_documents`, `entities`, `edges`, `reports` |
| `check` | `context_manifest`、文档 finding、实体 verdict、`schema_version` |
| `trace` | `context_manifest`, `query`, `resolved`, `nature`, `primary`, `candidates`, `attrs`, `edges` |
| `brief` | `context_manifest`, `schema_version`, `mode`, `query`, `resolved`, `nature`, `judgment_status`, `classification_complete`, `truncated`, `deterministic_deduplication`, `segments`, `omitted`, `diagnostics`, `boundary_pointers`, `tainted_by` |
| `verify` | `context_manifest`, `schema_version`, `baseline`, `baseline_source`, `scan_root`, `added_entities`, `removed_entities`, `added_edges`, `removed_edges`, `introduced_findings`, `graph_omissions`, `limitations` |
| `classify --pending` | `context_manifest`, `schema_version`, `mode`, `corpus_root`, `classification_complete`, `total_documents`, `pending_count`, `pending` |
| `harvest` | `context_manifest`, `schema_version`, `algo`, `filtered`, `candidates` |
| `drift` | `context_manifest`, `schema_version`, `drifts` |

当前 `check` 完整键集由 `tests.py::a_contract_toplevel` 和 `golden/check.json` 锁定，CI 不应另抄一份
不完整清单。

## 版本边界

`eg-3` 直接替换 `eg-2` 的混合语言 JSON，不提供混合输出兼容模式。输入兼容仍保留：旧中文
frontmatter 键和内置 selector 可继续使用，但所有 JSON 响应都是 eg-3。
