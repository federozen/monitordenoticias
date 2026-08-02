from __future__ import annotations

from typing import Any


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def build_source_editor_view(source_health: list[dict]) -> list[dict]:
    """Translate technical collector states into an editor-friendly recovery view."""
    rows: list[dict] = []
    for source in source_health or []:
        name = str(source.get("nombre") or source.get("Fuente") or source.get("id") or "Fuente")
        state = str(source.get("estado") or source.get("Estado") or "").lower()
        error = str(source.get("error") or source.get("Error") or "").strip()
        channel = str(source.get("canal") or source.get("Canal") or "")
        count = _int(source.get("noticias") or source.get("Noticias") or 0)
        if state == "ok" and count > 0:
            editorial_state = "SALUDABLE"
            problem = ""
            next_step = "Sin accion"
        elif "gnews" in channel.lower() and count > 0:
            editorial_state = "DEGRADADA / RESPALDO ACTIVO"
            problem = error or "La via principal no respondio; se usa Google News por dominio."
            next_step = "Mantener respaldo y revisar la fuente directa"
        elif "timeout" in error.lower() or "timed out" in error.lower():
            editorial_state = "DEMORADA"
            problem = "La fuente excedio el tiempo de respuesta."
            next_step = "Reintentar; usar Google News por dominio como respaldo"
        elif "403" in error or "401" in error or "bloq" in error.lower():
            editorial_state = "BLOQUEADA"
            problem = error or "La fuente rechazo el acceso automatico."
            next_step = "Usar RSS, sitemap o Google News por dominio"
        elif "rss" in error.lower() or "0 notas" in error.lower() or count == 0:
            editorial_state = "SIN CONTENIDO"
            problem = error or "No se encontraron publicaciones en este corte."
            next_step = "Revisar RSS alternativo, sitemap o fuente sustituta"
        else:
            editorial_state = "REQUIERE REVISION"
            problem = error or "No se pudo recuperar contenido."
            next_step = "Probar respaldo y decidir reemplazo tras tres fallos"
        rows.append({
            "source_id": str(source.get("id") or source.get("FuenteID") or ""),
            "source": name,
            "zone": str(source.get("zona") or source.get("Zona") or ""),
            "active_method": channel,
            "editorial_state": editorial_state,
            "items": count,
            "last_content": str(source.get("ultimo_contenido") or source.get("UltimoContenido") or ""),
            "problem": problem[:500],
            "fallback": next_step,
        })
    order = {"BLOQUEADA": 0, "REQUIERE REVISION": 1, "DEMORADA": 2, "SIN CONTENIDO": 3, "DEGRADADA / RESPALDO ACTIVO": 4, "SALUDABLE": 5}
    rows.sort(key=lambda row: (order.get(row["editorial_state"], 9), row["source"].lower()))
    return rows
