from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import fts_delete_document, fts_upsert_chunks, get_db
from app.models import AuditEvent, Chunk, Document, LegalNode, Page, ProcessingJob, User
from app.schemas import (
    AdminStats,
    AdminUserOut,
    AuditOut,
    LegalNodeUpdate,
    UserUpdate,
)
from app.services.audit import record_audit
from app.services.embeddings import get_embedding_provider
from app.services.retrieval import invalidate_vector_index
from app.services.text import normalize_vietnamese, tokenize

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserOut]:
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [AdminUserOut.model_validate(user) for user in users]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin" and payload.role == "user":
        admin_count = db.query(func.count(User.id)).filter(User.role == "admin", User.is_active.is_(True)).scalar()
        if admin_count and admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active admin")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(user, field, value)
    record_audit(
        db,
        actor_id=admin.id,
        action="user.admin_update",
        target_type="user",
        target_id=user.id,
        details=changed,
    )
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user)


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuditOut]:
    events = (
        db.query(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [AuditOut.model_validate(event) for event in events]


@router.get("/stats", response_model=AdminStats)
def stats(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminStats:
    documents = db.query(func.count(Document.id)).scalar() or 0
    return AdminStats(
        documents=documents,
        ready=db.query(func.count(Document.id)).filter(Document.status == "ready").scalar() or 0,
        processing=db.query(func.count(Document.id)).filter(Document.status == "processing").scalar() or 0,
        failed=db.query(func.count(Document.id)).filter(Document.status == "failed").scalar() or 0,
        pages=db.query(func.count(Page.id)).scalar() or 0,
        chunks=db.query(func.count(Chunk.id)).scalar() or 0,
        users=db.query(func.count(User.id)).scalar() or 0,
    )


@router.post("/documents/{document_id}/reindex")
def reindex_document(
    document_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    file = sorted(document.files, key=lambda item: item.uploaded_at)[-1] if document.files else None
    if not file:
        raise HTTPException(status_code=404, detail="Document file not found")
    job = ProcessingJob(document_file_id=file.id, status="queued", stage="queued")
    document.status = "processing"
    db.add(job)
    record_audit(
        db,
        actor_id=admin.id,
        action="document.admin_reindex",
        target_type="document",
        target_id=document.id,
        details={"job_id": job.id},
    )
    db.commit()
    return {"ok": True, "job_id": job.id}


@router.patch("/legal-nodes/{node_id}")
def update_legal_node(
    node_id: str,
    payload: LegalNodeUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    node = db.get(LegalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Legal node not found")
    document = db.get(Document, node.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(node, field, value)

    # A corrected node is re-chunked as one authoritative chunk. This is a
    # deliberate MVP trade-off: admin corrections are rare, and a single exact
    # chunk is safer than silently keeping stale text.
    db.query(Chunk).filter(Chunk.legal_node_id == node.id).delete()
    if node.text.strip():
        context = f"{document.title}\n{node.path}\n{node.title}".strip()
        provider = get_embedding_provider()
        vector = provider.embed_query(f"{context}\n{node.text}")
        chunk = Chunk(
            document_id=document.id,
            legal_node_id=node.id,
            text=node.text,
            context_text=context,
            normalized_text=normalize_vietnamese(f"{context}\n{node.text}"),
            page_number=node.page_start,
            bbox=node.bbox,
            embedding=vector,
            token_count=len(tokenize(node.text)),
        )
        db.add(chunk)
        db.flush()
    db.flush()

    fts_delete_document(db, document.id)
    all_chunks = db.query(Chunk).filter(Chunk.document_id == document.id).all()
    fts_upsert_chunks(db, all_chunks)
    invalidate_vector_index()
    record_audit(
        db,
        actor_id=admin.id,
        action="legal_node.admin_update",
        target_type="legal_node",
        target_id=node.id,
        details=changed,
    )
    db.commit()
    return {"ok": True, "document_id": document.id}
