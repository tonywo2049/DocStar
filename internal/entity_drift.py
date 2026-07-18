#!/usr/bin/env python3
"""entity_drift — 值漂移探测（EG-24「值漂移探测」；DG-48）。波13-P2 唯一交付本文件。

`drift` = 扫同一受管值的多处出现，列「出现点 + 值」差异表——**只列差异不判对错**（哪个值对是写作
判断、非引擎能力，G7 零语义），覆盖版本号/计数/状态词/已废术语类。受管值↔属主绑定经 conventions
`managed_values` 可选键声明（缺席即空跑，沿 type_sections/option_rows 休眠先例）：
  {name, owner_kind?(标注用), occ(出现形正则 group(1)=值), scope(doc 角色名|null 全语料)}。

漂移判据（DG-48）：某受管值 distinct_values 长度 >1 即一条漂移（多处不一致）；单处/一致不报。
输出骨架：{"drifts":[{"name", "occurrences":[{源文件,行,值,原文}], "distinct_values":[…]}], …}。
扫描先过代码遮罩（corpus.code_mask，DG-41）：围栏/行内代码里的示例值不当真出现（防假漂移）。

对外恰一接口（docstar.cmd_drift 调）：cmd_drift(g, conv, as_json)。输出挂 context_manifest（DG-43）+
结构态语义（无「语义验收」态词，DG-44）。零模型零 prompt、确定性（稳定排序）。
自验证：python3 entity_drift.py --selftest
"""

from pathlib import Path

import corpus
import entity_model as M
import i18n


def _scope_docs(g, conv, scope):
    """scope=doc 角色名（req_doc/param_registry/task_doc/mapping_doc）→ 限定该角色文档；null→全语料。
    未识别的 scope 串→按路径子串兜底过滤（宽松，供项目自定角色）。返回 rel 列表（稳定排序）。"""
    if not scope:
        return sorted(g.texts)
    role = {
        "req_doc": lambda rel: Path(rel).name == conv.req_doc,
        "param_registry": lambda rel: Path(rel).name == conv.param_registry,
        "task_doc": lambda rel: Path(rel).stem == conv.task_doc_stem,
        "mapping_doc": lambda rel: Path(rel).stem == conv.mapping_doc_stem,
    }.get(scope)
    if role is None:
        return sorted(rel for rel in g.texts if scope in rel)
    return sorted(rel for rel in g.texts if role(rel))


def _occurrences(g, conv, mv):
    """扫受管值 mv 的全部出现点（过代码遮罩）：每处 {源文件,行,值,原文}。group(1)=值。"""
    occ = []
    for rel in _scope_docs(g, conv, mv["scope"]):
        text = g.texts.get(rel)
        if text is None:
            continue
        for i, ln in enumerate(corpus.code_mask(text).split("\n"), 1):   # 遮罩后行仍保行号
            for m in mv["occ"].finditer(ln):
                val = m.group(1) if m.groups() else m.group(0)
                occ.append({"源文件": rel, "行": i, "值": val, "原文": m.group(0).strip()})
    occ.sort(key=lambda o: (o["源文件"], o["行"], o["值"]))
    return occ


def detect(g, conv):
    """→ drifts 列表（distinct_values 长度 >1 的受管值；确定性排序）。纯函数，供 cmd_drift 与自验证复用。"""
    drifts = []
    for mv in conv.managed_values:
        occ = _occurrences(g, conv, mv)
        distinct = sorted({o["值"] for o in occ})
        if len(distinct) > 1:                        # 漂移=多处不一致（DG-48）；单处/一致不报
            row = {"name": mv["name"], "occurrences": occ, "distinct_values": distinct}
            if mv.get("owner_kind"):
                row["owner_kind"] = mv["owner_kind"]  # 标注属主（可空，非判定）
            drifts.append(row)
    drifts.sort(key=lambda d: d["name"])
    return drifts


def cmd_drift(g, conv, as_json):
    """冻结签名（docstar 已 dispatch）：g=当前图，conv=约定集。managed_values 缺席=空跑（休眠）。"""
    drifts = detect(g, conv)
    out = {"schema_version": M.SCHEMA_VERSION, "drifts": drifts}
    # DG-43：corpus_revision='worktree'（工作树扫描稳定符号，沿 verify/dump 先例）；manifest 携 conventions_hash。
    out = {"context_manifest": M.context_manifest(
        "worktree", conv, "drift", body=out,
        include_archived=getattr(g, "include_archived", False)), **out}
    if as_json:
        print(M.emit(out))
    elif i18n.language() == "en":
        print(i18n.render_public(out))
    else:
        _print_text(out)
    return 0


def _print_text(out):
    m = out["context_manifest"]
    print(f"[context_manifest] corpus={m['corpus_revision']} tool={m['tool_version']} "
          f"conv={m['conventions_source']}:{m['conventions_hash']} output={m['output_hash']}")
    drifts = out["drifts"]
    print(f"\n值漂移 {len(drifts)} 条（受管值多处不一致；只列不判，哪个对归写作判断）")
    for d in drifts:
        print(f"\n[{d['name']}]  取值 {d['distinct_values']}")
        for o in d["occurrences"]:
            print(f"  {o['值']:<20} @{o['源文件']}:{o['行']}  「{o['原文']}」")
    if not drifts:
        print("  （无漂移：受管值一致或未声明 managed_values）")


# ==================== 自验证（测量装置先于被测对象：合成已知值核对） ====================

def _selftest():
    import re
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    class _G:                                        # 最小图桩：只需 texts + 角色文档名
        texts = {
            "a.md": "协议版本：v1.2\n重试次数：3\n",
            "b.md": "协议版本：v1.3\n重试次数：3\n```\n协议版本：v9.9\n```\n",   # 围栏内示例=假漂移
            "c.md": "唯一标记：X7\n",
        }

    class _Conv:
        req_doc = "a.md"; param_registry = "p"; task_doc_stem = "t"; mapping_doc_stem = "m"
        managed_values = [
            {"name": "协议版本", "owner_kind": None, "occ": re.compile(r"协议版本[:：]\s*(v[0-9.]+)"),
             "occ_src": "", "scope": None},
            {"name": "重试次数", "owner_kind": None, "occ": re.compile(r"重试次数[:：]\s*(\d+)"),
             "occ_src": "", "scope": None},
            {"name": "唯一标记", "owner_kind": None, "occ": re.compile(r"唯一标记[:：]\s*(\w+)"),
             "occ_src": "", "scope": None},
        ]

    g, conv = _G(), _Conv()
    drifts = detect(g, conv)
    names = [d["name"] for d in drifts]
    check("漂移只列 distinct>1 的受管值（协议版本）", names == ["协议版本"])
    ver = drifts[0]
    check("差异表列出现点+值（v1.2@a / v1.3@b）",
          [(o["值"], o["源文件"]) for o in ver["occurrences"]] == [("v1.2", "a.md"), ("v1.3", "b.md")])
    check("distinct_values 排序去重", ver["distinct_values"] == ["v1.2", "v1.3"])
    check("代码遮罩：围栏内 v9.9 示例不计入（防假漂移，DG-41）",
          "v9.9" not in ver["distinct_values"])
    check("一致值不报（重试次数两处皆 3）", "重试次数" not in names)
    check("单处值不报（唯一标记只 c.md 一次）", "唯一标记" not in names)
    check("只列不判：无 expected/对错字段", all("expected" not in d and "对" not in d for d in drifts))

    # scope=req_doc 限定（只扫 a.md）→ 协议版本仅 v1.2 一处 → 不漂移
    conv2 = _Conv()
    conv2.managed_values = [{"name": "协议版本", "owner_kind": None,
                             "occ": re.compile(r"协议版本[:：]\s*(v[0-9.]+)"), "occ_src": "", "scope": "req_doc"}]
    check("scope=req_doc 限定文档域（限 a.md → 单处不漂移）", detect(g, conv2) == [])

    print("\n  entity_drift 自验证：" + ("全 PASS" if ok else "有 FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
