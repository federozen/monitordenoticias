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
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

try:
    import gspread
except Exception:  # pragma: no cover
    gspread = None

_TZ_AR = timezone(timedelta(hours=-3))
_CONF = {"json": None, "sheet_id": None, "prefix": None}
_CACHE = {"sheet": None}

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
    "RunTS", "DiscoveryID", "Categoria", "Score", "ValorArgentina", "Titulo", "URL",
    "Publishers", "Medios", "FechaPublicacion", "AntiguedadHoras", "EsNuevo",
    "EstadoOle", "TituloOle", "URLOle", "Motivo", "Angulo", "Formato", "EvidenciaJSON",
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


def _sheet():
    if _CACHE["sheet"] is not None:
        return _CACHE["sheet"]
    if not disponible():
        raise RuntimeError("Faltan GOOGLE_SERVICE_ACCOUNT_JSON o SHEET_ID")
    sa, sid = _credentials()
    client = gspread.service_account_from_dict(json.loads(sa))
    _CACHE["sheet"] = client.open_by_key(sid)
    return _CACHE["sheet"]


def _ws(base: str, headers: list[str], rows: int = 1000):
    sh = _sheet()
    name = nombre_pestana(base)
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=rows, cols=max(len(headers), 3))
        ws.update(range_name="A1", values=[headers])
    return ws


def asegurar_estructura() -> None:
    _ws("Noticias", NOTICIAS_HEADERS, rows=1200)
    _ws("Temas", TEMAS_HEADERS, rows=250)
    _ws("Fuentes", FUENTES_HEADERS, rows=150)
    _ws("Control", CONTROL_HEADERS, rows=40)
    _ws("Feedback", FEEDBACK_HEADERS, rows=500)
    _ws("Recomendaciones", RECOMENDACIONES_HEADERS, rows=300)
    _ws("Descubrimientos", DESCUBRIMIENTOS_HEADERS, rows=200)
    _ws("Oportunidades", OPORTUNIDADES_HEADERS, rows=200)
    _ws("Informes", INFORMES_HEADERS, rows=500)
    _ws("Avisos", AVISOS_HEADERS, rows=1000)
    _ws("AgentLog", AGENT_LOG_HEADERS, rows=1000)


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
            ws.resize(rows=max(ws.row_count, target_rows),
                      cols=max(ws.col_count, target_cols))
    except Exception:
        pass
    ws.clear()
    ws.update(range_name="A1", values=values, value_input_option="RAW")
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
    try:
        values = _ws(base, headers).get_all_values()
        if len(values) < 2:
            return []
        keys = values[0]
        return [dict(zip(keys, row + [""] * (len(keys) - len(row)))) for row in values[1:]]
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
        _ws("Feedback", FEEDBACK_HEADERS, rows=500).append_row([
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), cluster, titulo,
            accion_sugerida, accion_editor, util, termino_en_nota, comentario,
        ], value_input_option="RAW")
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
            now, item.get("discovery_id", ""), item.get("category", ""),
            item.get("score", 0), item.get("value_argentina", 0), item.get("title", ""),
            item.get("url", ""), " | ".join(item.get("publishers", []) or []),
            item.get("media_count", 0), item.get("published_at", ""),
            item.get("age_hours", ""), item.get("is_new", False),
            item.get("ole_status", ""), item.get("ole_match_title", ""),
            item.get("ole_match_url", ""), item.get("reason", ""),
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


def _append(base: str, headers: list[str], row: list[Any], max_rows: int = 1500) -> bool:
    try:
        ws = _ws(base, headers, rows=max_rows)
        ws.append_row([_safe(value) for value in row], value_input_option="RAW")
        if ws.row_count > max_rows * 2:
            values = ws.get_all_values()
            kept = [values[0]] + values[-(max_rows - 1):]
            ws.clear()
            ws.update(range_name="A1", values=kept, value_input_option="RAW")
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
