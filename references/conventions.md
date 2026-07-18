---
性质: 规范
---

# DocStar conventions

## 目录

- [发现顺序](#发现顺序)
- [配置族](#配置族)
- [修改纪律](#修改纪律)

## 发现顺序

1. `--conventions DIR`。
2. `<corpus>/.docstar/conventions/conventions.json`。
3. 从语料根父目录上行到 Git 边界，最近者胜。
4. 内置通用默认。

显式配置是整套替换，不是逐键叠加。必须包含 `version` 和 loader 声明的必需 section；非法值退出 2，不回落默认。

## 配置族

- `edges.*`：有向键对、节引用标记、自指词和有意非链接前缀。
- `type_sections`、`def_forms`、`doc_id_kinds`：实体类型小节和项目自有 ID 语法。
- `task_columns`、`id_occ_kinds`、`cooccur_kinds`、`ac_prefix_kinds`：任务表和 ID 参与域。
- `nature_source`：从项目已有 frontmatter 字段映射规范/记述性质；显式 `性质` 始终优先。
- `required_edges`：跨类型必需边规则及 `report`/`gate` 严重级。
- `managed_values`：受管值与属主绑定，供 `drift` 使用。
- `revision_target_kinds`、`cooccur_mapping_kinds`：修订传导和共现完整性检查域；缺席即 `dormant`。
- `archive_globs`：按路径段排除归档子树；`--include-archived` 可临时恢复。
- `aliases`、`namespaces`：文档别名和裸 ID 消歧锚。

完整配置样例在 `fixtures/corpus/.docstar/conventions/conventions.json`，分特性样例在 `fixtures/methodology`、`fixtures/nonlink`、`fixtures/reqedge`、`fixtures/archived` 等目录。

## 修改纪律

新增 conventions 键必须同时满足：

1. additive 可选；不填不改变既有行为。
2. 缺席休眠且 golden 零涟漪。
3. 非法值 fail-closed。

每个新键同时补 loader selftest、端到端正例、负例和 hash 变化断言。
