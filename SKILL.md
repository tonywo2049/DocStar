---
name: docstar
description: '当问题跨越多篇文档时使用——“X 在哪定义、谁引用了它”“这篇文档依赖什么、被谁依赖”“文档改动有没有弄断引用”“这批文档能否交接或发布”，或接手需要任务上下文的工作时。看到语料里有 .docstar/ 配置目录，优先用本工具查询和检查，不要手搓 grep 扫描。它把 Markdown 语料当作可查询的文档图、实体索引和引用检查目标。Use when a question spans Markdown documents: find definitions and references, inspect document dependencies, detect broken links or section references after edits, validate a docs tree before handoff, or retrieve the exact context a task depends on.'
---

# DocStar

把 Markdown 语料当作可查询的文档图、实体索引和引用检查目标。DocStar 只用 Python 3.9+ 标准库，不调用模型、不保存索引；每次运行都重扫语料。

先把 `<tool-dir>` 解析为本 `SKILL.md` 所在目录，再调用唯一入口：

```bash
python3 <tool-dir>/docstar.py <command> [args] [--corpus DIR] [--conventions DIR]
```

`--corpus` 是受治理的 Markdown 语料根，不一定等于仓库根。工具安装在项目内时显式传它，避免把工具源码和说明当成业务语料。

## 选择命令

| 目标 | 命令 |
|---|---|
| 查一个 ID 或 `Doc §N` 在哪、谁引用它 | `id <ID>` |
| 看一篇文档的元信息、进出边、标题和 ID | `doc <name>` |
| 看全局文档关系 | `graph` |
| 汇总文档 frontmatter | `docs [glob] [--fields A,B]` |
| 检查死链、断锚、单向边和实体规则 | `check [--gate key1,key2]` |
| 取得任务的确定性上下文闭包 | `brief <task> [--mode execute|impact|review]` |
| 检查当前编辑相对 baseline 引入了什么 | `verify [--baseline REV]` |
| 导出或追踪实体图 | `dump [--kind K]` / `trace <entity>` |
| 处理文档性质和术语候选 | `classify --pending` / `harvest` |
| 检查受管值漂移 | `drift` |

查询和分析命令默认加 `--json`，把键名按原样处理，不要假设只使用一种语言；`html`/`html-entity` 始终写文件。精确参数、退出码和各命令 JSON 顶层键见 [references/command-contracts.md](references/command-contracts.md)；只有在编写消费脚本、CI gate 或排查调用失败时读取它。

## 主 session：按需拉取

- “`<ID>` 在哪定义，谁引用它？” → `id <ID> --json`
- “这篇文档依赖什么、被谁依赖？” → `doc <name> --json`
- “这棵树现在自洽吗？” → `check --json`
- “我需要处理 `<task>`。” → `brief <task> --json`
- 文档编辑完成、提交或交接前 → `verify --json`

不要先整篇通读语料再手工拼关系；先用 DocStar 缩小范围，输出不够时再按 `file:line` 指针读原文。

## subagent：推送起跑上下文

派发具体任务前运行 `brief <task> --json`，把结果作为任务上下文。subagent 后续用 `id`、`doc`、`trace` 按需补充，不要把全语料塞进 prompt。

## 读判定

`check` 的 verdict 有四种 `judgment_status`：

- `structurally_complete`：结论建立在完整解析和分类上。
- `tainted`：结论依赖未分类文档，不是干净通过。
- `broken`：必需输入未解析，无法形成可靠结论。
- `dormant`：对应策略未在 conventions 声明，从未武装，不算通过。

把 `check --gate` 接入 CI 前先清理 `classify --pending`，并只 gate 已声明的策略。

## 配置语料

零配置即可使用文档关系图和通用实体写法。需要索引项目自有 ID、声明有向键、归档过滤或跨类型规则时，读取 [references/conventions.md](references/conventions.md)，再创建或修改 `<corpus>/.docstar/conventions/conventions.json`。配置错误必须硬失败，不要静默回落。

## 文档撰写约定

把以下规则加入项目的 `AGENTS.md`、`CLAUDE.md` 或文档规范：

1. 在带类型的小节下写实体，每个项目符号只定义一个实体，只加粗实体名。
2. 用 frontmatter、Markdown link 或 wikilink 承载关系，不靠散文暗示依赖。
3. 在术语首次定义处明确标注，保证定义和引用可区分。
4. 新文档出生时声明规范性或记述性；未声明保持 unknown，不猜默认值。
5. 文档编辑后、提交或交接前运行 `verify`。

需要可复制模板、完整示例或给存量语料回填性质时，读取 [references/writing-guide.md](references/writing-guide.md)。

## 安装与自检

clone 本仓后可直接按绝对路径调用。注册为 skill 时，让 skill 目录指向本仓根：

```bash
# Codex 用户级
ln -s /path/to/DocStar "${CODEX_HOME:-$HOME/.codex}/skills/docstar"

# Codex 仓库级
mkdir -p <repo>/.agents/skills
mkdir <repo>/.agents/skills/docstar
git -C /path/to/DocStar archive HEAD | tar -x -C <repo>/.agents/skills/docstar

# Claude Code 用户级
ln -s /path/to/DocStar "$HOME/.claude/skills/docstar"
```

不便使用符号链接时复制完整目录。Codex 新增或更新 skill 后打开新任务或重启客户端。

安装后运行：

```bash
python3 <tool-dir>/tests.py --skip-slow
python3 <tool-dir>/internal/corpus.py --selftest
python3 <tool-dir>/conventions/__init__.py --selftest
```

三条都必须退出 0。
