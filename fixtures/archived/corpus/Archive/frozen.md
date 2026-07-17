---
性质: 规范
目标: fixture 已归档文档——自身上游含一条真断链，证「排除时该 finding 消失、包含时回来」（EG-30-AC1/AC4）；不回列 live-a 为下游，使 --include-archived 后与 live-a 的上游关系构成一条单向边 finding（EG-30-AC3）
上游:
  - [gone](../missing.md)
下游: []
---

# 已归档记录（frozen）

历史归档内容，正常情况下（默认过滤）不参与语料判定。

## 批次登记

- **AR1** 归档批次登记条目（登记原件在本归档件内——默认排除时 id 索引不含本文件的 AR1 出现、活文档出现处仍可查；--include-archived 后本文件出现回归，EG-30-AC1「id 索引不含其出现」两侧面）。
