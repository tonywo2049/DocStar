#!/usr/bin/env python3
"""entity_verify — 实体层增量自查（EG-14「病一自查」；G5）。波7 唯一交付本文件。

`verify --baseline <rev>` = 对**基线图**（`scan(corpus.GitSource(rev))`）与**当前图**（已扫好的 g）
各跑一次 `entity_extract.build(g, conv)`，取实体/边**集合差**，只报「我引入的」。四输出桶（DG-31）：

  引入实体 / 引入边   ——身份=主键 (kind,ns,cid) / (type,src,dst) 的集合差（当前∖基线）
  引入缺陷            ——已进图但有病：实体_重定义 + ambiguous_reference（present-but-defective）
  进图缺失            ——EG-14-AC3 三有限形态「命中 canonical 形态却未产生预期实体/边」：
                        ①显式ID未解析=unresolved_reference ②canonical directive失效=实体_修订行未解析
                        ③规范条目未产生预期实体=实体_无定义块（referenced-but-undefined，含映射/规范表行）

移动语义（EG-14-AC2/DG-31）：主键 ns/cid 含路径/文档 stem，**文件移动即改主键**→报「旧实体删除+新
实体新增」（删除实体/删除边桶）。**MVP 不承诺「移动下身份稳定」**（只排行号不排路径≠稳定）；git rename
map 归一列下一相=**未实现**，见 out["局限说明"]，不得读作已解决。

诊断独立身份（DG-31）：unresolved/歧义/修订未解析不是现存实体边，身份=`(检查key, 来源符号, 期望token/关系)`，
**file/line 仅展示不进身份**——line 防插行漂移；file 排除令「同类缺陷移到别处」不算新增（=「不含存量欠账」）。

基线缺省=`git merge-base HEAD @{u}` 失败回退 HEAD（EG-14-AC1）。快照隔离靠 GitSource(baseline)（EG-14-AC4；
最彻底=独立 worktree）。verify 是自查advisory：有发现仍退 0；仅 baseline 不可解析/基线扫描失败退 2。
零模型零 prompt、经 entity_model.emit、确定性（稳定排序）。自验证：python3 entity_verify.py --selftest
"""

import subprocess
import sys
from pathlib import Path

import corpus
import entity_extract
import entity_model as M


# ==================== baseline 解析（EG-14-AC1） ====================

def _git(*args):
    return subprocess.run(["git", "-C", str(corpus.ROOT), *args],
                          capture_output=True, text=True)


def _resolve_baseline(baseline):
    """→ (rev, 来源标签)。不可解析→(None, 诊断串)。
    显式 baseline 校验能解析为 commit（否则误当空基线把整树报成引入）；缺省 merge-base→回退 HEAD。"""
    if baseline:
        r = _git("rev-parse", "--verify", "--quiet", f"{baseline}^{{commit}}")
        if r.returncode != 0 or not r.stdout.strip():
            return None, f"baseline 无法解析为 commit：{baseline}"
        return baseline, "显式指定"
    mb = _git("merge-base", "HEAD", "@{u}")
    if mb.returncode == 0 and mb.stdout.strip():
        return mb.stdout.strip(), "merge-base(HEAD,@{u})"
    hd = _git("rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if hd.returncode == 0 and hd.stdout.strip():
        return "HEAD", "无上游，回退 HEAD"
    return None, "无法确定 baseline（无 HEAD/无上游）"


def _git_scan_root(g):
    """当前图扫描根 → 仓库相对 git 路径（镜像给 GitSource，使基线与当前扫同一子树）。
    全仓根→'.'（git 空 pathspec 非法）；仓库外→'.'（best-effort 全仓基线）。"""
    root = Path(getattr(g, "root", corpus.ROOT)).resolve()
    if root == corpus.ROOT:
        return "."
    try:
        return str(root.relative_to(corpus.ROOT))
    except ValueError:
        return "."


# ==================== 身份与集合差 ====================

def _entity_id(e):
    return tuple(e["key"])                                  # (kind, ns, cid)


def _edge_id(e):
    return (e["type"], tuple(e["src"]), tuple(e["dst"]))


def _diff(current, baseline, id_fn):
    """双向集合差 → (引入=当前∖基线, 删除=基线∖当前)，各按身份稳定排序。"""
    cur_ids = {id_fn(it) for it in current}
    base_ids = {id_fn(it) for it in baseline}
    introduced = sorted((it for it in current if id_fn(it) not in base_ids),
                        key=lambda it: tuple(str(x) for x in _flatten(id_fn(it))))
    removed = sorted((it for it in baseline if id_fn(it) not in cur_ids),
                     key=lambda it: tuple(str(x) for x in _flatten(id_fn(it))))
    return introduced, removed


def _flatten(idt):
    """身份元组可能含嵌套元组（边 src/dst）→ 展平成可比较的字符串序列基。"""
    out = []
    for x in idt:
        if isinstance(x, tuple):
            out.extend(x)
        else:
            out.append(x)
    return out


# ==================== 缺陷 / 进图缺失（仅新增方向；只报我引入的） ====================
# (report 键, 展示标签, 身份函数)。身份=(检查key, 来源符号, 期望token/关系)，file/line 不进身份。

_MISS_SPECS = [
    ("unresolved_reference", "①显式ID未解析",
     lambda it: ("unresolved_reference", it["来源"], it["期望"])),
    ("实体_修订行未解析", "②canonical_directive失效",
     lambda it: ("实体_修订行未解析", it["摘要"])),
    ("实体_无定义块", "③规范条目未产生预期实体",
     lambda it: ("实体_无定义块", tuple(it["key"]))),
]
_DEFECT_SPECS = [
    ("实体_重定义", "实体_重定义",
     lambda it: ("实体_重定义", tuple(it["key"]))),
    ("ambiguous_reference", "ambiguous_reference",
     lambda it: ("ambiguous_reference", it["来源"])),
]


def _introduced(cur_reports, base_reports, specs, tag_field):
    """逐 spec 取当前∖基线的诊断项，打标签；按 spec 序分组、组内按身份稳定排序。"""
    rows = []
    for rkey, label, id_fn in specs:
        base_ids = {id_fn(it) for it in base_reports.get(rkey, [])}
        introduced = [it for it in cur_reports.get(rkey, []) if id_fn(it) not in base_ids]
        introduced.sort(key=lambda it: tuple(str(x) for x in _flatten(id_fn(it))))
        for it in introduced:
            row = {tag_field: label}
            row.update(it)
            rows.append(row)
    return rows


# ==================== 主命令 ====================

_LIMIT_NOTE = ("移动=旧实体删除+新实体新增（主键含路径/文档stem，MVP 不承诺移动下身份稳定）；"
               "git rename map 归一列=未实现（下一相）；诊断身份不含 file/line（仅展示）。")


def cmd_verify(g, conv, baseline_rev, as_json):
    """冻结签名（DocStar 已 dispatch）：g=当前图，conv=约定集，baseline_rev=--baseline（可 None）。"""
    rev, source = _resolve_baseline(baseline_rev)
    if rev is None:
        print(f"verify：{source}", file=sys.stderr)
        return 2
    scan_root = _git_scan_root(g)
    import docstar            # 懒加载复用 scan()：dispatch 时根在 sys.path；避免模块级反向依赖，单文件自检不挂
    try:
        # 基线侧与当前侧同 conv 同 include_archived 开关（DG-59：两侧同语义，防伪增删差分）
        base_g = docstar.scan(corpus.GitSource(rev, scan_root=scan_root), conv,
                              include_archived=getattr(g, "include_archived", False))
    except Exception as e:                                  # noqa: BLE001（基线扫描任何失败都退 2 带诊断）
        print(f"verify：基线扫描失败（{rev}:{scan_root}）：{e}", file=sys.stderr)
        return 2

    cur = entity_extract.build(g, conv)
    base = entity_extract.build(base_g, conv)

    ent_in, ent_out = _diff(cur["entities"], base["entities"], _entity_id)
    edge_in, edge_out = _diff(cur["edges"], base["edges"], _edge_id)

    out = {
        "schema_version": M.SCHEMA_VERSION,
        "baseline": rev,
        "baseline_来源": source,
        "scan_root": scan_root,
        "引入实体": ent_in,
        "删除实体": [{"key": e["key"], "display": e["display"]} for e in ent_out],
        "引入边": edge_in,
        "删除边": [{"type": e["type"], "src": e["src"], "dst": e["dst"]} for e in edge_out],
        "引入缺陷": _introduced(cur["reports"], base["reports"], _DEFECT_SPECS, "类"),
        "进图缺失": _introduced(cur["reports"], base["reports"], _MISS_SPECS, "形态"),
        "局限说明": _LIMIT_NOTE,
    }
    # DG-43：corpus_revision='worktree'（当前扫描=工作树，稳定符号）；baseline rev 已在 out 体（"baseline"）。
    out = {"context_manifest": M.context_manifest(
        "worktree", conv, "verify", body=out,
        include_archived=getattr(g, "include_archived", False)), **out}

    if as_json:
        print(M.emit(out))
    else:
        _print_text(out)
    return 0


# ==================== 迁移验证模式（EG-25 / DG-49；裁定③缓做的轻量替代） ====================
# 文件移动/改名批次 → 前后图 diff + 断边清单（传导完备性的客观证据）。不改主键身份（身份与路径
# 分离属 schema 级手术=缓做），只把「删除+新增」翻译为「移动+断边」的可读客观证据（非语义判断）。

def _renamed_files(rev, scan_root):
    """git diff --name-status -z -M <rev>（基线→工作树）取重命名对 → [(旧, 新)]，均 scan_root 相对、限 .md。
    -z：NUL 分隔、禁 core.quotepath 八进制转义（非 ASCII 路径否则带引号，破 .md 判定，同 GitSource.docs）。
    scan_root='.' 时路径即仓库相对=语料相对；子树 scan_root 剥前缀（镜像 GitSource.docs）。
    -z 记录：A/M/D=<status>\\0<path>；R/C=<status>\\0<old>\\0<new>（重命名/复制多读一路径）。"""
    r = _git("diff", "--name-status", "-z", "-M", rev)
    if r.returncode != 0:
        return None                                  # 诊断由调用方给（基线不可 diff）
    prefix = "" if scan_root in (".", "") else scan_root.rstrip("/") + "/"
    toks = [t for t in r.stdout.split("\0") if t != ""]
    moved, i = [], 0
    while i < len(toks):
        status = toks[i]
        if status[:1] in ("R", "C") and i + 2 < len(toks):
            old, new = toks[i + 1], toks[i + 2]
            i += 3
            if not (status[:1] == "R" and old.endswith(".md") and new.endswith(".md")):
                continue                             # 只收重命名(R)的 .md（复制 C 非移动，不计断边）
            if prefix and not (old.startswith(prefix) and new.startswith(prefix)):
                continue                             # 子树外的移动不计入本语料
            moved.append((old[len(prefix):], new[len(prefix):]))
        else:                                        # A/M/D：单路径，跳过
            i += 2
    return sorted(moved)


def _endpoint_doc(ent_by_key, endpoint):
    """端点实体的定义文档（primary.doc）；未定义/无 primary→None。"""
    e = ent_by_key.get(tuple(endpoint))
    p = e.get("primary") if e else None
    return p.get("doc") if p else None


def cmd_verify_migrate(g, conv, baseline_rev, as_json):
    """冻结签名（DocStar 已 dispatch verify --migrate）：g=当前图，baseline_rev=--baseline（移动前 rev）。
    输出 DG-49 骨架：moved_files（重命名对）+ broken_edges（因移动而悬空的边：主键含旧路径 stem、现无对端）
    + context_manifest（携基线戳）。断边=基线有、当前无、且端点定义文档或抽取源在移动集内 → 客观断边清单。"""
    rev, source = _resolve_baseline(baseline_rev)
    if rev is None:
        print(f"verify --migrate：{source}", file=sys.stderr)
        return 2
    scan_root = _git_scan_root(g)
    moved = _renamed_files(rev, scan_root)
    if moved is None:
        print(f"verify --migrate：基线无法 diff（{rev}）", file=sys.stderr)
        return 2
    import docstar                                    # 懒加载复用 scan（同 cmd_verify）
    try:
        # 基线侧与当前侧同 conv 同 include_archived 开关（DG-59：两侧同语义，防伪增删差分）
        base_g = docstar.scan(corpus.GitSource(rev, scan_root=scan_root), conv,
                              include_archived=getattr(g, "include_archived", False))
    except Exception as e:                            # noqa: BLE001
        print(f"verify --migrate：基线扫描失败（{rev}:{scan_root}）：{e}", file=sys.stderr)
        return 2

    base = entity_extract.build(base_g, conv)
    cur = entity_extract.build(g, conv)
    base_ent_by_key = {tuple(e["key"]): e for e in base["entities"]}
    cur_edge_ids = {_edge_id(e) for e in cur["edges"]}
    moved_old = {old for old, _new in moved}

    broken = []
    for e in base["edges"]:
        if _edge_id(e) in cur_edge_ids:               # 当前仍在=未断
            continue
        causes = []                                   # 断因：哪一侧的移动使这条边悬空
        if _endpoint_doc(base_ent_by_key, e["src"]) in moved_old:
            causes.append("src移动")
        if _endpoint_doc(base_ent_by_key, e["dst"]) in moved_old:
            causes.append("dst移动")
        if e["prov"]["file"] in moved_old:
            causes.append("来源移动")
        if not causes:                                # 边消失但非移动所致（内容改）→ 不进迁移断边清单
            continue
        broken.append({"边类型": e["type"], "src": e["src"], "dst": e["dst"],
                       "断因": "|".join(causes), "prov": e["prov"]})
    broken.sort(key=lambda b: (b["边类型"], b["src"], b["dst"], b["prov"]["file"], b["prov"]["line"]))

    out = {
        "schema_version": M.SCHEMA_VERSION,
        "baseline": rev,
        "baseline_来源": source,
        "scan_root": scan_root,
        "moved_files": [{"从": old, "到": new} for old, new in moved],
        "broken_edges": broken,
        "局限说明": _MIGRATE_NOTE,
    }
    out = {"context_manifest": M.context_manifest(
        "worktree", conv, "verify-migrate", body=out,
        include_archived=getattr(g, "include_archived", False)), **out}
    if as_json:
        print(M.emit(out))
    else:
        _print_migrate_text(out)
    return 0


_MIGRATE_NOTE = ("迁移验证=前后图 diff+断边清单（EG-25/DG-49）；裁定③「身份跨移动稳定」缓做，本模式不改主键、"
                 "不做身份/路径分离，只客观报告移动的传导后果（断边=基线有·当前无·且端点/来源在移动集）。")


def _print_migrate_text(out):
    print(f"verify --migrate  baseline={out['baseline']}（{out['baseline_来源']}）  scan_root={out['scan_root']}")
    print(f"  移动文件 {len(out['moved_files'])} | 断边 {len(out['broken_edges'])}")
    for mv in out["moved_files"]:
        print(f"  移动  {mv['从']}  →  {mv['到']}")
    for b in out["broken_edges"]:
        print(f"  断边  {b['边类型']}  {b['src'][2]} → {b['dst'][2]}  [{b['断因']}]  @{b['prov']['file']}:{b['prov']['line']}")
    print(f"\n局限：{out['局限说明']}")


def _print_text(out):
    print(f"verify 增量自查  baseline={out['baseline']}（{out['baseline_来源']}）  scan_root={out['scan_root']}")
    print(f"  引入实体 {len(out['引入实体'])} / 删除实体 {len(out['删除实体'])} "
          f"| 引入边 {len(out['引入边'])} / 删除边 {len(out['删除边'])} "
          f"| 引入缺陷 {len(out['引入缺陷'])} | 进图缺失 {len(out['进图缺失'])}")

    def dump(title, rows, fmt):
        if not rows:
            return
        print(f"\n[{title}]  {len(rows)}")
        for r in rows:
            print("  " + fmt(r))

    dump("引入实体", out["引入实体"], lambda e: f"{e['key']}  {e.get('display', '')}")
    dump("删除实体", out["删除实体"], lambda e: f"{e['key']}  {e.get('display', '')}")
    dump("引入边", out["引入边"],
         lambda e: f"{e['type']}  {e['src'][2]} → {e['dst'][2]}  @{e['prov']['file']}:{e['prov']['line']}")
    dump("删除边", out["删除边"], lambda e: f"{e['type']}  {e['src'][2]} → {e['dst'][2]}")
    dump("引入缺陷", out["引入缺陷"], _fmt_diag)
    dump("进图缺失", out["进图缺失"], _fmt_diag)
    print(f"\n局限：{out['局限说明']}")


def _fmt_diag(r):
    tag = r.get("形态") or r.get("类") or "?"
    loc = ""
    if "file" in r:
        loc = f"  @{r['file']}:{r.get('line', '?')}"
    elif "首现" in r:
        loc = f"  @{r['首现'].get('doc', '?')}:{r['首现'].get('line', '?')}"
    body = r.get("来源") or (r.get("key") and r["key"][2]) or r.get("摘要") or ""
    exp = f" → {r['期望']}" if "期望" in r else ""
    return f"{tag}  {body}{exp}{loc}"


# ==================== 自验证（测量装置先于被测对象：合成已知值核对） ====================

def _selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    # 身份键（样例用通用/开放 kind，身份逻辑对任意 kind 一致——DG-38）
    e1 = {"key": ["需求AC", "requirements", "REQ-1"], "display": "REQ-1"}
    e2 = {"key": ["需求AC", "requirements", "REQ-2"], "display": "REQ-2"}
    check("实体身份=主键三元组", _entity_id(e1) == ("需求AC", "requirements", "REQ-1"))
    edge = {"type": "映射", "src": ["需求AC", "requirements", "REQ-7"],
            "dst": ["决策", "某设计", "D-1"]}
    check("边身份=(type,src,dst)",
          _edge_id(edge) == ("映射", ("需求AC", "requirements", "REQ-7"), ("决策", "某设计", "D-1")))

    # 集合差：引入 = 当前∖基线；删除 = 基线∖当前
    intro, rem = _diff([e1, e2], [e1], _entity_id)
    check("引入=当前∖基线（REQ-2 新增）", [x["key"][2] for x in intro] == ["REQ-2"])
    check("删除=空（e1 两侧都有）", rem == [])
    intro2, rem2 = _diff([e2], [e1, e2], _entity_id)
    check("删除=基线∖当前（e1 消失）", [x["key"][2] for x in rem2] == ["REQ-1"])
    check("引入=空", intro2 == [])

    # 移动=删除+新增：主键 ns 含文档 stem，移动改 ns → 旧删+新增
    old = {"key": ["节条目", "旧文档", "旧文档§3"], "display": "§3"}
    new = {"key": ["节条目", "新文档", "新文档§3"], "display": "§3"}
    mi, mr = _diff([new], [old], _entity_id)
    check("移动：新实体新增", [x["key"][1] for x in mi] == ["新文档"])
    check("移动：旧实体删除", [x["key"][1] for x in mr] == ["旧文档"])

    # 诊断身份不含 file/line：同 (来源,期望) 移到别文件/行 ≠ 新增（不含存量欠账）
    base_rep = {"unresolved_reference": [{"来源": "前置", "期望": "X-06", "file": "a.md", "line": 5}]}
    cur_rep = {"unresolved_reference": [{"来源": "前置", "期望": "X-06", "file": "b.md", "line": 99}]}
    misses = _introduced(cur_rep, base_rep, _MISS_SPECS, "形态")
    check("诊断身份不含 file/line：同类移位不算引入", misses == [])
    # 真新增（期望 token 变）→ 报
    cur_rep2 = {"unresolved_reference": [{"来源": "前置", "期望": "X-07", "file": "b.md", "line": 99}]}
    misses2 = _introduced(cur_rep2, base_rep, _MISS_SPECS, "形态")
    check("真新增诊断（期望变 X-07）被报", len(misses2) == 1 and misses2[0]["形态"] == "①显式ID未解析")

    # 三形态映射：unresolved→①、修订未解析→②、无定义块→③
    cur_all = {
        "unresolved_reference": [{"来源": "X", "期望": "Y", "file": "a.md", "line": 1}],
        "实体_修订行未解析": [{"file": "a.md", "line": 2, "摘要": "修订: 坏行"}],
        "实体_无定义块": [{"key": ["需求AC", "REQUIREMENTS", "R9-AC9"], "occurrences": 1,
                        "首现": {"doc": "a.md", "line": 3}}],
    }
    ms = _introduced(cur_all, {}, _MISS_SPECS, "形态")
    forms = [m["形态"] for m in ms]
    check("三形态齐备且按①②③序",
          forms == ["①显式ID未解析", "②canonical_directive失效", "③规范条目未产生预期实体"])

    # 缺陷桶：重定义 + 歧义（present-but-defective）
    cur_def = {
        "实体_重定义": [{"key": ["专名", "d", "T"], "primary": {"doc": "a.md", "line": 1},
                     "candidates": []}],
        "ambiguous_reference": [{"来源": "§3", "file": "a.md", "line": 4}],
    }
    ds = _introduced(cur_def, {}, _DEFECT_SPECS, "类")
    check("缺陷桶：重定义+歧义两类", [d["类"] for d in ds] == ["实体_重定义", "ambiguous_reference"])

    # 修订未解析身份=(检查key,摘要)，行号移动不算新增
    b = {"实体_修订行未解析": [{"file": "a.md", "line": 10, "摘要": "修订: 坏行"}]}
    c = {"实体_修订行未解析": [{"file": "a.md", "line": 40, "摘要": "修订: 坏行"}]}
    check("修订未解析：仅行号变≠新增", _introduced(c, b, _MISS_SPECS, "形态") == [])

    # baseline 解析：显式非法 rev → None；HEAD 可解析
    rev_bad, _ = _resolve_baseline("此rev不存在zzz999")
    check("非法 baseline → 拒绝", rev_bad is None)
    rev_head, src_head = _resolve_baseline("HEAD")
    check("显式 HEAD 可解析", rev_head == "HEAD" and src_head == "显式指定")

    # scan_root 镜像：全仓→'.'
    class _G:
        root = corpus.ROOT
    check("scan_root 全仓→'.'", _git_scan_root(_G()) == ".")

    print("\n  entity_verify 自验证：" + ("全 PASS" if ok else "有 FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
