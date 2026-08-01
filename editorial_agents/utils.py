from __future__ import annotations

import hashlib
import html
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

TZ_AR = timezone(timedelta(hours=-3))


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "on", "full"}


def env_int(name: str, default: int, minimum: int | None = None,
            maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def now_ar() -> datetime:
    return datetime.now(TZ_AR)


def normalize_text(text: str) -> str:
    raw = unicodedata.normalize("NFD", (text or "").lower())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def stable_id(text: str, prefix: str = "a") -> str:
    digest = hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def clamp(value: float, low: float = 0, high: float = 100) -> int:
    return int(max(low, min(high, round(value))))


def safe_html(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def unique_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        key = normalize_text(clean)
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out
