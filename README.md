# Banking Legal Assistant (MVP)

On-prem-first Vietnamese legal document search assistant with chat-first UI, legal-hierarchy fidelity, citations, and PDF/DOCX support.

## Quick start (local dev)

### Backend
```bash
cp .env.example .env
uv sync --extra dev
uv run alembic upgrade head  # if migrations exist
uv run uvicorn app.main:app --reload
```

### Frontend
```bash
cd web
npm install
npm run dev
```

API docs: http://localhost:8000/docs
Frontend dev: http://localhost:5173 (proxies `/api` to backend)

## Default access
- Default admin: `admin@example.com` (password set via `ADMIN_PASSWORD`; default `admin123` for local dev)
- Change admin password on first deployment.

## Docker (recommended)
```bash
cp .env.example .env
docker compose up --build
```
App: http://localhost:8000

### PostgreSQL (production)
```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build
```
The Postgres image includes the `pgvector` extension. The current MVP stores embeddings as
JSON and ranks them in-process, which is portable; pgvector can replace that path for
larger corpora without changing the ingestion pipeline.

## Features
- Upload PDF/DOCX, background OCR/parsing/chunking/indexing
- Vietnamese legal hierarchy (Phần/Chương/Mục/Điều/Khoản/Điểm) with clause/point-level chunks
- Hybrid search (SQLite FTS5 + local embeddings), citations with page and bbox
- Chat-first UI with Sources panel and PDF highlight
- Admin: users, audit log, reindex, document management
- SQLite by default; PostgreSQL + pgvector supported via `DATABASE_URL`

## Configuration
See `.env.example` for all settings. Key options:
- `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (empty base URL enables extractive fallback)
- `EMBEDDING_PROVIDER` (hash|openai), `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`
- `OCR_PROVIDER` (auto|paddle|tesseract|none) – enable for scanned PDFs
- `MAX_UPLOAD_MB`
- `RUN_WORKER_INPROCESS` (true for single-process deployment)

## Testing
```bash
uv run pytest -q
```

## Notes
- For production with many users, use PostgreSQL instead of SQLite.
- Docker enables Tesseract OCR by default. Local dev needs `tesseract-ocr` and
  `tesseract-ocr-vie` installed, or set `OCR_PROVIDER=none` for text-layer PDFs.
- OCR quality on the real scanned corpus still needs to be validated with representative files.
- Set `ENVIRONMENT=production` only behind HTTPS so session cookies stay secure.
- Change `SECRET_KEY` and `ADMIN_PASSWORD` before exposing the service.
- The frontend is built and served by FastAPI from `web/dist`.
