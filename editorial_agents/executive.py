from __future__ import annotations

from datetime import datetime

from .utils import TZ_AR, safe_html


def _line(rec: dict) -> str:
    return (
        f"- [{rec.get('action','OBSERVAR')}] {rec.get('title','')[:170]} "
        f"({rec.get('media_count',0)} medios, confianza {rec.get('confidence',0)}%)"
    )


def _discovery_line(item: dict) -> str:
    return (
        f"- [{item.get('category','HALLAZGO')}] {item.get('title','')[:170]} "
        f"(valor Argentina {item.get('value_argentina',0)}/100)"
    )


def build_report(recommendations: list[dict], discoveries: list[dict], opportunities: list[dict],
                 source_health: list[dict], report_type: str = "HOURLY",
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ_AR)
    operational = [
        r for r in recommendations
        if r.get("action") in {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR"}
        and r.get("priority", 0) >= 60
    ][:5]
    updates = [r for r in operational if r.get("action") == "ACTUALIZAR"][:3]
    gaps = [r for r in operational if r.get("coverage_status") == "NO_CUBIERTO"][:4]
    verify = [r for r in operational if r.get("action") == "VERIFICAR"][:3]
    findings = [d for d in discoveries if d.get("score", 0) >= 58][:4]
    errors = [s for s in source_health if s.get("estado") != "ok"]

    sections: list[str] = []
    if gaps:
        sections.append("NOVEDADES SIN CUBRIR\n" + "\n".join(_line(r) for r in gaps))
    if updates:
        sections.append("NOTAS QUE CONVIENE ACTUALIZAR\n" + "\n".join(_line(r) for r in updates))
    if verify:
        sections.append("VERIFICAR ANTES DE AVANZAR\n" + "\n".join(_line(r) for r in verify))
    if findings:
        sections.append("HALLAZGOS DEL EXTERIOR\n" + "\n".join(_discovery_line(d) for d in findings))
    if opportunities:
        sections.append("IDEAS DERIVADAS\n" + "\n".join(
            f"- {o.get('title','')[:180]}" for o in opportunities[:3]
        ))
    if errors:
        sections.append(f"SALUD DE FUENTES\n- {len(errors)} fuentes con problemas en este corte")

    plain = "\n\n".join(sections) if sections else "Sin cambios editoriales importantes ni hallazgos fuertes en este corte."
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
        "recommendation_ids": [r.get("recommendation_id", "") for r in operational],
        "opportunity_ids": [o.get("opportunity_id", "") for o in opportunities[:3]],
        "source_error_count": len(errors),
    }


def alert_message(recommendations: list[dict], discoveries: list[dict] | None = None,
                  max_items: int = 4) -> str:
    selected = [r for r in recommendations if r.get("notify")][:max_items]
    findings = [d for d in discoveries or [] if d.get("notify")][:max_items]
    if not selected and not findings:
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
    for item in findings[:max(0, max_items - len(selected))]:
        lines.append(
            f"\n\U0001f4a1 <b>{safe_html(item.get('title','')[:180])}</b>\n"
            f"{safe_html(item.get('category','HALLAZGO'))} - score {item.get('score',0)} - "
            f"valor Argentina {item.get('value_argentina',0)}\n"
            f"{safe_html(item.get('reason','')[:260])}"
        )
        if item.get("url"):
            lines.append(f"<a href=\"{safe_html(item['url'])}\">Abrir fuente</a>")
    return "\n".join(lines)
