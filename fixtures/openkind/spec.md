---
title: Open-kind proof corpus
性质: 规范
---

# 开放 kind 证明语料（fixture）

零配置默认词表之外的 kind 从「类型小节标题」涌现（EG-19），此语料自带 conventions 声明
三个 type_sections：`决策`（词表外开放 kind）、`Requirement`（需求 的同义写法，另成一 kind、不归并）、
`需求`（映射到内置默认 kind 需求AC，证默认词表与开放 kind 共存）。

## 决策

- **D-1**：采用方案甲作为默认路径。
- **D-2**：保留方案乙为回退期权。

## Requirement

- **user-can-undo**：删除后 5 秒内可撤销。

## 需求

- **REQ-100**：一条走内置默认 kind（需求AC）的通用需求。
