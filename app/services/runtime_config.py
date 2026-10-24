from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SystemSetting
from app.services.crypto import decrypt_secret, encrypt_secret

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 30.0


def invalidate_runtime_config_cache() -> None:
    _cache.clear()


def _get_db_cached(db: Session, key: str) -> dict[str, Any] | None:
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    return None


def _set_db_cached(key: str, value: dict[str, Any]) -> None:
    _cache[key] = (time.time(), value)


def get_all_settings(db: Session) -> list[SystemSetting]:
    return db.query(SystemSetting).all()


def get_setting(db: Session, key: str) -> SystemSetting | None:
    return db.query(SystemSetting).filter(SystemSetting.key == key).first()


def set_setting(
    db: Session,
    key: str,
    value: str | None,
    is_secret: bool = False,
    updated_by: str | None = None,
) -> SystemSetting:
    setting = get_setting(db, key)
    stored_value = encrypt_secret(value) if is_secret and value not in (None, "") else value
    if setting:
        setting.value = stored_value
        setting.is_secret = is_secret
        if updated_by:
            setting.updated_by = updated_by
    else:
        setting = SystemSetting(
            key=key,
            value=stored_value,
            is_secret=is_secret,
            updated_by=updated_by,
        )
        db.add(setting)
    db.commit()
    db.refresh(setting)
    invalidate_runtime_config_cache()
    return setting


def get_effective_llm_config(db: Session | None = None) -> dict[str, Any]:
    env_settings = get_settings()
    config: dict[str, Any] = {
        "base_url": env_settings.llm_base_url,
        "api_key": env_settings.llm_api_key,
        "model": env_settings.llm_model,
        "timeout_seconds": env_settings.llm_timeout_seconds,
        "enabled": True,
        "source": {
            "base_url": "env",
            "api_key": "env",
            "model": "env",
            "timeout_seconds": "env",
        },
    }

    if db is None:
        return config

    cached = _get_db_cached(db, "llm")
    if cached is not None:
        return cached

    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("llm.%")).all():
        key = setting.key.split(".", 1)[1]
        if key == "enabled":
            config["enabled"] = setting.value in ("true", "1", "True")
            config["source"][key] = "db"
            continue
        if key == "api_key":
            config["api_key"] = decrypt_secret(setting.value) or ""
            config["source"][key] = "db"
            continue
        if key == "timeout_seconds":
            try:
                config["timeout_seconds"] = int(setting.value) if setting.value else config["timeout_seconds"]
            except Exception:
                pass
            config["source"][key] = "db"
            continue
        if setting.value is not None:
            config[key] = setting.value
            config["source"][key] = "db"

    _set_db_cached("llm", config)
    return config


def get_effective_embedding_config(db: Session | None = None) -> dict[str, Any]:
    env_settings = get_settings()
    config: dict[str, Any] = {
        "provider": env_settings.embedding_provider,
        "base_url": env_settings.embedding_base_url,
        "api_key": env_settings.embedding_api_key,
        "model": env_settings.embedding_model,
        "dim": env_settings.embedding_dim,
        "source": {
            "provider": "env",
            "base_url": "env",
            "api_key": "env",
            "model": "env",
            "dim": "env",
        },
    }

    if db is None:
        return config

    cached = _get_db_cached(db, "embeddings")
    if cached is not None:
        return cached

    for setting in db.query(SystemSetting).filter(SystemSetting.key.like("embeddings.%")).all():
        key = setting.key.split(".", 1)[1]
        if key == "api_key":
            config["api_key"] = decrypt_secret(setting.value) or ""
            config["source"][key] = "db"
            continue
        if key == "dim":
            try:
                config["dim"] = int(setting.value) if setting.value else config["dim"]
            except Exception:
                pass
            config["source"][key] = "db"
            continue
        if setting.value is not None:
            config[key] = setting.value
            config["source"][key] = "db"

    _set_db_cached("embeddings", config)
    return config
