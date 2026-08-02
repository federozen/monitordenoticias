"""Snapshots online para la version liviana del Monitor Deportivo.

Puede usar la misma planilla del proyecto anterior sin tocar sus pestanas:
por defecto crea pestanas con prefijo ``V9_``. Para usar una planilla nueva,
basta con cambiar SHEET_ID. Para cambiar el prefijo, usar SHEET_PREFIX.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

try:
    import gspread
except Exception:  # pragma: no cover
    gspread = None

_TZ_AR = timezone(timedelta(hours=-3))
_CONF = {"json": None, "sheet_id": None, "prefix": None}
_CACHE = {"sheet": None, "worksheets": None, "records": {}}

NOTICIAS_HEADERS = [
    "RunTS", "NoticiaID", "FuenteID", "FuenteConfigurada", "PublisherOriginal",
    "CanalDescubrimiento", "Titulo", "URL", "Imagen", "FechaPublicacion", "Zona",
]
TEMAS_HEADERS = [
    "RunTS", "ClusterID", "Prioridad", "Accion", "Titulo", "URL", "Medios",
    "MediosOriginales", "TieneOle", "Nacional", "Internacional", "Momentum",
    "Nuevo", "Motivo", "Score", "FuentesJSON",
]
FUENTES_HEADERS = [
    "RunTS", "FuenteID", "Fuente", "Zona", "Canal", "Estado", "Noticias",
    "DuracionSeg", "Error", "UltimoContenido",
]
CONTROL_HEADERS = ["Clave", "Valor", "Actualizado"]
FEEDBACK_HEADERS = [
    "Fecha", "Hora", "ClusterID", "Titulo", "AccionSugerida", "AccionEditor",
    "Util", "TerminoEnNota", "Comentario",
]
RECOMENDACIONES_HEADERS = [
    "RunTS", "RecommendationID", "ClusterID", "Radar", "Prioridad", "Confianza", "Estado",
    "Accion", "CoberturaOle", "TituloOle", "URLOle", "Titulo", "URL", "Medios",
    "Publishers", "TieneOle", "Momentum", "EsNuevo", "FuentesOficiales", "Motivo", "EvidenciaJSON",
]
DESCUBRIMIENTOS_HEADERS = [
    "RunTS", "DiscoveryID", "Categoria", "Estado", "Score", "ValorArgentina", "Titulo", "URL",
    "Publishers", "Medios", "FechaPublicacion", "AntiguedadHoras", "EsNuevo",
    "EstadoOle", "TituloOle", "URLOle", "Motivo", "PorQueImporta", "Angulo", "Formato", "EvidenciaJSON",
]
CAMBIOS_HEADERS = [
    "RunTS", "ChangeID", "ClusterID", "TipoCambio", "Prioridad", "Accion",
    "CoberturaOle", "Titulo", "URL", "QueCambio", "MediosAhora", "MediosAntes",
    "TieneOle", "TituloOle", "URLOle", "Motivo",
]
RESUMEN_HEADERS = [
    "RunTS", "Titulo", "Texto", "ParaEvaluar", "ParaActualizar", "ParaVerificar",
    "EnCrecimiento", "Hallazgos", "ErroresFuentes", "ChangeIDs", "DiscoveryIDs",
]
OPORTUNIDADES_HEADERS = [
    "RunTS", "OpportunityID", "Score", "Formato", "Titulo", "TemaOrigen",
    "Angulo", "PorQueAhora", "TituloSugerido", "Esfuerzo", "Vigencia", "ClustersJSON",
]
INFORMES_HEADERS = [
    "FechaHora", "Tipo", "Titulo", "Texto", "RecommendationIDs", "OpportunityIDs",
    "ErroresFuentes",
]
AVISOS_HEADERS = ["FechaHora", "Clave", "Tipo", "Titulo"]

RESUMEN_4H_HEADERS = [
    "Corte", "Desde", "Hasta", "Orden", "Importancia", "Seccion", "Tema",
    "QuePaso", "QueCambio", "PorQueImporta", "EstadoOle", "NotaOle", "URLOle",
    "Accion", "Prioridad", "Medios", "Fuentes", "URLsFuentes", "URLPrincipal", "Generado"
]
HISTORIAL_4H_HEADERS = RESUMEN_4H_HEADERS
ACCIONES_EDITOR_HEADERS = [
    "ActionID", "Corte", "Prioridad", "Accion", "Estado", "TemaID", "Tema",
    "DatoNuevo", "NotaOle", "URLOle", "Fuentes", "URLsFuentes", "Actualizado", "Notas"
]
OLE_HOY_HEADERS = [
    "OleID", "PrimeraDeteccion", "UltimaDeteccion", "FechaPublicacion", "FechaActualizacion",
    "Seccion", "TemaID", "TemaAgrupado", "Enfoque", "Titulo", "URL", "Entidades",
    "NovedadesExternas", "AccionSugerida"
]
COBERTURA_OLE_EDITOR_HEADERS = [
    "TemaID", "Tema", "Piezas", "Secciones", "Enfoques", "PrimeraDeteccion",
    "UltimaDeteccion", "UltimoTitulo", "UltimaURL", "TitulosPublicados",
    "NovedadesExternas", "Accion", "Sobrecobertura"
]
HALLAZGOS_EDITOR_HEADERS = [
    "Corte", "Prioridad", "Tema", "QuePaso", "PorQueImporta", "EstadoOle",
    "Accion", "Fuentes", "URLsFuentes", "URLPrincipal"
]
FUENTES_EDITOR_HEADERS = [
    "FuenteID", "Fuente", "Zona", "MetodoActivo", "Estado", "Noticias",
    "UltimoContenido", "Problema", "RespaldoSugerido"
]
SOCIAL_INBOX_HEADERS = [
    "FechaHora", "SocialID", "Estado", "Plataforma", "Autor", "Titulo", "URL",
    "Nota", "PorQue", "TemaVinculado"
]
PARTE_IA_HEADERS = [
    "FechaHora", "Corte", "Modelo", "Titulo", "Texto", "Regeneracion", "TemasIncluidos"
]
AGENT_LOG_HEADERS = [
    "FechaHora", "Agente", "Estado", "DuracionSeg", "Recomendaciones",
    "Oportunidades", "AlertasEnviadas", "InformeEnviado", "Detalle",
]


def configure(service_account_json: str | None = None, sheet_id: str | None = None,
              prefix: str | None = None) -> None:
    if service_account_json:
        _CONF["json"] = service_account_json
    if sheet_id:
        _CONF["sheet_id"] = sheet_id
    if prefix is not None:
        _CONF["prefix"] = prefix
    _CACHE["sheet"] = None
    _CACHE["worksheets"] = None
    _CACHE["records"] = {}


def _credentials() -> tuple[str, str]:
    return (
        _CONF["json"] or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        _CONF["sheet_id"] or os.environ.get("SHEET_ID", ""),
    )


def disponible() -> bool:
    sa, sid = _credentials()
    return bool(gspread and sa and sid)


def prefix() -> str:
    raw = _CONF["prefix"] if _CONF["prefix"] is not None else os.environ.get("SHEET_PREFIX", "V9_")
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", raw or "")
    return clean[:30]


def nombre_pestana(base: str) -> str:
    return f"{prefix()}{base}"[:100]


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota exceeded" in text or "rate limit" in text


def _api_call(callable_, *, attempts: int = 4):
    """Ejecuta una llamada a Sheets y espera si Google aplica el limite por minuto."""
    delays = (5, 15, 35)
    for attempt in range(attempts):
        try:
            return callable_()
        except Exception as exc:
            if not _is_quota_error(exc) or attempt >= attempts - 1:
                raise
            time.sleep(delays[min(attempt, len(delays) - 1)])


def _sheet():
    if _CACHE["sheet"] is not None:
        return _CACHE["sheet"]
    if not disponible():
        raise RuntimeError("Faltan GOOGLE_SERVICE_ACCOUNT_JSON o SHEET_ID")
    sa, sid = _credentials()
    client = gspread.service_account_from_dict(json.loads(sa))
    _CACHE["sheet"] = _api_call(lambda: client.open_by_key(sid))
    return _CACHE["sheet"]


def _worksheet_map() -> dict[str, Any]:
    """Carga una sola vez todas las pestanas y evita una lectura por cada _ws()."""
    if _CACHE.get("worksheets") is None:
        worksheets = _api_call(lambda: _sheet().worksheets())
        _CACHE["worksheets"] = {ws.title: ws for ws in worksheets}
    return _CACHE["worksheets"]


def _invalidate_records(base: str) -> None:
    _CACHE.setdefault("records", {}).pop(nombre_pestana(base), None)


def _ws(base: str, headers: list[str], rows: int = 1000):
    sh = _sheet()
    name = nombre_pestana(base)
    worksheets = _worksheet_map()
    ws = worksheets.get(name)
    if ws is None:
        ws = _api_call(lambda: sh.add_worksheet(
            title=name, rows=rows, cols=max(len(headers), 3)
        ))
        _api_call(lambda: ws.update(range_name="A1", values=[headers]))
        worksheets[name] = ws
    return ws


def asegurar_estructura() -> None:
    _ws("Noticias", NOTICIAS_HEADERS, rows=1200)
    _ws("Temas", TEMAS_HEADERS, rows=250)
    _ws("Fuentes", FUENTES_HEADERS, rows=150)
    _ws("Control", CONTROL_HEADERS, rows=40)
    _ws("Feedback", FEEDBACK_HEADERS, rows=500)
    _ws("Recomendaciones", RECOMENDACIONES_HEADERS, rows=300)
    _ws("Descubrimientos", DESCUBRIMIENTOS_HEADERS, rows=200)
    _ws("Cambios", CAMBIOS_HEADERS, rows=300)
    _ws("Resumen", RESUMEN_HEADERS, rows=50)
    _ws("Oportunidades", OPORTUNIDADES_HEADERS, rows=200)
    _ws("Informes", INFORMES_HEADERS, rows=500)
    _ws("Avisos", AVISOS_HEADERS, rows=1000)
    _ws("AgentLog", AGENT_LOG_HEADERS, rows=1000)
    _ws("RESUMEN_4H", RESUMEN_4H_HEADERS, rows=100)
    _ws("HISTORIAL_4H", HISTORIAL_4H_HEADERS, rows=3000)
    _ws("ACCIONES", ACCIONES_EDITOR_HEADERS, rows=500)
    _ws("OLE_HOY", OLE_HOY_HEADERS, rows=500)
    _ws("COBERTURA_OLE", COBERTURA_OLE_EDITOR_HEADERS, rows=300)
    _ws("HALLAZGOS", HALLAZGOS_EDITOR_HEADERS, rows=300)
    _ws("FUENTES_EDITOR", FUENTES_EDITOR_HEADERS, rows=200)
    _ws("BUZON_SOCIAL", SOCIAL_INBOX_HEADERS, rows=1000)
    _ws("PARTES_IA", PARTE_IA_HEADERS, rows=500)


def _safe(value: Any, max_len: int = 45000) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "si" if value else "no"
    if isinstance(value, (dict, list, tuple, set)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    text = str(value).replace("\x00", "").strip()
    return text[:max_len]


def _replace(base: str, headers: list[str], rows: Iterable[Iterable[Any]],
             min_rows: int = 100) -> int:
    values = [headers] + [[_safe(v) for v in row] for row in rows]
    target_rows = max(min_rows, len(values) + 20)
    target_cols = max(len(headers), 3)
    ws = _ws(base, headers, rows=target_rows)
    try:
        if ws.row_count < target_rows or ws.col_count < target_cols:
            _api_call(lambda: ws.resize(rows=max(ws.row_count, target_rows),
                                        cols=max(ws.col_count, target_cols)))
    except Exception:
        pass
    _api_call(ws.clear)
    _api_call(lambda: ws.update(range_name="A1", values=values, value_input_option="RAW"))
    _invalidate_records(base)
    return max(0, len(values) - 1)


def _stable_id(text: str, prefix_id: str) -> str:
    digest = hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:14]
    return f"{prefix_id}_{digest}"


def cluster_id(titulo: str) -> str:
    try:
        from monitor_core import normalizar_titulo
        base = " ".join(sorted(normalizar_titulo(titulo))) or titulo
    except Exception:
        base = titulo
    return _stable_id(base, "c")


def guardar_snapshot_online(resultados: dict, tendencias: list, agenda: list,
                            estados_fuentes: list, run_info: dict | None = None) -> dict:
    """Reemplaza las pestanas operativas. No modifica Agenda/Snapshot historicos."""
    asegurar_estructura()
    run_info = dict(run_info or {})
    now = datetime.now(_TZ_AR).isoformat(timespec="seconds")
    max_news = int(os.environ.get("MAX_SNAPSHOT_NOTICIAS", "800") or 800)
    agenda_by_id = {cluster_id(x.get("titulo", "")): x for x in agenda}

    fuentes_por_id = {}
    try:
        from monitor_core import TODAS_FUENTES, FUENTES_NAC_IDS
        fuentes_por_id = {f["id"]: f for f in TODAS_FUENTES}
        nac_ids = set(FUENTES_NAC_IDS)
    except Exception:
        nac_ids = set()

    news_rows = []
    # Reparto equilibrado: evita que las primeras fuentes ocupen todo el snapshot.
    per_source = max(5, max_news // max(len(resultados), 1))
    for fid, items in resultados.items():
        fuente = fuentes_por_id.get(fid, {"id": fid, "nombre": fid})
        for n in items[:per_source]:
            publisher = n.get("publisher_original") or fuente.get("nombre", fid)
            canal = "Google News" if (fuente.get("es_rss") and "news.google.com" in fuente.get("url", "")) else (
                "RSS" if fuente.get("es_rss") else "Web directa"
            )
            nid = _stable_id(f"{n.get('url','')}|{n.get('titulo','')}|{fid}", "n")
            news_rows.append([
                now, nid, fid, fuente.get("nombre", fid), publisher, canal,
                n.get("titulo", ""), n.get("url", ""), n.get("imagen", ""),
                n.get("fecha_publicacion", ""), "Nacional" if fid in nac_ids else "Internacional",
            ])
    news_rows = news_rows[:max_news]

    temas_rows = []
    for pos, c in enumerate(tendencias[:120], start=1):
        cid = cluster_id(c.get("titulo", ""))
        action = agenda_by_id.get(cid, {})
        detalles = []
        for item in c.get("noticias", [])[:12]:
            n, f = item.get("noticia", {}), item.get("fuente", {})
            detalles.append({
                "fuente": n.get("publisher_original") or f.get("nombre", ""),
                "canal": f.get("nombre", ""),
                "titulo": n.get("titulo", ""),
                "url": n.get("url", ""),
                "fecha": n.get("fecha_publicacion", ""),
            })
        temas_rows.append([
            now, cid, pos, action.get("accion", "OBSERVAR"), c.get("titulo", ""),
            c.get("url", ""), c.get("cant_medios", 0),
            " | ".join(c.get("medios_originales", [])), c.get("tiene_ole", False),
            c.get("nac", 0), c.get("intl", 0), action.get("delta", 0),
            action.get("nuevo", False), action.get("motivo", ""), action.get("score", 0),
            detalles,
        ])

    source_rows = []
    for s in estados_fuentes:
        source_rows.append([
            now, s.get("id", ""), s.get("nombre", ""), s.get("zona", ""),
            s.get("canal", ""), s.get("estado", ""), s.get("noticias", 0),
            s.get("duracion", 0), s.get("error", ""), s.get("ultimo_contenido", ""),
        ])

    counts = {
        "noticias": _replace("Noticias", NOTICIAS_HEADERS, news_rows, 1200),
        "temas": _replace("Temas", TEMAS_HEADERS, temas_rows, 250),
        "fuentes": _replace("Fuentes", FUENTES_HEADERS, source_rows, 150),
    }
    control = {
        "ultima_actualizacion": now,
        "estado": run_info.pop("estado", "ok"),
        "noticias": counts["noticias"],
        "temas": counts["temas"],
        "fuentes_ok": sum(1 for s in estados_fuentes if s.get("estado") == "ok"),
        "fuentes_total": len(estados_fuentes),
        **run_info,
    }
    _replace("Control", CONTROL_HEADERS,
             [[k, v, now] for k, v in control.items()], 40)
    return counts


def _records(base: str, headers: list[str]) -> list[dict]:
    cache_key = nombre_pestana(base)
    cached = _CACHE.setdefault("records", {}).get(cache_key)
    if cached is not None:
        return [dict(row) for row in cached]
    try:
        values = _api_call(lambda: _ws(base, headers).get_all_values())
        if len(values) < 2:
            records = []
        else:
            keys = values[0]
            records = [dict(zip(keys, row + [""] * (len(keys) - len(row)))) for row in values[1:]]
        _CACHE["records"][cache_key] = records
        return [dict(row) for row in records]
    except Exception:
        return []


def leer_noticias() -> list[dict]:
    return _records("Noticias", NOTICIAS_HEADERS)


def leer_temas() -> list[dict]:
    rows = _records("Temas", TEMAS_HEADERS)
    for row in rows:
        try:
            row["Fuentes"] = json.loads(row.get("FuentesJSON") or "[]")
        except Exception:
            row["Fuentes"] = []
    return rows


def leer_fuentes() -> list[dict]:
    return _records("Fuentes", FUENTES_HEADERS)


def leer_control() -> dict:
    return {r.get("Clave", ""): r.get("Valor", "") for r in _records("Control", CONTROL_HEADERS)}


def guardar_feedback(cluster: str, titulo: str, accion_sugerida: str,
                     accion_editor: str, util: str = "", termino_en_nota: str = "",
                     comentario: str = "") -> bool:
    try:
        asegurar_estructura()
        now = datetime.now(_TZ_AR)
        _api_call(lambda: _ws("Feedback", FEEDBACK_HEADERS, rows=500).append_row([
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), cluster, titulo,
            accion_sugerida, accion_editor, util, termino_en_nota, comentario,
        ], value_input_option="RAW"))
        _invalidate_records("Feedback")
        return True
    except Exception:
        return False


def leer_feedback() -> list[dict]:
    return _records("Feedback", FEEDBACK_HEADERS)


def leer_descubrimientos() -> list[dict]:
    rows = _records("Descubrimientos", DESCUBRIMIENTOS_HEADERS)
    for row in rows:
        try:
            row["Evidencia"] = json.loads(row.get("EvidenciaJSON") or "[]")
        except Exception:
            row["Evidencia"] = []
    return rows



def guardar_agente_snapshot(recommendations: list[dict], discoveries: list[dict], opportunities: list[dict]) -> dict:
    """Replaces current outputs for the operational and discovery radars."""
    asegurar_estructura()
    now = datetime.now(_TZ_AR).isoformat(timespec="seconds")
    rec_rows = []
    for rec in recommendations:
        rec_rows.append([
            now, rec.get("recommendation_id", ""), rec.get("cluster_id", ""),
            rec.get("radar", "OPERATIVO LOCAL"), rec.get("priority", 0),
            rec.get("confidence", 0), rec.get("state", ""), rec.get("action", ""),
            rec.get("coverage_status", ""), rec.get("ole_match_title", ""),
            rec.get("ole_match_url", ""), rec.get("title", ""), rec.get("url", ""),
            rec.get("media_count", 0), " | ".join(rec.get("publishers", []) or []),
            rec.get("has_ole", False), rec.get("momentum", 0), rec.get("is_new", False),
            rec.get("official_count", 0), rec.get("reason", ""), rec.get("evidence", []),
        ])
    discovery_rows = []
    for item in discoveries:
        discovery_rows.append([
            now, item.get("discovery_id", ""), item.get("category", ""), item.get("status", ""),
            item.get("score", 0), item.get("value_argentina", 0), item.get("title", ""),
            item.get("url", ""), " | ".join(item.get("publishers", []) or []),
            item.get("media_count", 0), item.get("published_at", ""),
            item.get("age_hours", ""), item.get("is_new", False),
            item.get("ole_status", ""), item.get("ole_match_title", ""),
            item.get("ole_match_url", ""), item.get("reason", ""), item.get("why_it_matters", ""),
            item.get("suggested_angle", ""), item.get("suggested_format", ""),
            item.get("evidence", []),
        ])
    opp_rows = []
    for opp in opportunities:
        opp_rows.append([
            now, opp.get("opportunity_id", ""), opp.get("score", 0),
            opp.get("format", ""), opp.get("title", ""), opp.get("source_title", ""),
            opp.get("angle", ""), opp.get("why_now", ""),
            opp.get("suggested_headline", ""), opp.get("effort", ""),
            opp.get("expiry", ""), opp.get("cluster_ids", []),
        ])
    return {
        "recommendations": _replace("Recomendaciones", RECOMENDACIONES_HEADERS, rec_rows, 300),
        "discoveries": _replace("Descubrimientos", DESCUBRIMIENTOS_HEADERS, discovery_rows, 200),
        "opportunities": _replace("Oportunidades", OPORTUNIDADES_HEADERS, opp_rows, 200),
    }



def guardar_briefing_snapshot(changes: list[dict], summary: dict) -> dict:
    asegurar_estructura()
    now = datetime.now(_TZ_AR).isoformat(timespec="seconds")
    change_rows = []
    for item in changes or []:
        change_rows.append([
            now, item.get("change_id", ""), item.get("cluster_id", ""),
            item.get("change_type", ""), item.get("priority", 0), item.get("action", ""),
            item.get("coverage_status", ""), item.get("title", ""), item.get("url", ""),
            item.get("what_changed", ""), item.get("media_now", 0), item.get("media_before", 0),
            item.get("has_ole", False), item.get("ole_match_title", ""),
            item.get("ole_match_url", ""), item.get("reason", ""),
        ])
    summary_rows = [[
        summary.get("created_at", now), summary.get("title", "Resumen del corte"),
        summary.get("plain_text", ""), summary.get("publish_count", 0),
        summary.get("update_count", 0), summary.get("verify_count", 0),
        summary.get("growth_count", 0), summary.get("discovery_count", 0),
        summary.get("source_error_count", 0), summary.get("top_change_ids", []),
        summary.get("top_discovery_ids", []),
    ]]
    return {
        "changes": _replace("Cambios", CAMBIOS_HEADERS, change_rows, 300),
        "summary": _replace("Resumen", RESUMEN_HEADERS, summary_rows, 50),
    }


def leer_cambios() -> list[dict]:
    return _records("Cambios", CAMBIOS_HEADERS)


def leer_resumen() -> dict:
    rows = _records("Resumen", RESUMEN_HEADERS)
    return rows[-1] if rows else {}

def _append(base: str, headers: list[str], row: list[Any], max_rows: int = 1500) -> bool:
    try:
        ws = _ws(base, headers, rows=max_rows)
        _api_call(lambda: ws.append_row([_safe(value) for value in row], value_input_option="RAW"))
        _invalidate_records(base)
        if ws.row_count > max_rows * 2:
            values = _api_call(ws.get_all_values)
            kept = [values[0]] + values[-(max_rows - 1):]
            _api_call(ws.clear)
            _api_call(lambda: ws.update(range_name="A1", values=kept, value_input_option="RAW"))
            _invalidate_records(base)
        return True
    except Exception:
        return False


def registrar_avisos_descubrimiento(items: list[dict]) -> bool:
    ok = True
    for item in items or []:
        ok = registrar_aviso_clave(
            item.get("discovery_id", ""), "DISCOVERY", item.get("title", "")
        ) and ok
    return ok


def registrar_informe(report: dict) -> bool:
    return _append("Informes", INFORMES_HEADERS, [
        report.get("created_at", datetime.now(_TZ_AR).isoformat(timespec="seconds")),
        report.get("report_type", ""), report.get("title", ""),
        report.get("plain_text", ""), report.get("recommendation_ids", []),
        report.get("opportunity_ids", []), report.get("source_error_count", 0),
    ], max_rows=600)


def registrar_aviso_clave(key: str, notice_type: str, title: str = "") -> bool:
    return _append("Avisos", AVISOS_HEADERS, [
        datetime.now(_TZ_AR).isoformat(timespec="seconds"), key, notice_type, title,
    ], max_rows=1200)


def registrar_avisos(recommendations: list[dict], notice_type: str = "ALERT") -> int:
    count = 0
    for rec in recommendations:
        if registrar_aviso_clave(rec.get("recommendation_id", ""), notice_type, rec.get("title", "")):
            count += 1
    return count


def aviso_reciente(key: str, notice_type: str, hours: int = 6) -> bool:
    if not key:
        return False
    cutoff = datetime.now(_TZ_AR) - timedelta(hours=max(1, hours))
    for row in reversed(_records("Avisos", AVISOS_HEADERS)[-500:]):
        if row.get("Clave") != key or row.get("Tipo") != notice_type:
            continue
        try:
            timestamp = datetime.fromisoformat(row.get("FechaHora", ""))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=_TZ_AR)
            return timestamp >= cutoff
        except Exception:
            return True
    return False


def registrar_agent_log(data: dict) -> bool:
    return _append("AgentLog", AGENT_LOG_HEADERS, [
        datetime.now(_TZ_AR).isoformat(timespec="seconds"), data.get("agent", ""),
        data.get("status", ""), data.get("duration_seconds", 0),
        data.get("recommendations", 0), data.get("opportunities", 0),
        data.get("alerts_sent", 0), data.get("report_sent", False), data.get("detail", ""),
    ], max_rows=1200)


def leer_recomendaciones() -> list[dict]:
    rows = _records("Recomendaciones", RECOMENDACIONES_HEADERS)
    for row in rows:
        try:
            row["Evidencia"] = json.loads(row.get("EvidenciaJSON") or "[]")
        except Exception:
            row["Evidencia"] = []
    return rows


def leer_oportunidades() -> list[dict]:
    rows = _records("Oportunidades", OPORTUNIDADES_HEADERS)
    for row in rows:
        try:
            row["Clusters"] = json.loads(row.get("ClustersJSON") or "[]")
        except Exception:
            row["Clusters"] = []
    return rows


def leer_informes(limit: int = 20) -> list[dict]:
    return _records("Informes", INFORMES_HEADERS)[-max(1, limit):]


def leer_agent_log(limit: int = 50) -> list[dict]:
    return _records("AgentLog", AGENT_LOG_HEADERS)[-max(1, limit):]

def url_planilla() -> str:
    _, sid = _credentials()
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""


# ---------------------------------------------------------------------------
# V11: editor-facing sheets and on-demand AI parts
# ---------------------------------------------------------------------------

def _append_rows(base: str, headers: list[str], rows: list[list[Any]], max_rows: int = 5000) -> int:
    if not rows:
        return 0
    try:
        ws = _ws(base, headers, rows=max_rows)
        _api_call(lambda: ws.append_rows(
            [[_safe(value) for value in row] for row in rows], value_input_option="RAW"
        ))
        _invalidate_records(base)
        # El historial se depura solo cuando la hoja ya es muy grande. Evita una
        # lectura completa en cada corte de cuatro horas.
        if ws.row_count > max_rows * 2:
            values = _api_call(ws.get_all_values)
            if len(values) > max_rows:
                kept = [values[0]] + values[-(max_rows - 1):]
                _api_call(ws.clear)
                _api_call(lambda: ws.update(range_name="A1", values=kept, value_input_option="RAW"))
                _invalidate_records(base)
        return len(rows)
    except Exception:
        return 0


def _format_editorial_sheet(base: str, widths: list[int], tab_color: dict | None = None) -> None:
    """Best-effort formatting. Failures never stop the monitor."""
    try:
        ws = _ws(base, ["A"])
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}, **({"tabColorStyle": {"rgbColor": tab_color}} if tab_color else {})},
                    "fields": "gridProperties.frozenRowCount" + (",tabColorStyle" if tab_color else ""),
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.08, "green": 0.18, "blue": 0.34}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}, "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP"}},
                    "fields": "userEnteredFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1},
                    "cell": {"userEnteredFormat": {"verticalAlignment": "TOP", "wrapStrategy": "WRAP"}},
                    "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {"range": {"sheetId": ws.id, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": max(1, len(widths))}}
                }
            },
        ]
        for idx, width in enumerate(widths):
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
                    "properties": {"pixelSize": int(width)},
                    "fields": "pixelSize",
                }
            })
        _api_call(lambda: _sheet().batch_update({"requests": requests}))
    except Exception:
        pass


def leer_ole_hoy() -> list[dict]:
    return _records("OLE_HOY", OLE_HOY_HEADERS)


def leer_cobertura_ole_editor() -> list[dict]:
    return _records("COBERTURA_OLE", COBERTURA_OLE_EDITOR_HEADERS)


def leer_resumen_4h() -> list[dict]:
    return _records("RESUMEN_4H", RESUMEN_4H_HEADERS)


def leer_acciones_editor() -> list[dict]:
    return _records("ACCIONES", ACCIONES_EDITOR_HEADERS)


def leer_hallazgos_editor() -> list[dict]:
    return _records("HALLAZGOS", HALLAZGOS_EDITOR_HEADERS)


def leer_fuentes_editor() -> list[dict]:
    return _records("FUENTES_EDITOR", FUENTES_EDITOR_HEADERS)


def leer_buzon_social() -> list[dict]:
    return _records("BUZON_SOCIAL", SOCIAL_INBOX_HEADERS)


def agregar_buzon_social(plataforma: str, autor: str, titulo: str, url: str,
                         nota: str = "", por_que: str = "", tema: str = "") -> bool:
    now = datetime.now(_TZ_AR).isoformat(timespec="seconds")
    sid = _stable_id(f"{url}|{titulo}|{now}", "soc")
    return _append("BUZON_SOCIAL", SOCIAL_INBOX_HEADERS, [
        now, sid, "PENDIENTE", plataforma, autor, titulo, url, nota, por_que, tema,
    ], max_rows=1000)


def actualizar_buzon_social(social_id: str, status: str, linked_topic: str = "") -> bool:
    rows = leer_buzon_social()
    changed = False
    output = []
    for row in rows:
        if row.get("SocialID") == social_id:
            row["Estado"] = status
            if linked_topic:
                row["TemaVinculado"] = linked_topic
            changed = True
        output.append([row.get(h, "") for h in SOCIAL_INBOX_HEADERS])
    if changed:
        _replace("BUZON_SOCIAL", SOCIAL_INBOX_HEADERS, output, 1000)
    return changed


def actualizar_accion_editor(action_id: str, status: str, notes: str = "") -> bool:
    rows = leer_acciones_editor()
    changed = False
    output = []
    for row in rows:
        if row.get("ActionID") == action_id:
            row["Estado"] = status
            if notes:
                row["Notas"] = notes
            row["Actualizado"] = datetime.now(_TZ_AR).isoformat(timespec="seconds")
            changed = True
        output.append([row.get(h, "") for h in ACCIONES_EDITOR_HEADERS])
    if changed:
        _replace("ACCIONES", ACCIONES_EDITOR_HEADERS, output, 500)
    return changed


def guardar_mesa_editorial(desk: dict, ole_entries: list[dict], ole_coverage: list[dict],
                            source_rows: list[dict]) -> dict:
    asegurar_estructura()
    topics = list(desk.get("topics") or [])
    actions = list(desk.get("actions") or [])
    meta = dict(desk.get("meta") or {})
    cut_key = str(meta.get("cut_key") or "")

    current = leer_resumen_4h()
    previous_cut = str(current[0].get("Corte") or "") if current else ""
    if current and previous_cut and previous_cut != cut_key:
        _append_rows("HISTORIAL_4H", HISTORIAL_4H_HEADERS,
                     [[row.get(h, "") for h in HISTORIAL_4H_HEADERS] for row in current], max_rows=6000)

    topic_rows = [[
        item.get("cut_key", cut_key), item.get("window_start", ""), item.get("window_end", ""),
        item.get("order", 0), item.get("importance", ""), item.get("section", ""),
        item.get("topic", ""), item.get("what_happened", ""), item.get("what_changed", ""),
        item.get("why_it_matters", ""), item.get("ole_status", ""), item.get("ole_title", ""),
        item.get("ole_url", ""), item.get("action", ""), item.get("priority", 0),
        item.get("media_count", 0), item.get("sources", ""), item.get("source_urls", ""),
        item.get("url", ""), item.get("generated_at", ""),
    ] for item in topics]

    previous_actions = {row.get("ActionID", ""): row for row in leer_acciones_editor()}
    action_rows = []
    for item in actions:
        old = previous_actions.get(item.get("action_id", ""), {})
        action_rows.append([
            item.get("action_id", ""), item.get("cut_key", cut_key), item.get("priority", 0),
            item.get("action", ""), old.get("Estado") or item.get("status", "PENDIENTE"),
            item.get("topic_id", ""), item.get("topic", ""), item.get("new_data", ""),
            item.get("ole_title", ""), item.get("ole_url", ""), item.get("sources", ""),
            item.get("source_urls", ""), item.get("updated_at", ""), old.get("Notas") or item.get("notes", ""),
        ])

    ole_rows = [[
        item.get("ole_id", ""), item.get("first_seen", ""), item.get("last_seen", ""),
        item.get("published_at", ""), item.get("updated_at", ""), item.get("section", ""),
        item.get("topic_id", ""), item.get("topic", ""), item.get("focus", ""),
        item.get("title", ""), item.get("url", ""), " | ".join(item.get("entities", []) or []),
        " | ".join(item.get("related_external", []) or []), item.get("suggested_action", ""),
    ] for item in ole_entries or []]

    coverage_rows = [[
        item.get("topic_id", ""), item.get("topic", ""), item.get("piece_count", 0),
        " | ".join(item.get("sections", []) or []), " | ".join(item.get("focuses", []) or []),
        item.get("first_seen", ""), item.get("last_seen", ""), item.get("last_title", ""),
        item.get("last_url", ""), " || ".join(item.get("titles", []) or []),
        " || ".join(item.get("external_updates", []) or []), item.get("suggested_action", ""),
        item.get("overcoverage", False),
    ] for item in ole_coverage or []]

    hallazgo_rows = [[
        item.get("cut_key", cut_key), item.get("priority", 0), item.get("topic", ""),
        item.get("what_happened", ""), item.get("why_it_matters", ""), item.get("ole_status", ""),
        item.get("action", ""), item.get("sources", ""), item.get("source_urls", ""), item.get("url", ""),
    ] for item in topics if item.get("section") in {"HALLAZGOS", "BUZON SOCIAL"}]

    source_values = [[
        item.get("source_id", ""), item.get("source", ""), item.get("zone", ""),
        item.get("active_method", ""), item.get("editorial_state", ""), item.get("items", 0),
        item.get("last_content", ""), item.get("problem", ""), item.get("fallback", ""),
    ] for item in source_rows or []]

    counts = {
        "summary4h": _replace("RESUMEN_4H", RESUMEN_4H_HEADERS, topic_rows, 100),
        "actions": _replace("ACCIONES", ACCIONES_EDITOR_HEADERS, action_rows, 500),
        "ole_today": _replace("OLE_HOY", OLE_HOY_HEADERS, ole_rows, 500),
        "ole_coverage": _replace("COBERTURA_OLE", COBERTURA_OLE_EDITOR_HEADERS, coverage_rows, 300),
        "findings": _replace("HALLAZGOS", HALLAZGOS_EDITOR_HEADERS, hallazgo_rows, 300),
        "source_editor": _replace("FUENTES_EDITOR", FUENTES_EDITOR_HEADERS, source_values, 200),
    }
    _format_editorial_sheet("RESUMEN_4H", [110, 125, 125, 65, 115, 145, 300, 420, 360, 360, 155, 260, 230, 125, 80, 75, 240, 240, 230, 145], {"red": 0.07, "green": 0.35, "blue": 0.65})
    _format_editorial_sheet("ACCIONES", [160, 110, 80, 120, 110, 140, 320, 380, 260, 230, 220, 220, 150, 260], {"red": 0.78, "green": 0.25, "blue": 0.12})
    _format_editorial_sheet("OLE_HOY", [150, 145, 145, 140, 140, 130, 140, 300, 130, 360, 240, 180, 360, 180], {"red": 0.1, "green": 0.55, "blue": 0.22})
    _format_editorial_sheet("COBERTURA_OLE", [150, 320, 70, 180, 180, 145, 145, 320, 230, 480, 420, 180, 110], {"red": 0.1, "green": 0.55, "blue": 0.22})
    _format_editorial_sheet("HALLAZGOS", [110, 80, 320, 420, 400, 150, 120, 240, 240, 230], {"red": 0.55, "green": 0.2, "blue": 0.7})
    _format_editorial_sheet("FUENTES_EDITOR", [120, 230, 120, 150, 210, 80, 155, 360, 360], {"red": 0.35, "green": 0.35, "blue": 0.35})
    return counts


def guardar_parte_ia(cut_key: str, title: str, text: str, model: str,
                     topic_count: int, regeneration: bool = False) -> bool:
    return _append("PARTES_IA", PARTE_IA_HEADERS, [
        datetime.now(_TZ_AR).isoformat(timespec="seconds"), cut_key, model, title, text,
        "si" if regeneration else "no", topic_count,
    ], max_rows=500)


def leer_partes_ia(limit: int = 50) -> list[dict]:
    return _records("PARTES_IA", PARTE_IA_HEADERS)[-max(1, limit):]


def parte_ia_para_corte(cut_key: str) -> dict:
    rows = [row for row in leer_partes_ia(200) if row.get("Corte") == cut_key]
    return rows[-1] if rows else {}
