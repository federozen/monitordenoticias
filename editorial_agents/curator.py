from __future__ import annotations

import os
from datetime import datetime, timezone

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


def _parse_date(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _freshness(details: list[dict], max_age_hours: int) -> dict:
    dates = [dt for dt in (_parse_date(d.get("published_at", "")) for d in details) if dt]
    if not dates:
        return {"has_dates": False, "is_recent": False, "latest": "", "age_hours": None, "dated_count": 0}
    latest = max(dates)
    age_hours = max(0.0, (datetime.now(timezone.utc) - latest).total_seconds() / 3600)
    return {
        "has_dates": True,
        "is_recent": age_hours <= max_age_hours,
        "latest": latest.isoformat(),
        "age_hours": age_hours,
        "dated_count": len(dates),
    }


def _action(theme: dict, agenda_item: dict, official_count: int, rumor: bool, freshness: dict) -> str:
    coverage = str(theme.get("coverage_status") or ("CUBIERTO_IGUAL" if theme.get("tiene_ole") else "NO_CUBIERTO"))
    media = int(theme.get("cant_medios") or 0)
    delta = int(agenda_item.get("delta") or 0)
    is_new = bool(agenda_item.get("nuevo"))
    changed = is_new or delta > 0

    if freshness["has_dates"] and not freshness["is_recent"]:
        return "OBSERVAR"
    if not freshness["has_dates"]:
        return "VERIFICAR" if rumor and official_count == 0 else "OBSERVAR"

    # The operational radar is about gaps and updates, not relevance alone.
    if coverage == "CUBIERTO_IGUAL":
        return "OBSERVAR"
    if coverage == "CUBIERTO_CON_NOVEDAD":
        return "ACTUALIZAR"
    if coverage == "COINCIDENCIA_DUDOSA":
        return "VERIFICAR"
    if rumor and official_count == 0:
        return "VERIFICAR"
    if coverage == "NO_CUBIERTO" and (official_count > 0 or media >= 2):
        return "PUBLICAR AHORA"
    if coverage == "NO_CUBIERTO" and changed:
        return "VERIFICAR"
    return "OBSERVAR"


def curate(themes: list[dict], agenda: list[dict], config: dict | None = None) -> list[dict]:
    config = config or {}
    lookup = _agenda_lookup(agenda)
    recommendations: list[dict] = []
    max_age_hours = int(config.get("max_age_hours") or os.environ.get("MAX_ANTIGUEDAD_HORAS", "4") or 4)

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
        delta = int(agenda_item.get("delta") or 0)
        is_new = bool(agenda_item.get("nuevo"))
        fresh = _freshness(details, max_age_hours)
        coverage = str(theme.get("coverage_status") or ("CUBIERTO_IGUAL" if theme.get("tiene_ole") else "NO_CUBIERTO"))
        action = _action(theme, agenda_item, len(official), rumor, fresh)

        confidence = 28 + min(media, 5) * 9 + (18 if official else 0)
        confidence += 8 if fresh["has_dates"] else -18
        confidence -= 20 if rumor and not official else 0
        confidence -= 12 if coverage == "COINCIDENCIA_DUDOSA" else 0
        confidence = clamp(confidence)

        priority = 18 + min(media, 5) * 6 + max(delta, 0) * 7
        priority += 24 if coverage == "NO_CUBIERTO" else 0
        priority += 20 if coverage == "CUBIERTO_CON_NOVEDAD" else 0
        priority += 10 if official else 0
        priority += 8 if urgent_word else 0
        priority += 5 if is_new else 0
        if action == "OBSERVAR":
            priority = min(priority, 49)
        if not fresh["has_dates"]:
            priority = min(priority, 45)
        elif not fresh["is_recent"]:
            priority = min(priority, 25)
        priority = clamp(priority)

        reasons: list[str] = []
        if coverage == "NO_CUBIERTO":
            reasons.append("no se encontro una nota equivalente en Ole")
        elif coverage == "CUBIERTO_CON_NOVEDAD":
            details_new = ", ".join(theme.get("new_detail_tokens", [])[:5])
            reasons.append("Ole tiene el tema, pero aparecio un dato potencialmente nuevo" + (f": {details_new}" if details_new else ""))
        elif coverage == "COINCIDENCIA_DUDOSA":
            reasons.append("hay una coincidencia parcial con una nota de Ole y requiere revision humana")
        else:
            reasons.append("Ole ya tiene una cobertura equivalente sin novedad detectada")
        if media:
            reasons.append(f"{media} publishers originales")
        if official:
            reasons.append("hay una fuente primaria u oficial")
        if delta > 0:
            reasons.append(f"sumo {delta} publishers desde el corte anterior")
        if fresh["has_dates"]:
            reasons.append(f"ultima publicacion fechada hace {fresh['age_hours']:.1f} horas")
        else:
            reasons.append("sin fecha verificable")
        if rumor and not official:
            reasons.append("conserva lenguaje de version o negociacion")

        if not fresh["has_dates"]:
            state = "FECHA NO VERIFICADA"
        elif not fresh["is_recent"]:
            state = "FUERA DE VENTANA"
        elif coverage == "CUBIERTO_IGUAL":
            state = "YA CUBIERTO"
        elif rumor and not official:
            state = "REQUIERE VERIFICACION"
        else:
            state = "NOVEDAD OPERATIVA"

        recommendations.append({
            "recommendation_id": stable_id(f"{cluster_key}|{action}|{coverage}", "r"),
            "cluster_id": cluster_key,
            "position": position,
            "radar": "OPERATIVO LOCAL",
            "title": title,
            "url": theme.get("url") or "",
            "action": action,
            "state": state,
            "coverage_status": coverage,
            "ole_match_title": theme.get("ole_match_title", ""),
            "ole_match_url": theme.get("ole_match_url", ""),
            "ole_match_score": theme.get("ole_match_score", 0),
            "priority": priority,
            "confidence": confidence,
            "media_count": media,
            "publishers": publishers,
            "has_ole": coverage != "NO_CUBIERTO",
            "momentum": delta,
            "is_new": is_new,
            "official_count": len(official),
            "reason": ". ".join(unique_strings(reasons)),
            "evidence": details[:12],
            "notify": action in {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR"} and priority >= 65 and fresh["is_recent"],
        })

    recommendations.sort(key=lambda item: (-item["priority"], -item["confidence"], item["position"]))
    return recommendations
