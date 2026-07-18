---
locale: zh-CN
purpose: 向维护者说明 DocStar 内部模块。
status: approved
type: maintainer-guide
nature: descriptive
---

# DocStar 内部模块

这里存放根入口 `docstar.py` 的实现模块与渲染模板，不是独立的用户命令。

- `corpus.py`：文件系统与 Git 语料源。
- `entity_*.py`：抽取、检查、追溯、简报、验证、分类、采集、建模和 HTML 渲染。
- `*_template.html`：自包含的文档图和实体图页面。

`docstar.py` 会把本目录加入 `sys.path`，所以内部模块使用顶层导入。带自检的模块可运行
`python3 internal/<module>.py --selftest`。

English: [README.md](README.md)
