from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import fts_delete_document, fts_upsert_chunks
from app.models import Chunk, Document, DocumentFile, LegalNode, Page, ProcessingJob
from app.services.chunking import ChunkDraft, build_chunks
from app.services.embeddings import get_embedding_provider
from app.services.extraction import ExtractedPage, extract_document
from app.services.parser import ParsedNode, SourceLine, parse_legal_structure
from app.services.text import normalize_vietnamese

logger = logging.getLogger(__name__)
settings = get_settings()

_DOC_NUMBER_RE = re.compile(
    r"(?:Số|So)\s*[:\-]?\s*(\d{1,4}\s*/\s*\d{4}\s*/\s*[A-ZĐ0-9\-]+)",
    re.IGNORECASE,
)
_BARE_DOC_NUMBER_RE = re.compile(r"\b(\d{1,4}\s*/\s*\d{4}\s*/\s*[A-ZĐ0-9\-]+)\b", re.IGNORECASE)
_DOC_TYPE_RE = re.compile(
    r"\b(THÔNG TƯ|NGHỊ ĐỊNH|QUYẾT ĐỊNH|LUẬT|PHÁP LỆNH|CÔNG VĂN|CHỈ THỊ|NGHỊ QUYẾT)\b",
    re.IGNORECASE,
)
_TOC_RE = re.compile(r"\.{3,}\s*\d+\s*$")


class IngestionError(RuntimeError):
    pass


def _stage(db: Session, job: ProcessingJob, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    db.commit()


def _source_line_dict(line: SourceLine) -> dict:
    return {
        "text": line.text,
        "bbox": line.bbox,
        "font_size": line.font_size,
        "bold": line.bold,
    }


def _guess_metadata(pages: list[ExtractedPage], fallback_title: str) -> dict:
    first_text = "\n".join(page.text for page in pages[:3])
    number_match = _DOC_NUMBER_RE.search(first_text) or _BARE_DOC_NUMBER_RE.search(first_text)
    type_match = _DOC_TYPE_RE.search(first_text)
    lines = [line.strip() for line in first_text.splitlines() if line.strip()]

    def usable(candidate: str) -> bool:
        if len(candidate) < 12 or len(candidate) > 300 or _TOC_RE.search(candidate):
            return False
        normalized = normalize_vietnamese(candidate)
        if normalized.startswith(
            ("cong hoa", "doc lap", "ngan hang nha nuoc", "bo ", "so ", "ha noi", "ngay ", "can cu")
        ):
            return False
        if re.match(r"^(phan|chuong|muc|dieu)\s", normalized):
            return False
        if re.fullmatch(r"\d{1,4}\s*/\s*\d{4}\s*/\s*[a-z0-9\-]+", normalized):
            return False
        return True

    title = ""
    if type_match:
        type_text = normalize_vietnamese(type_match.group(1))
        for index, candidate in enumerate(lines):
            if type_text not in normalize_vietnamese(candidate):
                continue
            # A line such as "THÔNG TƯ 01/2024/TT-NHNN" is already descriptive.
            if usable(candidate) and len(candidate) > len(type_match.group(1)) + 10:
                title = candidate
            else:
                for follow_up in lines[index + 1 : index + 4]:
                    if usable(follow_up):
                        title = follow_up
                        break
            if title:
                break
    if not title:
        for candidate in lines:
            if usable(candidate) and candidate.isupper() and len(candidate) > 20:
                title = candidate
                break
    if not title and type_match:
        title = type_match.group(1).title()
        if number_match:
            title = f"{title} {number_match.group(1).replace(' ', '')}"
    return {
        "title": title.strip() or fallback_title,
        "document_number": number_match.group(1).replace(" ", "") if number_match else None,
        "document_type": type_match.group(1).title() if type_match else None,
    }


def _save_pages(db: Session, file: DocumentFile, pages: list[ExtractedPage]) -> None:
    for page in pages:
        db.add(
            Page(
                document_file_id=file.id,
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                image_path=page.image_path,
                text=page.text,
                lines=[_source_line_dict(line) for line in page.lines],
                text_source=page.text_source,
                ocr_confidence=page.ocr_confidence,
            )
        )
    file.page_count = len(pages)
    db.flush()


def _save_nodes(
    db: Session, document_id: str, parsed_nodes: list[ParsedNode]
) -> dict[int, LegalNode]:
    mapping: dict[int, LegalNode] = {}
    for parsed in parsed_nodes:
        node = LegalNode(
            document_id=document_id,
            parent_id=None,
            level=parsed.level,
            number=parsed.number,
            title=parsed.title,
            text=parsed.text,
            path=parsed.path,
            order_index=parsed.order_index,
            page_start=parsed.page_start,
            page_end=parsed.page_end,
            bbox=parsed.bbox,
            confidence=parsed.confidence,
            extraction_method=parsed.extraction_method,
        )
        db.add(node)
        db.flush()
        mapping[id(parsed)] = node
    for parsed in parsed_nodes:
        if parsed.parent is not None and id(parsed.parent) in mapping:
            mapping[id(parsed)].parent_id = mapping[id(parsed.parent)].id
    db.flush()
    return mapping


def _fallback_nodes(pages: list[ExtractedPage]) -> list[ParsedNode]:
    nodes: list[ParsedNode] = []
    for page in pages:
        if not page.text.strip():
            continue
        node = ParsedNode(
            level="page",
            number=str(page.page_number),
            title=f"Trang {page.page_number}",
            text=page.text,
            page_start=page.page_number,
            page_end=page.page_number,
            bbox=None,
            confidence=0.35,
            extraction_method="page-fallback",
        )
        nodes.append(node)
    for index, node in enumerate(nodes):
        node.order_index = index
    return nodes


def _save_chunks(
    db: Session,
    document: Document,
    drafts: list[ChunkDraft],
    node_mapping: dict[int, LegalNode],
) -> list[Chunk]:
    provider = get_embedding_provider()
    created: list[Chunk] = []
    batch_size = 32
    for offset in range(0, len(drafts), batch_size):
        batch = drafts[offset : offset + batch_size]
        texts = [f"{draft.context_text}\n{draft.text}" for draft in batch]
        vectors = provider.embed(texts)
        for draft, vector in zip(batch, vectors, strict=True):
            node = node_mapping.get(id(draft.legal_node))
            chunk = Chunk(
                document_id=document.id,
                legal_node_id=node.id if node else None,
                text=draft.text,
                context_text=draft.context_text,
                normalized_text=draft.normalized_text,
                page_number=draft.page_number,
                bbox=draft.bbox,
                embedding=vector,
                token_count=draft.token_count,
                part_index=draft.part_index,
            )
            db.add(chunk)
            created.append(chunk)
    db.flush()
    fts_upsert_chunks(db, created)
    return created


def process_file(db: Session, file_id: str, job_id: str | None = None) -> None:
    file = db.get(DocumentFile, file_id)
    if not file:
        raise IngestionError(f"DocumentFile {file_id} not found")
    document = db.get(Document, file.document_id)
    if not document:
        raise IngestionError(f"Document {file.document_id} not found")
    job = db.get(ProcessingJob, job_id) if job_id else None
    if job is None:
        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.document_file_id == file_id)
            .order_by(ProcessingJob.created_at.desc())
            .first()
        )
    if job is None:
        raise IngestionError("No processing job found")
    job_id = job.id

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.attempts += 1
    document.status = "processing"
    db.commit()

    try:
        _stage(db, job, "extracting", 10)
        pages = extract_document(
            Path(file.storage_path),
            mime_type=file.mime_type,
            original_filename=file.original_filename,
            ocr_provider=settings.ocr_provider,
            ocr_lang=settings.ocr_lang,
            ocr_dpi=settings.ocr_dpi,
            min_text_chars=settings.ocr_min_text_chars,
            output_dir=settings.pages_dir / file.id,
        )
        if not pages:
            raise IngestionError("No pages extracted from document")

        # Retry-safe: remove previous derived data for this document.
        fts_delete_document(db, document.id)
        db.query(Chunk).filter(Chunk.document_id == document.id).delete()
        db.query(Page).filter(Page.document_file_id == file.id).delete()
        db.query(LegalNode).filter(LegalNode.document_id == document.id).delete()
        db.flush()

        _stage(db, job, "saving_pages", 30)
        _save_pages(db, file, pages)

        metadata = _guess_metadata(pages, Path(file.original_filename).stem)
        document.title = document.title or metadata["title"]
        document.document_number = document.document_number or metadata["document_number"]
        document.document_type = document.document_type or metadata["document_type"]
        if not document.title:
            document.title = metadata["title"]

        _stage(db, job, "parsing_hierarchy", 50)
        parsed_nodes = parse_legal_structure(
            [(page.page_number, page.lines) for page in pages],
            document_type=document.document_type,
        )
        if not parsed_nodes:
            parsed_nodes = _fallback_nodes(pages)
        node_mapping = _save_nodes(db, document.id, parsed_nodes)

        _stage(db, job, "chunking", 65)
        drafts = build_chunks(parsed_nodes, document.title)
        if not drafts:
            fallback = _fallback_nodes(pages)
            if fallback:
                node_mapping = _save_nodes(db, document.id, fallback)
                drafts = build_chunks(fallback, document.title)
        if not drafts:
            raise IngestionError("No text chunks produced from document")

        _stage(db, job, "embedding", 80)
        _save_chunks(db, document, drafts, node_mapping)

        document.status = "ready"
        document.updated_at = datetime.now(timezone.utc)
        job.status = "done"
        job.stage = "ready"
        job.progress = 100
        job.error = None
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Processed document %s: %s pages, %s chunks", document.id, len(pages), len(drafts))
    except Exception as exc:
        logger.exception("Ingestion failed for file %s", file_id)
        db.rollback()
        file = db.get(DocumentFile, file_id)
        document = db.get(Document, file.document_id) if file else None
        job = db.get(ProcessingJob, job_id) if job_id else None
        if job is not None:
            job.status = "failed"
            job.stage = "failed"
            job.error = str(exc)[:4000]
            job.finished_at = datetime.now(timezone.utc)
        if document is not None:
            document.status = "failed"
        db.commit()
        raise
