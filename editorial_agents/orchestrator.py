from __future__ import annotations

import os
import time
from typing import Callable

from .coverage import enrich_themes
from .curator import curate
from .discovery import generate as generate_discoveries
from .executive import alert_message, build_report
from .opportunities import generate as generate_opportunities
from .utils import env_bool, env_int, now_ar


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
        ole_coverage: list[dict] | None = None) -> dict:
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

    storage.guardar_agente_snapshot(recommendations, discoveries, opportunities)
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
        hourly = env_bool("AGENT_HOURLY_DIGEST", True)
        report_key = f"{report_type}:{now.strftime('%Y-%m-%d-%H')}"
        due = (hourly or report_type in {"OPENING", "CLOSING"}) and not storage.aviso_reciente(
            report_key, "REPORT", 20
        )
        if due and send_telegram(report["telegram_html"], html=True, silencioso=True):
            sent_report = True
            storage.registrar_aviso_clave(report_key, "REPORT", report.get("title", ""))

    duration = round(time.perf_counter() - start, 3)
    storage.registrar_agent_log({
        "agent": "orchestrator_v9_2",
        "status": "ok",
        "duration_seconds": duration,
        "recommendations": len(recommendations),
        "opportunities": len(opportunities),
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "detail": f"mode={mode}; report={report_type}; discoveries={len(discoveries)}",
    })
    return {
        "enabled": True,
        "recommendations": recommendations,
        "discoveries": discoveries,
        "opportunities": opportunities,
        "report": report,
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "duration_seconds": duration,
    }
