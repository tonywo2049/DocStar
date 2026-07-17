# fixtures — 测试固定语料

隔离级合成语料（纯合成、无真实内容），测试套件与 golden 基线的输入面。经 `--corpus fixtures/<名>` 作替换扫描根运行；docstar.py 对工具自带 `fixtures/` 前缀恒隔离，自宿主扫描不会把它们混入本仓语料。

各语料一句话定位：

| 目录 | 覆盖面 |
|---|---|
| `corpus/` | 主固定语料，自带 `.docstar/conventions/`（自动发现）——六件 golden 基线与契约 drift-lock 的输入源 |
| `generic/` | 零配置语料（无 conventions）——内置默认行为与 dormant（政策未声明）态的证明场 |
| `methodology/` | 外部工作流预设示例：`nature_source` 性质映射 + 任务表列名 + required_edges |
| `archived/` | `archive_globs` 归档子树过滤（默认排除 + `--include-archived` 取证） |
| `nonlink/` | `edges.nonlink_prefixes` 有意非链接声明分桶 |
| `dupstem/` | 同名文件消歧：列候选合同 + 同目录唯一改判 |
| `naturestick/` | `性质` 显式声明优先级（含显式空值不落映射） |
| `codemask/` | 围栏/行内代码剥离（解析忠实性——代码块里的内容不当真） |
| `selfsec/` | 同文档自引 `§` 断锚检查 |
| `openkind/` | 开放 kind（项目专有实体类别） |
| `reqedge/` | `required_edges` 规则集（覆盖/映射政策） |
| `briefmode/` | `brief` 三模式（execute / impact / review）与预算裁剪 |
| `drift/` | `drift` 值漂移探测 |

断言与期望值从规格独立推导、不读实现源；golden 基线对 `fixtures/corpus` 输出逐字节锁定（贡献工序见 [CONTRIBUTING.md](../CONTRIBUTING.md)）。快速体验：

```bash
python3 docstar.py dump --corpus fixtures/corpus --json    # 109 实体 / 79 边（已配置）
python3 docstar.py check --corpus fixtures/generic         # 零配置：内置检查 + dormant 态
```
