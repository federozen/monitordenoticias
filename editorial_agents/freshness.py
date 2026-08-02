from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from .utils import explicit_date_in_text, normalize_text, parse_datetime

# Fechas extraidas de la nota o de metadata editorial estable.
CONFIRMED_DATE_TYPES = {
    "article_metadata",
    "official_timestamp",
    "publisher_metadata",
}
# Fechas que llegan desde un feed/listado directo del publisher. Son utiles para
# una mesa online, pero se muestran como probables hasta verificar la nota.
PROBABLE_DATE_TYPES = {
    "publisher_timestamp",
    "rss_publisher_timestamp",
    "listing_timestamp",
}
TRUSTED_DATE_TYPES = CONFIRMED_DATE_TYPES | PROBABLE_DATE_TYPES
UNTRUSTED_DATE_TYPES = {
    "discovery_timestamp",
    "missing",
    "unverified",
    "unverified_stale_risk",
}

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

_STATUS_ORDER = {"CONFIRMADO": 0, "PROBABLE": 1, "CANDIDATO": 2, "EXCLUIDO": 3}


@dataclass(frozen=True)
class FreshnessAssessment:
    accepted: bool
    reason: str
    timestamp: datetime | None = None
    trust: str = "missing"
    source: str = ""
    status: str = "EXCLUIDO"
    publisher: str = ""


@dataclass(frozen=True)
class FreshnessDecision:
    status: str
    reason: str
    timestamp: datetime | None = None
    trust: str = "missing"
    source: str = ""
    publisher: str = ""

    @property
    def accepted(self) -> bool:
        return self.status in {"CONFIRMADO", "PROBABLE"}


def is_stale_risk_title(title: str) -> bool:
    text = normalize_text(title)
    if any(pattern in text for pattern in STALE_RISK_PATTERNS):
        return True
    return bool(re.search(r"\b(?:hace|a)\s+\d{1,3}\s+dias?\b", text))


def _trust_from(item: dict) -> str:
    return str(
        item.get("date_trust")
        or item.get("DateTrust")
        or item.get("freshness_trust")
        or "missing"
    ).strip().lower()


def _publisher(item: dict) -> str:
    return str(item.get("publisher") or item.get("source_name") or item.get("fuente") or "").strip()


def _date_candidates(item: dict) -> list[tuple[str, datetime]]:
    values: list[tuple[str, datetime]] = []
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
            values.append(("publicacion", value))
            break
    for key in (
        "article_updated_at",
        "fecha_actualizacion",
        "updated_at",
        "FechaActualizacion",
        "actualizado",
    ):
        value = parse_datetime(item.get(key))
        if value:
            values.append(("actualizacion", value))
            break
    return values


def classify_item(item: dict, title: str, start: datetime, now: datetime) -> FreshnessDecision:
    explicit = explicit_date_in_text(title, now)
    if explicit is not None and explicit.date() < start.date():
        return FreshnessDecision("EXCLUIDO", "FECHA_EXPLICITA_ANTERIOR", explicit, "explicit_title", "title", _publisher(item))

    trust = _trust_from(item)
    dates = _date_candidates(item)
    publisher = _publisher(item)
    if not dates:
        return FreshnessDecision("CANDIDATO", "SIN_FECHA_VERIFICABLE", None, trust, "", publisher)

    # La actualizacion tiene prioridad si es posterior: permite detectar una nota
    # vieja que incorporo informacion nueva durante el corte.
    source, timestamp = max(dates, key=lambda pair: pair[1])
    if timestamp > now + timedelta(minutes=15):
        return FreshnessDecision("EXCLUIDO", "FECHA_FUTURA_INCONSISTENTE", timestamp, trust, source, publisher)

    normalized = normalize_text(title)
    stale_risk = is_stale_risk_title(title)
    has_fresh_hook = any(hook in normalized for hook in FRESH_HOOK_PATTERNS)
    if stale_risk and not has_fresh_hook:
        if trust not in CONFIRMED_DATE_TYPES:
            return FreshnessDecision("CANDIDATO", "TEMA_DE_ARCHIVO_REQUIERE_VERIFICACION", timestamp, trust, source, publisher)
        # Incluso con metadata de articulo, si el titulo es un simple archivo o
        # efemeride no se mezcla con el resumen operativo.
        return FreshnessDecision("EXCLUIDO", "CONTENIDO_HISTORICO_SIN_NOVEDAD", timestamp, trust, source, publisher)

    if timestamp < start:
        return FreshnessDecision("EXCLUIDO", "FUERA_DE_VENTANA", timestamp, trust, source, publisher)

    if trust in CONFIRMED_DATE_TYPES:
        reason = "ACTUALIZADA_EN_VENTANA" if source == "actualizacion" else "FECHA_DE_ARTICULO_EN_VENTANA"
        return FreshnessDecision("CONFIRMADO", reason, timestamp, trust, source, publisher)
    if trust in PROBABLE_DATE_TYPES:
        reason = "ACTUALIZACION_INFORMADA_POR_PUBLISHER" if source == "actualizacion" else "FECHA_INFORMADA_POR_FEED_DIRECTO"
        return FreshnessDecision("PROBABLE", reason, timestamp, trust, source, publisher)
    if trust in UNTRUSTED_DATE_TYPES:
        return FreshnessDecision("CANDIDATO", "FECHA_DE_DESCUBRIMIENTO_NO_VALIDA", timestamp, trust, source, publisher)
    # Un tipo desconocido con fecha directa no se descarta: queda como probable y
    # visible en auditoria para que pueda corregirse la fuente.
    return FreshnessDecision("PROBABLE", "TIPO_DE_FECHA_NO_CLASIFICADO", timestamp, trust, source, publisher)


def classify_evidence(evidence: Iterable[dict], title: str, start: datetime,
                      now: datetime) -> FreshnessDecision:
    decisions = [classify_item(item, title, start, now) for item in evidence]
    if not decisions:
        return FreshnessDecision("CANDIDATO", "SIN_EVIDENCIA_FECHADA")
    decisions.sort(key=lambda item: (
        _STATUS_ORDER.get(item.status, 9),
        -(item.timestamp.timestamp() if item.timestamp else 0),
    ))
    return decisions[0]


def assess_item(item: dict, title: str, start: datetime, now: datetime) -> FreshnessAssessment:
    decision = classify_item(item, title, start, now)
    return FreshnessAssessment(
        decision.accepted, decision.reason, decision.timestamp, decision.trust,
        decision.source, decision.status, decision.publisher,
    )


def assess_evidence(evidence: Iterable[dict], title: str, start: datetime,
                    now: datetime) -> FreshnessAssessment:
    decision = classify_evidence(evidence, title, start, now)
    return FreshnessAssessment(
        decision.accepted, decision.reason, decision.timestamp, decision.trust,
        decision.source, decision.status, decision.publisher,
    )


def confidence_from_evidence(items: list[dict]) -> tuple[int, str]:
    if not items:
        return 20, "No hay evidencia directa suficiente."
    publishers = {
        normalize_text(str(item.get("publisher") or item.get("source_name") or ""))
        for item in items
        if item.get("publisher") or item.get("source_name")
    }
    verified = sum(1 for item in items if _trust_from(item) in CONFIRMED_DATE_TYPES)
    probable = sum(1 for item in items if _trust_from(item) in PROBABLE_DATE_TYPES)
    official = sum(
        1 for item in items
        if any(term in normalize_text(str(item.get("source_id") or item.get("publisher") or ""))
               for term in ("fifa", "uefa", "conmebol", "club", "oficial", "federacion", "liga"))
    )
    score = 28 + min(24, len(publishers) * 8) + min(28, verified * 9) + min(12, probable * 4) + min(18, official * 9)
    score = max(0, min(100, score))
    parts = []
    if official:
        parts.append(f"{official} fuente(s) oficial(es)")
    if len(publishers) > 1:
        parts.append(f"{len(publishers)} publishers originales")
    if verified:
        parts.append(f"{verified} fecha(s) de articulo verificadas")
    elif probable:
        parts.append(f"{probable} fecha(s) de feed directo")
    return score, ", ".join(parts) if parts else "Una fuente directa con fecha probable."
