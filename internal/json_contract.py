"""DocStar eg-3 public JSON contract.

The engine keeps its established internal vocabulary so extraction and checks do not
depend on a display language.  Every JSON boundary passes through ``to_public``;
tests that exercise internal semantics may use ``to_internal``.
"""

from collections.abc import Mapping


KEYS = {
    "上游": "upstream",
    "下游": "downstream",
    "关联": "frontmatter_relations",
    "被引用frontmatter": "frontmatter_references_in",
    "键": "field",
    "方向": "direction",
    "正文引出": "body_links_out",
    "被正文引用": "body_links_in",
    "引出节引用": "section_references_out",
    "被节引用": "section_references_in",
    "节标题数": "section_count",
    "ID提及TOP": "top_id_mentions",
    "目标锚点": "target_anchor",
    "引用处": "references",
    "性质": "nature",
    "状态": "status",
    "类型": "document_type",
    "原文": "source_text",
    "规则": "rule",
    "诊断型": "diagnostic_type",
    "缺": "missing",
    "来源": "diagnostic_source",
    "锚": "anchor",
    "边": "edge",
    "从": "from",
    "到": "to",
    "深度": "depth",
    "首现": "first_seen",
    "r版本": "revision_version",
    "日期": "date",
    "落点原文": "target_text",
    "期望": "expected",
    "源文件": "source_file",
    "行": "source_line",
    "目标": "target",
    "摘要": "digest",
    "定义锚": "definition_anchor",
    "原始锚": "original_anchor",
    "裁定引用集": "decision_references",
    "展开": "expanded",
    "说明": "explanation",
    "实体_重定义": "entity_redefinitions",
    "实体_无定义块": "entities_without_definition",
    "实体_修订行未解析": "unresolved_revision_rows",
    "未分类文档": "unclassified_documents",
    "实体_schema_孤儿consumer": "orphan_schema_consumers",
    "执行日志诊断": "execution_log_diagnostics",
    "baseline_来源": "baseline_source",
    "引入实体": "added_entities",
    "删除实体": "removed_entities",
    "引入边": "added_edges",
    "删除边": "removed_edges",
    "引入缺陷": "introduced_findings",
    "进图缺失": "graph_omissions",
    "局限说明": "limitations",
    "边类型": "edge_type",
    "断因": "break_reason",
    "去重稳定排序": "deterministic_deduplication",
    "去重键": "deduplication_key",
    "排序键": "sort_key",
    "已应用": "applied",
    "原因": "omission_reason",
    "指针": "pointer",
    "关系": "relations",
    "预算转指针": "budget_pointer",
    "fm_断链": "frontmatter_broken_links",
    "fm_无链接条目": "frontmatter_unlinked_entries",
    "fm_有意非链接条目": "frontmatter_declared_nonlinks",
    "单向边_我列它为下游_它未列我为上游": "downstream_missing_upstream_reciprocal",
    "单向边_我列它为上游_它未列我为下游": "upstream_missing_downstream_reciprocal",
    "正文死链": "body_broken_links",
    "未登记参数_出现≥3次": "unregistered_parameters_3plus",
    "节引用前缀未解析TOP": "top_unresolved_section_prefixes",
    "节引用断锚": "broken_section_anchors",
    "缺frontmatter": "missing_frontmatter",
    "专名定义断锚": "broken_term_definition_anchors",
    "CHK-2覆盖缺口": "coverage_gaps",
    "CHK-2映射缺口": "mapping_gaps",
    "CHK-3传导断裂": "propagation_breaks",
    "CHK-环检测": "prerequisite_cycles",
    "环": "cycle",
    "节点数": "node_count",
    "共现完备性": "cooccurrence_completeness",
    "共现": "cooccurrences",
    "缺必需边": "required_edge_gaps",
    "未覆盖kind": "uncovered_kinds",
    "长度越界": "length_out_of_range",
    "结构化token": "structured_tokens",
    "文档名": "document_names",
    "已标注专名": "annotated_terms",
    "缺声明原因": "missing_declaration_reason",
    "证据": "evidence",
    "定义实体数": "defined_entity_count",
    "底账表形态": "ledger_shape",
    "被规范文档引用": "referenced_by_normative_document",
    "引用来源规范文档": "normative_reference_sources",
    "标题": "heading",
    "值": "value",
    "完成判据": "completion_criteria",
    "scope内文档数": "documents_in_scope",
    "未覆盖": "uncovered",
    "全覆盖": "fully_covered",
    "scope内": "in_scope",
    "scope外": "out_of_scope",
    "形态": "form",
}

FRONTMATTER_KEYS = {
    "目标": "purpose",
    "上游": "upstream",
    "下游": "downstream",
    "状态": "status",
    "类型": "type",
    "性质": "nature",
    "语言": "locale",
}

TOKENS = {
    "规范": "normative",
    "记述": "descriptive",
    "需求AC": "requirement-ac",
    "需求": "requirement",
    "参数": "parameter",
    "任务": "task",
    "测试": "test",
    "专名": "term",
    "文档": "document",
    "节条目": "section-item",
    "执行日志": "execution-log",
    "最新事件": "latest-event",
    "契约AC": "contract-ac",
    "审计AC": "audit-ac",
    "评审项": "review-item",
    "治理期权": "governance-option",
    "编号项": "numbered-item",
    "版本": "version",
    "决议": "decision",
    "里程碑": "milestone",
    "测试名": "test-name",
    "全局": "global",
    "路径": "path",
    "修订落账": "revision-record",
    "修订声明": "revision-declaration",
    "任务声明": "task-declaration",
    "验证声明": "verification-declaration",
    "任务测试声明": "task-test-declaration",
    "映射": "mapping",
    "阅读依赖": "reading-dependency",
    "前置依赖": "prerequisite-dependency",
    "共现索引": "cooccurrence-index",
    "高": "high",
    "确定": "deterministic",
    "中": "medium",
    "入": "in",
    "出": "out",
    "草稿": "draft",
    "已定稿-待批": "pending-approval",
    "已批准": "approved",
    "已关账": "closed",
    "未立项": "not-started",
    "立项": "initiated",
    "进行中": "in-progress",
    "关账": "closed",
    "已合并": "merged",
    "待开工": "not-started",
    "在飞": "in-progress",
    "断锚": "broken-anchor",
    "歧义引用": "ambiguous-reference",
    "无定义块": "missing-definition",
    "未分类跳过": "skipped-unclassified",
    "任务表spec锚": "task-table-spec-anchor",
    "任务表红先列": "task-table-failing-test",
    "任务表前置列": "task-table-prerequisite",
    "定义块共现": "definition-block-cooccurrence",
    "映射表行": "mapping-table-row",
    "底账表行": "ledger-table-row",
    "修改清单表行": "change-list-row",
    "靶契约AC无定义块": "target-contract-ac-missing-definition",
    "CHK-2覆盖缺口": "coverage_gaps",
    "CHK-2映射缺口": "mapping_gaps",
    "CHK-3传导断裂": "propagation_breaks",
    "CHK-环检测": "prerequisite_cycles",
    "共现完备性": "cooccurrence_completeness",
}

_INTERNAL_KEYS = {value: key for key, value in KEYS.items()}
_INTERNAL_FRONTMATTER_KEYS = {value: key for key, value in FRONTMATTER_KEYS.items()}
_INTERNAL_TOKENS = {value: key for key, value in TOKENS.items()}
_INTERNAL_TOKENS["closed"] = "已关账"
_INTERNAL_TOKENS["not-started"] = "待开工"
_INTERNAL_TOKENS["in-progress"] = "在飞"


def to_internal_key(value):
    """Resolve a public contract key accepted by CLI selectors such as --gate."""
    return _INTERNAL_KEYS.get(value, value)


def to_public_key(value):
    """Return the canonical public spelling for an internal contract key."""
    return KEYS.get(value, value)


def to_internal_token(value):
    """Resolve a public built-in token accepted by CLI selectors such as --kind."""
    return _INTERNAL_TOKENS.get(value, value)


def frontmatter_candidates(value):
    """Return exact and alias field names in deterministic lookup order."""
    public = FRONTMATTER_KEYS.get(value, value)
    legacy = _INTERNAL_FRONTMATTER_KEYS.get(value, _INTERNAL_FRONTMATTER_KEYS.get(public))
    return tuple(dict.fromkeys(x for x in (value, public, legacy) if x))


def _mapped_key(key, frontmatter=False):
    if not isinstance(key, str):
        return key
    if frontmatter:
        return FRONTMATTER_KEYS.get(key, KEYS.get(key, key))
    return KEYS.get(key, key)


def to_public(value, *, _frontmatter=False, _edge_groups=False):
    """Return an eg-3 JSON-safe value with canonical English keys and tokens."""
    if isinstance(value, Mapping):
        if value and all(
            isinstance(item, Mapping) and {"unique", "total", "note", "ids"} <= set(item)
            for item in value.values()
        ):
            return {"kinds": [
                {"kind": TOKENS.get(kind, kind), **to_public(item)}
                for kind, item in value.items()
            ]}
        result = {}
        frontmatter_row = "doc" in value and "has_fm" in value
        for key, item in value.items():
            key_is_frontmatter = _frontmatter or (frontmatter_row and key not in ("doc", "has_fm"))
            public_key = TOKENS.get(key, key) if _edge_groups else _mapped_key(key, key_is_frontmatter)
            if public_key in result:
                raise ValueError(f"eg-3 key collision: {key!r} -> {public_key!r}")
            child_frontmatter = public_key == "meta"
            result[public_key] = to_public(
                item,
                _frontmatter=child_frontmatter,
                _edge_groups=public_key == "edges",
            )
        return result
    if isinstance(value, (list, tuple)):
        return [to_public(item) for item in value]
    if isinstance(value, str):
        return TOKENS.get(value, value)
    return value


def to_internal(value, *, _frontmatter=False, _edge_groups=False):
    """Decode eg-3 output for legacy internal semantic tests."""
    if isinstance(value, Mapping):
        if set(value) == {"kinds"} and isinstance(value.get("kinds"), list) and all(
            isinstance(item, Mapping) and "kind" in item for item in value["kinds"]
        ):
            result = {}
            for item in value["kinds"]:
                kind = _INTERNAL_TOKENS.get(item["kind"], item["kind"])
                result[kind] = to_internal({k: v for k, v in item.items() if k != "kind"})
            return result
        result = {}
        frontmatter_row = "doc" in value and "has_fm" in value
        for key, item in value.items():
            key_is_frontmatter = _frontmatter or (frontmatter_row and key not in ("doc", "has_fm"))
            if _edge_groups:
                internal_key = _INTERNAL_TOKENS.get(key, key)
            elif key_is_frontmatter:
                internal_key = _INTERNAL_FRONTMATTER_KEYS.get(key, _INTERNAL_KEYS.get(key, key))
            else:
                internal_key = _INTERNAL_KEYS.get(key, key)
            child_frontmatter = key == "meta"
            result[internal_key] = to_internal(
                item,
                _frontmatter=child_frontmatter,
                _edge_groups=key == "edges",
            )
        return result
    if isinstance(value, list):
        return [to_internal(item) for item in value]
    if isinstance(value, str):
        return _INTERNAL_TOKENS.get(value, value)
    return value
