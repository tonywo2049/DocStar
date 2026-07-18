"""conventions — per-project 约定配置的 schema / loader / 只读接口（DG-33；波5 冻结）。

波6/7 一律经此取约定（def_forms / term_forms / 命名空间锚 / harvest 过滤 / 形态表头），
不硬编码项目常量（否则波10 换第二套配置须二次重构）。entity_model 只留纯 schema，
项目值在此单一事实源。

发现契约（DG-33 / 外源评审 4.2；2026-07-17 DG-55 增祖先走查层）：
  CLI --conventions DIR 显式指定  >  语料根内 .docstar/conventions/ 项目配置  >
  祖先走查（语料根父级→git 边界，最近者胜，DG-55）  >  内置默认集
root 三义澄清：仓库根（git 边界） ≠ 语料根（--corpus，扫哪些 md） ≠ 配置目录（--conventions，读哪套约定）三者可分处。
配置带 version 字段版本化；非法配置（缺必填键 / 正则不编译 / version 不识别）→ ConventionsError（调用方退非零带诊断）。

零依赖 stdlib。自验证：python3 conventions/__init__.py --selftest
"""

import json
import re
from pathlib import Path

try:
    from . import default as _default          # 作为包被 import 时
except ImportError:                            # 作为脚本直接跑 --selftest 时
    import default as _default

SUPPORTED_VERSIONS = {"1"}                     # 配置 schema 格式版本（DG-33）
CONFIG_FILENAME = "conventions.json"
DISCOVERY_SUBPATH = ".docstar/conventions"    # 语料根内项目配置目录
PRESETS_DIR = Path(__file__).resolve().parent / "presets"

REQUIRED_KEYS = ("version", "namespaces", "def_forms", "term_forms", "form_headers", "harvest")
REQUIRED_NS_KEYS = ("prefix_namespaces", "kind_namespace", "req_doc", "param_registry",
                    "task_doc_stem", "mapping_doc_stem")


class ConventionsError(Exception):
    """非法配置：缺必填键 / 正则不编译 / version 不识别（DG-33）。调用方捕获→退非零带诊断。"""


class Conventions:
    """只读约定接口。构造即校验形状 + 编译正则（「正则不编译=非法」在此触发）。"""

    def __init__(self, raw, source_label="<default>"):
        self.source = source_label
        self._validate_shape(raw)
        self._raw = raw                            # 规范化 hash 源（DG-43；正则以源字符串存，与外部 JSON 同形）
        self.version = raw["version"]
        ns = raw["namespaces"]
        self._prefix_namespaces = dict(ns["prefix_namespaces"])
        self._kind_namespace = dict(ns["kind_namespace"])
        self.req_doc = ns["req_doc"]
        self.param_registry = ns["param_registry"]
        self.task_doc_stem = ns["task_doc_stem"]
        self.mapping_doc_stem = ns["mapping_doc_stem"]
        self.def_forms = {k: self._compile(v, f"def_forms.{k}")
                          for k, v in raw["def_forms"].items()}
        tf = raw["term_forms"]
        self.term_inplace = self._compile(tf["inplace"], "term_forms.inplace")
        self.term_glossary = self._compile(tf["glossary"], "term_forms.glossary")
        fh = raw["form_headers"]
        self.ledger_header = self._compile(fh["ledger"], "form_headers.ledger")
        self.changelist_header = self._compile(fh["changelist"], "form_headers.changelist")
        self.glossary_section = self._compile(fh["glossary_section"], "form_headers.glossary_section")
        h = raw["harvest"]
        self.harvest_len_range = tuple(h["len_range"])
        self._harvest_exclude = [self._compile(p, "harvest.exclude") for p in h["exclude"]]
        self.aliases = dict(raw.get("aliases", {}))
        # 文档层建边约定（关系通配；皆可选，缺省=纯通配无向图 + 无 ID 索引）
        self.doc_id_kinds = [(k, self._compile(rx, f"doc_id_kinds[{k}]"), note)
                             for k, rx, note in raw.get("doc_id_kinds", [])]
        edges = raw.get("edges", {})
        self.directed_pairs = [tuple(p) for p in edges.get("directed_pairs", [])]
        self.self_words = set(edges.get("self_words", []))
        # self_ref_words（DG-51）：self_words 中「显式自指本文档」的指代词子集——self_words 管「不成
        # 跨文档边」（含动词 见/详见），本键管其中哪些词的 §N 须做本文档锚点存在性检查（自引断锚）。
        # 缺席回落通用默认（省略≠关闭，沿 id_occ_kinds 先例）；显式 []=只关词表两形（精确/后缀），
        # 具名自引（文档名解析到本文档）不经词表、恒检。
        self.self_ref_words = list(edges.get("self_ref_words",
                                             ["本文", "本节", "本表", "上文", "下文", "上表", "下表"]))
        self.section_ref_marker = edges.get("section_ref_marker", "§")
        # nonlink_prefixes（DG-58/EG-29）：方向键（directed_pairs）无链接条目的「有意非链接」标记前缀词——
        # 条目值以任一词起头即声明为合法非链接形态（链根/仓外产物/口头裁决等），check 报告层与疑漏链分桶。
        # 缺席/显式空=无词→fm_无链接条目 回落全计（本条引入前行为，内置默认不含该键）。
        self.nonlink_prefixes = list(edges.get("nonlink_prefixes", []))
        # config-free 类型识别：类型小节词表（可选；缺省→关闭，靠 def_forms）
        self.type_sections = [(k, self._compile(rx, f"type_sections[{k}]"))
                              for k, rx in raw.get("type_sections", [])]
        # ---- 实体层抽取约定（DG-38 波12-块1：项目专有抽取形/kind 下沉配置层） ----
        # 缺席语义：id_occ_kinds/cooccur_kinds/ac_prefix_kinds 缺→通用默认（需求AC/参数/任务）；
        #           option_rows/review_item/prov_form 缺→该形休眠（沿 type_sections 先例，不 bump version）。
        # id_occ_kinds：doc_id_kinds 的 ID 提及 kind → 内容层实体 kind（哪些 ID 语法也促成实体）
        self.id_occ_kinds = dict(raw.get("id_occ_kinds", {"需求AC": "需求AC", "任务": "任务"}))
        # cooccur_kinds：参与共现索引的实体 kind（EG-2-AC9 限 ID 形实体）
        self.cooccur_kinds = set(raw.get("cooccur_kinds", ["需求AC", "参数", "任务"]))
        # ac_prefix_kinds：单元格内裸 AC id 的首字符前缀 → 实体 kind（映射/任务 spec/底账等表格通道）
        self.ac_prefix_kinds = dict(raw.get("ac_prefix_kinds", {"R": "需求AC"}))
        # task_columns：任务表表头 角色→列名（DG-54 沿 DG-52 表头单源：声明什么列名就解析什么列名；
        # 任务声明/阅读依赖/前置依赖/任务测试声明/状态属性的输入面）。缺席回落内置列名（省略≠关闭，
        # 沿 id_occ_kinds 先例）；识别判据（首列 `#` ∧ spec 列名在表头）在 extract，不在此键。
        tc = raw.get("task_columns")
        self.task_columns = ({k: v.strip() for k, v in tc.items()} if tc is not None else
                             {"spec": "spec 锚", "prereq": "前置", "red": "红先测试", "status": "状态"})
        # option_rows：表格行形自定义实体（如「决策记录表 D{n} 行」），每项 {kind, doc, row, id}
        #   doc=角色名（req_doc/param_registry/task_doc/mapping_doc）限定生效文档；None=任意文档
        #   id=正则替换模板（m.expand），如 "E-D\\1" 由 row 的捕获组构造 canonical_id
        self.option_rows = [{"kind": o["kind"], "doc": o.get("doc"),
                             "row": self._compile(o["row"], "option_rows.row"), "id": o["id"]}
                            for o in raw.get("option_rows", [])]
        # review_item：登记源文档内自识别 ID 形的实体（{form 正则, kind}）；缺→无此类实体
        ri = raw.get("review_item")
        self.review_item = ({"form": self._compile(ri["form"], "review_item.form"), "kind": ri["kind"]}
                            if ri else None)
        # prov_form：记述文档固定引用句式正则（provenance 边源）；缺→不抽 provenance
        pf = raw.get("prov_form")
        self.prov_form = self._compile(pf, "prov_form") if pf else None
        # ---- 跨类型政策：required-edge 规则集（DG-47/EG-20 收缩；additive 可选键，缺席即休眠） ----
        # 每条规则：{rule, src_kinds, edge, direction(in|out), dst_kinds?(缺=不限靶), severity(report|gate)}。
        # 语义：src_kinds 的实体须有 edge 类型的边（direction=in 须有入边即被 dst 指向，out 须有出边即指向 dst）；
        #   规则就地绑 kind（显式点名覆盖写法，防「需求」闸门静默漏「Requirements」假绿，EG-20-AC3）。
        # 缺席→[]（跨类型政策休眠：CHK-2 覆盖/映射报「无规则声明」而非假绿，DG-47）。dst_kinds 缺→None（不限靶）。
        self.required_edges = [
            {"rule": r["rule"], "src_kinds": list(r["src_kinds"]), "edge": r["edge"],
             "direction": r["direction"], "dst_kinds": (list(r["dst_kinds"]) if r.get("dst_kinds") else None),
             "severity": r.get("severity", "report")}
            for r in raw.get("required_edges", [])]
        # Kinds that are intentionally outside required-edge policy. This keeps the
        # open-kind drift warning useful without flagging generic graph/support kinds
        # (document, section, test, parameter, etc.) in every project preset.
        self.uncovered_kind_exclusions = list(raw.get("uncovered_kind_exclusions", []))
        # ---- 值漂移：受管值↔属主绑定（DG-48/EG-24；additive 可选键，缺席即休眠） ----
        # 每条：{name, owner_kind?(可选), occ(出现形正则 group(1)=值), scope(doc 角色名|null 全语料)}。
        # 缺席→[]（drift 空跑，沿休眠先例）；occ 编译，group(1) 取受管值。
        self.managed_values = [
            {"name": mv["name"], "owner_kind": mv.get("owner_kind"),
             "occ": self._compile(mv["occ"], f"managed_values.{mv['name']}.occ"),
             "occ_src": mv["occ"], "scope": mv.get("scope")}
            for mv in raw.get("managed_values", [])]
        # ---- 检查 kind 域（DG-50，补完 DG-47/EG-20 收缩；additive 可选键，缺席即休眠） ----
        # revision_target_kinds：修订声明/修订落账 的有效靶 kind 域（CHK-3 传导断裂的判定域）；
        # cooccur_mapping_kinds：共现完备性检查的 kind 域（域内 kind 定义块共现须有映射边）。
        # 缺席→[]（对应检查休眠报「无声明」而非假绿，沿 DG-47 required_edges 先例）。
        self.revision_target_kinds = list(raw.get("revision_target_kinds", []))
        # ---- 性质映射源（DG-53/EG-26；additive 可选键，缺席即休眠） ----
        # {"field": frontmatter 键, "map": {值→规范|记述}, "normalize"?: "bracket-base"}：
        # 文档无显式 `性质` 键时按此取性质；normalize 声明时 map 未中回落括注剥离再查（DG-56/EG-27）。
        # 显式 `性质` 恒最高（corpus.doc_nature 短路，拼错不被映射掩盖）。缺席→None。
        # map 值域字面与 corpus.NATURE_VALUES 同源（双写点，勿独改；分层方向选择——
        # conventions 为底层配置层不 import 处理层，非 import 环所迫，critic F2 订正）。
        ns_ = raw.get("nature_source")
        if ns_ is not None:
            if not isinstance(ns_, dict) or not isinstance(ns_.get("field"), str) or not ns_["field"].strip():
                raise ConventionsError("nature_source 须为 {field: 非空字符串, map: 非空映射}")
            extra = set(ns_) - {"field", "map", "normalize"}
            if extra:
                raise ConventionsError(
                    f"nature_source 子键须为 {{field, map, normalize}} 子集，多余键：{sorted(extra)}")
            nm = ns_.get("map")
            if not isinstance(nm, dict) or not nm:
                raise ConventionsError("nature_source.map 须为非空映射")
            nature_aliases = {"规范": "规范", "normative": "规范", "记述": "记述", "descriptive": "记述"}
            bad = sorted(str(v) for v in nm.values() if v not in nature_aliases)
            if bad:
                raise ConventionsError(f"nature_source.map 值域越界（仅 normative|descriptive 及旧中文别名）：{bad}")
            self.nature_source = {"field": ns_["field"].strip(),
                                  "map": {str(k): nature_aliases[v] for k, v in nm.items()}}
            if "normalize" in ns_:
                if ns_["normalize"] != "bracket-base":
                    raise ConventionsError('nature_source.normalize 仅支持字面量 "bracket-base"')
                self.nature_source["normalize"] = ns_["normalize"]
        else:
            self.nature_source = None
        self.cooccur_mapping_kinds = list(raw.get("cooccur_mapping_kinds", []))
        # ---------------- 归档子树语料级过滤（DG-59/EG-30；additive 可选键，缺席即休眠） ----------------
        # archive_globs：路径段（目录名或文件名）glob 模式列表——scan() 收口点消费，命中件不入语料
        # （corpus.archived 以 fnmatchcase 逐段匹配 Path(rel).parts，任一段命中即排除，子树语义天然
        # 任意深度）。声明须非空 list 且元素全为非空字符串、不含 `/`（防按路径直觉写 "Archive/**"——
        # 字面 `/` 恒不命中任何段=静默失效，一并拒收）。缺席→None（休眠，行为与引入前逐字节一致）。
        ag = raw.get("archive_globs")
        if ag is not None:
            if not isinstance(ag, list) or not ag:
                raise ConventionsError("archive_globs 须为非空列表（路径段 glob 模式，段=目录名或文件名）")
            if any(not isinstance(p, str) or not p.strip() for p in ag):
                raise ConventionsError("archive_globs 元素须为非空字符串")
            if any("/" in p for p in ag):
                raise ConventionsError(
                    "archive_globs 模式不得含 '/'（按路径段匹配，字面 '/' 恒不命中任何段——防按路径直觉误写 'Archive/**'）")
            self.archive_globs = list(ag)
        else:
            self.archive_globs = None

    @staticmethod
    def _compile(pattern, where):
        try:
            return re.compile(pattern)
        except re.error as e:
            raise ConventionsError(f"正则不编译（{where}）：{pattern!r} — {e}")

    @staticmethod
    def _validate_shape(raw):
        if not isinstance(raw, dict):
            raise ConventionsError("配置根须为对象")
        missing = [k for k in REQUIRED_KEYS if k not in raw]
        if missing:
            raise ConventionsError(f"缺必填键：{missing}")
        if raw["version"] not in SUPPORTED_VERSIONS:
            raise ConventionsError(
                f"version 不识别：{raw['version']!r}（支持 {sorted(SUPPORTED_VERSIONS)}）")
        ns_missing = [k for k in REQUIRED_NS_KEYS if k not in raw.get("namespaces", {})]
        if ns_missing:
            raise ConventionsError(f"namespaces 缺键：{ns_missing}")
        for sect in ("def_forms", "term_forms", "form_headers", "harvest"):
            if not isinstance(raw.get(sect), dict):
                raise ConventionsError(f"{sect} 须为对象")
        for k in ("inplace", "glossary"):
            if k not in raw["term_forms"]:
                raise ConventionsError(f"term_forms 缺键：{k}")
        for k in ("ledger", "changelist", "glossary_section"):
            if k not in raw["form_headers"]:
                raise ConventionsError(f"form_headers 缺键：{k}")
        for k in ("len_range", "exclude"):
            if k not in raw["harvest"]:
                raise ConventionsError(f"harvest 缺键：{k}")
        # 文档层建边约定（可选；给了就校验形状）
        dik = raw.get("doc_id_kinds", [])
        if not isinstance(dik, list) or any(
                not (isinstance(t, (list, tuple)) and len(t) == 3) for t in dik):
            raise ConventionsError("doc_id_kinds 须为 [kind, regex, note] 三元组列表")
        edges = raw.get("edges", {})
        if not isinstance(edges, dict):
            raise ConventionsError("edges 须为对象")
        dp = edges.get("directed_pairs", [])
        if not isinstance(dp, list) or any(
                not (isinstance(p, (list, tuple)) and len(p) == 2) for p in dp):
            raise ConventionsError("edges.directed_pairs 须为 [上游键, 下游键] 二元对列表")
        srw = edges.get("self_ref_words", [])
        if not isinstance(srw, list) or any(not isinstance(w, str) for w in srw):
            raise ConventionsError("edges.self_ref_words 须为字符串列表")
        nlp = edges.get("nonlink_prefixes", [])
        if not isinstance(nlp, list) or any(not isinstance(w, str) or not w.strip() for w in nlp):
            raise ConventionsError("edges.nonlink_prefixes 须为非空字符串列表（空串前缀 startswith 恒真=整桶静默吞）")
        ts = raw.get("type_sections", [])
        if not isinstance(ts, list) or any(
                not (isinstance(t, (list, tuple)) and len(t) == 2) for t in ts):
            raise ConventionsError("type_sections 须为 [kind, 标题正则] 二元对列表")
        # 实体层抽取约定（可选；给了就校验形状）
        for o in raw.get("option_rows", []):
            if not (isinstance(o, dict) and {"kind", "row", "id"} <= set(o)):
                raise ConventionsError("option_rows 每项须含 kind/row/id 键")
        ri = raw.get("review_item")
        if ri is not None and not (isinstance(ri, dict) and {"form", "kind"} <= set(ri)):
            raise ConventionsError("review_item 须含 form/kind 键")
        # required_edges（DG-47）：可选；给了就校验每条规则形状（沿 option_rows 校验先例）
        re_rules = raw.get("required_edges", [])
        if not isinstance(re_rules, list):
            raise ConventionsError("required_edges 须为列表")
        for r in re_rules:
            if not (isinstance(r, dict) and {"rule", "src_kinds", "edge", "direction"} <= set(r)):
                raise ConventionsError("required_edges 每条须含 rule/src_kinds/edge/direction 键")
            if not (isinstance(r["src_kinds"], list) and r["src_kinds"]):
                raise ConventionsError(f"required_edges[{r['rule']}] src_kinds 须为非空列表")
            if r["direction"] not in ("in", "out"):
                raise ConventionsError(f"required_edges[{r['rule']}] direction 须为 in|out")
            if r.get("dst_kinds") is not None and not isinstance(r["dst_kinds"], list):
                raise ConventionsError(f"required_edges[{r['rule']}] dst_kinds 须为列表")
            if r.get("severity", "report") not in ("report", "gate"):
                raise ConventionsError(f"required_edges[{r['rule']}] severity 须为 report|gate")
        uke = raw.get("uncovered_kind_exclusions", [])
        if not isinstance(uke, list) or any(not isinstance(k, str) or not k.strip() for k in uke):
            raise ConventionsError("uncovered_kind_exclusions 须为非空字符串列表")
        # managed_values（DG-48）：可选；给了就校验每条形状
        mvs = raw.get("managed_values", [])
        if not isinstance(mvs, list):
            raise ConventionsError("managed_values 须为列表")
        for mv in mvs:
            if not (isinstance(mv, dict) and {"name", "occ"} <= set(mv)):
                raise ConventionsError("managed_values 每条须含 name/occ 键")
        # 检查 kind 域（DG-50）：可选；给了就校验形状（kind 字符串列表）
        for key in ("revision_target_kinds", "cooccur_mapping_kinds"):
            v = raw.get(key, [])
            if not isinstance(v, list) or not all(isinstance(k, str) for k in v):
                raise ConventionsError(f"{key} 须为 kind 字符串列表")
        # task_columns（DG-54）：可选；给了就校验——整键封闭四角色（部分声明=其余列静默失明，fail-closed）；
        # 列名互撞/取 "#" 同拒（cells.index 取首现，双角色同列或绑首列识别标记=同类静默失明）
        tc = raw.get("task_columns")
        if tc is not None:
            if not isinstance(tc, dict) or set(tc) != {"spec", "prereq", "red", "status"}:
                raise ConventionsError("task_columns 须为完整四键 {spec, prereq, red, status}")
            if any(not isinstance(v, str) or not v.strip() for v in tc.values()):
                raise ConventionsError("task_columns 列名须为非空字符串")
            tvals = {v.strip() for v in tc.values()}
            if len(tvals) != 4 or "#" in tvals:
                raise ConventionsError('task_columns 列名不得互撞、不得为 "#"（任务表首列识别标记）')

    # ---------------- 只读访问（波6/7 唯一取约定入口） ----------------

    def namespace_for(self, kind, cid):
        """裸 ID 的固定命名空间锚（DG-28 兜底锚源）。任务→task_doc_stem；kind_namespace 固定锚优先；
        否则按 cid 前缀查 prefix_namespaces（任何 cid 前缀进 prefix_namespaces 的 kind 走该路径——
        配置驱动，不点名具体 kind）；无锚→None（不建实体）。"""
        if kind == "任务":
            return self.task_doc_stem
        return self._kind_namespace.get(kind) or self._prefix_namespaces.get(cid.split("-", 1)[0])

    def is_ledger_doc(self, text):
        """DG-25：文档含底账表头 → 修订底账源（非写死文件名）。"""
        return any(self.ledger_header.match(ln) for ln in text.splitlines())

    def is_changelist_header(self, line):
        """DG-25：修改清单表头（declared_impact 源）。"""
        return bool(self.changelist_header.match(line))

    def is_glossary_heading(self, title):
        """DG-27 订正：标题命中术语表节形态 → 该节内 term_glossary 生效（散文粗体+冒号海量误命中，
        故 term_glossary 须节语境约束；term_inplace 有确定标记不受限）。title=标题正文（可空）。"""
        return bool(title) and bool(self.glossary_section.search(title))

    def type_of_heading(self, title):
        """config-free 类型识别：标题正文命中某型 type_sections 词表 → 返回该 kind（该节内自然定义形成
        此 kind 实体，节级作用域抗洪水，同术语表机制）；无命中/空标题/未配置→None。"""
        if not title:
            return None
        for kind, rx in self.type_sections:
            if rx.search(title):
                return kind
        return None

    def harvest_excluded(self, word):
        """EG-5：ID 形/日期/版本号等结构化 token 不作专名候选（长度筛由 harvest_len_range 另判）。"""
        return any(rx.match(word) for rx in self._harvest_exclude)

    # ---------------- 可复现 manifest 支持（DG-43；conventions hash 入 manifest 防不可见第二事实源） ----------------

    def canonical_bytes(self):
        """规范化序列化（键排序，正则以源字符串——raw 里本就是源串）→ 确定性字节（DG-43）。
        键排序消除「等价配置不同键序产不同 hash」；同内容同字节、改配置字节必变。禁时间戳/绝对路径入源。"""
        return json.dumps(self._raw, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")

    def hash(self, n=16):
        """conventions_hash（DG-43）=规范化字节 sha256 前 n 位。配置变则 hash 变、可解释 check 差异。"""
        import hashlib
        return hashlib.sha256(self.canonical_bytes()).hexdigest()[:n]

    def source_label(self):
        """manifest 的 conventions_source（DG-43）：稳定、机器无关（禁绝对路径入输出）——
        内置默认→'default'；发现/显式项目配置→'project'。具体哪套由 conventions_hash 精确鉴别。"""
        if self.source == "<default>":
            return "default"
        if self.source.startswith("<preset:"):
            return self.source[1:-1]
        return "project"


def validate(raw, source_label="<raw>"):
    """校验 + 编译 → Conventions；非法 → ConventionsError。"""
    return Conventions(raw, source_label)


def _load_dir(config_dir):
    d = Path(config_dir)
    f = d / CONFIG_FILENAME
    if not f.is_file():
        raise ConventionsError(f"配置目录缺 {CONFIG_FILENAME}：{d}")
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConventionsError(f"配置读取/解析失败（{f}）：{e}")
    return Conventions(raw, source_label=str(f))


def _load_preset(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ConventionsError(f"preset 名称非法：{name!r}")
    path = PRESETS_DIR / f"{name}.json"
    if not path.is_file():
        available = sorted(p.stem for p in PRESETS_DIR.glob("*.json"))
        raise ConventionsError(f"preset 不存在：{name}；可选：{available}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConventionsError(f"preset 读取/解析失败（{path.name}）：{e}")
    return Conventions(raw, source_label=f"<preset:{name}>")


def load_conventions(corpus_root=None, explicit_dir=None, preset=None):
    """发现契约（DG-33/DG-55）：explicit_dir（--conventions）> 语料根/.docstar/conventions/ >
    祖先走查（语料根父级→git 边界，最近者胜，DG-55）> 内置默认。

    corpus_root=语料根（--corpus），explicit_dir=配置目录（--conventions）；与仓库根三分。
    显式指定非法即报错（不静默回退——用户明确指了就该按指的来）。"""
    if explicit_dir is not None:
        return _load_dir(explicit_dir)
    if preset is not None:
        return _load_preset(preset)
    if corpus_root is not None:
        proj = Path(corpus_root) / DISCOVERY_SUBPATH
        if (proj / CONFIG_FILENAME).is_file():
            return _load_dir(proj)
        anc = _ancestor_config_dir(corpus_root)
        if anc is not None:
            return _load_dir(anc)
    return Conventions(_default.DEFAULT, source_label="<default>")


def _ancestor_config_dir(corpus_root):
    """语料根祖先链探测：resolve 后父级起逐层上行至 git 边界（含边界目录）找项目约定配置（DG-55 走查支本体）。

    先 resolve 语料根再取 parents 链——链型物理确定，不受调用者传相对/符号链接路径影响
    （语料根一级判定与扫描不涉）；.git 文件或目录皆判界（linked worktree 的 .git 是文件）；最近者胜；
    语料根自身即 git 边界→无祖先跨度→None；上行到文件系统根仍无 .git→无边界→None（不采用边界外配置）。
    """
    root = Path(corpus_root).resolve()
    if (root / ".git").exists():
        return None
    candidate = None
    for d in root.parents:
        if candidate is None:
            p = d / DISCOVERY_SUBPATH
            if (p / CONFIG_FILENAME).is_file():
                candidate = p
        if (d / ".git").exists():
            return candidate
    return None


# ---------------- 自验证（测量装置先于被测对象） ----------------

def _selftest():
    import copy
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond

    def raises(fn):
        try:
            fn()
            return False
        except ConventionsError:
            return True

    good = copy.deepcopy(_default.DEFAULT)

    # 1. 默认集校验+编译通过
    conv = load_conventions()
    check("默认集加载（version=1）", conv.version == "1")
    check("默认集来源=<default>", conv.source == "<default>")
    gmgn = load_conventions(preset="gmgn-v1")
    check("内置预设 gmgn-v1 可加载", gmgn.source == "<preset:gmgn-v1>")
    check("gmgn-v1 固定英文任务表头",
          gmgn.task_columns == {"spec": "spec anchor", "prereq": "prerequisite",
                                "red": "failing test", "status": "status"})
    check("gmgn-v1 只把 Rn-ACn 当需求 AC",
          gmgn.type_of_heading("Requirements") is None)
    check("gmgn-v1 辅助 kind 不进入 AC→Task 策略网",
          set(gmgn.uncovered_kind_exclusions)
          == {"参数", "测试", "专名", "文档", "节条目", "里程碑"})
    check("未知预设 fail-closed", raises(lambda: load_conventions(preset="missing-preset")))

    # 2. namespace_for（通用默认值 + 前缀机制配置驱动，不点名具体 kind）
    check("命名空间：需求AC→requirements（通用默认）", conv.namespace_for("需求AC", "REQ-1") == "requirements")
    check("命名空间：无 kind_namespace 且无前缀映射→None（通用默认）", conv.namespace_for("组件AC", "X2-AC1") is None)
    check("命名空间：任务→tasks（通用默认）", conv.namespace_for("任务", "TASK-3") == "tasks")
    check("映射文档 stem（通用默认）", conv.mapping_doc_stem == "mapping")

    # 3. def_forms / term / form_headers 正则命中样例（通用形，非项目专有语法）
    check("定义形：需求AC 命中 REQ-N", bool(conv.def_forms["需求AC"].match("- **REQ-12** 某需求…")))
    check("定义形：参数命中反引号", bool(conv.def_forms["参数"].match("| `some_param` | 说明 |")))
    check("定义形：任务命中 TASK-N", bool(conv.def_forms["任务"].match("| **TASK-3** | 某任务 |")))
    check("专名就地：中文标记命中", bool(conv.term_inplace.search("**某专名**（定义：见 X）")))
    check("专名就地：英文标记命中", bool(conv.term_inplace.search("**Widget** (def: a thing)")))
    check("底账表头识别（中英）", conv.is_ledger_doc("| date | change | note |\n| x | y | z |"))
    check("非底账不误判", not conv.is_ledger_doc("普通正文\n没有表头"))
    check("术语表节标题命中（中英）",
          conv.is_glossary_heading("Glossary") and conv.is_glossary_heading("名词解释（术语表）"))
    check("讨论术语的节不误判", not conv.is_glossary_heading("范围与术语"))  # 裸「术语」非词表
    check("空标题不误判", not conv.is_glossary_heading(None))

    # 4. harvest 过滤（通用：排除纯数字/日期/版本号；普通词放行）
    check("harvest 排除纯数字", conv.harvest_excluded("123"))
    check("harvest 排除日期", conv.harvest_excluded("2026-07-15"))
    check("harvest 排除版本号", conv.harvest_excluded("v1.2.3"))
    check("harvest 放行普通词", not conv.harvest_excluded("背压门"))
    check("harvest 长度范围", conv.harvest_len_range == (2, 40))

    # 4.4 文档层建边约定（关系通配默认——通用非项目化）
    check("默认 doc_id_kinds 通用两类（需求/任务）",
          [k for k, _rx, _n in conv.doc_id_kinds] == ["需求", "任务"])
    check("默认 doc_id_kinds：REQ-12 命中",
          any(cre.search("见 REQ-12 说明") for _k, cre, _n in conv.doc_id_kinds))
    check("默认 directed_pairs 含 上游/下游 + upstream/downstream",
          ("上游", "下游") in conv.directed_pairs and ("upstream", "downstream") in conv.directed_pairs)
    check("默认 self_words 含 本文/本节", {"本文", "本节"} <= conv.self_words)
    check("默认 self_ref_words=七指代词（自引检锚域 DG-51；缺席回落≠关闭）",
          conv.self_ref_words == ["本文", "本节", "本表", "上文", "下文", "上表", "下表"])
    check("默认 self_ref_words ⊆ self_words（检锚域是「不成边」域的语义子集）",
          set(conv.self_ref_words) <= conv.self_words)
    srw_proj = copy.deepcopy(good)
    srw_proj["edges"]["self_ref_words"] = ["this-doc"]
    check("项目 self_ref_words 覆盖默认", validate(srw_proj).self_ref_words == ["this-doc"])
    check("self_ref_words 声明入 hash（DG-43）", validate(srw_proj).hash() != conv.hash())
    srw_off = copy.deepcopy(good)
    srw_off["edges"]["self_ref_words"] = []
    check("self_ref_words 显式空=关闭（区别于缺席回落默认）", validate(srw_off).self_ref_words == [])
    bad_srw = copy.deepcopy(good); bad_srw["edges"]["self_ref_words"] = "本文"
    check("非法：self_ref_words 非字符串列表报错", raises(lambda: validate(bad_srw)))
    check("默认 section_ref_marker=§", conv.section_ref_marker == "§")
    # nonlink_prefixes（DG-58/EG-29：有意非链接声明前缀词表，可选键，缺席/显式空回落全计，fail-closed）
    check("nonlink_prefixes：缺席→[]（回落全计）", conv.nonlink_prefixes == [])
    nlp_proj = copy.deepcopy(good)
    nlp_proj["edges"]["nonlink_prefixes"] = ["外部：", "泛指："]
    check("nonlink_prefixes：声明→覆盖", validate(nlp_proj).nonlink_prefixes == ["外部：", "泛指："])
    check("nonlink_prefixes 声明入 hash（DG-43）", validate(nlp_proj).hash() != conv.hash())
    nlp_off = copy.deepcopy(good)
    nlp_off["edges"]["nonlink_prefixes"] = []
    check("nonlink_prefixes 显式空=无词不报错（同缺席回落全计）", validate(nlp_off).nonlink_prefixes == [])
    bad_nlp1 = copy.deepcopy(good); bad_nlp1["edges"]["nonlink_prefixes"] = "外部："
    check("非法：nonlink_prefixes 非列表报错", raises(lambda: validate(bad_nlp1)))
    bad_nlp2 = copy.deepcopy(good); bad_nlp2["edges"]["nonlink_prefixes"] = ["外部：", " "]
    check("非法：nonlink_prefixes 含纯空白串报错（startswith 恒真防吞）", raises(lambda: validate(bad_nlp2)))
    # nature_source（DG-53/EG-26：可选键，缺席休眠，fail-closed）
    check("nature_source：缺席→None（休眠）", validate(copy.deepcopy(good)).nature_source is None)
    ns_proj = copy.deepcopy(good)
    ns_proj["nature_source"] = {"field": "类型", "map": {"结论型": "规范", "过程型": "记述"}}
    check("nature_source：声明→解析", validate(ns_proj).nature_source
          == {"field": "类型", "map": {"结论型": "规范", "过程型": "记述"}})
    check("nature_source 声明入 hash（DG-43）", validate(ns_proj).hash() != conv.hash())
    bad_ns1 = copy.deepcopy(good); bad_ns1["nature_source"] = {"field": " ", "map": {"a": "规范"}}
    check("非法：nature_source.field 空报错", raises(lambda: validate(bad_ns1)))
    bad_ns2 = copy.deepcopy(good); bad_ns2["nature_source"] = {"field": "类型", "map": {}}
    check("非法：nature_source.map 空报错", raises(lambda: validate(bad_ns2)))
    bad_ns3 = copy.deepcopy(good); bad_ns3["nature_source"] = {"field": "类型", "map": {"结论型": "policy"}}
    check("非法：nature_source.map 值域越界报错", raises(lambda: validate(bad_ns3)))
    # nature_source.normalize（DG-56/EG-27：可选子键，括号剥离归一；子键集封闭 {field, map, normalize}）
    check("nature_source：缺席 normalize 时 self.nature_source 不含该键", "normalize" not in validate(ns_proj).nature_source)
    ns_norm_proj = copy.deepcopy(good)
    # map 与 ns_proj 逐字同——hash 对比单变量（只差 normalize 一键），沿 srw/tc 对照先例
    ns_norm_proj["nature_source"] = {"field": "类型", "map": {"结论型": "规范", "过程型": "记述"}, "normalize": "bracket-base"}
    nsnorm_conv = validate(ns_norm_proj)
    check("nature_source.normalize：合法装载",
          nsnorm_conv.nature_source.get("normalize") == "bracket-base" and "normalize" in nsnorm_conv.nature_source)
    check("nature_source.normalize 声明入 hash（DG-43）", nsnorm_conv.hash() != validate(ns_proj).hash())
    bad_ns4 = copy.deepcopy(good)
    bad_ns4["nature_source"] = {"field": "类型", "map": {"结论型": "规范"}, "normalize": "prefix"}
    check("非法：nature_source.normalize 坏值报错", raises(lambda: validate(bad_ns4)))
    bad_ns5 = copy.deepcopy(good)
    bad_ns5["nature_source"] = {"field": "类型", "map": {"结论型": "规范"}, "normalize": True}
    check("非法：nature_source.normalize 非字符串报错", raises(lambda: validate(bad_ns5)))
    bad_ns6 = copy.deepcopy(good)
    bad_ns6["nature_source"] = {"field": "类型", "map": {"结论型": "规范"}, "normalise": "bracket-base"}
    check("非法：nature_source 规范外子键报错（如 normalise 拼错）", raises(lambda: validate(bad_ns6)))
    # task_columns（DG-54：可选键，缺席回落内置列名，省略≠关闭）
    check("task_columns：缺席→内置列名（省略≠关闭）",
          conv.task_columns == {"spec": "spec 锚", "prereq": "前置", "red": "红先测试", "status": "状态"})
    tc_proj = copy.deepcopy(good)
    tc_proj["task_columns"] = {"spec": "规格锚", "prereq": "前置", "red": "失败先行测试", "status": "状态"}
    check("task_columns：声明→覆盖", validate(tc_proj).task_columns
          == {"spec": "规格锚", "prereq": "前置", "red": "失败先行测试", "status": "状态"})
    check("task_columns 声明入 hash（DG-43）", validate(tc_proj).hash() != conv.hash())
    bad_tc1 = copy.deepcopy(good); bad_tc1["task_columns"] = {"spec": "规格锚"}
    check("非法：task_columns 缺角色键报错（整键封闭防静默缺列）", raises(lambda: validate(bad_tc1)))
    bad_tc2 = copy.deepcopy(good)
    bad_tc2["task_columns"] = {"spec": " ", "prereq": "前置", "red": "红先测试", "status": "状态"}
    check("非法：task_columns 空列名报错", raises(lambda: validate(bad_tc2)))
    bad_tc3 = copy.deepcopy(good)
    bad_tc3["task_columns"] = {"spec": "规格锚", "prereq": "前置", "red": "失败先行测试", "status": "状态", "备": "x"}
    check("非法：task_columns 多余键报错（整键封闭闭集）", raises(lambda: validate(bad_tc3)))
    bad_tc4 = copy.deepcopy(good)
    bad_tc4["task_columns"] = {"spec": "锚", "prereq": "前置", "red": "锚", "status": "状态"}
    check("非法：task_columns 列名互撞报错（双角色同列静默失明）", raises(lambda: validate(bad_tc4)))
    bad_tc5 = copy.deepcopy(good)
    bad_tc5["task_columns"] = {"spec": "#", "prereq": "前置", "red": "红先测试", "status": "状态"}
    check("非法：task_columns 列名取 # 报错（首列识别标记）", raises(lambda: validate(bad_tc5)))
    # config-free 类型小节（默认词表通用中英）
    check("类型小节：需求标题→需求AC", conv.type_of_heading("需求") == "需求AC"
          and conv.type_of_heading("Requirements") == "需求AC")
    check("类型小节：参数标题→参数", conv.type_of_heading("参数") == "参数"
          and conv.type_of_heading("Parameters") == "参数")
    check("类型小节：任务标题→任务", conv.type_of_heading("任务") == "任务"
          and conv.type_of_heading("Tasks") == "任务")
    check("类型小节：普通标题→None", conv.type_of_heading("背景与动机") is None)
    check("类型小节：空标题→None", conv.type_of_heading(None) is None)
    no_ts = {k: v for k, v in copy.deepcopy(good).items() if k != "type_sections"}
    check("类型小节：缺配置→关闭（特性 off，如老语料靠 def_forms）", validate(no_ts).type_sections == [])
    bad_ts = copy.deepcopy(good); bad_ts["type_sections"] = [["需求AC"]]
    check("非法：type_sections 非二元对报错", raises(lambda: validate(bad_ts)))
    proj_edges = copy.deepcopy(good)
    proj_edges["doc_id_kinds"] = [["需求AC", r"R\d+-AC\d+", "项目 AC"]]
    proj_edges["edges"] = {"directed_pairs": [["deps", "usedby"]], "self_words": [], "section_ref_marker": "#"}
    pe = validate(proj_edges)
    check("项目 doc_id_kinds 覆盖", [k for k, _rx, _n in pe.doc_id_kinds] == ["需求AC"])
    check("项目 directed_pairs 覆盖", pe.directed_pairs == [("deps", "usedby")])
    check("项目 section_ref_marker 覆盖", pe.section_ref_marker == "#")
    bad_dik = copy.deepcopy(good); bad_dik["doc_id_kinds"] = [["k", "rx"]]
    check("非法：doc_id_kinds 非三元组报错", raises(lambda: validate(bad_dik)))
    bad_dp = copy.deepcopy(good); bad_dp["edges"] = {"directed_pairs": [["a", "b", "c"]]}
    check("非法：directed_pairs 非二元对报错", raises(lambda: validate(bad_dp)))
    bad_rx2 = copy.deepcopy(good); bad_rx2["doc_id_kinds"] = [["k", r"([", "n"]]
    check("非法：doc_id_kinds 坏正则报错", raises(lambda: validate(bad_rx2)))

    # 4.5 项目配置覆盖默认（不同 grammar / 命名空间）——验证引擎-约定分离（EG-17）
    proj_raw = copy.deepcopy(good)
    proj_raw["namespaces"]["prefix_namespaces"] = {"S2": "spec-two"}
    proj_raw["namespaces"]["kind_namespace"]["需求AC"] = "REQ_DOC"
    proj_raw["def_forms"]["需求AC"] = r"^-\s*\*\*(R\d+-AC\d+)\*\*"
    pconv = validate(proj_raw)
    # 前缀机制配置驱动：任何 cid 前缀进 prefix_namespaces 的 kind 走该路径（不点名某 kind）
    check("项目配置：cid 前缀 S2 映射生效（任意 kind）", pconv.namespace_for("某专有AC", "S2-AC1") == "spec-two")
    check("项目配置：需求AC 覆盖命名空间", pconv.namespace_for("需求AC", "R1-AC1") == "REQ_DOC")
    check("项目配置：需求AC 用项目 grammar", bool(pconv.def_forms["需求AC"].match("- **R7-AC1** x")))

    # 4.6 required_edges（DG-47）/ managed_values（DG-48）——additive 可选键，缺席即休眠
    check("required_edges 缺省→空（跨类型政策休眠）", conv.required_edges == [])
    check("uncovered_kind_exclusions 缺省→空", conv.uncovered_kind_exclusions == [])
    check("managed_values 缺省→空（drift 休眠）", conv.managed_values == [])
    re_raw = copy.deepcopy(good)
    re_raw["required_edges"] = [
        {"rule": "覆盖-验证", "src_kinds": ["需求AC", "Requirements"], "edge": "验证声明",
         "direction": "in", "dst_kinds": ["测试"], "severity": "gate"}]
    re_raw["managed_values"] = [
        {"name": "schema_version", "owner_kind": None, "occ": r"schema_version\s*=\s*\"([^\"]+)\"", "scope": None}]
    rc = validate(re_raw)
    check("required_edges 装载：规则显式点名 kind 写法", rc.required_edges[0]["src_kinds"] == ["需求AC", "Requirements"])
    check("required_edges 装载：direction/severity/edge 保真",
          rc.required_edges[0]["direction"] == "in" and rc.required_edges[0]["severity"] == "gate"
          and rc.required_edges[0]["edge"] == "验证声明")
    check("required_edges：dst_kinds 缺→None（不限靶）",
          validate({**copy.deepcopy(good), "required_edges": [
              {"rule": "r", "src_kinds": ["需求AC"], "edge": "任务声明", "direction": "in"}]}
                   ).required_edges[0]["dst_kinds"] is None)
    check("managed_values 装载：occ 编译 group(1)=值",
          rc.managed_values[0]["occ"].search('schema_version = "eg-2"').group(1) == "eg-2")
    check("required_edges/managed_values 入 hash（防不可见第二事实源）", rc.hash() != conv.hash())
    uke_raw = copy.deepcopy(good); uke_raw["uncovered_kind_exclusions"] = ["参数", "文档"]
    check("uncovered_kind_exclusions 装载保真",
          validate(uke_raw).uncovered_kind_exclusions == ["参数", "文档"])
    check("uncovered_kind_exclusions 入 hash", validate(uke_raw).hash() != conv.hash())
    bad_uke = copy.deepcopy(good); bad_uke["uncovered_kind_exclusions"] = [""]
    check("非法：uncovered_kind_exclusions 空元素报错", raises(lambda: validate(bad_uke)))
    bad_re1 = copy.deepcopy(good); bad_re1["required_edges"] = [{"rule": "r", "src_kinds": ["x"], "edge": "e"}]
    check("非法：required_edges 缺 direction 报错", raises(lambda: validate(bad_re1)))
    bad_re2 = copy.deepcopy(good); bad_re2["required_edges"] = [
        {"rule": "r", "src_kinds": ["x"], "edge": "e", "direction": "sideways"}]
    check("非法：required_edges direction 非 in|out 报错", raises(lambda: validate(bad_re2)))
    bad_re3 = copy.deepcopy(good); bad_re3["required_edges"] = [
        {"rule": "r", "src_kinds": [], "edge": "e", "direction": "in"}]
    check("非法：required_edges src_kinds 空报错", raises(lambda: validate(bad_re3)))
    bad_mv = copy.deepcopy(good); bad_mv["managed_values"] = [{"name": "x"}]
    check("非法：managed_values 缺 occ 报错", raises(lambda: validate(bad_mv)))
    bad_mv2 = copy.deepcopy(good); bad_mv2["managed_values"] = [{"name": "x", "occ": r"(["}]
    check("非法：managed_values occ 坏正则报错", raises(lambda: validate(bad_mv2)))

    # 4.7 检查 kind 域（DG-50）——additive 可选键，缺席即休眠
    check("revision_target_kinds 缺省→空（CHK-3 传导政策休眠）", conv.revision_target_kinds == [])
    check("cooccur_mapping_kinds 缺省→空（共现完备政策休眠）", conv.cooccur_mapping_kinds == [])
    kd_raw = copy.deepcopy(good)
    kd_raw["revision_target_kinds"] = ["需求AC", "契约AC", "审计AC"]
    kd_raw["cooccur_mapping_kinds"] = ["需求AC", "契约AC"]
    kc = validate(kd_raw)
    check("检查 kind 域装载保真", kc.revision_target_kinds == ["需求AC", "契约AC", "审计AC"]
          and kc.cooccur_mapping_kinds == ["需求AC", "契约AC"])
    check("检查 kind 域入 hash（防不可见第二事实源）", kc.hash() != conv.hash())
    bad_kd = copy.deepcopy(good); bad_kd["revision_target_kinds"] = "需求AC"
    check("非法：revision_target_kinds 非列表报错", raises(lambda: validate(bad_kd)))
    bad_kd2 = copy.deepcopy(good); bad_kd2["cooccur_mapping_kinds"] = [["需求AC"]]
    check("非法：cooccur_mapping_kinds 元素非字符串报错", raises(lambda: validate(bad_kd2)))

    # 4.8 archive_globs（DG-59/EG-30）——additive 可选键，缺席即休眠
    check("archive_globs：缺席→None（休眠）", validate(copy.deepcopy(good)).archive_globs is None)
    ag_proj = copy.deepcopy(good); ag_proj["archive_globs"] = ["Archive"]
    check("archive_globs：声明→解析", validate(ag_proj).archive_globs == ["Archive"])
    check("archive_globs 声明入 hash（DG-43）", validate(ag_proj).hash() != conv.hash())
    bad_ag1 = copy.deepcopy(good); bad_ag1["archive_globs"] = "Archive"
    check("非法：archive_globs 非列表报错", raises(lambda: validate(bad_ag1)))
    bad_ag2 = copy.deepcopy(good); bad_ag2["archive_globs"] = []
    check("非法：archive_globs 空列表报错", raises(lambda: validate(bad_ag2)))
    bad_ag3 = copy.deepcopy(good); bad_ag3["archive_globs"] = ["Archive", "  "]
    check("非法：archive_globs 空白元素报错", raises(lambda: validate(bad_ag3)))
    bad_ag4 = copy.deepcopy(good); bad_ag4["archive_globs"] = ["Archive/**"]
    check("非法：archive_globs 元素含 / 报错", raises(lambda: validate(bad_ag4)))

    # 5. 非法配置 → ConventionsError（缺键 / 坏正则 / 坏 version）
    bad_missing = copy.deepcopy(good); del bad_missing["harvest"]
    check("非法：缺必填键报错", raises(lambda: validate(bad_missing)))
    bad_re = copy.deepcopy(good); bad_re["def_forms"]["需求AC"] = r"(["
    check("非法：正则不编译报错", raises(lambda: validate(bad_re)))
    bad_ver = copy.deepcopy(good); bad_ver["version"] = "99"
    check("非法：version 不识别报错", raises(lambda: validate(bad_ver)))

    # 6. 发现契约优先级：explicit > 语料根/.docstar > 默认
    with tempfile.TemporaryDirectory() as tmp:
        corpus_root = Path(tmp) / "corpus"
        proj = corpus_root / DISCOVERY_SUBPATH
        proj.mkdir(parents=True)
        proj_cfg = copy.deepcopy(good); proj_cfg["namespaces"]["req_doc"] = "PROJ.md"
        (proj / CONFIG_FILENAME).write_text(
            json.dumps(proj_cfg, ensure_ascii=False), encoding="utf-8")
        c2 = load_conventions(corpus_root=str(corpus_root))
        check("发现：语料根 .docstar 覆盖默认", c2.req_doc == "PROJ.md")

        exp = Path(tmp) / "explicit"; exp.mkdir()
        exp_cfg = copy.deepcopy(good); exp_cfg["namespaces"]["req_doc"] = "EXPLICIT.md"
        (exp / CONFIG_FILENAME).write_text(
            json.dumps(exp_cfg, ensure_ascii=False), encoding="utf-8")
        c3 = load_conventions(corpus_root=str(corpus_root), explicit_dir=str(exp))
        check("发现：--conventions 显式最高", c3.req_doc == "EXPLICIT.md")
        check("发现：显式非法目录报错",
              raises(lambda: load_conventions(explicit_dir=str(Path(tmp) / "nope"))))
        check("发现：无配置回落默认",
              load_conventions(corpus_root=str(Path(tmp) / "empty")).source == "<default>")

    # 6b. _ancestor_config_dir + load 级走查（DG-55 走查支：探测函数原②告警复用，现为发现逻辑本体）
    with tempfile.TemporaryDirectory() as tmp:
        # 先 resolve 基址：避免 /tmp 符号链接（如 macOS /var→/private/var）导致「函数内部 resolve
        # 后路径」与「测试侧字面拼接路径」不逐字节相等的假失败（_ancestor_config_dir 内部亦 resolve）。
        base = Path(tmp).resolve()
        outer = base / "repo"
        mid = outer / "mid"
        leaf = mid / "corpus"
        leaf.mkdir(parents=True)
        (outer / ".git").mkdir()
        outer_cfg = outer / DISCOVERY_SUBPATH
        outer_cfg.mkdir(parents=True)
        (outer_cfg / CONFIG_FILENAME).write_text(
            json.dumps(good, ensure_ascii=False), encoding="utf-8")
        mid_raw = copy.deepcopy(good); mid_raw["namespaces"]["req_doc"] = "MID.md"
        mid_cfg = mid / DISCOVERY_SUBPATH
        mid_cfg.mkdir(parents=True)
        (mid_cfg / CONFIG_FILENAME).write_text(
            json.dumps(mid_raw, ensure_ascii=False), encoding="utf-8")
        check("_ancestor_config_dir：两层祖先都有配置→最近者胜",
              _ancestor_config_dir(leaf) == mid_cfg)
        check("load 级走查：两层祖先→最近层（mid）内容生效（req_doc 区分层）",
              load_conventions(corpus_root=str(leaf)).req_doc == "MID.md")
        check("load 级走查：来源=project（非 default）",
              load_conventions(corpus_root=str(leaf)).source_label() == "project")

        nogit_cfg = base / "nogit" / DISCOVERY_SUBPATH
        nogit_cfg.mkdir(parents=True)
        (nogit_cfg / CONFIG_FILENAME).write_text(
            json.dumps(good, ensure_ascii=False), encoding="utf-8")
        nogit_leaf = base / "nogit" / "sub" / "corpus"
        nogit_leaf.mkdir(parents=True)
        check("_ancestor_config_dir：无 .git 边界→None",
              _ancestor_config_dir(nogit_leaf) is None)

        self_git = base / "selfgit"
        (self_git / ".git").mkdir(parents=True)
        check("_ancestor_config_dir：语料根自带 .git→None",
              _ancestor_config_dir(self_git) is None)

        # .git 为文件判界（linked worktree 形；DG-55）：探测直调返回该层配置
        fg_outer = base / "filegit"
        fg_leaf = fg_outer / "sub" / "corpus"
        fg_leaf.mkdir(parents=True)
        (fg_outer / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        fg_cfg = fg_outer / DISCOVERY_SUBPATH
        fg_cfg.mkdir(parents=True)
        (fg_cfg / CONFIG_FILENAME).write_text(
            json.dumps(good, ensure_ascii=False), encoding="utf-8")
        check("_ancestor_config_dir：.git 为文件同判界（linked worktree）",
              _ancestor_config_dir(fg_leaf) == fg_cfg)

        # load 级 fail-closed：祖先唯一命中层配置非法→ConventionsError（不落默认、不续走更远层）
        bad_outer = base / "badcfg"
        bad_leaf = bad_outer / "sub" / "corpus"
        bad_leaf.mkdir(parents=True)
        (bad_outer / ".git").mkdir()
        bad_cfg_dir = bad_outer / DISCOVERY_SUBPATH
        bad_cfg_dir.mkdir(parents=True)
        bad_anc_raw = copy.deepcopy(good); del bad_anc_raw["harvest"]
        (bad_cfg_dir / CONFIG_FILENAME).write_text(
            json.dumps(bad_anc_raw, ensure_ascii=False), encoding="utf-8")
        check("load 级 fail-closed：祖先唯一命中层非法（缺必填键）→ConventionsError",
              raises(lambda: load_conventions(corpus_root=str(bad_leaf))))

    # 7. 可复现 hash（DG-43）：同内容同 hash、改配置 hash 变、source_label 稳定机器无关
    h1 = load_conventions().hash()
    h2 = validate(copy.deepcopy(good)).hash()
    check("hash：默认集同内容同 hash（确定性）", h1 == h2)
    mutated = copy.deepcopy(good); mutated["def_forms"]["需求AC"] = r"^-\s*\*\*(CHANGED-\d+)\*\*"
    check("hash：改配置则 hash 变", validate(mutated).hash() != h1)
    check("hash：键序无关（规范化排序）", validate({k: good[k] for k in reversed(list(good))}).hash() == h1)
    check("source_label：默认→default", load_conventions().source_label() == "default")
    check("canonical_bytes：确定性字节（可复跑）",
          load_conventions().canonical_bytes() == validate(copy.deepcopy(good)).canonical_bytes())

    print("\n  conventions 自验证：" + ("全 PASS" if ok else "有 FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
