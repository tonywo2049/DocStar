# Doc A — 代码遮罩证明语料（DG-41 / EG-21-AC1）

零配置通用语料（无 .docstar/conventions → 内置默认约定）。证明：围栏/行内代码内的示例
链接/wiki/§引用**不当真链接**（假阳清零），而代码外的真断链**仍被检出**（两侧都测）。

有效链接（应解析、不报死链）：[Doc B](doc-b.md)。

真断链（代码外，**应报死链**）：[缺失目标](nonexistent-file.md)。

真断 wiki（代码外，**应报死链**）：[[nonexistent-wiki]]。

真断锚（代码外，**应报断锚**）：doc-b §77（doc-b 无 §77）。

围栏代码块内的示例（**不应报**）：

```text
[围栏假链接](phantom-file.md)
[[phantom-wiki]]
见 doc-b §99
```

行内代码内的示例（**不应报**）：`[行内假链接](ghost-file.md)`、`[[inline-wiki]]`、`doc-b §88`。
