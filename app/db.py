from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base, User
from app.services.text import tokenize

logger = logging.getLogger(__name__)
settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        legal_node_id UNINDEXED,
                        text,
                        normalized_text,
                        tokenize='unicode61 remove_diacritics 2'
                    )
                    """
                )
            )
    _seed_admin()


def _seed_admin() -> None:
    from app.auth import hash_password

    with SessionLocal() as db:
        existing = db.query(User).filter(User.role == "admin").first()
        if existing:
            return
        admin = User(
            email=settings.admin_email.lower().strip(),
            password_hash=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        logger.info("Seeded admin user %s", admin.email)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def fts_delete_document(db: Session, document_id: str) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    db.execute(text("DELETE FROM chunk_fts WHERE document_id = :document_id"), {"document_id": document_id})


def fts_upsert_chunks(db: Session, chunks: list) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    for chunk in chunks:
        db.execute(
            text(
                """
                INSERT INTO chunk_fts(chunk_id, document_id, legal_node_id, text, normalized_text)
                VALUES (:chunk_id, :document_id, :legal_node_id, :text, :normalized_text)
                """
            ),
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "legal_node_id": chunk.legal_node_id,
                "text": chunk.text,
                "normalized_text": chunk.normalized_text,
            },
        )


def fts_search(db: Session, query: str, limit: int = 80) -> list[tuple[str, float]]:
    if not settings.database_url.startswith("sqlite"):
        return []
    # FTS5 is strict about syntax. Quote every token and OR them together.
    tokens = tokenize(query)[:32]
    if not tokens:
        return []
    fts_query = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
    rows = db.execute(
        text(
            """
            SELECT chunk_id, bm25(chunk_fts) AS rank
            FROM chunk_fts
            WHERE chunk_fts MATCH :query
            ORDER BY rank
            LIMIT :limit
            """
        ),
        {"query": fts_query, "limit": limit},
    ).all()
    # bm25() is ordered best-first. Convert rank position to a stable score.
    return [(row[0], 1.0 / (1.0 + index)) for index, row in enumerate(rows)]
