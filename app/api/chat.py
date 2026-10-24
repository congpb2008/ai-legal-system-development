from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import ChatRequest, ChatResponse
from app.services.llm import extractive_answer, generate_answer, make_citations, stream_answer
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _history(payload: ChatRequest) -> list[dict]:
    return [{"role": message.role, "content": message.content} for message in payload.history]


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    started = time.perf_counter()
    results, retrieval_ms = search_chunks(
        db,
        payload.message,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )
    if not payload.generate_answer:
        return ChatResponse(
            answer="",
            citations=[],
            sources=results,
            timings={"retrieval_ms": retrieval_ms, "total_ms": int((time.perf_counter() - started) * 1000)},
        )

    answer_started = time.perf_counter()
    if not results:
        answer = extractive_answer([])
        citations = []
        abstained = True
    else:
        answer, citations, abstained = generate_answer(payload.message, results, _history(payload), db=db)
    answer_ms = int((time.perf_counter() - answer_started) * 1000)
    return ChatResponse(
        answer=answer,
        citations=citations,
        sources=results,
        abstained=abstained,
        timings={
            "retrieval_ms": retrieval_ms,
            "answer_ms": answer_ms,
            "total_ms": int((time.perf_counter() - started) * 1000),
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    results, retrieval_ms = search_chunks(
        db,
        payload.message,
        top_k=payload.top_k,
        document_ids=payload.document_ids,
    )

    def generate():
        yield _sse(
            "sources",
            {
                "sources": [result.model_dump(mode="json") for result in results],
                "retrieval_ms": retrieval_ms,
            },
        )
        if not payload.generate_answer:
            yield _sse("done", {"answer": "", "citations": [], "abstained": False, "timings": {"retrieval_ms": retrieval_ms}})
            return
        if not results:
            answer = extractive_answer([])
            yield _sse("token", {"text": answer})
            yield _sse(
                "done",
                {
                    "answer": answer,
                    "citations": [],
                    "abstained": True,
                    "timings": {"retrieval_ms": retrieval_ms},
                },
            )
            return

        answer_parts: list[str] = []
        answer_started = time.perf_counter()
        try:
            for token in stream_answer(payload.message, results, _history(payload), db=db):
                answer_parts.append(token)
                yield _sse("token", {"text": token})
        except Exception as exc:  # pragma: no cover - defensive SSE path
            yield _sse("error", {"message": str(exc)})
            return
        answer = "".join(answer_parts).strip()
        if not answer:
            answer = extractive_answer(results)
            yield _sse("token", {"text": answer})
        citations = make_citations(results, answer)
        answer_ms = int((time.perf_counter() - answer_started) * 1000)
        yield _sse(
            "done",
            {
                "answer": answer,
                "citations": [citation.model_dump(mode="json") for citation in citations],
                "abstained": "không tìm thấy đủ căn cứ" in answer.lower(),
                "timings": {
                    "retrieval_ms": retrieval_ms,
                    "answer_ms": answer_ms,
                    "total_ms": int((time.perf_counter() - started) * 1000),
                },
            },
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
