from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user: UserOut


class DocumentOut(BaseModel):
    id: str
    title: str
    document_number: str | None = None
    document_type: str | None = None
    issuer: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    status: str
    page_count: int = 0
    created_at: datetime
    owner_id: str | None = None
    original_filename: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuer: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None


class PageOut(BaseModel):
    page_number: int
    text: str
    text_source: str
    width: float | None = None
    height: float | None = None


class LegalNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    level: str
    number: str | None
    title: str
    text: str
    path: str
    order_index: int
    page_start: int | None
    page_end: int | None
    bbox: list[float] | None
    confidence: float
    extraction_method: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_file_id: str
    status: str
    stage: str
    progress: int
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    document_ids: list[str] | None = None
    include_text: bool = True


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    document_number: str | None
    legal_path: str
    node_level: str
    text: str
    snippet: str
    page_number: int | None
    bbox: list[float] | None
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    took_ms: int


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)
    top_k: int = Field(default=8, ge=1, le=30)
    generate_answer: bool = True
    document_ids: list[str] | None = None


class Citation(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    document_title: str
    document_number: str | None
    legal_path: str
    page_number: int | None
    bbox: list[float] | None
    quote: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    sources: list[SearchResult]
    abstained: bool = False
    timings: dict[str, int] = Field(default_factory=dict)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict
    created_at: datetime


class AdminUserOut(UserOut):
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


class LegalNodeUpdate(BaseModel):
    title: str | None = None
    text: str | None = None


class AdminStats(BaseModel):
    documents: int
    ready: int
    processing: int
    failed: int
    pages: int
    chunks: int
    users: int
