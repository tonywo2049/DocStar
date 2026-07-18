#!/usr/bin/env python3
"""entity_brief — 确定性上下文编译器（EG-23 / DG-45·DG-46；扩展 EG-13，病二「起跑线」兑现）。

把 brief 从「单一执行闭包」重做为三模式确定性上下文编译器；仍零模型零 prompt、确定性、cwd 无关。

三模式（EG-23-AC2；皆确定性零语义，纳入集由确定性边/规则算出，非语义相似）：
  · execute（缺省）＝最小执行闭包＝EG-13-AC1 遍历表（**遍历面逐字不变**：任务声明→AC 定义块正文、
    阅读依赖→§ 节正文、前置依赖→前置任务行坐标+摘要、任务测试声明→红测试坐标；只走规范来源边，
    映射/共现不入闭包）。execute＝现行 EG-13 语义的 bundle 化，取材面不变，只按 DG-46 合同重形。
  · impact＝全部反向引用 + 下游传导点（谁依赖我、改我波及谁）：沿指向本任务的入边，
    {前置依赖/修订落账/映射} 反向＝下游传导点（取正文），其余入边＝反向引用（取坐标）。
  · review＝更宽确定性取材（评审这块要看的材料）：execute 闭包 + 同 namespace 兄弟断言（携状态，
    superseded 由状态属性显式可见）+ 结构邻居（全部相邻图邻居）+ unknown/歧义节点（经 omitted 显式报告）。

bundle 最小合同（EG-23-AC3 / DG-46；缺任一件的 bundle 非法）：①原文逐字（禁摘要替代）②来源锚
  （文件:行）③每段 inclusion_reason（因哪条边/规则纳入）④omitted 清单（禁无声截断）⑤diagnostics
  ⑥context_manifest（含 bundle output_hash）⑦去重/稳定排序标记。

部分分类降级（EG-23-AC1，替代 EG-13-AC4 全有全无）：语料 classification_complete=false 时出部分闭包——
  未分类（性质=unknown）节点＝跳过并显式报告（列入 omitted 原因「未分类跳过」+ judgment tainted），
  已声明部分产出可用闭包、未声明部分显式可见（不静默纳入、不静默丢弃）。任务来源非规范＝broken 但仍
  出任务行段 + 依赖列入 omitted（来源非规范），替代旧 EG-13-AC4 的「全空闭包」。

确定性预算裁剪（EG-23-AC4 / DG-45）：内容层原文按固定优先级裁剪——**根断言完整 > 直接前置与消费者 >
  结构邻居**；**绝不切半条断言**（断言为原子单位：整条入、或整条转坐标指针并列 omitted「预算截断」），
  标 truncated。预算由 --budget 传入（解释权在本模块）；缺省 CONTENT_BUDGET_CHARS。

锚点粒度（EG-23-AC5）：每取材段携 文件:行（坐标到行/节，非仅到文档）——agent 一跳回原文核验。
指针层/内容层分离（EG-23-AC6）：每段带 layer∈{content,pointer}；内容层携原文、指针层仅坐标（前置带摘要）。
  逐层展开＝指针段 + boundary_pointers 给出下一跳坐标（两跳＝对邻居再跑 brief）。受冻结 CLI 面约束
  （docstar 只透传 --mode/--budget，无 --depth），MVP 不做进程内 2-hop 展开，以边界指针替代。

judgment_status（DG-44 结构态命名，全输出面无「语义验收通过」词）：任务来源非规范→broken（结构不可判）；
  任务规范但闭包触达/跳过 unknown→tainted（不冒充干净绿）；任务规范且全规范→structurally_complete。

schema/定序/manifest 取自 entity_model；实体与边取自 entity_extract.build（每次即时构建，设计 §6）。
签名 cmd_brief(g, conv, query, as_json, mode="execute", budget=None)（docstar 冻结缝；mode/budget 由
  dispatch 透传）。零模型零 prompt、经 M.emit 序列化、确定性、cwd 无关。
"""

import sys
from collections import defaultdict

import entity_extract
import entity_model as M
import i18n

# 内容预算：bundle 内容层原文累计字符上限（缺省，可经 --budget 覆写）。命名策略常量非散落魔数。
CONTENT_BUDGET_CHARS = 16000

# 展开模式（EG-23-AC2）：execute（默认，向后兼容）/ impact / review。
MODES = ("execute", "impact", "review")

# execute 遍历面（EG-13-AC1 逐字：任务声明/阅读依赖/前置依赖/任务测试声明四类，只走这四类、只走规范来源边）。
_BRIEF_OUT = ("任务声明", "阅读依赖", "前置依赖", "任务测试声明")

# impact 下游传导点边类型（沿其反向＝改我波及谁，DG-45）：其余入边＝一般反向引用（取坐标）。
_IMPACT_TRANSMIT = ("前置依赖", "修订落账", "映射")

# 预算裁剪优先级三档（EG-23-AC4）：根断言完整 > 直接前置与消费者 > 结构邻居。数值越小越先纳入、越不被裁。
TIER_ROOT, TIER_PREREQ, TIER_NEIGHBOR = 1, 2, 3


# ---------------- 小工具 ----------------

def _fmt_key(key):
    return ":".join(key)


def _clip(s, n=120):
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


def _parse_budget(raw):
    """--budget 透传值（CLI 字符串/None）→ 有效字符预算（int）。解释权在本模块（DG-45）：
    None/非数字→缺省 CONTENT_BUDGET_CHARS；非负整数照用（0＝内容层全裁为指针）。"""
    if raw is None:
        return CONTENT_BUDGET_CHARS
    if isinstance(raw, int):
        return raw if raw >= 0 else CONTENT_BUDGET_CHARS
    s = str(raw).strip()
    return int(s) if s.isdigit() else CONTENT_BUDGET_CHARS


def _coord(p):
    """primary 块 → 锚坐标 {doc,line,line_end}（EG-23-AC5 行级粒度）；无定义块→None。"""
    if not p:
        return None
    return {"doc": p["doc"], "line": p["line"], "line_end": p["line_end"]}


def _block_text(g, p):
    """按 primary 的 line..line_end 从 g.texts 摘录为原文串（逐字，含节标题行；EG-23-AC3 ①）。"""
    lines = g.texts.get(p["doc"], "").splitlines()
    return "\n".join(lines[n - 1] for n in range(p["line"], p["line_end"] + 1)
                     if 1 <= n <= len(lines))


# ---------------- 任务解析（brief 各模式主体皆为任务，EG-23-AC2「brief <任务>」） ----------------

def _resolve_task(entities, query):
    """→ ("ok", ent) | ("multi", [ent…]) | ("nontask", ent) | ("none", None)。brief 只接受任务实体。"""
    tasks = [e for e in entities if e["key"][0] == "任务"]
    tup = _parse_tuple(query)                                   # ① 主键三元组精确
    if tup is not None:
        for e in entities:
            if tuple(e["key"]) == tup:
                return ("ok", e) if e["key"][0] == "任务" else ("nontask", e)
    exact_t = sorted((e for e in tasks if e["key"][2] == query),  # ② canonical_id 精确（任务内）
                     key=lambda e: tuple(e["key"]))
    if len(exact_t) == 1:
        return "ok", exact_t[0]
    if len(exact_t) > 1:
        return "multi", exact_t
    exact_all = [e for e in entities if e["key"][2] == query]   # 精确命中非任务→明示引导
    if len(exact_all) == 1 and exact_all[0]["key"][0] != "任务":
        return "nontask", exact_all[0]
    pre = sorted((e for e in tasks if e["key"][2].startswith(query)),  # ③ 唯一前缀（任务内）
                 key=lambda e: tuple(e["key"]))
    if len(pre) == 1:
        return "ok", pre[0]
    if len(pre) > 1:
        return "multi", pre
    con = sorted((e for e in tasks if query in e["key"][2]),    # ④ 唯一包含（任务内）
                 key=lambda e: tuple(e["key"]))
    if len(con) == 1:
        return "ok", con[0]
    if len(con) > 1:
        return "multi", con
    return "none", None


def _suggest_tasks(entities, query, limit=10):
    ql = query.lower()
    out = [e for e in entities if e["key"][0] == "任务"
           and (ql in e["key"][2].lower() or ql in str(e["display"]).lower())]
    out.sort(key=lambda e: tuple(e["key"]))
    return out[:limit]


# ---------------- 候选生成（每模式确定性取材面） ----------------

def _cand(key, tier, layer, reason, prov=None, summary=False, is_subject=False):
    """一个纳入候选：key=对端主键；tier=预算档；layer=content|pointer；reason=inclusion_reason；
    prov=触发边的溯源（无边=None）；summary=指针层是否附一行摘要（前置依赖用）。"""
    return {"key": tuple(key), "tier": tier, "layer": layer, "reason": reason,
            "prov": prov, "summary": summary, "is_subject": is_subject}


def _edge_reason(edge, direction, depth):
    """inclusion_reason（因哪条边纳入，EG-23-AC3 ③）：边类型 + 边源主键（从）+ 深度 + 方向。"""
    return {"边": edge["type"], "从": list(edge["src"]), "深度": depth, "方向": direction}


def _subject_cand(subject_key):
    return _cand(subject_key, TIER_ROOT, "content",
                 {"边": "(自身)", "从": [], "深度": 0}, is_subject=True)


def _gen_execute(subject_key, out_by_type):
    """execute 遍历面（EG-13-AC1 五行逐字）：任务行(根) + 任务声明→AC(根,正文) + 阅读依赖→§(邻居,正文)
    + 前置依赖→任务(前置,坐标+摘要) + 任务测试→红测试(前置,坐标)。映射/共现不入（非 brief 消费边）。"""
    cands = [_subject_cand(subject_key)]
    for e in out_by_type.get("任务声明", []):
        cands.append(_cand(e["dst"], TIER_ROOT, "content", _edge_reason(e, "出", 1), prov=e["prov"]))
    for e in out_by_type.get("阅读依赖", []):
        cands.append(_cand(e["dst"], TIER_NEIGHBOR, "content", _edge_reason(e, "出", 1), prov=e["prov"]))
    for e in out_by_type.get("前置依赖", []):
        cands.append(_cand(e["dst"], TIER_PREREQ, "pointer", _edge_reason(e, "出", 1),
                           prov=e["prov"], summary=True))
    for e in out_by_type.get("任务测试声明", []):
        cands.append(_cand(e["dst"], TIER_PREREQ, "pointer", _edge_reason(e, "出", 1), prov=e["prov"]))
    return cands


def _gen_impact(subject_key, in_by_type):
    """impact：全部反向引用 + 下游传导点（EG-23-AC2）。入边 {前置依赖/修订落账/映射} 反向＝下游传导点
    （取正文，前置档），其余入边＝一般反向引用（取坐标，邻居档）。答「改我波及谁」。"""
    cands = [_subject_cand(subject_key)]
    for etype, es in in_by_type.items():
        transmit = etype in _IMPACT_TRANSMIT
        tier = TIER_PREREQ if transmit else TIER_NEIGHBOR
        layer = "content" if transmit else "pointer"
        for e in es:                                    # 入边：对端＝边源（依赖我者）
            cands.append(_cand(e["src"], tier, layer, _edge_reason(e, "入", 1), prov=e["prov"]))
    return cands


def _gen_review(subject_key, subject, out_by_type, incident, entities):
    """review：execute 闭包 + 同 namespace 兄弟断言（携状态，superseded 显式可见）+ 结构邻居（全部相邻
    图邻居）+ unknown/歧义节点（经 性质门 落 omitted 显式报告）。答「评审这块要看的确定性材料」。"""
    cands = _gen_execute(subject_key, out_by_type)
    kind, ns, _ = subject_key
    for e in entities:                                  # 同 namespace 同 kind 兄弟断言（superseded 靠状态列显式）
        k = tuple(e["key"])
        if k != subject_key and e["key"][0] == kind and e["key"][1] == ns:
            cands.append(_cand(k, TIER_NEIGHBOR, "pointer", {"规则": "同namespace断言", "深度": 0}))
    for edge in incident:                               # 结构邻居：全部相邻图邻居（任意边类型/方向）
        s, d = tuple(edge["src"]), tuple(edge["dst"])
        if s == subject_key and d != subject_key:
            peer, direction = d, "出"
        elif d == subject_key and s != subject_key:
            peer, direction = s, "入"
        else:
            continue
        cands.append(_cand(peer, TIER_NEIGHBOR, "pointer",
                           {"规则": "结构邻居", "边": edge["type"], "方向": direction, "深度": 1}))
    return cands


# ---------------- 段/omitted/诊断构造 ----------------

def _segment(g, ent, cand, layer):
    """构造一个 bundle 段（EG-23-AC3 ①②③ + AC5 锚 + AC6 layer）。content 携逐字原文；pointer 仅锚
    （前置附一行摘要）。状态属性带出（review 的 superseded 显式可见）。无定义块→原文 None + note。"""
    p = ent.get("primary")
    seg = {"key": list(ent["key"]), "display": ent["display"], "性质": ent["性质"],
           "锚": _coord(p), "inclusion_reason": cand["reason"], "layer": layer}
    if ent.get("状态"):
        seg["状态"] = ent["状态"]
    if layer == "content":
        seg["原文"] = _block_text(g, p) if p else None
        if p is None:
            seg["note"] = "无定义块（未在语料找到定义形块）"
    else:                                               # pointer：仅坐标；前置依赖附一行摘要
        seg["原文"] = None
        if cand.get("summary"):
            body = _block_text(g, p).strip() if p else ""
            seg["摘要"] = _clip(body.splitlines()[0] if body else ent["display"])
    return seg


def _omit(key, ent, reason, cand):
    """omitted 条目（EG-23-AC3 ④；禁无声截断）：携对端 + 原因 + 指针（锚，供 agent 自取）+ inclusion_reason。"""
    o = {"key": list(key), "display": ent["display"] if ent else key[2],
         "性质": ent["性质"] if ent else "unknown", "原因": reason,
         "指针": _coord(ent.get("primary")) if ent else None}
    if cand.get("reason"):
        o["inclusion_reason"] = cand["reason"]
    return o


def _diag_nodef(ent, cand):
    """无定义块诊断（EG-23-AC3 ⑤；DG-42 同形溯源）：命中引用形却无定义块＝真 provenance 缺口。"""
    prov = cand.get("prov") or {}
    return {"诊断型": "无定义块", "源文件": prov.get("file"), "行": prov.get("line"),
            "原文": ent["display"], "规则": prov.get("method", "闭包"), "目标": list(ent["key"])}


# ---------------- bundle 组装（性质门 + 部分降级 + 确定性预算裁剪） ----------------

def _assemble(g, subject, cands, mode, budget, idx):
    """按（tier, 主键）稳定排序 + 主键去重（EG-23-AC3 ⑦），逐候选过 性质门 与预算档：
      · 任务来源非规范 → broken：仅出任务行段，其余候选全列 omitted「来源非规范」（EG-23-AC1 替全空闭包）。
      · 对端 unknown → omitted「未分类跳过」+ tainted（EG-23-AC1 部分降级：跳过并显式报告）。
      · 对端 记述 且 execute 模式 → omitted「记述来源(模式外)」（EG-13-AC3 记述 Evidence 不自动纳入）。
      · 否则 → 段（content 受预算裁剪，pointer 不占预算）。
    预算：仅内容层原文占预算，按 tier 序累减；单条不够则**整条转指针 + 列 omitted「预算截断」**（EG-23-AC4
    绝不切半条断言），标 truncated。返回 (segments, omitted, diagnostics, judgment, tainted_by, truncated)。"""
    subject_key = tuple(subject["key"])
    authoritative = subject["性质"] == "规范"

    subj_cand = next(c for c in cands if c["is_subject"])
    others = sorted((c for c in cands if not c["is_subject"]),
                    key=lambda c: (c["tier"], c["key"]))     # 稳定排序（EG-23-AC3 ⑦）
    ordered = [subj_cand] + others

    segments, omitted, diagnostics = [], [], []
    visited = set()
    budget_left, truncated, tainted_docs = budget, False, set()

    def _take_budget(seg):
        """内容层原文占预算：整条纳入或整条转指针（绝不切半条断言，EG-23-AC4）。"""
        nonlocal budget_left, truncated
        text = seg.get("原文")
        if not text:                                          # 无原文（指针/无定义块）不占预算
            return seg
        if len(text) <= budget_left:
            budget_left -= len(text)
            return seg
        omitted.append({"key": seg["key"], "display": seg["display"], "性质": seg["性质"],
                        "原因": "预算截断", "指针": seg["锚"], "inclusion_reason": seg["inclusion_reason"]})
        seg["原文"], seg["layer"], seg["预算转指针"] = None, "pointer", True
        truncated = True
        return seg

    for cand in ordered:
        key = cand["key"]
        if key in visited:                                    # 去重（EG-23-AC3 ⑦：同实体多路径命中取一）
            continue
        visited.add(key)
        ent = idx.get(key)

        if cand["is_subject"]:                                # 任务行段恒纳入（根断言，最先占预算）
            segments.append(_take_budget(_segment(g, subject, cand, "content")))
            continue

        if not authoritative:                                 # 来源非规范：broken，依赖全列 omitted 显式可见
            omitted.append(_omit(key, ent, f"来源非规范({subject['性质']})", cand))
            continue

        nature = ent["性质"] if ent else "unknown"
        if nature == "unknown":                               # 部分降级：未分类跳过并显式报告（EG-23-AC1）
            omitted.append(_omit(key, ent, "未分类跳过", cand))
            if ent and ent.get("primary"):
                tainted_docs.add(ent["primary"]["doc"])
            else:
                tainted_docs.add(key[1])                       # 无定义块的 unknown：记 namespace 兜底
                if ent:                                        # 无定义块＝真 provenance 缺口，诊断照发（AC3 ⑤）
                    diagnostics.append(_diag_nodef(ent, cand)) # （性质随 primary 后无定义块必 unknown，诊断随迁）
            continue
        if nature == "记述" and mode == "execute":             # 记述 Evidence 不自动纳入（EG-13-AC3），显式列出
            omitted.append(_omit(key, ent, "记述来源(模式外)", cand))
            continue

        segments.append(_take_budget(_segment(g, ent, cand, cand["layer"])))

    if not authoritative:
        judgment = "broken"
    elif tainted_docs:
        judgment = "tainted"
    else:
        judgment = "structurally_complete"
    return segments, omitted, diagnostics, judgment, sorted(tainted_docs), truncated


def _boundary(idx, incident, subject_key, surfaced):
    """边界指针（EG-13-AC2 延续）：未展开且未在 segments/omitted 出现的相邻图邻居坐标；去重、稳定排序。"""
    rels = defaultdict(set)
    for e in incident:
        s, d = tuple(e["src"]), tuple(e["dst"])
        if s == subject_key and d != subject_key:
            peer, direction = d, "出"
        elif d == subject_key and s != subject_key:
            peer, direction = s, "入"
        else:
            continue                                          # 自环：不作邻居
        if peer in surfaced:                                  # 已进 segments/omitted → 非「未展开」
            continue
        rels[peer].add((e["type"], direction))
    out = []
    for peer in sorted(rels):
        ent = idx.get(peer)
        out.append({"key": list(peer),
                    "display": ent["display"] if ent else peer[2],
                    "性质": ent["性质"] if ent else "unknown",
                    "锚": _coord(ent.get("primary")) if ent else None,
                    "关系": sorted(f"{t}({d})" for t, d in rels[peer])})
    return out


# ---------------- bundle 顶层 ----------------

def _build_bundle(g, subject, entities, edges, mode, budget, classification_complete, query):
    idx = {tuple(e["key"]): e for e in entities}
    subject_key = tuple(subject["key"])

    out_by_type, in_by_type, incident = defaultdict(list), defaultdict(list), []
    for e in edges:
        s, d = tuple(e["src"]), tuple(e["dst"])
        if s == subject_key:
            out_by_type[e["type"]].append(e)
        if d == subject_key:
            in_by_type[e["type"]].append(e)
        if s == subject_key or d == subject_key:
            incident.append(e)

    if mode == "impact":
        cands = _gen_impact(subject_key, in_by_type)
    elif mode == "review":
        cands = _gen_review(subject_key, subject, out_by_type, incident, entities)
    else:                                                     # execute（默认）
        cands = _gen_execute(subject_key, out_by_type)

    segments, omitted, diagnostics, judgment, tainted_by, truncated = _assemble(
        g, subject, cands, mode, budget, idx)

    surfaced = {tuple(s["key"]) for s in segments} | {tuple(o["key"]) for o in omitted}
    boundary = _boundary(idx, incident, subject_key, surfaced)

    top = {
        "schema_version": M.SCHEMA_VERSION,
        "mode": mode,
        "query": query,
        "resolved": list(subject["key"]),
        "性质": subject["性质"],
        "judgment_status": judgment,
        "classification_complete": classification_complete,
        "truncated": truncated,
        # 去重/稳定排序标记（EG-23-AC3 ⑦）：明示合同已应用（防实现者悄悄漏做）。
        "去重稳定排序": {"去重键": "主键三元组", "排序键": "(tier, 主键三元组)", "已应用": True},
        "segments": segments,
        "omitted": omitted,
        "diagnostics": diagnostics,
        "boundary_pointers": boundary,
    }
    if judgment == "tainted":
        top["tainted_by"] = tainted_by
    if judgment == "broken":
        top["broken_reason"] = (f"任务来源非规范（性质={subject['性质']}）：无规范来源边可遍历，闭包不作结构结论；"
                                f"依赖已列 omitted 显式可见（EG-23-AC1 部分降级，替代旧全空闭包）。")
    return top


# ---------------- 渲染 ----------------

_LABELS = {"任务声明": "任务声明→AC", "阅读依赖": "阅读依赖→§", "前置依赖": "前置依赖→任务",
           "任务测试声明": "任务测试→红测试", "(自身)": "任务行(根)"}


def _reason_str(r):
    if "边" in r:
        return f"{r['边']}·{r.get('方向', '')}(深{r['深度']})"
    return f"{r.get('规则', '?')}(深{r.get('深度', 0)})"


def _render_human(top):
    m = top["context_manifest"]
    print(f"== brief[{top['mode']}] {top['query']}  [{_fmt_key(top['resolved'])}]  性质={top['性质']} ==")
    print(f"judgment_status={top['judgment_status']}  classification_complete={top['classification_complete']}"
          f"  truncated={top['truncated']}  budget={m['budget']}  bundle_hash={m['output_hash']}")
    if "broken_reason" in top:
        print("⚠ " + top["broken_reason"])
    if "tainted_by" in top:
        print("⚠ tainted_by（闭包触达/跳过 unknown 文档）：" + "、".join(top["tainted_by"]))

    print(f"\n[segments] ×{len(top['segments'])}（content=原文逐字 / pointer=坐标+摘要）")
    for s in top["segments"]:
        c = s["锚"]
        coord = f"{c['doc']}:{c['line']}..{c['line_end']}" if c else "无定义块"
        st = f"  状态={s['状态']}" if s.get("状态") else ""
        print(f"  [{s['layer']}] {_fmt_key(s['key'])}  {coord}  ←{_reason_str(s['inclusion_reason'])}{st}")
        if s.get("摘要"):
            print(f"    摘要: {s['摘要']}")
        elif s.get("原文"):
            for ln in s["原文"].splitlines():
                print("    " + ln)
        elif s.get("note"):
            print(f"    {s['note']}")
        elif s.get("预算转指针"):
            print("    （预算截断：原文见 omitted 指针，坐标自取）")

    if top["omitted"]:
        print(f"\n[omitted] ×{len(top['omitted'])}（禁无声截断——每条带原因+指针）")
        for o in top["omitted"]:
            c = o["指针"]
            coord = f"{c['doc']}:{c['line']}..{c['line_end']}" if c else "（无定义块）"
            print(f"  {_fmt_key(o['key'])}  原因={o['原因']}  指针={coord}")

    if top["diagnostics"]:
        print(f"\n[diagnostics] ×{len(top['diagnostics'])}")
        for d in top["diagnostics"]:
            print(f"  {d['诊断型']}: {d['原文']}  源={d['源文件']}:{d['行']}  规则={d['规则']}")

    nbrs = top["boundary_pointers"]
    print(f"\n[boundary_pointers] 未展开相邻图邻居 ×{len(nbrs)}（起跑线非围墙，需要时经坐标自取，EG-13-AC2）")
    for nb in nbrs:
        c = nb["锚"]
        coord = f"{c['doc']}:{c['line']}..{c['line_end']}" if c else "（无定义块）"
        print(f"  {_fmt_key(nb['key'])}  {coord}  关系={'、'.join(nb['关系'])}")


# ---------------- 命令入口 ----------------

def cmd_brief(g, conv, query, as_json, mode="execute", budget=None):
    # docstar dispatch 透传 mode（execute|impact|review，DG-45）与 budget（--budget，解释权在本模块）。
    query = (query or "").strip()
    if mode not in MODES:
        print(f"未知 brief 模式：{mode}（须 ∈ {MODES}，DG-45）", file=sys.stderr)
        return 2
    eff_budget = _parse_budget(budget)

    data = entity_extract.build(g, conv)
    entities = data["entities"]

    status, res = _resolve_task(entities, query)
    if status == "none":
        sugg = _suggest_tasks(entities, query)
        msg = f"无任务实体：{query}"
        if sugg:
            msg += "；相近任务：" + "、".join(_fmt_key(tuple(x["key"])) for x in sugg)
        print(msg, file=sys.stderr)
        return 1
    if status == "multi":
        print(f"「{query}」多命中 {len(res)} 个任务，请用三元组形（任务:namespace:canonical_id）限定：",
              file=sys.stderr)
        for e in res:
            print("  " + _fmt_key(tuple(e["key"])), file=sys.stderr)
        return 1
    if status == "nontask":
        print(f"brief 仅接受任务实体；「{query}」解析为 {res['key'][0]}:{res['key'][2]}"
              f"（非任务实体用 trace 查）", file=sys.stderr)
        return 1

    subject = res
    top = _build_bundle(g, subject, entities, data["edges"], mode, eff_budget,
                        data["classification_complete"], query)
    # context_manifest（DG-43；mode/budget 入 manifest，接 EG-22-AC1）：body=top（不含 manifest 自身）→ output_hash。
    top = {"context_manifest": M.context_manifest(
        "worktree", conv, f"brief:{mode}", budget=eff_budget, body=top,
        include_archived=getattr(g, "include_archived", False)), **top}

    if as_json:
        print(M.emit(top))
        return 0
    if i18n.language() == "en":
        print(i18n.render_public(top))
        return 0
    _render_human(top)
    return 0
