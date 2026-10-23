from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import SearchRequest, SearchResponse
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    results, took_ms = search_chunks(
        db,
        payload.query,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
        include_text=payload.include_text,
    )
    return SearchResponse(query=payload.query, results=results, took_ms=took_ms)
