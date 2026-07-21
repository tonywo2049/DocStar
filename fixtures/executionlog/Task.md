---
locale: en
purpose: Exercise configured task execution-log pointers.
status: approved
type: task-plan
nature: normative
---

# Task

## Tasks

| # | task | spec anchor | prerequisite | failing test | status |
|---|---|---|---|---|---|
| **T1** | Pointer-table happy path | none | none | `red_t1` | in-progress |
| **T2** | Missing log target | none | none | `red_t2` | in-progress |
| **T3** | Missing latest-event anchor | none | none | `red_t3` | in-progress |
| **T4** | Card/log ID mismatch | none | none | `red_t4` | in-progress |
| **T5** | Current-card happy path | none | none | `red_t5` | in-progress |
| **T6** | Invalid log metadata | none | none | `red_t6` | in-progress |
| **T7** | Explicitly no execution history yet | none | none | `red_t7` | not-started |
| **TA2.11b** | Project-local ID remains outside gmgn-v1 | none | none | `red_ta` | in-progress |

| legacy id | note |
|---|---|
| **T9** | Non-canonical tombstone row must not define a task. |

- **Ownership, DAG, and three anchors**: first repeated field label.
- **Ownership, DAG, and three anchors**: second repeated field label.

## Execution pointers

| card_id | execution_log | latest_event |
|---|---|---|
| `T1` | [T1](execution/T1.md) | [event-2](execution/T1.md#event-2) |
| `T2` | [T2](execution/missing.md) | [event-1](execution/missing.md#event-1) |
| `T3` | [T3](execution/T3.md) | [missing-event](execution/T3.md#missing-event) |
| `T4` | [T4](execution/WRONG.md) | [event-1](execution/WRONG.md#event-1) |
| `T6` | [T6](execution/T6.md) | [event-1](execution/T6.md#event-1) |
| `T7` | none | none |

## T5 Current card

- `execution_log`=[T5](execution/T5.md); `latest_event`=[event-1](execution/T5.md#event-1).
