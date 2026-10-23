from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator

import httpx

from app.config import get_settings
from app.schemas import Citation, SearchResult
from app.services.text import snippet

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """Bạn là trợ lý tra cứu văn bản pháp luật ngân hàng bằng tiếng Việt.

Quy tắc bắt buộc:
1. Chỉ sử dụng các đoạn văn bản trong PHẦN NGỮ CẢNH được cung cấp.
2. Không bịa điều khoản, số hiệu văn bản, ngày tháng, hoặc nội dung không có trong ngữ cảnh.
3. Mỗi kết luận phải có trích dẫn dạng [1], [2] tương ứng với nguồn trong ngữ cảnh.
4. Nếu ngữ cảnh không đủ để trả lời, hãy nói rõ: "Tôi không tìm thấy đủ căn cứ trong tài liệu hiện có."
5. Trả lời ngắn gọn, ưu tiên nêu điều khoản áp dụng trước, giải thích sau.
6. Không đưa ra tư vấn pháp lý cá nhân; chỉ tóm tắt nội dung văn bản.

Định dạng câu trả lời:
- Kết luận ngắn.
- Căn cứ: liệt kê điều/khoản/điểm kèm trích dẫn [N].
- Lưu ý nếu có điều kiện hoặc ngoại lệ.
"""


def _chat_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.model)

    def chat(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 1600) -> str:
        if not self.available:
            return ""
        response = httpx.post(
            _chat_endpoint(self.base_url),
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()

    def stream_chat(
        self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 1600
    ) -> Iterator[str]:
        if not self.available:
            return
        with httpx.stream(
            "POST",
            _chat_endpoint(self.base_url),
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                else:
                    continue
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                    token = payload["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if token:
                    yield token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def build_context(results: list[SearchResult]) -> str:
    blocks: list[str] = []
    for index, result in enumerate(results, start=1):
        document = result.document_title
        if result.document_number:
            document += f" — {result.document_number}"
        location = result.legal_path or "Không xác định cấu trúc"
        page = f"Trang {result.page_number}" if result.page_number else "Không rõ trang"
        blocks.append(f"[{index}] {document} | {location} | {page}\n{result.text}")
    return "\n\n".join(blocks)


def _messages(question: str, results: list[SearchResult], history: list[dict] | None = None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
    messages.append(
        {
            "role": "user",
            "content": f"PHẦN NGỮ CẢNH:\n{build_context(results)}\n\nCÂU HỎI:\n{question}",
        }
    )
    return messages


def extractive_answer(results: list[SearchResult]) -> str:
    if not results:
        return "Tôi không tìm thấy đủ căn cứ trong tài liệu hiện có."
    lines = ["Tôi tìm thấy các quy định liên quan sau:"]
    for index, result in enumerate(results[:3], start=1):
        location = result.legal_path or result.document_title
        lines.append(f"- {location}: {snippet(result.text, '', 280)} [{index}]")
    lines.append("Vui lòng kiểm tra nguồn ở khung bên phải để xem toàn văn.")
    return "\n".join(lines)


def make_citations(results: list[SearchResult], answer: str) -> list[Citation]:
    used = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    citations: list[Citation] = []
    for index, result in enumerate(results, start=1):
        if used and index not in used:
            continue
        citations.append(
            Citation(
                index=index,
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_title=result.document_title,
                document_number=result.document_number,
                legal_path=result.legal_path,
                page_number=result.page_number,
                bbox=result.bbox,
                quote=snippet(result.text, "", 420),
            )
        )
    if not used:
        # The prompt requires citations, but do not hide the available sources.
        citations = [
            Citation(
                index=index,
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_title=result.document_title,
                document_number=result.document_number,
                legal_path=result.legal_path,
                page_number=result.page_number,
                bbox=result.bbox,
                quote=snippet(result.text, "", 420),
            )
            for index, result in enumerate(results[:3], start=1)
        ]
    return citations


def generate_answer(
    question: str,
    results: list[SearchResult],
    history: list[dict] | None = None,
) -> tuple[str, list[Citation], bool]:
    if not results:
        return extractive_answer([]), [], True
    client = LLMClient()
    if not client.available:
        answer = extractive_answer(results)
        return answer, make_citations(results, answer), False

    try:
        answer = client.chat(_messages(question, results, history))
    except Exception:
        logger.exception("LLM answer generation failed; using extractive fallback")
        answer = extractive_answer(results)
    if not answer:
        answer = extractive_answer(results)
    abstained = "không tìm thấy đủ căn cứ" in answer.lower()
    return answer, make_citations(results, answer), abstained


def stream_answer(
    question: str,
    results: list[SearchResult],
    history: list[dict] | None = None,
) -> Iterator[str]:
    if not results:
        yield extractive_answer([])
        return
    client = LLMClient()
    if not client.available:
        yield extractive_answer(results)
        return
    yielded = False
    try:
        for token in client.stream_chat(_messages(question, results, history)):
            yielded = True
            yield token
    except Exception:
        logger.exception("LLM streaming failed")
        if not yielded:
            yield extractive_answer(results)
