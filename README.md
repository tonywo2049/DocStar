---
性质: 记述
---

# DocStar

**把一堆互相引用的 Markdown 文档变成一张可查询的关系图、一套可检索的实体索引、外加一台自动体检机。**

零依赖（Python 3.9+ stdlib）、当前不建持久索引、每次全量重扫——没有过期缓存要同步。几百篇文档亚秒级。

<!-- badges 占位：CI / Python 3.9+ / MIT —— CI 建成后启用 -->
<!-- 截图占位：graph.html（文档关系图）+ entity.html（实体查询页）双图 —— 发布波补 -->

## 目录

- [它解决什么](#它解决什么)
- [特性一览](#特性一览)
- [设计基线：三层切分](#设计基线三层切分)
- [Agent-first 设计](#agent-first-设计)
- [安装与卸载](#安装与卸载)
- [快速开始](#快速开始)
- [命令总览](#命令总览)
- [conventions 配置](#conventions-配置)
- [对比与边界](#对比与边界)
- [自宿主：本仓就是零配置活样例](#自宿主本仓就是零配置活样例)
- [文档](#文档)
- [项目状态](#项目状态)
- [License](#license)

## 它解决什么

在 agent 驱动的项目里，几个结构性事实同时成立：agent 没有跨会话记忆，项目里唯一持久的东西是**写下来的文字**——文字不是「关于工作的记录」，它就是工作本身的共享内存；agent 众多且并行，N 个 agent × M 篇文档，读取成本是乘法；agent 写得又快又流畅，能自信地引用根本不存在的东西。于是两种病必然发生：

1. **引用完整性以 agent 速度腐坏**——代码里引用一个不存在的符号，编译器当场报错；文档里引用一个不存在的裁定、概念、章节，**什么都不会响**。链接、章节引用、依赖声明悄悄失效，没人发现；用的 agent 越多，坏得越快。
2. **上下文获取成本从不摊销**——人读过一遍能记住，agent 不能：每个 agent 每次都付全价，不知道该读哪部分就整篇读。「X 在哪定义、谁依赖 Y」每次都要重新翻文件。

两种病的解药是同一件东西：**符号表**。如同编译器的符号表既服务类型检查（报未定义符号）也服务 IDE 导航（跳定义/找引用）——一张表，两种用途。

DocStar 就是**文档语料的编译器前端**：符号表（每个标识符/术语/章节在哪）+ 引用检查器（死链、悬空引用、单向边）+ 依赖解析器（一件事依赖哪些文档）。

为什么 grep 不够：定位问题 grep 免费就能解；它解不了的是**闭世界问题**——「这个东西到底有没有定义」「这条声明到底落没落账」。快速定位只是符号表的副产品，不是目的。

## 特性一览

- **零配置关系图**——任何 Markdown 语料开箱即出上下游/关联图，不要求遵守任何写作规范
- **开放类型实体索引**——「类型小节标题 + 加粗条目」零配置抽实体；已有 ID 语法（如 `R7-AC1`）一次声明即被精确索引
- **分层一致性检查**——引用级检查永远内置，跨类型政策按声明执行，三态判定不装绿
- **确定性上下文编译器**——`brief` 输出任务闭包+边界指针，给 agent 的起跑上下文
- **增量与维护命令**——`verify` 改动差分、`classify` 分类台账、`harvest` 未定义高频词、`drift` 值漂移表
- **自包含 HTML 可视化**——关系图页+实体查询页，单文件 `file://` 直开
- **明确退出码合同**——`0` 干净 / `1` 命中 / `2` 用法配置错（fail-closed），可直接接 CI

## 设计基线：三层切分

- **关系（边）通配**——任意 frontmatter 键、Markdown 链接、`[[wikilink]]`、章节引用皆成边，键名即边类型；声明为方向对（如 `上游`/`下游`）的键额外带 ↑↓ 方向+互查，其余键=无向关联边。对任何 Markdown 语料都成立，零配置。
- **实体识别、类型开放、走两条路**：
  - **零配置路**——文档里写"类型小节"标题（`## 需求`/`## Requirements`/`## 任务` 等，词表可扩）+ 节内加粗条目 `- **X** ...`，零 ID 语法即抽成实体，kind = 标题词本身（开放，不限内置的 7 个默认词）。这是"认 agent 自然写法"的设计取舍——文档大多是 agent 写的，不该要求每个项目先申报一套 conventions 才能用。内置通用 ID 形（`REQ-1`/`TASK-2`）也是零配置就能被索引、参与共现边。
  - **声明层**（conventions 的 `def_forms`/`doc_id_kinds`）——项目已经有自己的一套 ID 语法（比如 `R7-AC1`）时，声明后被精确索引、参与共现边。这是给"老项目"retrofit 存量 ID 用的加速器，不是"用实体层"的前提。
- **检查两层**——关系级检查（死链/单向边/断锚/悬空引用/歧义引用）永远内置、零配置、与 kind 无关；跨类型政策检查（比如"每条需求须有测试"）永远是**声明**（conventions 里的 required-edge 规则集），不冒充引擎内置知识，规则集缺席时只报"无规则声明"，不假装绿。

## Agent-first 设计

DocStar 假定语料的主要读者和写者都是 agent——执行者、编排者、评审者、CI 门禁，还有「下周的你」：在没有跨会话记忆的世界里，下一个会话的你也是全新 agent。接口决策从这里出发：

- **认 agent 的自然写法**——实体识别键在「类型小节+加粗条目」这种 agent 本来就在写的形态上（见设计基线），不发明一套要先学会的标注语法。
- **每个结论自带可引用锚**——输出全部给到 file:line 级出处，agent 能把证据链原样粘进自己的回传，不必二次翻找。
- **机器可读是一等输出**——任意命令加 `--json`；输出确定性、byte-stable，同输入同输出，可锁 golden、可做差分。
- **brief 是起跑线，不是围墙**——任务闭包+边界指针（「你拿到了这些节，全文在这里」）；agent 觉得不够自己再拉取，工具不替它设限。派发 subagent 时把 `brief --json` 直接粘进任务书，就是它的起跑上下文。
- **不装绿，因为 agent 会盲信绿**——判定分四态（structurally_complete / tainted / broken / dormant），结论建立在不完整输入上时显式暴露，政策未声明的检查自报 dormant 而非冒充完备；宁可红得难看，不给出一个会被无条件采信的假绿。

## 安装与卸载

DocStar 零安装——clone 下来按路径调用即可（见快速开始），不加任何可选项时 clone 目录就是唯一落点；装后自检 `python3 tests.py --skip-slow` 应全绿。要固定落点、让 agent 把命令用成反射，可再加（均可选，详见 [SKILL.md](SKILL.md)「Setup」）：

- **注册为 skill**：把本仓 symlink 进 agent 框架的 skills 目录，如 `ln -s /path/to/DocStar ~/.claude/skills/docstar`。
- **复制进项目**：把整个工具目录 copy 进你仓的 `tools/` 下。
- **写作约定进项目指令**：把 SKILL.md 的四条 doc-authoring conventions 加进项目 standing instructions（如 CLAUDE.md）。

卸载 = 逐个移除你创建过的落点：

- 注册过 skill → 删除 `~/.claude/skills/docstar`（symlink 或目录）。
- 复制进过项目 → 删除你仓里的工具目录副本。
- 写作约定进过项目指令 → 四条约定是语料侧写作纪律、留不留随你，但其中指向工具命令的句子（如 `classify --pending`）须一并清掉，否则成死指引。
- 运行残留 → 工具目录树内的各 `__pycache__/`（`internal/`、`conventions/` 下；跑过 tests.py 后根目录也有），以及未显式给输出路径时生成的 `graph.html`/`internal/entity_graph.html`。
- 不再要 clone 本体 → 整目录删除即净（默认写盘位点全在目录内）。
- **你语料里的 `.docstar/conventions/` 不删**——那是你项目的配置资产，不是工具的一部分；重装后继续生效。

## 快速开始

```bash
cd <你的文档仓>
python3 /path/to/DocStar/docstar.py graph               # 关系图（零配置）
python3 /path/to/DocStar/docstar.py check                # 体检：死链/单向边/断锚 + 实体层检查
python3 /path/to/DocStar/docstar.py html graph.html       # 交互式关系图页（自包含 HTML，浏览器打开）
python3 /path/to/DocStar/docstar.py html-entity entity.html  # 交互式实体查询页（同上，查实体/共现）
python3 /path/to/DocStar/docstar.py                       # 不带任何参数=打印全部命令（下方「命令总览」的权威源）
```

不需要任何配置文件，也不要求你的文档遵守某套规范——**任意 Markdown 语料开箱即用**（零配置能得到什么、配置后还能多什么，见[自宿主实测](#自宿主本仓就是零配置活样例)）。

## 命令总览

文档层（关系通配，零配置可用）：

```
docstar.py graph                       # 全局 frontmatter 上下游/关联链
docstar.py doc <名称>                  # 单文档：元信息/出入边/节标题/ID 概览
docstar.py id <ID>                     # 一个 ID 的全部出现位置（file:line）
docstar.py id "<文档> §3"              # 跨文档节引用：目标锚点 + 全部引用处（注意加引号）
docstar.py ids [--kind K]              # ID 清单与计数，按类别
docstar.py check [--gate 键1,键2]      # 一致性检查：死链/单向边/断锚/未登记参数 + 实体层检查项
```

实体层（`dump`/`trace`/`brief`/`verify`/`classify`/`harvest` + `check` 的实体半部分；识别机制见上）：

```
docstar.py dump                                    # 实体+边全量导出（byte-stable，golden 权威）
docstar.py trace <实体>                            # 一个实体的定义块全文 + 全部关系边
docstar.py brief <任务> [--mode execute|impact|review] [--budget N]
                                                    # 任务闭包+边界指针；确定性上下文编译器，给 agent 用的起跑上下文
docstar.py verify [--baseline REV] [--migrate]     # 增量差分：这次改动引入/删除了哪些实体/边/缺陷；
                                                    #   --migrate 专测文档搬家/改名有没有留断边
docstar.py classify --pending                      # 待声明"性质"（规范/记述）的文档清单，带判定证据
docstar.py classify --validate --baseline REV --manifest SCOPE
                                                    # 校验一个分片：范围内都已分类、范围外正文未变
docstar.py harvest [--baseline F]                  # 高频但未标注的候选术语；--baseline 对比上次输出做差量
docstar.py drift                                   # 受管值多处出现的取值差异表（只列不判，哪个对归写作判断）
```

可视化（自包含单文件 HTML，`file://` 直开）：

```
docstar.py html [输出路径]             # 文档层交互关系图：力导向布局+搜索定位+详情面板
                                       #   不给路径→写在工具目录下的 graph.html
docstar.py html-entity [输出路径]      # 实体层交互查询页：ego 邻域图+搜索+判定瓦片
                                       #   不给路径→写在 internal/entity_graph.html（落点目录和 html 不同，建议都显式给路径）
```

通用旗标：`--json`（任意命令，输出机器可读 JSON）· `--corpus DIR`（扫描根，默认=当前目录）· `--conventions DIR`（显式指定 conventions 目录，覆盖自动发现）· `--include-archived`（任意命令，停用 conventions 声明的 archive_globs 归档过滤，取证查询用）。

退出码：`0` 成功/干净 · `1` 查询未命中（含 `ids`/`dump` 的 `--kind` 未命中类别，stderr 列可选集合）或 `--gate` 命中 · `2` 用法或配置错误（fail-closed——conventions 缺必需 section、`--gate` 键名拼错、未知旗标，都不静默放过）。

## conventions 配置

配置文件固定路径：`<语料根>/.docstar/conventions/conventions.json`。发现顺序：

1. `--conventions DIR`（显式指定，最高优先级）
2. `<语料根>/.docstar/conventions/conventions.json`（自动发现）
3. 祖先目录：语料根父级逐层上行至 git 边界内的同名配置文件（最近者胜；无 git 边界则不采用）
4. 内置通用默认（什么都不配也能跑，见上「设计基线」）

配置是**整套替换**，不是逐项覆盖——必须含 `version` 字段和 5 个必需 section：`namespaces`/`def_forms`/`term_forms`/`form_headers`/`harvest`；缺任何一个，加载即报错退出（fail-closed，不会静默拿默认值补）。其余键（`doc_id_kinds`/`edges`/`type_sections`/`required_edges`/`cooccur_kinds` 等）可选，省略即回落内置默认或直接休眠。

完整样例见 [fixtures/corpus/.docstar/conventions/conventions.json](fixtures/corpus/.docstar/conventions/conventions.json)——可以直接照着改。

## 对比与边界

同类工具各管一段，DocStar 的位置在「语料内引用完整性 + 实体索引 + agent 上下文」：

| 工具 | 它做什么 | 与 DocStar 的分界 |
|---|---|---|
| [lychee](https://github.com/lycheeverse/lychee)、[markdown-link-check](https://github.com/tcort/markdown-link-check) | 检查链接死活，强项是**外部 URL** 的 HTTP 探测 | DocStar 不查外链；专注语料**内部**引用（frontmatter 边/`[[wikilink]]`/`§` 节引用都是一等公民），并在其上建图、抽实体 |
| [zk](https://github.com/zk-org/zk)、[dendron](https://github.com/dendronhq/dendron) | 个人笔记/知识库工作流：建笔记、模板、编辑器集成，链接图服务导航 | DocStar 不管理文档生命周期，是**只读测量仪**——面向规范/需求类语料的体检与依赖解析 |
| [vale](https://github.com/errata-ai/vale) | 散文风格 lint（措辞、风格指南规则） | DocStar 不管风格，只管引用结构与实体一致性 |

**DocStar 不是什么**：

- **不是笔记应用**——不创建、不改写文档，只读取与测量。
- **不查外部 URL**——体检范围=语料内引用；外链死活交给 lychee 这类工具。
- **不是裁决者**——`check` 是测量仪：关系级检查内置，跨类型政策必须声明；未声明就诚实报「休眠」，未分类语料诚实报 `tainted`，不装绿。
- **不做语义推断、永不调 LLM**——图是文字的镜子，只映射写下来的引用，绝不脑补连边；引擎零模型、零 prompt，输出确定性、可复跑，判断留给人和 agent。也因此它不是知识图谱、不是搜索引擎。

## 自宿主：本仓就是零配置活样例

本仓自己的文档故意不带 `.docstar/conventions/`——运行任何命令看到的都是纯内置默认行为，不是精心摆拍的 demo。clone 后可当场复跑核对：

- 关系图零配置：`python3 docstar.py graph` 即见本仓文档的 frontmatter 关系链（数字随仓演化，不在此写死）。
- 实体零配置的证明场在 `fixtures/generic/`：一份从零开始配合内置写法的语料，零配置抽出 7 个真实体（2 任务/2 参数/2 需求AC/1 专名）——`python3 docstar.py dump --corpus fixtures/generic --json`。
- 「先有自己的 ID 习惯、后接入工具」的语料（比如满篇 `EG-13` 这类自有编号），零配置查不到这些 ID——差的只是把这套写法声明给工具看：写一份 conventions 声明 ID 语法后，`id` 从查不到变为跨文件全命中（定义处+每个引用的 file:line），共现索引随之点亮。
- 想直接看「已声明 conventions」的完整效果：`python3 docstar.py dump --corpus fixtures/corpus --json`（该 fixture 自带 `.docstar/conventions/conventions.json`，自动发现，实测 109 实体 / 79 边）。

想自己实验：挑一个目录写 `conventions.json`（格式见上），`--conventions <目录>` 指过去，跑一遍 `dump`/`check` 对比前后。实验产物不要提交进本仓——本仓的"零配置"是设计声明，不是还没配置好的临时状态。

## 文档

给 agent 的用法合同（命令语义、JSON 输出契约表、写作约定、K-shot 示例）在 [SKILL.md](SKILL.md)——注册为 skill 后 agent 直接照它办事。贡献工序（测试两档、golden 纪律、conventions 三铁律）在 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 项目状态

**开发中，advisory 优先。** 引擎与测试可跑（clone 后 `python3 tests.py --skip-slow` 即可复核，含六件 golden 逐字节比对）；「关系通配 · 类型开放 · 检查=内置机器+声明政策」三层切分已全部落地；工具自身语料分类完备，自宿主存量 `python3 docstar.py check` 当场可见。边界：**DocStar 是测量仪，不是裁决者**——`check` 对未声明「性质」的语料会诚实报 unknown/tainted（fail-visible 设计，不装绿）；拿它当硬门禁前，先把语料分类做完、把想要的跨类型政策声明成 conventions 里的 required-edge 规则集。

## License

本项目以 [MIT License](LICENSE) 发布。
