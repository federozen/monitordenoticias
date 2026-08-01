from __future__ import annotations

import os
import time
from typing import Callable

from .curator import curate
from .executive import alert_message, build_report
from .opportunities import generate
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


def run(themes: list[dict], agenda: list[dict], source_health: list[dict],
        storage, send_telegram: Callable[..., bool] | None = None,
        config: dict | None = None, force: bool = False) -> dict:
    start = time.perf_counter()
    enabled = env_bool("AGENT_ENABLED", False) or force
    if not enabled:
        return {"enabled": False, "recommendations": [], "opportunities": [], "report": None}

    recommendations = curate(themes, agenda, config)
    opportunities = generate(recommendations, max_items=env_int("AGENT_MAX_OPPORTUNITIES", 6, 1, 12))
    now = now_ar()
    report_type = _report_type(now.hour)
    report = build_report(recommendations, opportunities, source_health, report_type, now)

    storage.guardar_agente_snapshot(recommendations, opportunities)
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
        message = alert_message(eligible, max_items=env_int("AGENT_MAX_ALERTS", 4, 1, 10))
        if message and send_telegram(message, html=True, silencioso=False):
            sent_alerts = len(eligible[:env_int("AGENT_MAX_ALERTS", 4, 1, 10)])
            storage.registrar_avisos(eligible[:sent_alerts], "ALERT")

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
        "agent": "orchestrator",
        "status": "ok",
        "duration_seconds": duration,
        "recommendations": len(recommendations),
        "opportunities": len(opportunities),
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "detail": f"mode={mode}; report={report_type}",
    })
    return {
        "enabled": True,
        "recommendations": recommendations,
        "opportunities": opportunities,
        "report": report,
        "alerts_sent": sent_alerts,
        "report_sent": sent_report,
        "duration_seconds": duration,
    }
