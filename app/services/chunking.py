from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.parser import ParsedNode
from app.services.text import normalize_vietnamese, tokenize

MAX_CHUNK_CHARS = 1600
OVERLAP_CHARS = 180


@dataclass
class ChunkDraft:
    text: str
    context_text: str
    normalized_text: str
    legal_node: ParsedNode
    page_number: int | None
    bbox: list[float] | None
    token_count: int
    part_index: int


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if len(paragraphs) == 1:
        paragraphs = [part.strip() for part in re.split(r"(?<=[\.\;\:])\s+", text) if part.strip()]

    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 1 <= max_chars:
            current += "\n" + paragraph
        else:
            parts.append(current)
            current = paragraph
    if current:
        parts.append(current)

    if len(parts) == 1:
        # Hard split as a last resort.
        parts = [text[i : i + max_chars] for i in range(0, len(text), max_chars - OVERLAP_CHARS)]

    # Add a small overlap so a clause split across chunks remains retrievable.
    if len(parts) > 1:
        overlapped: list[str] = []
        previous = ""
        for part in parts:
            combined = (previous[-OVERLAP_CHARS:] + "\n" + part).strip() if previous else part
            overlapped.append(combined)
            previous = part
        return overlapped
    return parts


def build_chunks(nodes: list[ParsedNode], document_title: str) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for node in nodes:
        if node.level not in {"article", "clause", "point", "page"}:
            continue
        body = node.text.strip()
        if not body:
            continue
        heading = node.heading
        title = f"{heading} {node.title}".strip()
        context = f"{document_title}\n{node.path}\n{title}".strip()
        for part_index, part in enumerate(_split_text(body)):
            chunks.append(
                ChunkDraft(
                    text=part,
                    context_text=context,
                    normalized_text=normalize_vietnamese(context + "\n" + part),
                    legal_node=node,
                    page_number=node.page_start,
                    bbox=node.bbox,
                    token_count=len(tokenize(part)),
                    part_index=part_index,
                )
            )
    return chunks
