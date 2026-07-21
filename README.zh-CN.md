---
locale: zh-CN
purpose: 介绍 DocStar、对外契约和主要使用路径。
status: approved
type: guide
nature: descriptive
---

# DocStar

[English](README.md)

DocStar 把 Markdown 语料变成可查询的文档图、实体索引和结构检查器。它只读运行，
只依赖 Python 3.9+ 标准库，不保存索引，也不调用模型。

适合处理跨文档问题：

- 某个 ID 在哪里定义，谁引用了它？
- 一篇文档依赖什么，又被谁依赖？
- 编辑是否弄断了链接、章节引用或已声明策略？
- 一张任务卡实际需要哪些上下文？
- 一批文档在结构上能否交接？

## 快速开始

```bash
git clone https://github.com/tonywo2049/DocStar.git
cd DocStar
python3 docstar.py graph --lang zh-CN --corpus /path/to/docs
python3 docstar.py check --json --corpus /path/to/docs
```

不需要 `pip install`。相对路径都从调用者的当前目录解析。

## 安装

### Codex marketplace（推荐）

```bash
codex plugin marketplace add tonywo2049/DocStar
codex plugin add docstar@DocStar
codex plugin list
```

安装后新建 Codex 任务。不要再把手工 `docstar` 副本放入 `~/.codex/skills`；marketplace
安装与手工安装不得并存，否则会重复触发。

### 手工安装 Skill（可选）

### Git clone 加软链接

只在未安装 marketplace 插件时使用本方式。把 DocStar clone 到固定的绝对路径，再把该
checkout 链接到 Codex 或 Claude Code。将 `/absolute/path/to/DocStar` 替换成实际路径。

```bash
git clone https://github.com/tonywo2049/DocStar.git /absolute/path/to/DocStar
mkdir -p ~/.codex/skills ~/.claude/skills
ln -s /absolute/path/to/DocStar ~/.codex/skills/docstar
ln -s /absolute/path/to/DocStar ~/.claude/skills/docstar
```

### Release ZIP 或复制目录

从[最新 Release](https://github.com/tonywo2049/DocStar/releases/latest)下载
`Source code (zip)`，解压后把完整目录放到 `~/.codex/skills/docstar` 或
`~/.claude/skills/docstar`。

不要把新版文件叠加复制到已有目录。应完整替换已安装的 `docstar` 目录，避免新版已经删除或
重命名的文件残留自旧版本。

## 升级

### 通过 Codex marketplace 安装

先刷新 marketplace，再检查已安装版本：

```bash
codex plugin marketplace upgrade DocStar
codex plugin list
```

如果仍显示旧版本，从刷新后的 marketplace 重新安装：

```bash
codex plugin remove docstar@DocStar
codex plugin add docstar@DocStar
codex plugin list
```

### 手工 ZIP 或源码安装

如果通过软链接使用 Git clone，只需更新共享 checkout，无需重建链接。

```bash
git -C /absolute/path/to/DocStar pull --ff-only
```

如果通过 ZIP 或复制目录安装，下载最新 Release，并完整替换每个已安装的 `docstar` 目录。
需要备份时先把旧目录移走，不要把新版文件与旧目录合并。

把占位路径换成实际绝对路径，验证 checkout 或安装目录；输出的最后一行会显示已安装的发布版本：

```bash
python3 /absolute/path/to/DocStar/docstar.py
```

手工安装是可选方式，不得与 Codex marketplace 插件并存。无论采用哪种升级方式，完成后都要
新建 Codex task 或 Claude Code session，让客户端重新加载 Skill 指令。

## 卸载

通过 Codex marketplace 安装时：

```bash
codex plugin remove docstar@DocStar
codex plugin marketplace remove DocStar
```

手工安装时，只删除自己创建的 `docstar` 目录或软链接，不要残留两种安装方式。

## 命令

| 问题 | 命令 |
|---|---|
| 查看文档图 | `graph` |
| 查看单篇文档 | `doc <name>` |
| 查 ID 或 `Document §N` | `id <query>` |
| 列出 ID | `ids [--kind K]` |
| 批量投影 frontmatter | `docs [glob] [--fields A,B]` |
| 运行结构检查 | `check [--gate key1,key2]` |
| 导出或追踪实体图 | `dump [--kind K]` / `trace <entity>` |
| 生成确定性任务上下文 | `brief <task>` |
| 对比基线检查编辑 | `verify [--baseline REV]` |
| 补文档性质 | `classify --pending` / `classify --validate` |
| 找未定义高频术语 | `harvest` |
| 找受管值漂移 | `drift` |
| 生成交互视图 | `html` / `html-entity` |

查询和分析命令加 `--json`。完整旗标、退出码和 JSON 合同见
[references/command-contracts.zh-CN.md](references/command-contracts.zh-CN.md)。

## 多语言模型

DocStar 把人类语言和机器契约分开：

- `--lang en|zh-CN` 只切换帮助、CLI 和 HTML 的人类可读标签。
- `--json` 始终输出 `eg-3` 英文 schema，完全不受 `--lang` 影响。
- 新建且纳入文档图管理的项目文档使用固定英文 frontmatter 键和值；正文和标题可以写中文或英文。
- `性质`、`上游`、`下游` 等旧中文键仍可作为迁移输入，但新文档使用 canonical 键。

共享项目文档元信息契约如下：

```yaml
locale: zh-CN # 或 en
purpose: <一句话说明本文回答什么>
upstream: [<显示名>](<相对路径>.md)
downstream: [<显示名>](<相对路径>.md)
status: draft # draft | pending-approval | approved | closed
type: requirement # 类型表见写作指南
nature: normative # normative | descriptive
```

双语结构规则与内容检查清单见
[references/writing-guide.zh-CN.md](references/writing-guide.zh-CN.md)。DocStar 不规定章节或版式；
必备内容由项目工作流或当前 Skill 定义。

平台控制文件不属于文档语料：`AGENTS.md`、`CLAUDE.md`、`SKILL.md`、隐藏的 agent 配置目录，
以及仓库根的 `agents/`。`docs/agents/` 这类业务文档目录仍会进入语料。

## 零配置与 conventions

零配置时，DocStar 能识别 Markdown 链接、wikilink、常见 frontmatter 关系、编号章节，
以及通用需求和任务小节。项目自有 ID 和策略写在：

```text
<corpus>/.docstar/conventions/conventions.json
```

发现顺序是：显式 `--conventions`、语料根配置、向上到 Git 边界的最近配置、内置默认。
非法配置退出 2，不静默回落。

也可以直接使用内置 preset：

```bash
python3 docstar.py check --preset gmgn-v1 --json --corpus /path/to/project
```

GMGN preset 识别固定的 `Goal.md → Requirement.md → Design.md → Task.md` 文档链、
`Rn-ACn` 验收标准、GMGN 任务编号和共享元信息契约。详见
[references/conventions.zh-CN.md](references/conventions.zh-CN.md)。

## 读取检查结果

实体检查使用四种结构状态：

- `structurally_complete`：形成结论所需的结构输入齐全。
- `tainted`：未分类文档影响了结论。
- `broken`：必需输入无法解析。
- `dormant`：项目没有声明该策略，因此检查未运行。

这些状态不表示语义验收通过。只有显式传 `--gate` 时，`check` 才按命中结果改变退出码；
未知 gate 键退出 2。

## Agent 工作方式

仓库根同时是 Codex 和 Claude Code skill。先从 `SKILL.md` 解析工具路径，用 JSON 缩小范围，
再按返回的 `file:line` 指针读取原文。派发任务前运行：

```bash
python3 /path/to/DocStar/docstar.py brief <task> --json --corpus /path/to/docs
```

## 开发

```bash
python3 tests.py --skip-slow
python3 internal/corpus.py --selftest
python3 conventions/__init__.py --selftest
```

贡献规则和仅维护者可执行的 golden 更新工序见
[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。

## License

MIT
