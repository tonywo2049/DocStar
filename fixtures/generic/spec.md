---
title: Widget Spec
性质: 规范
upstream: "[[overview]]"
related: guide.md
---

# Widget spec

## 需求

- **用户可离线创建 widget**：无网络时也能新建，联网后自动同步。
- **REQ-9**：删除操作可在 5 秒内撤销。

## Parameters

- **同步重试上限**：单次同步失败后最多重试的次数。
- **离线缓存容量**：本地最多缓存多少个未同步 widget。

## Tasks

- **接入同步网关**：把本地写队列接到同步网关。
- **加撤销缓冲**：实现 5 秒撤销窗口。

## Glossary

- **write queue**: the local buffer that holds not-yet-synced operations.
