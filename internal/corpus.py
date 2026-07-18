#!/usr/bin/env python3
"""corpus — 语料源抽象与语料边界原语（波5 地基；控制者唯一写者，DG-1）。

承载需求 r9 / 设计 v2 的四个机制，全部是「机制」不含项目 schema（具体锚表注入）：
  1. Source        扫描源抽象：文件系统根 | 指定 git revision（DG-21；verify --baseline 复用）
  2. strip_strike  删除线剔除（EG-11-AC5；文内级语料边界，保行号）
  3. nature        性质读取：frontmatter + 节级覆盖；缺→unknown（EG-11-AC2/AC3，非缺省记述）
  4. namespace     命名空间作用域解析（DG-28：文档>节>表列，一函数替四补丁）

零依赖 stdlib；git 源经 subprocess 调本仓 git（VCS 非外部服务，README 已用）。
引擎不调模型、不含 prompt（G7 不变量）。自验证：python3 corpus.py --selftest
"""

import fnmatch
import re
import subprocess
from pathlib import Path

# ROOT = **当前语料根**（独立工具：不再假设自己位于 <repo>/ 之下）。
# 默认 cwd（标准 CLI 行为：相对路径按 cwd 解析）；main() 依 --corpus 覆写为实际语料根。
# 消费者（FileSource 默认根 / GitSource 仓库 / entity_verify 的 git 操作）据此自动落到语料仓。
ROOT = Path.cwd()
TOOL_DIR = Path(__file__).resolve().parent                        # 工具自身目录（模板/fixtures 等自带资产）
EXCLUDE_PARTS = frozenset({
    ".git", ".agents", ".claude", ".codex", ".docstar", "node_modules",
})
ROOT_CONTROL_DIRS = frozenset({"agents"})
CONTROL_DOC_BASENAMES = frozenset({
    "agent.md", "agents.md", "agents.override.md", "claude.md", "skill.md",
})


def excluded_doc(rel):
    """控制文件、隐藏配置子树和仓库根 agents/ 不入语料；业务 docs/agents/ 保留。"""
    parts = Path(rel).parts
    return (any(part in EXCLUDE_PARTS for part in parts)
            or bool(parts and parts[0] in ROOT_CONTROL_DIRS)
            or bool(parts and parts[-1].casefold() in CONTROL_DOC_BASENAMES))

# ==================== 1. Source：扫描源抽象（DG-21） ====================
# scan(src) 消费 Source；工作树与 git revision 同一接口，verify --baseline 无需第二套扫描逻辑。


class FileSource:
    """文件系统根（工作树或 --corpus 指定的语料根）。"""

    def __init__(self, root=None):
        self.root = Path(root if root is not None else ROOT).resolve()   # 调用时解析（ROOT 可被 main 覆写）
        self.label = str(self.root)

    def docs(self):
        out = []
        for p in sorted(self.root.rglob("*.md")):
            rel = p.relative_to(self.root)
            if excluded_doc(rel):
                continue
            out.append(rel.as_posix())   # rel 恒 POSIX `/`（Windows 归一；GitSource 天然 `/`——docs glob 与全库 `/` 假设跨平台一致，DG-59 分隔符教训）
        return out

    def text(self, rel):
        try:
            return (self.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None


class GitSource:
    """指定 git revision 的语料快照（DG-21；EG-14-AC3 verify 基线用）。
    只读该 revision 下 scan_root 子树的 .md，路径 rel 相对 scan_root（与 FileSource 同形）。"""

    def __init__(self, revision, scan_root=".", repo=None):
        self.revision = revision
        self.scan_root = scan_root.strip("/")
        self.repo = Path(repo if repo is not None else ROOT).resolve()   # 调用时解析（同 FileSource）
        self.label = f"{revision}:{self.scan_root}"

    def _git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True, text=True, check=True).stdout

    def docs(self):
        # -z：NUL 分隔、禁 core.quotepath 八进制转义（非 ASCII 路径会带引号，破 .md 判定）
        try:
            listing = self._git("ls-tree", "-r", "--name-only", "-z",
                                 self.revision, "--", self.scan_root)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        out = []
        prefix = self.scan_root + "/"
        for path in listing.split("\0"):
            if not path.endswith(".md"):
                continue
            rel = path[len(prefix):] if path.startswith(prefix) else path
            if excluded_doc(rel):
                continue
            out.append(rel)
        return sorted(out)

    def text(self, rel):
        full = f"{self.scan_root}/{rel}" if self.scan_root else rel
        try:
            return self._git("show", f"{self.revision}:{full}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None


# ==================== 2. 删除线剔除（EG-11-AC5） ====================
# ~~...~~ 跨度内文本不入图（防 `前置: ~~X-06 裁定~~` 型死依赖假边）。
# 保行号、保列位：内容替换为等长空格，file:line 溯源不偏移。真实语料删除线均单行。

_STRIKE_RE = re.compile(r"~~(.+?)~~")


def strip_strikethrough(text):
    """删除线跨度置空（保长度→保行列）。返回处理后文本。"""
    if "~~" not in text:
        return text
    def blank(m):
        return " " * (len(m.group(0)))          # 含 ~~ 标记本身，等长空格
    return "\n".join(_STRIKE_RE.sub(blank, ln) for ln in text.split("\n"))


# ============ 2b. 代码遮罩（DG-41 围栏/行内代码剥离；与 strip_strikethrough 同层） ============
# fenced code（```/~~~ 围栏）与 inline code（成对反引号）内的示例文本不当真链接/引用/ID。
# 置空为等长空格（保行列→file:line 溯源不偏移，同 strip_strikethrough）。
# 粒度分层（mask_inline）：围栏恒遮罩；inline 仅在 mask_inline=True 时遮罩——因反引号在某些
# 约定里是实体语法（参数 `X_y`、测试名），ID 提及扫描须保留反引号内文本，故 ID 提及用 mask_inline=False
# （仅剥围栏示例）、链接/§引用用 mask_inline=True（剥围栏+行内，链接/引用绝不合法地写在反引号内）。

_FENCE_OPEN_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})")


def _mask_inline_backticks(ln):
    """行内成对反引号跨度（等长运行配对，GFM 语义）置空（含反引号本身）；未配对反引号留字面。"""
    if "`" not in ln:
        return ln
    out = list(ln)
    i, n = 0, len(ln)
    while i < n:
        if ln[i] != "`":
            i += 1
            continue
        j = i
        while j < n and ln[j] == "`":
            j += 1
        run = j - i                              # 开启反引号运行长度
        k = j
        while k < n:                             # 找等长闭合运行
            if ln[k] == "`":
                p = k
                while p < n and ln[p] == "`":
                    p += 1
                if p - k == run:
                    for x in range(i, p):
                        out[x] = " "
                    i = p
                    break
                k = p
            else:
                k += 1
        else:
            i = j                                # 无闭合→开启反引号留字面，越过
    return "".join(out)


def code_mask(text, mask_inline=True):
    """围栏代码块（+可选行内代码）置空（保行列）。返回处理后文本，供链接/§引用/ID 提及扫描先过。

    围栏：```/~~~（缩进 ≤3 空格）配对，闭合围栏同字符、长度 ≥ 开启、其后仅空白；围栏行本身亦置空。
    行内：mask_inline=True 时成对反引号跨度置空（DG-41）。未闭合围栏延至文末（GFM）。
    保守边界：缩进码块（4 空格/tab）不识别——中文散文/嵌套列表缩进与其无法确定性区分，误遮会
    藏真链接（比漏遮一例缩进码块更糟）；观测到的假阳全在 ```/`` 围栏与行内，本实现全覆盖。"""
    if "`" not in text and "~~~" not in text:
        return text
    out, fence = [], None                        # fence=(字符, 长度) 表示在围栏内
    for ln in text.split("\n"):
        if fence is None:
            fo = _FENCE_OPEN_RE.match(ln)
            if fo:
                fence = (fo.group(2)[0], len(fo.group(2)))
                out.append(" " * len(ln))
                continue
            out.append(_mask_inline_backticks(ln) if mask_inline else ln)
        else:
            ch, length = fence
            out.append(" " * len(ln))
            cm = re.match(r"^\s{0,3}(" + re.escape(ch) + r"{" + str(length) + r",})\s*$", ln)
            if cm:
                fence = None
    return "\n".join(out)


# ==================== 3. 性质读取（EG-11-AC1/AC2/AC3） ====================
# 判定参与开关，非存在开关（EG-D10）。缺→unknown（非缺省记述，P0-2）。
# 节级 `性质: 规范` 紧随标题→覆盖文档缺省（章节级提升，混合文档不逼整篇二选一）。

NATURE_VALUES = ("规范", "记述")
NATURE_ALIASES = {
    "规范": "规范", "normative": "规范",
    "记述": "记述", "descriptive": "记述",
}
_NATURE_LINE_RE = re.compile(r"^\s*(?:性质|nature)\s*[：:]\s*(\S+)\s*$", re.I)
_BRACKET_BASE_RE = re.compile(r"^(.*?)（[^（）]*）$")


def normalize_nature(value):
    """Return the internal nature token for a canonical or legacy alias."""
    return NATURE_ALIASES.get(str(value).strip())


def doc_nature(meta, conv=None):
    """frontmatter meta（parse_frontmatter 产出：键→值列表）→ 规范|记述|unknown。
    conv.nature_source 声明时（DG-53/EG-26）：无显式 `性质` 键才按 {field, map} 映射取值；
    map 未中且声明 normalize="bracket-base"（DG-56/EG-27）时剥括注单次回落再查；
    显式 `性质` 恒最高且短路（键在而值非法→unknown，不被映射掩盖）。conv 缺省=原语义。"""
    if isinstance(meta, dict):
        declared = []
        for key in ("nature", "性质"):
            if key not in meta:
                continue
            vals = meta[key]
            raw = vals[0] if isinstance(vals, list) and vals else "" if isinstance(vals, list) else vals
            declared.append(normalize_nature(raw))
        if declared:                                  # 显式键存在即短路；双写冲突 fail-closed
            return declared[0] if declared[0] and len(set(declared)) == 1 else "unknown"
    ns = getattr(conv, "nature_source", None) if conv is not None else None
    if ns and isinstance(meta, dict):
        mv = meta.get(ns["field"])
        if mv:
            raw = mv[0].strip() if isinstance(mv, list) else str(mv).strip()
            mapped = normalize_nature(ns["map"].get(raw))
            if mapped:
                return mapped
            if ns.get("normalize") == "bracket-base":      # 单次剥离不递归；仅全角括号（DG-56/EG-27）
                m = _BRACKET_BASE_RE.match(raw)
                base = m.group(1).strip() if m else ""
                if base:
                    mapped = normalize_nature(ns["map"].get(base))
                    if mapped:
                        return mapped
    return "unknown"


def section_nature_overrides(lines, heading_re):
    """扫正文，收「标题行后紧跟 `性质: X` 行」→ {标题锚: 规范|记述}（EG-11-AC3）。
    heading_re 由调用方注入（实体层 ENTITY_HEADING_RE，group(2)=锚）。"""
    overrides = {}
    pending_anchor = None
    for ln in lines:
        hm = heading_re.match(ln)
        if hm:
            pending_anchor = hm.group(2)
            continue
        if pending_anchor is not None:
            nm = _NATURE_LINE_RE.match(ln)
            value = normalize_nature(nm.group(1)) if nm else None
            if value:
                overrides[pending_anchor] = value
            if ln.strip():                       # 非空行后不再是「紧随标题」
                pending_anchor = None
    return overrides


def in_judgment_domain(nature):
    """门禁域纳入判据（EG-11-AC2 保守侧）：规范与 unknown 进域，记述不进。
    unknown 进域至多产生可见假门禁；排除它产生不可见漏义务，取可见侧。"""
    return nature in ("规范", "unknown")


# ============ 3b. 归档子树过滤（DG-59/EG-30；语料边界原语，与 EXCLUDE_PARTS 同一枚举轴的声明化） ============

def archived(rel, globs):
    """rel（语料根相对路径）的任一路径段（目录名或文件名）命中 globs 任一模式（fnmatchcase 段匹配）
    → True（该文件不入语料）；globs 为 None/空 → False（特性休眠）。段匹配使子树语义天然任意深度——
    单模式如 "Archive" 覆盖一切深度的 Archive/ 子树，无需 "Archive/**"/"**/Archive/**" 双模式声明。"""
    if not globs:
        return False
    return any(fnmatch.fnmatchcase(part, pat) for part in Path(rel).parts for pat in globs)


# ==================== 4. 命名空间作用域（DG-28：一函数替三补丁） ====================
# 裸 ID 归属由「最具体语境」锚定：表列 > 节 > 文档兜底（r11 订正——词法作用域是
# 最内层优先；r10 原写「文档>节>表列」把方向搞反，会让文档默认压过映射表列语境）。
# 替代 r8 三处补丁：歧义降级条款 / DG-14 E节豁免 / EG-1-AC4 映射表豁免。
# （「别名同目录优先」= §引用文档消歧 same_dir_pick，是另一解析问题，独立保留，见下。）
# 具体锚表（E节→E-D、映射表→REQUIREMENTS）由调用方注入，corpus 只做优先级机制。


def resolve_namespace(doc_ns=None, section_ns=None, column_ns=None):
    """最具体语境优先取命名空间锚；全空→None（歧义降级：不建实体不建边，EG-12-AC5）。
    column_ns 所在表列语境（最具体，如映射表 R 列→'REQUIREMENTS'）——最强
    section_ns 所在节语境（如 E 节→'REQUIREMENTS-E'）
    doc_ns    文档 frontmatter `namespace:` 声明——兜底默认（非强制覆盖：一个 ID 明明
              在映射表 R 列就归 REQUIREMENTS，文档默认不该压它；真要强制是 per-ID 不是 per-doc）"""
    for ns in (column_ns, section_ns, doc_ns):   # 最具体 → 兜底
        if ns:
            return ns
    return None


def same_dir_pick(candidates, src_rel):
    """§引用前缀多命中时同目录优先（§引用文档消歧，非命名空间作用域——EG-12-AC5 注：
    与 resolve_namespace 是两个解析问题，独立保留）。返回唯一同目录命中，否则 None。"""
    src_dir = str(Path(src_rel).parent)
    same = [c for c in candidates if str(Path(c).parent) == src_dir]
    return same[0] if len(same) == 1 else None


# ==================== 自验证（测量装置先于被测对象） ====================


def _selftest():
    import re as _re
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    # 1. 删除线剔除：保行号、内容置空、ID 消失
    t = "前置: ~~X-06 裁定~~ 已解除\n正常行 REQ-31"
    s = strip_strikethrough(t)
    check("删除线：行数不变", len(s.split("\n")) == 2)
    check("删除线：X-06 消失", "X-06" not in s.split("\n")[0])
    check("删除线：跨度外 ID 保留", "REQ-31" in s)
    check("删除线：列位不偏移（等长）", len(s.split("\n")[0]) == len(t.split("\n")[0]))
    check("删除线：无 ~~ 时原样返回", strip_strikethrough("无删除线") == "无删除线")

    # 1b. 代码遮罩（DG-41）：围栏/行内代码内示例置空、保行列；围栏外真链接保留
    fenced = "见示例：\n```\n[[假链接]] 见 specB §3\n```\n真链接 [x](y.md)"
    cm = code_mask(fenced)
    check("代码遮罩：围栏内 [[假链接]] 消失", "[[假链接]]" not in cm)
    check("代码遮罩：围栏内 §3 消失", "specB §3" not in cm)
    check("代码遮罩：围栏外真链接保留", "[x](y.md)" in cm)
    check("代码遮罩：行数不变（保行号）", len(cm.split("\n")) == len(fenced.split("\n")))
    inl = "参考 `[[X]]` 与 `设计 §2` 示例，但参数 `retry_limit` 是语法"
    check("代码遮罩：行内 [[X]] 消失", "[[X]]" not in code_mask(inl))
    check("代码遮罩：行内 §2 消失", "设计 §2" not in code_mask(inl))
    check("代码遮罩：mask_inline=False 保留行内（ID 语法面）", "retry_limit" in code_mask(inl, mask_inline=False))
    check("代码遮罩：列位不偏移（等长）",
          all(len(a) == len(b) for a, b in zip(code_mask(inl).split("\n"), inl.split("\n"))))
    check("代码遮罩：无代码时原样返回", code_mask("普通一行无代码") == "普通一行无代码")
    check("代码遮罩：~~~ 围栏亦识别",
          "[[t]]" not in code_mask("~~~\n[[t]]\n~~~"))

    # 2. 性质：缺→unknown（非缺省记述）；显式值透传
    check("性质：缺声明=unknown", doc_nature({}) == "unknown")
    check("性质：规范透传", doc_nature({"性质": ["规范"]}) == "规范")
    check("性质：记述透传", doc_nature({"性质": ["记述"]}) == "记述")
    check("性质：非法值=unknown", doc_nature({"性质": ["随便"]}) == "unknown")
    # nature_source 映射（DG-53/EG-26）
    _ns = type("C", (), {"nature_source": {"field": "类型", "map": {"结论型": "规范", "过程型": "记述"}}})()
    check("性质：映射生效（无显式键）", doc_nature({"类型": ["结论型"]}, _ns) == "规范")
    check("性质：映射未命中=unknown（不猜）", doc_nature({"类型": ["随笔"]}, _ns) == "unknown")
    check("性质：显式恒最高（短路映射）", doc_nature({"性质": ["记述"], "类型": ["结论型"]}, _ns) == "记述")
    check("性质：显式非法不落映射", doc_nature({"性质": ["随便"], "类型": ["结论型"]}, _ns) == "unknown")
    check("性质：显式空值不落映射（键存在门，critic F1）", doc_nature({"性质": [], "类型": ["结论型"]}, _ns) == "unknown")
    check("性质：conv 缺省=原语义", doc_nature({"类型": ["结论型"]}) == "unknown")
    # nature_source.normalize：括号剥离归一（DG-56/EG-27）
    _ns_norm = type("C", (), {"nature_source": {
        "field": "类型",
        "map": {"结论型": "规范", "过程型": "记述", "结论型（需求池）": "记述"},
        "normalize": "bracket-base"}})()
    check("归一：精确命中优先于剥离", doc_nature({"类型": ["结论型（需求池）"]}, _ns_norm) == "记述")
    check("归一：剥离回落取基值", doc_nature({"类型": ["结论型（评估）"]}, _ns_norm) == "规范")
    check("归一：附注含次级分隔（·）不碍剥离",
          doc_nature({"类型": ["结论型（需求基线·公共前提）"]}, _ns_norm) == "规范")
    check("归一：normalize 缺席不回落", doc_nature({"类型": ["结论型（评估）"]}, _ns) == "unknown")
    check("归一：基值归一后仍未中=unknown", doc_nature({"类型": ["随笔（草）"]}, _ns_norm) == "unknown")
    check("归一：半角括号不剥=unknown", doc_nature({"类型": ["结论型(评估)"]}, _ns_norm) == "unknown")
    check("归一：空基值不二次查=unknown", doc_nature({"类型": ["（评估）"]}, _ns_norm) == "unknown")
    check("归一：空附注仍剥（结论型（）→基值）", doc_nature({"类型": ["结论型（）"]}, _ns_norm) == "规范")
    check("归一：基值尾随空白剥净", doc_nature({"类型": ["结论型 （评估）"]}, _ns_norm) == "规范")
    check("归一：附注内半角括号不碍剥离", doc_nature({"类型": ["结论型（a(b)注）"]}, _ns_norm) == "规范")
    check("归一：双组值单次剥离不递归（剥一层得 基值（附注），仍未中=unknown）",
          doc_nature({"类型": ["结论型（评估）（草）"]}, _ns_norm) == "unknown")
    check("归一：显式 性质 非法值仍短路（不被归一映射掩盖）",
          doc_nature({"性质": ["乱来"], "类型": ["结论型（评估）"]}, _ns_norm) == "unknown")
    check("门禁域：规范进", in_judgment_domain("规范"))
    check("门禁域：unknown 保守进", in_judgment_domain("unknown"))
    check("门禁域：记述不进", not in_judgment_domain("记述"))

    # 3. 节级覆盖：标题后紧跟 `性质: 规范`
    hre = _re.compile(r"^(#{1,6})\s*(?:§\s*)?(\d+[A-Z]?(?:\.\d+)*)(?:[.、:：\s]+(.*))?\s*$")
    lines = ["## 2.1 某裁决", "性质: 规范", "正文", "## 3 调研", "记了点东西"]
    ov = section_nature_overrides(lines, hre)
    check("节级覆盖：2.1 提升为规范", ov.get("2.1") == "规范")
    check("节级覆盖：3 无覆盖", "3" not in ov)

    # 4. 命名空间作用域：优先级 + 同目录消歧
    # 最具体优先：表列 > 节 > 文档兜底（r11；三层冲突案例=评审要求）
    check("作用域：三层冲突→表列最强", resolve_namespace("docNS", "secNS", "colNS") == "colNS")
    check("作用域：无表列→节次之", resolve_namespace("docNS", "REQUIREMENTS-E", None) == "REQUIREMENTS-E")
    check("作用域：只有文档→兜底", resolve_namespace("docNS", None, None) == "docNS")
    check("作用域：映射表 R 列不被文档默认压过", resolve_namespace("某文档NS", None, "REQUIREMENTS") == "REQUIREMENTS")
    check("作用域：全空=None（歧义降级）", resolve_namespace() is None)
    cands = ["docs/module-a/design.md", "docs/module-b/deploy-design.md"]
    check("同目录消歧：唯一同目录命中",
          same_dir_pick(cands, "docs/module-a/tasks.md") == cands[0])
    check("同目录消歧：无同目录→None",
          same_dir_pick(cands, "docs/elsewhere/X.md") is None)

    # 5. FileSource：可扫、可读、排除生效——打在**自带 fixture 语料**上（工具独立：不假设
    # 存在某个特定项目的语料形状；原断言写死 former host project 的 protocol/ 与 REQUIREMENTS.md，抽离后不成立）
    src = FileSource(TOOL_DIR.parent / "fixtures" / "corpus")   # 内部模块在 internal/，fixtures 在仓根
    docs = src.docs()
    check("FileSource：扫到 md 文档", len(docs) > 0 and all(d.endswith(".md") for d in docs))
    check("FileSource：排除 .git/.docstar 等", not any(
        p in Path(d).parts for d in docs for p in EXCLUDE_PARTS))
    check("FileSource：可读文本", bool(src.text(docs[0])) if docs else False)
    check("FileSource：rel 为语料相对（非绝对）", all(not Path(d).is_absolute() for d in docs))

    # 5b. AI agent 控制文档不是业务语料；工作树与 git 快照必须共用同一边界。
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp)
        included = {"visible.md", "nested/keep.md", "docs/agents/architecture.md"}
        files = {
            "visible.md", "nested/keep.md", "docs/agents/architecture.md",
            "AGENT.md", "agents.md", "nested/AgEnTs.Override.md", "nested/ClAuDe.md", "SKILL.md",
            "agents/author.md", "agents/reviewer.md",
            ".agents/skills/docstar/SKILL.md", ".codex/control.md", ".claude/control.md",
        }
        for rel in files:
            p = probe / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {rel}\n", encoding="utf-8")

        file_docs = set(FileSource(probe).docs())
        check("FileSource：排除 agent/claude/skill 控制文档与根 agents/，保留 docs/agents/",
              file_docs == included)

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(probe), *args], capture_output=True, text=True, check=True)

        try:
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=DocStar Selftest", "-c", "user.email=selftest@example.invalid",
                "commit", "-qm", "fixture")
            git_docs = set(GitSource("HEAD", repo=probe).docs())
            check("GitSource：与 FileSource 同语义排除控制文档与根 agents/",
                  git_docs == included and git_docs == file_docs)
        except (subprocess.CalledProcessError, FileNotFoundError):
            check("GitSource：自验证临时仓可用", False)

    print("\n  corpus 自验证：" + ("全 PASS" if ok else "有 FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
