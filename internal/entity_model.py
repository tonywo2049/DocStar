#!/usr/bin/env python3
"""entity_model — 实体图谱 schema 常量与构造器。

对外 schema 由 references/command-contracts.md 与 golden/*.json 共同锁定；entity_* 模块只从这里
取结构常量，不得自立副本。

The current model removes the retired requirement-R kind, corpus tiers, allowlists, and registry layer.
→ (parse, consumers 集合)（DG-24）；删定义于(降属性)/约束/依据/散文/弱共现，加阅读依赖/前置依赖/
provenance，块内引用→共现索引；专名就地标注(DG-27)；CHECK_REGISTRY 单源+无孤儿自检(DG-34)。

项目专有常量（命名空间锚/定义形/harvest 过滤）已迁至 conventions 包（DG-33 单一事实源，
勿在此留副本）；本文件只留纯 schema，消费者经 conv 取项目约定。自检：python3 entity_model.py --selftest
"""

import json
import re
from collections import defaultdict

import json_contract

SCHEMA_VERSION = "eg-3"
HARVEST_ALGO = "h1"   # harvest 算法版本（输出携带）
TOOL_VERSION = "eg-3"  # 工具版本戳（DG-43 manifest；随 schema 契约版本，无独立 bump 负担）

# ================================================================
# 表 A·实体 kind 与主键（kind, namespace, canonical_id）
# ================================================================

# DEFAULT_KINDS = 内置默认词表（EG-19-AC3；DG-38 起 kind 集开放——本元组是「默认非上限」，
# 越出它的 kind 照原样处理、不报「非法 kind」、不静默丢弃、不做同义归并）。项目专有 kind
# （如老语料的契约AC/审计AC/评审项/治理期权）由该项目 conventions 声明获得，不在引擎内置。
DEFAULT_KINDS = ("需求AC", "参数", "任务", "测试", "专名", "文档", "节条目")
# 仅在 conventions 显式启用相应机制时出现的内置辅助 kind；不进入通用默认词表，确保零配置输出不变。
AUXILIARY_KINDS = ("执行日志", "最新事件")

# 通用 key 构造器（namespace 或为传入 doc_stem、或为泛化标签，无项目硬编码）。
# 带固定项目命名空间锚的 kind 经 conv.namespace_for(kind, cid) 取锚，再 make_entity((kind, ns, cid))；
# 项目专有 kind（评审项等）的键由消费者以 (kind, stem, cid) 直接构造，kind 值来自 conv（DG-38 开放）。
def key_param(name):    return ("参数", "全局", name)
def key_test(name):     return ("测试", "测试名", name)
def key_doc(rel):       return ("文档", "路径", rel)
def key_execution_log(rel): return ("执行日志", "路径", rel)
def key_latest_event(rel, anchor): return ("最新事件", rel, anchor)

def key_section(doc_stem, anchor):
    """namespace=所在文档 stem，canonical_id={doc}§<锚>。`### R{n}` 标题也走此 kind（r11 折入）。"""
    return ("节条目", doc_stem, f"{doc_stem}§{anchor}")

def key_term(doc_stem, name):
    """专名（r11/DG-27）：就地定义标注，namespace=定义所在文档 stem（非「登记册」）。"""
    return ("专名", doc_stem, name)

# 节条目锚文法：N | N.M | N[A-Z] | N[A-Z].M（覆盖 4A、4A.1）
ANCHOR_RE = re.compile(r"^\d+[A-Z]?(?:\.\d+)?$")
ENTITY_HEADING_RE = re.compile(
    r"^(#{1,6})\s*(?:§\s*)?(\d+[A-Z]?(?:\.\d+)*)(?:[.、:：\s]+(.*))?\s*$")

def normalize_anchor(raw):
    """子锚/深层编号归一至文法内（DG-11）。返回 (归一锚, 原始锚或 None)；无法归一→(None, raw)。"""
    m = re.match(r"^(\d+[A-Z]?(?:\.\d+)?)", raw.strip())
    if not m:
        return None, raw
    norm = m.group(1)
    return norm, (raw if raw != norm else None)

# 定义形/专名就地标注/底账·修改清单表头（DG-25/27）均已迁 conventions（conv.def_forms、
# conv.term_inplace/term_glossary、conv.is_ledger_doc/is_changelist_header）——项目约定单一事实源。

# ================================================================
# 表 B·边类型：(parse, consumers 集合)（DG-24；删 semantic_strength/check 布尔）
# consumers 由边类型 schema 单源静态生成，抽取器不填（EG-15 / 外源评审 3.2）。
# 每个 consumer 名字须在 CHECK_REGISTRY 注册（DG-34 无孤儿自检，模块加载时校验）。
# ================================================================

EDGE_TYPES = {
    # 边类型            (parse,  consumers)                         端点（源→靶）
    "修订落账":        ("高",   frozenset({"CHK-3传导断裂"})),        # 文档→AC/节条目
    "修订声明":        ("高",   frozenset({"CHK-3传导断裂"})),        # 节条目/项目专有条目→AC/节条目
    "任务声明":        ("高",   frozenset({"CHK-2覆盖缺口", "brief"})),  # 任务↔AC
    "验证声明":        ("确定", frozenset({"CHK-2覆盖缺口"})),        # 测试→AC（ac_ 前缀单 canonical）
    "任务测试声明":    ("高",   frozenset({"brief"})),               # 任务→测试（不推导 测试→AC）
    "映射":            ("确定", frozenset({"CHK-2映射缺口", "共现完备性"})),  # 需求AC↔下游AC（跨层映射，边/检查语义属块2）
    "阅读依赖":        ("高",   frozenset({"brief"})),               # 任务→节条目（新）
    "前置依赖":        ("高",   frozenset({"brief", "CHK-环检测"})),  # 任务→任务（新，多消费者）
    "执行日志":        ("高",   frozenset({"brief"})),               # 任务→按卡执行日志（可选）
    "最新事件":        ("高",   frozenset({"brief"})),               # 执行日志→最新事件锚（可选）
    "provenance":      ("中",   frozenset()),                        # 记述文档/节→AC/节/参数（新，不进门禁）
    "共现索引":        ("确定", frozenset({"共现完备性"})),          # 实体→实体（原块内引用正名）
}

# 端点封闭性（表B）：文档作端点仅限以下边类型（源侧）
_DOC_SOURCE_TYPES = {"修订落账", "provenance"}

def make_entity(key, display, 性质="unknown", primary=None, candidates=None, 状态=None, attrs=None):
    """r11：删 tier，加 性质（判定参与开关 EG-D10）+ 状态（标注 EG-12-AC3，可空）。
    专名的定义锚存 attrs['定义锚']（DG-27）。
    DG-38：kind 开放——不校验 key[0] ∈ 某固定集，越出 DEFAULT_KINDS 的 kind 照原样构造。"""
    e = {"key": list(key), "display": display, "性质": 性质,
         "primary": primary, "candidates": candidates or [], "attrs": attrs or {}}
    if 状态 is not None:
        e["状态"] = 状态
    return e

def make_edge(etype, src, dst, file, line, method, attrs=None):
    """端点封闭性（表B）：文档作源仅限 修订落账/provenance。违规=抽取器缺陷，抛错。
    r11：输出 consumers（集合→排序列表），删 strength/check。
    DG-38：端点 kind 开放——不校验 ∈ 固定 kind 集；文档端点的结构约束（作源限定）仍在。"""
    if etype not in EDGE_TYPES:
        raise ValueError(f"非法边类型：{etype}")
    for pos, end in (("src", src), ("dst", dst)):
        if end[0] == "文档" and not (pos == "src" and etype in _DOC_SOURCE_TYPES):
            raise ValueError(f"文档端点仅限 {_DOC_SOURCE_TYPES} 作源：{etype} {pos}")
    parse, consumers = EDGE_TYPES[etype]
    return {"type": etype, "src": list(src), "dst": list(dst),
            "prov": {"file": file, "line": line, "method": method},
            "parse": parse, "consumers": sorted(consumers), "attrs": attrs or {}}

# ================================================================
# CHECK_REGISTRY（DG-34）：consumer/check 单源注册表 + 无孤儿自检
# 每条：名称 → {kind(查询|门禁|提示|诊断), 输入边类型集, 判定状态, 严重度, AC}
# 「工具对自己 schema 跑 CHK」：EDGE_TYPES 每个 consumers 名字须在此注册。
# ================================================================

CHECK_REGISTRY = {
    "brief":            {"kind": "查询", "输入边": {"任务声明", "阅读依赖", "前置依赖", "任务测试声明",
                                                   "执行日志", "最新事件"},
                         "判定状态": None, "严重度": None, "AC": "EG-13"},
    "CHK-2覆盖缺口":    {"kind": "门禁", "输入边": {"任务声明", "验证声明"},
                         "判定状态": "report", "严重度": "报告级", "AC": "EG-15-AC2"},
    "CHK-2映射缺口":    {"kind": "门禁", "输入边": {"映射"},
                         "判定状态": "report", "严重度": "报告级", "AC": "EG-15-AC2"},
    "CHK-3传导断裂":    {"kind": "门禁", "输入边": {"修订落账", "修订声明"},
                         "判定状态": "report", "严重度": "报告级", "AC": "EG-15-AC3"},
    "CHK-环检测":       {"kind": "门禁", "输入边": {"前置依赖"},
                         "判定状态": "report", "严重度": "报告级", "AC": "EG-15-AC4"},
    "共现完备性":       {"kind": "提示", "输入边": {"共现索引", "映射"},
                         "判定状态": "hint", "严重度": "提示级", "AC": "EG-15-AC7"},
    # 以下非边 consumer 触发，但属检查注册（诊断/属性源）：
    "专名定义断锚":     {"kind": "门禁", "输入边": set(), "判定状态": "report",
                         "严重度": "报告级", "AC": "EG-15-AC1"},    # 消费 attrs.定义锚 + unresolved
    "unresolved_reference": {"kind": "诊断", "输入边": set(), "判定状态": "graded",
                             "严重度": "分级(规范门禁/unknown tainted/记述报告)", "AC": "EG-15-AC5"},
    "ambiguous_reference":  {"kind": "诊断", "输入边": set(), "判定状态": "graded",
                             "严重度": "分级", "AC": "EG-15-AC6"},
}

def orphan_consumers():
    """DG-34 无孤儿自检：EDGE_TYPES 里出现、CHECK_REGISTRY 里没注册的 consumer 名。空=健康。"""
    declared = set(CHECK_REGISTRY)
    used = set()
    for _parse, consumers in EDGE_TYPES.values():
        used |= consumers
    return sorted(used - declared)


def consumer_input_edge_mismatches():
    """consumer 注册的输入边须等于 EDGE_TYPES 反向投影；空列表=双向一致。"""
    actual = defaultdict(set)
    for edge_type, (_parse, consumers) in EDGE_TYPES.items():
        for consumer in consumers:
            actual[consumer].add(edge_type)
    mismatches = []
    for consumer in sorted(set(CHECK_REGISTRY) | set(actual)):
        declared = set(CHECK_REGISTRY.get(consumer, {}).get("输入边", set()))
        if declared != actual[consumer]:
            mismatches.append({"consumer": consumer,
                               "declared": sorted(declared),
                               "actual": sorted(actual[consumer])})
    return mismatches

# ---------------- 报告与 check 键（EG-15 七检查 + 抽取报告） ----------------

EXTRACT_REPORT_KEYS = ("实体_重定义", "实体_无定义块", "实体_修订行未解析",
                       "未分类文档", "实体_schema_孤儿consumer")     # build/自检产出
# EG-15 七类检查 = 八 check 键（CHK-2 覆盖声明缺口拆「覆盖」+「映射」两键，同一检查两维度）
ENTITY_CHECK_KEYS = ("专名定义断锚", "CHK-2覆盖缺口", "CHK-2映射缺口", "CHK-3传导断裂",
                     "CHK-环检测", "unresolved_reference", "ambiguous_reference", "共现完备性")

# DG-44 输出语义分层结构态命名（supersede DG-35 词汇；真值表算法 DG-35 不变，仅状态词改名+全输出面审计）：
#   authoritative→structurally_complete（去「权威/通过」的语义验收暗示）、tainted 保留、
#   indeterminate→broken（消费的诊断输入未归零=结构断裂不可判）；新增 resolved=findings 级（单引用已解析到目标）。
#   DG-63 增 dormant（政策未声明/从未武装；真值表第四态，诚实化替旧谎报 structurally_complete）。
#   全输出面不存在可读作「语义验收通过」的状态词（产品使命固定语；tests DG-44 审计断言锁定）。
JUDGMENT_STATUS = ("structurally_complete", "tainted", "broken", "dormant")  # 检查级判定态（EG-15-AC8；DG-63 增 dormant）
STRUCTURAL_STATES = ("resolved", "structurally_complete", "tainted", "broken", "dormant")  # 全结构态词汇（含 findings 级 resolved、DG-63 dormant）
_LEGACY_STATUS = {"authoritative": "structurally_complete",                 # 旧→新（外部对照；代码内一律用新词）
                  "indeterminate": "broken", "tainted": "tainted"}

# ---------------- 定序与序列化（DG-9：golden 字节权威） ----------------

def entity_sort_key(e):
    return tuple(e["key"])

def edge_sort_key(e):
    return (e["type"], tuple(e["src"]), tuple(e["dst"]), e["prov"]["file"], e["prov"]["line"])

def emit(obj):
    """全部机器输出统一经此序列化（禁时间戳/绝对路径入 obj）"""
    return json.dumps(json_contract.to_public(obj), ensure_ascii=False, indent=1)


# ---------------- 可复现 manifest（DG-43；各命令输出顶层单源构造器） ----------------

def _output_hash(body):
    import hashlib
    return hashlib.sha256(emit(body).encode("utf-8")).hexdigest()[:16]


def context_manifest(corpus_revision, conv, mode, budget=None, body=None, include_archived=False):
    """DG-43 可复现 manifest（挂各命令输出顶层）：绑定 语料 revision + 工具版本 + conventions hash。
    corpus_revision=语料 revision 戳：工作树扫描='worktree'（稳定符号，非逐 commit 变的 SHA——沿 verify
      golden 用符号先例，SHA 会破 golden 可复现）；快照输出由调用方传已解析 revision，
      `brief --baseline` 使用完整 commit SHA。
    conventions_hash=conv 规范化 sha256（防配置成不可见第二事实源，EG-22-AC1/清单15：配置变→hash 变→可解释差异）。
    body=输出体（**不含 manifest 自身**）→ output_hash：同输入（corpus_rev+tool+conv+body）必同 hash（可复现判据）。
    include_archived=True 时落 "include_archived": true（DG-59/EG-30 取证开关条件字段；默认 False 不写
      该键，默认路径 manifest 字节不动）。
    禁时间戳/绝对路径/机器名入 hash（DG-9/DG-43）；键序固定=golden 字节权威。"""
    m = {"corpus_revision": corpus_revision,
         "tool_version": TOOL_VERSION,
         "conventions_hash": conv.hash(),
         "conventions_source": conv.source_label(),
         "mode": mode,
         "budget": budget}
    if include_archived:
        m["include_archived"] = True
    if body is not None:
        m["output_hash"] = _output_hash(body)
    return m

# harvest 过滤素材（EG-5-AC1）已迁 conventions（conv.harvest_excluded / conv.harvest_len_range）。

# ================================================================
# 模块加载时的 schema 自洽自检（DG-34「工具对自己 schema 跑 CHK」）
# ================================================================

def _schema_selfcheck():
    """返回 (ok, 问题清单)。schema 不自洽即抽取器基座坏，宁可加载时抛。"""
    issues = []
    orphans = orphan_consumers()
    if orphans:
        issues.append(f"孤儿 consumer（EDGE_TYPES 用了但 CHECK_REGISTRY 未注册）：{orphans}")
    mismatches = consumer_input_edge_mismatches()
    if mismatches:
        issues.append(f"consumer 输入边与 EDGE_TYPES 反向投影不一致：{mismatches}")
    # 每个门禁/提示 check 键须在 CHECK_REGISTRY
    for k in ENTITY_CHECK_KEYS:
        if k not in CHECK_REGISTRY:
            issues.append(f"ENTITY_CHECK_KEYS「{k}」未在 CHECK_REGISTRY 注册")
    # 通用 key 构造器须都产出内置默认 kind（项目专有 kind 经 conv 声明、直接构造，不走这些构造器）
    for fn2, args in ((key_param, ("X",)), (key_test, ("X",)),
                      (key_section, ("d", "1")), (key_term, ("d", "X")), (key_doc, ("p",)),
                      (key_execution_log, ("p",)), (key_latest_event, ("p", "e"))):
        if fn2(*args)[0] not in DEFAULT_KINDS + AUXILIARY_KINDS:
            issues.append(f"构造器 {fn2.__name__} 产出非默认 kind")
    expected_tokens = {"执行日志": "execution-log", "最新事件": "latest-event"}
    for internal, public in expected_tokens.items():
        if json_contract.TOKENS.get(internal) != public:
            issues.append(f"辅助 token 缺 machine mapping：{internal}→{public}")
    return (not issues), issues


_ok, _issues = _schema_selfcheck()
if not _ok:
    raise RuntimeError("entity_model schema 自检失败：\n  " + "\n  ".join(_issues))


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        ok, issues = _schema_selfcheck()
        print(f"schema_version = {SCHEMA_VERSION}")
        print(f"DEFAULT_KINDS ({len(DEFAULT_KINDS)}): {DEFAULT_KINDS}")
        print(f"EDGE_TYPES ({len(EDGE_TYPES)}): {list(EDGE_TYPES)}")
        print(f"CHECK_REGISTRY ({len(CHECK_REGISTRY)}): {list(CHECK_REGISTRY)}")
        print(f"ENTITY_CHECK_KEYS ({len(ENTITY_CHECK_KEYS)}): {ENTITY_CHECK_KEYS}")
        print(f"孤儿 consumer: {orphan_consumers() or '无'}")
        print(f"consumer 输入边反向不一致: {consumer_input_edge_mismatches() or '无'}")
        # 冒烟：越出 DEFAULT_KINDS 的开放 kind 照常构造、不报「非法 kind」（DG-38）
        make_entity(("决策", "某设计", "D-7"), "D-7", 性质="规范")
        edge = make_edge("映射", ("需求AC", "requirements", "REQ-7"),
                         ("决策", "某设计", "D-7"), "x.md", 1, "映射表行")
        assert edge["consumers"] == ["CHK-2映射缺口", "共现完备性"], edge["consumers"]
        # 端点封闭的结构约束仍在（文档作 共现索引 端点非法）
        try:
            make_edge("共现索引", key_doc("p"), ("需求AC", "requirements", "REQ-1"), "x.md", 1, "m")
            print("FAIL 端点封闭未生效"); sys.exit(1)
        except ValueError:
            pass
        print(f"\nschema 自检：{'全 PASS' if ok else 'FAIL: ' + str(issues)}")
        sys.exit(0 if ok else 1)
    print(__doc__)
