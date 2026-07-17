#!/usr/bin/env python3
"""entity_classify — classify 的确定性两端：--pending / --validate（EG-11-AC6 / DG-32；波7-C）。

引擎零 prompt 零模型（G7 不变量）——性质判断在进程外 agent（prompt 正本随 skill，EG-16），
工具只出两端确定性事实：

  --pending  扫语料，列缺 `性质` frontmatter 声明的文档 + 每篇「机械证据」（确定性线索，非模型判断）：
             缺声明原因 / 定义句式命中（定义了几个 canonical-grammar 实体、是否底账表形态）/
             被规范文档引用否（含引用来源）/ 标题·类型信号。供 agent 判该文档分「规范|记述」。

  --validate 以 baseline(git rev) 为基准校验分类回填「只动 frontmatter」（DG-32 / 外源评审 P0-3.4）：
             ① 覆盖——scope 内文档须都已声明性质；② 只动 frontmatter——正文（去 frontmatter 后的行）
             相对 baseline 零改动。分片(--manifest)：只判 scope 内覆盖、容忍 scope 外 frontmatter 改动
             （共享工作树并发分片），拒 scope 外正文改动；无 manifest=合并后全局 validate（全覆盖 + 任
             一文档零正文改动）。manifest=（baseline + 该分片允许改的 repo-relative paths + 完成判据）。

只消费 entity_extract.build(g,conv) 的分类事实 + corpus 性质原语 + git 基线；不改任何状态、不调模型。
"""

import json
import subprocess
import sys
from pathlib import Path

import corpus
import entity_extract
import entity_model as M

# 路径空间＝**语料本身**（独立工具无「工具所在仓库」概念；原 REPO=parents[2] 是位置硬假设，
# 抽离后 parents[2] 会漂成任意上级目录并把它泄进输出——已删）。输出/manifest 一律语料相对。


# ---------------- 路径空间（扫描根 rel ↔ 仓库相对） ----------------

def _corpus_root(g):
    """语料根在自身路径空间中的位置＝"."（禁绝对路径入输出：输出内一切 path 皆语料相对）。"""
    return "."


def _repo_rel(g, rel):
    """语料相对路径（manifest 匹配与 git 定位用）。工具路径空间＝语料，故恒等；保留函数名以免
    调用点大改，语义已由「仓库相对」订正为「语料相对」。"""
    return rel


def _body(text):
    """去 frontmatter 后的正文行——镜像 docstar.parse_frontmatter 边界（`---` 包围、≤60 行窗口）。
    frontmatter-only 改动 → 正文行不变；「只动 frontmatter」据此判定。"""
    if text is None:
        return []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return lines
    for i in range(1, min(len(lines), 60)):
        if lines[i].strip() == "---":
            return lines[i + 1:]
    return lines                                 # 无闭合 → 全文即正文（body_start=0，同 parse_frontmatter）


def _title(text, stem):
    """标题信号=正文首个顶级 `# ` 标题原文（无则文件名 stem）；确定性提取、不判断。"""
    for ln in _body(text):
        s = ln.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return stem


# ==================== --pending：待分类清单 + 机械证据 ====================

def pending(g, conv):
    """扫语料 → 缺 `性质` 声明的文档清单，每篇附机械证据。消费 entity_extract.build。"""
    data = entity_extract.build(g, conv)
    unknown = data["unknown_documents"]          # docnat=unknown（缺 性质 声明），build 权威定序

    # 每文档定义的 canonical-grammar 实体数（primary 落在该文档）＋实体→定义文档映射
    defcount, home = {}, {}
    for e in data["entities"]:
        pr = e.get("primary")
        if pr and pr.get("doc"):
            defcount[pr["doc"]] = defcount.get(pr["doc"], 0) + 1
            home[tuple(e["key"])] = pr["doc"]

    # 被规范文档引用：源文档性质=规范 的边/链接指向该文档（文档层 + 实体层，取并集）
    docnat = {r: corpus.doc_nature(g.docs[r]["meta"], conv) for r in g.docs}
    normrefs = {}

    def _add_ref(src, dst):
        if dst and dst != src and docnat.get(src) == "规范":
            normrefs.setdefault(dst, set()).add(src)

    for s, dst, _key, _dir, _entry, _raw in g.fm_edges:    # frontmatter 引用（通配键，含上下游）
        _add_ref(s, dst)
    for s, dst, _raw, _ln in g.body_links:                 # 正文链接
        _add_ref(s, dst)
    for s, _w, _n, dst, _ln in g.sec_refs:                 # § 引用
        _add_ref(s, dst)
    for ed in data["edges"]:                               # 实体边：靶实体定义在某文档
        src = ed["prov"]["file"]
        if docnat.get(src) == "规范":
            _add_ref(src, home.get(tuple(ed["dst"])))

    out = []
    for rel in unknown:
        d = g.docs[rel]
        meta = d["meta"]
        if not d["has_fm"]:
            reason = "无frontmatter"
        elif "性质" not in meta:
            reason = "frontmatter缺性质字段"
        else:
            reason = "性质值非法（非规范|记述）"
        refs = normrefs.get(rel, set())
        out.append({
            "path": _repo_rel(g, rel) or rel,
            "缺声明原因": reason,
            "证据": {
                "定义实体数": defcount.get(rel, 0),
                "底账表形态": conv.is_ledger_doc(g.texts.get(rel, "") or ""),
                "被规范文档引用": bool(refs),
                "引用来源规范文档": sorted(_repo_rel(g, r) or r for r in refs),
                "标题": _title(g.texts.get(rel, "") or "", d["stem"]),
                "类型": list(meta.get("类型", [])),
            },
        })
    out.sort(key=lambda x: x["path"])
    return {
        "schema_version": M.SCHEMA_VERSION,
        "mode": "pending",
        "corpus_root": _corpus_root(g),
        "classification_complete": data["classification_complete"],
        "total_documents": len(g.docs),
        "pending_count": len(out),
        "pending": out,
    }


# ==================== --validate：baseline + scope 校验 ====================

def _err(msg, code):
    return {"schema_version": M.SCHEMA_VERSION, "mode": "validate", "result": "error", "error": msg}, code


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(corpus.ROOT), *args],
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _rev_parse(rev):
    out = _git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return out.strip() if out else None


def _git_show(rev, repo_rel):
    return _git("show", f"{rev}:{repo_rel}")      # baseline 无此文件（新增）→ None


def _read(repo_rel):
    try:
        return (corpus.ROOT / repo_rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None                               # 当前无此文件（删除）→ None


def _changed_md(rev, corpus_prefix):
    """baseline→当前工作树 变更的 .md（仓库相对，NUL 分隔避免 quotepath）。"""
    whole = corpus_prefix in (".", "")
    pathspec = [] if whole else [corpus_prefix]
    out = _git("diff", "--name-only", "-z", rev, "--", *pathspec)
    if out is None:
        return []
    res = set()
    for path in out.split("\0"):
        if not path.endswith(".md"):
            continue
        if whole and path.startswith("fixtures/"):   # 隔离级 fixtures（同 scan 排除）
            continue
        res.add(path)
    return sorted(res)


def _in_scope(repo_rel, paths):
    """scope 命中：路径等值 或 位于某 scope 目录下（迁移-C 按目录分片）。"""
    for p in paths:
        p2 = p.rstrip("/")
        if repo_rel == p2 or repo_rel.startswith(p2 + "/"):
            return True
    return False


def _load_manifest(manifest, rev):
    """分片 scope 文件 → {paths, 完成判据, source}。paths=repo-relative 允许改路径（文件或目录）。"""
    p = Path(manifest)
    if not p.is_absolute():
        p = corpus.ROOT / manifest
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"manifest 读取/解析失败（{manifest}）：{e}"
    if not isinstance(raw, dict):
        return None, "manifest 顶层须为对象 {paths:[...], baseline?, 完成判据?}"
    paths = raw.get("paths")
    if not (isinstance(paths, list) and paths and all(isinstance(x, str) and x.strip() for x in paths)):
        return None, "manifest.paths 须为非空字符串数组（该分片允许改的 repo-relative 路径）"
    mb = raw.get("baseline")
    if mb is not None and _rev_parse(str(mb)) != rev:
        return None, f"manifest.baseline({mb}) 与 --baseline 解析到不同 commit（scope 基线须唯一）"
    return {"paths": [x.strip() for x in paths], "完成判据": raw.get("完成判据", ""),
            "source": str(manifest)}, None


def validate(g, conv, baseline, manifest):
    """→ (结果 dict, 退出码)。baseline 必填(git rev)；manifest 可选(分片 scope)。零 prompt 零模型。"""
    if not baseline:
        return _err("classify --validate 须 --baseline <git-rev>（分片/全局均以 baseline 为基准，DG-32）", 2)
    rev = _rev_parse(baseline)
    if rev is None:
        return _err(f"--baseline 非合法 git revision：{baseline}", 2)

    corpus_prefix = _corpus_root(g)   # 语料非 git 仓时，上面的 _rev_parse(baseline) 已先行拒绝

    scope = None
    if manifest is not None:
        scope, e = _load_manifest(manifest, rev)
        if e:
            return _err(e, 2)
    scoped = scope is not None

    # ① 覆盖：当前树内 scope 文档须都已声明性质（分片只判 scope 内；无 scope=全仓）
    in_scope_n, uncovered = 0, []
    for rel in g.docs:
        rr = _repo_rel(g, rel)
        if rr is None or (scoped and not _in_scope(rr, scope["paths"])):
            continue
        in_scope_n += 1
        if corpus.doc_nature(g.docs[rel]["meta"], conv) == "unknown":
            uncovered.append(rr)
    uncovered.sort()

    # ② 只动 frontmatter：变更文档的正文相对 baseline 须零改动（区分 scope 内/外，仅诊断分类）
    body_internal, body_external, fm_only = [], [], []
    for rr in _changed_md(rev, corpus_prefix):
        base_txt, cur_txt = _git_show(rev, rr), _read(rr)
        if _body(base_txt) != _body(cur_txt):
            bucket = body_internal if (not scoped or _in_scope(rr, scope["paths"])) else body_external
            bucket.append(rr)
        elif base_txt != cur_txt:
            fm_only.append(rr)                    # 仅 frontmatter 改动（scope 外亦容忍：并发分片回填）
    body_internal.sort(); body_external.sort(); fm_only.sort()

    ok = not uncovered and not body_internal and not body_external
    return {
        "schema_version": M.SCHEMA_VERSION,
        "mode": "validate",
        "corpus_root": corpus_prefix,
        "baseline": rev,
        "scoped": scoped,
        "scope": ({"paths": scope["paths"], "完成判据": scope["完成判据"], "source": scope["source"]}
                  if scoped else None),
        "result": "pass" if ok else "fail",
        "覆盖": {"scope内文档数": in_scope_n, "未覆盖": uncovered, "全覆盖": not uncovered},
        "正文改动": {"scope内": body_internal, "scope外": body_external},
        "仅frontmatter改动": fm_only,
    }, (0 if ok else 1)


# ==================== 人读输出 ====================

def _print_pending(data):
    print(f"classify --pending（schema={data['schema_version']}，corpus_root={data['corpus_root']}）：")
    print(f"  文档 {data['total_documents']} 篇，缺 性质 声明 {data['pending_count']} 篇"
          f"（分类完成={data['classification_complete']}）")
    for it in data["pending"]:
        ev = it["证据"]
        print(f"  - {it['path']}｜{it['缺声明原因']}｜定义实体 {ev['定义实体数']}"
              f"｜底账表={ev['底账表形态']}｜被规范引用={ev['被规范文档引用']}"
              f"｜标题：{ev['标题']}")


def _print_validate(data, code):
    if data.get("result") == "error":
        print(f"classify --validate 拒绝：{data['error']}", file=sys.stderr)
        return
    cov, body = data["覆盖"], data["正文改动"]
    tag = "分片" if data["scoped"] else "全局"
    print(f"classify --validate（{tag}，baseline={data['baseline'][:12]}）：{data['result'].upper()}")
    print(f"  覆盖：scope 内 {cov['scope内文档数']} 篇，未覆盖 {len(cov['未覆盖'])} 篇，全覆盖={cov['全覆盖']}")
    print(f"  正文改动（违反只动 frontmatter）：scope 内 {len(body['scope内'])}、scope 外 {len(body['scope外'])}")
    for rr in cov["未覆盖"]:
        print(f"    未覆盖 {rr}")
    for rr in body["scope内"] + body["scope外"]:
        print(f"    正文改动 {rr}")


# ==================== DocStar dispatch 入口（冻结签名） ====================

def cmd_classify(g, conv, mode, baseline, manifest, as_json):
    if mode == "pending":
        data = pending(g, conv)
        data = {"context_manifest": M.context_manifest(  # DG-43
            "worktree", conv, "classify:pending", body=data,
            include_archived=getattr(g, "include_archived", False)), **data}
        print(M.emit(data)) if as_json else _print_pending(data)
        return 0
    if mode == "validate":
        data, code = validate(g, conv, baseline, manifest)
        data = {"context_manifest": M.context_manifest(  # DG-43
            "worktree", conv, "classify:validate", body=data,
            include_archived=getattr(g, "include_archived", False)), **data}
        print(M.emit(data)) if as_json else _print_validate(data, code)
        return code
    print(f"未知 classify 模式：{mode}（应由 DocStar 校验为 pending|validate）", file=sys.stderr)
    return 2
