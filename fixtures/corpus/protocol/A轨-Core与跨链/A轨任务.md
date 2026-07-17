---
目标: fixture 合成 A轨任务表（eg-2 隔离级）——覆盖 任务声明（spec 锚 AC 列）、阅读依赖（spec 锚 § 列→节条目，新）、前置依赖（前置列→任务，新+环检测）、任务测试声明（红先列）、验证声明单一 canonical（ac_r{n}_ac{m}_ 前缀）、状态属性、删除线剔除死依赖、字段名 token 不成测试节点
性质: 规范
上游:
  - [A轨设计](A轨设计.md)
下游: []
状态: fixture（隔离级）
类型: 过程型
---

# 合成 A轨任务（fixture）

规格源三层：R*-AC*（需求）> 契约 C*-AC*/AUD-AC*（接口）> 设计 §（形态）。spec 锚列的 AC token＝任务声明源、其 § 引用部分＝阅读依赖源；前置列＝前置依赖源；红先测试列＝任务测试声明源；ac_r 前缀测试名（仅需求 AC）＝验证声明单一 canonical。

## 2. 任务卡

| # | 目标 | spec 锚 | 前置 | 红先测试 | done / 规模 | 状态 |
|---|---|---|---|---|---|---|
| **TA1.1** | Core 状态机 VSET/STAKE | R1-AC1、R1-AC2；C1-AC1；设计 §2.1 | — | `ac_r1_ac1_stake_admit` | AC 测试绿 / M | 已合并 |
| **TA2.1** | 集合凭据采纳 | C1-AC13；设计 §4.1 | — | `ac_r2_ac1_setcred_dispatch` | 测试绿 / M | 已合并 |
| **TA2.3** | 入站验证三件 + mint | R7-AC1；C2-AC1、C2-AC2；设计 §4.2、设计 §2.1 | TA2.1 | `packet_statement_binding`、`payload_type_gate`（负向，非 ac_ 前缀→无验证声明）、`ac_r7_ac1_inbound_mint` | P0 负向绿 + 正向绿 / M | 已合并 |
| **TA2.4** | 逃生舱退款拒付 | C2-AC31；设计 §4.3 | TA2.3 | `refunded_packet_escape_denied`（契约 AC 测试，无 r 型验证声明） | 负向绿 / S | 在飞 |
| **TA3.1** | 死依赖剔除 | C2-AC3；设计 §3.3 | ~~TA0.9 裁定~~、TA1.1 | `dual_ac_guard` | 待开工 / S | 待开工 |
| **TA9.1** | 环检测反例甲 | 设计 §2.1 | TA9.2 | `cycle_probe_a` | 待开工 / S | 待开工 |
| **TA9.2** | 环检测反例乙 | 设计 §2.1 | TA9.1 | `cycle_probe_b` | 待开工 / S | 待开工 |

## 3. 字段名 token 说明

TA2.3 核 `state_root` 与 `sequence` 反引号字段名 token 属实现细节，不在红先测试列、非 ac_ 前缀 → 不成测试节点（测试 kind 准入=强声明源）。
