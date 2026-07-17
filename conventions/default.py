"""conventions 内置**通用**默认约定集——DG-33 波5 冻结的默认内容（去项目化，2026-07-15）。

这是一个**通用的规格/需求类语料起步集**（generic starter），不绑定任何具体项目：
识别通用 ID 形（`REQ-1` / `TASK-2` / 反引号参数）、通用定义/术语/表头形态。任何项目开箱即用，
需要自己的 ID 语法/文档名/命名空间锚时，在 `<语料根>/.docstar/conventions/conventions.json`
放一份同 schema 的配置即可覆盖（发现契约见 __init__.py）——「老项目声明自己约定」的活样例见
`fixtures/corpus/.docstar/conventions/`；本仓自身文档不带配置、走本默认集（自宿主即零配置语料的活样例）。

正则以「源字符串」存（与外部 JSON 配置同形，Conventions 构造时统一编译）。
"""

DEFAULT = {
    "version": "1",                       # 配置 schema 格式版本（loader 校验，DG-33）
    "namespaces": {
        # ID 前缀 → 命名空间（供有前缀分档的 kind，如同一语法多个来源文档时；通用默认无）
        "prefix_namespaces": {},
        # 有固定归属锚的 kind：裸 ID → 命名空间（值=项目自定的命名空间名，通用默认给占位）
        "kind_namespace": {
            "需求AC": "requirements",
        },
        # 各角色文档的标识（哪个文件是需求/参数/任务/映射文档；通用默认给通用文件名）
        "req_doc": "requirements.md",
        "param_registry": "parameters.md",
        "task_doc_stem": "tasks",
        "mapping_doc_stem": "mapping",
    },
    # kind → 行级定义正则源，group(1)=canonical_id（DG-25 形态识别）。通用默认只给普适三类；
    # 其它 kind 的语法由各项目在自己的 conventions 里补。
    "def_forms": {
        "需求AC": r"^-\s*\*\*(REQ-\d+)\*\*",
        "参数":   r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`[^|]*\|",
        "任务":   r"^\|\s*\*\*(TASK-\d+)\*\*",
    },
    # 专名就地标注两形（DG-27）；通用支持中英标记：`**X**（定义：…）` / `**X** (def: …)`
    "term_forms": {
        "inplace":  r"\*\*([^*]{2,40})\*\*\s*[（(]\s*(?:定义|def)\s*[:：]\s*([^）)]+)\s*[）)]",
        "glossary": r"^-?\s*\*\*([^*]{2,40})\*\*\s*[:：](.{4,})",
    },
    # 形态自识别表头（DG-25）；通用支持中英
    "form_headers": {
        "ledger":           r"^\|\s*(?:date|日期)\s*\|\s*(?:change|变更)\s*\|",
        "changelist":       r"^\|\s*(?:item|项)\s*\|\s*(?:location|落点|文档与落点)\b",
        "glossary_section": r"(?i)术语表|名词解释|词汇表|glossary",
    },
    # 未标注高频词提示的过滤（EG-5）；通用排除纯数字/日期/版本号
    "harvest": {
        "len_range": [2, 40],
        "exclude": [
            r"^\d+$",
            r"^\d{4}-\d{2}-\d{2}$",
            r"^v?\d+(?:\.\d+)+[a-z]?$",
        ],
    },
    # ---- 文档层建边约定（关系通配；以下皆可选，缺省即纯通配无向图） ----
    # doc_id_kinds：ID 提及索引形 [kind, regex_src, note]（供 id/ids 浏览与参数登记检查）。
    # 通用默认给普适两类；项目自定 ID 语法（如 R\d+-AC\d+）在自己 conventions 里补。
    "doc_id_kinds": [
        ["需求", r"(?<![A-Za-z0-9_])REQ-\d+(?![A-Za-z0-9_])", "通用需求编号 REQ-N"],
        ["任务", r"(?<![A-Za-z0-9_])TASK-\d+(?![A-Za-z0-9_])", "通用任务编号 TASK-N"],
    ],
    # edges：frontmatter 建边的方向/自引配置。
    #   directed_pairs  [上游键, 下游键] 对——赋方向(↑↓)+互查(单向边检查)；未列的键=通配无向边（键名=边类型）
    #   self_words      § 引用中指代本文的词（避免自引成边）；其指代词子集的自引断锚检查域
    #                   见 loader 可选键 self_ref_words（缺席回落默认七词，DG-51）
    #   section_ref_marker  节引用标记（默认 §；置空则不抽裸文本节引用，仅靠链接 #锚）
    "edges": {
        "directed_pairs": [
            ["上游", "下游"], ["upstream", "downstream"],
            ["parent", "child"], ["depends_on", "required_by"],
        ],
        "self_words": ["本文", "本节", "本表", "上文", "下文", "上表", "下表", "附录", "详见", "见"],
        "section_ref_marker": "§",
    },
    # type_sections：config-free 类型识别——认 agent 自然写的「类型小节」。
    # 小节标题命中某型词表 → 该节内的自然定义形（加粗名条目 `- **X** …`）成该 kind 实体，
    # 名字=加粗文本（有编号写编号、无编号那句话本身即标识）。节级作用域=抗「散文粗体海量误命中」
    # 洪水（复用术语表节同一证明）。是 def_forms 的 config-free 兜底：某行已被 def_forms 命中即不重促。
    # 每项：[kind, 标题词表正则源]。DG-38 起 kind 值开放（标题词=kind 本身、任意名，越出内置默认词表
    # 照原样处理，不报「非法 kind」）；本默认集只映射到内置默认 kind。留空/缺省→特性关闭（如老语料靠 def_forms）。
    "type_sections": [
        ["需求AC", r"(?i)需求|验收标准|requirements?|acceptance criteria"],
        ["参数",   r"(?i)参数|parameters?"],
        ["任务",   r"(?i)任务|待办|tasks?|to-?dos?"],
    ],
    # ---- 实体层抽取约定（DG-38 波12-块1；只含通用值，项目专有形在各自 conventions 里补） ----
    # id_occ_kinds：哪些 doc_id_kinds 的 ID 提及也促成内容层实体（id 提及 kind → 实体 kind）。
    "id_occ_kinds": {"需求AC": "需求AC", "任务": "任务"},
    # cooccur_kinds：参与共现索引的实体 kind（EG-2-AC9 限 ID 形实体）。
    "cooccur_kinds": ["需求AC", "参数", "任务"],
    # ac_prefix_kinds：单元格内裸 AC id 首字符 → 实体 kind（映射/任务 spec/底账等表格通道）。
    "ac_prefix_kinds": {"R": "需求AC"},
    # option_rows（表格行形自定义实体）/review_item（登记源 ID 形实体）/prov_form（记述引用句式）：
    # 通用默认不含（缺席即休眠，沿 type_sections 先例）；项目需要时在自己的 conventions 里声明。
    # 别名（可选；默认空）
    "aliases": {},
}
