from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from .utils import (explicit_date_in_text, normalize_text, now_ar, parse_datetime,
                    stable_id, unique_strings)

_GENERIC = {
    "partido", "equipo", "futbol", "club", "jugador", "tecnico", "liga", "copa",
    "torneo", "fecha", "hoy", "manana", "ultimo", "nueva", "nuevo", "tras", "ante",
    "para", "con", "sin", "sobre", "desde", "como", "cuando", "donde", "hora", "tv",
}

_FOCUS_RULES = [
    ("SERVICIO", ("hora", "tv", "donde ver", "agenda", "formaciones", "probable", "fixture")),
    ("ULTIMO MOMENTO", ("confirmo", "oficial", "comunicado", "ultima hora", "baja", "lesion", "sancion")),
    ("MERCADO", ("mercado", "refuerzo", "fichaje", "oferta", "contrato", "pase", "negociacion")),
    ("DECLARACIONES", ("dijo", "hablo", "declaro", "conferencia", "apunto", "respondio", "revelo")),
    ("ANALISIS", ("claves", "por que", "como", "radiografia", "analisis", "explicacion")),
    ("RESULTADO", ("gano", "empato", "perdio", "vencio", "clasifico", "elimino", "campeon", "gol")),
    ("HISTORIA/COLOR", ("historia", "record", "insolito", "viral", "emotivo", "curiosidad")),
]


def _tokens(text: str) -> set[str]:
    return {token for token in normalize_text(text).split() if len(token) >= 3 and token not in _GENERIC}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _infer_focus(title: str) -> str:
    text = normalize_text(title)
    for focus, terms in _FOCUS_RULES:
        if any(term in text for term in terms):
            return focus
    return "INFORMACION"


def _infer_section(url: str, title: str) -> str:
    source = normalize_text(f"{url} {title}")
    rules = [
        ("RIVER", ("/river-plate/", " river ")),
        ("BOCA", ("/boca-juniors/", " boca ")),
        ("SELECCION", ("/seleccion/", "seleccion argentina", "scaloni")),
        ("RACING", ("/racing-club/", " racing ")),
        ("INDEPENDIENTE", ("/independiente/", " independiente ")),
        ("SAN LORENZO", ("/san-lorenzo/", "san lorenzo")),
        ("FUTBOL ARGENTINO", ("/futbol-primera/", "liga profesional", "torneo clausura")),
        ("INTERNACIONAL", ("/internacional/", "/futbol-internacional/", "champions", "premier league")),
        ("SELECCION", ("messi", "di maria", "dibu martinez")),
        ("AUTOS", ("/autos/", "formula 1", "turismo carretera", "colapinto")),
        ("TENIS", ("/tenis/", "atp", "wta", "tenis")),
        ("RUGBY", ("/rugby/", "rugby", "pumas")),
        ("BASQUET", ("/basquet/", "nba", "basquet")),
    ]
    padded = f" {source} "
    for section, terms in rules:
        if any(term in padded for term in terms):
            return section
    return "OTROS"


def _entities(title: str) -> list[str]:
    try:
        from monitor_core import detectar_entidades
        return list(detectar_entidades(title) or [])
    except Exception:
        return []


def _first_seen_map(previous: list[dict] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in previous or []:
        key = str(row.get("URL") or row.get("url") or normalize_text(str(row.get("Titulo") or row.get("title") or ""))).strip()
        first = str(row.get("PrimeraDeteccion") or row.get("first_seen") or "").strip()
        if key and first:
            result[key] = first
    return result




def _belongs_to_today(item: dict, title: str, first_seen_value: str, now: datetime) -> bool:
    """Filtra OLE_HOY con una regla estricta de fecha editorial.

    La fecha de primera detección no prueba que una nota haya sido publicada hoy:
    una portada o Google News puede resucitar una pieza vieja. Solo entran notas
    con publicación o actualización fechada en el día actual.
    """
    published = parse_datetime(item.get("fecha_publicacion") or item.get("fecha"))
    updated = parse_datetime(item.get("fecha_actualizacion") or item.get("actualizado"))
    explicit = explicit_date_in_text(title, now)
    origin = str(item.get("ole_origin") or item.get("origen_ole") or "").lower()

    # Una fecha escrita en el título manda sobre cualquier hora de descubrimiento.
    if explicit is not None and explicit.date() != now.date():
        return False

    # Google News se conserva para comparar cobertura, pero su hora es una hora
    # de descubrimiento/indexación y no alcanza para afirmar que Olé publicó hoy.
    if origin == "gnews":
        return False

    if published is not None and published.date() == now.date():
        return True
    if updated is not None and updated.date() == now.date():
        return True
    return False


def build_ole_today(ole_items: list[dict] | None, previous: list[dict] | None = None,
                    recommendations: list[dict] | None = None,
                    now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Build a readable memory of what Ole has published and a grouped coverage map.

    This is intentionally rules-based: it does not call AI and can run every collection cycle.
    """
    now = now or now_ar()
    now_iso = now.isoformat(timespec="seconds")
    first_seen = _first_seen_map(previous)
    recommendation_by_ole_url: dict[str, list[dict]] = defaultdict(list)
    recommendation_by_ole_title: list[dict] = []
    for rec in recommendations or []:
        url = str(rec.get("ole_match_url") or "").strip()
        if url:
            recommendation_by_ole_url[url].append(rec)
        if rec.get("ole_match_title"):
            recommendation_by_ole_title.append(rec)

    entries: list[dict] = []
    seen: set[str] = set()
    seen_titles: set[str] = set()
    for item in ole_items or []:
        title = str(item.get("titulo") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if len(title) < 8:
            continue
        normalized_title = normalize_text(title)
        key = url or normalized_title
        if not key or key in seen:
            continue
        # Google News puede devolver la misma nota con una URL de redirección.
        # Un título exactamente igual no debe contarse como una segunda pieza.
        if normalized_title and normalized_title in seen_titles:
            continue
        first_seen_value = first_seen.get(key, now_iso)
        if not _belongs_to_today(item, title, first_seen_value, now):
            continue
        seen.add(key)
        if normalized_title:
            seen_titles.add(normalized_title)
        related = list(recommendation_by_ole_url.get(url, []))
        if not related:
            scored = []
            for rec in recommendation_by_ole_title:
                score = _similarity(title, str(rec.get("ole_match_title") or ""))
                if score >= 0.45:
                    scored.append((score, rec))
            related = [x[1] for x in sorted(scored, key=lambda pair: pair[0], reverse=True)[:3]]
        actions = unique_strings([str(rec.get("action") or "") for rec in related if rec.get("action")])
        external = unique_strings([str(rec.get("title") or "") for rec in related if rec.get("title")])
        entries.append({
            "ole_id": stable_id(key, "ole"),
            "first_seen": first_seen_value,
            "last_seen": now_iso,
            "published_at": str(item.get("fecha_publicacion") or item.get("fecha") or ""),
            "updated_at": str(item.get("fecha_actualizacion") or item.get("actualizado") or ""),
            "section": _infer_section(url, title),
            "topic_id": "",
            "topic": "",
            "focus": _infer_focus(title),
            "title": title,
            "url": url,
            "entities": _entities(title),
            "related_external": external,
            "suggested_action": " | ".join(actions),
        })

    # Greedy topic grouping. Multiple angles on the same story are shown together.
    groups: list[dict[str, Any]] = []
    for entry in entries:
        best_group = None
        best_score = 0.0
        for group in groups:
            score = max(_similarity(entry["title"], member["title"]) for member in group["members"])
            entity_overlap = bool(set(entry.get("entities") or []) & set(group.get("entities") or []))
            if entity_overlap:
                score += 0.12
            if score > best_score:
                best_score, best_group = score, group
        if best_group is not None and best_score >= 0.42:
            best_group["members"].append(entry)
            best_group["entities"] = unique_strings(best_group["entities"] + entry.get("entities", []))
        else:
            groups.append({"members": [entry], "entities": list(entry.get("entities") or [])})

    coverage_rows: list[dict] = []
    for group in groups:
        members = group["members"]
        representative = max(members, key=lambda item: (len(item.get("related_external") or []), len(item["title"])))
        topic_id = stable_id("|".join(sorted(_tokens(representative["title"]))), "ot")
        topic = representative["title"]
        all_external = unique_strings([x for item in members for x in item.get("related_external", [])])
        actions = unique_strings([item.get("suggested_action", "") for item in members if item.get("suggested_action")])
        for entry in members:
            entry["topic_id"] = topic_id
            entry["topic"] = topic
        def _event_time(item):
            return (parse_datetime(item.get("updated_at"))
                    or parse_datetime(item.get("published_at"))
                    or parse_datetime(item.get("first_seen"))
                    or now)
        latest_member = max(members, key=_event_time)
        coverage_rows.append({
            "topic_id": topic_id,
            "topic": topic,
            "piece_count": len(members),
            "sections": unique_strings([item.get("section", "") for item in members]),
            "focuses": unique_strings([item.get("focus", "") for item in members]),
            "first_seen": min(item.get("first_seen", now_iso) for item in members),
            "last_seen": max(item.get("last_seen", now_iso) for item in members),
            "last_title": latest_member["title"],
            "last_url": latest_member["url"],
            "titles": [item["title"] for item in members],
            "external_updates": all_external,
            "suggested_action": " | ".join(actions) if actions else "YA CUBIERTO / SEGUIR",
            "overcoverage": len(members) >= 5,
        })

    entries.sort(
        key=lambda item: (
            parse_datetime(item.get("updated_at"))
            or parse_datetime(item.get("published_at"))
            or parse_datetime(item.get("first_seen"))
            or now,
            item.get("title", ""),
        ),
        reverse=True,
    )
    coverage_rows.sort(key=lambda item: (-item["piece_count"], item["topic"]))
    return entries, coverage_rows
