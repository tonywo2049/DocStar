#!/usr/bin/env python3
"""entity_extract — entity/edge extraction pipeline and eg-3 dump output.

schema 唯一权威 = entity_model（表A/B 代码化，本文件不自立 schema 常量）；项目约定唯一来自
conv（entity_model 已无项目常量——命名空间锚/定义形/形态表头/harvest 过滤全经 conv）。

The current engine replaces the retired eg-1 registry/corpus-tier implementation:
  · 删 tier 体系 → `性质`（判定参与开关，EG-D10）；删 include_examples；删 registry
  · 删边：定义于（降 entity.primary，DG-20）/约束/依据/散文修订声明/弱共现
  · 加边：阅读依赖(任务→节条目)/前置依赖(任务→任务)/provenance(记述→AC/节/参数)（EG-12-AC1/2/4）
  · 块内引用 → 共现索引（正名，限 ID 形实体，EG-2-AC9）
  · 专名：conv.term_inplace/term_glossary 就地标注（DG-27，primary=定义行+attrs.定义锚），非登记册
  · consumers 由 EDGE_TYPES schema 经 make_edge 自动填（DG-24，抽取器不填）
  · 形态自识别：conv.is_ledger_doc / is_changelist_header 替 EC 白名单（DG-25）
  · 命名空间：带固定锚 kind 经 conv.namespace_for 建键；裸 ID 经 corpus.resolve_namespace（DG-28）

架构（两遍）：pass① _scan 单遍行扫描收位点；pass② _entities 装配实体+性质+状态；pass③ _edges
装配内置边（全经 make_edge，端点封闭由 model 把守）。输出确定性（entity_sort_key/edge_sort_key）。

接口：build(g, conv)→{"entities","edges","reports"}；cmd_dump(g, conv, as_json)。
注：设计 §6 旧写 build(g)/sections(g) 未带 conv——entity_model 纯 schema 化后 conv 必传，
docstar.py 冻结签名 cmd_dump(g,conv,as_json)/entity_check.sections(g,conv) 已按此，build 随之带 conv。
"""

import posixpath
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

import corpus
import entity_model as M
import i18n

# ================ 抽取用正则（抽取机制，非项目 schema——项目 schema 一律走 conv） ================
_L = r"(?<![A-Za-z0-9_])"
_R = r"(?![A-Za-z0-9_])"
ANY_AC_RE = re.compile(_L + r"(?:R\d+-AC\d+|C\d+-AC\d+|AUD-AC\d+)" + _R)
# AC 缩写紧凑记法展开（DG-16 保留）：如 X2-AC9/AC15、X1-AC17..19、R1-AC1/2/4/5（前缀经 ac_prefix_kinds 归类）
AC_EXPAND_RE = re.compile(
    _L + r"(R\d+|C\d+|AUD)-AC(\d+)((?:\s*(?:/|、|\.\.)\s*(?:AC)?\d+)*)" + _R)
RVER_RE = re.compile(_L + r"r\d+(?:\.\d+)?(?![0-9.])")      # r 版本（边属性域）
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TICK_RE = re.compile(r"`([^`]+)`")
TEST_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")            # snake_case（准入还须含 "_"）
AC_PREFIX_TEST_RE = re.compile(r"^ac_r(\d+)_ac(\d+)_")     # 验证声明单一 canonical（DG-24）
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MAP_ROW_RE = re.compile(r"^\|\s*(R\d+-AC\d+)\s*\|")        # 映射表行
# 裸 R/D/M 定义列表项（修订清单「- R5：…」型）：局部序号，与需求/决议/里程碑全局歧义（EG-12-AC5）
BARE_LOCAL_RE = re.compile(r"^-\s*([RDM]\d+)\s*[：:、]")
# 任务前置列 ID（含 T0.*/TA*/TG.*/T*.*）；范围 TA{maj}.{a}..{b} 先展开
TASK_ID_RE = re.compile(_L + r"(?:TA\d+(?:\.\d+)?[a-z]?|TG\.\d+[a-z]?|T\d+(?:\.\d+)?[a-z]?)" + _R)
TASK_RANGE_RE = re.compile(r"(TA?\d+)\.(\d+)\.\.(\d+)")
# § 引用：可选前缀词 + § + 锚（含子锚尾 7(a)/7-4(b)/2.1-4；归一走 normalize_anchor）
SECREF_RE = re.compile(
    r"(?:([A-Za-z0-9一-鿿][A-Za-z0-9一-鿿.+_-]{0,29})[ \t]*)?"
    r"§[ \t]*(\d+[A-Z]?(?:\.\d+)*(?:(?:[-–]\d+[a-zA-Z]?)|(?:\([a-zA-Z0-9]+\)))*)")

# 项目专有抽取形（评审项 ID 形 review_item / 决策记录表行 option_rows / 记述引用句式 prov_form）
# 及其 kind 归类（id_occ_kinds / cooccur_kinds / ac_prefix_kinds）皆已迁 conventions（DG-38 波12-块1，
# 单一事实源）；通用/精简约定集缺席即休眠。取用须容缺不崩。

_NO_MATCH = re.compile(r"(?!)")                       # 永不匹配（缺 def_form 时的哨兵）
def _df(conv, kind):
    return conv.def_forms.get(kind, _NO_MATCH)


# ---------------- 键构造（带固定锚经 conv；泛化经 key_*） ----------------

def _ac_key(conv, acid):
    """单元格内裸 AC id → 主键 tuple：首字符经 conv.ac_prefix_kinds 归类 kind，再 namespace_for 取锚；
    kind 无映射或命名空间无法定（如未知前缀）→ None，不建。"""
    kind = conv.ac_prefix_kinds.get(acid[0])
    if not kind:
        return None
    ns = conv.namespace_for(kind, acid)
    return (kind, ns, acid) if ns else None


def _def_key(conv, kind, cid):
    """def_form 命中 (已知 kind, cid) → 主键：参数用「全局」占位锚，其余经 namespace_for；无锚→None。"""
    if kind == "参数":
        return tuple(M.key_param(cid))
    ns = conv.namespace_for(kind, cid)
    return (kind, ns, cid) if ns else None


def _doc_role_match(role, rel, conv, g):
    """option_rows 的 doc 角色限定：role∈{req_doc/param_registry/task_doc/mapping_doc}→比对对应角色文档；
    None→任意文档生效。"""
    if role is None:
        return True
    if role == "req_doc":
        return _stem_is(rel, conv.req_doc)
    if role == "param_registry":
        return _stem_is(rel, conv.param_registry)
    if role == "task_doc":
        return g.docs[rel]["stem"] == conv.task_doc_stem
    if role == "mapping_doc":
        return g.docs[rel]["stem"] == conv.mapping_doc_stem
    return False


def _stem_is(rel, name):
    """rel 的 stem == name 的 stem（扫描根无关；name 可带 .md 后缀）。"""
    return Path(rel).stem == Path(name).stem


# ---------------- 语料原语 ----------------

def _split_row(ln):
    return [c.strip() for c in ln.strip().strip("|").split("|")]


def _is_sep(cells):
    return bool(cells) and all(set(c) <= set("-: ") for c in cells) and any(cells)


def _cell_acs(text, expand=False):
    """单元格内 AC id 序列 → [(acid, 展开原文|None)]，序保持去重。
    expand=True 仅限专用表格通道（映射/任务 spec/底账/清单）：缩写形按前缀展开。"""
    out, seen = [], set()
    if not expand:
        for m in ANY_AC_RE.finditer(text):
            if m.group(0) not in seen:
                seen.add(m.group(0))
                out.append((m.group(0), None))
        return out
    for m in AC_EXPAND_RE.finditer(text):
        pre, first, tail = m.group(1), m.group(2), m.group(3)
        raw = m.group(0) if tail else None
        ids = [(f"{pre}-AC{first}", None)]
        prev = int(first)
        for sep, num in re.findall(r"(/|、|\.\.)\s*(?:AC)?(\d+)", tail or ""):
            n = int(num)
            if sep == "..":
                ids += [(f"{pre}-AC{k}", raw) for k in range(prev + 1, n + 1)]
            else:
                ids.append((f"{pre}-AC{n}", raw))
            prev = n
        for acid, r in ids:
            if acid not in seen:
                seen.add(acid)
                out.append((acid, r))
    return out


def _resolve_secref_doc(g, own_rel, word):
    """§ 前缀词 → 目标文档 rel。无词/自指→本文档；canon 命中→目标；
    canon 后缀匹配够不到的缩写（「design」←「module-a-design」）→ stem 含 word 的候选 + same_dir_pick 消歧
    （§引用文档消歧，corpus.same_dir_pick，DG-28 注）；仍未解析且含 ASCII（外源名）→ None；
    未解析纯中文（见/详见）→ 本文档。"""
    if not word:
        return own_rel
    _cn, dst = g.canon(word)
    if dst:
        return dst
    cands = sorted(rel for rel, d in g.docs.items() if word in d["stem"])
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        pick = corpus.same_dir_pick(cands, own_rel)
        if pick:
            return pick
    if re.search(r"[A-Za-z0-9]", word):
        return None
    return own_rel


def _scan_refs(g, own_rel, text, sticky=False):
    """text 内 § 引用序列 → (refs, unresolved)。
    refs=[(target_rel, 归一锚, 原始锚|None, 原文)]；紧邻接续继承前一目标文档，
    sticky=True（清单落点格）时前缀在整格内粘滞。"""
    refs, unresolved = [], []
    last_rel, last_end = None, None
    for m in SECREF_RE.finditer(text):
        word, raw = m.group(1), m.group(2)
        mtext = (word + " " if word else "") + "§" + raw
        if word:
            rel = _resolve_secref_doc(g, own_rel, word)
            if rel is None:
                unresolved.append(mtext)
                last_rel, last_end = None, m.end()
                continue
            cur = rel
        else:
            gap = text[last_end:m.start()] if last_end is not None else None
            if last_rel and (sticky or (gap is not None and len(gap) <= 1
                                        and gap in ("", "/", "、", "+", "＋"))):
                cur = last_rel
            else:
                cur = own_rel
        norm, orig = M.normalize_anchor(raw)
        if norm:
            refs.append((cur, norm, orig, mtext))
        last_rel, last_end = cur, m.end()
    return refs, unresolved


def _expand_task_ids(cell):
    """前置列任务 ID 序列（范围 TA1.1..1.5 先展开）→ 去重保序 list。"""
    def _sub(m):
        maj, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        return " ".join(f"{maj}.{k}" for k in range(a, b + 1))
    text = TASK_RANGE_RE.sub(_sub, cell)
    out, seen = [], set()
    for m in TASK_ID_RE.finditer(text):
        t = m.group(0)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ================ 性质（判定参与开关）作用域（EG-11-AC3；extract 的活，corpus 给点声明） ================

def _line_natures(lines, docnat, overrides):
    """标题层级栈实现节级性质作用域：某节的覆盖延至下一同级/更浅标题；内层覆盖外层。
    返回 line_no→性质。overrides={标题锚:性质}（corpus.section_nature_overrides 产）。"""
    res, stack = {}, []            # stack=[(depth, 性质)]
    for i, ln in enumerate(lines, 1):
        hm = M.ENTITY_HEADING_RE.match(ln)
        if hm:
            depth, anchor = len(hm.group(1)), hm.group(2)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            nat = overrides.get(anchor)
            if nat:
                stack.append((depth, nat))
        res[i] = stack[-1][1] if stack else docnat
    return res


def _line_glossary(lines, conv):
    """术语表节作用域（DG-27 订正）：标题正文命中 conv.is_glossary_heading → 该节内 term_glossary
    生效。同标题层级栈；祖先任一为术语表节则本行属术语表节。返回 line_no→bool。
    通用标题栈（_ANY_HEADING_RE，不限数字锚——通用语料 `## Glossary` 无编号；K-shot 示例演练坐实缺口，
    与 _line_type_section 同法；项目专有数字锚标题作为其子集照常命中）。"""
    res, stack = {}, []            # stack=[(depth, is_glossary)]
    for i, ln in enumerate(lines, 1):
        hm = _ANY_HEADING_RE.match(ln)
        if hm:
            depth, title = len(hm.group(1)), hm.group(2)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, conv.is_glossary_heading(title)))
        res[i] = any(g for _d, g in stack)
    return res


# config-free 类型识别自然条目形（DG-37）：类型小节内 `- **X**` 加粗名列表项 → 该型实体，名字=X。
# 节级作用域抗洪水（同术语表机制）；仅未被 def_forms 命中的行兜底促。X≤80 字、不含 *。
_TYPE_ITEM_RE = re.compile(r"^\s*[-*+]\s+\*\*([^*\n]{1,80}?)\*\*")
# 通用标题（任意 `## 文字`，不要求数字锚——类型小节按标题文字命名，非项目专有数字编号）。
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
_HTML_ANCHOR_RE = re.compile(
    r"<a\s+[^>]*(?:id|name)\s*=\s*(['\"])([^'\"]+)\1[^>]*>", re.I)


def _line_type_section(lines, conv):
    """config-free 类型小节作用域（DG-37）：标题命中 conv.type_of_heading → 该节内行属该 kind。
    通用标题栈（不限数字锚——类型节按文字命名如 `## 需求`/`## Requirements`）；取最近的有类型祖先
    （非类型子标题继承父型）。返回 line_no→kind|None。未配置 type_sections→恒 None（特性关闭）。"""
    res, stack = {}, []            # stack=[(depth, kind|None)]
    for i, ln in enumerate(lines, 1):
        hm = _ANY_HEADING_RE.match(ln)
        if hm:
            depth, title = len(hm.group(1)), hm.group(2)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, conv.type_of_heading(title)))
        res[i] = next((k for _d, k in reversed(stack) if k), None)
    return res


# ================ pass① 位点容器 ================

class _Sites:
    def __init__(self):
        self.def_sites = defaultdict(list)   # 实体key -> [(rel,line)]（定义形行；含 option_rows 行形）
        self.sec_sites = defaultdict(list)   # (stem,anchor) -> [(rel,line,line_end,raw)]
        self.term_sites = defaultdict(list)  # (stem,name) -> [(rel,line,定义锚|None)]（专名 DG-27）
        self.review_sites = defaultdict(list)  # (stem,cid) -> [(rel,line)]（review_item 登记源 ID 形）
        self.test_sites = defaultdict(list)  # name -> [(rel,line)]
        self.task_rows = []                  # (rel,line,tid,spec_cell,prereq_cell,red_tokens,状态)
        self.map_rows = []                   # (rel,line,req_acid,[(cid,展开)])
        self.ledger_rows = []                # (rel,line,日期,r版本,targets,引用集,摘要)
        self.decl_rows = []                  # (rel,line,src_key,targets,落点原文)
        self.ver_a = []                      # (rel,line,name,acid)
        self.cooccur = []                    # (rel,line,owner_key,[(kind,idkey)])
        self.prov_sites = []                 # (rel,line,src_key,[(kind,dstkey,原文)])
        self.natures = {}                    # rel -> {line: 性质}
        self.docnat = {}                     # rel -> 文档性质
        self.striplines = {}                 # rel -> 剥删除线后的行（EG-11-AC5 实体侧过滤用）
        self.unresolved = []                 # (来源符号, 期望token, rel, line, 规则)（EG-15/DG-42 携溯源+诊断型）
        self.ambiguous = []                  # (来源符号, rel, line)（EG-12-AC5/DG-42 ambiguous_reference）
        self.execution_links = []            # 已验证 (task_key, log_key, event_key, pointer rel/line)
        self.execution_entities = {}         # key -> 实体骨架（执行日志 frontmatter / latest event 块）
        self.execution_diags = []            # task execution 指针失败（配置启用时显式报告）


def _plain_pointer_cell(value):
    """表格 card_id 单元格去最外层轻量 Markdown 标记；不从散文猜 ID。"""
    s = re.sub(r"<a\b[^>]*>\s*</a>", "", value, flags=re.I).strip()
    m = _MD_LINK_RE.fullmatch(s)
    if m:
        s = m.group(1).strip()
    if len(s) >= 2 and s[0] == s[-1] == "`":
        s = s[1:-1].strip()
    if len(s) >= 4 and s.startswith("**") and s.endswith("**"):
        s = s[2:-2].strip()
    return s


def _pointer_value(value):
    """→ ('none',None,None) | ('link',label,href) | ('invalid',None,None)。只认真实 Markdown 链接。"""
    s = value.strip().strip(".;；。")
    if re.match(r"^(?:`?none`?|`?无`?)(?:$|[\s（(])", s, re.I):
        return "none", None, None
    m = _MD_LINK_RE.fullmatch(s)
    if not m:
        return "invalid", None, None
    href = m.group(2).strip()
    if href.startswith("<") and href.endswith(">"):
        href = href[1:-1].strip()
    if not href or any(ch.isspace() for ch in href):
        return "invalid", None, None
    return "link", m.group(1).strip(), href


def _resolve_execution_href(own_rel, href):
    """相对 Markdown href → (语料相对目标, fragment)|None。拒绝 URL、绝对路径、查询串和越界。"""
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or parsed.query or not parsed.path or parsed.path.startswith("/"):
        return None
    path = unquote(parsed.path)
    if not path.casefold().endswith(".md"):
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(own_rel), path))
    if target == ".." or target.startswith("../"):
        return None
    return target, unquote(parsed.fragment)


def _heading_slug(title):
    """GFM 常用标题锚的确定性子集；显式 HTML id 仍优先。"""
    text = re.sub(r"<[^>]+>", "", title).strip().casefold()
    text = re.sub(r"[^\w\-\s\u4e00-\u9fff]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text).strip("-")


def _mask_html_comments(text):
    """HTML comment 全跨度置空且保换行/列，避免注释内伪锚改变溯源行号。"""
    return re.sub(
        r"<!--.*?(?:-->|$)",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        text,
        flags=re.S,
    )


def _event_primary(lines, anchor):
    """定位 latest_event 锚并返回事件 heading 块；代码与 HTML comment 内伪锚不参与。"""
    heading_text = _mask_html_comments(
        corpus.code_mask("\n".join(lines), mask_inline=False))
    heading_lines = heading_text.split("\n")
    explicit_lines = corpus.code_mask(heading_text, mask_inline=True).split("\n")
    explicit, headings = [], []
    for i, line in enumerate(heading_lines, 1):
        for m in _HTML_ANCHOR_RE.finditer(explicit_lines[i - 1]):
            if m.group(2) == anchor:
                explicit.append(i)
        hm = _ANY_HEADING_RE.match(line)
        if hm:
            headings.append((i, len(hm.group(1)), hm.group(2)))
    if explicit:
        anchor_line = explicit[0]
        next_nonblank = next((i for i in range(anchor_line + 1, len(heading_lines) + 1)
                              if heading_lines[i - 1].strip()), None)
        start = (next_nonblank if next_nonblank is not None
                 and any(line == next_nonblank for line, _depth, _title in headings)
                 else anchor_line)
    else:
        start = next((line for line, _depth, title in headings if _heading_slug(title) == anchor), None)
    if start is None:
        return None
    heading = next(((line, depth) for line, depth, _title in headings if line == start), None)
    if heading:
        _line, depth = heading
        end = next((line - 1 for line, d, _title in headings if line > start and d <= depth),
                   len(heading_lines))
    else:
        end = next((line - 1 for line, _d, _title in headings if line > start),
                   len(heading_lines))
    return {"line": start, "line_end": end}


def _meta_first(meta, key):
    values = meta.get(key, []) if isinstance(meta, dict) else []
    return values[0].strip() if isinstance(values, list) and values else ""


def _execution_pointer_columns(cells, cfg):
    """配置表头别名命中三角色时返回列索引；否则 None。"""
    if cfg is None:
        return None
    alias_roles = {name.casefold(): role
                   for role, names in cfg["pointer_columns"].items() for name in names}
    roles = [alias_roles.get(_plain_pointer_cell(cell).casefold()) for cell in cells]
    required = ("card_id", "execution_log", "latest_event")
    if not all(role in roles for role in required):
        return None
    return {role: roles.index(role) for role in required}


def _scan_task_execution(g, S, conv):
    """配置启用时，从 Task pointer table 或当前卡字段收集并验证两跳执行关系。"""
    cfg = conv.task_execution
    if cfg is None:
        return
    task_ids_by_rel = defaultdict(set)
    for rel, _line, tid, *_rest in S.task_rows:
        task_ids_by_rel[rel].add(tid)
    if not task_ids_by_rel:
        return
    field_aliases = cfg["card_fields"]
    pointers = defaultdict(list)

    def field_value(block, names):
        invalid_line = None
        for line_no, line, raw_line in block:
            for name in names:
                marker = re.compile(r"(?<![A-Za-z0-9_])(?:`|\*\*)?" + re.escape(name)
                                    + r"(?:`|\*\*)?\s*(?:=|:|：)\s*", re.I)
                m = marker.search(line)
                if not m:
                    # 注释内形不参与抽取，但保留一次明确的坏声明诊断和原始行号。
                    if raw_line != line and marker.search(raw_line) and invalid_line is None:
                        invalid_line = line_no
                    continue
                tail = line[m.end():]
                lm = _MD_LINK_RE.match(tail)
                if lm:
                    link_start, link_end = m.end() + lm.start(), m.end() + lm.end()
                    inline_masked = corpus.code_mask(line, mask_inline=True)
                    # 仅字段名代码化合法；链接落在代码 span 内表示整条赋值或链接只是示例。
                    if inline_masked[link_start:link_end] != line[link_start:link_end]:
                        invalid_line = invalid_line or line_no
                        continue
                    return line_no, _pointer_value(lm.group(0))
                token = re.match(r"`?(?:none|无)`?", tail, re.I)
                if token:
                    # `none`/`无` 不可能成图；允许既有聚合 code span 把“尚无历史”写成
                    # execution_log=none，避免把安全的显式空值误报成伪链接。
                    return line_no, _pointer_value(token.group(0))
                invalid_line = invalid_line or line_no
        return ((invalid_line, ("invalid", None, None))
                if invalid_line is not None else (None, None))

    for rel in sorted(task_ids_by_rel):
        local_task_ids = task_ids_by_rel[rel]
        lines = S.striplines.get(rel, [])
        raw_scan_lines = corpus.code_mask("\n".join(lines), mask_inline=False).split("\n")
        scan_lines = _mask_html_comments("\n".join(raw_scan_lines)).split("\n")
        table_header = None
        for i, line in enumerate(scan_lines, 1):
            if not line.startswith("|"):
                table_header = None
                continue
            cells = _split_row(line)
            if _is_sep(cells):
                continue
            pointer_columns = _execution_pointer_columns(cells, cfg)
            if pointer_columns is not None:
                table_header = pointer_columns
                continue
            if table_header is None:
                continue
            tid_i, log_i, event_i = (table_header[k] for k in
                                     ("card_id", "execution_log", "latest_event"))
            tid = _plain_pointer_cell(cells[tid_i] if tid_i < len(cells) else "")
            if tid not in local_task_ids:
                continue
            pointers[tid].append((rel, i,
                                  _pointer_value(cells[log_i] if log_i < len(cells) else ""),
                                  _pointer_value(cells[event_i] if event_i < len(cells) else "")))

        headings = []
        for i, line in enumerate(scan_lines, 1):
            hm = _ANY_HEADING_RE.match(line)
            if hm:
                headings.append((i, len(hm.group(1)), hm.group(2)))
        for idx, (start, depth, title) in enumerate(headings):
            hits = [tid for tid in local_task_ids
                    if re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(tid)
                                 + r"(?![A-Za-z0-9_.-])", title)]
            if len(hits) != 1:
                continue
            end = next((line - 1 for line, d, _t in headings[idx + 1:] if d <= depth), len(scan_lines))
            block = [(line_no, scan_lines[line_no - 1], raw_scan_lines[line_no - 1])
                     for line_no in range(start + 1, end + 1)]
            log_line, log_val = field_value(block, field_aliases["execution_log"])
            event_line, event_val = field_value(block, field_aliases["latest_event"])
            if log_val is not None or event_val is not None:
                source_line = min(x for x in (log_line, event_line) if x is not None)
                pointers[hits[0]].append((rel, source_line,
                                          log_val or ("invalid", None, None),
                                          event_val or ("invalid", None, None)))

    def diagnostic(tid, rel, line, reason, target=None):
        S.execution_diags.append({"task": tid, "file": rel, "line": line,
                                  "reason": reason, "target": target})

    for tid in sorted(pointers):
        entries = sorted(pointers[tid], key=lambda x: (x[0], x[1]))
        # 链接 label 仅展示，不参与目标一致性；同 href 的表格/卡片双投影视为同一指针。
        signatures = {(x[2][0], x[2][2], x[3][0], x[3][2]) for x in entries}
        rel, line, log_value, event_value = entries[-1]
        if len(signatures) > 1:
            diagnostic(tid, rel, line, "conflicting_pointers")
            continue
        if log_value[0] == event_value[0] == "none":
            continue
        if log_value[0] != "link" or event_value[0] != "link":
            diagnostic(tid, rel, line, "invalid_pointer")
            continue
        log_resolved = _resolve_execution_href(rel, log_value[2])
        event_resolved = _resolve_execution_href(rel, event_value[2])
        if log_resolved is None or event_resolved is None:
            diagnostic(tid, rel, line, "invalid_relative_markdown_link")
            continue
        log_rel, log_fragment = log_resolved
        event_rel, event_anchor = event_resolved
        if log_fragment or not event_anchor or event_rel != log_rel:
            diagnostic(tid, rel, line, "pointer_target_mismatch", event_value[2])
            continue
        if log_rel not in g.docs:
            diagnostic(tid, rel, line, "log_target_missing", log_rel)
            continue
        if Path(log_rel).stem != tid:
            diagnostic(tid, rel, line, "card_log_id_mismatch", log_rel)
            continue
        meta = g.docs[log_rel]["meta"]
        if (_meta_first(meta, "type") != "execution-log"
                or _meta_first(meta, "nature") != "descriptive"):
            diagnostic(tid, rel, line, "invalid_log_metadata", log_rel)
            continue
        log_lines = S.striplines.get(log_rel, [])
        event_primary = _event_primary(log_lines, event_anchor)
        if event_primary is None:
            diagnostic(tid, rel, line, "latest_event_anchor_missing", event_value[2])
            continue

        task_key = ("任务", conv.namespace_for("任务", tid), tid)
        log_key = tuple(M.key_execution_log(log_rel))
        event_key = tuple(M.key_latest_event(log_rel, event_anchor))
        body_start = g.docs[log_rel]["body_start"]
        S.execution_entities[log_key] = {
            "key": list(log_key), "display": log_rel, "性质": "记述",
            "primary": {"doc": log_rel, "line": 1, "line_end": max(1, body_start)},
            "candidates": [], "状态": None, "attrs": {}}
        S.execution_entities[event_key] = {
            "key": list(event_key), "display": event_anchor, "性质": "记述",
            "primary": {"doc": log_rel, **event_primary}, "candidates": [],
            "状态": None, "attrs": {"锚": event_anchor}}
        S.execution_links.append((task_key, log_key, event_key, rel, line))


def _scan(g, conv):
    S = _Sites()
    scanned = set(g.docs)
    # 删除线剔除（EG-11-AC5）先行：全 doc 剥后行；实体/边/共现/位点一律基于剥后文本。
    # 落在 ~~…~~ span 内的 ID 出现（g.id_occ 未剥——docstar 层不剥）在此逐项剔除。
    for rel in scanned:
        t = g.texts.get(rel)
        if t is not None:
            S.striplines[rel] = corpus.strip_strikethrough(t).splitlines()
    strip = S.striplines
    # g.id_occ 复用（(rel,line)->[(ident,kind)]）：剥后行不含该 ident=删除线内=剔除
    occ_line = defaultdict(list)
    for ident in sorted(g.id_occ):
        k = g.id_kind[ident]
        for rel, line, _t in g.id_occ[ident]:
            sl = strip.get(rel)
            if sl and 1 <= line <= len(sl) and ident in sl[line - 1]:
                occ_line[(rel, line)].append((ident, k))
    S.occ_line = occ_line

    for rel in sorted(scanned):
        lines = strip.get(rel)
        if lines is None:
            continue
        stem = g.docs[rel]["stem"]
        docnat = corpus.doc_nature(g.docs[rel]["meta"], conv)
        overrides = corpus.section_nature_overrides(lines, M.ENTITY_HEADING_RE)
        S.docnat[rel] = docnat
        S.natures[rel] = _line_natures(lines, docnat, overrides)
        gloss = _line_glossary(lines, conv)          # 术语表节作用域（① term_glossary 门）
        typesec = _line_type_section(lines, conv)    # config-free 类型小节作用域（DG-37；未配置→全 None）

        is_task = stem == conv.task_doc_stem
        is_map = stem == conv.mapping_doc_stem
        is_ledger = conv.is_ledger_doc("\n".join(lines))  # 形态自识别（DG-25）：底账=conv.ledger_header 命中
        has_changelist = any(conv.is_changelist_header(ln) for ln in lines)
        is_review_src = has_changelist                # 登记源=登记/裁定块（清单形态；底账=修订日志非登记）
        # 项目专有抽取形（皆经 conv，缺→休眠）：review_item ID 形 / option_rows 表格行形
        review_form = conv.review_item["form"] if conv.review_item else None
        review_kind = conv.review_item["kind"] if conv.review_item else None
        option_rows_here = [o for o in conv.option_rows if _doc_role_match(o["doc"], rel, conv, g)]

        # 预扫：fence 行集 + 标题（任意标题=块边界 DG-4；节条目锚仅数字后缀 DG-11）
        fenced, headings, in_f = set(), [], False
        for i, ln in enumerate(lines, 1):
            if FENCE_RE.match(ln):
                in_f = not in_f
                fenced.add(i)
                continue
            if in_f:
                fenced.add(i)
                continue
            hm = re.match(r"^(#{1,6})\s", ln)
            if hm:
                em = M.ENTITY_HEADING_RE.match(ln)
                norm = raw = None
                if em:
                    norm, _o = M.normalize_anchor(em.group(2))
                    raw = em.group(2)
                headings.append((i, len(hm.group(1)), norm, raw))
        ends = {}
        for idx, (hl, hd, _n, _r) in enumerate(headings):
            end = len(lines)
            for jl, jd, _n2, _r2 in headings[idx + 1:]:
                if jd <= hd:
                    end = jl - 1
                    break
            ends[hl] = end
        for hl, _hd, norm, raw in headings:
            if norm:
                S.sec_sites[(stem, norm)].append((rel, hl, ends[hl], raw))

        # review_item（登记源文档内 conv.review_item.form 形全出现，namespace=登记源 stem）
        if is_review_src and review_form:
            for i, ln in enumerate(lines, 1):
                if i in fenced:
                    continue
                for mm in review_form.finditer(ln):
                    S.review_sites[(stem, mm.group(0))].append((rel, i))

        # 主循环
        hidx, stack = 0, []          # stack=[(depth, sec_key|None)]
        cur_task_hdr = None          # {"spec":i,"prereq":j|None,"red":k|None,"状态":s|None}
        execution_pointer_hdr = None # task_execution pointer table 列角色；启用时其数据行不走通用 def_forms
        in_ledger, decl_hdr = False, None   # decl_hdr={"落点":i,"项":0}

        def innermost():
            for _d, k in reversed(stack):
                if k:
                    return k
            return None

        def add_term(i, ln):
            """就地标注专名（DG-27）：inplace `**X**（定义：锚）` 有确定标记，任意语境；
            glossary `**X**：<定义正文>` 散文粗体海量误命中，故仅术语表节内生效（gloss[i]）。"""
            for m in conv.term_inplace.finditer(ln):
                S.term_sites[(stem, m.group(1))].append((rel, i, m.group(2)))
            if gloss.get(i):
                gm = conv.term_glossary.match(ln)
                if gm:
                    S.term_sites[(stem, gm.group(1))].append((rel, i, None))

        def add_ver(i, ln):
            """验证声明 (a)：ac_r{n}_ac{m}_ 前缀 → 测试实体 + 测试→AC（单一 canonical，DG-24）。
            前缀本身编码 AC，出现处即声明（含任务表红先列等表格单元格）。"""
            if "`" not in ln:
                return
            for tok in TICK_RE.findall(ln):
                pm = AC_PREFIX_TEST_RE.match(tok)
                if pm and TEST_NAME_RE.match(tok):
                    S.test_sites[tok].append((rel, i))
                    S.ver_a.append((rel, i, tok, f"R{pm.group(1)}-AC{pm.group(2)}"))

        def add_cooccur(i, owner_key):
            """共现索引（EG-2-AC9）：owner 与同行其它 ID 形实体精确共现。"""
            if owner_key is None:
                return
            peers = []
            for ident, dk in S.occ_line.get((rel, i), ()):
                mk = conv.id_occ_kinds.get(dk)
                if mk:
                    ns = conv.namespace_for(mk, ident)
                    if ns:
                        peers.append((mk, ns, ident))
                elif dk == "参数":
                    peers.append(tuple(M.key_param(ident)))
            for pk in peers:
                if pk != owner_key:
                    S.cooccur.append((rel, i, owner_key, tuple(pk)))

        def add_prov(i, ln):
            """provenance（EG-12-AC4）：记述固定引用形（conv.prov_form）→ 文档→AC/§/参数（consumers={}，不进门禁）。
            缺 prov_form→不抽 provenance（休眠）。"""
            if conv.prov_form is None:
                return
            pm = conv.prov_form.search(ln)
            if not pm:
                return
            tail = ln[pm.end():]
            dsts = []
            for acid, _e in _cell_acs(tail):
                k = _ac_key(conv, acid)
                if k:
                    dsts.append((k, acid))
            for trel, norm, _o, mtext in _scan_refs(g, rel, tail)[0]:
                sk = M.key_section(g.docs[trel]["stem"], norm)
                dsts.append((tuple(sk), mtext))
            for tm in TICK_RE.finditer(tail):
                tok = tm.group(1)
                if re.fullmatch(r"[A-Z]_[a-z][A-Za-z0-9_]*", tok):
                    dsts.append((tuple(M.key_param(tok)), tok))
            if dsts:
                S.prov_sites.append((rel, i, tuple(M.key_doc(rel)), dsts))

        for i, ln in enumerate(lines, 1):
            if i in fenced:
                in_ledger, decl_hdr, cur_task_hdr, execution_pointer_hdr = False, None, None, None
                continue
            # 标题行：更新节栈（需求R 折入 节条目——`### R{n}` 非数字锚，天然不产 节条目）
            if hidx < len(headings) and headings[hidx][0] == i:
                _hl, depth, norm, _raw = headings[hidx]
                hidx += 1
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                key = tuple(M.key_section(stem, norm)) if norm else None
                stack.append((depth, key))
                in_ledger, decl_hdr, cur_task_hdr, execution_pointer_hdr = False, None, None, None
                add_term(i, ln)
                add_ver(i, ln)
                add_cooccur(i, key or innermost())
                continue
            sec_key = innermost()
            if ln.startswith("|"):
                cells = _split_row(ln)
                sep = _is_sep(cells)
                task_m = _df(conv, "任务").match(ln)
                # ---- 表头识别 ----
                if not task_m and not sep:
                    pointer_columns = _execution_pointer_columns(cells, conv.task_execution)
                    if pointer_columns is not None:
                        execution_pointer_hdr = pointer_columns
                        cur_task_hdr = None
                        continue
                    if is_ledger and conv.ledger_header.match(ln):  # 表头=conv.ledger_header 单源（DG-52）
                        in_ledger, decl_hdr = True, None
                        continue
                    if conv.is_changelist_header(ln):
                        落点列 = next((ci for ci, c in enumerate(cells)
                                      if "落点" in c), 1)
                        decl_hdr = {"落点": 落点列}
                        in_ledger = False
                        continue
                    if is_task and cells and cells[0] == "#" and conv.task_columns["spec"] in cells:
                        tcols = conv.task_columns   # 表头列名=conv.task_columns 单源（DG-54，沿 DG-52）
                        cur_task_hdr = {
                            "spec": cells.index(tcols["spec"]),
                            "prereq": cells.index(tcols["prereq"]) if tcols["prereq"] in cells else None,
                            "red": cells.index(tcols["red"]) if tcols["red"] in cells else None,
                            "状态": cells.index(tcols["status"]) if tcols["status"] in cells else None}
                        continue
                if sep:
                    continue
                if execution_pointer_hdr is not None:
                    continue
                # ---- 修订落账（DG-12）：底账数据行 ----
                if in_ledger:
                    c0, c1, c2 = (cells + ["", "", ""])[:3]
                    dm, vm = DATE_RE.search(c0), RVER_RE.search(c1)
                    targets = [("AC", acid, None, exp)
                               for acid, exp in _cell_acs(c1, expand=True)]
                    for trel, norm, orig, _mt in _scan_refs(g, rel, c1)[0]:
                        targets.append(("SEC", trel, norm, orig))
                    cite, cseen = [], set()
                    if review_form:
                        for cell in (c1, c2):
                            for mm in review_form.finditer(cell):
                                if mm.group(0) not in cseen:
                                    cseen.add(mm.group(0))
                                    cite.append(mm.group(0))
                    S.ledger_rows.append(
                        (rel, i, dm.group(0) if dm else c0, vm.group(0) if vm else None,
                         targets, cite, (c1[:80] + "…") if len(c1) > 80 else c1))
                    continue
                # ---- 修订声明（清单表数据行；源=review_item/节条目，端点封闭 EG-12） ----
                if decl_hdr is not None:
                    项 = cells[0] if cells else ""
                    落点 = cells[decl_hdr["落点"]] if decl_hdr["落点"] < len(cells) else ""
                    rm = review_form.search(项) if review_form else None
                    if rm:                                    # 项含 review_item ID → 源=该 kind 实体
                        src = (review_kind, stem, rm.group(0))
                        S.review_sites[(stem, rm.group(0))].append((rel, i))
                    elif "§" in 项:                            # 项含 § → 源=节条目
                        refs = _scan_refs(g, rel, 项)[0]
                        src = (tuple(M.key_section(g.docs[refs[0][0]]["stem"], refs[0][1]))
                               if refs else sec_key)
                    else:
                        src = sec_key                          # 兜底=所在节
                    targets = []
                    for cell in (落点, 项):
                        targets += [("AC", acid, None, exp)
                                    for acid, exp in _cell_acs(cell, expand=True)]
                    for cell in (落点, 项):
                        for trel, norm, orig, _mt in _scan_refs(g, rel, cell, sticky=True)[0]:
                            targets.append(("SEC", trel, norm, orig))
                    if src is not None:
                        S.decl_rows.append((rel, i, src, targets,
                                            (落点[:80] + "…") if len(落点) > 80 else 落点))
                    continue
                # ---- 定义形数据行（任务 def_form 带行抽取；其余表格 def_form + option_rows 行形，kind 经 conv） ----
                def_key = None
                if (task_m and conv.task_execution
                        and conv.task_execution["canonical_task_table_only"]
                        and not (is_task and cur_task_hdr)):
                    task_m = None
                if task_m:
                    tid = task_m.group(1)
                    tns = conv.namespace_for("任务", tid)
                    def_key = ("任务", tns, tid) if tns else None
                    if is_task and cur_task_hdr:
                        h = cur_task_hdr
                        spec_cell = cells[h["spec"]] if h["spec"] < len(cells) else ""
                        prereq_cell = (cells[h["prereq"]] if h["prereq"] is not None
                                       and h["prereq"] < len(cells) else "")
                        状态 = (cells[h["状态"]] if h["状态"] is not None
                               and h["状态"] < len(cells) else None)
                        red = []
                        if h["red"] is not None and h["red"] < len(cells):
                            for tok in TICK_RE.findall(cells[h["red"]]):
                                if "_" in tok and TEST_NAME_RE.match(tok):
                                    red.append(tok)
                                    S.test_sites[tok].append((rel, i))
                        S.task_rows.append((rel, i, tid, spec_cell, prereq_cell, red, 状态))
                else:
                    for k, cre in conv.def_forms.items():      # ^| 形 def_form 自选命中表行（^- 形不命中）
                        if k == "任务":
                            continue
                        dm = cre.match(ln)
                        if dm:
                            def_key = _def_key(conv, k, dm.group(1))
                            break
                    if def_key is None:                        # option_rows 表格行形自定义实体（如 D{n}→治理期权）
                        for opt in option_rows_here:
                            om = opt["row"].match(ln)
                            if om:
                                cid = om.expand(opt["id"])
                                ns = corpus.resolve_namespace(
                                    section_ns=conv.namespace_for(opt["kind"], cid))
                                if ns:
                                    def_key = (opt["kind"], ns, cid)
                                else:
                                    S.ambiguous.append((cid, rel, i))
                                break
                if def_key:
                    S.def_sites[def_key].append((rel, i))
                if is_map:
                    mm = MAP_ROW_RE.match(ln)
                    if mm:
                        cs = [(cid, exp) for cid, exp in _cell_acs(ln, expand=True)
                              if cid.startswith("C") and cid != mm.group(1)]
                        S.map_rows.append((rel, i, mm.group(1), cs))
                add_term(i, ln)
                add_ver(i, ln)
                add_cooccur(i, def_key or sec_key)
                add_prov(i, ln)
                continue
            # ---- 普通行 ----
            in_ledger, decl_hdr, cur_task_hdr, execution_pointer_hdr = False, None, None, None
            def_key = None
            for kind, cre in conv.def_forms.items():   # 列表形 def_form（^- 形命中普通行；^| 表格形不命中）
                if kind == "任务":                       # 任务只在表格行（带行抽取），普通行不促
                    continue
                dm = cre.match(ln)
                if dm:
                    def_key = _def_key(conv, kind, dm.group(1))
                    if def_key:
                        S.def_sites[def_key].append((rel, i))
                    break
            # config-free 类型小节兜底（DG-37）：typed 节内 `- **X**` 自然条目 → 该型实体（名字=X，
            # namespace=doc stem）。仅当本行未被 def_forms 命中（def_key None + X 非本型 def_forms ID）→
            # 不与 def_forms 重促；节级作用域抗洪水。未配置 type_sections→typesec 全 None→不触发。
            tkind = typesec.get(i)
            if tkind and def_key is None and conv.allows_type_section_definition(tkind):
                tim = _TYPE_ITEM_RE.match(ln)
                if tim:
                    tname = tim.group(1).strip()
                    dfx = conv.def_forms.get(tkind)
                    if tname and not (dfx and dfx.match(ln)):
                        S.def_sites[(tkind, stem, tname)].append((rel, i))
            # ④ 裸 R/D/M 定义列表项无表列/节/文档锚 → ambiguous_reference（EG-12-AC5 全局歧义降级）
            bm = BARE_LOCAL_RE.match(ln)
            if bm and corpus.resolve_namespace(
                    doc_ns=(g.docs[rel]["meta"].get("namespace") or [None])[0]) is None:
                S.ambiguous.append((bm.group(1), rel, i))
            add_term(i, ln)
            add_ver(i, ln)
            add_cooccur(i, def_key or sec_key)
            add_prov(i, ln)
    _scan_task_execution(g, S, conv)
    return S


# ================ pass② 实体装配（性质=判定参与开关；无 tier） ================

def _nature_at(S, rel, line):
    return S.natures.get(rel, {}).get(line, S.docnat.get(rel, "unknown"))


def _unstruck(S, rel, line, ident):
    """该 ID 出现是否在删除线 span 外（剥后行仍含 ident=幸存）。EG-11-AC5 实体侧过滤。"""
    sl = S.striplines.get(rel)
    return bool(sl) and 1 <= line <= len(sl) and ident in sl[line - 1]


def _entities(g, S, conv):
    ent = {}                       # key(tuple) -> 骨架
    reports = {k: [] for k in ("实体_重定义", "实体_无定义块", "实体_修订行未解析")}
    review_kind = conv.review_item["kind"] if conv.review_item else None
    # 报重定义/无定义块的 def 形 kind（配置驱动派生：有 def_form / 促成 id_occ 实体 / option_rows /
    # 单元格 AC 前缀归类的 kind，减去自有路径的 专名/文档/节条目/测试/review_item kind）
    report_kinds = ((set(conv.def_forms) | set(conv.id_occ_kinds.values())
                     | {o["kind"] for o in conv.option_rows} | set(conv.ac_prefix_kinds.values()))
                    - {"专名", "文档", "节条目", "测试"})
    if review_kind:
        report_kinds.discard(review_kind)
    # 配置启用并验证通过的执行日志/最新事件实体；task_execution 缺席时集合恒空。
    ent.update(S.execution_entities)

    def ensure(key, display, rel, line):
        e = ent.get(key)
        if e is None:
            ent[key] = e = {"key": list(key), "display": display,
                            "性质": "unknown", "primary": None,   # 占位；终值由 primary 回写统一定
                            "candidates": [], "状态": None, "attrs": {}}
        return e

    # ① id 形实体：全语料出现即建（EG-D6 投影；命名空间经 conv）——删除线内出现剔除（EG-11-AC5）
    for ident in sorted(g.id_occ):
        dk = g.id_kind[ident]
        occs = sorted((rel, l) for rel, l, _t in g.id_occ[ident]
                      if _unstruck(S, rel, l, ident))
        if not occs:
            continue
        mk = conv.id_occ_kinds.get(dk)
        if mk:
            ns = conv.namespace_for(mk, ident)
            if ns is None:
                continue
            key = (mk, ns, ident)
        elif dk == "参数":
            key = tuple(M.key_param(ident))
        else:
            continue
        for rel, l in occs:
            ensure(key, ident, rel, l)

    # ② 定义位点兜底（def 行但无 id 出现的稀见情形；option_rows 行形已并入 def_sites）
    for key, sites in S.def_sites.items():
        r0, l0 = min(sites)
        ensure(key, key[2], r0, l0)

    # ③ 节条目
    for (stem, anchor), sites in S.sec_sites.items():
        key = tuple(M.key_section(stem, anchor))
        r0, l0, _e0, _r = sites[0]
        ensure(key, key[2], r0, l0)
        raws = sorted({raw for _r, _l, _e, raw in sites if raw and raw != anchor})
        if raws:
            ent[key]["attrs"]["原始锚"] = raws

    # ④ review_item 实体（登记源准入；namespace=源 stem，kind 经 conv.review_item）
    for (stem, cid), occs in S.review_sites.items():
        key = (review_kind, stem, cid)
        r0, l0 = min(occs)
        ensure(key, cid, r0, l0)

    # ⑤ 测试（强声明上下文准入）
    for name, sites in S.test_sites.items():
        key = tuple(M.key_test(name))
        r0, l0 = min(sites)
        ensure(key, name, r0, l0)

    # ⑥ 专名（就地标注 DG-27；primary=定义行、attrs.定义锚）
    for (stem, name), sites in S.term_sites.items():
        key = tuple(M.key_term(stem, name))
        r0, l0, anchor = sorted(sites)[0]
        e = ensure(key, name, r0, l0)
        e["primary"] = {"doc": r0, "line": l0, "line_end": l0}
        if anchor:
            e["attrs"]["定义锚"] = anchor
            # 悬空定义锚（解析不到 节条目）→ unresolved_reference（EG-15/DG-29 定义端）
            refs = _scan_refs(g, r0, anchor)[0]
            hit = any(tuple(M.key_section(g.docs[tr]["stem"], nm)) in
                      {tuple(M.key_section(s, a)) for (s, a) in S.sec_sites}
                      for tr, nm, _o, _mt in refs)
            if not hit:
                S.unresolved.append((name, anchor, r0, l0, "term_anchor"))  # DG-42 规则标识（专名定义锚）

    # primary 选择（无 tier）：归属文档优先 → (路径,行号)；def 形 kind 报重定义/无定义块。
    # 通用角色文档（需求/参数/任务）按角色判归属；其余（含项目专有/开放 kind）按 stem 前缀匹配 ns。
    def home(key, rel):
        k, ns = key[0], key[1]
        if k == "需求AC":
            return _stem_is(rel, conv.req_doc)
        if k == "参数":
            return _stem_is(rel, conv.param_registry)
        if k == "任务":
            return g.docs[rel]["stem"] == conv.task_doc_stem
        return g.docs[rel]["stem"].startswith(ns)

    for key in sorted(ent):
        e, kind = ent[key], key[0]
        if kind in ("专名", "文档"):
            continue
        if kind == "节条目":
            sites = sorted(S.sec_sites.get((key[1], key[2].split("§", 1)[1]), ()),
                           key=lambda s: (0 if s[3] == key[2].split("§", 1)[1] else 1,
                                          s[0], s[1]))
            blocks = [{"doc": r, "line": l, "line_end": le} for r, l, le, _raw in sites]
            if blocks:
                e["primary"], e["candidates"] = blocks[0], blocks[1:]
            continue
        if review_kind and kind == review_kind:
            r, l = min(S.review_sites[(key[1], key[2])])
            e["primary"] = {"doc": r, "line": l, "line_end": l}
            continue
        if kind == "测试":
            r, l = min(S.test_sites[key[2]])
            e["primary"] = {"doc": r, "line": l, "line_end": l}
            continue
        # def 形 kind（含 option_rows 行形 kind）：多定义块→重定义；零定义块→无定义块
        sites = sorted(set(S.def_sites.get(key, ())),
                       key=lambda s: (0 if home(key, s[0]) else 1, s[0], s[1]))
        blocks = [{"doc": r, "line": l, "line_end": l} for r, l in sites]
        if blocks:
            e["primary"], e["candidates"] = blocks[0], blocks[1:]
        if kind in report_kinds:
            if e["primary"] is None:
                n_occ = len(g.id_occ.get(key[2], ()))
                r0, l0 = (min(g.id_occ[key[2]], key=lambda o: (o[0], o[1]))[:2]
                          if key[2] in g.id_occ else (key[1], 0))
                reports["实体_无定义块"].append(
                    {"key": list(key), "occurrences": n_occ, "首现": {"doc": r0, "line": l0}})
            if len(blocks) > 1:
                a = e["primary"]
                reports["实体_重定义"].append(
                    {"key": list(key), "primary": e["primary"],
                     "candidates": [{"doc": b["doc"], "line": b["line"]} for b in e["candidates"]],
                     "_sort": (a["doc"], a["line"])})

    # 性质随 primary 回写（EG-11-AC1 判定参与语义，2026-07-17 裁决①）：实体效力语境来自
    # primary 定义文档/节的性质，非首现行——首现黏连会让记述引用把规范实体漏出判定域（漏义务，
    # 违反 EG-11-AC2 保守侧）。无 primary（悬空占位）→ unknown（无定义可依，保守进域）。
    # 专名/测试/review_item 的 primary 与首现同址，回写幂等；节条目错位面（精确锚优先）一并修正。
    for e in ent.values():
        p = e["primary"]
        e["性质"] = _nature_at(S, p["doc"], p["line"]) if p else "unknown"

    # 状态属性（EG-12-AC3）：任务表 状态列 → 任务实体
    for rel, line, tid, _spec, _pre, _red, 状态 in S.task_rows:
        ns = conv.namespace_for("任务", tid)
        if ns and 状态:
            key = ("任务", ns, tid)
            if key in ent:
                ent[key]["状态"] = 状态.strip() or None
    return ent, reports


# ================ pass③ 边装配（全经 make_edge；consumers 由 schema 自动填） ================

def _edges(g, S, conv, ent, reports):
    raw = []
    sec_exists = {k for k in ent if k[0] == "节条目"}
    review_kind = conv.review_item["kind"] if conv.review_item else None
    ac_kinds = set(conv.ac_prefix_kinds.values())      # 单元格裸 AC id 归类的 kind（provenance 靶补建）

    def add(etype, src, dst, rel, line, method, attrs=None):
        raw.append(M.make_edge(etype, list(src), list(dst), rel, line, method, attrs or {}))

    def sec_key_of(rel, anchor):
        k = tuple(M.key_section(g.docs[rel]["stem"], anchor))
        return k if k in sec_exists else None

    def ensure_ac(acid, rel, line):
        key = _ac_key(conv, acid)
        if key is None:
            return None
        if key not in ent:
            ent[key] = {"key": list(key), "display": acid,
                        "性质": _nature_at(S, rel, line), "primary": None,
                        "candidates": [], "状态": None, "attrs": {}}
            reports["实体_无定义块"].append(
                {"key": list(key), "occurrences": 0, "首现": {"doc": rel, "line": line}})
        return key

    # 可选执行关系：task → execution_log → latest_event。
    for task_key, log_key, event_key, rel, line in S.execution_links:
        if task_key not in ent or log_key not in ent or event_key not in ent:
            continue
        add("执行日志", task_key, log_key, rel, line, "task_execution.pointer")
        add("最新事件", log_key, event_key, rel, line, "task_execution.latest_event")

    # 1. 修订落账（EG-2-AC2/DG-12）：文档→AC/节条目；空目标集→报告不静默丢
    for rel, line, date, rver, targets, cite, digest in S.ledger_rows:
        emitted, seen = False, set()
        for t in targets:
            if t[0] == "AC":
                dst, orig, exp = ensure_ac(t[1], rel, line), None, t[3]
            else:
                dst, orig, exp = sec_key_of(t[1], t[2]), t[3], None
            if dst is None or tuple(dst) in seen:
                continue
            seen.add(tuple(dst))
            attrs = {"r版本": rver, "日期": date}
            if cite:
                attrs["裁定引用集"] = cite
            if orig:
                attrs["原始锚"] = orig
            if exp:
                attrs["展开"] = exp
            add("修订落账", M.key_doc(rel), dst, rel, line, "底账表行", attrs)
            emitted = True
        if not emitted:
            reports["实体_修订行未解析"].append({"file": rel, "line": line, "摘要": digest})

    # 2. 修订声明（EG-2-AC3/DG-12）：节条目/review_item→AC/节条目
    for rel, line, src, targets, 落点 in S.decl_rows:
        if src is None:
            continue
        if src[0] == "节条目" and src not in sec_exists:
            continue
        if review_kind and src[0] == review_kind and src not in ent:
            continue
        seen = set()
        for t in targets:
            if t[0] == "AC":
                dst, orig, exp = ensure_ac(t[1], rel, line), None, t[3]
            else:
                dst, orig, exp = sec_key_of(t[1], t[2]), t[3], None
            if dst is None or tuple(dst) in seen or tuple(dst) == tuple(src):
                continue
            seen.add(tuple(dst))
            attrs = {"落点原文": 落点}
            if orig:
                attrs["原始锚"] = orig
            if exp:
                attrs["展开"] = exp
            add("修订声明", src, dst, rel, line, "修改清单表行", attrs)

    # 3. 映射（EG-2-AC4）：需求AC→下游AC（跨层映射；边/检查语义属块2）
    for rel, line, req, cs in S.map_rows:
        src = _ac_key(conv, req)
        if src is None:
            continue
        ensure_ac(req, rel, line)
        for cid, exp in cs:
            dst = ensure_ac(cid, rel, line)
            if dst:
                add("映射", src, dst, rel, line, "映射表行", {"展开": exp} if exp else {})

    # 4. 任务声明 + 阅读依赖 + 前置依赖 + 任务测试声明
    for rel, line, tid, spec_cell, prereq_cell, red, _状态 in S.task_rows:
        ns = conv.namespace_for("任务", tid)
        if ns is None:
            continue
        tkey = ("任务", ns, tid)
        for acid, exp in _cell_acs(spec_cell or "", expand=True):   # 任务声明（EG-2-AC5）
            dst = ensure_ac(acid, rel, line)
            if dst:
                add("任务声明", tkey, dst, rel, line, "任务表spec锚", {"展开": exp} if exp else {})
        for trel, norm, orig, _mt in _scan_refs(g, rel, spec_cell or "")[0]:  # 阅读依赖（EG-12-AC1）
            dst = sec_key_of(trel, norm)
            if dst:
                add("阅读依赖", tkey, dst, rel, line, "任务表spec锚§",
                    {"原始锚": orig} if orig else {})
        for ptid in _expand_task_ids(prereq_cell or ""):           # 前置依赖（EG-12-AC2）
            pns = conv.namespace_for("任务", ptid)
            if pns is None or (ptid == tid):
                continue
            pkey = ("任务", pns, ptid)
            add("前置依赖", tkey, pkey, rel, line, "任务表前置列")
        for name in red:                                            # 任务测试声明（EG-2-AC5）
            add("任务测试声明", tkey, M.key_test(name), rel, line, "任务表红先列")

    # 5. 验证声明（EG-2-AC6）：ac_ 前缀单一 canonical（测试→AC）
    for rel, line, name, acid in S.ver_a:
        dst = ensure_ac(acid, rel, line)
        if dst:
            add("验证声明", M.key_test(name), dst, rel, line, "ac前缀名")

    # 6. provenance（EG-12-AC4）：记述文档→AC/节条目/参数（consumers={}，不进门禁）
    for rel, line, src, dsts in S.prov_sites:
        seen = set()
        for dstkey, mtext in dsts:
            dst = tuple(dstkey)
            if dst[0] == "节条目" and dst not in sec_exists:
                S.unresolved.append(("provenance", mtext, rel, line, "prov_form"))  # DG-42 规则标识
                continue
            if dst[0] in ac_kinds:
                dst = tuple(ensure_ac(dst[2], rel, line) or dst)
            if dst in seen or dst == tuple(src):
                continue
            seen.add(dst)
            add("provenance", src, dst, rel, line, "记述引用形")

    # 7. 共现索引（EG-2-AC9）：定义块内 ID 精确共现（限 conv.cooccur_kinds 的 ID 形实体）
    for rel, line, owner, peer in S.cooccur:
        if owner not in ent or peer not in ent:
            continue
        if owner[0] not in conv.cooccur_kinds or peer[0] not in conv.cooccur_kinds:
            continue
        add("共现索引", owner, peer, rel, line, "定义块共现")

    # 文档端点物化（仅作 修订落账/provenance 源）
    for e in raw:
        for end in (e["src"], e["dst"]):
            if end[0] == "文档":
                key = tuple(end)
                if key not in ent:
                    d = g.docs.get(key[2])
                    prim = ({"doc": key[2], "line": 1, "line_end": d["body_start"]}
                            if d and d["has_fm"] else None)
                    ent[key] = {"key": list(key),
                                "display": d["stem"] if d else Path(key[2]).stem,
                                "性质": S.docnat.get(key[2], "unknown"), "primary": prim,
                                "candidates": [], "状态": None, "attrs": {}}
    return raw


# ================ 装配与序列化 ================

_ATTR_ORDER = ("定义锚", "原始锚", "锚")


def build(g, conv):
    """→ {"entities":[…],"edges":[…],"reports":{…}}（已按 DG-9 定序；接口见设计 §6，conv 必传）。"""
    S = _scan(g, conv)
    ent, reports = _entities(g, S, conv)
    raw_edges = _edges(g, S, conv, ent, reports)

    entities = []
    for key in sorted(ent):
        e = ent[key]
        attrs = {k: e["attrs"][k] for k in _ATTR_ORDER if k in e["attrs"]}
        entities.append(M.make_entity(
            tuple(key), e["display"], e["性质"], e["primary"],
            sorted(e["candidates"], key=lambda c: (c["doc"], c["line"])),
            e["状态"], attrs))

    seen, edges = set(), []
    for e in sorted(raw_edges, key=M.edge_sort_key):
        k = M.edge_sort_key(e)
        if k in seen:
            continue
        seen.add(k)
        edges.append(e)

    # 报告定序（golden 字节权威）
    out = {}
    dedup = sorted(reports["实体_重定义"], key=lambda x: x["_sort"] + (tuple(x["key"]),))
    for x in dedup:
        x.pop("_sort", None)
    out["实体_重定义"] = dedup
    out["实体_无定义块"] = sorted(
        reports["实体_无定义块"], key=lambda x: (x["首现"]["doc"], x["首现"]["line"], tuple(x["key"])))
    out["实体_修订行未解析"] = sorted(reports["实体_修订行未解析"], key=lambda x: (x["file"], x["line"]))
    # 未分类文档（EG-11-AC2）= 性质 unknown 的文档
    unknown_docs = sorted(r for r in g.docs if S.docnat.get(r, "unknown") == "unknown")
    out["未分类文档"] = unknown_docs
    # 诊断（EG-12-AC4/AC5；身份=符号+期望 token，行号仅展示 DG-31）+ DG-42 逐条溯源三元组（源文件:行+
    # 原文+规则标识）+ 诊断型（死链/断锚；§ 期望=断锚，其余=死链）——使任一告警可脱离工具上下文核验。
    out["unresolved_reference"] = sorted(
        ({"来源": s, "期望": tok, "file": rel, "line": ln,
          "原文": tok, "规则": rule, "诊断型": ("断锚" if "§" in tok else "死链")}
         for s, tok, rel, ln, rule in S.unresolved),
        key=lambda x: (x["来源"], x["期望"], x["file"], x["line"]))
    out["ambiguous_reference"] = sorted(
        ({"来源": s, "file": rel, "line": ln, "原文": s, "规则": "bare_id", "诊断型": "歧义引用"}
         for s, rel, ln in S.ambiguous),
        key=lambda x: (x["来源"], x["file"], x["line"]))
    # schema 无孤儿自检（DG-34；EDGE_TYPES consumers 全须在 CHECK_REGISTRY）
    out["实体_schema_孤儿consumer"] = M.orphan_consumers()
    if conv.task_execution is not None:
        out["执行日志诊断"] = sorted(
            S.execution_diags, key=lambda x: (x["task"], x["file"], x["line"], x["reason"]))

    return {"entities": entities, "edges": edges, "reports": out,
            "classification_complete": not unknown_docs, "unknown_documents": unknown_docs}


def _corpus_root(g):
    """语料根在自身路径空间中的位置＝"."（禁绝对路径入输出：输出内一切 path 皆语料相对）。
    原 parents[2]「工具所在仓库」锚＝位置硬假设，抽离后会漂成任意上级目录并泄进输出——已删。"""
    return "."


def cmd_dump(g, conv, as_json, kind=None):
    """全量实体+边导出（DG-9 golden 权威形状）。kind（EG-31/DG-62 投影）非空时按 kind 过滤：
    实体过滤 key[0]==K、边过滤 src[0]==K∨dst[0]==K（触及式，支持邻接查询）；语料级诊断
    （reports/unknown_documents/classification_complete/context_manifest/schema_version/corpus_root）
    与 kind 正交、不过滤（过滤会藏告警）。K 不在实际 kind 集→列可选集合退 1（镜像 cmd_ids）。"""
    data = build(g, conv)
    entities, edges = data["entities"], data["edges"]
    if kind is not None:
        kinds = sorted({e["key"][0] for e in data["entities"]})
        if kind not in kinds:
            print(f"无此 kind：{kind}；可选：{'、'.join(kinds)}", file=sys.stderr)
            return 1
        entities = [e for e in entities if e["key"][0] == kind]
        edges = [e for e in edges if e["src"][0] == kind or e["dst"][0] == kind]
    top = {"schema_version": M.SCHEMA_VERSION, "corpus_root": _corpus_root(g),
           "classification_complete": data["classification_complete"],
           "unknown_documents": data["unknown_documents"],
           "entities": entities, "edges": edges, "reports": data["reports"]}
    top = {"context_manifest": M.context_manifest(
        "worktree", conv, "dump", body=top,
        include_archived=getattr(g, "include_archived", False)), **top}  # DG-43
    if as_json:
        print(M.emit(top))
        return 0
    if i18n.language() == "en":
        print(i18n.render_public(top))
        return 0
    kind_n, type_n = defaultdict(int), defaultdict(int)
    for e in entities:
        kind_n[e["key"][0]] += 1
    for e in edges:
        type_n[e["type"]] += 1
    print(f"实体图谱 dump（schema={M.SCHEMA_VERSION}，corpus_root={top['corpus_root']}，"
          f"分类完成={data['classification_complete']}，unknown 文档={len(data['unknown_documents'])}"
          f"{('，kind=' + kind) if kind else ''}）")
    print(f"实体 {len(entities)} 个：")
    for k in sorted(kind_n):          # 开放 kind 集：按实际出现的 kind 输出（含内置默认外的开放/项目专有 kind）
        print(f"  {k} × {kind_n[k]}")
    print(f"边 {len(edges)} 条：")
    for t in M.EDGE_TYPES:
        if type_n.get(t):
            print(f"  {t} × {type_n[t]}")
    print("报告：")
    for k, v in data["reports"].items():
        print(f"  {k} × {len(v)}")
    print("（--json 输出完整图谱，形状=golden/dump.json 字节锁定基线）")
    return 0
