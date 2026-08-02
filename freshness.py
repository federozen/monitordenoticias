from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from .utils import explicit_date_in_text, normalize_text, parse_datetime

TRUSTED_DATE_TYPES = {
    "article_metadata",
    "publisher_metadata",
    "official_timestamp",
    "publisher_timestamp",
    "rss_publisher_timestamp",
}
UNTRUSTED_DATE_TYPES = {
    "discovery_timestamp",
    "listing_timestamp",
    "missing",
    "unverified",
    "unverified_stale_risk",
}

# Titulares de archivo, efemeride o recapitulacion que suelen reaparecer en
# portadas/agregadores. No se excluyen para siempre, pero requieren fecha del
# articulo verificada en la pagina original para entrar a una ventana operativa.
FRESH_HOOK_PATTERNS = (
    "nuevo dato", "nueva informacion", "inedito", "inedita", "revelo", "revela",
    "confirmo", "confirmacion", "actualizacion", "documental", "video nuevo",
    "imagen inedita", "testimonio nuevo", "cambio", "consecuencia",
)

STALE_RISK_PATTERNS = (
    "final del mundial",
    "final de la copa del mundo",
    "100 partidos de scaloni",
    "cien partidos de scaloni",
    "aniversario",
    "efemeride",
    "el dia que",
    "asi fue la final",
    "repaso de la final",
    "recuerdo de",
    "a dos semanas de",
    "a una semana de",
    "hace dos semanas",
    "hace una semana",
    "la historia de",
    "archivo",
)


@dataclass(frozen=True)
class FreshnessAssessment:
    accepted: bool
    reason: str
    timestamp: datetime | None = None
    trust: str = "missing"
    source: str = ""


def is_stale_risk_title(title: str) -> bool:
    text = normalize_text(title)
    if any(pattern in text for pattern in STALE_RISK_PATTERNS):
        return True
    # "hace 12 dias", "a 15 dias de", etc.
    return bool(re.search(r"\b(?:hace|a)\s+\d{1,3}\s+dias?\b", text))


def _date_from(item: dict) -> datetime | None:
    for key in (
        "article_published_at",
        "fecha_publicacion_verificada",
        "fecha_publicacion",
        "published_at",
        "FechaPublicacion",
        "fecha",
    ):
        value = parse_datetime(item.get(key))
        if value:
            return value
    return None


def _trust_from(item: dict) -> str:
    return str(
        item.get("date_trust")
        or item.get("DateTrust")
        or item.get("freshness_trust")
        or "missing"
    ).strip().lower()


def assess_item(item: dict, title: str, start: datetime, now: datetime) -> FreshnessAssessment:
    explicit = explicit_date_in_text(title, now)
    if explicit is not None and explicit.date() < start.date():
        return FreshnessAssessment(False, "FECHA_EXPLICITA_ANTERIOR", explicit, "explicit_title", "title")

    trust = _trust_from(item)
    timestamp = _date_from(item)
    if timestamp is None:
        return FreshnessAssessment(False, "SIN_FECHA_VERIFICABLE", None, trust)
    if trust in UNTRUSTED_DATE_TYPES:
        return FreshnessAssessment(False, "FECHA_DE_DESCUBRIMIENTO_NO_VALIDA", timestamp, trust)
    if trust not in TRUSTED_DATE_TYPES:
        return FreshnessAssessment(False, "TIPO_DE_FECHA_NO_CONFIABLE", timestamp, trust)

    if is_stale_risk_title(title):
        if trust not in {"article_metadata", "publisher_metadata", "official_timestamp"}:
            return FreshnessAssessment(False, "TEMA_DE_ARCHIVO_SIN_FECHA_DE_ARTICULO", timestamp, trust)
        normalized = normalize_text(title)
        if not any(hook in normalized for hook in FRESH_HOOK_PATTERNS):
            return FreshnessAssessment(False, "CONTENIDO_HISTORICO_SIN_NOVEDAD", timestamp, trust)

    if timestamp < start:
        return FreshnessAssessment(False, "FUERA_DE_VENTANA", timestamp, trust)
    if timestamp > now + timedelta(minutes=15):
        return FreshnessAssessment(False, "FECHA_FUTURA_INCONSISTENTE", timestamp, trust)
    return FreshnessAssessment(True, "FECHA_VERIFICADA_EN_VENTANA", timestamp, trust)


def assess_evidence(evidence: Iterable[dict], title: str, start: datetime,
                    now: datetime) -> FreshnessAssessment:
    assessments = [assess_item(item, title, start, now) for item in evidence]
    accepted = [item for item in assessments if item.accepted]
    if accepted:
        return max(accepted, key=lambda item: item.timestamp or start)
    if not assessments:
        return FreshnessAssessment(False, "SIN_EVIDENCIA_FECHADA")
    # Prioriza la explicacion mas util para auditoria.
    order = {
        "FECHA_EXPLICITA_ANTERIOR": 0,
        "TEMA_DE_ARCHIVO_SIN_FECHA_DE_ARTICULO": 1,
        "FUERA_DE_VENTANA": 2,
        "FECHA_DE_DESCUBRIMIENTO_NO_VALIDA": 3,
        "SIN_FECHA_VERIFICABLE": 4,
    }
    return min(assessments, key=lambda item: order.get(item.reason, 99))


def confidence_from_evidence(items: list[dict]) -> tuple[int, str]:
    if not items:
        return 20, "No hay evidencia directa suficiente."
    publishers = {
        normalize_text(str(item.get("publisher") or item.get("source_name") or ""))
        for item in items
        if item.get("publisher") or item.get("source_name")
    }
    verified = sum(1 for item in items if _trust_from(item) in TRUSTED_DATE_TYPES)
    official = sum(
        1 for item in items
        if any(term in normalize_text(str(item.get("source_id") or item.get("publisher") or ""))
               for term in ("fifa", "uefa", "conmebol", "club", "oficial", "federacion", "liga"))
    )
    score = 30 + min(25, len(publishers) * 8) + min(25, verified * 8) + min(20, official * 10)
    score = max(0, min(100, score))
    parts = []
    if official:
        parts.append(f"{official} fuente(s) oficial(es)")
    if len(publishers) > 1:
        parts.append(f"{len(publishers)} publishers originales")
    if verified:
        parts.append(f"{verified} fecha(s) verificadas")
    return score, ", ".join(parts) if parts else "Una fuente directa con fecha verificable."
