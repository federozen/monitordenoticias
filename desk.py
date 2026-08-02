from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .freshness import assess_evidence
from .utils import normalize_text, now_ar, stable_id, unique_strings

_ACTIONABLE = {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR", "PROFUNDIZAR", "SEGUIR"}
_OTHER_SPORTS = (
    "tenis", "atp", "wta", "rugby", "pumas", "basquet", "nba", "voley", "hockey",
    "automovilismo", "formula 1", "f1", "colapinto", "turismo carretera", "moto", "golf",
)
_ARGENTINA = (
    "argentina", "seleccion", "messi", "scaloni", "di maria", "dibu", "julian alvarez",
    "river", "boca", "racing", "independiente", "san lorenzo", "liga profesional",
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"si", "sí", "true", "1", "yes"}


def _title(row: dict) -> str:
    return str(row.get("title") or row.get("Titulo") or row.get("titulo") or "").strip()


def _url(row: dict) -> str:
    return str(row.get("url") or row.get("URL") or "").strip()


def _cluster(row: dict) -> str:
    return str(row.get("cluster_id") or row.get("ClusterID") or stable_id(normalize_text(_title(row)), "c"))


def _cut_window(now: datetime) -> tuple[datetime, datetime, str]:
    start_hour = (now.hour // 4) * 4
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)
    key = f"{start.strftime('%Y-%m-%dT%H:%M')}_{end.strftime('%H:%M')}"
    return start, end, key


def _category(title: str, row: dict) -> str:
    text = f" {normalize_text(title)} "
    if any(term in text for term in _OTHER_SPORTS):
        return "OTROS DEPORTES"
    if any(term in text for term in _ARGENTINA):
        if "seleccion" in text or "messi" in text or "scaloni" in text or "dibu" in text:
            return "SELECCION / ARGENTINOS"
        return "FUTBOL ARGENTINO"
    national = _int(row.get("nac") or row.get("Nacional") or 0)
    international = _int(row.get("intl") or row.get("Internacional") or 0)
    if international > national:
        return "INTERNACIONAL"
    return "PANORAMA"


def _evidence_from_theme(row: dict) -> list[dict]:
    raw = row.get("fuentes") or row.get("Fuentes") or row.get("noticias") or []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        news = item.get("noticia") if isinstance(item.get("noticia"), dict) else item
        source = item.get("fuente") if isinstance(item.get("fuente"), dict) else {}
        source_id = str(news.get("source_id") or source.get("id") or "")
        discovery_channel = str(news.get("discovery_channel") or "")
        source_url = str(source.get("url") or "")
        date_trust = str(news.get("date_trust") or "")
        if not date_trust:
            is_gnews = (
                discovery_channel.lower() == "google news"
                or "news.google.com" in source_url
                or source_id.startswith("gn_")
            )
            date_trust = "discovery_timestamp" if is_gnews else "publisher_timestamp"
        out.append({
            "publisher": str(news.get("publisher_original") or news.get("fuente") or source.get("nombre") or "Fuente"),
            "title": str(news.get("titulo") or news.get("title") or ""),
            "url": str(news.get("url") or ""),
            "published_at": str(news.get("fecha_publicacion") or news.get("fecha") or ""),
            "article_published_at": str(news.get("article_published_at") or news.get("fecha_publicacion_verificada") or ""),
            "source_id": source_id,
            "discovery_channel": discovery_channel,
            "date_trust": date_trust,
        })
    return out




def _is_in_cut(row: dict, change: dict | None, start: datetime, now: datetime) -> tuple[bool, str]:
    """Acepta solo actividad fechada y verificable dentro del corte.

    `first_seen`, momentum o una hora de Google News no prueban actualidad. Los
    temas de archivo/efemeride requieren metadata de la nota original.
    """
    evidence = _evidence_from_theme(row)
    # Algunas fuentes escriben la fecha a nivel de tema. La convertimos en una
    # evidencia solo si conserva un tipo de confianza explícito.
    if row.get("published_at") or row.get("FechaPublicacion") or row.get("fecha_publicacion"):
        evidence.append({
            "published_at": str(row.get("published_at") or row.get("FechaPublicacion") or row.get("fecha_publicacion") or ""),
            "article_published_at": str(row.get("article_published_at") or row.get("fecha_publicacion_verificada") or ""),
            "date_trust": str(row.get("date_trust") or row.get("DateTrust") or "missing"),
            "publisher": str(row.get("publisher") or "Tema"),
        })
    assessment = assess_evidence(evidence, _title(row), start, now)
    return assessment.accepted, assessment.reason


def _discovery_in_cut(discovery: dict, start: datetime, now: datetime) -> bool:
    assessment = assess_evidence([{
        "published_at": discovery.get("published_at") or discovery.get("FechaPublicacion"),
        "article_published_at": discovery.get("article_published_at") or discovery.get("FechaPublicacionVerificada"),
        "date_trust": discovery.get("date_trust") or discovery.get("DateTrust") or "missing",
        "publisher": discovery.get("publisher") or discovery.get("Publishers") or "",
    }], _title(discovery), start, now)
    return assessment.accepted


def _source_line(evidence: list[dict], max_items: int = 5) -> tuple[str, str]:
    publishers = unique_strings([str(item.get("publisher") or "") for item in evidence if item.get("publisher")])[:max_items]
    urls = unique_strings([str(item.get("url") or "") for item in evidence if item.get("url")])[:max_items]
    return " | ".join(publishers), " | ".join(urls)


def _what_happened(title: str, media: int, evidence: list[dict], status: str = "") -> str:
    if evidence:
        variants = unique_strings([str(item.get("title") or "") for item in evidence if item.get("title") and normalize_text(item.get("title", "")) != normalize_text(title)])
        if variants:
            return f"{title}. Entre las publicaciones relacionadas aparece: {variants[0][:220]}."
    if media > 1:
        return f"{title}. El asunto fue detectado en {media} medios originales durante el corte."
    if status:
        return f"{title}. Estado del radar: {status}."
    return title


def _ole_status(rec: dict | None, row: dict) -> tuple[str, str, str]:
    rec = rec or {}
    status = str(rec.get("coverage_status") or rec.get("CoberturaOle") or "").strip()
    if not status:
        status = "YA CUBIERTO" if _bool(row.get("tiene_ole") or row.get("TieneOle")) else "NO CUBIERTO"
    return status, str(rec.get("ole_match_title") or rec.get("TituloOle") or ""), str(rec.get("ole_match_url") or rec.get("URLOle") or "")


def _action(rec: dict | None, row: dict) -> str:
    action = str((rec or {}).get("action") or (rec or {}).get("Accion") or row.get("accion") or row.get("Accion") or "INFORMARSE").upper()
    if action == "OBSERVAR":
        return "INFORMARSE"
    return action


def _priority(rec: dict | None, row: dict, fallback: int = 30) -> int:
    return max(_int((rec or {}).get("priority") or (rec or {}).get("Prioridad") or 0), _int(row.get("score") or row.get("Score") or row.get("Prioridad") or fallback))


def _candidate_key(title: str) -> set[str]:
    generic = {
        "tema", "deportivo", "partido", "equipo", "futbol", "club", "jugador",
        "nuevo", "nueva", "ultima", "ultimo", "para", "ante", "sobre", "tras",
        "protagonista", "distinto", "noticia", "informacion",
    }
    return {word for word in normalize_text(title).split() if len(word) >= 4 and word not in generic}


def _is_duplicate(title: str, selected: list[dict]) -> bool:
    keys = _candidate_key(title)
    if not keys:
        return False
    for item in selected:
        other = _candidate_key(item.get("topic", ""))
        if other and len(keys & other) / len(keys | other) >= 0.55:
            return True
    return False


def _build_topic(row: dict, rec: dict | None, change: dict | None, order_hint: int = 0) -> dict:
    title = _title(row)
    evidence = _evidence_from_theme(row)
    media = _int(row.get("cant_medios") or row.get("Medios") or (rec or {}).get("media_count") or 0)
    status, ole_title, ole_url = _ole_status(rec, row)
    action = _action(rec, row)
    priority = _priority(rec, row, fallback=max(20, 100 - order_hint))
    sources, source_urls = _source_line(evidence)
    change_text = str((change or {}).get("what_changed") or (change or {}).get("QueCambio") or "").strip()
    if not change_text:
        if row.get("_carried_from_previous"):
            change_text = "Se conserva del ultimo panorama completo; la fuente no estuvo disponible en este corte parcial."
        elif str(row.get("nuevo") or row.get("Nuevo") or "").lower() in {"true", "si", "1"}:
            change_text = "Ingresó en este corte."
        else:
            change_text = "Se mantiene entre los temas relevantes del período."
    why = str((rec or {}).get("reason") or (rec or {}).get("Motivo") or row.get("motivo") or row.get("Motivo") or "").strip()
    return {
        "topic_id": _cluster(row),
        "section": _category(title, row),
        "topic": title,
        "what_happened": _what_happened(title, media, evidence, status),
        "what_changed": change_text,
        "why_it_matters": why,
        "ole_status": status,
        "ole_title": ole_title,
        "ole_url": ole_url,
        "action": action,
        "priority": priority,
        "media_count": media,
        "sources": sources,
        "source_urls": source_urls,
        "url": _url(row),
        "origin": "PANORAMA PREVIO" if row.get("_carried_from_previous") else "PANORAMA",
    }


def build_editorial_desk(themes: list[dict], changes: list[dict], recommendations: list[dict],
                         discoveries: list[dict], source_health: list[dict],
                         social_items: list[dict] | None = None, now: datetime | None = None,
                         min_topics: int = 30, max_topics: int = 40,
                         cut_quality: dict | None = None) -> dict:
    now = now or now_ar()
    start, end, cut_key = _cut_window(now)
    rec_map = {_cluster(rec): rec for rec in recommendations or []}
    change_map = {_cluster(change): change for change in changes or []}
    theme_map = {_cluster(theme): theme for theme in themes or []}
    selected: list[dict] = []

    eligible_theme_ids: set[str] = set()
    exclusion_reasons: dict[str, str] = {}
    for theme in themes or []:
        cid = _cluster(theme)
        eligible, reason = _is_in_cut(theme, change_map.get(cid), start, now)
        if eligible:
            eligible_theme_ids.add(cid)
        else:
            exclusion_reasons[cid] = reason

    # 1. Real changes and actionable items first, but only if the underlying
    # story had activity inside this four-hour window.
    change_order = sorted(
        [item for item in (changes or []) if _cluster(item) in eligible_theme_ids],
        key=lambda item: -_int(item.get("priority") or item.get("Prioridad") or 0),
    )
    for change in change_order:
        cid = _cluster(change)
        row = theme_map.get(cid) or change
        item = _build_topic(row, rec_map.get(cid), change, len(selected))
        if not _is_duplicate(item["topic"], selected):
            selected.append(item)
        if len(selected) >= max_topics:
            break

    # 2. Recommendations that did not produce a delta.
    if len(selected) < max_topics:
        rec_order = sorted(
            [item for item in (recommendations or []) if _cluster(item) in eligible_theme_ids],
            key=lambda item: -_int(item.get("priority") or item.get("Prioridad") or 0),
        )
        for rec in rec_order:
            cid = _cluster(rec)
            row = theme_map.get(cid) or rec
            item = _build_topic(row, rec, change_map.get(cid), len(selected))
            if not _is_duplicate(item["topic"], selected):
                selected.append(item)
            if len(selected) >= max_topics:
                break

    # 3. Discovery candidates: always keep a few so the editor does not need to browse abroad.
    for discovery in discoveries or []:
        if len(selected) >= max_topics:
            break
        status = str(discovery.get("status") or discovery.get("Estado") or "").upper()
        if status not in {"HALLAZGO FUERTE", "HALLAZGO"}:
            continue
        if not _discovery_in_cut(discovery, start, now):
            continue
        title = _title(discovery)
        if not title or _is_duplicate(title, selected):
            continue
        evidence = discovery.get("evidence") or discovery.get("Evidencia") or []
        sources, source_urls = _source_line(evidence if isinstance(evidence, list) else [])
        selected.append({
            "topic_id": str(discovery.get("discovery_id") or discovery.get("DiscoveryID") or stable_id(title, "d")),
            "section": "HALLAZGOS",
            "topic": title,
            "what_happened": str(discovery.get("reason") or discovery.get("Motivo") or title),
            "what_changed": "Detectado por el radar internacional en este corte.",
            "why_it_matters": str(discovery.get("why_it_matters") or discovery.get("PorQueImporta") or ""),
            "ole_status": str(discovery.get("ole_status") or discovery.get("EstadoOle") or "NO CUBIERTO"),
            "ole_title": str(discovery.get("ole_match_title") or discovery.get("TituloOle") or ""),
            "ole_url": str(discovery.get("ole_match_url") or discovery.get("URLOle") or ""),
            "action": "EXPLORAR",
            "priority": _int(discovery.get("score") or discovery.get("Score") or 50),
            "media_count": _int(discovery.get("media_count") or discovery.get("Medios") or 1),
            "sources": sources or str(discovery.get("Publishers") or ""),
            "source_urls": source_urls,
            "url": _url(discovery),
            "origin": "DESCUBRIMIENTO",
            "finding_status": status,
            "finding_category": str(discovery.get("category") or discovery.get("Categoria") or ""),
            "confidence": _int(discovery.get("confidence") or discovery.get("Confianza") or 0),
            "confidence_reason": str(discovery.get("confidence_reason") or discovery.get("MotivoConfianza") or ""),
            "editorial_signal_count": _int(discovery.get("editorial_signal_count") or discovery.get("SenalesEditoriales") or 0),
        })

    # 4. Manually forwarded social links are included as a distinct queue.
    for social in social_items or []:
        if len(selected) >= max_topics:
            break
        status = str(social.get("Estado") or social.get("status") or "PENDIENTE").upper()
        if status in {"HECHO", "DESCARTADO"}:
            continue
        title = str(social.get("Titulo") or social.get("title") or social.get("Nota") or "Enlace social para revisar").strip()
        if _is_duplicate(title, selected):
            continue
        selected.append({
            "topic_id": str(social.get("SocialID") or social.get("social_id") or stable_id(title, "soc")),
            "section": "BUZON SOCIAL",
            "topic": title,
            "what_happened": str(social.get("Nota") or social.get("note") or "Enlace enviado por un editor para incorporar al radar."),
            "what_changed": "Ingreso manual al buzón social.",
            "why_it_matters": str(social.get("PorQue") or social.get("why") or "Requiere verificación y contextualización."),
            "ole_status": "POR COMPARAR",
            "ole_title": "",
            "ole_url": "",
            "action": "VERIFICAR",
            "priority": 65,
            "media_count": 1,
            "sources": str(social.get("Autor") or social.get("author") or social.get("Plataforma") or "Red social"),
            "source_urls": str(social.get("URL") or social.get("url") or ""),
            "url": str(social.get("URL") or social.get("url") or ""),
            "origin": "SOCIAL",
        })


    # 5. Completa solo con temas que pertenecen realmente a la ventana.
    # Si hubo menos de 30 asuntos, se muestran menos: no se rellena con notas
    # viejas para alcanzar una cuota artificial.
    for pos, theme in enumerate(themes or [], start=1):
        if len(selected) >= max_topics:
            break
        if _cluster(theme) not in eligible_theme_ids:
            continue
        title = _title(theme)
        if not title or _is_duplicate(title, selected):
            continue
        selected.append(_build_topic(theme, rec_map.get(_cluster(theme)), change_map.get(_cluster(theme)), pos))

    # Keep the result useful even when the day is quiet; do not pad with empty rows.
    selected = selected[:max_topics]
    for idx, item in enumerate(selected, start=1):
        item["order"] = idx
        item["cut_key"] = cut_key
        item["window_start"] = start.isoformat(timespec="minutes")
        item["window_end"] = end.isoformat(timespec="minutes")
        item["generated_at"] = now.isoformat(timespec="seconds")
        if idx <= 10:
            item["importance"] = "IMPRESCINDIBLE"
        elif item["section"] == "HALLAZGOS":
            item["importance"] = "HALLAZGO"
        else:
            item["importance"] = "PANORAMA"

    actionable = [item for item in selected if item["action"] in _ACTIONABLE and item["action"] != "INFORMARSE"]
    actions = []
    for item in actionable:
        actions.append({
            "action_id": stable_id(f"{item['topic_id']}|{item['action']}|{cut_key}", "act"),
            "cut_key": cut_key,
            "priority": item["priority"],
            "action": item["action"],
            "status": "PENDIENTE",
            "topic_id": item["topic_id"],
            "topic": item["topic"],
            "new_data": item["what_changed"],
            "ole_title": item["ole_title"],
            "ole_url": item["ole_url"],
            "sources": item["sources"],
            "source_urls": item["source_urls"],
            "updated_at": item["generated_at"],
            "notes": "",
        })

    broken = [source for source in source_health or [] if str(source.get("estado") or source.get("Estado") or "").lower() != "ok"]
    meta = {
        "cut_key": cut_key,
        "window_start": start.isoformat(timespec="minutes"),
        "window_end": end.isoformat(timespec="minutes"),
        "generated_at": now.isoformat(timespec="seconds"),
        "topic_count": len(selected),
        "action_count": len(actions),
        "finding_count": sum(1 for item in selected if item["section"] == "HALLAZGOS"),
        "social_count": sum(1 for item in selected if item["section"] == "BUZON SOCIAL"),
        "broken_source_count": len(broken),
        "minimum_target": min_topics,
        "cut_quality": str((cut_quality or {}).get("state") or "COMPLETO"),
        "cut_quality_label": str((cut_quality or {}).get("label") or ""),
        "source_coverage_pct": (cut_quality or {}).get("coverage_pct", 100),
        "snapshot_preserved": bool((cut_quality or {}).get("preserve_previous")),
        "carried_topic_count": sum(1 for item in selected if item.get("origin") == "PANORAMA PREVIO"),
        "excluded_outside_window": len(exclusion_reasons),
        "excluded_unverified_date": sum(
            1 for reason in exclusion_reasons.values()
            if "VERIFIC" in reason or "DESCUBRIMIENTO" in reason
        ),
    }
    return {"topics": selected, "actions": actions, "meta": meta}
