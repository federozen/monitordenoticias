"""Online editorial monitor and proactive assistant (V9).

GitHub Actions performs collection and analysis. Streamlit only reads snapshots,
shows recommendations, records editorial decisions, and runs on-demand writing.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

import monitor_core
import online_storage as store
import predictor_runtime
import sheets_memoria

TZ_AR = timezone(timedelta(hours=-3))

st.set_page_config(
    page_title="Monitor Deportivo V11",
    page_icon="MD",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = os.environ.get(name, default)
    return str(value) if value is not None else default


store.configure(
    _secret("GOOGLE_SERVICE_ACCOUNT_JSON"),
    _secret("SHEET_ID"),
    _secret("SHEET_PREFIX", "V9_"),
)
sheets_memoria.configure(
    _secret("GOOGLE_SERVICE_ACCOUNT_JSON"),
    _secret("SHEET_ID"),
)


@st.cache_data(ttl=120, show_spinner=False)
def load_data() -> dict:
    return {
        "themes": store.leer_temas(),
        "news": store.leer_noticias(),
        "sources": store.leer_fuentes(),
        "control": store.leer_control(),
        "recommendations": store.leer_recomendaciones(),
        "changes": store.leer_cambios(),
        "summary": store.leer_resumen(),
        "discoveries": store.leer_descubrimientos(),
        "opportunities": store.leer_oportunidades(),
        "reports": store.leer_informes(20),
        "agent_log": store.leer_agent_log(50),
        "summary4h": store.leer_resumen_4h(),
        "actions_editor": store.leer_acciones_editor(),
        "ole_today": store.leer_ole_hoy(),
        "ole_coverage_editor": store.leer_cobertura_ole_editor(),
        "findings_editor": store.leer_hallazgos_editor(),
        "sources_editor": store.leer_fuentes_editor(),
        "social_inbox": store.leer_buzon_social(),
        "ai_parts": store.leer_partes_ia(50),
    }


@st.cache_resource(show_spinner=False)
def load_model():
    return predictor_runtime.cargar_modelo()


def as_int(value, default=0):
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def as_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def is_yes(value) -> bool:
    return str(value).strip().lower() in {"si", "true", "1", "yes"}


def title_link(title: str, url: str) -> str:
    safe_title = html.escape(title or "Sin titulo")
    if url:
        return f'<a href="{html.escape(url, quote=True)}" target="_blank">{safe_title}</a>'
    return safe_title


def dispatch_workflow() -> tuple[bool, str]:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    workflow = _secret("GITHUB_WORKFLOW", "vigia.yml")
    ref = _secret("GITHUB_REF", "main")
    if not token or not repo:
        return False, "Faltan GITHUB_TOKEN o GITHUB_REPO en los Secrets de Streamlit."
    response = requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": ref},
        timeout=20,
    )
    if response.status_code == 204:
        return True, "Actualizacion solicitada. El ultimo panorama seguira visible mientras corre."
    return False, f"GitHub respondio {response.status_code}: {response.text[:180]}"


def evidence_from_theme(row: dict) -> list[dict]:
    evidence = row.get("Fuentes")
    if isinstance(evidence, list):
        return evidence
    try:
        return json.loads(row.get("FuentesJSON") or "[]")
    except Exception:
        return []


def evidence_from_recommendation(row: dict) -> list[dict]:
    evidence = row.get("Evidencia")
    if isinstance(evidence, list):
        return evidence
    try:
        return json.loads(row.get("EvidenciaJSON") or "[]")
    except Exception:
        return []


def feedback_widget(cluster_id: str, title: str, suggested_action: str, key: str) -> None:
    with st.popover("Registrar decision"):
        action = st.selectbox(
            "Que hiciste",
            ["", "Publicar ahora", "Actualizar una nota", "Seguir esperando", "Verificar", "Descartar"],
            key=f"action_{key}",
        )
        useful = st.selectbox("Fue util?", ["", "Si", "No"], key=f"useful_{key}")
        article = st.selectbox("Termino en nota?", ["", "Si", "No"], key=f"article_{key}")
        comment = st.text_area("Comentario opcional", key=f"comment_{key}")
        if st.button("Guardar", key=f"save_{key}", type="primary"):
            if not action:
                st.warning("Elegi una accion.")
            elif store.guardar_feedback(cluster_id, title, suggested_action, action, useful, article, comment):
                st.success("Decision guardada.")
            else:
                st.error("No se pudo guardar el feedback.")


def render_recommendation(row: dict, idx: int, compact: bool = False) -> None:
    priority = as_int(row.get("Prioridad"))
    confidence = as_int(row.get("Confianza"))
    action = row.get("Accion") or "OBSERVAR"
    with st.container(border=True):
        left, right = st.columns([5.2, 1.2])
        with left:
            st.markdown(
                f"### {title_link(row.get('Titulo',''), row.get('URL',''))}",
                unsafe_allow_html=True,
            )
            st.caption(
                f"{row.get('Radar','OPERATIVO LOCAL')} | {action} | prioridad {priority}/100 | "
                f"confianza {confidence}% | {row.get('Medios','0')} medios | "
                f"cobertura: {row.get('CoberturaOle','')}"
            )
            if row.get("Motivo"):
                st.write(row.get("Motivo"))
            if row.get("TituloOle"):
                st.markdown(
                    "**Coincidencia detectada en Ole:** " +
                    title_link(row.get("TituloOle", ""), row.get("URLOle", "")),
                    unsafe_allow_html=True,
                )
        with right:
            feedback_widget(
                row.get("ClusterID", ""), row.get("Titulo", ""), action,
                f"rec_{idx}_{row.get('RecommendationID','')}",
            )
        if not compact:
            evidence = evidence_from_recommendation(row)
            if evidence:
                with st.expander(f"Ver evidencia ({len(evidence)})"):
                    for item in evidence:
                        publisher = item.get("publisher") or item.get("configured_source") or "Fuente"
                        st.markdown(
                            f"- **{html.escape(str(publisher))}:** "
                            f"{title_link(item.get('title',''), item.get('url',''))}",
                            unsafe_allow_html=True,
                        )


def evidence_from_discovery(row: dict) -> list[dict]:
    evidence = row.get("Evidencia")
    if isinstance(evidence, list):
        return evidence
    try:
        return json.loads(row.get("EvidenciaJSON") or "[]")
    except Exception:
        return []


def render_discovery(row: dict, idx: int, compact: bool = False) -> None:
    with st.container(border=True):
        left, right = st.columns([5.2, 1.2])
        with left:
            st.markdown(
                f"### {title_link(row.get('Titulo',''), row.get('URL',''))}",
                unsafe_allow_html=True,
            )
            st.caption(
                f"{row.get('Estado') or row.get('Categoria','HALLAZGO')} | {row.get('Categoria','')} | score {row.get('Score','0')}/100 | "
                f"valor Argentina {row.get('ValorArgentina','0')}/100 | "
                f"{row.get('Medios','0')} publishers"
            )
            if row.get("PorQueImporta"):
                st.write(f"**Por que puede importar:** {row.get('PorQueImporta')}")
            if row.get("Motivo"):
                st.write(row.get("Motivo"))
            if row.get("Angulo"):
                st.write(f"**Enfoque sugerido:** {row.get('Angulo')}")
            if row.get("Formato"):
                st.write(f"**Formato:** {row.get('Formato')}")
            if row.get("TituloOle"):
                st.markdown(
                    "**Posible coincidencia en Ole:** " +
                    title_link(row.get("TituloOle", ""), row.get("URLOle", "")),
                    unsafe_allow_html=True,
                )
        with right:
            feedback_widget(
                row.get("DiscoveryID", ""), row.get("Titulo", ""), "HALLAZGO",
                f"disc_{idx}_{row.get('DiscoveryID','')}",
            )
        if not compact:
            evidence = evidence_from_discovery(row)
            if evidence:
                with st.expander(f"Ver fuentes ({len(evidence)})"):
                    for item in evidence:
                        st.markdown(
                            f"- **{html.escape(str(item.get('publisher') or item.get('source_name') or 'Fuente'))}:** "
                            f"{title_link(item.get('title',''), item.get('url',''))}",
                            unsafe_allow_html=True,
                        )


def render_theme(row: dict, idx: int) -> None:
    with st.container(border=True):
        st.markdown(f"### {title_link(row.get('Titulo',''), row.get('URL',''))}", unsafe_allow_html=True)
        st.caption(
            f"{row.get('Accion','OBSERVAR')} | {row.get('Medios','0')} medios | "
            f"Ole: {'si' if is_yes(row.get('TieneOle')) else 'no'} | momentum {row.get('Momentum','0')}"
        )
        if row.get("Motivo"):
            st.write(row.get("Motivo"))
        evidence = evidence_from_theme(row)
        if evidence:
            with st.expander(f"Publicaciones relacionadas ({len(evidence)})"):
                for item in evidence:
                    publisher = item.get("fuente") or item.get("canal") or "Fuente"
                    st.markdown(
                        f"- **{html.escape(str(publisher))}:** "
                        f"{title_link(item.get('titulo',''), item.get('url',''))}",
                        unsafe_allow_html=True,
                    )
        feedback_widget(
            row.get("ClusterID", ""), row.get("Titulo", ""), row.get("Accion", ""),
            f"theme_{idx}_{row.get('ClusterID','')}",
        )


def render_change(row: dict, idx: int) -> None:
    with st.container(border=True):
        st.markdown(f"### {title_link(row.get('Titulo',''), row.get('URL',''))}", unsafe_allow_html=True)
        st.caption(
            f"{row.get('TipoCambio','CAMBIO')} | {row.get('Accion','OBSERVAR')} | "
            f"prioridad {row.get('Prioridad','0')} | medios {row.get('MediosAntes','0')} → {row.get('MediosAhora','0')}"
        )
        if row.get("QueCambio"):
            st.write(row.get("QueCambio"))
        if row.get("TituloOle"):
            st.markdown(
                "**Nota de Ole vinculada:** " + title_link(row.get("TituloOle", ""), row.get("URLOle", "")),
                unsafe_allow_html=True,
            )
        if row.get("Motivo"):
            with st.expander("Ver criterio y evidencia"):
                st.write(row.get("Motivo"))
        feedback_widget(
            row.get("ClusterID", ""), row.get("Titulo", ""), row.get("Accion", ""),
            f"change_{idx}_{row.get('ChangeID','')}",
        )




def render_cut_quality(control: dict) -> None:
    state = str(control.get("calidad_corte") or "").upper()
    if not state:
        return
    pct = control.get("cobertura_fuentes_pct") or ""
    ok = control.get("fuentes_ok") or "0"
    total = control.get("fuentes_total") or "0"
    last_full = control.get("ultima_actualizacion_completa") or control.get("ultima_actualizacion_snapshot") or ""
    detail = control.get("calidad_detalle") or ""
    if state == "COMPLETO":
        st.success(f"Corte completo: {ok}/{total} fuentes ({pct}%).")
    elif state == "DEGRADADO":
        message = f"Corte parcial: {ok}/{total} fuentes ({pct}%). Se conserva el ultimo panorama completo"
        if last_full:
            message += f" de {str(last_full).replace('T', ' ')[:19]}"
        message += ". Las novedades visibles provienen de las fuentes que si respondieron."
        st.warning(message)
        if detail:
            st.caption(detail)
    else:
        st.error(f"Corte critico: {ok}/{total} fuentes ({pct}%). El panorama anterior no fue reemplazado.")

def page_now(data: dict) -> None:
    control = data["control"]
    summary = data.get("summary") or {}
    changes = data.get("changes") or []
    discoveries = data["discoveries"]
    sources = data["sources"]

    st.title("Monitor Deportivo V11")
    st.caption("Un resumen del corte, los cambios concretos para agregar y un radar de hallazgos que evita navegar fuente por fuente.")
    render_cut_quality(control)
    last = control.get("ultima_actualizacion", "Sin datos")
    actionable_changes = [
        row for row in changes
        if row.get("Accion") in {"PUBLICAR AHORA", "ACTUALIZAR", "VERIFICAR"}
        and as_int(row.get("Prioridad")) >= 60
    ]
    strong_findings = [d for d in discoveries if (d.get("Estado") or "") in {"HALLAZGO FUERTE", "CANDIDATO"}]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ultima actualizacion", last.replace("T", " ")[:19])
    c2.metric("Cambios accionables", len(actionable_changes))
    c3.metric("Hallazgos y candidatos", len(strong_findings))
    c4.metric("Fuentes activas", f"{control.get('fuentes_ok','0')}/{control.get('fuentes_total','0')}")

    st.subheader(summary.get("Titulo") or "Resumen del corte")
    if summary.get("Texto"):
        st.text(summary.get("Texto"))
    else:
        st.info("Todavia no se genero el resumen comparado. Ejecuta una nueva corrida: la primera crea la base y la segunda muestra los cambios.")

    tab_changes, tab_findings, tab_panorama = st.tabs([
        "Que cambio", "Hallazgos", "Panorama completo"
    ])
    with tab_changes:
        st.subheader("Que cambio desde el corte anterior")
        st.caption("Solo aparecen novedades, crecimiento, cambios de cobertura o acciones nuevas. Los temas estables no se repiten.")
        if not changes:
            st.info("No se detectaron cambios relevantes desde el corte anterior.")
        for idx, row in enumerate(changes[:20]):
            render_change(row, idx)

    with tab_findings:
        st.subheader("Historias para descubrir")
        st.caption("Siempre muestra los mejores candidatos internacionales del corte, aunque ninguno alcance la categoria de hallazgo fuerte.")
        if not discoveries:
            st.warning("No hubo material internacional util en las fuentes del corte. Revisa V9_Fuentes y los radares de descubrimiento.")
        for idx, row in enumerate(discoveries[:15]):
            render_discovery(row, idx, compact=True)

    with tab_panorama:
        st.caption("Inventario amplio para consultar. No equivale a una lista de temas para publicar.")
        for idx, row in enumerate(data["themes"][:40]):
            render_theme(row, idx)

    errors = [source for source in sources if source.get("Estado") != "ok"]
    with st.expander(f"Salud de fuentes: {len(errors)} con problemas"):
        if not errors:
            st.success("Todas las fuentes del snapshot respondieron.")
        for source in errors:
            st.write(f"**{source.get('Fuente')}** - {source.get('Error') or 'sin noticias'}")

def page_assistant(data: dict) -> None:
    st.title("Asistente editorial V10")
    recs = data["recommendations"]
    discoveries = data["discoveries"]
    opportunities = data["opportunities"]
    reports = data["reports"]

    tab_recs, tab_disc, tab_opps, tab_reports = st.tabs([
        "Acciones", "Hallazgos", "Ideas derivadas", "Informes"
    ])
    with tab_recs:
        st.info("Solo propone publicar, actualizar o verificar cuando detecta una brecha o un dato nuevo respecto de la cobertura de Ole.")
        min_priority = st.slider("Prioridad minima", 0, 100, 55, 5)
        filtered = [r for r in recs if as_int(r.get("Prioridad")) >= min_priority]
        st.caption(f"{len(filtered)} acciones")
        for idx, row in enumerate(filtered[:60]):
            render_recommendation(row, 1000 + idx)

    with tab_disc:
        min_score = st.slider("Score minimo de descubrimiento", 0, 100, 55, 5)
        filtered = [d for d in discoveries if as_int(d.get("Score")) >= min_score]
        st.caption(f"{len(filtered)} hallazgos")
        for idx, row in enumerate(filtered[:60]):
            render_discovery(row, 2000 + idx)

    with tab_opps:
        if not opportunities:
            st.info("No hay ideas derivadas en este corte.")
        for row in opportunities:
            with st.container(border=True):
                st.markdown(f"### {row.get('Titulo','')}")
                st.caption(
                    f"Formato: {row.get('Formato','')} | score {row.get('Score','0')} | "
                    f"esfuerzo {row.get('Esfuerzo','')} | vigencia {row.get('Vigencia','')}"
                )
                st.write(f"**Tema de origen:** {row.get('TemaOrigen','')}")
                st.write(f"**Por que ahora:** {row.get('PorQueAhora','')}")
                st.write(f"**Angulo:** {row.get('Angulo','')}")
                st.write(f"**Titulo tentativo:** {row.get('TituloSugerido','')}")

    with tab_reports:
        if not reports:
            st.info("No hay informes guardados todavia.")
        for row in reversed(reports):
            with st.expander(f"{row.get('FechaHora','')} - {row.get('Titulo','Informe')}"):
                st.text(row.get("Texto", ""))

def page_explore(data: dict) -> None:
    themes = data["themes"]
    st.title("Explorar panorama")
    query = st.text_input("Buscar tema, equipo, jugador o competencia")
    c1, c2, c3 = st.columns(3)
    with c1:
        actions = st.multiselect("Accion", sorted({t.get("Accion", "") for t in themes if t.get("Accion")}))
    with c2:
        without_ole = st.checkbox("Solo temas que Ole no tiene")
    with c3:
        min_media = st.number_input("Minimo de medios", min_value=1, max_value=30, value=2)
    filtered = []
    for row in themes:
        text = f"{row.get('Titulo','')} {row.get('MediosOriginales','')}".lower()
        if query and query.lower() not in text:
            continue
        if actions and row.get("Accion") not in actions:
            continue
        if without_ole and is_yes(row.get("TieneOle")):
            continue
        if as_int(row.get("Medios")) < min_media:
            continue
        filtered.append(row)
    st.caption(f"{len(filtered)} temas")
    for idx, row in enumerate(filtered[:100]):
        render_theme(row, idx)


def page_produce(data: dict) -> None:
    themes = data["themes"]
    discoveries = data["discoveries"]
    st.title("Producir")
    st.caption("Podes trabajar sobre una accion local o convertir un hallazgo internacional en una historia con mirada argentina.")

    theme_options = {f"[LOCAL · {t.get('Accion','OBSERVAR')}] {t.get('Titulo','')}": t for t in themes}
    discovery_options = {f"[HALLAZGO · {d.get('Categoria','')}] {d.get('Titulo','')}": d for d in discoveries}
    selected_theme_keys = st.multiselect(
        "Acciones o temas locales", list(theme_options.keys()), max_selections=4
    )
    selected_discovery_keys = st.multiselect(
        "Hallazgos del exterior", list(discovery_options.keys()), max_selections=4
    )
    selected_themes = [theme_options[key] for key in selected_theme_keys]
    selected_discoveries = [discovery_options[key] for key in selected_discovery_keys]

    if selected_themes or selected_discoveries:
        st.subheader("Material disponible")
        for row in selected_themes:
            st.markdown(f"**{row.get('Titulo')}**")
            for item in evidence_from_theme(row):
                st.markdown(
                    f"- {item.get('fuente')}: {title_link(item.get('titulo',''), item.get('url',''))}",
                    unsafe_allow_html=True,
                )
        for row in selected_discoveries:
            st.markdown(f"**{row.get('Titulo')}**")
            st.write(f"Enfoque sugerido: {row.get('Angulo','')}")
            for item in evidence_from_discovery(row):
                st.markdown(
                    f"- {item.get('publisher') or item.get('source_name')}: "
                    f"{title_link(item.get('title',''), item.get('url',''))}",
                    unsafe_allow_html=True,
                )

    output_type = st.selectbox(
        "Que necesitas",
        ["Brief editorial", "Angulos y titulos", "Resumen comparado", "Borrador de nota"],
    )
    instructions = st.text_area("Indicaciones adicionales", placeholder="Extension, foco o dato a verificar")
    has_selection = bool(selected_themes or selected_discoveries)
    if st.button("Generar", type="primary", disabled=not has_selection):
        api_key = _secret("ANTHROPIC_API_KEY")
        if not api_key:
            st.error("Falta ANTHROPIC_API_KEY en los Secrets de Streamlit.")
        else:
            context = []
            for row in selected_themes:
                context.append({
                    "tipo": "operativo local", "tema": row.get("Titulo"),
                    "accion": row.get("Accion"), "motivo": row.get("Motivo"),
                    "fuentes": evidence_from_theme(row),
                })
            for row in selected_discoveries:
                context.append({
                    "tipo": "hallazgo internacional", "tema": row.get("Titulo"),
                    "categoria": row.get("Categoria"), "valor_argentina": row.get("ValorArgentina"),
                    "motivo": row.get("Motivo"), "angulo_sugerido": row.get("Angulo"),
                    "fuentes": evidence_from_discovery(row),
                })
            prompt = f"""Sos editor deportivo de Ole. Prepara un {output_type.lower()} en espanol rioplatense.
No inventes datos. Separa coincidencias, versiones y datos que requieren verificacion.
Para los hallazgos internacionales, explica por que pueden interesar al lector deportivo promedio de Argentina y evita una traduccion plana.
Indicaciones: {instructions or 'ninguna'}
Material: {json.dumps(context, ensure_ascii=False)}"""
            with st.spinner("Analizando material..."):
                try:
                    text = monitor_core.call_claude(
                        prompt, api_key, max_tokens=2200, modelo=monitor_core.MODELO_ECONOMICO
                    )
                    st.markdown(text)
                except Exception as exc:
                    st.error(str(exc))

def _row_link(title: str, url: str) -> str:
    return title_link(title, url)


def _current_cut(rows: list[dict]) -> str:
    return str(rows[0].get("Corte") or "") if rows else ""


def render_summary_row(row: dict) -> None:
    action = row.get("Accion") or "INFORMARSE"
    with st.container(border=True):
        st.markdown(f"### {row.get('Orden','')}. {_row_link(row.get('Tema',''), row.get('URLPrincipal',''))}", unsafe_allow_html=True)
        st.caption(
            f"{row.get('Importancia','')} | {row.get('Seccion','')} | {action} | "
            f"prioridad {row.get('Prioridad','0')} | {row.get('Medios','0')} medios | Olé: {row.get('EstadoOle','')}"
        )
        if row.get("QuePaso"):
            st.write(row.get("QuePaso"))
        if row.get("QueCambio"):
            st.write(f"**Qué cambió:** {row.get('QueCambio')}")
        if row.get("PorQueImporta"):
            st.write(f"**Por qué importa:** {row.get('PorQueImporta')}")
        if row.get("NotaOle"):
            st.markdown("**Cobertura relacionada de Olé:** " + _row_link(row.get("NotaOle", ""), row.get("URLOle", "")), unsafe_allow_html=True)
        if row.get("Fuentes"):
            st.caption(f"Fuentes: {row.get('Fuentes')}")


def render_action_editor(row: dict, idx: int) -> None:
    options = ["PENDIENTE", "EN CURSO", "HECHO", "DESCARTADO", "SEGUIR"]
    current = row.get("Estado", "PENDIENTE")
    with st.container(border=True):
        left, right = st.columns([4.8, 1.5])
        with left:
            st.markdown(f"### {row.get('Accion','')} · {row.get('Tema','')}")
            st.caption(f"Prioridad {row.get('Prioridad','0')} | estado {current}")
            if row.get("DatoNuevo"):
                st.write(f"**Dato o cambio:** {row.get('DatoNuevo')}")
            if row.get("NotaOle"):
                st.markdown("**Nota de Olé:** " + _row_link(row.get("NotaOle", ""), row.get("URLOle", "")), unsafe_allow_html=True)
            if row.get("Fuentes"):
                st.caption(f"Fuentes: {row.get('Fuentes')}")
        with right:
            status = st.selectbox(
                "Estado", options, index=options.index(current) if current in options else 0,
                key=f"action_status_{idx}_{row.get('ActionID','')}",
            )
            note = st.text_input("Nota", value=row.get("Notas", ""), key=f"action_note_{idx}_{row.get('ActionID','')}")
            if st.button("Guardar", key=f"action_save_{idx}_{row.get('ActionID','')}"):
                if store.actualizar_accion_editor(row.get("ActionID", ""), status, note):
                    load_data.clear()
                    st.success("Acción actualizada.")
                    st.rerun()
                else:
                    st.error("No se pudo actualizar.")


def _build_paid_prompt(rows: list[dict], cut_key: str) -> str:
    material = []
    for row in rows[:40]:
        material.append({
            "seccion": row.get("Seccion"), "tema": row.get("Tema"),
            "que_paso": row.get("QuePaso"), "que_cambio": row.get("QueCambio"),
            "por_que_importa": row.get("PorQueImporta"), "estado_ole": row.get("EstadoOle"),
            "nota_ole": row.get("NotaOle"), "accion": row.get("Accion"),
            "fuentes": row.get("Fuentes"), "urls": row.get("URLsFuentes"),
        })
    return f'''Sos un editor jefe deportivo de Olé. Redactá un PARTE EDITORIAL AMPLIADO en español rioplatense sobre el corte {cut_key}.
Usá exclusivamente el material suministrado. No inventes datos, horarios, estados oficiales ni citas.
Diferenciá OFICIAL, VERSION, A CONFIRMAR y COINCIDENCIA DUDOSA cuando corresponda.
El informe debe tener:
1. FÚTBOL ARGENTINO.
2. SELECCIÓN / ARGENTINOS EN EL EXTERIOR.
3. INTERNACIONAL Y HALLAZGOS.
4. OTROS DEPORTES.
5. PARA SEGUIR EN LAS PRÓXIMAS HORAS.
6. CAMBIOS RESPECTO DEL CORTE ANTERIOR.
7. CIERRE EJECUTIVO con imprescindibles, oportunidades no publicadas, notas para actualizar y alertas de verificación.
Para los temas principales usá: NOVEDAD, QUÉ PASÓ, ESTADO, POR QUÉ IMPORTA, COBERTURA EN OLÉ, ACCIÓN SUGERIDA y FUENTES.
No recomiendes una noticia nueva si Olé ya la cubrió sin un dato posterior. En ese caso indicá INFORMARSE, SEGUIR o NO HACER OTRA NOTA.
Priorizá historias raras o internacionales con valor para el lector deportivo argentino.
Material estructurado: {json.dumps(material, ensure_ascii=False)}'''


def paid_report_block(data: dict) -> None:
    rows = data.get("summary4h") or []
    cut_key = _current_cut(rows)
    if not rows:
        st.info("Todavía no existe un resumen gratuito de cuatro horas.")
        return
    existing = store.parte_ia_para_corte(cut_key)
    st.subheader("Parte editorial ampliado con IA")
    st.caption("No se genera automáticamente. Solo consume Anthropic cuando confirmás y pulsás el botón.")
    if existing:
        st.success(f"Ya existe un parte para este corte, generado {existing.get('FechaHora','')}.")
        with st.expander(existing.get("Titulo") or "Abrir parte ampliado", expanded=False):
            st.markdown(existing.get("Texto", ""))
        regenerate = st.checkbox("Quiero regenerarlo y aceptar una nueva llamada paga", key=f"regen_{cut_key}")
        button_label = "Regenerar parte con IA"
        disabled = not regenerate
    else:
        st.info("Informe ampliado: no generado. Costo de IA utilizado en este corte: ninguno.")
        confirm = st.checkbox("Confirmo que quiero generar un informe pago bajo demanda", key=f"confirm_ai_{cut_key}")
        button_label = "Generar parte editorial ampliado"
        disabled = not confirm
    if st.button(button_label, type="primary", disabled=disabled, key=f"paid_part_{cut_key}"):
        api_key = _secret("ANTHROPIC_API_KEY")
        if not api_key:
            st.error("Falta ANTHROPIC_API_KEY en los Secrets de Streamlit.")
            return
        prompt = _build_paid_prompt(rows, cut_key)
        with st.spinner("Generando el parte ampliado bajo demanda..."):
            try:
                text = monitor_core.call_claude(prompt, api_key, max_tokens=5000, modelo=monitor_core.MODELO_ECONOMICO)
                title = f"Parte editorial ampliado · {cut_key}"
                store.guardar_parte_ia(cut_key, title, text, monitor_core.MODELO_ECONOMICO, len(rows), regeneration=bool(existing))
                st.success("Parte generado y guardado. Volver a abrirlo no consume IA.")
                st.markdown(text)
            except Exception as exc:
                st.error(str(exc))


def page_desk(data: dict) -> None:
    rows = data.get("summary4h") or []
    actions = [row for row in data.get("actions_editor", []) if row.get("Estado") not in {"HECHO", "DESCARTADO"}]
    findings = data.get("findings_editor") or []
    ole_today = data.get("ole_today") or []
    ole_coverage = data.get("ole_coverage_editor") or []
    today_ar = datetime.now(TZ_AR).date()
    def _row_date(value):
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=TZ_AR)
            return parsed.astimezone(TZ_AR).date()
        except Exception:
            return None
    ole_published_today = sum(1 for row in ole_today if _row_date(row.get("FechaPublicacion")) == today_ar)
    ole_updated_only = sum(
        1 for row in ole_today
        if _row_date(row.get("FechaActualizacion")) == today_ar
        and _row_date(row.get("FechaPublicacion")) != today_ar
    )
    source_rows = data.get("sources_editor") or []
    st.title("Mesa editorial V11")
    st.caption("Una sola pantalla para saber qué pasó, qué cambió, qué publicó Olé, qué falta y qué conviene seguir.")
    render_cut_quality(data.get("control") or {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temas del corte", len(rows))
    c2.metric("Acciones pendientes", len(actions))
    c3.metric("Hallazgos", len(findings))
    ole_status = str((data.get("control") or {}).get("ole_cobertura_dia") or "").strip().lower()
    ole_pages = (data.get("control") or {}).get("ole_paginas_revisadas") or ""
    ole_metric_delta = f"{ole_updated_only} actualizada(s) · {ole_pages} pág." if ole_pages else f"{ole_updated_only} actualizada(s)"
    c4.metric("Publicadas por Olé hoy", ole_published_today, delta=ole_metric_delta)
    if rows:
        st.info(f"Corte: {rows[0].get('Desde','')} a {rows[0].get('Hasta','')} · actualizado {rows[0].get('Generado','')}")
    tabs = st.tabs(["Resumen 4H", "Acciones", "Olé hoy", "Hallazgos", "Fuentes", "Parte ampliado"])
    with tabs[0]:
        mode = st.radio("Lectura", ["2 minutos", "Completa"], horizontal=True)
        limit = 10 if mode == "2 minutos" else 40
        for row in rows[:limit]:
            render_summary_row(row)
        if store.url_planilla():
            st.link_button("Abrir la planilla", store.url_planilla())
    with tabs[1]:
        if not actions:
            st.success("No hay acciones pendientes en este corte.")
        for idx, row in enumerate(actions[:50]):
            render_action_editor(row, idx)
    with tabs[2]:
        st.subheader("Memoria viva de lo publicado por Olé")
        st.caption("Las notas se agrupan por tema para evitar recomendar otra pieza general cuando ya existen varios enfoques.")
        control = data.get("control") or {}
        ole_status = str(control.get("ole_cobertura_dia") or "").strip().lower()
        ole_detail = (
            f"{control.get('ole_paginas_revisadas','')} páginas revisadas · "
            f"{control.get('ole_notas_listado','')} notas recuperadas"
        ).strip(" ·")
        ole_range = ""
        if control.get("ole_primera_nota_hoy") or control.get("ole_ultima_nota_hoy"):
            ole_range = f" · rango fechado: {control.get('ole_primera_nota_hoy','?')} a {control.get('ole_ultima_nota_hoy','?')}"
        m1, m2, m3 = st.columns(3)
        m1.metric("Publicadas hoy", ole_published_today)
        m2.metric("Actualizadas hoy", ole_updated_only)
        m3.metric("Temas agrupados", len(ole_coverage))
        if ole_status == "completa":
            st.success(f"Cobertura del día completa: {ole_detail}{ole_range}")
        elif ole_status == "estimada":
            st.warning(f"Cobertura del día estimada: {ole_detail}{ole_range}. El listado no permitió confirmar con certeza la frontera de las 00:00.")
        elif ole_status:
            st.warning(f"Cobertura de Olé parcial: {ole_detail}{ole_range}. Puede faltar parte del día.")
        for group in ole_coverage[:40]:
            with st.expander(f"{group.get('Tema','')} · {group.get('Piezas','0')} pieza(s)"):
                st.write(f"**Enfoques:** {group.get('Enfoques','')}")
                st.write(f"**Acción:** {group.get('Accion','')}")
                if is_yes(group.get("Sobrecobertura")):
                    st.warning("Posible sobrecobertura: buscar un ángulo distinto antes de sumar otra nota general.")
                if group.get("NovedadesExternas"):
                    st.write(f"**Novedades externas relacionadas:** {group.get('NovedadesExternas')}")
                if group.get("UltimoTitulo"):
                    st.markdown(_row_link(group.get("UltimoTitulo", ""), group.get("UltimaURL", "")), unsafe_allow_html=True)
        with st.expander("Línea de tiempo de publicaciones"):
            st.dataframe(ole_today[:200], use_container_width=True, hide_index=True)
    with tabs[3]:
        if not findings:
            st.info("No hay hallazgos en este corte. El resumen general sigue disponible.")
        for row in findings[:30]:
            with st.container(border=True):
                st.markdown(f"### {_row_link(row.get('Tema',''), row.get('URLPrincipal',''))}", unsafe_allow_html=True)
                st.caption(f"Prioridad {row.get('Prioridad','')} | {row.get('Accion','')} | Olé: {row.get('EstadoOle','')}")
                st.write(row.get("QuePaso", ""))
                if row.get("PorQueImporta"):
                    st.write(f"**Valor para Argentina:** {row.get('PorQueImporta')}")
                st.caption(f"Fuentes: {row.get('Fuentes','')}")
    with tabs[4]:
        broken = [row for row in source_rows if row.get("Estado") != "SALUDABLE"]
        st.metric("Fuentes que requieren atención", len(broken))
        st.dataframe(source_rows, use_container_width=True, hide_index=True)
    with tabs[5]:
        paid_report_block(data)


def page_social_inbox(data: dict) -> None:
    st.title("Buzón social")
    st.caption("Pegá enlaces de X, Instagram, YouTube, TikTok, Bluesky u otras redes. El próximo corte los incorpora sin necesitar una API paga.")
    with st.form("social_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        platform = c1.selectbox("Plataforma", ["X/Twitter", "Instagram", "YouTube", "TikTok", "Bluesky", "Facebook", "Otra"])
        author = c2.text_input("Autor o cuenta")
        title = st.text_input("Título o descripción breve")
        url = st.text_input("Enlace")
        note = st.text_area("Qué viste o qué habría que verificar")
        why = st.text_input("Por qué puede importar")
        if st.form_submit_button("Agregar al radar", type="primary"):
            if not url:
                st.warning("Pegá un enlace.")
            elif store.agregar_buzon_social(platform, author, title, url, note, why):
                load_data.clear()
                st.success("Enlace agregado al buzón.")
                st.rerun()
            else:
                st.error("No se pudo guardar.")
    items = data.get("social_inbox") or []
    st.subheader("Enlaces cargados")
    for idx, row in enumerate(reversed(items[-100:])):
        with st.container(border=True):
            st.markdown(f"### {_row_link(row.get('Titulo') or 'Enlace social', row.get('URL',''))}", unsafe_allow_html=True)
            st.caption(f"{row.get('Plataforma','')} · {row.get('Autor','')} · {row.get('Estado','')}")
            if row.get("Nota"):
                st.write(row.get("Nota"))
            options = ["PENDIENTE", "SEGUIR", "HECHO", "DESCARTADO"]
            current = row.get("Estado", "PENDIENTE")
            status = st.selectbox("Estado", options, index=options.index(current) if current in options else 0, key=f"social_status_{idx}_{row.get('SocialID','')}")
            if st.button("Actualizar", key=f"social_update_{idx}_{row.get('SocialID','')}"):
                store.actualizar_buzon_social(row.get("SocialID", ""), status)
                load_data.clear()
                st.rerun()


def page_predictive() -> None:
    st.title("Predictivo")
    pack = load_model()
    metrics = predictor_runtime.cargar_metricas()
    if pack is None:
        st.warning("Todavia no hay un modelo publicado en models/modelo_semaforo.joblib.")
        st.info("Usa el notebook de colab para entrenar y subir el modelo aprobado.")
        return
    if metrics:
        st.caption(
            f"Modelo: {metrics.get('fecha_entrenamiento','')} | "
            f"precision de prueba: {metrics.get('accuracy','s/d')}"
        )
    title = st.text_input("Titulo o propuesta")
    c1, c2, c3 = st.columns(3)
    with c1:
        section = st.text_input("Seccion")
    with c2:
        hour = st.text_input("Hora prevista", value=datetime.now(TZ_AR).strftime("%H:%M"))
    with c3:
        in_panorama = st.checkbox("El tema esta en el panorama")
    if st.button("Evaluar potencial", type="primary", disabled=not title.strip()):
        try:
            pred = predictor_runtime.predecir(pack, title, section, in_panorama, hour)
            labels = {"verde": "ALTO", "amarillo": "MEDIO", "rojo": "BAJO"}
            st.metric("Potencial estimado", labels.get(pred["clase"], pred["clase"].upper()))
            st.write("Probabilidades:", " | ".join(
                f"{labels.get(label,label)} {prob:.0%}" for label, prob in pred["probas"]
            ))
            if pred.get("empuja"):
                st.success("Favorece: " + ", ".join(pred["empuja"]))
            if pred.get("frena"):
                st.warning("Frena: " + ", ".join(pred["frena"]))
            st.caption("Es una ayuda editorial, no una garantia de audiencia.")
        except Exception as exc:
            st.error(f"No se pudo evaluar: {exc}")


def page_config(data: dict) -> None:
    st.title("Configuracion y control")
    if store.url_planilla():
        st.link_button("Abrir la planilla", store.url_planilla())
    prefix = store.prefix()
    st.write(
        f"Pestanas del monitor: **{prefix}Noticias, {prefix}Temas, {prefix}Fuentes, "
        f"{prefix}RESUMEN_4H, {prefix}ACCIONES, {prefix}OLE_HOY, {prefix}COBERTURA_OLE, "
        f"{prefix}HALLAZGOS, {prefix}FUENTES_EDITOR, {prefix}BUZON_SOCIAL y {prefix}PARTES_IA**. "
        "Las hojas tecnicas siguen disponibles como respaldo."
    )
    config = sheets_memoria.leer_config() if sheets_memoria.disponible() else {}
    if config:
        st.subheader("Configuracion editorial actual")
        st.json(config, expanded=False)
    st.subheader("Fuentes")
    st.dataframe([
        {
            "Fuente": source.get("Fuente"), "Estado": source.get("Estado"),
            "Noticias": as_int(source.get("Noticias")), "Canal": source.get("Canal"),
            "Duracion": as_float(source.get("DuracionSeg")), "Error": source.get("Error"),
        }
        for source in data["sources"]
    ], use_container_width=True, hide_index=True)
    st.subheader("Estado tecnico")
    st.json(data["control"], expanded=False)
    if data["agent_log"]:
        st.subheader("Ultimas ejecuciones del asistente")
        st.dataframe(data["agent_log"], use_container_width=True, hide_index=True)


with st.sidebar:
    st.header("Monitor V11")
    page = st.radio(
        "Ir a",
        ["Mesa editorial", "Buzón social", "Ahora técnico", "Asistente", "Explorar", "Producir", "Predictivo", "Configuracion"],
    )
    st.divider()
    if st.button("Recargar pantalla", use_container_width=True):
        load_data.clear()
        st.rerun()
    github_ready = bool(_secret("GITHUB_TOKEN") and _secret("GITHUB_REPO"))
    if github_ready:
        if st.button("Buscar noticias ahora", use_container_width=True):
            ok, message = dispatch_workflow()
            (st.success if ok else st.warning)(message)
    else:
        st.caption("La actualización manual se ejecuta desde GitHub > Actions. El token de GitHub es opcional.")
    st.caption("La IA paga nunca corre sola: solo se activa desde Parte ampliado y con confirmación.")

if not store.disponible():
    st.error("No estan configurados GOOGLE_SERVICE_ACCOUNT_JSON y SHEET_ID.")
    st.stop()

data = load_data()
if not data["themes"] and not data["control"]:
    st.warning("La conexion funciona, pero todavia no existe un snapshot del monitor. Ejecuta el workflow una vez.")

if page == "Mesa editorial":
    page_desk(data)
elif page == "Buzón social":
    page_social_inbox(data)
elif page == "Ahora técnico":
    page_now(data)
elif page == "Asistente":
    page_assistant(data)
elif page == "Explorar":
    page_explore(data)
elif page == "Producir":
    page_produce(data)
elif page == "Predictivo":
    page_predictive()
else:
    page_config(data)
