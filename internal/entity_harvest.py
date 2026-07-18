#!/usr/bin/env python3
"""entity_harvest — 未标注高频词提示（EG-5 harvest 半；波6-TB 交付，改自 eg-1 登记册候选）。

The current harvest mode reports unannotated high-frequency terms as writing hints:
harvest 不再产「登记册候选」，而是提示语料里**高频出现却从未就地标注/术语表定义**的粗体·
反引号专名候选——即「该写 `**X**（定义：<锚>）` 或术语表行却没写」的欠账线索（提示级，
不进任何门禁；无 `[[X]]` 显式引用语法，引用端不可确定性判定，故只提示不判定）。

源=语料内**性质=规范**文档正文（DG-25：harvest 输入=规范文档；记述/unknown 不扫）；删除线
跨度先剔除（EG-11-AC5）。候选=粗体 `**…**`／反引号 `` `…` `` 内词，清洗后过四过滤器
（长度 conv.harvest_len_range／conv.harvest_excluded 结构化 token／文档名 g.canon／已就地标注
或术语表定义的专名），每过滤器 first-match 记数、构成不重叠分区。排序=(文档数, 频次) 降序、
同分词典序（golden 定序）；输出经 entity_model.emit（禁时间戳/绝对路径，DG-9 字节可复现）。

schema 常量取 entity_model（SCHEMA_VERSION/HARVEST_ALGO/emit）；项目约定一律取 conv
（harvest_len_range/harvest_excluded/term_inplace/term_glossary，DG-33 单一事实源，不硬编码）。
冻结签名=cmd_harvest(g, conv, as_json, baseline)。
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import corpus
import entity_model
import i18n

# 候选抽取：粗体 **…** 与反引号 `…`（非贪婪，逐行 finditer）
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
# 通用 markdown 标题（提取标题正文供 conv.is_glossary_heading；节语境跟踪）
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
# 清洗 strip 字符集=首尾空白与包裹标点；不含 - _（标识符字符保留）、不含 |（走丢弃判定）
_STRIP = " \t\r\n`*\"'“”‘’「」『』()（）[]【】{}<>《》〈〉。.,，、;；:：!！?？…—·~～/\\"

# 过滤器键（顺序=罗列序；first-match 记数，构成不重叠分区）。名称固定短描述，稳定入 golden。
F_LEN, F_EXCLUDE, F_DOCNAME, F_TERM = (
    "长度越界", "结构化token", "文档名", "已标注专名")


def _norm_docs(g, conv):
    """产出 (rel, body_start, lines)：doc 级性质=规范 的文档（DG-25 harvest 源；正文=行号 > body_start）。
    删除线跨度先置空（EG-11-AC5：~~X-06~~ 型不作候选、不污染频次）。"""
    for rel, text in g.texts.items():
        if corpus.doc_nature(g.docs[rel]["meta"], conv) != "规范":
            continue
        clean = corpus.strip_strikethrough(text)
        yield rel, g.docs[rel]["body_start"], clean.splitlines()


def _annotated_terms(g, conv):
    """已标注专名集=就地标注 `**X**（定义：<锚>）`（**任意语境**，确定标记）∪ 术语表行 `**X**：<正文>`
    （**仅术语表节内**，conv.is_glossary_heading 判节标题）的专名名。散文里 `**X**：` 海量（如
    「**否定凭据**：指…」在散文/列表随处可现），无条件套 term_glossary 会误当已标注→漏出合法候选；
    故 glossary 须节语境约束（DG-27 订正，与 conv.is_glossary_heading 一致），term_inplace 不受限。
    在任一文档标注过即「已标注」（跨规范/记述/unknown 都算，删除线内不算）——候选据此剔除。"""
    terms = set()
    for rel, text in g.texts.items():
        in_glossary = False                              # 逐文档重置；标题切节即更新
        for ln in corpus.strip_strikethrough(text).splitlines():
            hm = _HEADING_RE.match(ln)
            if hm:                                       # 进入新节：术语表节则本节 term_glossary 生效
                in_glossary = conv.is_glossary_heading(hm.group(1))
            for mi in conv.term_inplace.finditer(ln):    # 就地标注：任意语境，一行可多个
                terms.add(mi.group(1))
            if in_glossary:                              # 术语表行：仅术语表节内算，一行至多一个
                mg = conv.term_glossary.match(ln)
                if mg:
                    terms.add(mg.group(1))
    return terms


def _tokens(line):
    """一行内粗体/反引号原始 token（未清洗）。"""
    for rx in (_BOLD_RE, _CODE_RE):
        for m in rx.finditer(line):
            yield m.group(1)


def _clean(raw):
    """strip 首尾标点；空/含管道符/含 markdown 链接 → None（清洗丢弃，不计过滤器）。"""
    w = raw.strip(_STRIP)
    if not w or "|" in w or "](" in w:
        return None
    return w


def _harvest(g, conv):
    """单遍扫描 → (已定序 candidates, filtered 计数, 规范源篇数)。"""
    lo, hi = conv.harvest_len_range
    terms = _annotated_terms(g, conv)
    filtered = {F_LEN: 0, F_EXCLUDE: 0, F_DOCNAME: 0, F_TERM: 0}
    docs = defaultdict(set)       # word → {rel}（文档数）
    freq = defaultdict(int)       # word → 总频次
    exemplar = defaultdict(list)  # word → [file:line]（≤3，去重）
    src = 0
    for rel, body_start, lines in _norm_docs(g, conv):
        src += 1
        for i, ln in enumerate(lines, 1):
            if i <= body_start:
                continue
            for raw in _tokens(ln):
                w = _clean(raw)
                if w is None:
                    continue
                if not (lo <= len(w) <= hi):
                    filtered[F_LEN] += 1
                    continue
                if conv.harvest_excluded(w):
                    filtered[F_EXCLUDE] += 1
                    continue
                if g.canon(w)[0] is not None:                 # 文档名/别名/候选名
                    filtered[F_DOCNAME] += 1
                    continue
                if w in terms:                                # 已就地标注/术语表定义
                    filtered[F_TERM] += 1
                    continue
                docs[w].add(rel)
                freq[w] += 1
                ref = f"{rel}:{i}"
                if len(exemplar[w]) < 3 and ref not in exemplar[w]:
                    exemplar[w].append(ref)
    cands = [{"word": w, "docs": len(docs[w]), "freq": freq[w], "examples": exemplar[w]}
             for w in docs]
    cands.sort(key=lambda c: (-c["docs"], -c["freq"], c["word"]))   # 降序 + 词典序兜底
    return cands, filtered, src


def _load_baseline(path):
    """读上次 harvest --json 的候选词集；不存在/不可解析→None（调用方按无 baseline 运行）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {c["word"] for c in data["candidates"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ---------------- 人读表格（CJK 宽度对齐；JSON 才是字节权威） ----------------

def _w(s):
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def _pad(s, n):
    return s + " " * max(0, n - _w(s))


def _rows(title, rows, cap=40):
    print(f"\n[{title}]")
    if not rows:
        print("  （无）")
        return
    for c in rows[:cap]:
        print(f"  {_pad(c['word'], 24)} {c['docs']:>3} {c['freq']:>4}  {'、'.join(c['examples'])}")
    if len(rows) > cap:
        print(f"  … 另 {len(rows) - cap} 项（--json 看全量）")


def cmd_harvest(g, conv, as_json, baseline):
    """未标注高频词提示（冻结签名；baseline=--baseline 值＝上次 harvest --json 文件路径，可空）。"""
    cands, filtered, src = _harvest(g, conv)

    base = None
    if baseline:
        base = _load_baseline(baseline)
        if base is None:
            print(f"--baseline 无法读取/解析：{baseline}（按无 baseline 运行）", file=sys.stderr)
    if base is not None:
        for c in cands:
            c["baseline"] = "既有" if c["word"] in base else "新增"

    data = {"schema_version": entity_model.SCHEMA_VERSION,
            "algo": entity_model.HARVEST_ALGO,
            "filtered": filtered, "candidates": cands}
    data = {"context_manifest": entity_model.context_manifest(  # DG-43
        "worktree", conv, "harvest", body=data,
        include_archived=getattr(g, "include_archived", False)), **data}
    if as_json:
        print(entity_model.emit(data))
        return 0
    if i18n.language() == "en":
        print(i18n.render_public(data))
        return 0

    stat = "  ".join(f"{k}×{v}" for k, v in filtered.items())
    print(f"过滤 {stat}；未标注高频词候选 {len(cands)} 个（规范源 {src} 篇，算法 {data['algo']}）")
    if base is not None:                                       # 分节：新增在前
        new = [c for c in cands if c["baseline"] == "新增"]
        old = [c for c in cands if c["baseline"] == "既有"]
        _rows(f"新增 {len(new)}", new)
        _rows(f"既有 {len(old)}", old)
    else:
        _rows("候选 前40（词/文档数/频次/出处样例）", cands)
    print("\n提示级：候选=该就地标注 `**X**（定义：<锚>）` 或术语表却没写的高频词；--json 看全量")
    return 0
