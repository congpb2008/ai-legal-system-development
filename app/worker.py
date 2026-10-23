from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import ProcessingJob
from app.services.ingestion import process_file
from app.services.retrieval import invalidate_vector_index

logger = logging.getLogger(__name__)
settings = get_settings()
_stop = threading.Event()


def requeue_stale_jobs(max_age_minutes: int = 30) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    with SessionLocal() as db:
        jobs = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == "running",
                or_(ProcessingJob.started_at.is_(None), ProcessingJob.started_at < cutoff),
            )
            .all()
        )
        for job in jobs:
            job.status = "queued"
            job.stage = "requeued"
            job.error = "Worker restarted while processing; job requeued."
        db.commit()
        return len(jobs)


def process_one() -> bool:
    with SessionLocal() as db:
        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at.asc())
            .first()
        )
        if not job:
            return False
        try:
            process_file(db, job.document_file_id, job.id)
        except Exception:
            logger.exception("Job %s failed", job.id)
        finally:
            invalidate_vector_index()
        return True


def run_worker(poll_seconds: float | None = None) -> None:
    poll = poll_seconds if poll_seconds is not None else settings.worker_poll_seconds
    logger.info("Ingestion worker started")
    requeue_stale_jobs()
    while not _stop.is_set():
        worked = process_one()
        if not worked:
            _stop.wait(poll)
    logger.info("Ingestion worker stopped")


def stop_worker() -> None:
    _stop.set()


def start_worker_thread() -> threading.Thread:
    _stop.clear()
    thread = threading.Thread(target=run_worker, name="ingestion-worker", daemon=True)
    thread.start()
    return thread


def main() -> None:
    parser = argparse.ArgumentParser(description="Legal document ingestion worker")
    parser.add_argument("--once", action="store_true", help="Process queued jobs and exit")
    parser.add_argument("--init-db", action="store_true", help="Create tables and seed admin")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.init_db:
        init_db()
    if args.once:
        requeue_stale_jobs()
        while process_one():
            pass
        return
    requeue_stale_jobs()
    run_worker()


if __name__ == "__main__":
    main()
