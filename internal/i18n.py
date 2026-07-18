"""Small, dependency-free display-language switch for DocStar's human output."""

import json

import json_contract

SUPPORTED_LANGUAGES = ("en", "zh-CN")
_language = "zh-CN"


def set_language(value):
    global _language
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError(value)
    _language = value


def language():
    return _language


def text(en, zh_cn):
    return en if _language == "en" else zh_cn


def render_public(value):
    """Render canonical eg-3 data as compact, English, human-readable text."""
    value = json_contract.to_public(value)
    lines = []

    def walk(item, indent=0, label=None):
        pad = "  " * indent
        prefix = f"{label}:" if label is not None else ""
        if isinstance(item, dict):
            if label is not None:
                lines.append(f"{pad}{prefix}")
                indent += 1
                pad = "  " * indent
            if not item:
                lines.append(f"{pad}{{}}")
            for key, child in item.items():
                walk(child, indent, str(key))
            return
        if isinstance(item, list):
            if not item:
                lines.append(f"{pad}{prefix} []".rstrip())
                return
            if all(not isinstance(child, (dict, list)) for child in item):
                body = ", ".join(json.dumps(child, ensure_ascii=False) for child in item)
                lines.append(f"{pad}{prefix} [{body}]".rstrip())
                return
            if label is not None:
                lines.append(f"{pad}{prefix}")
                indent += 1
            for child in item:
                bullet_pad = "  " * indent
                if isinstance(child, dict):
                    lines.append(f"{bullet_pad}-")
                    walk(child, indent + 1)
                else:
                    lines.append(f"{bullet_pad}- {json.dumps(child, ensure_ascii=False)}")
            return
        scalar = json.dumps(item, ensure_ascii=False) if item is not None else "null"
        lines.append(f"{pad}{prefix} {scalar}".rstrip())

    walk(value)
    return "\n".join(lines)


_HTML_EN = {
    '<html lang="zh">': '<html lang="en">',
    "DocStar 文档图谱": "DocStar document graph",
    "实体图谱查询": "Entity graph query",
    "实体图谱": "Entity graph",
    "搜索文档名（Enter 定位）": "Search document name (Enter to locate)",
    "搜索：名称 / 标识 / 主键三元组（Enter 定位首个）":
        "Search name / ID / key triple (Enter to locate first)",
    "双击画布同效": "Same as double-clicking the canvas",
    "适配视野": "Fit view",
    "表格视图": "Table view",
    "图视图": "Graph view",
    "正文链接": "Body links",
    "上下游": "Dependencies",
    "§引用": "Section references",
    "清空选择与搜索": "Clear selection and search",
    "清空": "Clear",
    "切换明暗": "Toggle theme",
    "明暗": "Theme",
    "实体类别": "Entity kinds",
    "关系类型": "Relation types",
    "全选": "Select all",
    "判定概览": "Check overview",
    "项检查，": " checks, ",
    "项检查": " checks",
    "项非干净通过": " not clean",
    "判定不可用": "Checks unavailable",
    "无判定数据（该特性为可选）。": "No check data (this feature is optional).",
    "命中": "Findings",
    "阻断": "Blocked",
    "污染源": "Tainted by",
    "污染": "Tainted",
    "个匹配": " matches",
    "个实体": " entities",
    "显示前": "showing first ",
    "可搜索/按类别收窄": "search or filter by kind",
    "无匹配实体": "No matching entities",
    "无定义块": "No definition block",
    "类别": "Kind",
    "命名空间": "Namespace",
    "性质": "Nature",
    "状态": "Status",
    "关系度": "Degree",
    "已被关系类型过滤隐藏": "Hidden by relation-type filters",
    "定义位置": "Definition location",
    "另见定义块": "Also defined at",
    "主体正文": "Definition text",
    "本实体指向谁": "targets of this entity",
    "谁指向本实体": "sources pointing to this entity",
    "左侧搜索或点选一个实体查看详情：类别、命名空间、性质、定义位置、主体正文，以及按关系类型分组的全部出入边（可点邻居跳转）。选中后上方显示其一跳邻域图。":
        "Search or select an entity to inspect its kind, namespace, nature, definition, text, and grouped incoming and outgoing relations. The one-hop graph appears above.",
    "用顶部搜索框按 <b>名称 / 标识 / 主键三元组</b> 定位；用左侧 <b>类别</b>、<b>关系类型</b> chips 过滤。":
        "Use the top search box for <b>name / ID / key triple</b>; filter by <b>kind</b> or <b>relation type</b> on the left.",
    "按类别分布": "Distribution by kind",
    "抽取报告": "Extraction reports",
    "未分类文档": "Unclassified documents",
    "分类完备：": "Classification complete: ",
    "分类完备": "Classification complete",
    "一跳邻域：": "One-hop neighborhood: ",
    "一跳邻域": "One-hop neighborhood",
    "邻居": "neighbors",
    "按关系度截取": "limited by degree",
    "点节点跳转": "click a node to navigate",
    "滚轮缩放": "wheel to zoom",
    "拖拽平移": "drag to pan",
    "关闭": "Close",
    "目标: ": "Purpose: ",
    "状态: ": "Status: ",
    "入边": "Incoming",
    "出边": "Outgoing",
    "连接强度": "Degree",
    "（入 ": " (incoming ",
    " / 出 ": " / outgoing ",
    ">入<": ">Incoming<",
    ">出<": ">Outgoing<",
    "谁指向它": "sources pointing to it",
    "它指向谁": "its targets",
    "命令": "Command",
    "文档": "Document",
    "分组": "Group",
    "强度": "Degree",
    "有frontmatter": "has frontmatter",
    "虚环=Archive": "Dashed ring=Archive",
    "箭头=上游→下游": "arrow=upstream→downstream",
    "粗细=次数": "width=count",
    "§节引用": "Section references",
    "篇": " docs",
    "上下游边": "dependency edges",
    "链接边": "link edges",
    "链接": "Links",
    "§引用边": "section-reference edges",
    "生成于": "generated",
    "实体": " entities",
    "关系": " relations",
    " 类别 ·": " kinds ·",
    " 次": " refs",
    '"有"': '"yes"',
    "graph: ${_dropped} 条边端点不在图内已跳过（数据面应零此类，DG-61）":
        "graph: ${_dropped} edges with missing endpoints were skipped (expected zero; DG-61)",
    "是": "yes",
    "否": "no",
    "（无）": "(none)",
    "）·": ") ·",
    "（": " (",
    "）": ")",
    "、": ", ",
}


def localize_html(template):
    """Localize static HTML/JS interface strings without duplicating templates."""
    if _language != "en":
        return template
    for source in sorted(_HTML_EN, key=len, reverse=True):
        template = template.replace(source, _HTML_EN[source])
    return template


def help_text(zh_cn):
    if _language == "zh-CN":
        return zh_cn
    return """DocStar — a read-only graph and structural checker for Markdown corpora.

Usage:
  python3 docstar.py graph
  python3 docstar.py doc <name>
  python3 docstar.py id <ID|doc §N>
  python3 docstar.py ids [--kind K]
  python3 docstar.py docs [glob] [--fields A,B]
  python3 docstar.py check [--gate key1,key2]
  python3 docstar.py dump [--kind K]
  python3 docstar.py trace <entity>
  python3 docstar.py brief <task> [--mode execute|impact|review] [--budget N]
  python3 docstar.py verify [--baseline REV] [--migrate]
  python3 docstar.py classify --pending|--validate
  python3 docstar.py harvest [--baseline FILE]
  python3 docstar.py drift
  python3 docstar.py html [output]
  python3 docstar.py html-entity [output]

Common options:
  --json                 Emit the stable eg-3 English JSON contract.
  --lang en|zh-CN        Select human-readable CLI and HTML labels only.
  --corpus DIR           Set the Markdown corpus root (default: current directory).
  --conventions DIR      Use an explicit conventions directory.
  --preset NAME          Use a bundled preset, for example gmgn-v1.
  --include-archived     Include content excluded by archive_globs.

Relative paths are resolved from the caller's current directory. Unknown flags,
languages, presets, or convention keys fail closed with exit code 2.
"""
