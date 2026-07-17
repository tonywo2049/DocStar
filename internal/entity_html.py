#!/usr/bin/env python3
"""entity_html — 实体图谱交互查询页（人工浏览器内查图：搜索/详情/邻域图/判定瓦片）。

viz 辅助，非 EG 关账项。把 entity_extract.build(g, conv) 的实体+边、entity_check.sections(g,
conv) 的判定对象整形为一份 payload，内联注入 entity_template.html——自包含、零外部依赖、
file:// 可离线直开。页面通用不项目化：kind/边类型/性质标签一律直取数据值，不写死清单。

接口：cmd_html_entity(g, conv, out)——docstar.py html-entity dispatch 调（先 load conv 再传）。
数据形依赖（build/sections 输出，见 entity_extract/entity_check 文件头）：
  · 实体 {key:[kind,ns,cid], display, 性质, primary|null, candidates, attrs, 状态?(可空缺)}
  · 边   {type, src:[3], dst:[3], prov:{file,line,method}, parse, consumers, attrs}
  · 判定 sections()：schema_version(字符串) + 每 check 键=判定对象
        {result, judgment_status, findings, tainted_by, blocked_by}
"""

import json
from datetime import datetime
from pathlib import Path

import entity_extract
import entity_check
import entity_model as M

# 输出相对路径按 cwd 解析（独立 CLI 标准行为）

_TXT_CAP = 480    # 定义块摘录字符上限（节条目块可能长，仅供详情速览）
_TXT_LINES = 60   # 定义块摘录行数上限（防节条目跨大段拼接）


def _def_text(g, primary):
    """primary {doc,line,line_end} → 定义块摘录（行数+字符双截断）。无 primary/越界→空串。"""
    if not primary:
        return ""
    lines = g.texts.get(primary.get("doc", ""), "").splitlines()
    a = primary.get("line", 0) - 1
    if a < 0 or a >= len(lines):
        return ""
    b = primary.get("line_end") or primary.get("line", 0)
    b = max(a + 1, min(b, a + _TXT_LINES))
    seg = "\n".join(lines[a:b]).strip()
    return seg if len(seg) <= _TXT_CAP else seg[:_TXT_CAP - 1] + "…"


def _verdicts(g, conv):
    """entity_check.sections → 判定瓦片（欠账概览）。sections 属可选特性，且 check 子系统可能
    并行重写中——失败则降级为空瓦片，核心查询页照常生成（不因可选项阻断出页）。"""
    try:
        sec = entity_check.sections(g, conv)
    except Exception as e:                     # noqa: BLE001 — 判定瓦片可选，降级不阻断出页
        return {"schema_version": None, "error": type(e).__name__, "tiles": []}
    tiles = []
    for key, v in sec.items():
        if not isinstance(v, dict):            # 跳过 schema_version 之类的标量值
            continue
        tiles.append({"key": key, "result": v.get("result"),
                      "status": v.get("judgment_status"),
                      "findings": len(v.get("findings", [])),
                      "tainted_by": list(v.get("tainted_by", [])),
                      "blocked_by": list(v.get("blocked_by", []))})
    return {"schema_version": sec.get("schema_version"), "error": None, "tiles": tiles}


def _tally(names):
    """名称序列 → [{name,count}]（降序）；标签直取数据值，kind/边类型/性质清单不硬编码。"""
    d = {}
    for n in names:
        d[n] = d.get(n, 0) + 1
    return sorted(({"name": k, "count": c} for k, c in d.items()),
                  key=lambda x: (-x["count"], x["name"]))


def _payload(g, conv):
    built = entity_extract.build(g, conv)
    ents, edges = built["entities"], built["edges"]
    idx = {tuple(e["key"]): i for i, e in enumerate(ents)}
    deg = [0] * len(ents)
    out_edges = []
    for e in edges:
        s, t = idx.get(tuple(e["src"])), idx.get(tuple(e["dst"]))
        if s is None or t is None:
            continue                           # 端点未物化（不应发生，稳妥跳过）
        deg[s] += 1
        deg[t] += 1
        out_edges.append({"s": s, "t": t, "ty": e["type"],
                          "file": e["prov"]["file"], "line": e["prov"]["line"],
                          "method": e["prov"].get("method", ""), "attrs": e.get("attrs", {})})
    ent_out = []
    for i, e in enumerate(ents):
        p = e.get("primary")
        ent_out.append({
            "kind": e["key"][0], "ns": e["key"][1], "cid": e["key"][2], "disp": e["display"],
            "nature": e.get("性质", "unknown"), "status": e.get("状态"),
            "doc": p["doc"] if p else None, "line": p["line"] if p else None,
            "txt": _def_text(g, p),
            "cand": [{"doc": c["doc"], "line": c["line"]} for c in e.get("candidates", [])],
            "attrs": e.get("attrs", {}), "deg": deg[i]})
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "schema_version": M.SCHEMA_VERSION,
            "counts": {"entities": len(ent_out), "edges": len(out_edges)},
            "kinds": _tally(e["kind"] for e in ent_out),
            "edgeTypes": _tally(e["ty"] for e in out_edges),
            "natures": _tally(e["nature"] for e in ent_out),
            "reports": {k: len(v) for k, v in built["reports"].items()},
            "classification_complete": built["classification_complete"],
            "unknown_documents": built["unknown_documents"],
            "verdicts": _verdicts(g, conv),
            "ents": ent_out, "edges": out_edges}


def cmd_html_entity(g, conv, out):
    payload = _payload(g, conv)
    tpl = (Path(__file__).parent / "entity_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*__DATA__*/null",
                       json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    out_path = Path(out) if out else Path(__file__).parent / "entity_graph.html"
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.write_text(html, encoding="utf-8")
    c = payload["counts"]
    print(f"已生成 {out_path}（{c['entities']} 实体 / {c['edges']} 边；搜索+详情+邻域图+判定瓦片）")
    return 0
