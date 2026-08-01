from __future__ import annotations

from typing import Any

from .utils import clamp, normalize_text, stable_id, unique_strings

OFFICIAL_HINTS = {
    "oficial", "afa", "fifa", "conmebol", "liga profesional", "seleccion argentina",
    "club atletico", "ministerio", "federacion", "asociacion del futbol argentino",
}

RUMOR_HINTS = {
    "podria", "seria", "trascendio", "rumor", "version", "interesa", "sondeo",
    "negocia", "posible", "evalua", "analiza", "habria", "tendria",
}

URGENT_HINTS = {
    "confirmado", "oficial", "ultima hora", "suspendido", "lesion", "baja",
    "murio", "fallecio", "renuncio", "despedido", "sancion", "fallo", "resultado",
}


def _source_details(theme: dict) -> list[dict]:
    details: list[dict] = []
    for item in theme.get("noticias", []) or []:
        news = item.get("noticia", {}) or {}
        source = item.get("fuente", {}) or {}
        details.append({
            "publisher": news.get("publisher_original") or source.get("nombre") or source.get("id") or "Fuente",
            "configured_source": source.get("nombre") or source.get("id") or "",
            "title": news.get("titulo") or "",
            "url": news.get("url") or "",
            "published_at": news.get("fecha_publicacion") or "",
        })
    return details


def _is_official(detail: dict) -> bool:
    text = normalize_text(f"{detail.get('publisher','')} {detail.get('configured_source','')}")
    return any(hint in text for hint in OFFICIAL_HINTS)


def _agenda_lookup(agenda: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in agenda or []:
        key = stable_id(" ".join(sorted(normalize_text(item.get("titulo", "")).split())), "c")
        out[key] = item
    return out


def _action(theme: dict, agenda_item: dict, official_count: int, rumor: bool) -> str:
    action = str(agenda_item.get("accion") or "").upper()
    media = int(theme.get("cant_medios") or 0)
    ole = bool(theme.get("tiene_ole"))
    delta = int(agenda_item.get("delta") or 0)

    if action in {"SUBIR YA", "EXPLOTA"}:
        return "PUBLICAR AHORA" if not ole else "ACTUALIZAR"
    if official_count and not ole:
        return "PUBLICAR AHORA" if media >= 2 else "VERIFICAR"
    if rumor and official_count == 0:
        return "VERIFICAR"
    if ole and delta >= 2:
        return "ACTUALIZAR"
    if not ole and media >= 3:
        return "PUBLICAR AHORA"
    if action == "RETOMAR":
        return "ACTUALIZAR"
    if action in {"REDACTAR", "SEGUIR"}:
        return "SEGUIR"
    return "OBSERVAR"


def curate(themes: list[dict], agenda: list[dict], config: dict | None = None) -> list[dict]:
    config = config or {}
    lookup = _agenda_lookup(agenda)
    recommendations: list[dict] = []

    for position, theme in enumerate(themes or [], start=1):
        title = str(theme.get("titulo") or "").strip()
        if not title:
            continue
        cluster_key = stable_id(" ".join(sorted(normalize_text(title).split())), "c")
        agenda_item = lookup.get(cluster_key, {})
        details = _source_details(theme)
        publishers = unique_strings([d["publisher"] for d in details])
        media = int(theme.get("cant_medios") or len(publishers) or 0)
        official = [d for d in details if _is_official(d)]
        title_norm = normalize_text(title)
        rumor = any(word in title_norm for word in RUMOR_HINTS)
        urgent_word = any(word in title_norm for word in URGENT_HINTS)
        ole = bool(theme.get("tiene_ole"))
        delta = int(agenda_item.get("delta") or 0)
        is_new = bool(agenda_item.get("nuevo"))

        confidence = 25 + min(media, 5) * 10
        confidence += min(len(official), 1) * 20
        confidence += 5 if any(d.get("published_at") for d in details) else 0
        confidence -= 18 if rumor and not official else 0
        confidence -= 8 if media <= 1 else 0
        confidence = clamp(confidence)

        urgency = 15 + min(media, 6) * 8 + max(delta, 0) * 9
        urgency += 18 if not ole else 0
        urgency += 12 if official else 0
        urgency += 10 if urgent_word else 0
        urgency += 5 if is_new else 0
        urgency = clamp(urgency)

        action = _action(theme, agenda_item, len(official), rumor)
        reasons: list[str] = []
        if media:
            reasons.append(f"{media} medios originales")
        if official:
            reasons.append("hay una fuente primaria u oficial")
        if not ole:
            reasons.append("no aparece cubierto por Ole en el panorama")
        if delta > 0:
            reasons.append(f"crecio en {delta} medios desde el corte anterior")
        if rumor and not official:
            reasons.append("la informacion conserva lenguaje de version o negociacion")
        if agenda_item.get("motivo"):
            reasons.append(str(agenda_item["motivo"]))

        state = "CONFIRMADO" if official and confidence >= 70 else (
            "EN DESARROLLO" if media >= 2 else "SEGUIR"
        )
        if rumor and not official:
            state = "REQUIERE VERIFICACION"

        recommendations.append({
            "recommendation_id": stable_id(f"{cluster_key}|{action}", "r"),
            "cluster_id": cluster_key,
            "position": position,
            "title": title,
            "url": theme.get("url") or "",
            "action": action,
            "state": state,
            "priority": urgency,
            "confidence": confidence,
            "media_count": media,
            "publishers": publishers,
            "has_ole": ole,
            "momentum": delta,
            "is_new": is_new,
            "official_count": len(official),
            "reason": ". ".join(unique_strings(reasons)) or "Tema detectado por el monitor",
            "evidence": details[:12],
            "notify": action in {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR"} and urgency >= 60,
        })

    recommendations.sort(key=lambda item: (-item["priority"], -item["confidence"], item["position"]))
    return recommendations
