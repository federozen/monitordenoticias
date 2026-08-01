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
    page_title="Monitor Deportivo V9",
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
        "opportunities": store.leer_oportunidades(),
        "reports": store.leer_informes(20),
        "agent_log": store.leer_agent_log(50),
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
                f"{action} | prioridad {priority}/100 | confianza {confidence}% | "
                f"{row.get('Medios','0')} medios originales | estado: {row.get('Estado','')}"
            )
            if row.get("Motivo"):
                st.write(row.get("Motivo"))
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


def page_now(data: dict) -> None:
    control = data["control"]
    recs = data["recommendations"]
    sources = data["sources"]
    st.title("Monitor Deportivo y asistente editorial")
    last = control.get("ultima_actualizacion", "Sin datos")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ultima actualizacion", last.replace("T", " ")[:19])
    c2.metric("Noticias", control.get("noticias", "0"))
    c3.metric("Recomendaciones", len(recs))
    c4.metric("Fuentes activas", f"{control.get('fuentes_ok','0')}/{control.get('fuentes_total','0')}")

    urgent = [r for r in recs if as_int(r.get("Prioridad")) >= 60]
    st.subheader("Que hacer ahora")
    if not urgent:
        st.info("No hay recomendaciones de prioridad alta en el ultimo corte.")
    for idx, row in enumerate(urgent[:8]):
        render_recommendation(row, idx, compact=True)

    errors = [source for source in sources if source.get("Estado") != "ok"]
    with st.expander(f"Salud de fuentes: {len(errors)} con problemas"):
        if not errors:
            st.success("Todas las fuentes del snapshot respondieron.")
        for source in errors:
            st.write(f"**{source.get('Fuente')}** - {source.get('Error') or 'sin noticias'}")


def page_assistant(data: dict) -> None:
    st.title("Asistente editorial proactivo")
    recs = data["recommendations"]
    opportunities = data["opportunities"]
    reports = data["reports"]

    tab_recs, tab_opps, tab_reports = st.tabs(["Recomendaciones", "Temas para hacer", "Informes"])
    with tab_recs:
        min_priority = st.slider("Prioridad minima", 0, 100, 45, 5)
        actions = sorted({row.get("Accion", "") for row in recs if row.get("Accion")})
        selected = st.multiselect("Acciones", actions)
        filtered = [
            row for row in recs
            if as_int(row.get("Prioridad")) >= min_priority
            and (not selected or row.get("Accion") in selected)
        ]
        st.caption(f"{len(filtered)} recomendaciones")
        for idx, row in enumerate(filtered[:80]):
            render_recommendation(row, 1000 + idx)

    with tab_opps:
        if not opportunities:
            st.info("Todavia no hay oportunidades generadas. Ejecuta el workflow V9 una vez.")
        for idx, row in enumerate(opportunities):
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
    st.title("Producir")
    options = {f"[{t.get('Accion','OBSERVAR')}] {t.get('Titulo','')}": t for t in themes}
    selected_keys = st.multiselect("Elegi uno o mas temas", list(options.keys()), max_selections=5)
    selected = [options[key] for key in selected_keys]
    if selected:
        st.subheader("Material verificado")
        for row in selected:
            st.markdown(f"**{row.get('Titulo')}**")
            for item in evidence_from_theme(row):
                st.markdown(
                    f"- {item.get('fuente')}: {title_link(item.get('titulo',''), item.get('url',''))}",
                    unsafe_allow_html=True,
                )

    output_type = st.selectbox(
        "Que necesitas",
        ["Brief editorial", "Angulos y titulos", "Resumen comparado", "Borrador de nota"],
    )
    instructions = st.text_area("Indicaciones adicionales", placeholder="Extension, foco o dato a verificar")
    if st.button("Generar", type="primary", disabled=not selected):
        api_key = _secret("ANTHROPIC_API_KEY")
        if not api_key:
            st.error("Falta ANTHROPIC_API_KEY en los Secrets de Streamlit.")
        else:
            context = []
            for row in selected:
                context.append({
                    "tema": row.get("Titulo"), "accion": row.get("Accion"),
                    "motivo": row.get("Motivo"), "fuentes": evidence_from_theme(row),
                })
            prompt = f"""Sos editor deportivo de Ole. Prepara un {output_type.lower()} en espanol rioplatense.
No inventes datos. Separa coincidencias, versiones y datos que requieren verificacion.
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
        f"Pestanas V9: **{prefix}Noticias, {prefix}Temas, {prefix}Fuentes, "
        f"{prefix}Recomendaciones, {prefix}Oportunidades, {prefix}Informes, "
        f"{prefix}Avisos y {prefix}AgentLog**."
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
    st.header("Monitor V9")
    page = st.radio(
        "Ir a",
        ["Ahora", "Asistente", "Explorar", "Producir", "Predictivo", "Configuracion"],
    )
    st.divider()
    if st.button("Recargar pantalla", use_container_width=True):
        load_data.clear()
        st.rerun()
    if st.button("Buscar noticias ahora", use_container_width=True):
        ok, message = dispatch_workflow()
        (st.success if ok else st.warning)(message)
    st.caption("La busqueda y los agentes corren en GitHub. La app conserva el ultimo snapshot valido.")

if not store.disponible():
    st.error("No estan configurados GOOGLE_SERVICE_ACCOUNT_JSON y SHEET_ID.")
    st.stop()

data = load_data()
if not data["themes"] and not data["control"]:
    st.warning("La conexion funciona, pero todavia no existe un snapshot V9. Ejecuta el workflow una vez.")

if page == "Ahora":
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
