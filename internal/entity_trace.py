#!/usr/bin/env python3
"""entity_trace — trace entity definitions and grouped relations (eg-3 public output).

schema/定序取自 entity_model；实体与边取自 entity_extract.build(g, conv)（无持久索引，每次即时
构建，设计 §6）。相对 eg-1：去登记册别名依赖（EG-4；无 M.load_registry/_registry_aliases）；
primary 直读 entity.primary（DG-20 定义于降属性）；专名读 attrs.定义锚（DG-27）；边展示改
parse+consumers（DG-24，删 strength/check）。签名 cmd_trace(g, conv, query, as_json)（DocStar 冻结）。

解析序（EG-4-AC1）：①主键三元组精确 ②canonical_id 全局唯一 ③别名（conv.aliases→canonical /
g.canon→文档节点）④唯一前缀 / 唯一包含（canonical_id）⑤多命中→列候选退 1。
无命中→相近实体建议（大小写不敏感子串，≤10，退 1，EG-4-AC2）。
"""

import sys
from collections import defaultdict

import entity_extract
import entity_model as M
import i18n


def _fmt_key(key):
    """主键三元组 → kind:namespace:canonical_id（与解析序①输入形互逆）。"""
    return ":".join(key)


def _clip(s, n=72):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _parse_tuple(query):
    """kind:namespace:canonical_id 或 kind/namespace/canonical_id → tuple；非三段→None。"""
    for sep in (":", "/"):
        if sep in query:
            parts = query.split(sep)
            if len(parts) == 3 and all(p.strip() for p in parts):
                return tuple(p.strip() for p in parts)
    return None


def _resolve(g, conv, idx, query):
    """→ ("ok", key) | ("multi", [key…]) | ("none", None)。idx=主键 tuple → 实体。"""
    tup = _parse_tuple(query)                          # ① 主键三元组精确
    if tup is not None and tup in idx:
        return "ok", tup
    hits = sorted(k for k in idx if k[2] == query)     # ② canonical_id 全局唯一
    if len(hits) == 1:
        return "ok", hits[0]
    if len(hits) > 1:
        return "multi", hits
    alias = conv.aliases.get(query)                    # ③ 别名：conv.aliases → canonical
    if alias:
        ah = sorted(k for k in idx if k[2] == alias)
        if len(ah) == 1:
            return "ok", ah[0]
        if len(ah) > 1:
            return "multi", ah
    _cn, rel = g.canon(query)                          # ③ 文档昵称 → 文档节点
    if rel:
        dk = tuple(M.key_doc(rel))
        if dk in idx:
            return "ok", dk
    pre = sorted(k for k in idx if k[2].startswith(query))   # ④ 唯一前缀
    if len(pre) == 1:
        return "ok", pre[0]
    if len(pre) > 1:
        return "multi", pre
    con = sorted(k for k in idx if query in k[2])            # ④ 唯一包含
    if len(con) == 1:
        return "ok", con[0]
    if len(con) > 1:
        return "multi", con
    return "none", None                                # ⑤ 无命中


def _suggest(entities, query, limit=10):
    """相近实体（大小写不敏感子串匹配 canonical_id/display）；按主键定序取前 limit（EG-4-AC2）。"""
    ql = query.lower()
    out = [e for e in entities
           if ql in e["key"][2].lower() or ql in str(e["display"]).lower()]
    out.sort(key=lambda e: tuple(e["key"]))
    return out[:limit]


def _block_text(g, block):
    """按 primary/candidate 的 line..line_end 从 g.texts 摘录 → [(行号, 文本)…]。"""
    lines = g.texts.get(block["doc"], "").splitlines()
    return [(n, lines[n - 1]) for n in range(block["line"], block["line_end"] + 1)
            if 1 <= n <= len(lines)]


def _collect_edges(all_edges, key):
    """本实体为源或靶的全部边，按边类型分组；组内按 edge_sort_key 定序。"""
    groups = defaultdict(list)
    for e in all_edges:
        if tuple(e["src"]) == key or tuple(e["dst"]) == key:
            groups[e["type"]].append(e)
    for t in groups:
        groups[t].sort(key=M.edge_sort_key)
    return groups


def _edge_view(e, key):
    """→ (方向, 对端主键 tuple)；出=本实体为源、入=本实体为靶。"""
    if tuple(e["src"]) == key:
        return "出", tuple(e["dst"])
    return "入", tuple(e["src"])


_ENT_ATTR_ORDER = ("定义锚", "原始锚")


def _fmt_edge_attrs(attrs):
    parts = []
    for k, v in attrs.items():
        if isinstance(v, list):
            v = "、".join(map(str, v))
        parts.append(f"{k}={v}")
    return _clip(" ".join(parts), 72)


# ---------------- 渲染 ----------------

def _render_human(g, e, groups):
    key = tuple(e["key"])
    print(f"== {e['display']}  [{_fmt_key(key)}]  性质={e['性质']} ==")
    if e.get("状态"):
        print(f"状态: {_clip(e['状态'], 120)}")
    for ak in _ENT_ATTR_ORDER:
        if ak in e["attrs"]:
            v = e["attrs"][ak]
            print(f"{ak}: {_clip('、'.join(map(str, v)) if isinstance(v, list) else v, 120)}")

    p = e["primary"]
    if p:
        print(f"\n定义块  {p['doc']}:{p['line']}..{p['line_end']}")
        for n, ln in _block_text(g, p):
            print(f"  {n:>5}  {ln}")
    else:
        print("\n定义块  无（未在语料找到定义形块）")
    if e["candidates"]:
        print(f"候选定义块 {len(e['candidates'])} 个：")
        for c in e["candidates"]:
            print(f"  {c['doc']}:{c['line']}..{c['line_end']}")

    total = sum(len(v) for v in groups.values())
    print(f"\n关系边 {total} 条（本实体为源→/靶←）：")
    if not total:
        print("  （无）")
    for etype in M.EDGE_TYPES:                          # 表B 顺序分组
        group = groups.get(etype)
        if not group:
            continue
        parse, consumers = M.EDGE_TYPES[etype]
        cons = "、".join(sorted(consumers)) if consumers else "—"
        print(f"[{etype}] parse={parse} consumers={cons} ×{len(group)}")
        for ed in group:
            direction, peer = _edge_view(ed, key)
            arrow = "→" if direction == "出" else "←"
            av = _fmt_edge_attrs(ed["attrs"])
            print(f"  {arrow} {_fmt_key(peer)}  {ed['prov']['file']}:{ed['prov']['line']}"
                  + (f"  {av}" if av else ""))


def _json_top(g, e, groups, query):
    key = tuple(e["key"])
    p = e["primary"]
    primary = None
    if p:
        primary = {"doc": p["doc"], "line": p["line"], "line_end": p["line_end"],
                   "text": "\n".join(ln for _n, ln in _block_text(g, p))}
    edges = {}
    for etype in M.EDGE_TYPES:                          # 表B 顺序，组内 edge_sort_key 序
        group = groups.get(etype)
        if not group:
            continue
        lst = []
        for ed in group:
            direction, _peer = _edge_view(ed, key)
            item = dict(ed)
            item["方向"] = direction
            lst.append(item)
        edges[etype] = lst
    top = {"query": query, "resolved": list(key), "性质": e["性质"],
           "primary": primary, "candidates": e["candidates"], "attrs": e["attrs"],
           "edges": edges}
    if e.get("状态"):
        top["状态"] = e["状态"]
    return top


# ---------------- 命令入口 ----------------

def cmd_trace(g, conv, query, as_json):
    query = (query or "").strip()
    data = entity_extract.build(g, conv)
    entities = data["entities"]
    idx = {tuple(e["key"]): e for e in entities}

    status, res = _resolve(g, conv, idx, query)
    if status == "none":
        sugg = _suggest(entities, query)
        msg = f"无实体：{query}"
        if sugg:
            msg += "；相近：" + "、".join(_fmt_key(tuple(x["key"])) for x in sugg)
        print(msg, file=sys.stderr)
        return 1
    if status == "multi":
        print(f"「{query}」多命中 {len(res)} 个，请用三元组形"
              f"（kind:namespace:canonical_id）限定：", file=sys.stderr)
        for k in res:
            print("  " + _fmt_key(k), file=sys.stderr)
        return 1

    e = idx[res]
    groups = _collect_edges(data["edges"], res)
    if as_json:
        top = _json_top(g, e, groups, query)
        top = {"context_manifest": M.context_manifest(
            "worktree", conv, "trace", body=top,
            include_archived=getattr(g, "include_archived", False)), **top}  # DG-43
        print(M.emit(top))
        return 0
    if i18n.language() == "en":
        top = _json_top(g, e, groups, query)
        print(i18n.render_public(top))
        return 0
    _render_human(g, e, groups)
    return 0
