from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_admin
from app.config import get_settings
from app.db import fts_delete_document, get_db
from app.models import Document, DocumentFile, LegalNode, Page, ProcessingJob, User
from app.schemas import DocumentOut, DocumentUpdate, JobOut, LegalNodeOut, PageOut
from app.services.audit import record_audit
from app.services.storage import (
    delete_document_files,
    guess_mime_type,
    sanitize_for_header,
    save_upload,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()
ALLOWED_SUFFIXES = {".pdf", ".docx"}


def _latest_file(document: Document) -> DocumentFile | None:
    if not document.files:
        return None
    return sorted(document.files, key=lambda item: item.uploaded_at)[-1]


def _doc_out(document: Document) -> DocumentOut:
    file = _latest_file(document)
    return DocumentOut(
        id=document.id,
        title=document.title or (Path(file.original_filename).stem if file else "Tài liệu"),
        document_number=document.document_number,
        document_type=document.document_type,
        issuer=document.issuer,
        issued_date=document.issued_date,
        effective_date=document.effective_date,
        status=document.status,
        page_count=file.page_count if file else 0,
        created_at=document.created_at,
        owner_id=document.owner_id,
        original_filename=file.original_filename if file else None,
    )


def _get_document(db: Session, document_id: str) -> Document:
    document = (
        db.query(Document)
        .options(selectinload(Document.files))
        .filter(Document.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    filename = file.filename or "document.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    document = Document(
        # Leave blank when the user does not supply a title so ingestion can
        # extract the official title and document number from the first pages.
        title=(title or "").strip(),
        owner_id=user.id,
        status="processing",
    )
    db.add(document)
    db.flush()

    try:
        storage_path, sha256, _size = save_upload(file.file, document.id, filename)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        delete_document_files(document.id)
        raise

    existing = db.query(DocumentFile).filter(DocumentFile.sha256 == sha256).first()
    if existing:
        existing_document = db.get(Document, existing.document_id)
        db.delete(document)
        db.commit()
        delete_document_files(document.id)
        if existing_document:
            existing_document = _get_document(db, existing_document.id)
            return _doc_out(existing_document)
        raise HTTPException(status_code=409, detail="A file with this checksum exists but its document is missing")

    document_file = DocumentFile(
        document_id=document.id,
        original_filename=sanitize_for_header(filename),
        sha256=sha256,
        storage_path=str(storage_path),
        mime_type=guess_mime_type(filename),
        uploaded_by=user.id,
    )
    db.add(document_file)
    db.flush()
    job = ProcessingJob(document_file_id=document_file.id, status="queued", stage="queued")
    db.add(job)
    db.commit()

    document = _get_document(db, document.id)
    return _doc_out(document)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    documents = (
        db.query(Document)
        .options(selectinload(Document.files))
        .order_by(Document.created_at.desc())
        .all()
    )
    return [_doc_out(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    return _doc_out(_get_document(db, document_id))


@router.get("/{document_id}/file")
def download_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = _get_document(db, document_id)
    file = _latest_file(document)
    if not file:
        raise HTTPException(status_code=404, detail="Document file not found")
    path = Path(file.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing")
    if user.role == "admin":
        record_audit(
            db,
            actor_id=user.id,
            action="document.admin_view",
            target_type="document",
            target_id=document.id,
            details={"filename": file.original_filename},
        )
        db.commit()
    return FileResponse(
        path,
        media_type=file.mime_type,
        filename=file.original_filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/pages/{page_number}", response_model=PageOut)
def get_page(
    document_id: str,
    page_number: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageOut:
    document = _get_document(db, document_id)
    file = _latest_file(document)
    if not file:
        raise HTTPException(status_code=404, detail="Document file not found")
    page = (
        db.query(Page)
        .filter(Page.document_file_id == file.id, Page.page_number == page_number)
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if user.role == "admin":
        record_audit(
            db,
            actor_id=user.id,
            action="document.admin_page_view",
            target_type="document",
            target_id=document.id,
            details={"page": page_number},
        )
        db.commit()
    return PageOut(
        page_number=page.page_number,
        text=page.text,
        text_source=page.text_source,
        width=page.width,
        height=page.height,
    )


@router.get("/{document_id}/nodes", response_model=list[LegalNodeOut])
def get_nodes(
    document_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LegalNodeOut]:
    _get_document(db, document_id)
    nodes = (
        db.query(LegalNode)
        .filter(LegalNode.document_id == document_id)
        .order_by(LegalNode.order_index.asc())
        .all()
    )
    return [LegalNodeOut.model_validate(node) for node in nodes]


@router.get("/{document_id}/jobs", response_model=list[JobOut])
def get_jobs(
    document_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobOut]:
    document = _get_document(db, document_id)
    file_ids = [file.id for file in document.files]
    if not file_ids:
        return []
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_file_id.in_(file_ids))
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )
    return [JobOut.model_validate(job) for job in jobs]


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: str,
    payload: DocumentUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = _get_document(db, document_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    record_audit(
        db,
        actor_id=admin.id,
        action="document.admin_update",
        target_type="document",
        target_id=document.id,
        details=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    return _doc_out(_get_document(db, document_id))


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    document = _get_document(db, document_id)
    if user.role != "admin" and document.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete this document")
    fts_delete_document(db, document.id)
    record_audit(
        db,
        actor_id=user.id,
        action="document.delete",
        target_type="document",
        target_id=document.id,
        details={"title": document.title, "admin": user.role == "admin"},
    )
    db.delete(document)
    db.commit()
    delete_document_files(document_id)
    return {"ok": True}
