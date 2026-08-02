from __future__ import annotations

from .utils import stable_id


def generate(recommendations: list[dict], discoveries: list[dict], max_items: int = 6) -> list[dict]:
    """Create genuinely derivative ideas.

    Priority is given to international/rare discoveries. Local topics only become
    opportunities when the recommended action is UPDATE and the angle adds value
    beyond repeating the breaking-news headline.
    """
    opportunities: list[dict] = []

    for item in discoveries:
        if item.get("status") not in {"HALLAZGO FUERTE", "HALLAZGO"}:
            continue
        category = item.get("category", "HISTORIA RARA")
        angle = item.get("suggested_angle", "Encontrar el giro narrativo y explicar por que importa.")
        fmt = item.get("suggested_format", "HISTORIA")
        opportunities.append({
            "opportunity_id": stable_id(f"{item.get('discovery_id')}|{angle}", "o"),
            "radar": "DESCUBRIMIENTO",
            "title": f"{category.title()}: {item.get('title','')}",
            "source_title": item.get("title", ""),
            "cluster_ids": [item.get("discovery_id", "")],
            "format": fmt,
            "angle": angle,
            "why_now": item.get("reason", ""),
            "suggested_headline": _headline(category, item.get("title", "")),
            "effort": "BAJO" if fmt in {"NOTA BREVE + VIDEO", "DATOS / COMPARATIVA"} else "MEDIO",
            "expiry": "PROXIMAS HORAS" if item.get("age_hours") is None or item.get("age_hours", 99) <= 4 else "HOY",
            "score": item.get("score", 0),
        })
        if len(opportunities) >= max_items:
            break

    if len(opportunities) < max_items:
        for rec in recommendations:
            if rec.get("action") != "ACTUALIZAR" or rec.get("priority", 0) < 62:
                continue
            angle = "Explicar la consecuencia concreta del dato nuevo y como cambia el panorama respecto de la nota ya publicada."
            opportunities.append({
                "opportunity_id": stable_id(f"{rec.get('cluster_id')}|actualizacion-derivada", "o"),
                "radar": "OPERATIVO LOCAL",
                "title": f"DERIVADA: que cambia despues de {rec.get('title','')}",
                "source_title": rec.get("title", ""),
                "cluster_ids": [rec.get("cluster_id", "")],
                "format": "EXPLICADOR / CONSECUENCIA",
                "angle": angle,
                "why_now": rec.get("reason", ""),
                "suggested_headline": f"Que cambia ahora: las consecuencias de {rec.get('title','')[:100]}",
                "effort": "MEDIO",
                "expiry": "PROXIMAS HORAS",
                "score": min(100, int(rec.get("priority", 0)) + 4),
            })
            if len(opportunities) >= max_items:
                break

    opportunities.sort(key=lambda item: -int(item.get("score", 0)))
    return opportunities[:max_items]


def _headline(category: str, title: str) -> str:
    cleaned = title.strip().rstrip(".")
    if category == "CONEXION ARGENTINA":
        return f"La historia del exterior que mira Argentina: {cleaned}"
    if category == "OPORTUNIDAD VISUAL":
        return f"El video que sorprende al deporte: {cleaned}"
    if category == "DATO O RECORD":
        return f"El dato que rompe la logica: {cleaned}"
    return f"La historia inesperada detras de {cleaned}"
