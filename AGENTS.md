# DocStar 协作说明

- 修改前先读 `CONTRIBUTING.md`，只改与任务有关的文件。
- 涉及多篇 Markdown 的定义、引用、依赖或任务上下文时，先按 `SKILL.md` 使用 DocStar。
- DocStar 只使用 Python 3.9+ 标准库；不要引入运行时依赖。
- 修改引擎行为时先补能失败的测试，再实现最小修复。
- 不得手改或自行重锁 `golden/*.json`；输出面确需变化时，在变更说明里列出差异，交维护者确认。
- 提交前运行：

  ```bash
  python3 tests.py --skip-slow
  python3 internal/corpus.py --selftest
  python3 conventions/__init__.py --selftest
  ```

- 修改受 DocStar 管理的文档后，再运行 `python3 docstar.py verify --json`。
