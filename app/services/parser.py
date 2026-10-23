from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.text import normalize_vietnamese

LEVEL_ORDER = {
    "part": 1,
    "chapter": 2,
    "section": 3,
    "article": 4,
    "clause": 5,
    "point": 6,
    "page": 7,
}

LEVEL_LABEL = {
    "part": "Phần",
    "chapter": "Chương",
    "section": "Mục",
    "article": "Điều",
    "clause": "Khoản",
    "point": "Điểm",
    "page": "Trang",
}

_PART_RE = re.compile(r"^(PHẦN|Phần)\s+([IVXLCDM]+|\d+)(?=[\.:\s]|$)\s*[\.:]?\s*(.*)$")
_CHAPTER_RE = re.compile(r"^(CHƯƠNG|Chương)\s+([IVXLCDM]+|\d+)(?=[\.:\s]|$)\s*[\.:]?\s*(.*)$")
_SECTION_RE = re.compile(r"^(MỤC|Mục)\s+(\d+|[IVXLCDM]+)(?=[\.:\s]|$)\s*[\.:]?\s*(.*)$")
_ARTICLE_RE = re.compile(r"^(ĐIỀU|Điều)\s+(\d+[a-zA-Z]?)(?=[\.:\s]|$)\s*[\.:]?\s*(.*)$")
_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]\s*(.+)$")
_POINT_RE = re.compile(r"^([a-zđ])[\)\.]\s*(.+)$")
_TOC_LINE_RE = re.compile(r"\.{3,}\s*\d+\s*$")
_PAGE_NO_RE = re.compile(r"^\d{1,4}$")


@dataclass
class SourceLine:
    text: str
    page_number: int
    bbox: list[float] | None = None
    font_size: float = 0.0
    bold: bool = False


@dataclass
class ParsedNode:
    level: str
    number: str
    title: str
    text: str = ""
    page_start: int = 1
    page_end: int = 1
    bbox: list[float] | None = None
    confidence: float = 0.9
    extraction_method: str = "rule"
    parent: ParsedNode | None = None
    children: list[ParsedNode] = field(default_factory=list)
    order_index: int = 0

    @property
    def path(self) -> str:
        parts: list[str] = []
        node: ParsedNode | None = self
        while node is not None:
            if node.level in LEVEL_ORDER:
                parts.append(f"{LEVEL_LABEL[node.level]} {node.number}".strip())
            node = node.parent
        return " > ".join(reversed(parts))

    @property
    def heading(self) -> str:
        label = LEVEL_LABEL.get(self.level, self.level)
        return f"{label} {self.number}".strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _union_bbox(a: list[float] | None, b: list[float] | None) -> list[float] | None:
    if not a:
        return b
    if not b:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _is_toc_page(lines: list[SourceLine]) -> bool:
    if any("muc luc" in normalize_vietnamese(line.text) for line in lines if line.text.strip()):
        return True
    dotted = sum(1 for line in lines if _TOC_LINE_RE.search(line.text))
    return dotted >= 3


def _match_heading(text: str) -> tuple[str, str, str, float] | None:
    for level, pattern in (
        ("part", _PART_RE),
        ("chapter", _CHAPTER_RE),
        ("section", _SECTION_RE),
        ("article", _ARTICLE_RE),
    ):
        match = pattern.match(text)
        if match:
            return level, match.group(2), _clean(match.group(3)), 0.95
    return None


def _title_from_next_line(lines: list[SourceLine], index: int) -> tuple[str, int] | None:
    if index + 1 >= len(lines):
        return None
    candidate = _clean(lines[index + 1].text)
    if not candidate or _PAGE_NO_RE.match(candidate) or _match_heading(candidate):
        return None
    if _CLAUSE_RE.match(candidate) or _POINT_RE.match(candidate):
        return None
    # Don't consume a long paragraph as a heading.
    if len(candidate) > 220:
        return None
    return candidate, index + 1


def parse_legal_structure(
    pages: list[tuple[int, list[SourceLine]]],
    document_type: str | None = None,
) -> list[ParsedNode]:
    """Extract a Vietnamese legal hierarchy from page lines.

    The parser is intentionally deterministic. It handles the common forms:
    Phần, Chương, Mục, Điều, Khoản, Điểm. Ambiguous lines are left as plain
    text rather than forced into the tree. An LLM fallback can be added later
    for low-confidence nodes, but it should never be the primary extractor.
    """
    del document_type  # reserved for type-specific rules
    nodes: list[ParsedNode] = []
    stack: list[ParsedNode] = []
    current: ParsedNode | None = None

    for page_number, page_lines in pages:
        if _is_toc_page(page_lines):
            continue
        lines = page_lines
        index = 0
        while index < len(lines):
            line = lines[index]
            text = _clean(line.text)
            index += 1
            if not text or _PAGE_NO_RE.match(text) or _TOC_LINE_RE.search(text):
                continue

            heading = _match_heading(text)
            if heading:
                level, number, title, confidence = heading
                if not title:
                    next_title = _title_from_next_line(lines, index - 1)
                    if next_title:
                        title, consumed_index = next_title
                        index = consumed_index + 1

                node = ParsedNode(
                    level=level,
                    number=number,
                    title=title,
                    page_start=page_number,
                    page_end=page_number,
                    bbox=line.bbox,
                    confidence=confidence,
                )
                order = LEVEL_ORDER[level]
                while stack and LEVEL_ORDER[stack[-1].level] >= order:
                    stack.pop()
                if stack:
                    node.parent = stack[-1]
                    stack[-1].children.append(node)
                nodes.append(node)
                stack.append(node)
                current = node
                continue

            clause = _CLAUSE_RE.match(text)
            if clause and any(item.level == "article" for item in stack):
                number, body = clause.group(1), _clean(clause.group(2))
                node = ParsedNode(
                    level="clause",
                    number=number,
                    title="",
                    text=body,
                    page_start=page_number,
                    page_end=page_number,
                    bbox=line.bbox,
                    confidence=0.78,
                )
                _attach(stack, node)
                nodes.append(node)
                current = node
                continue

            point = _POINT_RE.match(text)
            if point and any(item.level in {"article", "clause"} for item in stack):
                number, body = point.group(1), _clean(point.group(2))
                node = ParsedNode(
                    level="point",
                    number=number,
                    title="",
                    text=body,
                    page_start=page_number,
                    page_end=page_number,
                    bbox=line.bbox,
                    confidence=0.68,
                )
                _attach(stack, node)
                nodes.append(node)
                current = node
                continue

            if current is not None:
                current.text = (current.text + "\n" + text).strip()
                current.page_end = page_number
                current.bbox = _union_bbox(current.bbox, line.bbox)
                for ancestor in stack:
                    if ancestor is not current:
                        ancestor.page_end = max(ancestor.page_end, page_number)

    for order, node in enumerate(nodes):
        node.order_index = order
    return nodes


def _attach(stack: list[ParsedNode], node: ParsedNode) -> None:
    order = LEVEL_ORDER[node.level]
    while stack and LEVEL_ORDER[stack[-1].level] >= order:
        stack.pop()
    if stack:
        node.parent = stack[-1]
        stack[-1].children.append(node)
    stack.append(node)
