from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # repo root
    return Path(__file__).resolve().parent.parent


def writable_dir() -> Path:
    if is_frozen():
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            return Path.cwd()
    return Path(__file__).resolve().parent.parent
