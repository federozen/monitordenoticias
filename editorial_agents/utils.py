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

_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def parse_datetime(value: Any, assume_tz=TZ_AR) -> datetime | None:
    """Parsea fechas ISO y normaliza a la zona horaria argentina.

    Las fuentes entregan una mezcla de fechas con y sin zona. Para las fechas
    sin zona se asume Argentina, porque es el criterio editorial del tablero.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=assume_tz)
    return dt.astimezone(TZ_AR)


def explicit_date_in_text(text: str, now: datetime | None = None) -> datetime | None:
    """Extrae una fecha calendarizada escrita en un titulo.

    Sirve para descartar servicios viejos que siguen apareciendo en portadas,
    por ejemplo: "Partidos de HOY, miercoles 29 de julio".
    """
    now = (now or now_ar()).astimezone(TZ_AR)
    normalized = normalize_text(text)
    raw_text = unicodedata.normalize("NFD", str(text or "").lower())
    raw_text = "".join(ch for ch in raw_text if unicodedata.category(ch) != "Mn")

    # 29 de julio / 29 de julio de 2026
    months = "|".join(sorted(_MONTHS_ES, key=len, reverse=True))
    match = re.search(rf"\b(\d{{1,2}})\s+de\s+({months})(?:\s+de\s+(\d{{4}}))?\b", normalized)
    if match:
        day = int(match.group(1))
        month = _MONTHS_ES[match.group(2)]
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            candidate = datetime(year, month, day, tzinfo=TZ_AR)
            # Evita interpretar como futuro una fecha de diciembre vista en enero.
            if not match.group(3) and candidate > now + timedelta(days=45):
                candidate = candidate.replace(year=year - 1)
            return candidate
        except ValueError:
            return None

    # 29/07, 29-07, 29/07/2026
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", raw_text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        raw_year = match.group(3)
        year = now.year if not raw_year else int(raw_year)
        if raw_year and year < 100:
            year += 2000
        try:
            candidate = datetime(year, month, day, tzinfo=TZ_AR)
            if not raw_year and candidate > now + timedelta(days=45):
                candidate = candidate.replace(year=year - 1)
            return candidate
        except ValueError:
            return None
    return None
