from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def normalize_vietnamese(value: str) -> str:
    """Lowercase and strip Vietnamese diacritics for forgiving matching."""
    lowered = value.lower().replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_marks).strip()


def tokenize(value: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(normalize_vietnamese(value)) if len(token) > 1]


def fts_query(value: str) -> str:
    tokens = tokenize(value)
    return " OR ".join(f'"{token}"' for token in tokens)


def snippet(text: str, query: str, length: int = 320) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= length:
        return clean
    normalized = normalize_vietnamese(clean)
    best = 0
    for token in tokenize(query):
        position = normalized.find(token)
        if position >= 0:
            best = max(0, position - length // 3)
            break
    return ("…" if best else "") + clean[best : best + length].strip() + "…"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_vietnamese(value)).strip("-") or "document"
