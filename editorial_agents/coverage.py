from __future__ import annotations

from typing import Any

from .utils import normalize_text, unique_strings

STATUS_WORDS = {
    "confirmado", "oficial", "descartado", "lesion", "lesionado", "baja",
    "suspendido", "sancion", "renuncio", "despedido", "fallecio", "murio",
    "acuerdo", "firmo", "firma", "presentado", "convocado", "titular",
    "diagnostico", "operado", "recuperacion", "fecha", "horario", "sede",
    "resultado", "gol", "clasifico", "eliminado", "campeon", "semanas",
    "meses", "dias", "millones", "euros", "dolares", "contrato", "resciso",
    "operacion", "cirugia", "reemplazo", "suplente", "capitan",
}

GENERIC_WORDS = {
    "partido", "equipo", "futbol", "club", "jugador", "tecnico", "dt",
    "liga", "copa", "torneo", "fecha", "hoy", "manana", "ultimo", "nueva",
    "nuevo", "tras", "ante", "para", "con", "sin", "sobre", "desde",
}


def _tokens(title: str) -> set[str]:
    return {t for t in normalize_text(title).split() if len(t) >= 3}


def _distinctive(title: str) -> set[str]:
    return _tokens(title) - GENERIC_WORDS


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def normalize_ole_items(items: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        title = str(item.get("titulo") or item.get("title") or "").strip()
        if len(title) < 8:
            continue
        key = normalize_text(title)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "title": title,
            "url": str(item.get("url") or ""),
            "published_at": str(item.get("fecha_publicacion") or item.get("fecha") or ""),
        })
    return out


def best_ole_match(title: str, ole_items: list[dict]) -> dict:
    best: dict[str, Any] = {"score": 0.0, "title": "", "url": "", "shared": []}
    source_distinctive = _distinctive(title)
    for item in ole_items:
        candidate = item.get("title", "")
        sim = _similarity(title, candidate)
        shared = sorted(source_distinctive & _distinctive(candidate))
        # Two strong proper/topic tokens are meaningful even when headlines differ.
        entity_bonus = min(0.22, len(shared) * 0.07)
        score = min(1.0, sim + entity_bonus)
        if score > best["score"]:
            best = {
                "score": score,
                "title": candidate,
                "url": item.get("url", ""),
                "shared": shared,
            }
    return best


def _new_detail_tokens(external_titles: list[str], ole_title: str) -> list[str]:
    ole = _distinctive(ole_title)
    candidates: list[str] = []
    for title in external_titles:
        for token in _distinctive(title) - ole:
            if token in STATUS_WORDS or token.isdigit():
                candidates.append(token)
    return unique_strings(candidates)[:8]


def enrich_theme_coverage(theme: dict, ole_items: list[dict]) -> dict:
    enriched = dict(theme)
    source_titles = [
        str((item.get("noticia") or {}).get("titulo") or "")
        for item in theme.get("noticias", []) or []
    ]
    representative = str(theme.get("titulo") or "")
    matches = [best_ole_match(title, ole_items) for title in [representative, *source_titles] if title]
    match = max(matches, key=lambda x: x.get("score", 0), default={"score": 0.0})
    score = float(match.get("score", 0) or 0)
    direct = bool(theme.get("tiene_ole"))

    if direct or score >= 0.62:
        status = "CUBIERTO_IGUAL"
    elif score >= 0.38:
        status = "COINCIDENCIA_DUDOSA"
    else:
        status = "NO_CUBIERTO"

    new_details = _new_detail_tokens(source_titles or [representative], str(match.get("title") or ""))
    if status in {"CUBIERTO_IGUAL", "COINCIDENCIA_DUDOSA"} and new_details:
        # Only call it an update when there is a concrete status/number/detail absent in the Olé headline.
        status = "CUBIERTO_CON_NOVEDAD"

    enriched.update({
        "coverage_status": status,
        "ole_match_score": round(score, 3),
        "ole_match_title": match.get("title", ""),
        "ole_match_url": match.get("url", ""),
        "new_detail_tokens": new_details,
        "tiene_ole": status != "NO_CUBIERTO",
    })
    return enriched


def enrich_themes(themes: list[dict], ole_items: list[dict] | None) -> list[dict]:
    normalized = normalize_ole_items(ole_items)
    return [enrich_theme_coverage(theme, normalized) for theme in themes or []]
