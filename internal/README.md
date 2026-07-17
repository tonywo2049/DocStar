---
性质: 记述
---

# internal — DocStar 内部模块

`docstar.py`（仓库根）的实现模块与渲染模板，**不是日常入口**——所有命令经根 `docstar.py <command>` 调用，用法见 [SKILL.md](../SKILL.md)。

- `corpus.py` — 语料源抽象（文件系统 / git 扫描）
- `entity_*.py` — 实体层：抽取 / 检查 / 追溯 / 简报 / 校验 / 分类 / 采集 / 建模 / HTML 渲染
- `*.html` — graph 与 entity 交互页的自包含模板

`docstar.py` 启动时把本目录加入 `sys.path`，故模块间以顶层名互相 import（如 `import corpus`）；带自检的模块可单独运行 `python3 internal/<模块>.py --selftest`。
