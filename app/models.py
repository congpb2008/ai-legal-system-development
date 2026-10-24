from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(500), default="")
    document_number: Mapped[str | None] = mapped_column(String(120), index=True)
    document_type: Mapped[str | None] = mapped_column(String(80), index=True)
    issuer: Mapped[str | None] = mapped_column(String(300))
    issued_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    files: Mapped[list[DocumentFile]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    legal_nodes: Mapped[list[LegalNode]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentFile(Base):
    __tablename__ = "document_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/pdf")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="files")
    pages: Mapped[list[Page]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_files.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    width: Mapped[float | None] = mapped_column(Float)
    height: Mapped[float | None] = mapped_column(Float)
    image_path: Mapped[str | None] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text, default="")
    lines: Mapped[list[dict]] = mapped_column(JSON, default=list)
    text_source: Mapped[str] = mapped_column(String(30), default="text")
    ocr_confidence: Mapped[float | None] = mapped_column(Float)

    file: Mapped[DocumentFile] = relationship(back_populates="pages")

    __table_args__ = (Index("ix_pages_file_number", "document_file_id", "page_number", unique=True),)


class LegalNode(Base):
    __tablename__ = "legal_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("legal_nodes.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(30), index=True)
    number: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(1000), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(String(2000), default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    extraction_method: Mapped[str] = mapped_column(String(30), default="rule")

    document: Mapped[Document] = relationship(back_populates="legal_nodes")
    parent: Mapped[LegalNode | None] = relationship(remote_side="LegalNode.id", back_populates="children")
    children: Mapped[list[LegalNode]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="legal_node", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_legal_nodes_doc_level", "document_id", "level"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    legal_node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("legal_nodes.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="", index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, index=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    part_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")
    legal_node: Mapped[LegalNode | None] = relationship(back_populates="chunks")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_files.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    file: Mapped[DocumentFile] = relationship(back_populates="jobs")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
