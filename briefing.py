from __future__ import annotations

from datetime import datetime
from typing import Any

from .utils import normalize_text, stable_id, unique_strings, now_ar


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"si", "sí", "true", "1", "yes"}


def _title(row: dict) -> str:
    return str(row.get("titulo") or row.get("Titulo") or "").strip()


def _url(row: dict) -> str:
    return str(row.get("url") or row.get("URL") or "").strip()


def _media(row: dict) -> int:
    return _int(row.get("cant_medios") or row.get("Medios") or 0)


def _cluster_id(row: dict) -> str:
    existing = str(row.get("cluster_id") or row.get("ClusterID") or "").strip()
    if existing:
        return existing
    title = _title(row)
    try:
        from monitor_core import normalizar_titulo
        base = " ".join(sorted(normalizar_titulo(title))) or title
    except Exception:
        base = " ".join(sorted(normalize_text(title).split())) or title
    return stable_id(base, "c")


def _has_ole(row: dict) -> bool:
    if "tiene_ole" in row:
        return bool(row.get("tiene_ole"))
    return _bool(row.get("TieneOle"))


def _momentum(row: dict) -> int:
    return _int(row.get("momentum") or row.get("Momentum") or 0)


def _action(row: dict) -> str:
    return str(row.get("accion") or row.get("Accion") or "OBSERVAR").strip().upper()


def _source_titles(row: dict) -> list[str]:
    raw = row.get("fuentes") or row.get("Fuentes") or []
    if not isinstance(raw, list):
        return []
    titles = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("titulo") or item.get("title") or "").strip()
        if title:
            titles.append(title)
    return unique_strings(titles)



def _similarity(a: str, b: str) -> float:
    ta = {x for x in normalize_text(a).split() if len(x) >= 3}
    tb = {x for x in normalize_text(b).split() if len(x) >= 3}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _best_previous(row: dict, previous: dict[str, dict], used: set[str]) -> tuple[str | None, dict | None]:
    cid = _cluster_id(row)
    if cid in previous and cid not in used:
        return cid, previous[cid]
    best_id = None
    best_row = None
    best_score = 0.0
    for prev_id, prev_row in previous.items():
        if prev_id in used:
            continue
        score = _similarity(_title(row), _title(prev_row))
        if score > best_score:
            best_id, best_row, best_score = prev_id, prev_row, score
    if best_score >= 0.52:
        return best_id, best_row
    return None, None

def _current_map(themes: list[dict]) -> dict[str, dict]:
    return {_cluster_id(row): row for row in themes or [] if _title(row)}


def _previous_map(themes: list[dict]) -> dict[str, dict]:
    return {_cluster_id(row): row for row in themes or [] if _title(row)}


def _recommendation_by_cluster(recommendations: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for rec in recommendations or []:
        cid = str(rec.get("cluster_id") or rec.get("ClusterID") or "").strip()
        if cid:
            result[cid] = rec
    return result


def _delta_description(current: dict, previous: dict | None, rec: dict | None) -> tuple[str, str, int]:
    current_media = _media(current)
    current_ole = _has_ole(current)
    current_action = str((rec or {}).get("action") or _action(current)).upper()
    current_momentum = _momentum(current)

    if previous is None:
        if current_ole:
            return "NUEVO EN EL CORTE", "Aparecio por primera vez en el panorama, pero Ole ya tiene cobertura equivalente.", 40
        return "NUEVO SIN CUBRIR", "Aparecio por primera vez en el panorama y no se detecto una cobertura equivalente en Ole.", 82

    prev_media = _media(previous)
    prev_ole = _has_ole(previous)
    prev_action = _action(previous)
    deltas: list[str] = []
    priority = 35
    change_type = "CAMBIO MENOR"

    if current_media > prev_media:
        diff = current_media - prev_media
        deltas.append(f"paso de {prev_media} a {current_media} publishers (+{diff})")
        priority += min(30, diff * 8)
        change_type = "TEMA EN CRECIMIENTO"
    if not prev_ole and current_ole:
        deltas.append("Ole publico o incorporo una cobertura equivalente")
        priority += 8
        change_type = "YA CUBIERTO"
    elif prev_ole and not current_ole:
        deltas.append("dejo de encontrarse la coincidencia previa con Ole; requiere revision")
        priority += 12
        change_type = "REVISAR COBERTURA"
    if current_action != prev_action:
        deltas.append(f"la accion sugerida cambio de {prev_action} a {current_action}")
        priority += 12
        change_type = "CAMBIO DE ACCION"
    if current_momentum > _momentum(previous):
        deltas.append(f"aumento el momentum a {current_momentum}")
        priority += 8

    current_titles = set(normalize_text(x) for x in _source_titles(current))
    previous_titles = set(normalize_text(x) for x in _source_titles(previous))
    new_titles = [x for x in current_titles - previous_titles if x]
    if new_titles:
        deltas.append(f"sumo {len(new_titles)} titular(es) distinto(s) respecto del corte anterior")
        priority += min(18, len(new_titles) * 5)
        if change_type == "CAMBIO MENOR":
            change_type = "NUEVA INFORMACION"

    if not deltas:
        return "SIN CAMBIO", "No cambio de forma relevante respecto del corte anterior.", 0

    if current_action == "ACTUALIZAR":
        change_type = "ACTUALIZAR NOTA"
        priority = max(priority, 78)
    elif current_action == "VERIFICAR":
        change_type = "VERIFICAR"
        priority = max(priority, 68)
    elif current_action == "PUBLICAR AHORA" and not current_ole:
        change_type = "PUBLICAR"
        priority = max(priority, 82)

    return change_type, "; ".join(deltas) + ".", min(100, priority)


def build_changes(current_themes: list[dict], previous_themes: list[dict],
                  recommendations: list[dict]) -> list[dict]:
    current = _current_map(current_themes)
    previous = _previous_map(previous_themes)
    recs = _recommendation_by_cluster(recommendations)
    changes: list[dict] = []

    used_previous: set[str] = set()
    for cid, row in current.items():
        rec = recs.get(cid)
        prev_id, prev_row = _best_previous(row, previous, used_previous)
        if prev_id:
            used_previous.add(prev_id)
        change_type, detail, priority = _delta_description(row, prev_row, rec)
        if change_type == "SIN CAMBIO":
            continue
        action = str((rec or {}).get("action") or _action(row)).upper()
        coverage = str((rec or {}).get("coverage_status") or ("CUBIERTO_IGUAL" if _has_ole(row) else "NO_CUBIERTO"))
        changes.append({
            "change_id": stable_id(f"{cid}|{change_type}|{detail}", "dlt"),
            "cluster_id": cid,
            "change_type": change_type,
            "priority": priority,
            "action": action,
            "coverage_status": coverage,
            "title": _title(row),
            "url": _url(row),
            "what_changed": detail,
            "media_now": _media(row),
            "media_before": _media(prev_row or {}),
            "has_ole": _has_ole(row),
            "ole_match_title": str((rec or {}).get("ole_match_title") or ""),
            "ole_match_url": str((rec or {}).get("ole_match_url") or ""),
            "reason": str((rec or {}).get("reason") or ""),
        })

    changes.sort(key=lambda item: (-item["priority"], item["title"]))
    return changes


def _short_line(item: dict) -> str:
    return f"- {item.get('title','')} — {item.get('what_changed','')}"


def build_summary(changes: list[dict], discoveries: list[dict], recommendations: list[dict],
                  source_health: list[dict], total_topics: int = 0, now: datetime | None = None) -> dict:
    now = now or now_ar()
    actionable = [
        item for item in changes
        if item.get("action") in {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR"}
        and item.get("priority", 0) >= 60
    ]
    publish = [x for x in actionable if x.get("action") == "PUBLICAR AHORA"][:5]
    update = [x for x in actionable if x.get("action") == "ACTUALIZAR"][:5]
    verify = [x for x in actionable if x.get("action") == "VERIFICAR"][:5]
    growth = [x for x in changes if x.get("change_type") == "TEMA EN CRECIMIENTO"][:5]
    findings = [x for x in discoveries if x.get("status") in {"HALLAZGO FUERTE", "HALLAZGO"}][:8]
    errors = [x for x in source_health or [] if str(x.get("estado", "")).lower() != "ok"]

    stable_count = max(0, total_topics - len(changes))
    sections: list[str] = [
        f"PANORAMA DEL CORTE\n- {total_topics} temas agrupados; {len(changes)} con cambios y {stable_count} sin cambios relevantes."
    ]
    if publish:
        sections.append("PARA EVALUAR AHORA\n" + "\n".join(_short_line(x) for x in publish))
    if update:
        sections.append("QUE CAMBIO PARA AGREGAR\n" + "\n".join(_short_line(x) for x in update))
    if verify:
        sections.append("QUE CONVIENE VERIFICAR\n" + "\n".join(_short_line(x) for x in verify))
    if growth:
        sections.append("TEMAS QUE CRECIERON\n" + "\n".join(_short_line(x) for x in growth))
    if findings:
        sections.append("HALLAZGOS PARA EXPLORAR\n" + "\n".join(
            f"- {x.get('title','')} — {x.get('why_it_matters') or x.get('reason','')}" for x in findings
        ))
    if not sections:
        sections.append("No hubo cambios editoriales fuertes en este corte. El panorama completo sigue disponible para consulta.")
    if errors:
        sections.append(f"SALUD DE FUENTES\n- {len(errors)} fuente(s) tuvieron problemas en este corte.")

    return {
        "created_at": now.isoformat(timespec="seconds"),
        "title": f"Resumen del corte {now.strftime('%H:%M')}",
        "plain_text": "\n\n".join(sections),
        "publish_count": len(publish),
        "update_count": len(update),
        "verify_count": len(verify),
        "growth_count": len(growth),
        "discovery_count": len(findings),
        "source_error_count": len(errors),
        "top_change_ids": [x.get("change_id", "") for x in actionable[:10]],
        "top_discovery_ids": [x.get("discovery_id", "") for x in findings[:10]],
    }


def build(current_themes: list[dict], previous_themes: list[dict], recommendations: list[dict],
          discoveries: list[dict], source_health: list[dict]) -> tuple[list[dict], dict]:
    changes = build_changes(current_themes, previous_themes, recommendations)
    summary = build_summary(changes, discoveries, recommendations, source_health, total_topics=len(current_themes or []))
    return changes, summary
