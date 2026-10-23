from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..config import get_settings


def _cache_path(key: str) -> Path:
    settings = get_settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return settings.cache_dir / digest[:2] / f"{digest}.json"


def get_json(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put_json(key: str, value: dict[str, Any]) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def delete_cache() -> int:
    count = 0
    root = get_settings().cache_dir
    if root.exists():
        for path in root.rglob("*.json"):
            path.unlink(missing_ok=True)
            count += 1
    return count
