from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import fts_search
from app.models import Chunk, Document, LegalNode
from app.schemas import SearchResult
from app.services.embeddings import get_embedding_provider
from app.services.text import normalize_vietnamese, snippet

settings = get_settings()

_ARTICLE_RE = re.compile(r"(?:điều|dieu)\s+(\d+[a-zA-Z]?)", re.IGNORECASE)
_INDEX_LOCK = threading.Lock()
# Embeddings from different providers/models can coexist while a corpus is
# being reindexed. Group them by dimension so a dimension change never crashes
# retrieval; the group matching the query provider is used.
_INDEX_GROUPS: dict[int, tuple[list[str], list[str], np.ndarray]] = {}
_INDEX_SIGNATURE: tuple[int, str] | None = None


def invalidate_vector_index() -> None:
    global _INDEX_SIGNATURE
    with _INDEX_LOCK:
        _INDEX_SIGNATURE = None


def _load_vector_index(db: Session) -> dict[int, tuple[list[str], list[str], np.ndarray]]:
    global _INDEX_GROUPS, _INDEX_SIGNATURE

    count = db.query(func.count(Chunk.id)).filter(Chunk.embedding.isnot(None)).scalar() or 0
    latest = db.query(func.max(Chunk.created_at)).filter(Chunk.embedding.isnot(None)).scalar()
    signature = (int(count), str(latest))
    with _INDEX_LOCK:
        if _INDEX_SIGNATURE == signature:
            return _INDEX_GROUPS

    rows = (
        db.query(Chunk.id, Chunk.document_id, Chunk.embedding)
        .filter(Chunk.embedding.isnot(None))
        .all()
    )
    grouped: dict[int, tuple[list[str], list[str], list[list[float]]]] = {}
    for chunk_id, document_id, embedding in rows:
        if not embedding:
            continue
        entry = grouped.setdefault(len(embedding), ([], [], []))
        entry[0].append(chunk_id)
        entry[1].append(document_id)
        entry[2].append(embedding)

    groups: dict[int, tuple[list[str], list[str], np.ndarray]] = {}
    for dimension, (ids, doc_ids, vectors) in grouped.items():
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        groups[dimension] = (ids, doc_ids, matrix / norms)

    with _INDEX_LOCK:
        _INDEX_GROUPS = groups
        _INDEX_SIGNATURE = signature
    return groups


def _vector_candidates(
    db: Session, query: str, limit: int = 80, document_ids: list[str] | None = None
) -> list[str]:
    provider = get_embedding_provider()
    query_vector = np.asarray(provider.embed_query(query), dtype=np.float32)
    norm = float(np.linalg.norm(query_vector))
    if norm == 0:
        return []
    query_vector = query_vector / norm
    group = _load_vector_index(db).get(len(query_vector))
    if group is None:
        return []
    ids, doc_ids, matrix = group
    if not ids:
        return []
    scores = matrix @ query_vector
    if document_ids:
        allowed = set(document_ids)
        mask = np.array([doc_id in allowed for doc_id in doc_ids], dtype=bool)
        scores = np.where(mask, scores, -1.0)
    top_indices = np.argsort(-scores)[:limit]
    return [ids[int(index)] for index in top_indices if scores[int(index)] > 0]


def _lexical_candidates(
    db: Session, query: str, limit: int = 80, document_ids: list[str] | None = None
) -> list[str]:
    normalized = normalize_vietnamese(query)
    if not normalized:
        return []
    if settings.database_url.startswith("sqlite"):
        rows = fts_search(db, normalized, limit=limit * 2)
        ids = [chunk_id for chunk_id, _score in rows]
        if document_ids and ids:
            allowed = set(document_ids)
            found = {
                row[0]
                for row in db.query(Chunk.id)
                .filter(Chunk.id.in_(ids), Chunk.document_id.in_(allowed))
                .all()
            }
            ids = [chunk_id for chunk_id in ids if chunk_id in found]
        return ids[:limit]

    tokens = [token for token in normalized.split() if len(token) > 1][:12] or [normalized]
    stmt = db.query(Chunk.id).filter(
        or_(*(Chunk.normalized_text.ilike(f"%{token}%") for token in tokens))
    )
    if document_ids:
        stmt = stmt.filter(Chunk.document_id.in_(document_ids))
    return [row[0] for row in stmt.limit(limit).all()]


def _article_candidates(
    db: Session, query: str, document_ids: list[str] | None = None, limit: int = 30
) -> list[str]:
    match = _ARTICLE_RE.search(query) or _ARTICLE_RE.search(normalize_vietnamese(query))
    if not match:
        return []
    number = match.group(1)
    article_ids = [
        row[0]
        for row in db.query(LegalNode.id)
        .filter(LegalNode.level == "article", LegalNode.number == number)
        .all()
    ]
    if not article_ids:
        return []
    child_ids = [
        row[0]
        for row in db.query(LegalNode.id).filter(LegalNode.parent_id.in_(article_ids)).all()
    ]
    node_ids = article_ids + child_ids
    stmt = db.query(Chunk.id).filter(Chunk.legal_node_id.in_(node_ids))
    if document_ids:
        stmt = stmt.filter(Chunk.document_id.in_(document_ids))
    return [row[0] for row in stmt.limit(limit).all()]


@dataclass
class _Candidate:
    chunk: Chunk
    document: Document
    node: LegalNode | None
    score: float


def search_chunks(
    db: Session,
    query: str,
    *,
    top_k: int = 10,
    document_ids: list[str] | None = None,
    include_text: bool = True,
) -> tuple[list[SearchResult], int]:
    started = time.perf_counter()
    query = query.strip()
    if not query:
        return [], 0

    lexical_ids = _lexical_candidates(db, query, document_ids=document_ids)
    vector_ids = _vector_candidates(db, query, document_ids=document_ids)
    exact_ids = _article_candidates(db, query, document_ids=document_ids)

    fused: dict[str, float] = {}
    for ranked_list in (lexical_ids, vector_ids):
        for rank, chunk_id in enumerate(ranked_list):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60.0 + rank + 1.0)
    for chunk_id in exact_ids:
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 0.08

    if not fused:
        normalized = normalize_vietnamese(query)
        stmt = db.query(Chunk.id).filter(Chunk.normalized_text.ilike(f"%{normalized}%"))
        if document_ids:
            stmt = stmt.filter(Chunk.document_id.in_(document_ids))
        fused = {chunk_id: 1.0 / (60.0 + index) for index, (chunk_id,) in enumerate(stmt.limit(40))}

    candidate_ids = [chunk_id for chunk_id, _score in sorted(fused.items(), key=lambda item: item[1], reverse=True)[:160]]
    rows = (
        db.query(Chunk, Document, LegalNode)
        .join(Document, Chunk.document_id == Document.id)
        .outerjoin(LegalNode, Chunk.legal_node_id == LegalNode.id)
        .filter(Chunk.id.in_(candidate_ids))
        .all()
    )

    normalized_query = normalize_vietnamese(query)
    candidates: list[_Candidate] = []
    for chunk, document, node in rows:
        score = fused.get(chunk.id, 0.0)
        if normalized_query and normalized_query in chunk.normalized_text:
            score += 0.04
        if exact_ids and chunk.id in exact_ids:
            score += 0.12
        candidates.append(_Candidate(chunk=chunk, document=document, node=node, score=score))

    # Deduplicate by legal node so the top results are not five fragments of
    # the same clause. Keep the highest-scoring fragment.
    best_by_node: dict[tuple[str, str | None], _Candidate] = {}
    for candidate in candidates:
        key = (candidate.document.id, candidate.node.id if candidate.node else None)
        current = best_by_node.get(key)
        if current is None or candidate.score > current.score:
            best_by_node[key] = candidate
    ordered = sorted(best_by_node.values(), key=lambda item: item.score, reverse=True)[:top_k]

    results: list[SearchResult] = []
    for candidate in ordered:
        chunk = candidate.chunk
        node = candidate.node
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=candidate.document.id,
                document_title=candidate.document.title or "Tài liệu không tên",
                document_number=candidate.document.document_number,
                legal_path=node.path if node else "",
                node_level=node.level if node else "",
                text=chunk.text if include_text else snippet(chunk.text, query),
                snippet=snippet(chunk.text, query),
                page_number=chunk.page_number,
                bbox=chunk.bbox,
                score=round(candidate.score, 6),
            )
        )
    took_ms = int((time.perf_counter() - started) * 1000)
    return results, took_ms
