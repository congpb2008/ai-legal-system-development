from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import fts_delete_document, fts_upsert_chunks, get_db
from app.models import AuditEvent, Chunk, Document, LegalNode, Page, ProcessingJob, SystemSetting, User
from app.schemas import (
    AdminSettingsOut,
    AdminSettingsUpdate,
    AdminStats,
    AdminUserOut,
    AuditOut,
    LegalNodeUpdate,
    UserUpdate,
)
from app.services.audit import record_audit
from app.services.crypto import decrypt_secret
from app.services.embeddings import get_embedding_provider
from app.services.llm import LLMClient
from app.services.retrieval import invalidate_vector_index
from app.services.runtime_config import (
    get_effective_embedding_config,
    get_effective_llm_config,
    invalidate_runtime_config_cache,
    set_setting,
)
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
        provider = get_embedding_provider(db)
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


@router.get("/settings", response_model=AdminSettingsOut)
def get_settings_admin(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    llm_cfg = get_effective_llm_config(db)
    emb_cfg = get_effective_embedding_config(db)
    llm_secret = db.query(SystemSetting).filter(SystemSetting.key == "llm.api_key").first()
    emb_secret = db.query(SystemSetting).filter(SystemSetting.key == "embeddings.api_key").first()
    return AdminSettingsOut(
        llm={
            "base_url": llm_cfg.get("base_url") or "",
            "api_key_set": bool(llm_secret and llm_secret.value) or bool(llm_cfg.get("api_key")),
            "model": llm_cfg.get("model") or "gpt-4o-mini",
            "timeout_seconds": int(llm_cfg.get("timeout_seconds") or 300),
            "enabled": bool(llm_cfg.get("enabled", True)),
            "source": llm_cfg.get("source") or {},
        },
        embeddings={
            "provider": emb_cfg.get("provider") or "hash",
            "base_url": emb_cfg.get("base_url") or "",
            "api_key_set": bool(emb_secret and emb_secret.value) or bool(emb_cfg.get("api_key")),
            "model": emb_cfg.get("model") or "text-embedding-3-small",
            "dim": int(emb_cfg.get("dim") or 384),
            "source": emb_cfg.get("source") or {},
        },
    )


@router.put("/settings", response_model=AdminSettingsOut)
def update_settings_admin(
    payload: AdminSettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    changed: list[str] = []
    if payload.llm:
        llm = payload.llm
        if llm.base_url is not None:
            set_setting(db, "llm.base_url", llm.base_url, False, admin.id)
            changed.append("llm.base_url")
        if llm.api_key_clear:
            set_setting(db, "llm.api_key", None, True, admin.id)
            changed.append("llm.api_key")
        elif llm.api_key is not None and llm.api_key != "":
            set_setting(db, "llm.api_key", llm.api_key, True, admin.id)
            changed.append("llm.api_key")
        if llm.model is not None:
            set_setting(db, "llm.model", llm.model, False, admin.id)
            changed.append("llm.model")
        if llm.timeout_seconds is not None:
            set_setting(db, "llm.timeout_seconds", str(llm.timeout_seconds), False, admin.id)
            changed.append("llm.timeout_seconds")
        if llm.enabled is not None:
            set_setting(db, "llm.enabled", "true" if llm.enabled else "false", False, admin.id)
            changed.append("llm.enabled")
    if payload.embeddings:
        emb = payload.embeddings
        if emb.provider is not None:
            set_setting(db, "embeddings.provider", emb.provider, False, admin.id)
            changed.append("embeddings.provider")
        if emb.base_url is not None:
            set_setting(db, "embeddings.base_url", emb.base_url, False, admin.id)
            changed.append("embeddings.base_url")
        if emb.api_key_clear:
            set_setting(db, "embeddings.api_key", None, True, admin.id)
            changed.append("embeddings.api_key")
        elif emb.api_key is not None and emb.api_key != "":
            set_setting(db, "embeddings.api_key", emb.api_key, True, admin.id)
            changed.append("embeddings.api_key")
        if emb.model is not None:
            set_setting(db, "embeddings.model", emb.model, False, admin.id)
            changed.append("embeddings.model")
        if emb.dim is not None:
            set_setting(db, "embeddings.dim", str(emb.dim), False, admin.id)
            changed.append("embeddings.dim")
    invalidate_runtime_config_cache()
    record_audit(
        db,
        actor_id=admin.id,
        action="settings.admin_update",
        target_type="settings",
        target_id=None,
        details={"changed": changed},
    )
    db.commit()
    return get_settings_admin(_admin, db)


@router.post("/settings/test/llm")
def test_llm_settings(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        config = get_effective_llm_config(db)
        client = LLMClient(config=config)
        if not client.available:
            return {"ok": False, "error": "LLM not configured (missing base_url or model)"}
        # Try a minimal request
        resp = client.chat([{"role": "user", "content": "ping"}], temperature=0, max_tokens=1)
        return {"ok": True, "message": "Connected successfully"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/settings/test/embeddings")
def test_embedding_settings(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        provider = get_embedding_provider(db)
        vectors = provider.embed(["test"])
        if not vectors or not vectors[0]:
            return {"ok": False, "error": "Empty embedding returned"}
        return {"ok": True, "message": f"Connected successfully (dim={len(vectors[0])})"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
