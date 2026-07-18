#!/usr/bin/env python3
"""DocStar — 文档语料图谱：关系通配 + ID 引用索引（引擎项目无关，项目约定经 conventions 注入）。

零依赖（Python 3.9+ stdlib）。每次全量扫描（数百篇 <1s），不建持久索引——没有 stale/同步问题。
关系(边)通配：任意 Markdown 语料零配置即出关系图；ID 索引/实体识别按 conventions 提供的语法点亮。

用法：
  python3 docstar.py graph            # 全局：frontmatter 关系链（通配：上下游+任意键关联）
  python3 docstar.py doc <名称>       # 单文档：元信息/出入边/节标题/ID 概览（名称可带目录限定，如 M1/Requirement）
  python3 docstar.py id <ID>          # 一个 ID 的全部出现位置（file:line）
  python3 docstar.py id "<文档> §3"   # 节引用：目标锚点+全部跨文档引用处（自引断锚见 check；文档名同支持目录限定）
  python3 docstar.py ids [--kind K]   # ID 清单与计数（按类别）
  python3 docstar.py docs [glob] [--fields A,B]  # 批量文档 frontmatter 投影（EG-31；glob 对全路径 fnmatch）
  python3 docstar.py check            # 一致性检查：断链/单向边/死链/未登记参数
  python3 docstar.py html [输出路径]  # 交互式图谱页（默认 graph.html）
  python3 docstar.py html-entity      # 实体图谱交互页（ego 邻域视图+统计）
  python3 docstar.py dump [--kind K]  # 实体图谱全量导出（实体层；--kind 投影单类实体+触及边）
  python3 docstar.py trace <实体>     # 实体：定义块全文+全部关系边（实体层）
  python3 docstar.py brief <任务>     # 任务闭包+边界指针（EG-13，实体层）
  python3 docstar.py verify           # 增量差分+进图自查（EG-14，实体层）
  python3 docstar.py classify --pending|--validate  # 文档性质分类（EG-11-AC6）
  python3 docstar.py harvest          # 未标注高频词提示（实体层）
  除 html/html-entity 外的查询与分析命令加 --json 输出机器可读 JSON；HTML 命令始终写文件。
  旗标：
    --corpus DIR          替换扫描根=语料根（fixtures 隔离级；默认全仓）
    --conventions DIR     显式约定集（DG-33；未指定→语料根 .docstar/conventions/ →祖先走查至 git 边界[DG-55] →内置默认）
    --include-archived    取证开关：停用 archive_globs 过滤（EG-30；默认按 conventions 声明排除归档子树）
    dump/ids --kind K     投影单一 kind（dump：实体 key[0]==K + 触及边 src/dst[0]==K；ids：该类计数）
    docs --fields A,B     逗号分隔字段名（保序）投影 frontmatter；字段缺失=null
    check --gate 键1,键2  指定判定项非空→退出码 1；键名拼错→退出码 2（fail-closed）
    verify --baseline REV 差分基线 git revision；classify --validate --baseline REV --manifest SCOPE
    harvest --baseline F  对上次输出文件做差量视图
  实体层 JSON 形状权威=golden/*.json 字节锁定基线（tests.py 层 B 逐字节校验；命令→顶层键契约表见 references/command-contracts.md）。
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import unquote

__version__ = "0.2.0"   # 发布版本（语义化）；与 manifest 的 tool_version="eg-3"（schema 契约戳）正交

sys.path.insert(0, str(Path(__file__).resolve().parent / "internal"))  # 内部模块（corpus/entity_*）迁入 internal/

import conventions                          # DG-33 约定集（loader + Conventions + ConventionsError）
import corpus                               # DG-21 语料源抽象（FileSource/GitSource；scan 消费）
import i18n
import json_contract

TOOL_DIR = Path(__file__).resolve().parent      # 工具自身目录（模板/自带 fixtures）
_SELF_FIXTURES = TOOL_DIR / "fixtures"          # 自带测试语料
# 语料根＝corpus.ROOT（main 依 --corpus 或 cwd 设定；调用时取，勿在 def 默认值处绑定）。


def _is_self_fixture(root, rel):
    """工具自带 fixtures 不混入被扫语料（自宿主扫本仓时）；但 --corpus 显式指向 fixtures 内部时照扫
    （那是刻意测它）。取代原「rel 以工具仓内 fixtures/ 路径开头」的仓内位置硬假设。"""
    try:
        if Path(root).resolve().is_relative_to(_SELF_FIXTURES):
            return False
        return (Path(root) / rel).resolve().is_relative_to(_SELF_FIXTURES)
    except (OSError, ValueError):
        return False

# ---------------- 通用建边形态（不项目化；关系通配） ----------------
# 关系(边)来自「链接 + frontmatter 引用」，做成通配：任何 Markdown 语料零配置即出关系图。
#   · frontmatter 通配：任意键，值解析到语料内某文档 → 一条边，键名=边类型（cmd 见 fm_edges）
#   · 正文链接：Markdown [t](x.md) + Wiki [[目标]]（Obsidian/Foam/Logseq 主力链接形）
# 项目专有的 ID 语法(doc_id_kinds)、别名(aliases)、§标记(section_ref_marker)、上下游键对
# (directed_pairs)、参数登记册(param_registry) 一律经 conv 注入（DG-33 单一事实源，勿在此写死）。
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+?\.md)(?:[#?][^)]*)?\)")            # Markdown 内联链接→.md
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")     # [[目标]]/[[目标#节]]/[[目标|别名]]
HEADING_RE = re.compile(r"^(#{1,6})\s*(?:§\s*)?(\d+(?:\.\d+)*)(?:[.、:：\s]+(.*))?\s*$")
_FM_LINKISH = re.compile(r"[\[/]|\.md(?:[#)\s]|$)")   # frontmatter 值含链接/路径形才尝试解析（否则机会式跳过）


def secref_re(marker):
    """节引用正则（跨文档建边＋同文档自引检锚，DG-51）：可选前缀词 + <marker>N[.N…]。marker 由 conv 注入（默认 §）。
    前缀经「最长后缀匹配」解析到别的文档才建边（中文无分词，「见specB §3」捕获「见specB」取后缀命中）。
    前缀内层可含 `/`（DG-57①：捕获 `M1/Requirement §3` 路径形），但末字符禁 `/`——`§4A/§4A.1` 一类
    斜杠分隔 § 列表不产出 `A/` 型垃圾词（使其维持裸 § 跳过）；对无 `/` 文本与旧正则逐字等价。"""
    m = re.escape(marker)
    return re.compile(
        r"(?:([A-Za-z0-9一-鿿](?:[A-Za-z0-9一-鿿.+_/-]{0,28}[A-Za-z0-9一-鿿.+_-])?)[ \t]*)?"
        + m + r"[ \t]*(\d+(?:\.\d+)*)")

# ---------------- 扫描 ----------------

def parse_frontmatter(lines):
    """宽容解析：--- 包围块内，顶格 `键:` 起新键，缩进/- 行归入当前键。"""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = 0
    for i in range(1, min(len(lines), 60)):
        if lines[i].strip() == "---":
            end = i
            break
    if not end:
        return {}, 0
    meta, key = {}, None
    for raw in lines[1:end]:
        m = re.match(r"^([^\s:#][^:：]*)[：:]\s*(.*)$", raw)
        if m and raw[:1] not in (" ", "\t", "-"):
            key = m.group(1).strip()
            val = m.group(2).strip()
            meta[key] = [val] if val else []
        elif key is not None and raw.strip():
            item = raw.strip()
            meta[key].append(item[1:].strip() if item.startswith("-") else item)
    return meta, end + 1

class Graph:
    def __init__(self, root=None, conv=None):
        self.root = Path(root if root is not None else corpus.ROOT)   # 语料根（--corpus 或 cwd）
        self.conv = conv        # 约定集（aliases/directed_pairs/self_words/…；DG-33）
        self.texts = {}         # rel -> 全文（实体层复用，免二次读盘）
        self.docs = {}          # rel -> {stem, meta, headings{num:(line,title)}, has_fm}
        self.fm_edges = []      # (src, dst|None, 键名, 方向 up/down/None, 原文条目, 链接raw|None)
        self.body_links = []    # (src, dst|None, raw, line)
        self.id_occ = defaultdict(list)   # id -> [(doc, line, text)]
        self.id_kind = {}                 # id -> kind
        self.sec_refs = []      # (src, 前缀词, num, dst|None, line)
        self.self_sec_refs = [] # (src, 前缀词, num, src, line)——同文档自引 §（检锚域三形；DG-51）
        self._names = None      # 候选名 -> doc（唯一时才可用）
        self._multi = None      # 候选名 -> sorted[doc]（len≥2 多候选，DG-57 same_dir_pick 消歧用）

    def _build_names(self):
        multi = defaultdict(set)
        for rel, d in self.docs.items():
            stem = d["stem"]
            multi[stem].add(rel)
            head = stem.split("-", 1)[0].strip()
            if len(head) >= 2:
                multi[head].add(rel)
        self._multi = {n: sorted(s) for n, s in multi.items() if len(s) >= 2}
        names = {n: next(iter(s)) for n, s in multi.items() if len(s) == 1}
        aliases = self.conv.aliases if self.conv else {}
        for alias, stem in aliases.items():
            hits = [r for r, d in self.docs.items() if d["stem"] == stem]
            if len(hits) == 1:
                names[alias] = hits[0]
        self._names = names

    def _seg_hits(self, q):
        """路径限定段对齐候选（DG-57②，canon/wikilink_target/resolve_name 三面共用单源）：
        rel 去 `.md` 后全等 q 或以 "/"+q 结尾（命中 docs/M1/Requirement.md，不命中 XM1/Requirement.md）。"""
        if q.endswith(".md"):
            q = q[:-3]
        return [rel for rel in self.docs if rel[:-3] == q or rel[:-3].endswith("/" + q)]

    def canon(self, word, src=None):
        """最长后缀匹配候选名：返回 (规范名, doc) 或 (None, None)。word 含 `/` 先走路径限定段对齐
        （DG-57②）；src（引用方 rel）给出时供路径限定多候选与多候选名消歧调用 same_dir_pick（②④，EG-28）。"""
        if self._names is None:
            self._build_names()
        if not word:
            return None, None
        if word.endswith(".md"):  # 链接 URL 作前缀词：「…specB-detailed-design.md §3」
            word = word[:-3]
        if "/" in word:
            cands = self._seg_hits(word)
            if len(cands) == 1:
                return word, cands[0]
            elif len(cands) >= 2:
                if src is None:
                    return None, None
                pick = corpus.same_dir_pick(cands, src)
                return (word, pick) if pick else (None, None)
            else:                # 零命中：限定词不作否证，取末段落入③④（兼容旧捕获语义）
                word = word.rsplit("/", 1)[-1]
        best = None
        for n in self._names:
            if word == n or word.endswith(n):
                if best is None or len(n) > len(best):
                    best = n
        if src is not None:      # ④ 多候选名最长后缀匹配（仅严格长于③命中/③无命中才可能覆盖）
            multi_best = None
            for n in self._multi:
                if word == n or word.endswith(n):
                    if multi_best is None or len(n) > len(multi_best):
                        multi_best = n
            if multi_best is not None and (best is None or len(multi_best) > len(best)):
                pick = corpus.same_dir_pick(self._multi[multi_best], src)
                if pick:
                    return multi_best, pick
        return (best, self._names[best]) if best else (None, None)

    def wikilink_target(self, target):
        """[[目标]] → doc rel：精确候选名/别名 > 精确 stem（非后缀模糊，wiki 链接是命名引用）> 路径限定
        段对齐（DG-57⑥）。无唯一命中→None（wiki 链接无引用方目录消歧，多候选不建边）。"""
        target = target.strip()
        if not target:
            return None
        if self._names is None:
            self._build_names()
        if target in self._names:
            return self._names[target]
        hits = [rel for rel, d in self.docs.items() if d["stem"] == target]
        if hits:
            return hits[0] if len(hits) == 1 else None
        if "/" not in target:
            return None
        cands = self._seg_hits(target)
        return cands[0] if len(cands) == 1 else None

    # -- CLI 文档名解析：路径限定段对齐 > exact stem > 别名/候选名 > stem 前缀 > stem 包含 > 路径包含
    def resolve_name(self, q):
        q = q.strip()
        if "/" in q:              # 路径限定（DG-57⑤）：候选同 _seg_hits 单源，≥1 即返回全部（cmd_doc 既有多命中分支自然生效）
            cands = self._seg_hits(q)
            if cands:
                return cands
        stems = defaultdict(list)   # stem → [rel] 多值：同 stem 各文件皆候选（单值 dict 键覆盖曾致多命中静默取末位）
        for rel, d in self.docs.items():
            stems[d["stem"]].append(rel)
        if q in stems:
            return stems[q]
        if self._names is None:
            self._build_names()
        if q in self._names:
            return [self._names[q]]
        for probe in (lambda s: s.startswith(q), lambda s: q in s):
            hits = [rel for s, rels in stems.items() if probe(s) for rel in rels]
            if hits:
                return hits
        return [rel for rel in self.docs if q.lower() in rel.lower()]

def resolve_link(src_rel, raw, root=None):
    """链接目标解析：相对本文目录 > 相对语料根。返回 rel str 或 None。"""
    raw = unquote(raw.strip())
    if raw.startswith(("http://", "https://")):
        return None
    root = Path(root if root is not None else corpus.ROOT)
    for base in (root / Path(src_rel).parent, root):
        try:
            cand = (base / raw).resolve()
            if cand.is_file() and cand.is_relative_to(root):
                return str(cand.relative_to(root))
        except (OSError, ValueError):
            pass
    return None


def _fm_refs(g, src_rel, entry, root):
    """frontmatter 值 → [(dst|None, raw)]（通配机会式，非声明键用）：
    显式 Markdown/wiki 链接一律算引用（dst 可 None，供断链标注）；裸路径形仅解析成功才算
    （不臆测）；普通标量（日期、状态词、纯文本）返回 []（不当引用）。"""
    out = []
    for _txt, raw in LINK_RE.findall(entry):
        out.append((resolve_link(src_rel, raw, root), raw))
    for tgt in WIKILINK_RE.findall(entry):
        out.append((g.wikilink_target(tgt), f"[[{tgt}]]"))
    if not out and _FM_LINKISH.search(entry):
        dst = resolve_link(src_rel, entry.strip(), root)
        if dst:
            out.append((dst, entry.strip()))
    return out

def scan(source, conv, include_archived=False):
    """扫描语料源 → Graph（DG-21 契约：source=corpus.FileSource|GitSource，统一 docs()/text(rel)）。
    conv 注入建边约定（DG-33）：doc_id_kinds（ID 语法）、directed_pairs（上下游键对→方向）、
    section_ref_marker/self_words/self_ref_words（§ 引用与自引检锚，DG-51）、aliases（经 Graph）。关系通配——frontmatter 任意键
    值解析到文档即成边（键名=边类型）、正文 Markdown+wiki 链接皆成边。
    fixtures 隔离=DocStar 级策略（文件名镜像真实语料，混入即 stem 碰撞污染 canon/节引用）；
    root 供 resolve_link 相对解析（GitSource 无 root→corpus.ROOT 兜底，纯文件系统探测）。
    include_archived=False（默认）：conv.archive_globs 命中件不入语料（DG-59/EG-30 唯一收口点）；
    True=取证开关，停用过滤、命中件全量入图。"""
    root = getattr(source, "root", corpus.ROOT)
    g = Graph(root, conv)
    g.include_archived = include_archived   # 落章供 manifest 读取（无条件执行，即使语料为空，DG-59）
    kind_res = [(k, cre) for k, cre, _n in conv.doc_id_kinds]        # 已编译（Conventions 构造时）
    directed = {}                                                    # 键名 → up/down（directed_pairs 双向展开）
    for up_key, down_key in conv.directed_pairs:
        directed[up_key], directed[down_key] = "up", "down"
    SR = secref_re(conv.section_ref_marker) if conv.section_ref_marker else None
    texts = g.texts
    for rel in source.docs():
        if _is_self_fixture(root, rel):        # 工具自带 fixtures 永不混入被扫语料（自宿主时）
            continue
        if not include_archived and corpus.archived(rel, conv.archive_globs):
            continue                            # DG-59/EG-30：归档子树默认不入语料（枚举成员轴）
        t = source.text(rel)
        if t is None:
            continue
        texts[rel] = t
        lines = t.splitlines()
        meta, body_start = parse_frontmatter(lines)
        headings = {}
        for i, ln in enumerate(lines, 1):
            hm = HEADING_RE.match(ln)
            if hm:
                headings.setdefault(hm.group(2), (i, (hm.group(3) or "").strip()))
        g.docs[rel] = {"stem": Path(rel).stem, "meta": meta, "headings": headings,
                       "has_fm": bool(meta), "body_start": body_start}
    # 第二遍：需要 docs 全集（解析链接目标与 § 前缀、wiki 目标）
    for rel, text in texts.items():
        lines = text.splitlines()
        # 代码遮罩（DG-41）：围栏/行内代码内的示例不当真链接/引用/ID。分层——链接/§引用用
        # 全遮罩（链接绝不合法地写在反引号内）；ID 提及仅剥围栏（保反引号内 ID 语法如参数 `X_y`）。
        link_lines = corpus.code_mask(text).splitlines()
        id_lines = corpus.code_mask(text, mask_inline=False).splitlines()
        meta = g.docs[rel]["meta"]
        # frontmatter 通配建边：任意键，值解析到文档即成边（键名=边类型）
        for key, entries in meta.items():
            direction = directed.get(key)                # 声明的上下游键→方向；其它键→None
            for entry in entries:
                refs = _fm_refs(g, rel, entry, root)   # Markdown/wiki/路径形引用（dst 可 None=断链）
                if direction is not None:
                    # 声明链接键（上游/下游…）：无任何引用即「无链接条目」（依赖须落引用，断链纪律）
                    if not refs:
                        g.fm_edges.append((rel, None, key, direction, entry, None))
                    for dst, raw in refs:
                        g.fm_edges.append((rel, dst, key, direction, entry, raw))
                else:
                    # 机会式通配键：有引用即成边；普通标量（日期/状态词）无引用→静默跳过，不报错
                    for dst, raw in refs:
                        g.fm_edges.append((rel, dst, key, None, entry, raw))
        for i, ln in enumerate(lines, 1):
            link_ln = link_lines[i - 1] if i - 1 < len(link_lines) else ln   # 围栏+行内遮罩（链接/§引用）
            id_ln = id_lines[i - 1] if i - 1 < len(id_lines) else ln         # 仅围栏遮罩（ID 提及保反引号语法）
            # frontmatter 行不重复抽链接边（已作 fm 边），但仍抽 ID 与 § 引用
            if i > g.docs[rel]["body_start"]:
                for _txt, raw in LINK_RE.findall(link_ln):
                    g.body_links.append((rel, resolve_link(rel, raw, root), raw, i))
                for tgt in WIKILINK_RE.findall(link_ln):  # 通用 wiki 链接 [[目标]]（Obsidian/Foam/Logseq）
                    g.body_links.append((rel, g.wikilink_target(tgt), f"[[{tgt}]]", i))
            claimed = []
            def free(a, b):
                return all(b <= s or a >= e for s, e in claimed)
            for kind, cre in kind_res:
                for m in cre.finditer(id_ln):
                    if not free(*m.span()):
                        continue
                    claimed.append(m.span())
                    ident = m.group(0)
                    if kind == "版本":               # 可选 per-kind 精化：版本号按前缀词归属主体（inert 于无此 kind 的语料）
                        prefix = ln[: m.start()].rstrip()
                        pw = re.split(r"[\s，。;；:：()（）\[\]|/*`]+", prefix)[-1] if prefix else ""
                        cn, _doc = g.canon(pw)
                        owner = cn or (pw if 0 < len(pw) <= 12 else "")
                        ident = f"{owner} {ident}".strip()
                    g.id_occ[ident].append((rel, i, ln.strip()))
                    g.id_kind[ident] = kind
            if SR:
                for m in SR.finditer(link_ln):       # 遮罩后：代码内 § 示例不成引用（DG-41）
                    word, num = m.group(1), m.group(2)
                    if not word:                     # 裸 §N：归属是惯例推断非文本内确定，不检（DG-51 边界）
                        continue
                    if word in conv.self_ref_words:  # 显式自指（本文/本节…）→ 自引，检锚（DG-51）
                        g.self_sec_refs.append((rel, word, num, rel, i))
                        continue
                    if word in conv.self_words:      # 非自指前缀词（见/详见…）：无归属证据，同裸 §（DG-51 边界）
                        continue
                    cn, dst = g.canon(word, src=rel)   # src 供同目录/路径限定消歧（DG-57②④，EG-28）
                    if dst == rel:                   # 具名自引（文档名/别名解析到本文档）→ 检锚（DG-51）
                        g.self_sec_refs.append((rel, cn or word, num, rel, i))
                        continue
                    if dst is None and any(word.endswith(sw) for sw in conv.self_ref_words):
                        # 连写长前缀以自指词收尾（「…见本文 §N」；canon「最长后缀」同哲学）→ 自引（DG-51）
                        g.self_sec_refs.append((rel, word, num, rel, i))
                        continue
                    g.sec_refs.append((rel, cn or word, num, dst, i))
    return g

# ---------------- 输出助手 ----------------

def _clip(s, n=110):
    return s if len(s) <= n else s[: n - 1] + "…"

def _emit(data, as_json, text_fn):
    if as_json:
        print(json.dumps(json_contract.to_public(data), ensure_ascii=False, indent=1))
    elif i18n.language() == "en":
        print(i18n.render_public(data))
    else:
        text_fn()

# ---------------- 命令 ----------------

def cmd_graph(g, as_json):
    fm_docs = {d: v for d, v in g.docs.items() if v["has_fm"]}
    up, down = defaultdict(list), defaultdict(list)
    keyed = defaultdict(lambda: defaultdict(list))     # src → 键名 → [dst]（通配非方向键）
    for src, dst, key, direction, _e, _r in g.fm_edges:
        if not dst:
            continue
        if direction == "up":
            up[src].append(dst)
        elif direction == "down":
            down[src].append(dst)
        else:
            keyed[src][key].append(dst)
    data = {"docs_total": len(g.docs), "docs_with_frontmatter": len(fm_docs),
            "chains": {d: {"上游": up.get(d, []), "下游": down.get(d, []),
                           **({"关联": {k: v for k, v in sorted(keyed[d].items())}} if d in keyed else {})}
                       for d in sorted(fm_docs)}}
    def txt():
        print(f"文档 {len(g.docs)} 篇，含 frontmatter {len(fm_docs)} 篇（上下游/关联链仅覆盖后者）\n")
        for d in sorted(fm_docs):
            print(d)
            for u in up.get(d, []):
                print(f"  ↑ 上游  {u}")
            for w in down.get(d, []):
                print(f"  ↓ 下游  {w}")
            for k, vs in sorted(keyed.get(d, {}).items()):
                for x in vs:
                    print(f"  · {k}  {x}")
        print("\n正文链接边与节引用边见 `doc <名称>`；缺 frontmatter 清单见 `check`。")
    _emit(data, as_json, txt)
    return 0

def cmd_doc(g, q, as_json):
    hits = g.resolve_name(q)
    if not hits:
        print(f"未找到文档：{q}", file=sys.stderr)
        return 1
    if len(hits) > 1:
        print("命中多篇，请再限定：\n  " + "\n  ".join(hits), file=sys.stderr)
        return 1
    rel = hits[0]
    d = g.docs[rel]
    fm_up = [(dst, e) for s, dst, _k, dr, e, _ in g.fm_edges if s == rel and dr == "up"]
    fm_down = [(dst, e) for s, dst, _k, dr, e, _ in g.fm_edges if s == rel and dr == "down"]
    fm_keyed = defaultdict(list)                       # 键名 → [dst]（通配非方向键）
    for s, dst, k, dr, _e, _r in g.fm_edges:
        if s == rel and dr is None and dst:
            fm_keyed[k].append(dst)
    fm_in = sorted({(s, k, dr) for s, dst, k, dr, _e, _r in g.fm_edges if dst == rel})
    out_links = Counter(dst for s, dst, _r, _l in g.body_links if s == rel and dst and dst != rel)
    in_links = Counter(s for s, dst, _r, _l in g.body_links if dst == rel and s != rel)
    sec_in = Counter((s, f"§{n}") for s, _w, n, dst, _l in g.sec_refs if dst == rel)
    sec_out = Counter((dst, f"§{n}") for s, _w, n, dst, _l in g.sec_refs if s == rel and dst)
    ids = Counter()
    for ident, occ in g.id_occ.items():
        c = sum(1 for r, _i, _t in occ if r == rel)
        if c:
            ids[ident] = c
    data = {"doc": rel, "meta": d["meta"],
            "上游": [u for u, _ in fm_up], "下游": [w for w, _ in fm_down],
            **({"关联": {k: v for k, v in sorted(fm_keyed.items())}} if fm_keyed else {}),
            "被引用frontmatter": [{"doc": s, "键": k, "方向": dr} for s, k, dr in fm_in],
            "正文引出": dict(out_links.most_common()), "被正文引用": dict(in_links.most_common()),
            "引出节引用": {f"{k[0]} {k[1]}": v for k, v in sec_out.most_common()},
            "被节引用": {f"{k[0]} {k[1]}": v for k, v in sec_in.most_common()},
            "节标题数": len(d["headings"]), "ID提及TOP": ids.most_common(15)}
    def txt():
        print(f"== {rel} ==")
        for k in ("目标", "状态", "类型"):
            if k in d["meta"]:
                print(f"{k}: {_clip(' / '.join(d['meta'][k]), 140)}")
        if not d["has_fm"]:
            print("（无 frontmatter——存量文档，改到即补）")
        for label, rows, mark in (("上游", fm_up, "↑"), ("下游", fm_down, "↓")):
            if rows:
                print(f"{label}:")
                for dst, e in rows:
                    print(f"  {mark} {dst or '[未解析] ' + _clip(e, 80)}")
        if fm_keyed:
            print("关联(frontmatter 键):")
            for k, vs in sorted(fm_keyed.items()):
                for x in vs:
                    print(f"  · {k} → {x}")
        if fm_in:
            print("被引用(frontmatter):")
            for s, k, dr in fm_in:
                tag = "上游" if dr == "up" else "下游" if dr == "down" else k
                print(f"  ← {s}（其{tag}）")
        for label, cnt, mark in (("正文引出", out_links, "→"), ("被正文引用", in_links, "←")):
            if cnt:
                print(f"{label}:")
                for x, c in cnt.most_common(12):
                    print(f"  {mark} {x} ×{c}")
        if sec_out:
            print("引出节引用:")
            for (dst, sec), c in sec_out.most_common(10):
                print(f"  → {dst} {sec} ×{c}")
        if sec_in:
            print("被节引用（谁在引我的 §）:")
            for (s, sec), c in sec_in.most_common(10):
                print(f"  ← {s} 引 {sec} ×{c}")
        if d["headings"]:
            nums = sorted(d["headings"], key=lambda x: [int(p) for p in x.split(".")])
            print(f"节标题 {len(nums)} 个: " + _clip("、".join(f"§{n}" for n in nums), 150))
        if ids:
            print("ID 提及 TOP: " + "、".join(f"{i}×{c}" for i, c in ids.most_common(12)))
    _emit(data, as_json, txt)
    return 0

def cmd_id(g, q, as_json):
    q = q.strip()
    m = re.match(r"^(.+?)\s*§\s*(\d+(?:\.\d+)*)$", q)
    if m:  # 节引用查询：<文档名> §N
        hits = g.resolve_name(m.group(1))
        if not hits:
            print(f"节引用前缀未唯一解析：{m.group(1)}（命中 {len(hits)} 篇）", file=sys.stderr)
            return 1
        if len(hits) > 1:        # 多命中同 cmd_doc 列全候选（DG-57⑦，EG-28）
            print("命中多篇，请再限定：\n  " + "\n  ".join(hits), file=sys.stderr)
            return 1
        target, num = hits[0], m.group(2)
        occ = sorted((s, l) for s, _w, n, dst, l in g.sec_refs
                     if dst == target and (n == num or n.startswith(num + ".")))
        head = g.docs[target]["headings"].get(num)
        data = {"query": f"{target} §{num}",
                "目标锚点": {"line": head[0], "title": head[1]} if head else None,
                "引用处": [{"doc": s, "line": l} for s, l in occ]}
        def txt():
            print(f"== {target} §{num} ==")
            print(f"目标锚点: {target}:{head[0]} {head[1]}" if head
                  else "目标锚点: 未找到对应编号标题（疑似断锚或标题非数字编号）")
            print(f"被引用 {len(occ)} 处（含 §{num}.* 子节）:")
            for s, l in occ:
                print(f"  {s}:{l}")
        _emit(data, as_json, txt)
        return 0
    occ = g.id_occ.get(q, [])
    if not occ:
        near = [i for i in g.id_occ if q.lower() in i.lower()][:10]
        print(f"无 ID：{q}" + (f"；相近：{'、'.join(near)}" if near else ""), file=sys.stderr)
        return 1
    by_doc = defaultdict(list)
    for rel, line, text in occ:
        by_doc[rel].append((line, text))
    data = {"id": q, "kind": g.id_kind.get(q), "total": len(occ),
            "docs": {d: [l for l, _ in v] for d, v in sorted(by_doc.items())}}
    def txt():
        print(f"== {q}（{g.id_kind.get(q)}）共 {len(occ)} 处，跨 {len(by_doc)} 篇 ==")
        for d, v in sorted(by_doc.items(), key=lambda kv: -len(kv[1])):
            print(f"{d} ×{len(v)}")
            for l, t in v[:4]:
                print(f"  :{l} {_clip(t)}")
            if len(v) > 4:
                print(f"  … 另 {len(v) - 4} 处")
    _emit(data, as_json, txt)
    return 0

def cmd_ids(g, conv, kind, as_json):
    kinds = defaultdict(Counter)
    for ident, occ in g.id_occ.items():
        kinds[g.id_kind[ident]][ident] = len(occ)
    if kind and kind not in kinds:
        print(f"无此类别：{kind}；可选：{'、'.join(kinds)}", file=sys.stderr)
        return 1
    sel = {kind: kinds[kind]} if kind else kinds
    notes = {k: n for k, _rx, n in conv.doc_id_kinds}
    data = {k: {"unique": len(c), "total": sum(c.values()), "note": notes.get(k, ""),
                "ids": dict(c.most_common())} for k, c in sel.items()}
    def txt():
        for k, c in sorted(sel.items(), key=lambda kv: -sum(kv[1].values())):
            print(f"[{k}] 唯一 {len(c)} 个 / 共 {sum(c.values())} 次 — {notes.get(k, '')}")
            if kind:
                for i, n in c.most_common():
                    print(f"  {i} ×{n}")
            else:
                print("  " + _clip("、".join(f"{i}×{n}" for i, n in c.most_common(12)), 160))
    _emit(data, as_json, txt)
    return 0

def cmd_docs(g, glob, fields, as_json):
    """批量文档 frontmatter 投影（EG-31/DG-62）：12 份链路文档的 状态/类型 一次成表，替代逐篇
    doc --json 循环。glob 为可选位置参数，fnmatchcase 对 rel 全路径匹配（`*` 跨 `/`——有意的简单
    语义，非路径感知 glob）；fields 逗号分隔字段名（保序），取 meta 原值列表、不做 join，缺失=null。
    空结果退 0（glob 是模式非键，∅ 是合法答案；区别于 ids 未知 kind 退 1 那是无效键）。"""
    rels = sorted(g.docs)
    if glob:
        rels = [r for r in rels if fnmatchcase(r, glob)]
    rows = []
    for rel in rels:
        d = g.docs[rel]
        row = {"doc": rel, "has_fm": d["has_fm"]}
        for f in fields:
            row[f] = next((d["meta"][key] for key in json_contract.frontmatter_candidates(f)
                           if key in d["meta"]), None)   # 原值列表；字段缺失=null
        rows.append(row)
    data = {"docs": rows}
    def txt():
        for row in rows:
            cells = [row["doc"]]
            for f in fields:
                v = row[f]
                cells.append("/".join(v) if v else "—")             # 缺失/空值→占位
            print("  ".join(cells))
    _emit(data, as_json, txt)
    return 0

def _gate_hit(v):
    """--gate 命中判定（DG-60）：判定对象委托其 `gates()`（EG-15-AC8 真值表 fail∨tainted∨broken，
    单份存 entity_check 模型层、与 `_verdict` 同居）；文档层 findings 列表/标量按真值。判定对象不再
    谎报 `__bool__`（谎报会撞 json indent 编码器吞键，DG-60），故经显式 `gates()` 谓词、不用 `bool(它)`。"""
    gates = getattr(v, "gates", None)          # _Verdict 有；文档层 list/标量无 → 回落 bool
    return gates() if callable(gates) else bool(v)


def _gate_count(v):
    """--gate 命中计数（GATE FAIL 的 ×N）：判定对象取 findings 数（len(dict)=键数非工作量，
    同 txt 渲染口径），其余取自身长。"""
    if isinstance(v, dict) and "judgment_status" in v:
        return len(v.get("findings", []))
    return len(v)


def cmd_check(g, as_json, gate=None, conv=None):
    R = {}
    R["fm_断链"] = [{"doc": s, "raw": raw, "entry": _clip(e, 90)}
                    for s, dst, _k, _d, e, raw in g.fm_edges if raw and not dst]
    R["fm_无链接条目"] = [{"doc": s, "entry": _clip(e, 90)}
                          for s, dst, _k, _d, e, raw in g.fm_edges
                          if raw is None and not dst and not any(e.startswith(p) for p in conv.nonlink_prefixes)]
    # DG-58/EG-29：有意非链接声明——conv.nonlink_prefixes 前缀词标记的纯文字条目（链根/仓外产物/
    # 口头裁决/模板下游等）是合法非链接形态，与上面未标记的疑漏链分桶；声明桶计数可见、不作 finding
    # （--gate 语义仍绑 fm_无链接条目=未标记桶）。缺席/显式空词表→恒不命中，本键恒在但空（fail-visible）。
    R["fm_有意非链接条目"] = [{"doc": s, "entry": _clip(e, 90)}
                            for s, dst, _k, _d, e, raw in g.fm_edges
                            if raw is None and not dst and any(e.startswith(p) for p in conv.nonlink_prefixes)]
    declared_up = {(s, dst) for s, dst, _k, dr, _e, _r in g.fm_edges if dr == "up" and dst}
    declared_down = {(s, dst) for s, dst, _k, dr, _e, _r in g.fm_edges if dr == "down" and dst}
    # dst in g.docs 守卫（DG-59/EG-30-AC2）：dst 磁盘存在但图外（归档排除件/任意非语料成员文件）时
    # 互查限语料成员，不 KeyError 崩（既有触发形=上/下游 fm 边指向存在但非语料成员文件，受控复现）。
    R["单向边_我列它为下游_它未列我为上游"] = sorted(
        {f"{s} → {dst}" for s, dst in declared_down
         if dst in g.docs and g.docs[dst]["has_fm"] and (dst, s) not in declared_up})
    R["单向边_我列它为上游_它未列我为下游"] = sorted(
        {f"{s} → {dst}" for s, dst in declared_up
         if dst in g.docs and g.docs[dst]["has_fm"] and (dst, s) not in declared_down})
    # DG-42 诊断四分型之「死链」：链接目标文件不存在。每条携溯源三元组（源文件:行+原文+规则标识）+诊断型。
    R["正文死链"] = [{"源文件": s, "行": l, "原文": raw,
                     "规则": ("wiki_link" if raw.startswith("[[") else "md_link"), "诊断型": "死链"}
                     for s, dst, raw, l in g.body_links if not dst
                     and not raw.startswith(("http://", "https://"))]
    # 参数登记检查：conv.param_registry（文件名）为登记基准；无「参数」kind 或未配置→自然空（通用语料 no-op）
    reg_params = {i for i, occ in g.id_occ.items()
                  if g.id_kind[i] == "参数" and any(Path(r).name == conv.param_registry for r, _l, _t in occ)}
    R["未登记参数_出现≥3次"] = sorted(
        ((i, len(occ)) for i, occ in g.id_occ.items()
         if g.id_kind[i] == "参数" and i not in reg_params and len(occ) >= 3),
        key=lambda kv: -kv[1])
    unresolved = Counter(w for _s, w, _n, dst, _l in g.sec_refs if dst is None)
    R["节引用前缀未解析TOP"] = unresolved.most_common(15)
    # DG-42 诊断四分型之「断锚」：§N 目标无此节。改逐条溯源（源文件:行+原文+目标）——原按 (dst §n) 计数
    # 聚合丢了引用处坐标，无法据此定位；per-occurrence 使任一断锚告警可脱离工具核验（EG-21-AC2）。
    R["节引用断锚"] = sorted(
        ({"源文件": s, "行": l, "原文": (f"{w} §{n}" if w else f"§{n}"),
          "规则": ("section_ref_self" if s == dst else "section_ref"),   # s==dst 仅自引（DG-51；sec_refs 内恒 s≠dst）
          "诊断型": "断锚", "目标": f"{dst} §{n}"}
         for s, w, n, dst, l in g.sec_refs + g.self_sec_refs
         if dst and n not in g.docs[dst]["headings"]
         and not any(h == n or h.startswith(n + ".") for h in g.docs[dst]["headings"])),
        key=lambda x: (x["目标"], x["源文件"], x["行"]))
    R["缺frontmatter"] = sorted(d for d, v in g.docs.items() if not v["has_fm"])
    try:                        # 实体层检查项由同一发布包提供；失败时保留文档层结果并显式降级
        import entity_check
        R.update(entity_check.sections(g, conv))
    except (ImportError, AttributeError, TypeError) as e:
        # 未交付(ImportError) 或原子协调波重写中(AttributeError：引用已迁符号 / TypeError：eg-1 旧签名
        # sections(g) 撞新调用 sections(g,conv))——文档层检查仍有效，降级只跑文档层并明示（不静默）；
        # 波7 check 重做后签名一致、落 EG-15 完整真值表判定，届时不再触发。
        print(f"（实体层检查跳过：{type(e).__name__}——entity 层未交付或重写中）", file=sys.stderr)
    import entity_model as _M        # schema 家园恒在（DG-43 manifest 单源构造器）
    R = {"context_manifest": _M.context_manifest(
        "worktree", conv, "check", body=R,
        include_archived=getattr(g, "include_archived", False)), **R}  # DG-43
    def txt():
        m = R["context_manifest"]
        print(f"[context_manifest] corpus={m['corpus_revision']} tool={m['tool_version']} "
              f"conv={m['conventions_source']}:{m['conventions_hash']} output={m['output_hash']}")
        order = ["fm_断链", "单向边_我列它为下游_它未列我为上游", "单向边_我列它为上游_它未列我为下游",
                 "正文死链", "未登记参数_出现≥3次", "节引用断锚", "节引用前缀未解析TOP",
                 "fm_无链接条目", "fm_有意非链接条目", "缺frontmatter"]
        order += [k for k in R if k not in order and k != "context_manifest"]
        for k in order:
            v = R[k]
            if isinstance(v, str):      # 标量元信息键（schema_version）：直印，勿按集合逐字符渲染
                print(f"\n[{k}] {v}")
                continue
            # 判定对象（entity_check._Verdict，dict 子类）：len(dict)=键数（恒5/带说明6）非工作量，
            # 计数取 findings；说明字段（休眠反假绿信号，DG-47）须渲染。v[:cap] 切片本就走 findings。
            vd = isinstance(v, dict)
            n = len(v.get("findings", [])) if vd else len(v)
            print(f"\n[{k}] {n} 项")
            if vd and v.get("说明"):
                print(f"  说明：{v['说明']}")
            cap = 8 if k in ("缺frontmatter", "fm_无链接条目", "fm_有意非链接条目") else 25
            for item in v[:cap]:
                print(f"  {json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list, tuple)) else item}")
            if n > cap:
                print(f"  … 另 {n - cap} 项（--json 看全量）")
    _emit(R, as_json, txt)
    if gate:                    # EG-9-AC4：指定判定项非空→非零退出；键名拼错→2（fail-closed）
        items = [json_contract.to_internal_key(x.strip()) for x in gate.split(",") if x.strip()]
        unknown = [x for x in items if x not in R]
        if unknown:
            print(f"--gate 未知键：{'、'.join(unknown)}；可用键：{'、'.join(R)}", file=sys.stderr)
            return 2
        bad = {x: _gate_count(R[x]) for x in items if _gate_hit(R[x])}
        if bad:
            print("GATE FAIL: " + "、".join(f"{k}×{v}" for k, v in bad.items()), file=sys.stderr)
            return 1
        print("GATE PASS: " + "、".join(items), file=sys.stderr)
    return 0

def cmd_html(g, out):
    def top_dir(rel):
        # html 可视化的目录分组：取相对路径顶层目录名（如 internal/）；根目录文件归"仓库根"。
        # 分组从被扫语料实际路径运行时推导，不写死任何具体项目的目录结构。
        i = rel.find("/")
        return rel[:i] if i >= 0 else i18n.text("Repository root", "仓库根")
    groups = sorted({top_dir(rel) for rel in g.docs})   # 按名称稳定排序→色槽位顺序（分组数随语料变化）
    gindex = {name: i for i, name in enumerate(groups)}
    def gid(rel):
        return gindex[top_dir(rel)]
    agg = Counter()
    # DG-61：三通道边发射一律限语料成员（dst∈g.docs）——archive_globs 默认排除下，指向归档件的
    # 解析成功链接曾发射图外端点边（页内 JS 解引用 TypeError 白屏；与 DG-59 给 cmd_check 加的
    # 同名守卫同源，html 面当时漏改。NBL 适配方案 §11 遗留5 handback）。s 侧恒为成员（扫描面），
    # 但 fm 上游向翻转会把图外 dst 翻到 u 位，故守卫必须在翻转前按 dst 判。
    for s, dst, _k, dr, _e, _r in g.fm_edges:    # 统一方向为 上游→下游（非方向键按 src→dst）
        if dst and dst != s and dst in g.docs:
            u, v = (dst, s) if dr == "up" else (s, dst)
            agg[(u, v, "fm")] += 1
    for s, dst, _raw, _l in g.body_links:
        if dst and dst != s and dst in g.docs:
            agg[(s, dst, "link")] += 1
    for s, _w, _n, dst, _l in g.sec_refs:
        if dst and dst != s and dst in g.docs:
            agg[(s, dst, "sec")] += 1
    edges = [{"s": u, "t": v, "k": k, "w": w} for (u, v, k), w in agg.items()]
    din, dout = Counter(), Counter()
    for e in edges:
        dout[e["s"]] += 1
        din[e["t"]] += 1
    nodes = []
    # DG-61：arc 归档标记降 conv.archive_globs 单源（--include-archived 取证态按声明模式标虚环/
    # 开关；项目声明非 Archive 命名的归档目录时旧 "/Archive/" 子串启发式会整体失明）；
    # 未声明 globs 的语料回落旧子串启发式（省略≠关闭，纯显示层习惯保留）。
    agl = getattr(g.conv, "archive_globs", None) if g.conv else None
    for rel, d in g.docs.items():
        meta = d["meta"]
        goal = next((meta[k] for k in json_contract.frontmatter_candidates("purpose") if meta.get(k)), [])
        status = next((meta[k] for k in json_contract.frontmatter_candidates("status") if meta.get(k)), [])
        nodes.append({
            "id": rel, "path": rel, "stem": d["stem"], "g": gid(rel),
            "arc": (corpus.archived(rel, agl) if agl else "/Archive/" in rel), "fm": d["has_fm"],
            "goal": _clip(" ".join(goal), 160) if goal else "",
            "status": _clip(" ".join(status), 80) if status else "",
            "din": din[rel], "dout": dout[rel]})
    stats = {"docs": len(nodes),
             "fm": sum(1 for e in edges if e["k"] == "fm"),
             "link": sum(1 for e in edges if e["k"] == "link"),
             "link_refs": sum(e["w"] for e in edges if e["k"] == "link"),
             "sec": sum(1 for e in edges if e["k"] == "sec"),
             "sec_refs": sum(e["w"] for e in edges if e["k"] == "sec")}
    payload = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "groups": groups, "nodes": nodes, "edges": edges, "stats": stats}
    tpl = (Path(__file__).parent / "internal" / "graph_template.html").read_text(encoding="utf-8")
    tpl = i18n.localize_html(tpl)
    html = tpl.replace("/*__DATA__*/null",
                       json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    out_path = Path(out) if out else Path("graph.html")
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.write_text(html, encoding="utf-8")
    print(i18n.text(
        f"Generated {out_path} ({stats['docs']} nodes / {len(edges)} edges: "
        f"dependencies {stats['fm']}, links {stats['link']}, section references {stats['sec']})",
        f"已生成 {out_path}（{stats['docs']} 节点 / {len(edges)} 边：上下游 {stats['fm']}、链接 {stats['link']}、§引用 {stats['sec']}）",
    ))
    return 0

# ---------------- main ----------------

def _entity(name):
    """Lazy-load an entity-layer module and report a concise diagnostic on failure."""
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError:
        print(i18n.text(
            f"Entity-layer module {name}.py is unavailable.",
            f"实体层模块 {name}.py 不可用。",
        ), file=sys.stderr)
        return None

def main(argv):
    as_json = "--json" in argv
    corpus_dir = gate = baseline = conventions_dir = manifest = kind_arg = preset = None
    lang = "zh-CN"
    classify_mode = fields_arg = None
    brief_mode, brief_budget, verify_migrate = "execute", None, False   # 波13-P1/P2 预开缝旗标
    include_archived = False                                            # DG-59/EG-30 取证开关（默认过滤生效）
    args = []
    it = iter(a for a in argv if a != "--json")
    for a in it:
        if a == "--corpus":
            corpus_dir = next(it, None)
        elif a == "--gate":
            gate = next(it, None)
        elif a == "--baseline":
            baseline = next(it, None)
        elif a == "--conventions":
            conventions_dir = next(it, None)
        elif a == "--preset":
            preset = next(it, None)
        elif a == "--lang":
            lang = next(it, None)
        elif a == "--manifest":
            manifest = next(it, None)
        elif a == "--pending":
            classify_mode = "pending"
        elif a == "--validate":
            classify_mode = "validate"
        elif a == "--mode":
            brief_mode = next(it, None) or "execute"      # brief 展开模式（DG-45：execute|impact|review）
        elif a == "--budget":
            brief_budget = next(it, None)                 # brief 预算（DG-45；解释权在 entity_brief）
        elif a == "--migrate":
            verify_migrate = True                         # verify 迁移模式（DG-49）
        elif a == "--include-archived":
            include_archived = True                       # 取证开关：停用 archive_globs 过滤（DG-59/EG-30）
        elif a == "--kind":
            kind_arg = next(it, None)                     # ids/dump 类别过滤（中央解析，两命令共用）
        elif a == "--fields":
            fields_arg = next(it, None)                   # docs 字段投影（逗号分隔，保序；EG-31）
        elif a.startswith("-"):
            # 未知旗标 fail-closed（EG-9 退出码合同：2=用法错，不静默放过——原 else 分支把未知
            # 旗标吞作位置参数、verify --bogus 等静默照跑，NBL 线 2026-07-17 handback 件②）
            print(f"未知旗标：{a}；已知旗标见无参输出（--json/--corpus/--conventions/--gate/"
                  f"--baseline/--manifest/--preset/--lang/--pending/--validate/--mode/--budget/--migrate/"
                  f"--include-archived/--kind/--fields）", file=sys.stderr)
            return 2
        else:
            args.append(a)
    try:
        i18n.set_language(lang)
    except ValueError:
        print(f"Unsupported --lang: {lang}; expected en or zh-CN", file=sys.stderr)
        return 2
    if not args:
        print(i18n.help_text(__doc__))
        print(f"docstar v{__version__}")
        return 0
    cmd, rest = args[0], args[1:]
    scan_root = Path.cwd()      # 默认语料根=cwd（独立 CLI 标准行为）
    if corpus_dir:              # --corpus=语料根（相对路径按 cwd 解析）
        p = Path(corpus_dir)
        scan_root = (p if p.is_absolute() else Path.cwd() / p).resolve()
        if not scan_root.is_dir():
            print(f"--corpus 目录不存在：{corpus_dir}", file=sys.stderr)
            return 2
    corpus.ROOT = scan_root     # 语料根单一事实源（entity_verify 的 git 操作/GitSource 据此）
    # 约定集先于扫描加载（DG-33；关系通配需 directed_pairs/doc_id_kinds/§标记/aliases 注入 scan）。
    # 非法配置→退非零带诊断，不静默。默认集恒可加载，故任意 md 语料零配置仍出关系图。
    try:
        if conventions_dir and preset:
            raise conventions.ConventionsError("--conventions and --preset are mutually exclusive")
        conv = conventions.load_conventions(
            corpus_root=scan_root, explicit_dir=conventions_dir, preset=preset)
    except conventions.ConventionsError as e:
        print(f"约定配置非法：{e}", file=sys.stderr)
        return 2
    g = scan(corpus.FileSource(scan_root), conv, include_archived=include_archived)

    # 文档层（关系通配，零配置可用）
    if cmd == "graph":
        return cmd_graph(g, as_json)
    if cmd == "doc" and rest:
        return cmd_doc(g, " ".join(rest), as_json)
    if cmd == "id" and rest:
        return cmd_id(g, " ".join(rest), as_json)
    if cmd == "ids":
        return cmd_ids(g, conv, json_contract.to_internal_token(kind_arg), as_json)
    if cmd == "docs":
        fields = [x.strip() for x in fields_arg.split(",") if x.strip()] if fields_arg else []
        return cmd_docs(g, rest[0] if rest else None, fields, as_json)
    if cmd == "html":
        return cmd_html(g, rest[0] if rest else None)
    if cmd == "check":
        return cmd_check(g, as_json, gate, conv)
    if cmd == "html-entity":
        mod = _entity("entity_html")
        return mod.cmd_html_entity(g, conv, rest[0] if rest else None) if mod else 2
    if cmd == "dump":
        mod = _entity("entity_extract")
        return mod.cmd_dump(g, conv, as_json, json_contract.to_internal_token(kind_arg)) if mod else 2
    if cmd == "trace" and rest:
        mod = _entity("entity_trace")
        return mod.cmd_trace(g, conv, " ".join(rest), as_json) if mod else 2
    if cmd == "brief" and rest:
        mod = _entity("entity_brief")
        return mod.cmd_brief(g, conv, " ".join(rest), as_json,
                             mode=brief_mode, budget=brief_budget) if mod else 2
    if cmd == "verify":
        mod = _entity("entity_verify")
        if verify_migrate:                                 # DG-49（波13-P2 交付 cmd_verify_migrate）
            if mod and hasattr(mod, "cmd_verify_migrate"):
                return mod.cmd_verify_migrate(g, conv, baseline, as_json)
            print("verify --migrate 不可用：entity_verify 模块缺失或版本不含迁移模式", file=sys.stderr)
            return 2
        return mod.cmd_verify(g, conv, baseline, as_json) if mod else 2
    if cmd == "drift":
        mod = _entity("entity_drift")                      # DG-48（波13-P2 交付 entity_drift.py）
        return mod.cmd_drift(g, conv, as_json) if mod else 2
    if cmd == "classify":
        if classify_mode is None:
            print("classify 须指定 --pending 或 --validate（见用法）", file=sys.stderr)
            return 2
        mod = _entity("entity_classify")
        return mod.cmd_classify(g, conv, classify_mode, baseline, manifest, as_json) if mod else 2
    if cmd == "harvest":
        mod = _entity("entity_harvest")
        return mod.cmd_harvest(g, conv, as_json, baseline) if mod else 2
    print(i18n.help_text(__doc__))
    print(f"docstar v{__version__}")
    return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
