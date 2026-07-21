---
locale: zh-CN
purpose: 说明 conventions 发现顺序、内置 preset 和兼容规则。
status: approved
type: conventions-guide
nature: normative
---

# Conventions

[English](conventions.md)

Conventions 用来把 DocStar 的通用解析器适配到项目自有 ID、表格和策略。它会改变抽取和检查，
不会改变 eg-3 公开 JSON 的语言。

## 发现顺序

1. `--conventions DIR`
2. `--preset NAME`
3. `<corpus>/.docstar/conventions/conventions.json`
4. 从语料根向上到 Git 边界，取最近配置
5. 内置通用默认

`--conventions` 与 `--preset` 互斥。显式配置是整套替换，不是逐键叠加。非法配置退出 2。

## 内置 GMGN preset

```bash
python3 docstar.py check --preset gmgn-v1 --json --corpus <project>
```

`gmgn-v1` 识别：

- `Goal.md → Requirement.md → Design.md → Task.md`；
- 固定的 `upstream` 与 `downstream` 链接；
- `Rn-ACn` 验收标准和 `(Mn-)Tn` 任务编号；
- 中英文正文都使用的标准任务表结构：`# | task | spec anchor | prerequisite | failing test |
  status`；
- 任务实体只来自该标准任务表，不从重复的加粗字段标签或其他表格产生；
- 从当前任务卡字段或独立指针表读取配置声明的 `execution_log` 与 `latest_event` Markdown
  链接，形成 `task → execution-log → latest-event`；
- `none`、`external:`、`无`、`外部：` 四种有意非链接前缀；
- 每条需求 AC 必须有入向任务声明的策略。

Preset 文件是 [conventions/presets/gmgn-v1.json](../conventions/presets/gmgn-v1.json)。
需要自动发现时，把它复制到 `.docstar/conventions/conventions.json`；除非项目明确分叉契约，
否则保持逐字节一致。

## 配置组

- `edges.*`：有向键对、节标记、自指词和有意非链接前缀。
- `type_sections`、`def_forms`、`doc_id_kinds`：类型小节和项目 ID 写法。
- `task_columns`、`id_occ_kinds`、`cooccur_kinds`、`ac_prefix_kinds`：任务表与 ID 参与域。
- `task_execution`：可选的指针表／卡片字段别名和 `canonical_task_table_only` 开关。缺席时
  执行日志抽取休眠；存在时，链接必须是真实的相对 Markdown 链接，日志必须声明
  `type: execution-log` 与 `nature: descriptive`，文件名必须匹配任务 ID，且 `latest_event`
  必须解析到同一文件内的锚。非法声明会显式进入 `execution_log_diagnostics` 和 `brief` 的
  omitted 清单。
- `nature_source`：把存量元信息映射为 `normative` 或 `descriptive`；显式 `nature`/`性质` 优先。
- `required_edges`：跨 kind 策略和 report/gate 级别。
- `uncovered_kind_exclusions`：明确不属于这些策略的通用 kind 或辅助 kind；不能用它
  隐藏策略主体的拼写别名。
- `managed_values`：供 `drift` 检查的受管值。
- `revision_target_kinds`、`cooccur_mapping_kinds`：检查域；缺席即 `dormant`。
- `archive_globs`：按路径段过滤归档。
- `aliases`、`namespaces`：文档别名和裸 ID 消歧锚。

完整压力样例在 `fixtures/corpus/.docstar/conventions/conventions.json`；分特性样例在
`fixtures/gmgn`、`fixtures/methodology`、`fixtures/nonlink`、`fixtures/reqedge` 和
`fixtures/archived`。

## 兼容规则

每个新键都必须可选且 additive，缺席时不改变既有输出，非法时 fail-closed。同批补 loader
selftest、端到端正例、负例和 conventions hash 变化断言。
