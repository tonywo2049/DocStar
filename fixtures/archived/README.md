# 归档子树语料级过滤（DG-59/EG-30）

证明语料：`archive_globs` 声明生效后，`Archive/` 子树（任意深度）默认不入语料——不建节点、不发边、不进 classify 分母、不产 findings；`--include-archived` 取证开关停用过滤、命中件全量入图、全语义参与零降级（位置⊥性质裁决不变）。

## 用法

```bash
# 默认：Archive/ 子树被过滤
python3 docstar.py check --corpus fixtures/archived/corpus --json

# 取证：--include-archived 停用过滤
python3 docstar.py check --corpus fixtures/archived/corpus --include-archived --json
```

实际扫描根为 `corpus/`（本 README 置于其外，同 `fixtures/methodology/` 布局——避免本文档自身被当作语料的第 6 篇文档计入分母）。

## 预设声明了什么

`corpus/.docstar/conventions/conventions.json` 只声明本特性验证所需的两点：

| 键 | 值 | 作用 |
|---|---|---|
| `archive_globs` | `["Archive"]` | 单模式路径段匹配，覆盖任意深度的 `Archive/` 子树 |
| `edges.directed_pairs` | `[["上游", "下游"]]` | 点亮 上游/下游 方向判定，使单向边检查（KeyError 回归面）可测 |

其余必填 section（`namespaces`/`def_forms`/`term_forms`/`form_headers`/`harvest`）取最小骨架值，本语料不声明任何 ID 定义句式。

## 文件清单与断言角色

| 文件 | 性质 | 角色 |
|---|---|---|
| `live-a.md` | 规范 | 语料内活文档；frontmatter 上游 + 正文各一条链指向 `Archive/frozen.md`——证图外目标解析成功、不报死链（EG-30-AC2）；亦是 cmd_check 单向边推导式 `dst in g.docs` 守卫的 KeyError 回归面（守卫加入前，`declared_up` 含 (live-a, frozen) 而 frozen 默认不在 `g.docs` 时会直接 KeyError 崩溃） |
| `live-b.md` | 记述 | 普通活文档，充当语料分母第二篇，不涉归档 |
| `Archive/frozen.md` | 规范 | 已归档文档；自身上游含一条真断链（`../missing.md`）——排除时该 finding 随整篇一起消失，`--include-archived` 后回来；不回列 `live-a.md` 为下游，`--include-archived` 后与 live-a 的上游关系构成一条单向边 finding |
| `Archive/nofm.md` | 无 frontmatter | 归档子树内 unknown 分类文档；证 classify 分母/pending 随过滤开关增减 |
| `nested/Archive/deep.md` | 无 frontmatter | 位于 `nested/Archive/` 下（非根级 `Archive/`）；证段匹配单模式 `"Archive"` 对任意深度子树同样生效，无需 `Archive/**`/`**/Archive/**` 双模式声明 |

## 已知边界

- 本语料不声明任何 ID 定义句式（`def_forms` 留空）——实体层 dump 的 entities/edges 恒为空，`arch/default_dump_excludes` 断言对本语料是形状层面的守护（本语料不产生任何实体/边，故该断言当前恒真；未来若语料加入定义形态，断言即转为有效负载检验）。
- 排除面的**非空真**证明由 `doc_id_kinds`（`AR\d+`「归档条目」）承载：AR1 登记原件在 `Archive/frozen.md`、活文档 live-a.md 另有出现——`arch/id_index_two_sided` 断 id 索引默认仅见 live-a.md、`--include-archived` 后归档件出现回归（EG-30-AC1「id 索引不含其出现」两侧面）。声明了 `AR` 语法但**不声明** `def_forms`/`id_occ_kinds`（实体促升另有前置，id 出现索引即足以证枚举成员轴，死配置不留）。
- fixture 文件为新增内容，若尚未提交入 git 历史，`verify --baseline HEAD` 一类断言只验退出码与 JSON 形（`GitSource(HEAD)` 看不到未提交文件，基线图对本语料为空属预期）。
