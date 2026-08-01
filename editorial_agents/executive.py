from __future__ import annotations

from datetime import datetime

from .utils import TZ_AR, safe_html


def _line(rec: dict) -> str:
    return (f"- [{rec.get('action','OBSERVAR')}] {rec.get('title','')[:170]} "
            f"({rec.get('media_count',0)} medios, confianza {rec.get('confidence',0)}%)")


def build_report(recommendations: list[dict], opportunities: list[dict],
                 source_health: list[dict], report_type: str = "HOURLY",
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ_AR)
    top = recommendations[:5]
    verify = [r for r in recommendations if r.get("action") == "VERIFICAR"][:3]
    gaps = [r for r in recommendations if not r.get("has_ole") and r.get("priority", 0) >= 55][:4]
    errors = [s for s in source_health if s.get("estado") != "ok"]

    sections: list[str] = []
    if top:
        sections.append("PRIORIDADES\n" + "\n".join(_line(r) for r in top))
    if gaps:
        sections.append("HUECOS DE COBERTURA\n" + "\n".join(f"- {r.get('title','')[:180]}" for r in gaps))
    if verify:
        sections.append("VERIFICAR ANTES DE PUBLICAR\n" + "\n".join(f"- {r.get('title','')[:180]}" for r in verify))
    if opportunities:
        sections.append("TEMAS QUE SE PUEDEN HACER\n" + "\n".join(
            f"- {o.get('title','')}: {o.get('source_title','')[:135]}" for o in opportunities[:3]
        ))
    if errors:
        sections.append(f"SALUD DE FUENTES\n- {len(errors)} fuentes con problemas en este corte")

    plain = "\n\n".join(sections) if sections else "Sin cambios editoriales importantes en este corte."
    title_map = {
        "OPENING": "INFORME DE APERTURA",
        "CLOSING": "INFORME DE CIERRE",
        "HOURLY": "RESUMEN EDITORIAL",
        "MANUAL": "INFORME MANUAL",
    }
    label = title_map.get(report_type.upper(), report_type.upper())
    telegram = f"<b>{safe_html(label)}</b> - {now.strftime('%d/%m %H:%M')}\n\n{safe_html(plain)}"
    return {
        "report_type": report_type.upper(),
        "created_at": now.isoformat(timespec="seconds"),
        "title": label,
        "plain_text": plain,
        "telegram_html": telegram,
        "recommendation_ids": [r.get("recommendation_id", "") for r in top],
        "opportunity_ids": [o.get("opportunity_id", "") for o in opportunities[:3]],
        "source_error_count": len(errors),
    }


def alert_message(recommendations: list[dict], max_items: int = 4) -> str:
    selected = [r for r in recommendations if r.get("notify")][:max_items]
    if not selected:
        return ""
    lines = ["<b>ALERTA EDITORIAL</b>"]
    for rec in selected:
        icon = "\U0001f534" if rec.get("action") == "PUBLICAR AHORA" else (
            "\U0001f7e1" if rec.get("action") == "VERIFICAR" else "\u26a1"
        )
        lines.append(
            f"\n{icon} <b>{safe_html(rec.get('title','')[:180])}</b>\n"
            f"{safe_html(rec.get('action',''))} - prioridad {rec.get('priority',0)} - "
            f"confianza {rec.get('confidence',0)}%\n"
            f"{safe_html(rec.get('reason','')[:260])}"
        )
        if rec.get("url"):
            lines.append(f"<a href=\"{safe_html(rec['url'])}\">Abrir fuente</a>")
    return "\n".join(lines)
