#!/usr/bin/env python3
"""entity_check — entity-layer structural checks and per-check truth states.

权威=同目录 实体图谱需求.md（EG-15 全 AC / EG-11-AC2）+ 实体图谱设计.md（DG-23/29/34/35）；
schema 单源=entity_model（CHECK_REGISTRY/ENTITY_CHECK_KEYS/orphan_consumers）；冲突以需求为准。

对外恰一接口（设计 §6，docstar.cmd_check 调）：`sections(g, conv) -> dict`。
  键=八 check 键（ENTITY_CHECK_KEYS）+ 两自检键（classification_complete / 实体_schema_孤儿consumer）；
  值=**判定对象**（EG-15-AC8 / 设计 §3）：`{result, judgment_status, findings, tainted_by, blocked_by}`。
判定纪律（DG-23 判定参与统一）：边无 judgment 字段，判定域=按 consumers 成员过滤 + 按源实体性质过滤
  （corpus.in_judgment_domain：规范/unknown 进域、unknown 保守纳入、记述不进）。build() 是唯一数据源，
  extract 已产的诊断（unresolved/ambiguous/修订行未解析/未分类文档/孤儿consumer）本模块**消费不重算**。

真值表（EG-15-AC8，逐检查算，污染按检查传播非全局开关；DG-44 结构态命名，算法不变仅状态词改名）：
  消费的诊断输入未归零(blocked)→broken+blocked_by（CHK-3 唯一：修订行未解析≠0）；
  否则结论依赖 unknown 文档→tainted+tainted_by（该检查 findings/负向证明域含 unknown 来源）；
  否则 structurally_complete。result=pass/fail 由 findings 空否定；broken 时 result=None(「—」)。
  **政策未声明（从未武装）=dormant 第四态**（DG-63/EG-15-AC8 扩行；_dormant 产，result=None、不 gate、
  不 taint 传播——诚实态词使机读端从数据本身区分「未武装」与「通过」，非旧谎报 structurally_complete）。
  **零缺陷也可 tainted**（挂检查级非 item 级）。判定对象为 dict 子类：`gates()` 谓词使 DocStar --gate
  正确实现 AC8 退出码列（structurally_complete-clean 与 dormant→假=退0；fail/tainted/broken→真=退非零，不冒充绿；
  经 docstar `_gate_hit` 消费——**不再覆写 `__bool__`**，谎报空会撞 json indent 编码器吞键，DG-60），
  __getitem__ 让 DocStar 文本态 `v[:cap]` 取 findings 片（txt 适配，不涉 json 序列化路径）。

输出定序确定（DG-9 golden 字节权威）：findings 逐检查稳定排序、判定对象键序固定、sections 键序固定。
引擎零模型零 prompt（G7）。
"""

import corpus
import entity_extract
import entity_model as M
from collections import defaultdict


# ================================================================
# 判定对象（EG-15-AC8 / 设计 §3）：dict 子类，兼容 DocStar 既有 list 化 gate/txt
# ================================================================

class _Verdict(dict):
    """判定对象。普通 dict 真值（非空恒真）——**不覆写 `__bool__`**：dict 子类谎报空会撞
    `json.dumps(indent=1)` 的纯 Python 缩进编码器 `if not dct: yield '{}'`（Python ≤3.12），
    把 falsy 判定对象整体吞成 `{}` 丢全键+休眠「说明」反假绿信号（DG-60，3.13 编码器已不复现）。
    门禁「命中」语义移显式谓词 `gates()`（EG-15-AC8 退出码真值表，经 docstar `_gate_hit` 于 --gate 委托消费）。
    __getitem__：整数/切片→findings（DocStar 文本态 `v[:cap]` 用）；字符串键→常规 dict 取值
    （不涉 json 序列化路径，保留）。"""

    def __getitem__(self, k):
        if isinstance(k, (slice, int)):
            return self.get("findings", [])[k]
        return dict.__getitem__(self, k)

    def gates(self):
        """--gate 命中语义：真 ⟺ fail ∨ tainted ∨ broken（EG-15-AC8 退出码真值表）；
        structurally_complete 干净通过与 dormant（政策未武装，DG-63 第四态）→假→退 0，不冒充绿、
        休眠不误触。原 `__bool__` 落点（DG-60 移此显式谓词）。"""
        return (self.get("judgment_status") not in ("structurally_complete", "dormant")
                or self.get("result") == "fail")


def _verdict(findings, blocked_by, tainted_by):
    """按 EG-15-AC8 真值表组装（broken > tainted > structurally_complete）。键序固定=设计 §3。
    DG-44 结构态命名：indeterminate→broken、authoritative→structurally_complete（去语义验收暗示），
    真值表算法（DG-35）不变、仅状态词改名。result=pass/fail 由 findings 空否定（结构层，非语义验收）。"""
    findings = list(findings)
    blocked_by = list(blocked_by)
    tainted_by = sorted(set(tainted_by))
    if blocked_by:                              # 消费的诊断输入未归零 → 结构断裂不可判
        status, result = "broken", None
    elif tainted_by:                            # 结论依赖 unknown 来源 → 受污（零缺陷也标）
        status, result = "tainted", ("pass" if not findings else "fail")
    else:
        status, result = "structurally_complete", ("pass" if not findings else "fail")
    return _Verdict(result=result, judgment_status=status,
                    findings=findings, tainted_by=tainted_by, blocked_by=blocked_by)


def _tainted(dep_docs, unknown_set):
    """检查依赖域 ∩ unknown 文档 = tainted_by（逐检查算，DG-35）。"""
    return sorted(d for d in set(dep_docs) if d in unknown_set)


def _dormant(note):
    """跨类型政策休眠（DG-47/EG-20-AC2；DG-50 域声明键同语义；DG-63 第四态诚实化）：政策未声明 →
    报「无声明」而非假绿。judgment_status="dormant"（EG-15-AC8 真值表第四行——从未武装的检查自称
    结构完备是谎报，机读端无法从数据本身区分「未武装」与「通过」[NBL 实测踩坑：result:null 与 pass
    的区别只能靠库外知识]，故状态词诚实化为 dormant）；result=None（不冒充 pass）、findings/tainted_by/
    blocked_by 保持空、附 说明 字段（反假绿信号）。设计意图不变：dormant 不 gate（gates()=False，休眠
    不当 --gate 命中）、不 taint 传播——改的只是状态词，从 structurally_complete 诚实化为 dormant。"""
    v = _Verdict(result=None, judgment_status="dormant",
                 findings=[], tainted_by=[], blocked_by=[])
    v["说明"] = note
    return v


def _src_in_domain(edge, ent_by_key):
    """DG-23 源实体性质过滤：边源实体 in_judgment_domain？源缺失→保守 unknown（进域）。"""
    e = ent_by_key.get(tuple(edge["src"]))
    return corpus.in_judgment_domain(e["性质"] if e else "unknown")


# ================================================================
# 七检查（EG-15-AC1..AC7）
# ================================================================

def _term_broken(entities, unresolved, unknown_set):
    """专名定义断锚（EG-15-AC1 / DG-29 定义端门禁）：专名 attrs.定义锚 解析不到节条目/裁决 → 报。
    消费 extract 的 unresolved_reference 中「来源=专名名 ∧ 期望=该专名定义锚」项（非重算）。"""
    term_anchor, dep_docs = set(), set()
    for e in entities:
        anchor = e.get("attrs", {}).get("定义锚")
        if e["key"][0] == "专名" and anchor:
            term_anchor.add((e["display"], anchor))
            doc = (e.get("primary") or {}).get("doc")
            if doc:
                dep_docs.add(doc)               # 域=全部带定义锚专名（负向证明域）
    findings = [u for u in unresolved if (u.get("来源"), u.get("期望")) in term_anchor]
    findings.sort(key=lambda x: (x.get("file", ""), x.get("line", 0), x.get("来源", "")))
    return _verdict(findings, [], _tainted(dep_docs, unknown_set))


def _coverage_gap(entities, edges, ent_by_key, unknown_set, conv):
    """CHK-2 覆盖缺口（EG-15-AC2；DG-47 从写死降为消费 conv.required_edges）：政策=覆盖规则集
    （required_edges 中 direction='in' 的规则——主体须被指向的必需入边）。每条规则声明 src_kinds
    （就地绑 kind，防跨写法假绿 EG-20-AC3）+ edge（必需边类型）。完整覆盖=主体适用的每条规则边都在，
    缺任一即报（缺=按规则声明序列出未满足的 edge）。域=有 primary 且进判定域的、kind∈规则 src_kinds
    并集 的实体。无覆盖规则→休眠报「无规则声明」（非假绿，DG-47）。
    等价保绿：fixture 声明 覆盖-任务声明/覆盖-验证声明 两 in 规则（src_kinds=需求AC/契约AC）→ findings
    与旧写死「需求AC∪契约AC 须有 任务声明∧验证声明」逐字节等价。"""
    rules = [r for r in conv.required_edges if r["direction"] == "in"]
    if not rules:
        return _dormant("无 required_edges 覆盖规则声明（direction=in），覆盖政策休眠（DG-47）")
    subject_kinds = set().union(*(r["src_kinds"] for r in rules))
    dom, dep_docs = {}, set()
    for e in entities:
        if e["key"][0] in subject_kinds and e.get("primary") and corpus.in_judgment_domain(e["性质"]):
            dom[tuple(e["key"])] = {"key": e["key"], "display": e["display"], "have": set()}
            dep_docs.add(e["primary"]["doc"])
    for e in edges:
        for r in rules:                          # 主体=dst（被指向），edge 类型来自规则
            if e["type"] != r["edge"] or not _src_in_domain(e, ent_by_key):
                continue
            d = dom.get(tuple(e["dst"]))
            if d and e["dst"][0] in r["src_kinds"]:
                d["have"].add(r["edge"])
    findings = []
    for k in sorted(dom):
        d = dom[k]
        missing = [r["edge"] for r in rules
                   if d["key"][0] in r["src_kinds"] and r["edge"] not in d["have"]]
        if missing:
            findings.append({"key": d["key"], "display": d["display"], "缺": missing})
    return _verdict(findings, [], _tainted(dep_docs, unknown_set))


def _mapping_gap(edges, ent_by_key, unknown_set, conv):
    """CHK-2 映射缺口（EG-15-AC2 映射维度；DG-47 消费 conv.required_edges）：政策=映射规则集
    （required_edges 中 direction='out' 的规则——主体须指向已定义靶的必需出边）。对每条规则的 edge，
    主体(src)∈src_kinds、靶(dst)∈dst_kinds（缺→不限）的边，其靶无定义块（primary 缺）= 未落到已定义
    条款 → 报（缺=f「靶{靶kind}无定义块」，靶 kind 动态取自边 dst，对 契约AC 得旧文案逐字节等价）。
    无映射规则→休眠。规则就地绑 kind：一条为「需求AC」写的闸门不会静默漏别的写法（EG-20-AC3）。"""
    rules = [r for r in conv.required_edges if r["direction"] == "out"]
    if not rules:
        return _dormant("无 required_edges 映射规则声明（direction=out），映射政策休眠（DG-47）")
    findings, dep_docs = [], set()
    for e in edges:
        for r in rules:
            if e["type"] != r["edge"] or e["src"][0] not in r["src_kinds"]:
                continue
            if r["dst_kinds"] and e["dst"][0] not in r["dst_kinds"]:
                continue
            if not _src_in_domain(e, ent_by_key):
                continue
            dep_docs.add(e["prov"]["file"])
            dst_ent = ent_by_key.get(tuple(e["dst"]))
            if dst_ent is None or dst_ent.get("primary") is None:
                findings.append({"src": e["src"], "dst": e["dst"],
                                 "缺": f"靶{e['dst'][0]}无定义块", "prov": e["prov"]})
            break                                # 一边匹配一规则即可，避免多规则重复报
    findings.sort(key=lambda x: (tuple(x["src"]), tuple(x["dst"])))
    return _verdict(findings, [], _tainted(dep_docs, unknown_set))


def _uncovered_kinds(entities, conv):
    """开放 kind 规则覆盖告警（EG-20-AC5/清单17；反假绿配套 DG-47）：required_edges 存在时，报告
    语料中出现、但未被任何规则 src_kinds/dst_kinds 覆盖的 kind——开放词汇下 kind as-written 开放、
    确定性检查精确匹配 kind，未被点名的 kind 静默无检=假绿。报告级（不阻断，供 agent 补规则或忽略）。
    无 required_edges→休眠（无政策网则「网外」无意义）。"""
    if not conv.required_edges:
        return _dormant("无 required_edges 规则声明，未覆盖 kind 告警休眠（DG-47/EG-20-AC5）")
    covered = set()
    for r in conv.required_edges:
        covered |= set(r["src_kinds"])
        if r["dst_kinds"]:
            covered |= set(r["dst_kinds"])
    present = {e["key"][0] for e in entities} - set(conv.uncovered_kind_exclusions)
    findings = [{"kind": k} for k in sorted(present - covered)]
    return _verdict(findings, [], [])


def _transduction(edges, ent_by_key, unresolved_rev, unknown_set, conv):
    """CHK-3 传导断裂（EG-15-AC3，fail-closed；DG-50 从写死降为消费 conv.revision_target_kinds）：
    修订声明（落到域内靶）无对应修订落账 → 断裂。域=修订声明/落账的有效靶 kind（项目声明；
    fixture 声明 需求AC/契约AC/审计AC 与旧写死等价保绿）。无域声明→休眠报「无声明」（非假绿，
    沿 DG-47；政策不存在则无可判对象，休眠先于 blocked 判定）。
    条目ID 通道=∃ 修订落账 同域靶（F-02/N-03 语义，修复原「只匹配 §→74% 不可见」）；
    落点行锚剔除（EG-2-AC3）：同一声明行含域内靶时其节条目靶=落点行锚，非独立传导主体，剔出域。
    § 通道（祖先匹配）在本语料被条目ID 通道涵盖（落账行同时回引裁定簿 § 与 AC，见报告）。
    未解析输入 fail-closed：修订行未解析≠0 → 整检查 blocked/broken，不静默绿（EG-15-AC8）。"""
    if not conv.revision_target_kinds:
        return _dormant("无 revision_target_kinds 声明，修订传导政策休眠（DG-50，沿 DG-47）")
    targets = set(conv.revision_target_kinds)
    recorded_ac = set()
    for e in edges:
        if e["type"] == "修订落账" and e["dst"][0] in targets and _src_in_domain(e, ent_by_key):
            recorded_ac.add(tuple(e["dst"]))
    row_has_ac = set()                          # (file,line) 含域内靶的修订声明行
    for e in edges:
        if e["type"] == "修订声明" and e["dst"][0] in targets:
            row_has_ac.add((e["prov"]["file"], e["prov"]["line"]))
    findings, dep_docs = [], set()
    for e in edges:
        if e["type"] != "修订声明" or "CHK-3传导断裂" not in e["consumers"]:
            continue
        if not _src_in_domain(e, ent_by_key):
            continue
        if e["dst"][0] == "节条目" and (e["prov"]["file"], e["prov"]["line"]) in row_has_ac:
            continue                            # 落点行锚，非独立传导主体
        if e["dst"][0] not in targets:
            continue
        dep_docs.add(e["prov"]["file"])
        if tuple(e["dst"]) not in recorded_ac:  # 双通道均无匹配 → 断裂
            findings.append({"src": e["src"], "dst": e["dst"],
                             "attrs": e["attrs"], "prov": e["prov"]})
    findings.sort(key=lambda x: (tuple(x["src"]), tuple(x["dst"])))
    return _verdict(findings, list(unresolved_rev), _tainted(dep_docs, unknown_set))


def _cycle(edges, ent_by_key, unknown_set):
    """CHK-环检测（EG-15-AC4）：前置依赖边成环 → 报（Tarjan SCC，回边=非平凡 SCC 或自环）。"""
    adj, self_loops, dep_docs = defaultdict(list), set(), set()
    for e in edges:
        if e["type"] != "前置依赖" or "CHK-环检测" not in e["consumers"]:
            continue
        if not _src_in_domain(e, ent_by_key):
            continue
        s, d = tuple(e["src"]), tuple(e["dst"])
        adj[s].append(d)
        dep_docs.add(e["prov"]["file"])
        if s == d:
            self_loops.add(s)
    findings = []
    for scc in _sccs(adj):
        if len(scc) > 1 or (len(scc) == 1 and scc[0] in self_loops):
            findings.append({"环": sorted(n[2] for n in scc), "节点数": len(scc)})
    findings.sort(key=lambda x: x["环"])
    return _verdict(findings, [], _tainted(dep_docs, unknown_set))


def _sccs(adj):
    """Tarjan 强连通分量（迭代，确定性：节点/邻居按 sorted）。返回 [ [node,...], ... ]。"""
    index, lowlink, on_stack, stack, idx = {}, {}, set(), [], [0]
    out, nodes = [], sorted(set(adj) | {d for ds in adj.values() for d in ds})
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]                      # (node, 邻居游标)
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = lowlink[v] = idx[0]
                idx[0] += 1
                stack.append(v)
                on_stack.add(v)
            neigh = sorted(adj.get(v, ()))
            if pi < len(neigh):
                work[-1] = (v, pi + 1)
                w = neigh[pi]
                if w not in index:
                    work.append((w, 0))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])
            else:
                if lowlink[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    out.append(comp)
                work.pop()
                if work:
                    p = work[-1][0]
                    lowlink[p] = min(lowlink[p], lowlink[v])
    return out


def _passthrough(report_items, unknown_set):
    """unresolved_reference / ambiguous_reference（EG-15-AC5/AC6，诊断）：消费 extract 同名 reports
    （不重算）。分级按来源性质，检查级 judgment_status：findings 源含 unknown 文档 → tainted。"""
    dep_docs = {it.get("file") for it in report_items if it.get("file")}
    return _verdict(list(report_items), [], _tainted(dep_docs, unknown_set))


def _cooccur(edges, ent_by_key, unknown_set, conv):
    """共现完备性（EG-15-AC7，提示；DG-50 从写死降为消费 conv.cooccur_mapping_kinds）：域内 kind
    定义块共现索引却无映射边 → 提示（fixture 声明 需求AC/契约AC 与旧写死等价保绿）。
    过滤域外共现（task→AC / 参数）；映射任一方向存在即视为已映。无域声明→休眠（沿 DG-47）。"""
    if not conv.cooccur_mapping_kinds:
        return _dormant("无 cooccur_mapping_kinds 声明，共现完备政策休眠（DG-50，沿 DG-47）")
    dom = set(conv.cooccur_mapping_kinds)
    mapped = set()
    for e in edges:
        if e["type"] == "映射":
            mapped.add(frozenset((tuple(e["src"]), tuple(e["dst"]))))
    seen, findings, dep_docs = set(), [], set()
    for e in edges:
        if e["type"] != "共现索引" or "共现完备性" not in e["consumers"]:
            continue
        s, d = tuple(e["src"]), tuple(e["dst"])
        if s[0] not in dom or d[0] not in dom:  # 只留域内↔域内（剔 task→AC / 参数）
            continue
        if not _src_in_domain(e, ent_by_key):
            continue
        dep_docs.add(e["prov"]["file"])
        pair = frozenset((s, d))
        if pair in mapped or pair in seen:
            continue
        seen.add(pair)
        findings.append({"共现": sorted((s[2], d[2])), "src": list(s), "dst": list(d),
                         "prov": e["prov"]})
    findings.sort(key=lambda x: x["共现"])
    return _verdict(findings, [], _tainted(dep_docs, unknown_set))


# ================================================================
# 自检（EG-15-AC9 注册表无孤儿 / AC10 测量装置自验收：分类完备性）
# ================================================================

def _orphan_selfcheck():
    """EG-15-AC9 / DG-34：edge.consumers 每名字须在 CHECK_REGISTRY，否则报孤儿（工具对自己 schema
    跑 CHK）。复用 entity_model.orphan_consumers()（模块加载时已硬校验，此处纳入 check 输出）。"""
    findings = [{"孤儿consumer": name} for name in M.orphan_consumers()]
    return _verdict(findings, [], [])


def _classification(unknown_documents):
    """EG-15-AC10 / EG-11-AC2：check 输出携分类完备性。findings=unknown 文档清单；空=complete=pass。
    incomplete→result=fail（`gates()` 真→gate 退非零，不把「全 unknown 上跑的门禁」冒充干净绿）。
    注：dump 顶层 classification_complete 为 bool；check 侧作判定对象（DocStar 文本态 txt 对每键调
    len()/切片，裸 bool 会崩→此处判定对象既 txt 安全又 gate 可判，见交接报告波8门禁须知）。"""
    return _verdict(list(unknown_documents), [], [])


# ================================================================
# 组装（docstar.cmd_check 调一次；键序固定=golden 字节权威）
# ================================================================

def sections(g, conv):
    """→ dict：八 check 键（判定对象）+ classification_complete + 实体_schema_孤儿consumer（判定对象）。
    build() 唯一数据源；诊断消费不重算。冻结签名（docstar.cmd_check：R.update(sections(g, conv))）。"""
    data = entity_extract.build(g, conv)
    entities, edges, reports = data["entities"], data["edges"], data["reports"]
    ent_by_key = {tuple(e["key"]): e for e in entities}
    unknown_set = set(data["unknown_documents"])

    out = {}
    out["schema_version"] = M.SCHEMA_VERSION   # golden 版本鉴别（与 dump/harvest/classify 一致）
    out["专名定义断锚"] = _term_broken(entities, reports["unresolved_reference"], unknown_set)
    out["CHK-2覆盖缺口"] = _coverage_gap(entities, edges, ent_by_key, unknown_set, conv)
    out["CHK-2映射缺口"] = _mapping_gap(edges, ent_by_key, unknown_set, conv)
    out["CHK-3传导断裂"] = _transduction(edges, ent_by_key,
                                         reports["实体_修订行未解析"], unknown_set, conv)
    out["CHK-环检测"] = _cycle(edges, ent_by_key, unknown_set)
    out["unresolved_reference"] = _passthrough(reports["unresolved_reference"], unknown_set)
    out["ambiguous_reference"] = _passthrough(reports["ambiguous_reference"], unknown_set)
    out["共现完备性"] = _cooccur(edges, ent_by_key, unknown_set, conv)
    # 诊断四分型第四型（DG-42）：缺必需边——保留为 required-edge 违反的统一诊断位。DG-47 落地后
    # 跨类型政策违反经 CHK-2覆盖缺口/CHK-2映射缺口 两既有键就地承载（等价保绿），本统一位维持空占位
    # （避免同一违反双路重复上报=冗余；a_diagnostics 锁定其空态）。
    out["缺必需边"] = _verdict([], [], [])
    # EG-20-AC5：开放 kind 规则覆盖告警（required_edges 存在时报告未被规则覆盖的语料 kind，反假绿配套）
    out["未覆盖kind"] = _uncovered_kinds(entities, conv)
    # 自检键（EG-15-AC9/AC10）
    out["classification_complete"] = _classification(data["unknown_documents"])
    out["实体_schema_孤儿consumer"] = _orphan_selfcheck()
    return out
