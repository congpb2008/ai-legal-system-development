from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, chat, documents, search
from app.config import get_settings
from app.db import init_db
from app.worker import start_worker_thread, stop_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    thread = None
    if settings.run_worker_inprocess:
        thread = start_worker_thread()
        logger.info("In-process ingestion worker started")
    yield
    if thread is not None:
        stop_worker()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "app": settings.app_name, "environment": settings.environment}


if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    icon = WEB_DIST / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        """
        <html><body style="font-family: sans-serif; max-width: 720px; margin: 4rem auto;">
        <h1>Banking Legal Assistant</h1>
        <p>The API is running, but the web UI has not been built yet.</p>
        <pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>
        <p>API docs: <a href="/docs">/docs</a></p>
        </body></html>
        """,
        status_code=200,
    )
