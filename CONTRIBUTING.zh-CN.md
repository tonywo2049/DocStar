---
locale: zh-CN
purpose: 规定 DocStar 贡献所需的测试、兼容规则和审查工序。
status: approved
type: contribution-guide
nature: normative
---

# 参与 DocStar 贡献

[English](CONTRIBUTING.md)

`AGENTS.md` 约束仓库里的 coding agent；本指南面向人类贡献者和 PR，规定测试、
兼容性与 golden 工序，两者不能互相替代。

DocStar 运行时只依赖 Python 3.9+ 标准库。

## 必跑检查

提交 PR 前运行：

```bash
python3 tests.py --skip-slow
python3 internal/corpus.py --selftest
python3 conventions/__init__.py --selftest
python3 docstar.py verify --json
```

所有命令都必须退出 0。维护者还要在本机运行 `python3 tests.py`；其中的性能断言不放进共享
CI，避免机器负载造成误报。

CI 覆盖 Python 3.9–3.13，JSON 输出必须跨版本逐字节一致。

## 引擎改动先写失败测试

涉及解析、图、检查或输出行为时：

1. 先加 fixture 和一个会失败的断言。
2. 实现最小且完整的改动。
3. 同批补负例和兼容用例。
4. 跑完必跑检查。

PR 说明对外可观察的改前、改后行为即可。外部贡献者不需要补历史内部 `EG-*`、`DG-*` 编号。

## Golden 工序

`golden/*.json` 逐字节锁定公开 JSON 合同。贡献者和 agent 不得为了让测试变绿而手改或重建。

已批准的 schema 改动确实需要改变输出时：

1. 贡献者列出受影响的命令和字段。
2. 维护者检查新旧结构化差异。
3. 维护者运行带 schema 护栏的生成器：

   ```bash
   python3 scripts/update_golden.py --schema <expected-schema>
   ```

4. 维护者检查生成 diff，再跑完整测试。

脚本会拒绝与引擎不一致的 schema 参数，并逐个 golden 打印顶层键增删。

## 中英文一致性

公开文档成对维护：

- 英文主版：`README.md`、`CONTRIBUTING.md`、`references/*.md`。
- 简体中文：同名的 `*.zh-CN.md`。

两版的命令、ID、占位符、代码块、token 值域、警告和链接目标必须一致；正文可以自然翻译。
新增机器字段和值在两版里都保持英文。

`SKILL.md` 只保留一份可执行 skill，不拆成两个语言目录。触发描述覆盖中英文，运行时跟随项目或
用户语言。

## Conventions 兼容规则

新增 conventions 键必须同时满足：

1. additive 且可选；
2. 缺席时休眠，不改变既有 golden；
3. 非法时 fail-closed。

同批补 loader selftest、端到端正例、负例和 conventions hash 变化断言。

## 审查范围

实质性代码改动需要独立代码审查，重点检查未测面、断言判别力和不必要复杂度。实质性规范文档
改动需要一次独立证伪式审查，覆盖事实、完整性、内部一致、上下游一致、过度设计、语态和可判定性。
纯 typo 与格式调整豁免。
