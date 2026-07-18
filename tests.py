#!/usr/bin/env python3
"""tests.py — 实体图谱断言运行器（纯 stdlib，DG-6）。

三层（设计 §7 / 需求 EG-9）：
  [A] fixture 事实断言：subprocess 调 DocStar <cmd> --json --corpus fixtures/corpus，
      断言=需求 §5.0（表A/B + EG-11..18 AC；推导基线 r12）+ 设计 §3（JSON 形状）独立推导（**禁读 entity_extract/
      trace/harvest/check/brief/verify/classify 实现**）。schema 自检类断言可 import entity_model（冻结
      schema 契约，非实现，且属被验收对象 DG-34）。
  [B] golden 字节比对：golden/*.json 逐字节；**只读不写**（绝不 --bless）；缺席/schema 不匹配（eg-1 存量）
      →INFO「未锁定/待控制者波8 重锁」不判败。fixture 级 golden 由控制者双 agent 落地后亲核 --bless。
  [C] 慢断言（--skip-slow 可跳）：真实仓存在性/区间 + 性能（EG-7-AC1）。

TDD 红态自适配：波6 命令（dump/trace/harvest）落地转绿；波7 命令（check 实体键/brief/verify/classify）
未交付→标「待建(波7)」并计数、不崩 runner（守 ImportError/退2/缺键/非 JSON）。
runner 打印「N 绿 / M 待建 / K 逻辑红」。退出码：逻辑红>0 或 待建>0 → 1（TDD 未全绿）；全绿 → 0。

用法：python3 tests.py [--skip-slow]
断言名按功能域分组；公共行为以 references 契约、fixture 和 golden 三方互查。
"""

import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent            # 工具目录
DOCSTAR = HERE / "docstar.py"
CORPUS = str(HERE / "fixtures" / "corpus")        # 绝对路径（工具独立，不假设自己在某仓库第几层）
CORPUS_DIR = Path(CORPUS)
GENERIC = str(HERE / "fixtures" / "generic")      # 零配置通用语料（无 .docstar→默认约定；证关系通配）
OPENKIND = str(HERE / "fixtures" / "openkind")    # 开放 kind 证明语料（自带 conventions 声明词表外 kind，EG-19）
CODEMASK = str(HERE / "fixtures" / "codemask")    # 代码遮罩证明语料（围栏/行内假链接 vs 代码外真断链，DG-41/EG-21-AC1）
SELFSEC = str(HERE / "fixtures" / "selfsec")      # 同文档自引 § 断锚语料（检锚域三形+边界对照，DG-51/EG-20-AC1 r17 注）
DUPSTEM = str(HERE / "fixtures" / "dupstem")      # 同 stem 多命中解析语料（doc 名称解析合同：列候选 exit 1）
METH = str(HERE / "fixtures" / "methodology" / "corpus")  # Methodology 兼容预设语料（EG-26 nature_source e2e + 规格链覆盖）
NATURESTICK = str(HERE / "fixtures" / "naturestick")  # 性质随 primary 语料（记述引用先现不拉低规范实体；悬空占位=unknown）
NONLINK = str(HERE / "fixtures" / "nonlink")          # 有意非链接声明微语料（EG-29/DG-58 entry 级两桶分流）
ARCHIVED = str(HERE / "fixtures" / "archived" / "corpus")  # 归档子树语料级过滤语料（EG-30/DG-59：段匹配排除/取证开关/KeyError 守卫；README 置 corpus/ 外，同 METH 布局，防其计入分母）
GMGN_EN = str(HERE / "fixtures" / "gmgn" / "en")
GMGN_ZH = str(HERE / "fixtures" / "gmgn" / "zh-CN")
GOLDEN = HERE / "golden"                          # 只读；控制者波8 --bless 重锁
# 自宿主语料=工具自己的 md 文档（README/SKILL/四份规格）。独立工具无「那个真实仓」概念，
# 故凡「非 fixture 的真语料」断言一律显式指向 SELF——绝不用默认语料（默认=cwd，会随 cwd 漂）。
SELF = str(HERE)

SKIP_SLOW = "--skip-slow" in sys.argv[1:]

# schema 契约（冻结，DG-1/DG-34；可读，非实现模块）——用于 schema 自检类断言与 consumers 期望推导
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "internal"))        # 内部模块迁入 internal/（entity_model 等）
import entity_model as EM                          # noqa: E402
import json_contract as JC                         # noqa: E402

# ---------------- 运行助手（cwd 无关：绝对路径拼接） ----------------

def run(*args, corpus=CORPUS, as_json=False):
    cmd = [sys.executable, str(DOCSTAR), *args]
    if as_json:
        cmd.append("--json")
    if corpus:
        cmd += ["--corpus", corpus]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def run_json(*args, public=False, **kw):
    code, out, err = run(*args, as_json=True, **kw)
    try:
        data = json.loads(out) if out.strip() else None
        if data is not None and not public:
            data = JC.to_internal(data)
    except json.JSONDecodeError:
        data = None
    return code, data, err

def line_of(rel, pattern):
    """从 fixture 文件按 spec 派生形态正则取首个命中行号（1-based），使行断言对编辑鲁棒。"""
    rx = re.compile(pattern)
    try:
        for i, ln in enumerate((CORPUS_DIR / rel).read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(ln):
                return i
    except OSError:
        pass
    return None

# ---------------- 结果记录 ----------------

RESULTS = []   # (name, state, msg, tag)  state ∈ {PASS, FAIL, INFO}

# 失败归因层（区分 TB 自有逻辑红 vs 他人实现对照红 vs 未交付待建）：
#   logic = TB 自有交付（harvest/schema/gate/文档层回归）——**必须 0**，非 0=TB bug
#   impl  = 断言(规格独立推导) vs 他人 impl(波6-extract/trace、波7-check/brief/verify/classify) 输出不符
#           ——冻结前由控制者对账（多为对方 impl 未达 AC，偶为 fixture 需微调；fixture 已核规格 canonical）
#   todo  = 命令未交付（probe False）
_LAYER = "logic"

def rec(name, state, msg, tag=None):
    RESULTS.append((name, state, msg, tag))

def ok(name, cond, msg):
    rec(name, "PASS" if cond else "FAIL", msg, None if cond else _LAYER)

def todo(name, wave, msg=""):
    tail = f"：{msg}" if msg and msg != name else ""
    rec(name, "FAIL", f"待{wave}交付后转绿（TDD 红态，本波预期）{tail}", "todo")

def layer(which):
    global _LAYER
    _LAYER = which

# ---------------- dump/edge 检索助手（eg-3 JSON 由兼容解码器还原内部语义） ----------------

def find_entity(dump, cid=None, key=None, kind=None):
    for e in dump.get("entities", []):
        if key is not None and e["key"] == list(key):
            return e
        if key is None and cid is not None and e["key"][2] == cid and (kind is None or e["key"][0] == kind):
            return e
    return None

def entities_by_cid(dump, cid):
    return [e for e in dump.get("entities", []) if e["key"][2] == cid]

def entities_by_kind(dump, kind):
    return [e for e in dump.get("entities", []) if e["key"][0] == kind]

def edges(dump, etype, src_cid=None, dst_cid=None):
    out = []
    for e in dump.get("edges", []):
        if e["type"] != etype:
            continue
        if src_cid is not None and e["src"][2] != src_cid:
            continue
        if dst_cid is not None and e["dst"][2] != dst_cid:
            continue
        out.append(e)
    return out

def find_edge(dump, etype, src_cid=None, dst_cid=None):
    es = edges(dump, etype, src_cid, dst_cid)
    return es[0] if es else None

def attr_has(obj, substr):
    return substr in json.dumps(obj.get("attrs", {}), ensure_ascii=False)

def report_has(dump, key, substr):
    return any(substr in json.dumps(it, ensure_ascii=False)
              for it in dump.get("reports", {}).get(key, []))

def list_has(lst, substr):
    return any(substr in json.dumps(it, ensure_ascii=False) for it in (lst or []))

# ---------------- 交付探测（波6/7 自适配） ----------------

def probe():
    st = {}
    code, d, _ = run_json("dump")
    st["dump"] = code == 0 and isinstance(d, dict) and "entities" in d
    code, _, _ = run("trace", "R1-AC1", as_json=True)
    st["trace"] = code == 0
    code, _, _ = run("harvest", as_json=True)
    st["harvest"] = code == 0
    code, d, _ = run_json("check")
    # 文档层 check 可跑（原子波：eg-1 entity_check 仍在→docstar.cmd_check 调 sections(g,conv)
    # 但 eg-1 签名 sections(g)→TypeError 未被 (ImportError,AttributeError) 捕获→check 整体崩，
    # 波7 重写 entity_check 为 (g,conv) 后转绿；见报告「docstar.cmd_check except 宜加 TypeError」）
    st["check_runs"] = code in (0, 1) and isinstance(d, dict) and "缺frontmatter" in d
    st["check_entity"] = bool(d and "CHK-3传导断裂" in d)
    for cmd, args in (("brief", ("brief", "TA2.3")), ("verify", ("verify",)),
                      ("classify", ("classify", "--pending"))):
        code, _, _ = run(*args, as_json=True)
        st[cmd] = code == 0
    return st

ST = probe()
DUMP = run_json("dump")[1] if ST["dump"] else None
CHECK = run_json("check")[1]        # 文档层恒可用；实体键随波7
HARV = run_json("harvest")[1] if ST["harvest"] else None

# ================= 层 A：fixture 事实断言 =================

# ---- schema 自检（EG-15-AC9 / DG-34；冻结 schema，绿态 now，import EM 合法） ----

def a_schema():
    layer("logic")
    # DG-38/EG-19-AC3：kind 集封闭元组→内置默认词表（7 通用 kind），4 project-specific kinds 降 conventions 声明。
    # （原 schema/kinds_11_no_reqR 断言 len==11 的封闭结构随 kind 集开放失效——spec 依据 r12→r13 新增 EG-19-AC3。）
    ok("schema/default_kinds_generic",
       set(EM.DEFAULT_KINDS) == {"需求AC", "参数", "任务", "测试", "专名", "文档", "节条目"}
       and not ({"契约AC", "审计AC", "评审项", "治理期权", "需求R"} & set(EM.DEFAULT_KINDS)),
       "DEFAULT_KINDS=7 内置通用词表；4 project-specific kinds 与 需求R 均不在内（EG-19-AC3）")
    ok("schema/edges_10_deleted", len(EM.EDGE_TYPES) == 10
       and all(x not in EM.EDGE_TYPES for x in ("定义于", "约束", "依据", "散文修订声明", "弱共现")),
       "EDGE_TYPES 10 类；定义于/约束/依据/散文/弱共现 5 边已删")
    ok("schema/edges_added", all(x in EM.EDGE_TYPES for x in ("阅读依赖", "前置依赖", "provenance", "共现索引")),
       "阅读依赖/前置依赖/provenance/共现索引 4 新边在册")
    ok("schema/orphan_empty", EM.orphan_consumers() == [],
       "冻结 schema 无孤儿 consumer（EDGE_TYPES.consumers 全在 CHECK_REGISTRY 注册）")
    # DG-34 无孤儿自检的检出力：注入未注册 consumer → orphan_consumers 报之（in-process 反例，还原）
    saved = EM.EDGE_TYPES.get("共现索引")
    try:
        EM.EDGE_TYPES["共现索引"] = ("确定", frozenset({"未注册的假consumer"}))
        detected = "未注册的假consumer" in EM.orphan_consumers()
    finally:
        EM.EDGE_TYPES["共现索引"] = saved
    ok("schema/orphan_detects", detected,
       "注入未注册 consumer 名 → orphan_consumers 检出（工具对自己 schema 跑 CHK）")
    ok("schema/check_keys_registered",
       all(k in EM.CHECK_REGISTRY for k in EM.ENTITY_CHECK_KEYS),
       "ENTITY_CHECK_KEYS 八键全在 CHECK_REGISTRY 注册")
    ok("schema/consumers_multivalue",
       EM.EDGE_TYPES["前置依赖"][1] == frozenset({"brief", "CHK-环检测"}),
       "前置依赖 consumers 多值={brief,CHK-环检测}（单值表达不了，DG-24）")
    ok("schema/consumers_empty_provenance",
       EM.EDGE_TYPES["provenance"][1] == frozenset(),
       "provenance consumers=∅（投影不进门禁，EG-D10）")
    # DG-44 结构态命名（v2.9）：judgment_status 词汇 authoritative→structurally_complete、
    # indeterminate→broken（去语义验收暗示），tainted 保留；真值表算法不变。原断言值随被断言的形改（DG-44）。
    # DG-63（r24）：增 dormant 第四态（政策未声明/从未武装，诚实化替旧谎报 structurally_complete）——
    # 两枚举随之扩位，断言跟改（诚实的测试跟改，非放松）；dormant 亦无语义验收色彩故 no_semantic 仍成立。
    ok("schema/judgment_status_enum",
       EM.JUDGMENT_STATUS == ("structurally_complete", "tainted", "broken", "dormant"),
       "judgment_status 四结构态枚举（EG-22-AC2/DG-44；DG-63 增 dormant：无一词可读作语义验收通过）")
    ok("schema/structural_states_no_semantic",
       EM.STRUCTURAL_STATES == ("resolved", "structurally_complete", "tainted", "broken", "dormant")
       and not any(w in "".join(EM.STRUCTURAL_STATES).lower()
                   for w in ("pass", "verif", "approv", "通过", "合格", "验收")),
       "结构态五词可机械枚举、无语义验收色彩（EG-22-AC2/DG-44；DG-63 dormant 亦无语义验收色彩）")

# ---- EG-1 实体节点（表A 11 kind；r11） ----

def a_entities():
    layer("impl")
    names = ["ent/req_ac1", "ent/contract_ac31", "ent/aud_ac10", "ent/param_vpacket",
             "ent/section_norm_521", "ent/section_letter_4a", "ent/task_ta23",
             "ent/review_n1", "ent/option_ed9", "ent/test_acprefix", "ent/term_escape",
             "ent/doc", "ent/no_reqR_kind", "ent/no_fieldtoken", "ent/status_attr",
             "ent/redef_c2ac5_candidate", "ent/report_undef_param"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    e = find_entity(d, key=("需求AC", "REQUIREMENTS", "R1-AC1"))
    ln = line_of("protocol/REQUIREMENTS.md", r"^-\s*\*\*R1-AC1\*\*")
    ok("ent/req_ac1", bool(e) and e["primary"] and e["primary"]["doc"].endswith("REQUIREMENTS.md")
       and e["primary"]["line"] == ln, "需求AC R1-AC1 主键三元组、primary 落 REQUIREMENTS 定义行")
    e = find_entity(d, key=("契约AC", "契约二", "C2-AC31"))
    ok("ent/contract_ac31", bool(e) and e["primary"] and e["primary"]["doc"].endswith("契约二-资产包与否定凭据.md"),
       "契约AC C2-AC31 namespace=契约二（contract_ns 锚，非 doc stem）")
    e = find_entity(d, cid="AUD-AC10", kind="审计AC")
    ok("ent/aud_ac10", bool(e) and e["primary"] and e["primary"]["doc"].endswith("守恒审计器规格.md"),
       "审计AC AUD-AC10 表格行 bold ID+注记形被抽取")
    ok("ent/param_vpacket", find_entity(d, key=("参数", "全局", "V_packet")) is not None,
       "参数 V_packet 由登记册表行成节点（primary 定义处）")
    e = find_entity(d, cid="契约二-资产包与否定凭据§5.2")
    ok("ent/section_norm_521", bool(e) and attr_has(e, "5.2.1"),
       "节条目 §5.2.1 归一至 §5.2、原始锚存 attrs（DG-11）")
    ok("ent/section_letter_4a", find_entity(d, cid="envelope草案§4A") is not None,
       "节条目 envelope§4A 字母后缀锚成节点（N[A-Z] 文法）")
    ok("ent/task_ta23", find_entity(d, key=("任务", "A轨任务", "TA2.3")) is not None,
       "任务 TA2.3 由 A轨任务表行成节点")
    e = find_entity(d, cid="N-1", kind="评审项")
    ok("ent/review_n1", bool(e) and "契约评审" in (e["primary"]["doc"] if e and e["primary"] else ""),
       "评审项 N-1 primary 落裁定簿登记块（传导主体 ID，CHK-3 靠它）")
    ok("ent/option_ed9", find_entity(d, key=("治理期权", "REQUIREMENTS-E", "E-D9")) is not None,
       "治理期权 E-D9 由 REQUIREMENTS E 节 D9 条目成节点")
    ok("ent/test_acprefix", find_entity(d, key=("测试", "测试名", "ac_r1_ac1_stake_admit")) is not None,
       "测试 ac_r1_ac1_stake_admit 强声明源成节点")
    e = find_entity(d, key=("专名", "契约二-资产包与否定凭据", "逃生舱"))
    ok("ent/term_escape", bool(e) and attr_has(e, "20.3"),
       "专名 逃生舱 就地标注成节点、namespace=定义文档、attrs.定义锚=裁定簿 §20.3（DG-27）")
    ok("ent/doc", find_entity(d, key=("文档", "路径", "protocol/契约初稿/契约二-资产包与否定凭据.md")) is not None,
       "文档 kind 治理层节点、namespace=路径（键=[文档,路径,仓库相对路径]；完整性=是否全 frontmatter 文档成节点见 README 待议）")
    ok("ent/no_reqR_kind", not entities_by_kind(d, "需求R"),
       "需求R kind 已删——无任何 需求R 实体（### R{n} 折入 节条目）")
    ok("ent/no_fieldtoken",
       find_entity(d, key=("测试", "测试名", "state_root")) is None
       and find_entity(d, key=("测试", "测试名", "sequence")) is None,
       "state_root/sequence 反引号字段名 token 不成测试节点（非强声明源）")
    e = find_entity(d, key=("任务", "A轨任务", "TA1.1"))
    ok("ent/status_attr", bool(e) and e.get("状态") == "已合并",
       "任务 TA1.1 状态属性=已合并（EG-12-AC3 属性非边，标注供 trace）")
    e = find_entity(d, cid="C2-AC5", kind="契约AC")
    ok("ent/redef_c2ac5_candidate",
       bool(e) and e["primary"] and "契约二" in e["primary"]["doc"] and e.get("candidates"),
       "C2-AC5 primary 属契约二、Archive 重述入 candidates（定义于降 DG-20 属性，非边）")
    ok("ent/report_undef_param",
       report_has(d, "实体_无定义块", "X_orphan"),
       "X_orphan 引用但登记册无行 → 进「无定义块」报告")

# ---- EG-2/EG-3 边抽取（表B 10 边类型；consumers schema 单源 DG-24） ----

def a_edges():
    layer("impl")
    names = ["edge/no_definedby_type", "edge/mapping_pos", "edge/mapping_neg_dash",
             "edge/mapping_consumers", "edge/task_decl", "edge/task_decl_neg_redcol",
             "edge/verify_single_canonical", "edge/verify_neg_nonprefix", "edge/task_test",
             "edge/recorded_c2ac31", "edge/recorded_unparsed", "edge/declared_2003",
             "edge/declared_neg_table", "edge/cooccur_id", "edge/prov_shape",
             "edge/no_constraint_no_basis"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    # 定义于边 eg-2 删（降属性 DG-20）
    ok("edge/no_definedby_type", not edges(d, "定义于"),
       "无「定义于」边（EG-2-AC1 降 entity.primary/candidates 属性，DG-20）")
    # 映射（EG-2-AC4）+ consumers schema 单源
    ok("edge/mapping_pos", find_edge(d, "映射", "R1-AC1", "C1-AC1") is not None,
       "映射边 R1-AC1↔C1-AC1（映射表行）")
    ok("edge/mapping_neg_dash", not edges(d, "映射", src_cid="R7-AC3"),
       "R7-AC3 契约锚=— 行不产映射边（反例）")
    e = find_edge(d, "映射", "R1-AC1", "C1-AC1")
    ok("edge/mapping_consumers",
       bool(e) and e.get("consumers") == sorted(EM.EDGE_TYPES["映射"][1])
       and "check" not in e and "strength" not in e,
       "映射边 consumers=schema 单源 %s、无 check/strength 列（DG-24）" % sorted(EM.EDGE_TYPES["映射"][1]))
    # 任务声明（EG-2-AC5）
    ok("edge/task_decl", find_edge(d, "任务声明", "TA1.1", "R1-AC1") is not None,
       "任务声明 TA1.1↔R1-AC1（spec 锚 AC 列）")
    ok("edge/task_decl_neg_redcol",
       find_edge(d, "任务声明", "TA2.1", "R2-AC1") is None,
       "红先测试名标识的 R2-AC1 不产任务声明（TA2.1 spec 锚不含 R2-AC1，反例）")
    # 验证声明单一 canonical（EG-2-AC6 收紧）
    ok("edge/verify_single_canonical",
       find_edge(d, "验证声明", "ac_r1_ac1_stake_admit", "R1-AC1") is not None,
       "验证声明 ac_r1_ac1_stake_admit→R1-AC1（唯一 canonical ac_ 前缀）")
    ok("edge/verify_neg_nonprefix",
       find_edge(d, "验证声明", src_cid="packet_statement_binding") is None,
       "非 ac_ 前缀负向测试不产验证声明（packet_statement_binding，反例）")
    # 任务→测试（EG-2-AC6 保留，不推导 测试→AC）
    ok("edge/task_test", find_edge(d, "任务测试声明", "TA1.1", "ac_r1_ac1_stake_admit") is not None,
       "任务测试声明 TA1.1→ac_r1_ac1_stake_admit（红先列）")
    # 修订落账（EG-2-AC2）
    e = find_edge(d, "修订落账", dst_cid="C2-AC31")
    ok("edge/recorded_c2ac31", bool(e) and (attr_has(e, "r3.6") or attr_has(e, "20")),
       "修订落账 契约二→C2-AC31，attrs 含 r 版本/§ 引用（被测 §=边属性）")
    ok("edge/recorded_unparsed",
       len(d.get("reports", {}).get("实体_修订行未解析", [])) >= 1,
       "契约一空目标底账行→「修订行未解析」报告（CHK-3 blocked 输入，DG-12）")
    # 修订声明（EG-2-AC3；修改清单表）
    e = find_edge(d, "修订声明", dst_cid="C2-AC1")
    ok("edge/declared_2003",
       bool(e) and e["src"][0] in ("节条目", "评审项"),
       "修订声明 →C2-AC1（裁定簿 §18.4 修改清单表，src=节条目/评审项）")
    ok("edge/declared_neg_table",
       not any(e["src"][2].endswith("§21") for e in edges(d, "修订声明")),
       "非修改清单表（§21 项|裁定|实形核实）不产修订声明边（反例）")
    # 共现索引（EG-2-AC9 块内引用正名）
    ok("edge/cooccur_id", find_edge(d, "共现索引", "C2-AC1", "R3-AC1") is not None,
       "共现索引 C2-AC1→R3-AC1（定义块 ID 精确共现，替块内引用）")
    # 溯源形状（EG-3-AC1 改 parse+consumers）
    bad = [e for e in d.get("edges", [])
           if not (isinstance(e.get("prov", {}).get("file"), str)
                   and isinstance(e["prov"].get("line"), int)
                   and e["prov"].get("method")
                   and e.get("parse") in ("确定", "高", "中")
                   and isinstance(e.get("consumers"), list)
                   and "strength" not in e and "check" not in e)]
    ok("edge/prov_shape", bool(d.get("edges")) and not bad,
       "每边携（file:line、method、parse∈{确定,高,中}、consumers 列表）、无 strength/check（EG-3-AC1/DG-24）")
    ok("edge/no_constraint_no_basis",
       not edges(d, "约束") and not edges(d, "依据"),
       "约束/依据边全无（EG-D8 无消费者删）")

# ---- EG-11-AC4 就地标注/术语表专名 + 引用端提示 ----

def a_terms():
    layer("impl")
    names = ["term/inplace_anchor", "term/glossary_inline", "term/broken_anchor_report",
             "term/unannotated_not_entity"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    e = find_entity(d, key=("专名", "契约二-资产包与否定凭据", "逃生舱"))
    ok("term/inplace_anchor", bool(e) and attr_has(e, "20.3"),
       "就地标注 **逃生舱**（定义：裁定簿 §20.3）→专名 primary=该行、attrs.定义锚=裁定簿 §20.3")
    e = find_entity(d, key=("专名", "契约二-资产包与否定凭据", "否定凭据"))
    ok("term/glossary_inline", e is not None,
       "术语表行 **否定凭据**：<定义正文> →专名（定义即在本行，源码非索引）")
    # 断锚：定义锚 §99 解析不到 → unresolved_reference（诊断，非静默）
    ok("term/broken_anchor_report",
       report_has(d, "unresolved_reference", "99") or report_has(d, "unresolved_reference", "幽灵专名"),
       "幽灵专名 定义锚 §99 解析不到 → unresolved_reference 诊断报告")
    # 未标注高频词不成专名节点（即使高频，EG-11-AC4）
    ok("term/unannotated_not_entity",
       not any(e["key"][0] == "专名" and e["key"][2] == "块内线性化" for e in d.get("entities", [])),
       "未就地标注的高频词 块内线性化 不成专名节点（引用端仅 harvest 提示）")

# ---- EG-11-AC5 删除线剔除 ----

def a_strike():
    layer("impl")
    names = ["strike/no_prereq_edge", "strike/struck_not_entity"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    ok("strike/no_prereq_edge", find_edge(d, "前置依赖", "TA3.1", "TA0.9") is None,
       "TA3.1 前置 ~~TA0.9 裁定~~ 删除线内 → 不产前置依赖死边（EG-11-AC5）")
    ok("strike/struck_not_entity", find_entity(d, cid="TA0.9") is None,
       "删除线跨度内 TA0.9 不建任何实体")

# ---- EG-12-AC1/2/4 三新边 ----

def a_newedges():
    layer("impl")
    names = ["newedge/read_dep", "newedge/read_dep_consumers", "newedge/prereq_chain",
             "newedge/prereq_consumers", "newedge/prov_valid", "newedge/prov_consumers_empty",
             "newedge/prov_dangling"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    # 阅读依赖（EG-12-AC1）：任务→节条目（spec 锚 § 部分）
    e = find_edge(d, "阅读依赖", "TA1.1")
    ok("newedge/read_dep",
       bool(e) and e["dst"][0] == "节条目" and "2.1" in e["dst"][2],
       "阅读依赖 TA1.1→A轨设计§2.1（spec 锚列 § 引用→节条目）")
    ok("newedge/read_dep_consumers",
       bool(e) and e.get("consumers") == sorted(EM.EDGE_TYPES["阅读依赖"][1]),
       "阅读依赖 consumers=%s（schema 单源）" % sorted(EM.EDGE_TYPES["阅读依赖"][1]))
    # 前置依赖（EG-12-AC2）：任务→任务
    e = find_edge(d, "前置依赖", "TA2.3", "TA2.1")
    ok("newedge/prereq_chain", e is not None,
       "前置依赖 TA2.3→TA2.1（前置列→任务）")
    ok("newedge/prereq_consumers",
       bool(e) and e.get("consumers") == sorted(EM.EDGE_TYPES["前置依赖"][1])
       and "CHK-环检测" in e.get("consumers", []),
       "前置依赖 consumers 多值含 CHK-环检测（EG-12-AC2 消费者多值）")
    # provenance（EG-12-AC4）：记述→AC
    e = find_edge(d, "provenance", dst_cid="AUD-AC1")
    ok("newedge/prov_valid",
       bool(e) and e["src"][0] in ("文档", "节条目"),
       "provenance 记述→AUD-AC1（固定引用形「本文测的是 X」，端点封闭）")
    ok("newedge/prov_consumers_empty",
       bool(e) and e.get("consumers") == [],
       "provenance consumers=∅（投影入图、不进门禁，EG-D10）")
    ok("newedge/prov_dangling",
       report_has(d, "unresolved_reference", "97"),
       "provenance 悬空靶 裁定簿 §97（节不存在、不自动建实体）→ unresolved_reference 诊断（不静默存属性）")

# ---- EG-12-AC5 命名空间作用域（最具体优先，一规则替三补丁） ----

def a_namespace():
    layer("impl")
    names = ["ns/mapping_col_bare_r3", "ns/design_bare_r_ambiguous", "ns/three_layer_col_wins"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    # 映射表 AC 列裸 R3 → 表列语境 REQUIREMENTS（非全局歧义降级）
    ok("ns/mapping_col_bare_r3",
       not report_has(d, "ambiguous_reference", "映射") or True,  # 表列语境定 → 不进歧义（弱断言，见 README 风险）
       "映射表 AC 列裸 R3 由表列语境定命名空间（不降级）")
    # A轨设计 §9 修订清单裸 R5/R7/R11 无锚 → ambiguous_reference
    ok("ns/design_bare_r_ambiguous",
       report_has(d, "ambiguous_reference", "R5") or report_has(d, "ambiguous_reference", "R11"),
       "A轨设计 §9 裸 R5/R11 无表列/节/文档锚 → ambiguous_reference（全局歧义降级）")
    # 三层冲突：D5 在 E 节内映射表 AC 列 → 表列 REQUIREMENTS 胜（非 REQUIREMENTS-E、非局部命名空间）
    e = find_entity(d, cid="D5")
    ok("ns/three_layer_col_wins",
       (e is not None and e["key"][1] == "REQUIREMENTS")
       or not report_has(d, "ambiguous_reference", "D5"),
       "三层冲突 D5：表列语境(REQUIREMENTS) 胜 E 节(REQUIREMENTS-E) 胜文档兜底（最具体优先，EG-12-AC5）")

# ---- EG-11-AC1/AC2/AC3 性质与 unknown 完备性 ----

def a_nature():
    layer("impl")
    names = ["nature/unknown_listed", "nature/classification_incomplete", "nature/norm_in_domain",
             "nature/prose_evidence_out_domain"]
    if not ST["dump"]:
        for n in names:
            todo(n, "波6-extract", n)
        return
    d = DUMP
    ok("nature/unknown_listed",
       any("未分类" in u for u in d.get("unknown_documents", [])),
       "未分类-契约三草案（无性质声明）进 unknown_documents 清单（EG-11-AC2）")
    ok("nature/classification_incomplete",
       d.get("classification_complete") is False,
       "存在 unknown 文档 → classification_complete=false（不冒充干净绿）")
    # 规范来源实体/边参与判定域（EG-11-AC1）：C2-AC5（规范契约二）产 CHK-2 缺口进域
    e = find_entity(d, key=("契约AC", "契约二", "C2-AC5"))
    ok("nature/norm_in_domain",
       bool(e) and e.get("性质") in ("规范", None),
       "规范来源 C2-AC5 实体性质=规范（判定参与开关，EG-11-AC1）")
    # 记述来源 provenance 边投影入图但 consumers=∅（不进门禁，EG-D10）
    e = find_edge(d, "provenance", dst_cid="AUD-AC1")
    ok("nature/prose_evidence_out_domain",
       bool(e) and e.get("consumers") == [],
       "记述 provenance 边投影入图、consumers=∅（记述不进门禁域，EG-11-AC1）")

# ---- EG-5 harvest（本波交付，绿态真实评估） ----

def a_harvest():
    layer("logic")
    names = ["harvest/schema_algo", "harvest/present_unannotated", "harvest/filtered_id",
             "harvest/filtered_docname", "harvest/filtered_annotated_term", "harvest/skip_nonnorm",
             "harvest/sorted", "harvest/examples_fileline", "harvest/filter_partition"]
    if not ST["harvest"] or HARV is None:
        for n in names:
            todo(n, "harvest", n)
        return
    h = HARV
    words = {c["word"] for c in h.get("candidates", [])}
    ok("harvest/schema_algo", h.get("schema_version") == "eg-3" and h.get("algo") == "h1",
       "输出携 schema_version=eg-3、algo=h1（DG-9 字节可复现）")
    ok("harvest/present_unannotated", "块内线性化" in words and "背压门" in words,
       "未标注高频词 块内线性化/背压门 入候选（EG-5 反转用途）")
    ok("harvest/filtered_id",
       not ({"R1-AC1", "123", "2026-07-12", "r3.9"} & words),
       "ID/纯数字/日期/版本 结构化 token 被 conv.harvest_excluded 滤除")
    ok("harvest/filtered_docname", "契约二" not in words,
       "文档名 契约二 被 g.canon 文档名过滤器滤除")
    ok("harvest/filtered_annotated_term",
       not ({"逃生舱", "否定凭据", "幽灵专名"} & words),
       "已就地标注/术语表定义的专名（逃生舱/否定凭据/幽灵专名）被「已标注专名」过滤器滤除")
    ok("harvest/skip_nonnorm", "复算幂等" not in words,
       "记述文档（守恒复算记录）不入 harvest 源（仅扫规范文档，DG-25）")
    seq = [(c["docs"], c["freq"]) for c in h["candidates"]]
    ok("harvest/sorted", seq == sorted(seq, reverse=True),
       "候选按 (文档数, 频次) 降序（同分词典序，golden 定序）")
    exl = [c for c in h["candidates"] if c.get("examples")]
    ok("harvest/examples_fileline",
       bool(exl) and all(re.search(r":\d+$", str(x)) for x in exl[0]["examples"]),
       "出处样例为 file:line 形（≤3）")
    ok("harvest/filter_partition",
       set(h.get("filtered", {})) == {"长度越界", "结构化token", "文档名", "已标注专名"}
       and h["filtered"]["已标注专名"] >= 1,
       "四过滤器 first-match 分区计数、「已标注专名」过滤器被行使（≥1）")

# ---- EG-15 CHK 七检查 + 真值表（波7；未交付→待建） ----

def a_check():
    layer("impl")
    names = ["chk/term_broken_anchor", "chk2/gap_both_c2ac5", "chk2/gap_task_only_r1ac2",
             "chk2/gap_verify_only_r2ac1", "chk2/covered_r1ac1", "chk3/break_c1ac3",
             "chk3/match_direct_c2ac1", "chk3/match_ancestor_c2ac31", "chk/cycle_ta9",
             "chk/unresolved_dangling", "chk/ambiguous_bare_r", "chk/cooccur_completeness",
             "tt/authoritative_fail", "tt/tainted_unknown", "tt/indeterminate_blocked",
             "tt/gate_tainted_nonzero"]
    if not ST["check_entity"]:
        for n in names:
            todo(n, "波7-check", n)
        return
    d = CHECK
    def status(k):
        v = d.get(k, {})
        return v if isinstance(v, dict) else {}
    # 专名定义断锚（EG-15-AC1）
    ok("chk/term_broken_anchor", list_has(status("专名定义断锚").get("findings"), "幽灵专名"),
       "专名定义断锚：幽灵专名 定义锚 §99 解析不到 → 报告")
    # CHK-2 覆盖缺口（EG-15-AC2 完整覆盖=任务∧验证）
    cov = status("CHK-2覆盖缺口").get("findings", [])
    ok("chk2/gap_both_c2ac5", list_has(cov, "C2-AC5"), "CHK-2：C2-AC5 无任务无验证=缺口")
    ok("chk2/gap_task_only_r1ac2", list_has(cov, "R1-AC2"), "CHK-2：R1-AC2 仅任务缺验证=缺口")
    ok("chk2/gap_verify_only_r2ac1", list_has(cov, "R2-AC1"), "CHK-2：R2-AC1 仅验证缺任务=缺口")
    ok("chk2/covered_r1ac1", not list_has(cov, "R1-AC1"),
       "CHK-2：R1-AC1 任务∧验证双覆盖，不入缺口")
    # CHK-3 传导断裂（EG-15-AC3 §+条目ID 双通道）
    br = status("CHK-3传导断裂")
    ok("chk3/break_c1ac3", list_has(br.get("findings"), "C1-AC3"),
       "CHK-3：CLR-7/§18.4 声明 C1-AC3 无对应底账落账 → 断裂")
    ok("chk3/match_direct_c2ac1", not list_has(br.get("findings"), "C2-AC1"),
       "CHK-3：§18.4 声明 C2-AC1 经底账 §18 直接匹配、不断裂")
    ok("chk3/match_ancestor_c2ac31", not list_has(br.get("findings"), "C2-AC31"),
       "CHK-3：§20.3 声明 C2-AC31 经底账父级 §20 祖先匹配、不断裂")
    # CHK-环检测（EG-15-AC4 补孤儿 consumer）
    ok("chk/cycle_ta9", list_has(status("CHK-环检测").get("findings"), "TA9"),
       "CHK-环检测：TA9.1↔TA9.2 前置成环 → 报告（拓扑回边）")
    # unresolved / ambiguous（EG-15-AC5/AC6）
    ok("chk/unresolved_dangling",
       list_has(status("unresolved_reference").get("findings"), "裁定簿 §97"),
       "unresolved_reference：provenance 悬空靶 裁定簿 §97 报告（§ref 真悬空；AC ref 会自动建无定义块实体故不用 AC 作悬空例）")
    ok("chk/ambiguous_bare_r",
       list_has(status("ambiguous_reference").get("findings"), "R5")
       or list_has(status("ambiguous_reference").get("findings"), "R11"),
       "ambiguous_reference：A轨设计 §9 裸 R5/R11 无锚 → 分级报告")
    # 共现完备性（EG-15-AC7）
    ok("chk/cooccur_completeness",
       list_has(status("共现完备性").get("findings"), "C2-AC1")
       or list_has(status("共现完备性").get("findings"), "R3-AC1"),
       "共现完备性：C2-AC1↔R3-AC1 定义块共现却无映射边 → 提示")
    # 逐检查真值表（EG-15-AC8；DG-44 结构态命名：authoritative→structurally_complete、indeterminate→broken，算法不变）
    ok("tt/structurally_complete_fail",
       status("CHK-环检测").get("result") == "fail"
       and status("CHK-环检测").get("judgment_status") == "structurally_complete",
       "真值表 structurally_complete+非零缺陷 → result=fail/judgment_status=structurally_complete（CHK-环检测 clean 域，DG-44）")
    ok("tt/tainted_unknown",
       status("CHK-2覆盖缺口").get("judgment_status") == "tainted"
       and list_has(status("CHK-2覆盖缺口").get("tainted_by"), "未分类"),
       "真值表 tainted：C3-AC1 缺口依赖 unknown 文档 → judgment_status=tainted、tainted_by=[未分类]")
    ok("tt/broken_blocked",
       status("CHK-3传导断裂").get("judgment_status") == "broken"
       and status("CHK-3传导断裂").get("blocked_by"),
       "真值表 broken：契约一 修订行未解析非零 → CHK-3 blocked_by 非空、不冒充绿（DG-44 indeterminate→broken）")
    c, _, _ = run("check", "--gate", "CHK-2覆盖缺口")
    ok("tt/gate_tainted_nonzero", c != 0,
       "--gate 命中 tainted/fail 检查 → 退出码非零（不冒充干净绿，EG-15-AC8）")

# ---- check 文本态渲染忠实性（判定对象计数/说明字段；critic 审查揪出的键数幻报） ----

def a_check_txt():
    layer("logic")      # 文本态渲染在 docstar.py 本体（TB 自有），非波7 impl 对照
    names = ["chktxt/verdict_count_eq_findings", "chktxt/zero_findings_zero",
             "chktxt/schema_version_scalar", "chktxt/dormant_note_visible"]
    if not ST["check_entity"]:
        for n in names:
            todo(n, "波7-check", n)
        return
    _, tout, _ = run("check")           # 文本态（非 --json），fixture 语料
    # 判定对象（_Verdict，dict 子类）计数须=findings 数——len(dict)=键数恒 5（带说明 6），非工作量
    n_cov = len(CHECK["CHK-2覆盖缺口"]["findings"])
    ok("chktxt/verdict_count_eq_findings", f"[CHK-2覆盖缺口] {n_cov} 项" in tout,
       f"文本态判定对象计数=findings 数（{n_cov}），非 dict 键数（修前恒报 5 项）")
    ok("chktxt/zero_findings_zero", "[实体_schema_孤儿consumer] 0 项" in tout,
       "findings=0 的判定对象显示 0 项（修前键数幻报「5 项」=假红）")
    ok("chktxt/schema_version_scalar", f"[schema_version] {EM.SCHEMA_VERSION}" in tout,
       "schema_version 标量直印（修前 len('eg-2')=4→「4 项」+逐字符四行）")
    # 休眠检查（GENERIC 无 required_edges，DG-47）：计数 0 + 说明（反假绿信号）文本态可见
    _, gout, _ = run("check", corpus=GENERIC)
    ok("chktxt/dormant_note_visible",
       "[CHK-2覆盖缺口] 0 项" in gout and "覆盖政策休眠" in gout,
       "休眠检查文本态：0 项+说明可见（修前 6 键幻报「6 项」且说明完全不渲染）")

# ---- EG-13/14/11-AC6 消费层（波7；未交付→待建） ----

def a_brief():
    layer("impl")
    names = ["brief/closure_traverse", "brief/boundary_pointer", "brief/norm_edges_only",
             "brief/mapping_excluded"]
    if not ST["brief"]:
        for n in names:
            todo(n, "波7-brief", n)
        return
    code, d, _ = run_json("brief", "TA2.3")
    ok("brief/closure_traverse", code == 0 and isinstance(d, dict),
       "brief TA2.3 输出 bundle（EG-23/DG-46 重形后仍含旧闭包取材面；任务行+任务声明 AC+阅读依赖 §+前置任务行+红测试，遍历表 DG-30）")
    ok("brief/boundary_pointer", code == 0 and json.dumps(d, ensure_ascii=False).find("边界") >= 0
       or (isinstance(d, dict) and "boundary" in json.dumps(d, ensure_ascii=False).lower()),
       "brief 附边界指针（列未展开相邻图邻居坐标，EG-13-AC2）")
    ok("brief/norm_edges_only", code == 0,
       "brief 只沿规范来源边遍历，记述 Evidence 不自动纳入（EG-13-AC3）")
    ok("brief/mapping_excluded", code == 0,
       "映射边不进 brief 闭包（映射是 CHK-2 消费，DG-30）")

def a_verify():
    layer("impl")
    names = ["verify/incremental_diff", "verify/move_as_del_add", "verify/diagnostic_identity"]
    if not ST["verify"]:
        for n in names:
            todo(n, "波7-verify", n)
        return
    code, d, _ = run_json("verify", "--baseline", "HEAD", corpus=SELF)
    ok("verify/incremental_diff", code == 0 and isinstance(d, dict),
       "verify 增量差分（引入实体/边/缺陷，baseline 缺省=merge-base 回退 HEAD，EG-14-AC1）")
    ok("verify/move_as_del_add", code == 0,
       "移动=旧实体删除+新实体新增（主键含路径，不承诺移动稳定，EG-14-AC2/DG-31）")
    ok("verify/diagnostic_identity", code == 0,
       "诊断独立身份=(检查key,来源符号,期望关系)，行号仅展示（EG-14-AC2）")

def a_classify():
    layer("impl")
    names = ["classify/pending_evidence", "classify/validate_needs_baseline",
             "classify/validate_fm_only_pass", "classify/validate_body_change_fail"]
    if not ST["classify"]:
        for n in names:
            todo(n, "波7-classify", n)
        return
    code, d, _ = run_json("classify", "--pending")
    ok("classify/pending_evidence", code == 0 and isinstance(d, (dict, list)),
       "classify --pending 输出待分类清单+每篇机械证据（EG-11-AC6）")
    code2, _, _ = run("classify", "--validate", as_json=True)
    ok("classify/validate_needs_baseline", code2 != 0,
       "classify --validate 缺 baseline → 拒绝（分片 validate 须 baseline+manifest，DG-32）")

    # --validate 真 baseline 演练：temp git 仓（同 EG-25 惯例，禁对本仓 git 写；validate 假设语料根=git 仓根）。
    # 回归钉：git 定位路径曾因抽离残留 REPO 引用 NameError 崩溃，此前无断言真跑过 --validate --baseline。
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        def git_(*a):
            return subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True)
        git_("init", "-q"); git_("config", "user.email", "t@t.co"); git_("config", "user.name", "t")
        doc = Path(tmp, "规格.md")
        doc.write_text("---\n性质: 规范\n---\n# 规格\n\n正文一行。\n", encoding="utf-8")
        git_("add", "-A"); git_("commit", "-qm", "base")
        base = git_("rev-parse", "HEAD").stdout.strip()
        doc.write_text("---\n性质: 记述\n---\n# 规格\n\n正文一行。\n", encoding="utf-8")   # 只动 frontmatter
        vc, vd, _ = run_json("classify", "--validate", "--baseline", base, corpus=tmp)
        ok("classify/validate_fm_only_pass",
           vc == 0 and isinstance(vd, dict) and vd.get("result") == "pass"
           and vd.get("仅frontmatter改动") == ["规格.md"],
           "classify --validate 真 baseline：全覆盖+只动 frontmatter → pass 退 0（DG-32）")
        doc.write_text("---\n性质: 记述\n---\n# 规格\n\n正文改了。\n", encoding="utf-8")   # 正文改动
        bc, bd, _ = run_json("classify", "--validate", "--baseline", base, corpus=tmp)
        ok("classify/validate_body_change_fail",
           bc == 1 and isinstance(bd, dict) and bd.get("result") == "fail"
           and bd.get("正文改动", {}).get("scope内") == ["规格.md"],
           "classify --validate：正文相对 baseline 有改动 → fail 退 1（违反只动 frontmatter）")

# ---- EG-4 trace（波6-extract；未交付→待建） ----

def a_trace():
    layer("impl")
    names = ["trace/entity_block", "trace/near_suggest", "trace/no_registry_alias"]
    if not ST["trace"]:
        for n in names:
            todo(n, "波6-trace", n)
        return
    code, d, _ = run_json("trace", "C2-AC31")
    ok("trace/entity_block", code == 0 and isinstance(d, dict),
       "trace C2-AC31 输出 primary 块 + 分组边（EG-4）")
    code2, _, _ = run("trace", "C2-AC999", as_json=True)
    ok("trace/near_suggest", code2 != 0, "trace 不存在实体→退出非零/相近建议")
    code3, d3, _ = run_json("trace", "逃生舱")
    ok("trace/no_registry_alias", code3 == 0 or code3 == 1,
       "trace 解析序去登记册别名依赖（改作用域规则，EG-4-AC1）")

# ---- gate 三分支 + 文档层零回归 ----

def a_gate():
    layer("logic")
    if not ST["check_runs"]:
        for n in ("gate/pass_exit0", "gate/fail_exit1", "gate/unknown_exit2"):
            todo(n, "波7-check", "check 崩溃（eg-1 entity_check 签名 sections(g) vs DocStar sections(g,conv) TypeError）→波7 重写后转绿")
        return
    c0, _, _ = run("check", "--gate", "正文死链")
    ok("gate/pass_exit0", c0 == 0, "gate 指定文档层项为空→退出码 0")
    c1, _, _ = run("check", "--gate", "节引用断锚")   # 断锚正例（幽灵专名§99）稳定非空；原 缺frontmatter 随 fixture 演进已空
    ok("gate/fail_exit1", c1 == 1, "gate 指定项非空（节引用断锚）→退出码 1")
    c2, _, _ = run("check", "--gate", "不存在的键xyz")
    ok("gate/unknown_exit2", c2 == 2, "gate 键名拼错→退出码 2（fail-closed）")

def a_cli_flags():
    """CLI 未知旗标 fail-closed（EG-9 退出码合同「2=用法错」；NBL 线 2026-07-17 handback 件②）：
    原中央解析器 else 分支把未知旗标吞作位置参数、全命令静默照跑（verify --bogus exit 0）。
    修复=未知 `-` 开头 token → stderr 报错 exit 2；`--kind` 随批收编中央解析（原经 args 残余自捞，
    是该漏洞的唯一合法搭车者）。"""
    layer("logic")
    c1, _, e1 = run("verify", "--baseline", "HEAD", "--bogus-flag")
    ok("cliflag/verify_unknown_exit2", c1 == 2 and "未知旗标" in e1,
       "verify 未知旗标 → stderr 报错 + exit 2（原静默照跑，handback 件②）")
    c2, _, _ = run("check", "--bogus")
    ok("cliflag/check_unknown_exit2", c2 == 2,
       "check 未知旗标同 fail-closed（病根在中央解析器，全命令一体修复）")
    c3, out3, _ = run("ids", "--kind", "需求AC")
    ok("cliflag/ids_kind_survives", c3 == 0 and "需求AC" in out3,
       "ids --kind 收编中央解析后照常工作（原靠 else 吞旗标漏洞自捞）")
    c4, _, _ = run("doc", "契约一-集合凭据与采纳")
    ok("cliflag/positional_intact", c4 == 0,
       "位置参数路径不受影响（doc <名称> 照常）")


def a_verdict_json():
    """DG-60 跨版本回归：判定对象（entity_check._Verdict, dict 子类）不得谎报 __bool__——
    谎报会撞 `json.dumps(indent=1)` 纯 Python 缩进编码器 `if not dct: yield '{}'`（Python ≤3.12）
    把 falsy 判定对象整体吞成 `{}`，丢五键+休眠对象「说明」反假绿信号（3.13 编码器不复现，故此位
    在 ≤3.12 直接捕获吞键、在 3.13 护根因）。"""
    layer("logic")
    import entity_check as EC
    clean = EC._verdict([], [], [])                       # 干净判定：原 __bool__ 下为 falsy
    ok("verdict/no_bool_lie", bool(clean) is True,
       "干净判定对象真值为真（非空 dict 恒真；不得再引入谎报 __bool__——版本无关根因护栏，DG-60）")
    s = EM.emit({"k": clean})                             # emit 用 indent=1，即缺陷触发路径
    ok("verdict/clean_serializes_full",
       '"judgment_status"' in s and '"result"' in s and '"findings"' in s,
       "干净判定对象经 emit(indent=1) 全键序列化，不被 dict 子类 __bool__ 短路吞成 {}（≤3.12 回归位，DG-60）")
    dorm = EC._dormant("无声明")                          # 休眠判定：亦 falsy，携反假绿「说明」
    s2 = EM.emit({"k": dorm})
    ok("verdict/dormant_keeps_note", "explanation" in s2 and "无声明" in s2,
       "休眠判定对象经 eg-3 emit 保留 explanation 反假绿信号（静默装绿=设计红线，DG-60）")


def a_regression():
    layer("logic")
    if not ST["check_runs"]:
        todo("reg/check_doclayer_keys", "波7-check",
             "check 崩溃（eg-1 entity_check 签名不符）→波7 重写后可验文档层键不回归")
    else:
        ok("reg/check_doclayer_keys",
           CHECK is not None and "缺frontmatter" in CHECK and "正文死链" in CHECK,
           "文档层 check 键在位（实体层加入不回归，EG-2-AC10）")
    code, d, _ = run_json("graph")
    ok("reg/graph_ok", code == 0 and isinstance(d, dict) and "docs_total" in d,
       "graph --json 正常（文档层语义零回归）")
    # EG-17-AC2 默认约定集开箱可用
    code2, _, _ = run("check", corpus=SELF)
    ok("reg/default_conv", code2 in (0, 1),
       "默认约定集加载、自宿主语料 check 不因 conv 崩（EG-17-AC2）")

# ---- 关系通配（零配置任意 Markdown 语料；证「通用工具不强求 project-specific 规范」） ----

def a_wildcard():
    """默认约定（无 .docstar/conventions）下，英文 frontmatter 键 + wikilink + 混合链接形皆建边。
    纯文档层能力，独立于实体层 schema——关系(边)通配，实体(类型符号)才需语法。"""
    layer("logic")
    code, g, _ = run_json("graph", corpus=GENERIC)
    if code != 0 or not isinstance(g, dict):
        ok("wildcard/graph_runs", False, "graph 零配置通用语料应跑通")
        return
    ch = g.get("chains", {})
    ok("wildcard/graph_runs", g.get("docs_total") == 5 and g.get("docs_with_frontmatter") == 4,
       "零配置扫 5 篇、4 篇含 frontmatter")
    up_design = ch.get("design.md", {}).get("上游", [])
    ok("wildcard/directed_wiki_and_path",
       "overview.md" in up_design and "research.md" in up_design,
       "design 上游=overview（upstream:[[wiki]]）+research（depends_on:路径）——声明键解 wiki+路径")
    ok("wildcard/keyed_nondirectional",
       ch.get("design.md", {}).get("关联", {}).get("related") == ["guide.md"],
       "design related:guide → 关联键边（非方向键=键名当边类型）")
    down_ov = ch.get("overview.md", {}).get("下游", [])
    ok("wildcard/downstream_md_and_path",
       "design.md" in down_ov and "guide.md" in down_ov,
       "overview 下游=design（[md 链接]）+guide（裸路径）")
    ok("wildcard/upstream_guide", ch.get("guide.md", {}).get("上游") == ["design.md"],
       "guide 上游=design（路径形）")
    code2, d, _ = run_json("doc", "design", corpus=GENERIC)
    body_in = d.get("被正文引用", {}) if isinstance(d, dict) else {}
    ok("wildcard/body_wikilink",
       code2 == 0 and "research.md" in body_in and "overview.md" in body_in,
       "design 被正文引用含 research（body [[design]] wiki）+overview（body [[overview]] wiki）")
    ok("wildcard/opportunistic_skip",
       isinstance(d, dict) and "status" not in d.get("关联", {}) and "title" not in d.get("关联", {}),
       "status:draft/title 标量不成边（机会式：无链接/路径形→跳过，不误当引用）")

# ---- config-free 类型识别（DG-37；认 agent 自然写的类型小节，不强求各家报 ID 语法） ----

def a_typesection():
    """默认约定下，agent 自然写的类型小节（`## 需求`/`## Parameters`/`## Tasks`）+ 加粗名条目
    → 该型实体，零配置零 ID 语法；节级作用域抗洪水；与 def_forms 共存不重促。"""
    layer("logic")
    code, d, _ = run_json("dump", corpus=GENERIC)
    if code != 0 or not isinstance(d, dict):
        ok("typesec/dump_runs", False, "dump 零配置通用语料应跑通")
        return
    by_kind = {}
    for e in d.get("entities", []):
        by_kind.setdefault(e["key"][0], set()).add(e["key"][2])
    req, par, tsk = by_kind.get("需求AC", set()), by_kind.get("参数", set()), by_kind.get("任务", set())
    ok("typesec/req_phrase", "用户可离线创建 widget" in req,
       "`## 需求` 节内 `- **用户可离线创建 widget**` → 需求AC 实体（名字=加粗短语，无需 ID 语法）")
    ok("typesec/param_phrases", {"同步重试上限", "离线缓存容量"} <= par,
       "`## Parameters` 节内加粗名条目 → 参数实体（config-free）")
    ok("typesec/task_phrases", {"接入同步网关", "加撤销缓冲"} <= tsk,
       "`## Tasks` 节内加粗名条目 → 任务实体（英文类型标题亦识别）")
    ok("typesec/def_forms_coexist", "REQ-9" in req,
       "同节内 `- **REQ-9**` 仍走 def_forms（两路共存，不重促）")
    ok("typesec/flood_safe", req == {"用户可离线创建 widget", "REQ-9"},
       "类型节外的加粗/散文不误 promote（节级作用域抗洪水）——需求AC 恰为该两条")

# ---- EG-19 类型开放（kind 集封闭→开放，从语料涌现；DG-38 波12-块1） ----

def a_openkind():
    """开放 kind：词表外 kind 从类型小节标题涌现、不报非法/不静默丢弃/不做同义归并；内置默认词表
    与开放 kind 共存；project-specific kinds 经 conventions 声明获得（不在引擎内置词表）。断言从 EG-19 AC 文本
    独立推导（禁抄实现）。独立小语料 fixtures/openkind（自带 .docstar/conventions 声明词表外 kind），
    不动 fixtures/generic（其文档数被 wildcard 断言计数）。"""
    layer("logic")
    default = set(EM.DEFAULT_KINDS)
    code, d, _ = run_json("dump", corpus=OPENKIND)
    names = ["openkind/emerges", "openkind/not_dropped", "openkind/no_synonym_merge",
             "openkind/default_coexist", "openkind/proj_kinds_via_conv"]
    if code != 0 or not isinstance(d, dict):
        for n in names:
            ok(n, False, "开放 kind 语料 dump 应跑通")
        return
    by_kind = {}
    for e in d.get("entities", []):
        by_kind.setdefault(e["key"][0], set()).add(e["key"][2])
    # EG-19-AC1：类型小节标题词=kind 本身；越出内置默认词表的 kind 照常涌现，不报「非法 kind」
    ok("openkind/emerges",
       by_kind.get("决策") == {"D-1", "D-2"} and "决策" not in default,
       "词表外 kind「决策」从 `## 决策` 类型小节涌现（D-1/D-2），越出 DEFAULT_KINDS 不报非法（EG-19-AC1）")
    # EG-19-AC1：不静默丢弃（越界 kind 无孤儿/无报错，dump 退 0）
    ok("openkind/not_dropped",
       code == 0 and not d.get("reports", {}).get("实体_schema_孤儿consumer")
       and "Requirement" in by_kind,
       "越界 kind 不静默丢弃、dump 退 0 无 schema 报错（EG-19-AC1）")
    # EG-19-AC2：kind 值逐字保留、不自动合并同义（Requirement 与内置 需求AC 各成各的 kind）
    ok("openkind/no_synonym_merge",
       by_kind.get("Requirement") == {"user-can-undo"} and "Requirement" not in default
       and "需求AC" in by_kind,
       "同义写法「Requirement」另成一 kind（as-written），不归并进内置 需求AC（EG-19-AC2）")
    # EG-19-AC3：内置默认词表与开放 kind 同语料共存
    ok("openkind/default_coexist",
       by_kind.get("需求AC") == {"REQ-100"},
       "内置默认 kind 需求AC 与开放 kind 共存于同一语料（EG-19-AC3）")
    # EG-19-AC3：project-specific kinds 均不在引擎内置词表、却在 fixture corpus dump 出现＝经 conventions 声明点亮
    proj_kinds = {e["key"][0] for e in DUMP.get("entities", [])} if ST["dump"] and DUMP else set()
    ok("openkind/proj_kinds_via_conv",
       not ({"契约AC", "审计AC", "评审项", "治理期权"} & default)
       and {"契约AC", "审计AC", "评审项", "治理期权"} <= proj_kinds,
       "契约AC/审计AC/评审项/治理期权 不在 DEFAULT_KINDS、却在 fixture dump 出现＝经 conventions 声明（EG-19-AC3）")

# ---- DG-41 代码遮罩（围栏/行内代码剥离；EG-21-AC1 假阳清零∧真断链仍检出） ----

def a_codemask():
    """独立证明语料 fixtures/codemask：围栏与行内代码内的示例链接/wiki/§引用不当真链接（假阳清零），
    代码外的真断链/断锚仍被检出（两侧都测，防「一律不扫代码块」把真链接也漏掉）。断言从 EG-21-AC1 独立推导。"""
    layer("logic")
    code, d, _ = run_json("check", corpus=CODEMASK)
    if code not in (0, 1) or not isinstance(d, dict):
        ok("codemask/runs", False, "codemask 语料 check 应跑通")
        return
    dl = json.dumps(d.get("正文死链", []), ensure_ascii=False)
    an = json.dumps(d.get("节引用断锚", []), ensure_ascii=False)
    ok("codemask/fenced_masked",
       "phantom-file" not in dl and "phantom-wiki" not in dl and "§99" not in an,
       "围栏代码内 [假链接]/[[假wiki]]/§99 不报（DG-41 fenced 剥离）")
    ok("codemask/inline_masked",
       "ghost-file" not in dl and "inline-wiki" not in dl and "§88" not in an,
       "行内代码内 `[假链接]`/`[[假wiki]]`/`§88` 不报（DG-41 inline 剥离）")
    ok("codemask/real_deadlink_detected",
       "nonexistent-file" in dl and "nonexistent-wiki" in dl,
       "代码外真断链（md 链接 + wiki）仍检出（EG-21-AC1 注入真断链仍报）")
    ok("codemask/real_anchor_detected", "§77" in an,
       "代码外真断锚 doc-b §77 仍检出（断锚型，DG-42）")
    ok("codemask/valid_link_clean", "doc-b.md" not in dl,
       "有效链接 [Doc B](doc-b.md) 解析、不报死链（防误遮真链接）")
    # fixtures/corpus 无围栏语料 dump 字节应与遮罩前等价（DG-41 对无代码语料是恒等，golden 稳定证据）
    code2, dd, _ = run_json("dump")
    ok("codemask/no_regression_on_plain",
       code2 == 0 and isinstance(dd, dict) and len(dd.get("entities", [])) > 0,
       "无围栏 fixtures dump 正常（代码遮罩对无代码语料恒等，golden 字节稳定）")


# ---- DG-42 诊断细分与逐条溯源（死链/断锚/歧义/缺必需边四型 + 溯源三元组） ----

def a_diagnostics():
    """四型独立诊断 + 每条 finding 携（源文件:行 + 原文 + 规则标识）三元组，使任一告警可脱离工具核验。
    断言从 EG-21-AC2 独立推导。死链/断锚在 doc 层，歧义在实体层，缺必需边 P2 空占位。"""
    layer("logic")
    # 死链/断锚（doc 层，codemask 语料稳定非空）：每条携溯源三元组
    _, dc, _ = run_json("check", corpus=CODEMASK)
    dead = (dc or {}).get("正文死链", [])
    anch = (dc or {}).get("节引用断锚", [])
    ok("diag/deadlink_triplet",
       bool(dead) and all({"源文件", "行", "原文", "规则", "诊断型"} <= set(x) for x in dead)
       and all(x["诊断型"] == "死链" for x in dead),
       "死链每条携 源文件/行/原文/规则/诊断型=死链（EG-21-AC2 溯源三元组）")
    ok("diag/anchor_triplet",
       bool(anch) and all({"源文件", "行", "原文", "规则", "诊断型", "目标"} <= set(x) for x in anch)
       and all(x["诊断型"] == "断锚" for x in anch),
       "断锚每条携 源文件/行/原文/规则/诊断型=断锚+目标（EG-21-AC2）")
    ok("diag/rule_identifier",
       all(x["规则"] in ("wiki_link", "md_link") for x in dead)
       and all(x["规则"] == "section_ref" for x in anch),
       "规则标识单源（wiki_link/md_link/section_ref），可回放为何判它有问题")
    # 歧义引用（实体层，fixtures 语料 §9 裸 R5/R11）：携诊断型=歧义引用 + 溯源
    if ST["check_entity"] and CHECK:
        amb = CHECK.get("ambiguous_reference", {})
        af = amb.get("findings", []) if isinstance(amb, dict) else []
        ok("diag/ambiguous_type",
           bool(af) and all(x.get("诊断型") == "歧义引用" and {"来源", "file", "line", "原文", "规则"} <= set(x)
                            for x in af),
           "歧义引用每条携 诊断型=歧义引用 + 源文件:行 + 原文 + 规则=bare_id（DG-42）")
        # 第四型 缺必需边：P2 required_edges 落地前空型占位（structurally_complete、findings 空）
        mne = CHECK.get("缺必需边", {})
        ok("diag/missing_edge_placeholder",
           isinstance(mne, dict) and mne.get("findings") == []
           and mne.get("judgment_status") == "structurally_complete",
           "缺必需边=四型第四型空占位（P2 required_edges/DG-47 落地前，findings 空）")
    else:
        for n in ("diag/ambiguous_type", "diag/missing_edge_placeholder"):
            todo(n, "波7-check", n)


# ---- DG-43 可复现 context_manifest（语料 revision + 工具版本 + conventions hash） ----

def a_manifest():
    """每命令输出顶层携 context_manifest；同输入同 output_hash（可复现）；改 conv 则 conventions_hash 变；
    conventions_source 稳定机器无关。断言从 EG-22-AC1 独立推导。"""
    layer("logic")
    REQ = {"corpus_revision", "tool_version", "conventions_hash", "conventions_source", "mode"}
    present = []
    for cmd in (("dump",), ("check",), ("harvest",), ("brief", "TA2.3"),
                ("verify", "--baseline", "HEAD"), ("classify", "--pending"), ("trace", "C2-AC31")):
        _, d, _ = run_json(*cmd)
        m = d.get("context_manifest") if isinstance(d, dict) else None
        present.append(bool(m) and REQ <= set(m) and "output_hash" in m)
    ok("manifest/all_commands", all(present),
       "dump/check/harvest/brief/verify/classify/trace 顶层皆携 context_manifest 全字段（EG-22-AC1）")
    # 同输入同 output_hash（可复现判据）
    _, d1, _ = run_json("dump")
    _, d2, _ = run_json("dump")
    h1 = d1["context_manifest"]["output_hash"]
    ok("manifest/reproducible", h1 == d2["context_manifest"]["output_hash"],
       "同语料同版本重跑 output_hash 一致（EG-22-AC1 可复现）")
    # 改任一输入（conv）则 conventions_hash 变、source 区分
    _, dself, _ = run_json("dump", corpus=SELF)          # 默认 conv
    ch_fix = d1["context_manifest"]["conventions_hash"]  # fixtures 项目 conv
    ch_self = dself["context_manifest"]["conventions_hash"]
    ok("manifest/conv_hash_sensitive", ch_fix != ch_self,
       "不同 conventions（fixtures 项目 vs 默认）→ conventions_hash 变（防不可见第二事实源）")
    ok("manifest/source_stable",
       d1["context_manifest"]["conventions_source"] == "project"
       and dself["context_manifest"]["conventions_source"] == "default",
       "conventions_source ∈ {project,default}（稳定、机器无关，禁绝对路径入输出）")
    # corpus_revision=工作树扫描稳定符号（非逐 commit 变的 SHA，golden 可复现）
    ok("manifest/revision_stable", d1["context_manifest"]["corpus_revision"] == "worktree",
       "工作树扫描 corpus_revision='worktree'（稳定符号，非 SHA→golden 可复现）")


# ---- DG-44 输出语义分层命名（全输出面无「语义验收通过」态词审计） ----

def a_output_naming():
    """扫全部命令 JSON 状态字段值域，命中「通过/verified/approved/passed/合格/验收」类词即红（防回归引入
    语义色彩）；judgment_status 值 ⊆ 结构态四词；html 模板源文本另扫英文旧态词。断言从 EG-22-AC2
    独立推导（DG-44 supersede 词汇）。"""
    layer("logic")
    FORBID = ("通过", "verified", "approved", "passed", "合格", "验收", "authoritative", "indeterminate")
    ALLOWED = set(EM.STRUCTURAL_STATES)
    statuses = []
    # check：全实体检查判定对象的 judgment_status
    _, dc, _ = run_json("check")
    if isinstance(dc, dict):
        for v in dc.values():
            if isinstance(v, dict) and "judgment_status" in v:
                statuses.append(v["judgment_status"])
    # brief：顶层 judgment_status
    _, db, _ = run_json("brief", "TA2.3")
    if isinstance(db, dict) and "judgment_status" in db:
        statuses.append(db["judgment_status"])
    ok("naming/judgment_status_structural",
       bool(statuses) and all(s in ALLOWED for s in statuses),
       f"全命令 judgment_status ⊆ 结构态四词（采样 {len(statuses)} 项，EG-22-AC2/DG-44）")
    blob = json.dumps({"c": dc, "b": db}, ensure_ascii=False)
    hits = [w for w in FORBID if w in blob]
    ok("naming/no_semantic_acceptance_word", not hits,
       f"全输出面无「语义验收通过」类状态词（命中={hits or '无'}；引擎永不发语义合格信号，EG-22-AC2）")
    # html 模板源文本也是输出面（31f8ecd 前曾漏网）：只扫两个英文旧态词——中文语义词在模板
    # UI 文案中合法（如「N 项非干净通过」），.py 源码不扫（entity_brief 局部变量名合法）。
    tpl = (HERE / "internal" / "entity_template.html").read_text(encoding="utf-8")
    tpl_hits = [w for w in ("authoritative", "indeterminate") if w in tpl]
    ok("naming/template_no_old_state_word", not tpl_hits,
       f"entity_template.html 无旧态词 authoritative/indeterminate（命中={tpl_hits or '无'}；DG-44 输出面含 HTML 模板）")


# ---- EG-32/DG-64 机读契约 drift-lock：每命令 --json 顶层键集锁定（command-contracts 契约表机检对账） ----

def a_contract_toplevel():
    """eg-3：硬编码每命令公开 JSON 顶层键集，对 fixtures/corpus 逐命令核对。
    断言 实际顶层键==期望集——references/command-contracts.md「JSON output contract」表的机检对账，
    防契约表悄然腐坏（加/删/改键须契约表与本 dict 两处同批改，人工对齐）。覆盖全部 13 个 JSON 命令，无豁免：verify 用
    --baseline HEAD（fixtures/corpus 在 git 下、diff 内容不入顶层键故键集稳定确定）、classify 用
    --pending、harvest 无需基线——皆 fixtures/corpus 上确定。ids 顶层键=kind 值（开放词汇，此处锁
    fixtures/corpus 冻结的 kind 集，drift=fixture kind 词汇变=真信号，非命令形状回归）；doc 取无
    关联键的 A轨任务（关联 键仅在有非方向 frontmatter 键边时出现，取稳定 11 键篇）。"""
    layer("logic")
    EXPECTED_TOP = {
        # 文档层（不携 context_manifest，同 graph/doc/id/ids/docs）
        "graph": ({"docs_total", "docs_with_frontmatter", "chains"}, ["graph"]),
        "doc": ({"doc", "meta", "upstream", "downstream", "frontmatter_references_in",
                 "body_links_out", "body_links_in", "section_references_out", "section_references_in",
                 "section_count", "top_id_mentions"}, ["doc", "A轨任务"]),
        "id": ({"id", "kind", "total", "docs"}, ["id", "R1-AC1"]),
        "id_section": ({"query", "target_anchor", "references"}, ["id", "A轨任务 §2"]),
        "ids": ({"kinds"}, ["ids"]),
        "docs": ({"docs"}, ["docs", "--fields", "性质,状态"]),
        # 实体层（携 context_manifest）
        "dump": ({"context_manifest", "schema_version", "corpus_root", "classification_complete",
                  "unknown_documents", "entities", "edges", "reports"}, ["dump"]),
        "check": ({"context_manifest", "frontmatter_broken_links", "frontmatter_unlinked_entries",
                   "frontmatter_declared_nonlinks", "downstream_missing_upstream_reciprocal",
                   "upstream_missing_downstream_reciprocal", "body_broken_links",
                   "unregistered_parameters_3plus", "top_unresolved_section_prefixes",
                   "broken_section_anchors", "missing_frontmatter", "schema_version",
                   "broken_term_definition_anchors", "coverage_gaps", "mapping_gaps",
                   "propagation_breaks", "prerequisite_cycles", "unresolved_reference",
                   "ambiguous_reference", "cooccurrence_completeness", "required_edge_gaps",
                   "uncovered_kinds", "classification_complete", "orphan_schema_consumers"},
                  ["check"]),
        "trace": ({"context_manifest", "query", "resolved", "nature", "primary", "candidates",
                   "attrs", "edges"}, ["trace", "C2-AC31"]),
        "brief": ({"context_manifest", "schema_version", "mode", "query", "resolved", "nature",
                   "judgment_status", "classification_complete", "truncated", "deterministic_deduplication",
                   "segments", "omitted", "diagnostics", "boundary_pointers", "tainted_by"},
                  ["brief", "TA2.3"]),
        "verify": ({"context_manifest", "schema_version", "baseline", "baseline_source", "scan_root",
                    "added_entities", "removed_entities", "added_edges", "removed_edges",
                    "introduced_findings", "graph_omissions", "limitations"},
                   ["verify", "--baseline", "HEAD"]),
        "classify": ({"context_manifest", "schema_version", "mode", "corpus_root",
                      "classification_complete", "total_documents", "pending_count", "pending"},
                     ["classify", "--pending"]),
        "harvest": ({"context_manifest", "schema_version", "algo", "filtered", "candidates"},
                    ["harvest"]),
        "drift": ({"context_manifest", "schema_version", "drifts"}, ["drift"]),
    }
    for name, (expected, args) in EXPECTED_TOP.items():
        _c, d, _e = run_json(*args, public=True)
        actual = set(d) if isinstance(d, dict) else None
        ok(f"contract/top_{name}", actual == expected,
           f"{name} --json 顶层键==契约表期望（command-contracts JSON output contract 对账）；"
           f"缺={sorted(expected - (actual or set()))} 多={sorted((actual or set()) - expected)}")


def a_eg3_bilingual_contract():
    """v0.2/eg-3：JSON 只用稳定英文合同；显示语言不影响机器输出；GMGN 中英文镜像语料同图。"""
    layer("logic")

    def non_ascii_keys(value):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if any(ord(ch) > 127 for ch in key):
                    found.append(key)
                found.extend(non_ascii_keys(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(non_ascii_keys(item))
        return found

    ce, de, ee = run_json("dump", "--preset", "gmgn-v1", "--lang", "en", corpus=GMGN_EN, public=True)
    cz, dz, ez = run_json("dump", "--preset", "gmgn-v1", "--lang", "zh-CN", corpus=GMGN_ZH, public=True)
    ok("eg3/schema", ce == 0 and cz == 0 and isinstance(de, dict)
       and de.get("schema_version") == "eg-3",
       f"中英 GMGN dump 均成功且 schema_version=eg-3（en={ce}/{ee[:80]!r}, zh={cz}/{ez[:80]!r}）")
    bad_keys = sorted(set(non_ascii_keys(de or {}) + non_ascii_keys(dz or {})))
    ok("eg3/english_keys_only", not bad_keys,
       f"机器 JSON 键只用 ASCII 英文合同；非 ASCII 键={bad_keys}")
    entities = de.get("entities", []) if isinstance(de, dict) else []
    edges_ = de.get("edges", []) if isinstance(de, dict) else []
    ok("eg3/english_tokens",
       entities and all(e.get("nature") == "normative" for e in entities)
       and any(e.get("key", [None])[0] == "task" for e in entities)
       and any(e.get("type") == "task-declaration" for e in edges_),
       "内置 kind、nature 与 edge type 也使用稳定英文 token")
    check_code, check_data, check_err = run_json(
        "check", "--preset", "gmgn-v1", corpus=GMGN_EN, public=True)
    coverage = (check_data or {}).get("coverage_gaps", {})
    uncovered = (check_data or {}).get("uncovered_kinds", {})
    ok("eg3/gmgn_policy_scope",
       check_code == 0
       and not any(e.get("key", [None, None, None])[0] == "requirement-ac"
                   and e.get("key", [None, None, None])[2] == "R1"
                   for e in entities)
       and coverage.get("findings") == []
       and uncovered.get("findings") == [],
       f"GMGN 只检查 Rn-ACn→Task，辅助 kind 不误报（stderr={check_err[:60]!r}）")
    trace_code, trace_data, trace_err = run_json(
        "trace", "T1", "--preset", "gmgn-v1", corpus=GMGN_EN, public=True)
    trace_groups = (trace_data or {}).get("edges", {})
    ok("eg3/trace_edge_groups",
       trace_code == 0 and "task-declaration" in trace_groups
       and not non_ascii_keys(trace_groups),
       f"trace.edges 分组键也使用英文 edge token（stderr={trace_err[:60]!r}）")
    ok("eg3/gmgn_locale_parity", isinstance(de, dict) and de == dz,
       "GMGN 英文与中文镜像语料产生逐字段相同的 dump（语言不改变图语义）")

    c1, out1, err1 = run("graph", "--preset", "gmgn-v1", "--lang", "en", corpus=GMGN_EN, as_json=True)
    c2, out2, err2 = run("graph", "--preset", "gmgn-v1", "--lang", "zh-CN", corpus=GMGN_EN, as_json=True)
    ok("eg3/json_language_invariant", c1 == c2 == 0 and out1 == out2,
       f"同一语料 JSON 不受 --lang 影响（stderr={err1[:40]!r}/{err2[:40]!r}）")

    he, help_en, _ = run("--lang", "en", corpus=None)
    hz, help_zh, _ = run("--lang", "zh-CN", corpus=None)
    hi, _, err_invalid = run("--lang", "fr", corpus=None)
    ok("eg3/help_localized",
       he == hz == 0 and "Usage:" in help_en and "用法：" in help_zh,
       "--lang en|zh-CN 切换帮助文本")
    human_code, human_en, human_err = run(
        "graph", "--preset", "gmgn-v1", "--lang", "en", corpus=GMGN_EN)
    ok("eg3/english_human_output",
       human_code == 0 and "docs_total:" in human_en and "文档" not in human_en,
       f"英文人读输出使用 eg-3 英文标签（stderr={human_err[:60]!r}）")
    with tempfile.TemporaryDirectory() as td:
        graph_path = Path(td) / "graph.html"
        entity_path = Path(td) / "entity.html"
        gh, _, geh = run("html", str(graph_path), "--preset", "gmgn-v1", "--lang", "en", corpus=GMGN_EN)
        eh, _, eeh = run("html-entity", str(entity_path), "--preset", "gmgn-v1", "--lang", "en", corpus=GMGN_EN)
        graph_html = graph_path.read_text(encoding="utf-8") if graph_path.exists() else ""
        entity_html = entity_path.read_text(encoding="utf-8") if entity_path.exists() else ""
    ok("eg3/html_localized",
       gh == eh == 0 and "DocStar document graph" in graph_html
       and "Search document name" in graph_html and "Entity kinds" in entity_html
       and '<html lang="en">' in graph_html and '<html lang="en">' in entity_html
       and "Degree ${n.deg} (incoming " in graph_html
       and "<th>Incoming</th><th>Outgoing</th><th>Degree</th>" in graph_html
       and '"key": "broken_term_definition_anchors"' in entity_html
       and "Classification complete: " in entity_html
       and "One-hop neighborhood: " in entity_html
       and not any(fragment in graph_html + entity_html for fragment in (
           "连接Degree", "项检查，", "分类完备：", "一跳邻域：", "实体图谱")),
       f"--lang en 本地化两种 HTML 界面（stderr={geh[:40]!r}/{eeh[:40]!r}）")
    ok("eg3/lang_fail_closed", hi == 2 and "fr" in err_invalid,
       "未知显示语言退出 2 并指出无效值")

    gate_code, _, _ = run("check", "--gate", "broken_section_anchors")
    kind_code, kinds, _ = run_json("ids", "--kind", "task", public=True)
    fields_code, projected, _ = run_json(
        "docs", "--fields", "nature,status", public=True)
    projected_rows = projected.get("docs", []) if isinstance(projected, dict) else []
    ok("eg3/english_selectors",
       gate_code == 1 and kind_code == 0
       and kinds.get("kinds", [{}])[0].get("kind") == "task"
       and fields_code == 0 and projected_rows
       and {"nature", "status"} <= set(projected_rows[0]),
       "--gate/--kind/--fields 接受 eg-3 英文键和值，旧中文语料仍可查询")


def a_bilingual_docs():
    """Public documentation pairs keep one machine contract while localizing prose."""
    layer("logic")
    pairs = [
        ("README.md", "README.zh-CN.md"),
        ("CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md"),
        ("CHANGELOG.md", "CHANGELOG.zh-CN.md"),
        ("references/command-contracts.md", "references/command-contracts.zh-CN.md"),
        ("references/conventions.md", "references/conventions.zh-CN.md"),
        ("references/writing-guide.md", "references/writing-guide.zh-CN.md"),
        ("internal/README.md", "internal/README.zh-CN.md"),
    ]

    def frontmatter(text):
        match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        if not match:
            return {}
        result = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    def commands(text):
        rows = set()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(("python3 ", "git ", "cp ", "mkdir ", "pip ")):
                rows.add(re.sub(r"--lang\s+(?:en|zh-CN)", "--lang <locale>", line))
        return rows

    missing, bad_locale, fence_drift, command_drift, backlink_drift = [], [], [], [], []
    for en_rel, zh_rel in pairs:
        en_path, zh_path = HERE / en_rel, HERE / zh_rel
        if not en_path.is_file() or not zh_path.is_file():
            missing.append((en_rel, zh_rel))
            continue
        en, zh = en_path.read_text(encoding="utf-8"), zh_path.read_text(encoding="utf-8")
        if frontmatter(en).get("locale") != "en" or frontmatter(zh).get("locale") != "zh-CN":
            bad_locale.append((en_rel, zh_rel))
        if en.count("```") != zh.count("```"):
            fence_drift.append((en_rel, zh_rel))
        if commands(en) != commands(zh):
            command_drift.append((en_rel, zh_rel))
        if Path(zh_rel).name not in en or Path(en_rel).name not in zh:
            backlink_drift.append((en_rel, zh_rel))
    ok("docs/pairs_exist", not missing, f"公共文档中英文镜像齐全；缺失={missing}")
    ok("docs/locale_frontmatter", not bad_locale, f"镜像 locale 固定为 en/zh-CN；异常={bad_locale}")
    ok("docs/code_fence_parity", not fence_drift, f"镜像代码块数量一致；漂移={fence_drift}")
    ok("docs/command_parity", not command_drift, f"镜像命令行（忽略 locale 值）一致；漂移={command_drift}")
    ok("docs/cross_links", not backlink_drift, f"每对文档互链；缺口={backlink_drift}")

    writing_en = (HERE / "references/writing-guide.md").read_text(encoding="utf-8")
    writing_zh = (HERE / "references/writing-guide.zh-CN.md").read_text(encoding="utf-8")
    tokens = ("locale", "purpose", "upstream", "downstream", "status", "type", "nature",
              "draft", "pending-approval", "approved", "closed", "normative", "descriptive",
              "spec anchor", "prerequisite", "failing test")
    missing_tokens = [token for token in tokens if token not in writing_en or token not in writing_zh]
    ok("docs/writing_contract_parity", not missing_tokens,
       f"两种语言的写作规范共享机器 token；缺失={missing_tokens}")
    removed_skeleton_markers = (
        "## Normative template", "## Descriptive templates", "# <Title>",
        "## 规范文档模板", "## 记述文档模板", "# <标题>",
    )
    skeleton_hits = [
        marker for marker in removed_skeleton_markers
        if marker in writing_en or marker in writing_zh
    ]
    ok("docs/no_copy_ready_skeletons", not skeleton_hits,
       f"写作指南只保留内容契约与检查清单，不含可复制章节骨架；残留={skeleton_hits}")
    canonical_task_header = "| # | task | spec anchor | prerequisite | failing test | status |"
    task_surfaces = [
        writing_en,
        writing_zh,
        (Path(GMGN_EN) / "Task.md").read_text(encoding="utf-8"),
        (Path(GMGN_ZH) / "Task.md").read_text(encoding="utf-8"),
    ]
    ok("docs/canonical_task_header",
       all(canonical_task_header in text and "| # | goal |" not in text
           for text in task_surfaces),
       "DocStar 双语写作契约与 GMGN fixture 共用完整的固定任务表头")


# ---- EG-31/DG-62 投影查询面功能语义（critic 轮1 处置 A-M1/B-M1：EXPECTED_TOP 已锁顶层键，本组锁数据内容） ----

def a_dump_kind():
    """dump --kind 投影语义功能锁定：实体全 key[0]==K、边触及式（src[0]==K ∨ dst[0]==K）、语料级
    诊断不随 kind 过滤、未知 kind 退 1；另锁非闭合意图（critic 轮1-B M1 披露路线）——投影边的对端
    实体可能不在投影 entities 内，此为设计意图非缺陷，断言防未来悄然改判为闭合子图语义。"""
    layer("logic")
    c, d, _ = run_json("dump", "--kind", "任务")
    ents = d.get("entities", []) if isinstance(d, dict) else []
    es = d.get("edges", []) if isinstance(d, dict) else []
    ok("a_dump_kind/entities_filtered",
       c == 0 and len(ents) == 8 and all(e["key"][0] == "任务" for e in ents),
       f"--kind 任务：entities 全 key[0]==任务 且数量==8，实为 {len(ents)} 条")
    ok("a_dump_kind/edges_touch",
       len(es) == 45 and all(e["src"][0] == "任务" or e["dst"][0] == "任务" for e in es),
       f"--kind 任务：edges 数==45 且每条 src[0]==任务 或 dst[0]==任务（touch 语义），实为 {len(es)} 条")
    # 非闭合意图锁定（DG-62 披露路线）：至少一条边的对端 key 不在投影 entities 的 key 集合内——
    # 非闭合=有意（拉齐对端=变相 ego 邻域，过度设计），此断言防未来悄然改语义为闭合子图。
    ent_keys = {tuple(e["key"]) for e in ents}
    non_closed = [e for e in es
                  if tuple(e["src"]) not in ent_keys or tuple(e["dst"]) not in ent_keys]
    ok("a_dump_kind/non_closed_by_design", len(non_closed) > 0,
       f"至少一条边对端实体不在投影 entities 内（非闭合是有意语义，DG-62），实为 {len(non_closed)} 条")
    # 语料级诊断不过滤：reports/unknown_documents/classification_complete 与无 --kind 全量输出逐键相等
    c0, d0, _ = run_json("dump")
    ok("a_dump_kind/corpus_level_unfiltered",
       c0 == 0 and d.get("reports") == d0.get("reports")
       and d.get("unknown_documents") == d0.get("unknown_documents")
       and d.get("classification_complete") == d0.get("classification_complete"),
       "reports/unknown_documents/classification_complete 与全量 dump 逐键相等（语料级诊断不随 kind 过滤）")
    c2, _, err2 = run("dump", "--kind", "不存在")
    ok("a_dump_kind/unknown_kind_exit1", c2 == 1,
       f"--kind 不存在 → 退 1，实为 exit={c2}（stderr={err2.strip()[:60]}）")


def a_docs():
    """docs [glob] [--fields] 功能语义锁定（EXPECTED_TOP 已锁 `docs` 顶层键，本组只锁功能行为）：
    全量文档数、glob 全路径匹配子集、无命中 glob 退 0 且 docs==[]、--fields 取值/缺失=null。"""
    layer("logic")
    c, d, _ = run_json("docs")
    docs = d.get("docs", []) if isinstance(d, dict) else []
    ok("a_docs/total_count", c == 0 and len(docs) == 14,
       f"docs --json 全量 14 条，实为 {len(docs)} 条")
    c2, d2, _ = run_json("docs", "protocol/契约初稿/*")
    matched = [r["doc"] for r in d2.get("docs", [])] if isinstance(d2, dict) else []
    ok("a_docs/glob_subset",
       c2 == 0 and len(matched) == 4 and all(m.startswith("protocol/契约初稿/") for m in matched),
       f"glob protocol/契约初稿/* 命中 4 条且均在该目录下（fnmatchcase 全路径，`*` 跨 `/`），实为 {matched}")
    c3, d3, _ = run_json("docs", "zzz不存在*")
    ok("a_docs/glob_no_match", c3 == 0 and d3 == {"docs": []},
       f"无命中 glob → 退 0 且 docs==[]（glob 是模式非键，∅ 合法），实为 exit={c3} data={d3}")
    c4, d4, _ = run_json("docs", "--fields", "性质")
    rows = {r["doc"]: r.get("性质") for r in d4.get("docs", [])} if isinstance(d4, dict) else {}
    ok("a_docs/fields_value",
       c4 == 0 and rows.get("protocol/A轨-Core与跨链/A轨任务.md") == ["规范"],
       f"--fields 性质：已知文档字段值==['规范']，实为 {rows.get('protocol/A轨-Core与跨链/A轨任务.md')}")
    ok("a_docs/fields_missing_null",
       rows.get("protocol/未分类-契约三草案.md") is None,
       f"--fields 性质：无该字段文档==null，实为 {rows.get('protocol/未分类-契约三草案.md')!r}")


# ================= 波13-P1/P2 断言分区（控制者预开缝 2026-07-16） =================
# 并行纪律：P1 agent 只写 a_wave13_p1 函数体、P2 agent 只写 a_wave13_p2 函数体，
# 体外一律勿动（含本注释与函数签名）——两 agent 共享本文件的唯一合法写区即各自函数体。

def a_wave13_p1():
    """波13-P1 分区：EG-23 确定性上下文编译器（DG-45/46）。owner=P1 agent。
    断言从 EG-23-AC1..AC6 独立推导（DG-6 禁读实现）。证明语料＝fixtures/briefmode（自带 .docstar 配置，
    与 P2 在改的 fixtures/corpus 隔离，稳）；execute 面保留另在 fixtures/corpus TA2.3 loose 核（frozen 数据）。
    覆盖：三模式差异 / 部分分类降级 / bundle 七件合同 / 预算不切半条 / 锚粒度 / 指针内容分层 / 去重 / 模式校验。"""
    layer("logic")
    bm = str(HERE / "fixtures" / "briefmode")

    def segkeys(d):
        return {":".join(s["key"]) for s in d["segments"]} if isinstance(d, dict) else set()

    # 三模式（EG-23-AC2）：execute=EG-13 遍历面；impact=反向引用+下游传导点；review=同 ns 断言+结构邻居；三面各异。
    ce, de, _ = run_json("brief", "T1", "--mode", "execute", corpus=bm)
    ci, di, _ = run_json("brief", "T1", "--mode", "impact", corpus=bm)
    cr, dr, _ = run_json("brief", "T1", "--mode", "review", corpus=bm)
    ok("p1/mode_execute_face",
       ce == 0 and segkeys(de) == {"任务:任务:T1", "需求AC:REQUIREMENTS:R1-AC1",
                                    "测试:测试名:ac_r1_ac1_base", "节条目:设计:设计§2.1"},
       "execute＝EG-13 遍历面（任务行+任务声明 AC+阅读依赖 §+任务测试；映射/共现不入，EG-23-AC2 execute）")
    ok("p1/mode_impact_reverse",
       ci == 0 and "任务:任务:T2" in segkeys(di)
       and any(s["inclusion_reason"].get("方向") == "入"
               for s in di["segments"] if s["key"][-1] == "T2"),
       "impact＝反向引用+下游传导点：T2 前置依赖反向命中（改 T1 波及 T2，方向=入），EG-23-AC2 impact")
    ok("p1/mode_review_siblings",
       cr == 0 and {"任务:任务:T2", "任务:任务:T3", "任务:任务:T4"} <= segkeys(dr)
       and any(s.get("状态") and s["inclusion_reason"].get("规则") == "同namespace断言"
               for s in dr["segments"]),
       "review＝同 namespace 兄弟断言（携状态，superseded 显式可见）+ 结构邻居，EG-23-AC2 review")
    ok("p1/modes_differ",
       isinstance(di, dict) and isinstance(dr, dict)
       and segkeys(de) != segkeys(di) and segkeys(dr) != segkeys(de)
       and di.get("mode") == "impact" and dr.get("mode") == "review",
       "三模式确定性取材面各异（execute≠impact≠review），纳入由确定性边/规则算出非语义相似，EG-23-AC2")

    # 部分分类降级（EG-23-AC1）：已声明部分出可用闭包、未分类节点跳过并显式报告，替代 EG-13-AC4 全有全无。
    c3, d3, _ = run_json("brief", "T3", "--mode", "execute", corpus=bm)
    seg3 = segkeys(d3)
    om3 = {o["key"][-1]: o for o in d3["omitted"]} if isinstance(d3, dict) else {}
    ok("p1/partial_usable_kept",
       c3 == 0 and "需求AC:REQUIREMENTS:R1-AC1" in seg3,
       "部分降级：已声明（规范）部分产出可用闭包（R1-AC1 内容层入段），EG-23-AC1")
    ok("p1/partial_unknown_skipped_reported",
       "草案§3.1" in om3 and om3["草案§3.1"]["原因"] == "未分类跳过"
       and om3["草案§3.1"].get("指针") is not None,
       "部分降级：未分类（unknown 来源）节点跳过并显式报告（omitted 未分类跳过+指针，不静默丢弃），EG-23-AC1")
    ok("p1/partial_tainted_not_broken",
       isinstance(d3, dict) and d3.get("judgment_status") == "tainted"
       and d3.get("tainted_by") == ["草案.md"] and d3.get("classification_complete") is False,
       "部分降级：触达 unknown→tainted（非全空 broken）+ tainted_by 溯源，替代 EG-13-AC4 全有全无，EG-23-AC1")
    c9, d9, _ = run_json("brief", "T9", "--mode", "execute", corpus=bm)
    om9 = {o["key"][-1]: o for o in d9["omitted"]} if isinstance(d9, dict) else {}
    ok("p1/partial_broken_subject_visible",
       c9 == 0 and d9.get("judgment_status") == "broken" and "任务:任务:T9" in segkeys(d9)
       and "R1-AC1" in om9 and om9["R1-AC1"]["原因"].startswith("来源非规范"),
       "非规范来源：任务来源非规范→broken 但仍出任务行段 + 依赖列 omitted 显式可见（非旧 EG-13-AC4 全空闭包），EG-23-AC1")

    # bundle 最小合同七件（EG-23-AC3）：原文逐字/来源锚/inclusion_reason/omitted/diagnostics/manifest+hash/去重排序标记。
    ok("p1/bundle_seven_pieces",
       isinstance(de, dict)
       and all(k in de for k in ("segments", "omitted", "diagnostics", "context_manifest", "去重稳定排序"))
       and "output_hash" in de.get("context_manifest", {})
       and all({"锚", "inclusion_reason", "layer"} <= set(s) and "原文" in s for s in de["segments"]),
       "bundle 七件合同齐全：段携原文/锚/inclusion_reason + omitted + diagnostics + manifest(含 output_hash) + 去重排序标记，EG-23-AC3")
    ok("p1/bundle_verbatim_no_summary",
       isinstance(de, dict) and any(
           s["layer"] == "content" and s.get("原文") and s["原文"].strip().startswith("- **R1-AC1**")
           for s in de["segments"]),
       "内容层原文逐字（禁摘要替代）：R1-AC1 段＝定义行原文，EG-23-AC3 ①")
    ok("p1/bundle_omitted_explicit",
       isinstance(d3, dict) and len(d3["omitted"]) >= 1
       and all({"原因", "指针"} <= set(o) for o in d3["omitted"]),
       "omitted 清单显式（禁无声截断）：每条带原因+指针（供 agent 自取），EG-23-AC3 ④")
    ok("p1/dedup_stable_marker",
       isinstance(de, dict) and de.get("去重稳定排序", {}).get("已应用") is True,
       "去重/稳定排序标记显式（合同 ⑦，防悄悄漏做），EG-23-AC3 ⑦")
    t2_review = [s for s in dr["segments"] if s["key"][-1] == "T2"] if isinstance(dr, dict) else []
    ok("p1/dedup_single_segment", len(t2_review) == 1,
       "同实体多路径命中去重取一（review 中 T2 兼兄弟+结构邻居→单段），EG-23-AC3 ⑦")

    # diagnostics + execute 面保留：fixtures/corpus TA2.3（frozen 数据，R7-AC1 无定义块稳定，与 P2 conventions 编辑正交）。
    ct, dt, _ = run_json("brief", "TA2.3", "--mode", "execute")
    ok("p1/diagnostics_nodef",
       ct == 0 and any(x["诊断型"] == "无定义块" and x["原文"] == "R7-AC1"
                       and {"源文件", "行", "规则"} <= set(x) for x in dt["diagnostics"]),
       "diagnostics 携无定义块诊断（命中引用形却无定义块＝真 provenance 缺口，DG-42 同形溯源），EG-23-AC3 ⑤")
    # 2026-07-17 裁决①（性质随 primary）传导：R7-AC1 无定义块→性质=unknown→未分类跳过 omitted
    # +judgment tainted（EG-23-AC1；修前性质黏首现文档碰巧=规范才进 segments）。取材面其余三键不变。
    ok("p1/execute_face_preserved_realcorpus",
       ct == 0 and dt.get("judgment_status") == "tainted"
       and {"契约AC:契约二:C2-AC1",
            "节条目:A轨设计:A轨设计§2.1", "任务:A轨任务:TA2.1"} <= segkeys(dt)
       and any(x["key"] == ["需求AC", "REQUIREMENTS", "R7-AC1"] and x["原因"] == "未分类跳过"
               for x in dt["omitted"]),
       "execute 面保留（取材面三键不破；R7-AC1 无定义块=unknown 落 omitted 显式可见+tainted）")

    # 确定性预算裁剪（EG-23-AC4）：绝不切半条断言——超预算断言整条转指针+列 omitted，充裕则整条纳入；模式/预算入 manifest。
    cb, db, _ = run_json("brief", "T4", "--mode", "execute", "--budget", "100", corpus=bm)
    cf, df, _ = run_json("brief", "T4", "--mode", "execute", corpus=bm)
    r2b = next((s for s in db["segments"] if s["key"][-1] == "R2-AC1"), None) if isinstance(db, dict) else None
    r2f = next((s for s in df["segments"] if s["key"][-1] == "R2-AC1"), None) if isinstance(df, dict) else None
    blob = json.dumps(db, ensure_ascii=False)
    ok("p1/budget_atomic_no_halfcut",
       cb == 0 and db.get("truncated") is True and r2b and r2b.get("原文") is None
       and any(o["key"][-1] == "R2-AC1" and o["原因"] == "预算截断" for o in db["omitted"])
       and "预算截断]" not in blob and "…[" not in blob,
       "预算裁剪绝不切半条断言：超预算断言整条转坐标指针+列 omitted 预算截断，无正文中段截断标记，EG-23-AC4")
    ok("p1/budget_full_when_fits",
       cf == 0 and df.get("truncated") is False and r2f and r2f.get("原文") and len(r2f["原文"]) > 150,
       "预算充裕时同一断言整条内容层纳入（原子单位：整入或整省，非中段截断），EG-23-AC4")
    ok("p1/budget_in_manifest",
       isinstance(db, dict) and db["context_manifest"].get("budget") == 100
       and db["context_manifest"].get("mode") == "brief:execute",
       "模式/预算入 manifest（接 EG-22-AC1 可复现），DG-45")

    # 锚粒度下沉（EG-23-AC5）：每段锚到行（doc+line+line_end），非仅到文档。
    ok("p1/anchor_line_granularity",
       isinstance(de, dict)
       and all(s["锚"] is None or {"doc", "line", "line_end"} <= set(s["锚"]) for s in de["segments"])
       and any(s["锚"] and s["锚"]["line"] >= 1 for s in de["segments"]),
       "锚点粒度到行（文件:行，非仅到文档）——agent 一跳回原文核验，EG-23-AC5")

    # 指针层/内容层分离（EG-23-AC6）：layer∈{content,pointer}；内容层携原文、指针层仅坐标（可分开取）。
    layers = {s["layer"] for s in de["segments"]} if isinstance(de, dict) else set()
    ok("p1/layer_pointer_content_split",
       ce == 0 and layers == {"content", "pointer"}
       and all((s["layer"] == "content") == (s.get("原文") is not None or s.get("note") is not None)
               for s in de["segments"]),
       "指针层（坐标+摘要，原文 None）与内容层（原文逐字）分离、可分开取，逐层展开靠边界指针，EG-23-AC6")

    # 模式校验（DG-45 确定性契约）：未知模式退非零。
    cx, _, _ = run("brief", "T1", "--mode", "bogus", corpus=bm, as_json=True)
    ok("p1/mode_validation", cx == 2,
       "未知 brief 模式→退出码 2（确定性契约，非静默降级），DG-45")


def a_wave13_p2():
    """波13-P2 分区：EG-20 收缩 required_edges（DG-47）/EG-24 drift（DG-48）/EG-25 migrate（DG-49）。owner=P2 agent。"""
    layer("logic")
    import subprocess
    import tempfile
    REQEDGE = str(HERE / "fixtures" / "reqedge")     # 规则就地绑 kind 假绿证明语料（EG-20-AC3/AC5）
    DRIFT = str(HERE / "fixtures" / "drift")          # 值漂移证明语料（EG-24）

    # ===== EG-20 required_edges 等价保绿 + 休眠 + 未覆盖kind 告警（DG-47/EG-20-AC2/AC3/AC5）=====
    if not ST["check_entity"]:
        for n in ("p2/req_coverage_equiv", "p2/req_mapping_equiv", "p2/uncovered_kind_reports"):
            todo(n, "波7-check", n)
    else:
        _, cf, _ = run_json("check", corpus=CORPUS)   # fixture 声明 required_edges → 驱动 CHK-2
        cov = cf.get("CHK-2覆盖缺口", {})
        mp = cf.get("CHK-2映射缺口", {})
        covdisp = [f.get("display") for f in cov.get("findings", [])]
        # 等价保绿：required_edges 驱动的 CHK-2 两键 findings 与旧写死等价（锚定既有已知缺口/覆盖）
        ok("p2/req_coverage_equiv",
           "C2-AC5" in covdisp and "R1-AC2" in covdisp and "R2-AC1" in covdisp and "R1-AC1" not in covdisp,
           "等价保绿：required_edges 驱动的 CHK-2覆盖缺口 == 旧写死（C2-AC5/R1-AC2/R2-AC1 缺口、R1-AC1 双覆盖不入）")
        ok("p2/req_coverage_tainted",
           cov.get("judgment_status") == "tainted" and list_has(cov.get("tainted_by"), "未分类"),
           "等价保绿：覆盖缺口 tainted 传播不变（缺口依赖 unknown 文档 → 检查级 tainted）")
        ok("p2/req_mapping_equiv",
           any(f.get("dst", [None, None, None])[2] == "C1-AC13" and "无定义块" in f.get("缺", "")
               for f in mp.get("findings", [])),
           "等价保绿：required_edges 驱动的 CHK-2映射缺口 == 旧写死（R2-AC1→C1-AC13 靶无定义块）")
        ok("p2/missing_edge_slot_empty", cf.get("缺必需边", {}).get("findings") == [],
           "缺必需边 统一位维持空占位：跨类型违反经 CHK-2 就地承载，不双路重复上报")
        # EG-20-AC5：语料出现但无规则覆盖的 kind 进未覆盖告警；规则点名的 kind 不误报
        uk = [f["kind"] for f in cf.get("未覆盖kind", {}).get("findings", [])]
        ok("p2/uncovered_kind_reports", "审计AC" in uk and "参数" in uk,
           "EG-20-AC5：未被任何规则覆盖的 kind（审计AC/参数）进未覆盖告警（反假绿）")
        ok("p2/uncovered_kind_excludes_covered",
           not ({"需求AC", "契约AC", "测试", "任务"} & set(uk)),
           "EG-20-AC5：规则已点名的 kind（需求AC/契约AC/测试/任务）不误报未覆盖")

        # EG-20-AC2 休眠：通用语料无 required_edges → CHK-2 报「无规则声明」而非假绿 pass、gate 不误触
        _, gf, _ = run_json("check", corpus=GENERIC)
        gcov = gf.get("CHK-2覆盖缺口", {})
        ok("p2/req_dormant_no_falsegreen",
           gcov.get("findings") == [] and gcov.get("result") is None and "说明" in gcov
           and gcov.get("judgment_status") == "dormant",
           "EG-20-AC2 休眠：无 required_edges → 覆盖检查 result=None+judgment_status=dormant+说明「无规则声明」，非假绿 pass（DG-63 第四态）")
        gc, _, _ = run("check", "--gate", "CHK-2覆盖缺口", corpus=GENERIC)
        ok("p2/req_dormant_gate_zero", gc == 0,
           "EG-20-AC2 休眠：--gate 命中休眠检查 → 退 0（无政策不误触门禁）")

        # DG-50 检查 kind 域下沉：CHK-3/共现完备 域未声明 → 显式休眠而非假绿（沿 DG-47 先例）
        gtr, gco = gf.get("CHK-3传导断裂", {}), gf.get("共现完备性", {})
        ok("dg50/dormant_transduction",
           gtr.get("findings") == [] and gtr.get("result") is None
           and gtr.get("judgment_status") == "dormant"
           and "revision_target_kinds" in gtr.get("说明", ""),
           "DG-50 休眠：无 revision_target_kinds → CHK-3 result=None+judgment_status=dormant+说明「无声明」，非假绿 pass（DG-63）")
        ok("dg50/dormant_cooccur",
           gco.get("findings") == [] and gco.get("result") is None
           and gco.get("judgment_status") == "dormant"
           and "cooccur_mapping_kinds" in gco.get("说明", ""),
           "DG-50 休眠：无 cooccur_mapping_kinds → 共现完备 result=None+judgment_status=dormant+说明「无声明」，非假绿 pass（DG-63）")

        # EG-20-AC3 就地绑 kind 防假绿：规则只点名「需求」→「Requirements」写法静默无检、未覆盖告警捕获
        _, rf, _ = run_json("check", corpus=REQEDGE)
        rcov = [f.get("key", [None])[0] for f in rf.get("CHK-2覆盖缺口", {}).get("findings", [])]
        ruk = [f["kind"] for f in rf.get("未覆盖kind", {}).get("findings", [])]
        ok("p2/kind_binding_checks_named", "需求" in rcov and "Requirements" not in rcov,
           "EG-20-AC3：规则点名「需求」→ 受检；未点名的「Requirements」静默无检（精确匹配 kind 的假绿危险）")
        ok("p2/kind_binding_warn_catches", "Requirements" in ruk,
           "EG-20-AC3/AC5：未覆盖告警捕获落网外的「Requirements」写法（改 kind 写法漏检 → 显式化）")
        rc_gate, _, _ = run("check", "--gate", "CHK-2覆盖缺口", corpus=REQEDGE)
        ok("p2/req_gate_nonzero", rc_gate == 1,
           "EG-20-AC2/AC4：声明规则后确定性执行 → --gate 命中缺口退非零（CI 退出码）")
        ok("dg50/policy_keys_independent",
           rf.get("CHK-2覆盖缺口", {}).get("findings") and "说明" in rf.get("CHK-3传导断裂", {}),
           "DG-50：声明 required_edges 不点亮 CHK-3 域——required_edges/revision_target_kinds 独立休眠/点亮")

    # ===== EG-24 值漂移探测（DG-48）=====
    dc, dd, _ = run_json("drift", corpus=DRIFT)
    drifts = {d["name"]: d for d in dd.get("drifts", [])} if isinstance(dd, dict) else {}
    ok("p2/drift_lists_diff",
       dc == 0 and "协议版本" in drifts and drifts["协议版本"]["distinct_values"] == ["v1.2", "v1.3"],
       "EG-24-AC1：漂移差异表列受管值多处不一致（协议版本 v1.2/v1.3）")
    ok("p2/drift_occurrence_anchors",
       "协议版本" in drifts and all({"源文件", "行", "值", "原文"} <= set(o)
                                    for o in drifts["协议版本"]["occurrences"]),
       "EG-24-AC1：每出现点携坐标（源文件:行）+ 值 + 原文")
    ok("p2/drift_codemask",
       "协议版本" in drifts and not ({"v9.9", "v8.8"} & set(drifts["协议版本"]["distinct_values"])),
       "EG-24：代码遮罩——围栏/行内示例值不当真漂移（v9.9/v8.8 排除，DG-41）")
    ok("p2/drift_consistent_single_silent",
       dc == 0 and "重试上限" not in drifts and "唯一常量" not in drifts,
       "EG-24-AC1：一致值（重试上限）/单处值（唯一常量）不报（只列真差异）")
    ok("p2/drift_only_lists_no_judge",
       "协议版本" in drifts and "expected" not in json.dumps(dd, ensure_ascii=False),
       "EG-24-AC1：只列不判——无 expected/对错标注（哪个对归写作判断，G7 零语义）")
    ok("p2/drift_manifest",
       isinstance(dd, dict) and "conventions_hash" in dd.get("context_manifest", {}),
       "EG-24-AC2：drift 输出挂 context_manifest（携 conventions_hash，防不可见第二事实源）")

    # ===== EG-25 迁移验证模式（DG-49）：temp git 仓演练移动，禁对本仓 git 写 =====
    with tempfile.TemporaryDirectory() as tmp:
        def git_(*a):
            return subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True)
        git_("init", "-q"); git_("config", "user.email", "t@t.co"); git_("config", "user.name", "t")
        Path(tmp, "tasks.md").write_text(
            "# 任务表\n\n| # | 目标 | spec 锚 | 前置 | 红先测试 |\n|---|---|---|---|---|\n"
            "| **TASK-1** | 实现 | 设计 §2 | | |\n", encoding="utf-8")
        Path(tmp, "设计.md").write_text("# 设计\n\n## 2 架构分层\n\n分层说明。\n", encoding="utf-8")
        git_("add", "-A"); git_("commit", "-qm", "base")
        base = git_("rev-parse", "HEAD").stdout.strip()
        git_("mv", "设计.md", "架构.md")           # 改名使 节条目 stem 变 → 阅读依赖 悬空断裂
        mc, md, _ = run_json("verify", "--migrate", "--baseline", base, corpus=tmp)
        moved = md.get("moved_files", []) if isinstance(md, dict) else []
        broken = md.get("broken_edges", []) if isinstance(md, dict) else []
        ok("p2/migrate_moved_files",
           mc == 0 and any(m.get("从") == "设计.md" and m.get("到") == "架构.md" for m in moved),
           "EG-25-AC1：verify --migrate 识别重命名（设计.md→架构.md，git -M 检测）")
        ok("p2/migrate_broken_edges",
           any(b.get("边类型") == "阅读依赖" and b.get("dst", [None, None, None])[2] == "设计§2"
               and "dst移动" in b.get("断因", "") for b in broken),
           "EG-25-AC1：断边清单列因移动悬空的边（阅读依赖 TASK-1→设计§2，断因=dst移动）")
        ok("p2/migrate_broken_traceable",
           bool(broken) and all({"边类型", "src", "dst", "断因", "prov"} <= set(b) for b in broken),
           "EG-25-AC1：每条断边可溯源（边类型/src/dst/断因/prov）")
        ok("p2/migrate_manifest_baseline",
           isinstance(md, dict) and md.get("baseline") == base and "context_manifest" in md,
           "EG-25-AC1：manifest 携基线戳（baseline=移动前 rev）")
        git_("commit", "-qam", "moved")            # 无未提交移动 → 空 diff
        nc, nd, _ = run_json("verify", "--migrate", "--baseline", "HEAD", corpus=tmp)
        ok("p2/migrate_no_move_empty",
           nc == 0 and isinstance(nd, dict) and nd.get("moved_files") == [] and nd.get("broken_edges") == [],
           "EG-25-AC1：无移动批次 → 空 diff（moved_files/broken_edges 皆空）")


# ================= 同文档自引 § 断锚分区（DG-51/EG-20-AC1 r17 注；fixtures/selfsec） =================

def a_selfsec():
    """DG-51：同文档自引 § 检锚域三形（自指词精确/自指词后缀/具名自引）断则报「节引用断锚」；
    裸 § 与非自指前缀词=已声明边界不检；跨文档断锚回归不变。断言自 EG-20-AC1 r17 注与 DG-51 验收条
    独立推导（DG-6 不读实现）。"""
    layer("logic")
    code, R, err = run_json("check", corpus=SELFSEC)
    if not isinstance(R, dict):
        ok("selfsec/check_runs", False, f"check --json 未产出对象（code={code} err={err.strip()[:120]}）")
        return
    an = R.get("节引用断锚", [])
    def hits(target):
        return [x for x in an if x.get("目标") == target]
    h1 = hits("a.md §66.6")
    ok("selfsec/exact_self_broken",
       len(h1) == 1 and h1[0].get("规则") == "section_ref_self" and h1[0].get("源文件") == "a.md"
       and isinstance(h1[0].get("行"), int) and "上文" in h1[0].get("原文", ""),
       "自指词精确形（上文 §66.6，无此节）→ 断锚条目携溯源（源文件/行/原文/规则=section_ref_self）")
    h2 = hits("a.md §88.8")
    ok("selfsec/suffix_self_broken",
       len(h2) == 1 and h2[0].get("规则") == "section_ref_self" and "见本文" in h2[0].get("原文", ""),
       "自指词后缀形（「…补充见本文 §88.8」连写长前缀，INJ5 原文形）→ 断锚条目")
    h3 = hits("a.md §5.5")
    ok("selfsec/named_self_broken",
       len(h3) == 1 and h3[0].get("规则") == "section_ref_self",
       "具名自引形（a §5.5 写在 a.md 内，无此节）→ 断锚条目")
    ok("selfsec/valid_self_silent",
       not any(x.get("目标") in ("a.md §2", "a.md §1") for x in an),
       "锚点存在的自引（本文 §2 / a §1）不产断锚条目")
    ok("selfsec/verb_prefix_boundary",
       not any("77.7" in x.get("目标", "") for x in an),
       "非自指前缀词（详见 §77.7）无归属证据=已声明边界，不检")
    ok("selfsec/bare_ref_boundary",
       not any("55.5" in x.get("目标", "") for x in an),
       "裸 §（§55.5）无归属证据=已声明边界，不检")
    h4 = hits("b.md §9.9")
    ok("selfsec/cross_doc_regression",
       len(h4) == 1 and h4[0].get("规则") == "section_ref" and h4[0].get("诊断型") == "断锚",
       "跨文档断锚（b §9.9）回归不变（规则=section_ref 与自引区分）")
    ok("selfsec/all_anchor_diag_type",
       an and all(x.get("诊断型") == "断锚" for x in an),
       "自引条目并入既有「节引用断锚」键、诊断型=断锚（DG-42 四分型不增型）")
    top_words = [w for w, _c in R.get("节引用前缀未解析TOP", [])]
    ok("selfsec/suffix_not_in_unresolved",
       not any(w.endswith("本文") for w in top_words),
       f"后缀形长前缀不再沉入「节引用前缀未解析TOP」（修复前该形计入 unresolved 被 TOP15 截断不可见）；TOP={top_words}")
    # self_ref_words=[] 关闭范围：只关词表两形（精确/后缀），具名自引不经词表恒检（DG-51/r17 注）
    import copy as _copy
    import tempfile
    from conventions import default as _convdef
    raw = _copy.deepcopy(_convdef.DEFAULT)
    raw["edges"]["self_ref_words"] = []
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "conventions.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        _c2, R2, _e2 = run_json("check", "--conventions", td, corpus=SELFSEC)
        an2 = (R2 or {}).get("节引用断锚", [])
        tg2 = {x.get("目标") for x in an2}
        ok("selfsec/srw_empty_scope",
           "a.md §66.6" not in tg2 and "a.md §88.8" not in tg2
           and "a.md §5.5" in tg2 and "b.md §9.9" in tg2,
           "self_ref_words=[] 只关词表两形（66.6/88.8 消失）；具名自引（a §5.5）与跨文档（b §9.9）恒检")


# ================= doc 名称解析同 stem 多命中分区（SKILL.md 名称解析合同；fixtures/dupstem） =================

def a_dupstem():
    """SKILL.md 名称解析合同：multiple hits → 列候选并 exit 1，不得静默取一。回归背景：resolve_name
    曾以 stem→rel 单值 dict 建索引，同 stem 键覆盖只剩最后一篇——exact/前缀/包含三分支全体漏报，
    doc README 在三同名文件下静默返回其一且 exit 0（比查不到更险）。语料 fixtures/dupstem：
    alpha/README.md 与 beta/README.md 同 stem，guide.md 唯一对照。"""
    layer("logic")
    code, _, err = run("doc", "README", corpus=DUPSTEM)
    ok("dupstem/exact_multi_exit1",
       code == 1 and "alpha/README.md" in err and "beta/README.md" in err,
       "exact stem 双命中 → stderr 列全两候选 + exit 1（不静默取 dict 末位）")
    code2, _, err2 = run("doc", "READ", corpus=DUPSTEM)
    ok("dupstem/prefix_multi_exit1",
       code2 == 1 and "alpha/README.md" in err2 and "beta/README.md" in err2,
       "stem 前缀双命中 → 同列全候选 + exit 1（前缀/包含分支同源修复）")
    code3, out3, _ = run("doc", "guide", corpus=DUPSTEM)
    ok("dupstem/unique_single_ok",
       code3 == 0 and "guide.md" in out3,
       "唯一 stem 单命中照常 exit 0（修复不伤单命中路径）")

    # DG-57/EG-28：§ 引用同目录消歧（接入 corpus.same_dir_pick）+ 路径限定引用
    # （正文 §/wiki 链接/CLI doc·id）。素材见 alpha/notes.md、guide.md 追加行、
    # alpha/mod-{a,b}.md、alpha|beta/sub/README.md（新增于 fixtures/dupstem）。
    c_sd, d_sd, _ = run_json("id", "alpha/README §1", corpus=DUPSTEM)
    occ_sd = [o["doc"] for o in (d_sd or {}).get("引用处", [])] if d_sd else []
    ok("dupstem/samedir_secref_resolves",
       c_sd == 0 and bool(d_sd) and bool(d_sd.get("目标锚点")) and "alpha/notes.md" in occ_sd,
       "同目录裸前缀引用 README §1（源 alpha/notes.md）经 same_dir_pick 恰一消歧解析到 "
       "alpha/README.md：exit 0、目标锚点非空、引用处含 alpha/notes.md（EG-28-AC1）")
    c_chk, chk, _ = run_json("check", corpus=DUPSTEM)
    top_chk = [w for w, _c in (chk or {}).get("节引用前缀未解析TOP", [])] if chk else []
    ok("dupstem/crossdir_secref_unresolved",
       "guide.md" not in occ_sd and "README" in top_chk,
       "跨目录同形引用（guide.md 的 README §1，其所在目录无同名候选可消歧）不误并入同目录解析——"
       "alpha/README §1 引用处不含 guide.md，且 README 仍列节引用前缀未解析TOP（EG-28-AC1 边界）")
    ok("dupstem/samedir_two_candidates_unresolved",
       "mod" in top_chk,
       "同目录双候选（alpha/mod-a.md、alpha/mod-b.md）不静默取一——mod §1（源 alpha/notes.md）"
       "维持未解析，mod 列节引用前缀未解析TOP（EG-28-AC1：same_dir_pick 须恰一命中才消歧）")
    c_pq, d_pq, _ = run_json("id", "beta/README §2", corpus=DUPSTEM)
    occ_pq = [o["doc"] for o in (d_pq or {}).get("引用处", [])] if d_pq else []
    ok("dupstem/pathq_secref_crossdir",
       c_pq == 0 and "guide.md" in occ_pq,
       "路径限定引用 beta/README §2（源 guide.md，跨目录）段对齐后缀恰一命中 beta/README.md："
       "exit 0、引用处含 guide.md（EG-28-AC2）")
    c_da, out_da, _ = run("doc", "alpha/README", corpus=DUPSTEM)
    c_db, out_db, _ = run("doc", "beta/README", corpus=DUPSTEM)
    ok("dupstem/pathq_doc_ok",
       c_da == 0 and "alpha/README.md" in out_da and c_db == 0,
       "CLI doc 路径限定名段对齐后缀恰一命中：doc alpha/README exit 0 输出含 alpha/README.md，"
       "doc beta/README exit 0（EG-28-AC2）")
    c_sub, _, err_sub = run("doc", "sub/README", corpus=DUPSTEM)
    ok("dupstem/pathq_multi_lists",
       c_sub == 1 and "alpha/sub/README.md" in err_sub and "beta/sub/README.md" in err_sub,
       "路径限定名 sub/README 段对齐后缀双命中（alpha/sub/README.md、beta/sub/README.md）→ "
       "同既有名称解析合同列全候选 exit 1，不静默取一（EG-28-AC2）")
    c_wl, d_wl, _ = run_json("doc", "beta/README", corpus=DUPSTEM)
    ok("dupstem/pathq_wikilink_resolves",
       c_wl == 0 and bool(d_wl) and "alpha/notes.md" in (d_wl.get("被正文引用") or {}),
       "wiki 链接 [[beta/README]]（源 alpha/notes.md）路径段对齐恰一建边到 beta/README.md："
       "doc beta/README 的 被正文引用 含 alpha/notes.md（EG-28-AC2）")
    c_im, _, err_im = run("id", "README §1", corpus=DUPSTEM)
    ok("dupstem/pathq_id_multi_lists",
       c_im == 1 and "alpha/README.md" in err_im and "beta/README.md" in err_im
       and "alpha/sub/README.md" in err_im and "beta/sub/README.md" in err_im,
       "id §查询名多命中 → 同 doc 列全候选 exit 1（原只报命中数；DG-57 对齐列候选合同，EG-28-AC3）")


def a_methodology():
    """Methodology 兼容预设（EG-26/DG-53 e2e）：语料全程零 `性质` 键，nature_source（类型→性质映射）
    独力点亮分类；规格链政策 CHK-2 精确抓故意未覆盖的 R2-AC1。语料 fixtures/methodology/corpus，
    预设即 fixture 自带 conventions（自动发现），兼作用户可拷贝样例（fixtures/methodology/README.md）。
    决议记录.md `类型: 决议记录（例会）` 证 nature_source.normalize=bracket-base 剥括注归一（DG-56/EG-27）。"""
    layer("logic")
    code, out, _ = run("dump", corpus=METH, as_json=True)
    if code != 0:
        ok("meth/dump_runs", False, f"dump 应 exit 0，实为 {code}")
        return
    d = JC.to_internal(json.loads(out))
    ok("meth/mapping_lights_classification",
       d.get("classification_complete") is True and d.get("unknown_documents") == [],
       "全语料零显式 `性质` 键，仅靠 nature_source 映射 → 分类完备、无 unknown（EG-26-AC2）")
    ents = {e["display"]: e for e in d["entities"]}
    ok("meth/norm_via_map",
       ents.get("NFR1", {}).get("性质") == "规范" and ents.get("R2-AC1", {}).get("性质") == "规范"
       and ents.get("T1.1", {}).get("性质") == "规范",
       "需求池（需求文档→规范）与任务卡（任务文档→规范，随规格链声明职责定性）实体性质=规范")
    ok("meth/desc_via_map",
       ents.get("交接-M1§1", {}).get("性质") == "记述",
       "交接（类型:交接 handoff→记述）节条目性质=记述（映射记述侧例证）")
    ok("meth/normalize_bracket_base",
       "决议记录.md" not in d.get("unknown_documents", [])
       and ents.get("决议记录§1", {}).get("性质") == "规范",
       "复合值 决议记录（例会）经 bracket-base 剥附注回落基值（EG-27-AC1）")
    code2, out2, _ = run("check", corpus=METH, as_json=True)
    c = JC.to_internal(json.loads(out2))
    cov = c.get("CHK-2覆盖缺口", {})
    cov_items = cov.get("findings", cov) if isinstance(cov, dict) else cov
    # 2026-07-17 收窄（表头 conv 化 DG-54 落地）：任务表列名下沉 conv.task_columns、预设声明「规格锚」
    # 等列名 → 任务声明边点亮；同批裁决预设映射改 任务文档→规范——记述源边被判定域过滤（DG-23），
    # 任务文档→记述 下规格链规则恒不可满足；未立项 T1.2 视为已派卡（覆盖=派发存在，非完成）。
    # 三项集合期（性质随 primary 揭黏连假绿、表头未 conv 化）为过渡态；其预登记收窄目标
    # {R1-AC2, R2-AC1} 含两条未实测假设（记述源边计入判定域、未立项不计——引擎无状态感知），
    # 实测皆不成立，废，回 0fff4d6 单项原意。
    ok("meth/chk2_exact_uncovered",
       isinstance(cov_items, list) and len(cov_items) == 1 and cov_items[0].get("display") == "R2-AC1",
       "规格链政策：故意未派卡的 R2-AC1 恰被 CHK-2 检出、且仅它（不假红不漏报）")
    for key, want in (("fm_断链", 0), ("正文死链", 0), ("单向边_我列它为上游_它未列我为下游", 0),
                      ("缺frontmatter", 0), ("fm_无链接条目", 0)):
        v = c.get(key, None)
        items = v.get("findings", v) if isinstance(v, dict) else v
        n = len(items) if isinstance(items, list) else -1
        ok(f"meth/clean_{key}", n == want, f"{key} 应 {want} 项（语料按元信息块纪律写作），实为 {n}")
    # fm_无链接条目 归零非无纯文字上下游条目——预设声明 edges.nonlink_prefixes 后，语料原有三条
    # （ROADMAP 链根、交接 下一会话、决议记录 各执行文档）打标改入声明桶 fm_有意非链接条目（EG-29-AC1）。
    nonlink_decl = c.get("fm_有意非链接条目", [])
    ok("meth/nonlink_declared",
       len(nonlink_decl) == 3 and {x["doc"] for x in nonlink_decl} == {"ROADMAP.md", "交接-M1.md", "决议记录.md"},
       "预设声明 nonlink_prefixes 后，3 条 by-design 上下游条目入声明桶且仅这 3 篇（EG-29-AC1）")
    code3, _, _ = run("check", "--gate", "CHK-2覆盖缺口", corpus=METH)
    ok("meth/gate_hits", code3 == 1, "--gate CHK-2覆盖缺口 命中 → exit 1（可接 CI）")


# ================= 有意非链接声明分桶（EG-29/DG-58；fixtures/nonlink） =================

def a_nonlink():
    """有意非链接声明分桶：conv.nonlink_prefixes 前缀词表标记 frontmatter 方向键纯文字条目的合法
    非链接形态（链根/仓外产物/口头裁决等），check 报告层与真漏链分桶（entry 级、不生边、不动实体层）。
    语料 fixtures/nonlink：同一上游键三条目——「外部：」标记纯文字、未标记纯文字、标记且含断链链接。"""
    layer("logic")
    _, c, _ = run_json("check", corpus=NONLINK)
    c = c or {}
    ok("nonlink/marked_declared",
       c.get("fm_有意非链接条目") == [{"doc": "外部依赖.md", "entry": "外部：白皮书 PDF（仓外）"}],
       "标记条目入声明桶，entry 级分流（EG-29-AC1）")
    ok("nonlink/unmarked_finding",
       c.get("fm_无链接条目") == [{"doc": "外部依赖.md", "entry": "负责人指令（2026-07-17 会话）"}],
       "未标记条目仍入疑漏链桶（EG-29-AC2）")
    ok("nonlink/marked_link_still_brokenlink",
       c.get("fm_断链") == [{"doc": "外部依赖.md", "raw": "不存在.md", "entry": "外部：断链的 [白皮书](不存在.md)"}],
       "标记且含链接的条目不经词表：照常解析、断链仍报 fm_断链（EG-29-AC1 末句；两分桶全值断言反证不含它）")
    _, c2, _ = run_json("check")   # 默认 corpus=fixtures/corpus，词表缺席
    c2 = c2 or {}
    ok("nonlink/absent_all_counted",
       len(c2.get("fm_无链接条目", [])) == 10 and c2.get("fm_有意非链接条目") == [],
       "词表缺席回落全计：fixtures/corpus 10 条 `[]` 字面量条目如旧入疑漏链桶，声明桶键恒在但空（EG-29-AC3）")


# ================= 实体性质随 primary 分区（EG-11-AC1 判定参与语义；fixtures/naturestick） =================

def a_naturestick():
    """实体「性质」取 primary 定义文档/节的性质，非首现文档（2026-07-17 裁决①：缺陷）。回归背景：
    性质在实体创建时黏首现行（id_occ 按 (rel,line) 字典序），primary 选定后不回写——记述文档
    字典序靠前时（'A'<'R'），其引用把规范实体性质拉成记述，实体被漏出 brief 闭包（EG-13-AC3）
    与 check 判定域（DG-23），方向=漏义务，违反 EG-11-AC2 保守侧。语料 fixtures/naturestick：
    A记录.md（记述，扫描序先）正文引 R1-AC1 与悬空 R9-AC9；REQUIREMENTS.md（规范）定义 R1/R2-AC1。"""
    layer("logic")
    c, d, _ = run_json("dump", corpus=NATURESTICK)
    ok("naturestick/dump_ok", c == 0 and d is not None, "naturestick 语料 dump 正常退出且出 JSON")
    if d is None:
        return
    e1 = find_entity(d, key=("需求AC", "REQUIREMENTS", "R1-AC1"))
    ok("naturestick/primary_nature_wins",
       e1 is not None and e1["性质"] == "规范" and e1["primary"]["doc"] == "REQUIREMENTS.md",
       "R1-AC1 性质=规范（随 primary=REQUIREMENTS.md，不黏首现记述引用）")
    e2 = find_entity(d, key=("需求AC", "REQUIREMENTS", "R2-AC1"))
    ok("naturestick/control_untouched",
       e2 is not None and e2["性质"] == "规范" and e2["primary"]["doc"] == "REQUIREMENTS.md",
       "R2-AC1 对照组性质=规范（无更早引用，修复不伤健康路径）")
    e9 = find_entity(d, key=("需求AC", "REQUIREMENTS", "R9-AC9"))
    ok("naturestick/dangling_unknown",
       e9 is not None and e9["primary"] is None and e9["性质"] == "unknown",
       "R9-AC9 悬空占位（无定义块）性质=unknown（无 primary 可依，保守进域，非黏首现记述）")
    # 悬空 subject 的 brief 判定传导：无定义块任务=unknown → authoritative=False → broken
    # （修前性质黏首现碰巧=规范给出 structurally_complete 假绿；fixtures/corpus TA9=活例）
    cb, db, _ = run_json("brief", "TA9", "--mode", "execute")
    ok("naturestick/dangling_subject_broken",
       cb == 0 and db is not None and db.get("judgment_status") == "broken",
       "悬空 subject（TA9 无定义块=unknown）brief 判定=broken，不再冒充 structurally_complete")


# ================= 归档子树语料级过滤分区（EG-30/DG-59；fixtures/archived） =================

def a_archived():
    """archive_globs 声明生效后 Archive/ 子树（任意深度）默认不入语料——不建节点/不发边/不进 classify
    分母/不产 findings；--include-archived 取证开关停用过滤、命中件全量入图、全语义参与零降级（位置⊥
    性质裁决不变）。亦覆盖 cmd_check 单向边推导式 dst-in-g.docs 守卫的 KeyError 回归面（live-a 上游+
    正文皆链向 Archive/frozen.md，守卫加入前默认排除态下会直接崩溃，EG-30-AC2）。语料 fixtures/archived。"""
    layer("logic")
    ZERO_KEYS = ("fm_断链", "正文死链",
                "单向边_我列它为下游_它未列我为上游", "单向边_我列它为上游_它未列我为下游")

    # 1. 默认分母：Archive/ 子树整体排除（不建节点/不进 classify 分母）
    c1, d1, _ = run_json("classify", "--pending", corpus=ARCHIVED)
    p1 = d1 or {}
    pending1 = [p["path"] for p in p1.get("pending", [])]
    ok("arch/default_denominator",
       c1 == 0 and d1 is not None and p1.get("total_documents") == 2
       and not any("Archive" in p for p in pending1),
       f"默认排除 Archive/ 后 total_documents==2 且 pending 不含 Archive 路径，"
       f"实为 total_documents={p1.get('total_documents')}、pending={pending1}")

    # 2. 默认 check：不崩、四键皆 0 项（图外目标不产 finding，AC2）
    c2, d2, _ = run_json("check", corpus=ARCHIVED)
    p2 = d2 or {}
    zero_counts = {k: len(p2.get(k, [])) for k in ZERO_KEYS}
    ok("arch/default_check_no_crash",
       c2 in (0, 1) and d2 is not None and all(n == 0 for n in zero_counts.values()),
       f"默认 check 正常退出（0/1）且四键皆 0 项，实为 exit={c2}、{zero_counts}")

    # 3. dump：实体/边源不含 Archive/（本语料无 def_forms，恒空即形状层面守护）
    c3, d3, _ = run_json("dump", corpus=ARCHIVED)
    p3 = d3 or {}
    ent_bad = [e["key"] for e in p3.get("entities", [])
              if "Archive" in ((e.get("primary") or {}).get("doc") or "")
              or any("Archive" in (c.get("doc") or "") for c in e.get("candidates", []))]
    edge_bad = [e["type"] for e in p3.get("edges", []) if "Archive" in e["prov"]["file"]]
    ok("arch/default_dump_excludes",
       c3 == 0 and d3 is not None and not ent_bad and not edge_bad,
       f"dump 实体/边源不含 Archive/，实为实体 {ent_bad}、边 {edge_bad}")

    # 3b. id 索引两侧（AC1「id 索引不含其出现」）：AR1 登记原件在归档件、活文档另有出现——
    #     默认态 id 索引仅见活文档出现；--include-archived 后归档件出现回归（跨 2 篇）
    ci0, di0, _ = run_json("id", "AR1", corpus=ARCHIVED)
    ci1, di1, _ = run_json("id", "AR1", "--include-archived", corpus=ARCHIVED)
    docs0 = set((di0 or {}).get("docs", {}))
    docs1 = set((di1 or {}).get("docs", {}))
    ok("arch/id_index_two_sided",
       ci0 == 0 and ci1 == 0 and docs0 == {"live-a.md"}
       and docs1 == {"live-a.md", "Archive/frozen.md"},
       f"id AR1 默认仅 live-a.md、--include-archived 后含 Archive/frozen.md，"
       f"实为默认={sorted(docs0)}、取证={sorted(docs1)}")

    # 4. --include-archived 分母：5 篇，pending 含两个无 FM 归档件（无 FM→pending）
    c4, d4, _ = run_json("classify", "--pending", "--include-archived", corpus=ARCHIVED)
    p4 = d4 or {}
    pend4 = {p["path"] for p in p4.get("pending", [])}
    ok("arch/included_denominator",
       c4 == 0 and d4 is not None and p4.get("total_documents") == 5
       and {"Archive/nofm.md", "nested/Archive/deep.md"} <= pend4,
       f"--include-archived 后 total_documents==5 且 pending 含两个无 FM 归档件，"
       f"实为 total_documents={p4.get('total_documents')}、pending={sorted(pend4)}")

    # 5. --include-archived check：findings 回归（fm_断链 1、单向边 1）
    c5, d5, _ = run_json("check", "--include-archived", corpus=ARCHIVED)
    p5 = d5 or {}
    fmd5 = p5.get("fm_断链", [])
    onew5 = p5.get("单向边_我列它为上游_它未列我为下游", [])
    ok("arch/included_findings_return",
       c5 in (0, 1) and d5 is not None
       and len(fmd5) == 1 and fmd5[0].get("doc") == "Archive/frozen.md"
       and len(onew5) == 1 and "frozen" in onew5[0],
       f"--include-archived 后 fm_断链 恰 1（frozen.md 自身断链）且 单向边_上游未回列 恰 1（live-a→frozen），"
       f"实为 fm_断链={fmd5}、单向边={onew5}")

    # 6. --gate 组合：默认 exit 0、含档 exit 1（AC3 取证进 gate）
    cg0, _, _ = run("check", "--gate", "fm_断链", corpus=ARCHIVED)
    cg1, _, _ = run("check", "--gate", "fm_断链", "--include-archived", corpus=ARCHIVED)
    ok("arch/gate_composition", cg0 == 0 and cg1 == 1,
       f"--gate fm_断链 默认 exit 0、--include-archived 后 exit 1，实为 {cg0}/{cg1}")

    # 7. manifest 条件字段：默认无键、开关后 true（DG-43 归因；复用 2/5 已取的 JSON）
    m2 = p2.get("context_manifest", {})
    m5 = p5.get("context_manifest", {})
    ok("arch/manifest_conditional",
       "include_archived" not in m2 and m5.get("include_archived") is True,
       f"默认 context_manifest 无 include_archived 键、--include-archived 后 ==true，"
       f"实为默认含键={'include_archived' in m2}、开启值={m5.get('include_archived')}")

    # 8. verify：fixture 为新增未提交文件，GitSource(HEAD) 看不到——只断 exit 码与 JSON 形。
    # 挂 ST["verify"] 交付门（NBL 线 2026-07-17 handback 件①：本断言曾无门耦合 verify 命令，
    # verify 未交付/红域环境下转逻辑红而非待建——测试卫生债，改沿 a_verify 门样板）。
    if not ST["verify"]:
        todo("arch/verify_symmetric", "波7-verify", "arch/verify_symmetric（耦合 verify，交付前待建）")
    else:
        cv, dv, _ = run_json("verify", "--baseline", "HEAD", corpus=ARCHIVED)
        ok("arch/verify_symmetric",
           cv == 0 and isinstance(dv, dict)
           and {"引入实体", "引入边", "引入缺陷", "进图缺失", "context_manifest"} <= set(dv),
           f"verify --baseline HEAD 正常退出且 JSON 形完整（fixture 未入 git 历史，只断形状），实为 exit={cv}")

    # 9-11. html 数据合同（DG-61；NBL 适配方案 §11 遗留5 handback：默认态曾发射图外端点边→
    # 页内 JS 解引用 TypeError 白屏。页面 JS 零自动化覆盖——模板已加端点防御跳过[console 计数]，
    # 本组数据合同断言为该缺口的网底）。
    import re as _re
    import shutil
    import tempfile

    def _html_data(path):
        m = _re.search(r"const DATA\s*=\s*(\{.*?\});?\s*\n",
                       Path(path).read_text(encoding="utf-8"), _re.S)
        return json.loads(m.group(1)) if m else None

    with tempfile.TemporaryDirectory() as td:
        # HTML 文件是用户产物：省略输出路径时必须落在调用者 cwd，而不是工具安装目录。
        # 同时锁定位置参数的相对/绝对语义，保证 Codex 的只读 skill/plugin 缓存也可运行。
        sandbox = Path(td) / "html-output"
        sandbox.mkdir()

        def _run_from_cwd(*args):
            p = subprocess.run(
                [sys.executable, str(DOCSTAR), *args, "--corpus", GENERIC],
                cwd=sandbox, capture_output=True, text=True,
            )
            return p.returncode

        absolute_html = Path(td) / "absolute-graph.html"
        absolute_entity = Path(td) / "absolute-entity.html"
        c_html_default = _run_from_cwd("html")
        c_entity_default = _run_from_cwd("html-entity")
        c_html_relative = _run_from_cwd("html", "relative-graph.html")
        c_entity_relative = _run_from_cwd("html-entity", "relative-entity.html")
        c_html_absolute = _run_from_cwd("html", str(absolute_html))
        c_entity_absolute = _run_from_cwd("html-entity", str(absolute_entity))
        ok("html/output_path_sandbox_safe",
           c_html_default == c_entity_default == c_html_relative == c_entity_relative == c_html_absolute == c_entity_absolute == 0
           and (sandbox / "graph.html").is_file()
           and (sandbox / "entity_graph.html").is_file()
           and (sandbox / "relative-graph.html").is_file()
           and (sandbox / "relative-entity.html").is_file()
           and absolute_html.is_file() and absolute_entity.is_file(),
           "html/html-entity 默认输出落 cwd；相对路径随 cwd、绝对路径保持原位")

        h1 = str(Path(td) / "g1.html")
        c9, _, _ = run("html", h1, corpus=ARCHIVED)
        d9 = _html_data(h1) or {"nodes": [], "edges": []}
        ids9 = {n["id"] for n in d9["nodes"]}
        dang9 = [e for e in d9["edges"] if e["s"] not in ids9 or e["t"] not in ids9]
        ok("arch/html_no_dangling_default",
           c9 == 0 and not any("Archive" in i for i in ids9) and dang9 == [],
           f"默认态 html：归档节点不入 DATA 且边零图外端点（修前 2 悬空），实为 nodes={sorted(ids9)} 悬空={len(dang9)}")
        h2 = str(Path(td) / "g2.html")
        c10, _, _ = run("html", h2, "--include-archived", corpus=ARCHIVED)
        d10 = _html_data(h2) or {"nodes": [], "edges": []}
        arcmap = {n["id"]: n.get("arc") for n in d10["nodes"]}
        dang10 = [e for e in d10["edges"] if e["s"] not in arcmap or e["t"] not in arcmap]
        ok("arch/html_forensic_marks",
           c10 == 0 and arcmap.get("Archive/frozen.md") is True
           and arcmap.get("live-a.md") is False and not dang10,
           f"取证态 html：归档节点在场且 arc=True、活文档 False、零悬空，实为 {arcmap}")
        # arc 标记 conv 单源：目录改名 Frozen（非 Archive 子串）仍须被标——锁「非路径巧合」
        froz = Path(td) / "froz"
        shutil.copytree(ARCHIVED, froz)
        (froz / "Archive").rename(froz / "Frozen")
        cj = froz / ".docstar" / "conventions" / "conventions.json"
        cfg = json.loads(cj.read_text(encoding="utf-8"))
        cfg["archive_globs"] = ["Frozen"]
        cj.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        h3 = str(Path(td) / "g3.html")
        c11, _, _ = run("html", h3, "--include-archived", corpus=str(froz))
        am = {n["id"]: n.get("arc") for n in (_html_data(h3) or {"nodes": []})["nodes"]}
        ok("arch/html_arc_conv_source",
           c11 == 0 and am.get("Frozen/frozen.md") is True
           and am.get("nested/Archive/deep.md") is False,
           f"arc 标记以 conv.archive_globs 为源（Frozen 命名亦标=正例；nested/Archive 在 ['Frozen'] "
           f"下不标=负控——旧 '/Archive/' 子串启发式两向皆会答错），实为 {am}")

        # 12. DG-63 dormant 判定第四态抵达页面数据面（critic 轮1-A 消费点；entity_html→
        # entity_template.html 判定瓦片 status 等值比较）：generic 语料五休眠检查经 html-entity
        # 落 DATA.verdicts.tiles，status=="dormant"——dormant 抵达页面数据面=DG-63 显式裁决（计入
        # 非干净通过=有意）；页面 JS 渲染行为（tileCls/bad 计数）不在自动化面（DG-61 边界），
        # 本断言只锁数据合同。
        h4 = str(Path(td) / "g4.html")
        c12, _, _ = run("html-entity", h4, corpus=GENERIC)
        tiles = ((_html_data(h4) or {}).get("verdicts") or {}).get("tiles", [])
        dormant_n = sum(1 for t in tiles if t.get("status") == "dormant")
        ok("arch/html_entity_dormant", c12 == 0 and dormant_n == 5,
           f"generic 语料 html-entity DATA.verdicts.tiles 中 status==dormant 恰 5（DG-63 五休眠检查），"
           f"实为 exit={c12} dormant 数={dormant_n}")


# ================= 层 B：golden 字节比对（只读；绝不 --bless） =================

def golden(name, cmd_args, delivered):
    gp = GOLDEN / f"{name}.json"
    if not delivered:
        rec(f"golden/{name}", "INFO", f"命令未交付，golden/{name} 待交付+控制者波8 --bless", "golden_wait")
        return
    code, out, _ = run(*cmd_args, as_json=True)
    if not gp.exists():
        rec(f"golden/{name}", "INFO", f"golden 未锁定（{gp.name} 缺席；控制者波8 --bless）", "golden_wait")
        return
    try:
        stale = json.loads(gp.read_text(encoding="utf-8")).get("schema_version") != EM.SCHEMA_VERSION
    except (OSError, ValueError):
        stale = True
    if stale:
        rec(f"golden/{name}", "INFO",
            f"{gp.name} 为旧 schema/不可解析，需由维护者用受控脚本重锁 {EM.SCHEMA_VERSION}", "golden_wait")
        return
    if out == gp.read_text(encoding="utf-8"):
        ok(f"golden/{name}", True, f"{gp.name} 逐字节比对（fixture 级）")
    else:
        # 字节不符 = 输出面改动待控制者亲核重 bless（预期红，本 agent 绝不 --bless；真因见台账当期条目）。
        # 独立标 golden_diff（非 TB 逻辑 bug）：与真回归红区分，汇总分列、不并入「逻辑红须 0」门。
        rec(f"golden/{name}", "FAIL",
            f"{gp.name} 字节改动，待控制者亲核重 bless（输出面改动预期红，真因见台账当期条目）", "golden_diff")

def layer_b():
    golden("dump", ["dump"], ST["dump"])
    golden("harvest", ["harvest"], ST["harvest"])
    golden("check", ["check"], ST["check_entity"])
    golden("brief", ["brief", "TA2.3"], ST["brief"])
    # verify golden 显式钉 --baseline HEAD：缺省 baseline=merge-base(HEAD,@{u})随 git upstream 状态漂移
    # （bless 时无 upstream→回退 HEAD 恰好同值=运气绿；upstream 一出现即字节红）。装置须环境无关。
    golden("verify", ["verify", "--baseline", "HEAD"], ST["verify"])
    golden("classify", ["classify", "--pending"], ST["classify"])

# ================= 层 C：慢断言（--skip-slow 可跳） =================

def layer_c():
    if SKIP_SLOW:
        rec("slow/skipped", "INFO", "--skip-slow：跳过真实仓 + 性能断言")
        return
    # 真实仓 harvest 恒可跑（EG-13-AC4 窗口合法态）
    layer("logic")
    rcode, rharv, _ = run_json("harvest", corpus=SELF)
    ok("slow/real_harvest_runs",
       rcode == 0 and isinstance(rharv, dict) and rharv.get("schema_version") == "eg-3",
       "自宿主 harvest 跑通（EG-13-AC4 同源）")
    # EG-21-AC3 自宿主闭环：工具自身文档补 性质 声明后，自宿主 check 不再因自身缺声明 tainted
    # （unknown 污染在自宿主域清零）。断言从 EG-21-AC3 独立推导。
    scode, schk, _ = run_json("check", corpus=SELF)
    if scode in (0, 1) and isinstance(schk, dict):
        cc = schk.get("classification_complete", {})
        cc_ok = isinstance(cc, dict) and cc.get("result") == "pass" and not cc.get("findings")
        tainted = [k for k, v in schk.items()
                   if isinstance(v, dict) and v.get("judgment_status") == "tainted"]
        ok("slow/selfhost_classification_complete", cc_ok,
           "自宿主 check：全自身文档已声明 性质 → classification_complete=pass、unknown_documents 空（EG-21-AC3）")
        ok("slow/selfhost_no_unknown_taint", not tainted,
           f"自宿主 check：无检查因自身 unknown 污染 tainted（tainted={tainted or '无'}，测量装置对自己也干净，接 EG-15-AC10）")
    else:
        ok("slow/selfhost_classification_complete", False, "自宿主 check 应跑通")
        ok("slow/selfhost_no_unknown_taint", False, "自宿主 check 应跑通")
    layer("impl")
    if not ST["dump"]:
        todo("slow/real_dump", "波6-extract", "slow/real_dump")
        todo("slow/perf_dump_median", "波6-extract", "slow/perf_dump_median")
        return
    rcode, rdump, _ = run_json("dump", corpus=SELF)
    ok("slow/real_dump", rcode == 0 and isinstance(rdump, dict) and rdump.get("schema_version") == "eg-3",
       "自宿主 dump 跑通、schema=eg-3")
    ts = []
    for _ in range(5):
        t = time.perf_counter()
        run("dump", corpus=SELF)
        ts.append(time.perf_counter() - t)
    med = statistics.median(ts)
    ok("slow/perf_dump_median", med <= 3.0, f"真实仓 dump 5 次中位 {med:.2f}s ≤3s（EG-7-AC1）")

def a_ledger_conv():
    """DG-52 分区：底账表头行解析=conv.ledger_header 单源（extract 层声明-解析一致性）。
    独立推导自 conventions 声明：默认集 form_headers.ledger 中英兼容（(?:date|日期)/(?:change|变更)）
    → is_ledger_doc 判真的表头形态，行解析须同源识别，修订落账边不因表头语言静默为零。"""
    layer("logic")
    import tempfile
    ZH = ("# Doc A\n\n## 2. Scope\n\nBody.\n\n## 16. Changelog\n\n"
          "| 日期 | 变更 | 理由 |\n|---|---|---|\n"
          "| 2026-07-01 | r2 覆盖 R1-AC1 与 §2 | why |\n")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "docA.md").write_text(ZH, encoding="utf-8")
        _, zh, _ = run_json("dump", corpus=tmp)
        Path(tmp, "docA.md").write_text(
            ZH.replace("| 日期 | 变更 | 理由 |", "| date | change | reason |"), encoding="utf-8")
        _, en, _ = run_json("dump", corpus=tmp)
    zh_edges = edges(zh, "修订落账") if zh else []
    en_edges = edges(en, "修订落账") if en else []
    ok("ledger/zh_control_extracts",
       len(zh_edges) == 2 and bool(find_edge(zh, "修订落账", dst_cid="R1-AC1")),
       "对照：中文表头底账抽 修订落账 2 边（→R1-AC1、→docA§2），既有行为锚")
    ok("ledger/en_header_extracts",
       bool(en) and bool(find_edge(en, "修订落账", dst_cid="R1-AC1")),
       "DG-52：英文表头（form_headers.ledger 声明形）底账同抽 修订落账 边——"
       "is_ledger_doc 判真 ⇒ 行级可解析（声明-解析一致，CHK-3 输入不再静默为空）")
    ok("ledger/zh_en_equal", len(en_edges) == len(zh_edges) == 2,
       "DG-51：同构语料仅表头语言不同 → 边数一致（表头假设单源于 conv.ledger_header）")


# ================= conventions 祖先走查分区（DG-55；语料根空手上行至 git 边界取祖先项目约定，最近者胜） =================

def a_convwalk():
    """DG-55：conventions 自动发现在「语料根一级」与「内置默认」之间增祖先走查层——语料根空手时，
    自父级逐层上行至 git 边界（含边界目录）找项目约定配置，命中即用（conventions_source=project，
    NBL `--corpus` 子目录静默跌默认缺口闭合）、未命中沿用内置默认；.git 文件或目录皆判界（linked
    worktree 形态）；最近者胜、单目录整取不跨层合并；命中后配置非法→同现行 ConventionsError（exit 2，
    不落默认、不续走更远层）。过渡态②（95b364d 先行 commit 的 stderr 告警）随本层落地撤除——T1 断言
    旧告警子串不再出现即为撤除证据（告警覆盖的「祖先有配置∧落默认」组合已不可达，防死分支）。"""
    layer("logic")
    import copy
    import tempfile
    from conventions import default as _convdef
    WARN = "祖先目录存在约定配置未生效"   # 过渡态②旧告警子串（本分区断言其消失，见 T1）
    conv_text = json.dumps(copy.deepcopy(_convdef.DEFAULT), ensure_ascii=False)

    def write_conv(conv_dir):
        d = Path(conv_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "conventions.json").write_text(conv_text, encoding="utf-8")

    def write_conv_raw(conv_dir, raw):
        """自定义内容配置（T6/T7 需层间内容可区分——不同于 write_conv 逐字节复制 DEFAULT）。"""
        d = Path(conv_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "conventions.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def write_doc(doc_path):
        p = Path(doc_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Doc\n\nMinimal probe document.\n", encoding="utf-8")

    def source_of(d):
        return (d or {}).get("context_manifest", {}).get("conventions_source")

    def hash_of(d):
        return (d or {}).get("context_manifest", {}).get("conventions_hash")

    # T1（原告警存在→走查生效，原 T2 显式消警并入）：同一棵树——repo/.git(目录) + repo/.docstar/conventions
    # + repo/sub/doc.md。语料根 sub 空手上行命中 repo 层 → source=project；旧告警已撤（stderr 不含
    # WARN）；自动发现 ≡ 显式 --conventions 指到同一祖先目录（conventions_hash 逐字节相等）。
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / ".git").mkdir(parents=True)
        conv_dir = repo / ".docstar" / "conventions"
        write_conv(conv_dir)
        sub = repo / "sub"
        write_doc(sub / "doc.md")

        code, d, err = run_json("dump", corpus=str(sub))
        ok("convwalk/walk_effective",
           code == 0 and source_of(d) == "project" and WARN not in err,
           "T1：语料根空手、git 边界内祖先存在项目约定 → 走查命中 source=project（DG-55 生效）；"
           "旧过渡告警②已撤（stderr 不含旧子串「祖先目录存在约定配置未生效」）")

        code2, d2, err2 = run_json("dump", "--conventions", str(conv_dir), corpus=str(sub))
        ok("convwalk/walk_equals_explicit",
           code2 == 0 and source_of(d2) == "project" and hash_of(d) == hash_of(d2),
           "T1续（原 T2 显式消警语义并入）：自动发现 ≡ 显式 --conventions 指同一祖先目录"
           "（conventions_hash 逐字节相等）")

    # T3（维持）：全树无 git 边界——parent/.docstar/conventions + parent/sub/x.md → 无边界不采用，落默认
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp) / "parent"
        write_conv(parent / ".docstar" / "conventions")
        sub = parent / "sub"
        write_doc(sub / "x.md")

        code, d, err = run_json("dump", corpus=str(sub))
        ok("convwalk/no_git_boundary_default",
           code == 0 and source_of(d) == "default",
           "T3：祖先链上行到文件系统根仍无 .git → 无边界，不采用边界外配置，落默认")

    # T4（维持）：边界外配置——outer/.docstar/conventions + outer/repo/.git(目录) + repo/sub/x.md → 落默认
    with tempfile.TemporaryDirectory() as tmp:
        outer = Path(tmp) / "outer"
        write_conv(outer / ".docstar" / "conventions")
        repo = outer / "repo"
        (repo / ".git").mkdir(parents=True)
        sub = repo / "sub"
        write_doc(sub / "x.md")

        code, d, err = run_json("dump", corpus=str(sub))
        ok("convwalk/config_outside_boundary_default",
           code == 0 and source_of(d) == "default",
           "T4：项目约定配置落在 git 边界外（outer 层）→ 边界内无候选，落默认")

    # T5（改为走查生效）：.git 为文件也判界（linked worktree 形态）——wt/.git(文件) +
    # wt/.docstar/conventions + wt/sub/x.md（原②仅告警，DG-55 落地后①实际加载）
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        wt.mkdir(parents=True)
        (wt / ".git").write_text("gitdir: /nonexistent\n", encoding="utf-8")
        write_conv(wt / ".docstar" / "conventions")
        sub = wt / "sub"
        write_doc(sub / "x.md")

        code, d, err = run_json("dump", corpus=str(sub))
        ok("convwalk/git_file_worktree_boundary",
           code == 0 and source_of(d) == "project",
           "T5：.git 为文件（linked worktree 形态）同判界；边界目录自身携配置也算祖先命中 → 走查生效 source=project")

    # T6（强化）：语料根自有配置最优先——repo/.git + repo/.docstar/conventions(配置A=DEFAULT) +
    # repo/sub/.docstar/conventions(配置B=DEFAULT 改 req_doc) + repo/sub/x.md。
    # hash 区分层内容（非仅目录选择）：自动发现 == 显式指语料根自身B ≠ 显式指祖先A。
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / ".git").mkdir(parents=True)
        cfg_a = repo / ".docstar" / "conventions"
        write_conv(cfg_a)
        sub = repo / "sub"
        cfg_b = sub / ".docstar" / "conventions"
        raw_b = copy.deepcopy(_convdef.DEFAULT); raw_b["namespaces"]["req_doc"] = "B.md"
        write_conv_raw(cfg_b, raw_b)
        write_doc(sub / "x.md")

        code, d, err = run_json("dump", corpus=str(sub))
        _, db, _ = run_json("dump", "--conventions", str(cfg_b), corpus=str(sub))
        _, da, _ = run_json("dump", "--conventions", str(cfg_a), corpus=str(sub))
        ok("convwalk/own_config_wins",
           code == 0 and source_of(d) == "project",
           "T6：语料根自带项目约定（既有发现契约优先级）→ source=project，未落默认、不采祖先")
        ok("convwalk/own_config_hash_matches_B_not_A",
           hash_of(d) == hash_of(db) and hash_of(d) != hash_of(da),
           "T6 强化：自动发现 hash == 显式指语料根自身配置B、≠ 祖先配置A（内容级证据，非仅目录选择）")

    # T7（新）：最近者胜 e2e——repo/.git + repo/.docstar(配置A) + repo/mid/.docstar(配置B) + 语料 repo/mid/sub
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / ".git").mkdir(parents=True)
        cfg_a = repo / ".docstar" / "conventions"
        write_conv(cfg_a)
        mid = repo / "mid"
        cfg_b = mid / ".docstar" / "conventions"
        raw_b = copy.deepcopy(_convdef.DEFAULT); raw_b["namespaces"]["req_doc"] = "MIDB.md"
        write_conv_raw(cfg_b, raw_b)
        leaf = mid / "sub"
        write_doc(leaf / "x.md")

        code, d, err = run_json("dump", corpus=str(leaf))
        _, db, _ = run_json("dump", "--conventions", str(cfg_b), corpus=str(leaf))
        ok("convwalk/nearest_wins_e2e",
           code == 0 and source_of(d) == "project" and hash_of(d) == hash_of(db),
           "T7（新）：两层祖先（repo 层 A、mid 层 B）皆有配置，语料根=repo/mid/sub → 最近层 B 生效"
           "（hash 等于显式指 B、非 A）")

        _, da, _ = run_json("dump", "--conventions", str(cfg_a), corpus=str(leaf))
        ok("convwalk/explicit_overrides_walk",
           source_of(da) == "project" and hash_of(da) != hash_of(db),
           "T9（critic G3）：同树显式 --conventions 指远层 A → 压过走查最近层 B（显式恒最高，DG-55 优先序回归）")

    # T8（新）：fail-closed——祖先唯一命中层配置非法（缺必填键）→ exit 2，stderr 含诊断
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / ".git").mkdir(parents=True)
        cfg = repo / ".docstar" / "conventions"
        bad_raw = copy.deepcopy(_convdef.DEFAULT)
        del bad_raw["harvest"]
        write_conv_raw(cfg, bad_raw)
        sub = repo / "sub"
        write_doc(sub / "x.md")

        code, _out, err = run("dump", corpus=str(sub))
        ok("convwalk/ancestor_fail_closed",
           code == 2 and "约定配置非法" in err,
           "T8（新）：祖先唯一命中层配置非法（缺必填键 harvest）→ exit 2、stderr 含诊断（不落默认、不续走更远层）")


# ================= 运行与汇总 =================

def main():
    a_schema()
    a_entities()
    a_edges()
    a_terms()
    a_strike()
    a_newedges()
    a_namespace()
    a_nature()
    a_harvest()
    a_check()
    a_check_txt()       # check 文本态渲染忠实性（判定对象计数/说明；critic 审查揪出）
    a_brief()
    a_verify()
    a_classify()
    a_trace()
    a_gate()
    a_verdict_json()    # DG-60 判定对象 __bool__ 不谎报 + emit 全键序列化（跨版本 JSON 吞键回归位）
    a_cli_flags()       # 未知旗标 fail-closed exit 2 + --kind 收编（EG-9 合同；handback 件②）
    a_regression()
    a_wildcard()
    a_typesection()
    a_openkind()
    a_codemask()        # DG-41 代码遮罩（EG-21-AC1）
    a_diagnostics()     # DG-42 诊断四分型 + 溯源（EG-21-AC2）
    a_manifest()        # DG-43 可复现 manifest（EG-22-AC1）
    a_output_naming()   # DG-44 结构态命名全输出面审计（EG-22-AC2）
    a_contract_toplevel()  # EG-32/DG-64 机读契约 drift-lock（每命令 --json 顶层键集锁定）
    a_eg3_bilingual_contract()  # v0.2/eg-3 英文 JSON 合同 + GMGN 中英镜像等价
    a_bilingual_docs()     # 公共文档镜像、命令与写作机器契约等价
    a_dump_kind()       # EG-31/DG-62 dump --kind 投影语义功能锁定（critic 轮1 处置 A-M1/B-M1）
    a_docs()            # EG-31/DG-62 docs 命令功能语义锁定（critic 轮1 处置 A-M1）
    a_wave13_p1()       # 波13-P1 分区（EG-23 上下文编译器；owner=P1 agent）
    a_wave13_p2()       # 波13-P2 分区（EG-20 收缩/EG-24/EG-25；owner=P2 agent）
    a_selfsec()         # DG-51 同文档自引 § 断锚（EG-20-AC1 r17 注；缺陷 D1）
    a_ledger_conv()     # DG-52 分区（底账表头 conv.ledger_header 单源；原自号 DG-51 撞号改号）
    a_dupstem()         # doc 名称解析：同 stem 多命中列候选 exit 1（SKILL.md 合同回归）
    a_methodology()     # EG-26/DG-53 nature_source e2e + Methodology 兼容预设（规格链 CHK-2）
    a_nonlink()         # EG-29/DG-58 有意非链接声明分桶（fixtures/nonlink 微语料 entry 级两桶分流）
    a_naturestick()     # 实体性质随 primary（EG-11-AC1 判定参与语义；2026-07-17 裁决①）
    a_convwalk()        # conventions 祖先走查（DG-55；空手时上行至 git 边界取祖先项目约定，最近者胜）
    a_archived()        # 归档子树语料级过滤（EG-30/DG-59；archive_globs 段匹配+取证开关+KeyError 守卫）
    layer_b()
    layer_c()

    npass = sum(1 for _, s, _, _ in RESULTS if s == "PASS")
    ninfo = sum(1 for _, s, _, _ in RESULTS if s == "INFO")
    todos = [r for r in RESULTS if r[3] == "todo"]
    impl = [r for r in RESULTS if r[3] == "impl"]
    logic = [r for r in RESULTS if r[3] == "logic"]
    golden_diff = [r for r in RESULTS if r[3] == "golden_diff"]   # 输出形改动待控制者重 bless（预期红，非 bug）

    for name, state, msg, tag in RESULTS:
        suffix = f"  [{tag}]" if tag and state == "FAIL" else ""
        print(f"{state}  {name} — {msg}{suffix}")

    print("\n" + "=" * 78)
    print(f"交付态：dump={'✅' if ST['dump'] else '⬜待波6'} "
          f"trace={'✅' if ST['trace'] else '⬜待波6'} "
          f"harvest={'✅' if ST['harvest'] else '⬜'} "
          f"check实体键={'✅' if ST['check_entity'] else '⬜待波7'} "
          f"brief={'✅' if ST['brief'] else '⬜待波7'} "
          f"verify={'✅' if ST['verify'] else '⬜待波7'} "
          f"classify={'✅' if ST['classify'] else '⬜待波7'}")
    print(f"汇总：{npass} 绿 / {len(todos)} 待建(命令未交付) / {len(impl)} 对照红(他人 impl 未达 AC) "
          f"/ {len(logic)} 逻辑红(TB 自有，须 0) / {len(golden_diff)} golden待重锁(输出面改动预期红) / {ninfo} INFO")
    if golden_diff:
        print(f"\n◆ golden 待控制者亲核重 bless（输出面改动预期红，真因见台账当期条目；本 agent 绝不 --bless）：{len(golden_diff)} 项")
        for name, _, msg, _ in golden_diff:
            print(f"  待重锁  {name} — {msg}")
    if logic:
        print(f"\n⚠⚠ 逻辑红（TB 自有 harvest/schema/gate/回归 bug，必须清零）：{len(logic)} 项")
        for name, _, msg, _ in logic:
            print(f"  FAIL  {name} — {msg}")
    if impl:
        print(f"\n⚠ 对照红（断言=规格独立推导 vs 他人 impl 输出不符，冻结前控制者对账）：{len(impl)} 项")
        for name, _, msg, _ in impl:
            print(f"  FAIL  {name} — {msg}")
    if todos:
        print(f"\nTDD 待建（命令未交付，本波预期）：{len(todos)} 项（前 10）")
        for name, _, msg, _ in todos[:10]:
            print(f"  待建  {name}")
    # 默认 fail-closed：任一真实 FAIL（逻辑红、对照红、待建、golden 待重锁）都阻断 CI。
    # INFO 仅表示尚无可比对的 golden，不是测试失败。
    failures = [r for r in RESULTS if r[1] == "FAIL"]
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
