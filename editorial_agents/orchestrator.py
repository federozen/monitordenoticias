from __future__ import annotations

import os
import time
from typing import Callable

from .coverage import enrich_themes
from .briefing import build as build_briefing
from .curator import curate
from .discovery import generate as generate_discoveries
from .executive import alert_message, build_report
from .opportunities import generate as generate_opportunities
from .desk import build_editorial_desk
from .ole_today import build_ole_today
from .source_health import build_source_editor_view
from .utils import env_bool, env_int, now_ar, safe_html


def _telegram_mode() -> str:
    return os.environ.get("AGENT_TELEGRAM_MODE", "off").strip().lower()


def _report_type(hour: int) -> str:
    opening = env_int("AGENT_OPENING_HOUR", 8, 0, 23)
    closing = env_int("AGENT_CLOSING_HOUR", 23, 0, 23)
    if hour == opening:
        return "OPENING"
    if hour == closing:
        return "CLOSING"
    return "HOURLY"


def run(themes: list[dict], agenda: list[dict], source_health: list[dict], storage,
        send_telegram: Callable[..., bool] | None = None, config: dict | None = None,
        force: bool = False, raw_results: dict | None = None,
        ole_coverage: list[dict] | None = None, previous_themes: list[dict] | None = None,
        panorama_themes: list[dict] | None = None, cut_quality: dict | None = None) -> dict:
    start = time.perf_counter()
    enabled = env_bool("AGENT_ENABLED", False) or force
    if not enabled:
        return {
            "enabled": False, "recommendations": [], "discoveries": [],
            "opportunities": [], "report": None,
        }

    enriched_themes = enrich_themes(themes, ole_coverage)
    recommendations = curate(enriched_themes, agenda, config)
    previous_discoveries = storage.leer_descubrimientos() if hasattr(storage, "leer_descubrimientos") else []
    discoveries = generate_discoveries(
        raw_results or {}, ole_coverage, previous=previous_discoveries,
        max_items=env_int("AGENT_MAX_DISCOVERIES", 10, 1, 30), config=config,
    )
    opportunities = generate_opportunities(
        recommendations, discoveries,
        max_items=env_int("AGENT_MAX_OPPORTUNITIES", 6, 1, 12),
    )
    now = now_ar()
    report_type = _report_type(now.hour)
    report = build_report(recommendations, discoveries, opportunities, source_health, report_type, now)
    changes, briefing = build_briefing(
        enriched_themes, previous_themes or [], recommendations, discoveries, source_health
    )

    # V11: mesa editorial legible. Se genera sin IA en cada corrida y se organiza
    # en cortes de cuatro horas. El parte narrativo pago se produce solo desde
    # Streamlit cuando el editor pulsa el boton correspondiente.
    previous_ole = storage.leer_ole_hoy() if hasattr(storage, "leer_ole_hoy") else []
    ole_today, ole_groups = build_ole_today(ole_coverage or [], previous_ole, recommendations, now)
    social_items = storage.leer_buzon_social() if hasattr(storage, "leer_buzon_social") else []
    desk_themes = enrich_themes(panorama_themes or themes, ole_coverage)
    editorial_desk = build_editorial_desk(
        desk_themes, changes, recommendations, discoveries, source_health,
        social_items=social_items, now=now,
        min_topics=env_int("EDITORIAL_SUMMARY_MIN_TOPICS", 30, 10, 50),
        max_topics=env_int("EDITORIAL_SUMMARY_MAX_TOPICS", 40, 15, 60),
        cut_quality=cut_quality,
    )
    source_editor = build_source_editor_view(source_health)

    # El informe horario usa el resumen comparado: cuenta cambios y hallazgos,
    # no repite el inventario completo del monitor.
    report["title"] = briefing.get("title", report.get("title", "RESUMEN EDITORIAL"))
    report["plain_text"] = briefing.get("plain_text", report.get("plain_text", ""))
    report["telegram_html"] = (
        f"<b>{safe_html(report['title'])}</b>\n\n{safe_html(report['plain_text'])}"
    )

    storage.guardar_agente_snapshot(recommendations, discoveries, opportunities)
    if hasattr(storage, "guardar_briefing_snapshot"):
        storage.guardar_briefing_snapshot(changes, briefing)
    if hasattr(storage, "guardar_mesa_editorial"):
        storage.guardar_mesa_editorial(editorial_desk, ole_today, ole_groups, source_editor)
    storage.registrar_informe(report)

    mode = _telegram_mode()
    sent_alerts = 0
    sent_report = False
    if send_telegram and mode in {"alerts", "full"}:
        eligible = []
        silence_hours = env_int("AGENT_ALERT_SILENCE_HOURS", 6, 1, 168)
        for rec in recommendations:
            if not rec.get("notify"):
                continue
            if storage.aviso_reciente(rec.get("recommendation_id", ""), "ALERT", silence_hours):
                continue
            eligible.append(rec)
        eligible_discoveries = []
        for item in discoveries:
            if not item.get("notify"):
                continue
            if storage.aviso_reciente(item.get("discovery_id", ""), "DISCOVERY", silence_hours):
                continue
            eligible_discoveries.append(item)
        message = alert_message(
            eligible, eligible_discoveries,
            max_items=env_int("AGENT_MAX_ALERTS", 4, 1, 10),
        )
        if message and send_telegram(message, html=True, silencioso=False):
            max_alerts = env_int("AGENT_MAX_ALERTS", 4, 1, 10)
            selected_recs = eligible[:max_alerts]
            remaining = max(0, max_alerts - len(selected_recs))
            selected_disc = eligible_discoveries[:remaining]
            sent_alerts = len(selected_recs) + len(selected_disc)
            storage.registrar_avisos(selected_recs, "ALERT")
            if hasattr(storage, "registrar_avisos_descubrimiento"):
                storage.registrar_avisos_descubrimiento(selected_disc)

    if send_telegram and mode in {"digest", "full"}:
        four_hour = env_bool("AGENT_FOUR_HOUR_DIGEST", True)
        due_hour = now.hour in {0, 4, 8, 12, 16, 20}
        report_key = f"4H:{now.strftime('%Y-%m-%d-%H')}"
        due = (four_hour and due_hour) and not storage.aviso_reciente(
            report_key, "REPORT", 180
        )
        if due and send_telegram(report["telegram_html"], html=True, silencioso=True):
            sent_report = True
            storage.registrar_aviso_clave(report_key, "REPORT", report.get("title", ""))

    duration = round(time.perf_counter() - start, 3)
    storage.registrar_agent_log({
        "agent": "orchestrator_v11",
        "status": "ok",
        "duration_seconds": duration,
        "recommendations": len(recommendations),
        "opportunities": len(opportunities),
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "detail": (f"mode={mode}; report={report_type}; discoveries={len(discoveries)}; "
                   f"cut_quality={(cut_quality or {}).get('state', 'COMPLETO')}; "
                   f"coverage={(cut_quality or {}).get('coverage_pct', 100)}%"),
    })
    return {
        "enabled": True,
        "recommendations": recommendations,
        "discoveries": discoveries,
        "opportunities": opportunities,
        "report": report,
        "changes": changes,
        "briefing": briefing,
        "editorial_desk": editorial_desk,
        "ole_today": ole_today,
        "ole_coverage_groups": ole_groups,
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "duration_seconds": duration,
    }
