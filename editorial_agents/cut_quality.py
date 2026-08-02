from __future__ import annotations

import os
from typing import Any

from .utils import normalize_text, stable_id


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).replace(",", "."))
    except Exception:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, str(default)).replace(",", ".")))
    except Exception:
        return default


def assess(source_health: list[dict]) -> dict:
    """Evaluate whether a collection cut is complete enough to replace the last good snapshot.

    The monitor may still produce a useful partial briefing when Google News or several
    sites fail. A degraded cut must not erase the last reliable panorama.
    """
    rows = list(source_health or [])
    total = len(rows)
    ok_rows = [row for row in rows if str(row.get("estado") or row.get("Estado") or "").lower() == "ok" and _int(row.get("noticias") or row.get("Noticias")) > 0]
    ok = len(ok_rows)
    ratio = (ok / total) if total else 0.0

    gnews_rows = [row for row in rows if "google news" in str(row.get("canal") or row.get("Canal") or "").lower()]
    direct_rows = [row for row in rows if row not in gnews_rows]
    gnews_ok = sum(1 for row in gnews_rows if row in ok_rows)
    direct_ok = sum(1 for row in direct_rows if row in ok_rows)

    min_ratio = max(0.1, min(1.0, _float_env("MIN_HEALTHY_SOURCE_RATIO", 0.60)))
    min_sources = max(5, _int_env("MIN_HEALTHY_SOURCES", 35))
    complete = ok >= min_sources and ratio >= min_ratio
    usable = ok >= max(5, min(12, min_sources // 3))

    if complete:
        state = "COMPLETO"
        label = "Cobertura suficiente"
    elif usable:
        state = "DEGRADADO"
        label = "Cobertura parcial: se conserva el ultimo panorama completo"
    else:
        state = "CRITICO"
        label = "Cobertura insuficiente: no se reemplaza el panorama anterior"

    failed_503 = sum(1 for row in rows if "503" in str(row.get("error") or row.get("Error") or ""))
    failed_404 = sum(1 for row in rows if "404" in str(row.get("error") or row.get("Error") or ""))
    empty = sum(1 for row in rows if "vac" in str(row.get("error") or row.get("Error") or "").lower() or "0 notas" in str(row.get("error") or row.get("Error") or "").lower())

    return {
        "state": state,
        "label": label,
        "complete": complete,
        "usable": usable,
        "preserve_previous": not complete,
        "sources_ok": ok,
        "sources_total": total,
        "coverage_ratio": round(ratio, 4),
        "coverage_pct": round(ratio * 100, 1),
        "min_ratio": min_ratio,
        "min_sources": min_sources,
        "gnews_ok": gnews_ok,
        "gnews_total": len(gnews_rows),
        "direct_ok": direct_ok,
        "direct_total": len(direct_rows),
        "errors_503": failed_503,
        "errors_404": failed_404,
        "empty_sources": empty,
    }


def _cluster_id(row: dict) -> str:
    existing = str(row.get("cluster_id") or row.get("ClusterID") or "").strip()
    if existing:
        return existing
    title = str(row.get("titulo") or row.get("Titulo") or "").strip()
    try:
        from monitor_core import normalizar_titulo
        base = " ".join(sorted(normalizar_titulo(title))) or title
    except Exception:
        base = " ".join(sorted(normalize_text(title).split())) or title
    return stable_id(base, "c")


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in {"si", "sí", "true", "1", "yes"}


def _previous_to_theme(row: dict) -> dict:
    evidence = row.get("Fuentes") if isinstance(row.get("Fuentes"), list) else []
    news = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        news.append({
            "noticia": {
                "titulo": item.get("titulo") or item.get("title") or "",
                "url": item.get("url") or "",
                "publisher_original": item.get("fuente") or item.get("publisher") or "",
                "fecha_publicacion": item.get("fecha") or item.get("published_at") or "",
            },
            "fuente": {
                "nombre": item.get("canal") or item.get("fuente") or item.get("publisher") or "",
            },
        })
    publishers = [part.strip() for part in str(row.get("MediosOriginales") or "").split("|") if part.strip()]
    return {
        "cluster_id": _cluster_id(row),
        "titulo": row.get("Titulo") or row.get("titulo") or "",
        "url": row.get("URL") or row.get("url") or "",
        "cant_medios": _int(row.get("Medios") or row.get("cant_medios")),
        "medios_originales": publishers,
        "tiene_ole": _bool(row.get("TieneOle") or row.get("tiene_ole")),
        "nac": _int(row.get("Nacional") or row.get("nac")),
        "intl": _int(row.get("Internacional") or row.get("intl")),
        "noticias": news,
        "_carried_from_previous": True,
    }


def merge_with_previous(current_themes: list[dict], previous_rows: list[dict], max_items: int = 120) -> list[dict]:
    """Keep current themes first and fill missing slots with the last valid panorama.

    This prevents a Google News outage from making topics disappear or look newly absent.
    Carried rows are explicitly marked so the editorial desk can explain their origin.
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for row in current_themes or []:
        item = dict(row)
        cid = _cluster_id(item)
        item["cluster_id"] = cid
        item["_current_cut"] = True
        merged.append(item)
        seen.add(cid)
        if len(merged) >= max_items:
            return merged

    for row in previous_rows or []:
        item = _previous_to_theme(row)
        cid = item["cluster_id"]
        if not item.get("titulo") or cid in seen:
            continue
        merged.append(item)
        seen.add(cid)
        if len(merged) >= max_items:
            break
    return merged
