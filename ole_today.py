from __future__ import annotations

from datetime import datetime
from typing import Any

from .freshness import TRUSTED_DATE_TYPES
from .utils import normalize_text, now_ar, parse_datetime, stable_id, unique_strings

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
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _infer_focus(title: str) -> str:
    text = normalize_text(title)
    for focus, terms in _FOCUS_RULES:
        if any(term in text for term in terms):
            return focus
    return "INFORMACION"


def _infer_section(url: str, title: str) -> str:
    source = f" {normalize_text(f'{url} {title}')} "
    rules = [
        ("RIVER", ("/river-plate/", " river ")),
        ("BOCA", ("/boca-juniors/", " boca ")),
        ("SELECCION", ("/seleccion/", "seleccion argentina", "scaloni", "messi")),
        ("RACING", ("/racing-club/", " racing ")),
        ("INDEPENDIENTE", ("/independiente/", " independiente ")),
        ("SAN LORENZO", ("/san-lorenzo/", "san lorenzo")),
        ("FUTBOL ARGENTINO", ("/futbol-primera/", "liga profesional", "torneo clausura")),
        ("INTERNACIONAL", ("/internacional/", "/futbol-internacional/", "champions", "premier league")),
        ("AUTOS", ("/autos/", "formula 1", "turismo carretera", "colapinto")),
        ("TENIS", ("/tenis/", "atp", "wta", "tenis")),
        ("RUGBY", ("/rugby/", "rugby", "pumas")),
        ("BASQUET", ("/basquet/", "nba", "basquet")),
    ]
    for section, terms in rules:
        if any(term in source for term in terms):
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


def _classification(item: dict, now: datetime) -> str | None:
    origin = str(item.get("ole_origin") or item.get("origen_ole") or "").lower()
    if origin == "gnews":
        return None
    trust = str(item.get("date_trust") or "publisher_metadata").lower()
    if trust not in TRUSTED_DATE_TYPES:
        return None
    published = parse_datetime(item.get("fecha_publicacion") or item.get("fecha"))
    updated = parse_datetime(item.get("fecha_actualizacion") or item.get("actualizado"))
    if published and published.date() == now.date():
        return "PUBLICADA_HOY"
    if updated and updated.date() == now.date():
        return "ACTUALIZADA_HOY"
    return None


def build_ole_today(ole_items: list[dict] | None, previous: list[dict] | None = None,
                    recommendations: list[dict] | None = None,
                    now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Memoria diaria estricta: solo publicaciones o actualizaciones verificadas de hoy."""
    now = now or now_ar()
    now_iso = now.isoformat(timespec="seconds")
    first_seen = _first_seen_map(previous)
    recs = recommendations or []

    entries: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in ole_items or []:
        title = str(item.get("titulo") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        kind = _classification(item, now)
        if len(title) < 8 or not kind:
            continue
        key = url or normalize_text(title)
        norm_title = normalize_text(title)
        if key in seen_urls or (norm_title and norm_title in seen_titles):
            continue
        seen_urls.add(key)
        seen_titles.add(norm_title)

        related = []
        for rec in recs:
            if url and str(rec.get("ole_match_url") or "") == url:
                related.append(rec)
            elif rec.get("ole_match_title") and _similarity(title, str(rec.get("ole_match_title"))) >= 0.48:
                related.append(rec)
        actions = unique_strings([str(rec.get("action") or "") for rec in related if rec.get("action")])
        external = unique_strings([str(rec.get("title") or "") for rec in related if rec.get("title")])
        entries.append({
            "ole_id": stable_id(key, "ole"),
            "first_seen": first_seen.get(key, now_iso),
            "last_seen": now_iso,
            "publication_type": kind,
            "published_at": str(item.get("fecha_publicacion") or item.get("fecha") or ""),
            "updated_at": str(item.get("fecha_actualizacion") or item.get("actualizado") or ""),
            "date_trust": str(item.get("date_trust") or "publisher_metadata"),
            "page": item.get("ole_page", ""),
            "origin": str(item.get("ole_origin") or "ultimas"),
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

    groups: list[dict[str, Any]] = []
    for entry in entries:
        best_group = None
        best_score = 0.0
        for group in groups:
            score = max(_similarity(entry["title"], member["title"]) for member in group["members"])
            if set(entry.get("entities") or []) & set(group.get("entities") or []):
                score += 0.12
            if score > best_score:
                best_score, best_group = score, group
        if best_group is not None and best_score >= 0.44:
            best_group["members"].append(entry)
            best_group["entities"] = unique_strings(best_group["entities"] + entry.get("entities", []))
        else:
            groups.append({"members": [entry], "entities": list(entry.get("entities") or [])})

    coverage_rows: list[dict] = []
    for group in groups:
        members = group["members"]
        representative = max(members, key=lambda item: (len(item.get("related_external") or []), len(item["title"])))
        topic_id = stable_id("|".join(sorted(_tokens(representative["title"]))), "ot")
        for entry in members:
            entry["topic_id"] = topic_id
            entry["topic"] = representative["title"]
        def event_time(item):
            return parse_datetime(item.get("updated_at")) or parse_datetime(item.get("published_at")) or now
        latest = max(members, key=event_time)
        coverage_rows.append({
            "topic_id": topic_id,
            "topic": representative["title"],
            "piece_count": len(members),
            "published_count": sum(1 for item in members if item["publication_type"] == "PUBLICADA_HOY"),
            "updated_count": sum(1 for item in members if item["publication_type"] == "ACTUALIZADA_HOY"),
            "sections": unique_strings([item["section"] for item in members]),
            "focuses": unique_strings([item["focus"] for item in members]),
            "first_seen": min(item["first_seen"] for item in members),
            "last_seen": max(item["last_seen"] for item in members),
            "last_title": latest["title"],
            "last_url": latest["url"],
            "titles": [item["title"] for item in members],
            "external_updates": unique_strings([x for item in members for x in item.get("related_external", [])]),
            "suggested_action": " | ".join(unique_strings([item["suggested_action"] for item in members if item["suggested_action"]])) or "YA CUBIERTO / SEGUIR",
            "overcoverage": len(members) >= 5,
        })

    entries.sort(key=lambda item: (parse_datetime(item.get("updated_at")) or parse_datetime(item.get("published_at")) or now), reverse=True)
    coverage_rows.sort(key=lambda item: (-item["piece_count"], item["topic"]))
    return entries, coverage_rows
