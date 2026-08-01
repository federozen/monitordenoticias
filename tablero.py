# -*- coding: utf-8 -*-
"""🚦 TABLERO PREDICTIVO — app independiente del monitor.
Lee todo de la planilla (no scrapea): estado del dataset de métricas,
entrenamiento del semáforo, y el panorama del día clasificado 🟢🟡🔴.
Se despliega como segunda app de Streamlit desde este mismo repo
(main file: tablero.py) con los mismos secrets que la app principal.
"""
import streamlit as st
from collections import Counter

st.set_page_config(page_title="Tablero Predictivo", page_icon="🚦", layout="wide")

from monitor_core import entrenar_semaforo, predecir_semaforo, entrenar_detector, predecir_incendio  # noqa: E402
import sheets_memoria  # noqa: E402

st.title("🚦 Tablero Predictivo")
st.caption("El círculo de resultados: cuántos datos hay, qué tan bien predice el modelo, y el panorama de hoy semaforizado. No scrapea: lee la planilla que alimentan el vigía y los reportes diarios.")

if not sheets_memoria.disponible():
    st.error("Sin conexión con la planilla. Verificá que esta app tenga los mismos Secrets que la principal (Settings → Secrets).")
    st.stop()

# ─── 1) SALUD DEL DATASET ─────────────────────────────────────────────────────
st.header("📊 El dataset")
metricas = sheets_memoria.leer_metricas()
if not metricas:
    st.info("Todavía no hay métricas guardadas. Subí reportes diarios desde la app principal (pestaña 📈 Resultados).")
    st.stop()

por_fecha = Counter(m.get("Fecha", "") for m in metricas if m.get("Fecha"))
fechas = sorted(por_fecha.keys(), key=lambda f: (f.split("/")[1] if "/" in f else "0",
                                                 f.split("/")[0]))
c1, c2, c3, c4 = st.columns(4)
c1.metric("Notas acumuladas", f"{len(metricas):,}".replace(",", "."))
c2.metric("Días cargados", len(fechas))
c3.metric("Promedio por día", round(len(metricas) / max(len(fechas), 1)))
umbral = "🟢 listo" if len(metricas) >= 500 else ("🟡 preliminar" if len(metricas) >= 150 else "🔴 juntando")
c4.metric("Estado para entrenar", umbral)

with st.expander("Detalle por día (para detectar huecos o días flacos)"):
    for f in fechas:
        n = por_fecha[f]
        barra = "█" * min(n // 4, 20)
        alerta = "  ⚠️ día flaco (¿faltó re-subir?)" if n < 40 else ""
        st.text(f"{f}  {barra} {n}{alerta}")

st.markdown("---")

# ─── 2) EL MODELO ────────────────────────────────────────────────────────────
st.header("🧠 El modelo")
if st.button("Entrenar / actualizar con los datos de hoy", type="primary"):
    with st.spinner("Entrenando..."):
        import monitor_core as _mc
        _mc._HIST_PARA_MOMENTUM = sheets_memoria.leer_historial(60)
        pack = entrenar_semaforo(metricas)
        if "error" in pack:
            st.warning(pack["error"])
        else:
            st.session_state.pack = pack
            sheets_memoria.guardar_evolucion(pack, len(metricas))

pack = st.session_state.get("pack")
if pack:
    mejora = pack["acc"] - pack["acc_base"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Precisión", f"{pack['acc']:.0%}")
    m2.metric("Base (sin modelo)", f"{pack['acc_base']:.0%}")
    m3.metric("Mejora real", f"{mejora:+.0%}")
    m4.metric("Algoritmo ganador", "Random Forest" if pack["tipo"] == "rf" else "Reg. logística")
    if mejora < 0.05:
        st.warning("⚠️ El modelo todavía no le gana claro a la base. Con más días de datos, los patrones emergen — no lo uses para decidir aún.")
    elif pack.get("preliminar"):
        st.info("Modo preliminar (menos de 500 notas): orientativo.")
    st.caption("⬆️ Lo que empuja a 🟢: " + " · ".join(n for n, _ in pack["factores_verde"][:7]))
    st.caption("⬇️ Lo que frena: " + " · ".join(n for n, _ in reversed(pack["frena_verde"])))
    st.caption(f"Competencia interna: logística {pack['acc_logit']:.0%} vs Random Forest {pack['acc_rf']:.0%} — manda el mejor; las razones las explica siempre la logística.")

    evol = sheets_memoria.leer_evolucion()
    if evol:
        with st.expander(f"📈 Evolución del modelo ({len(evol)} entrenamientos registrados)"):
            st.text(f"{'Fecha':<12}{'Notas':>8}{'Base':>7}{'Logít.':>8}{'R.Forest':>10}{'Mejora':>8}  Ganador")
            for e in evol[-20:]:
                st.text(f"{e.get('Fecha',''):<12}{e.get('NotasDataset',''):>8}{e.get('Base',''):>7}"
                        f"{e.get('Logistica',''):>8}{e.get('RandomForest',''):>10}{e.get('Mejora',''):>8}  {e.get('Ganador','')}")
else:
    st.info("Entrená el modelo para habilitar el semáforo de abajo.")

st.markdown("---")

# ─── 3) EL PANORAMA DE HOY, SEMAFORIZADO ─────────────────────────────────────
st.header("🚦 El panorama de hoy")
st.caption("Los temas del último panorama del vigía (Snapshot), clasificados por el modelo: en qué conviene invertir energía.")
if not pack:
    st.info("Primero entrená el modelo.")
else:
    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        solo_faltantes = st.toggle("Solo lo que Olé NO tiene", value=True,
                                   help="Cruza el panorama con la cobertura de Olé y esconde lo ya publicado")
    with col_f2:
        top_n = st.selectbox("Mostrar", [10, 15, 25, "todos"], index=1)

    try:
        temas = sheets_memoria.leer_snapshot_anterior()
    except Exception:
        temas = []
    # cruce con lo que Olé ya publicó (últimos días)
    try:
        publicados = sheets_memoria.titulos_cobertura_ole(3)
    except Exception:
        publicados = []
    from monitor_core import normalizar_titulo, solapamiento
    keys_pub = [normalizar_titulo(t) for t in publicados if t]

    if not temas:
        st.info("No hay Snapshot reciente — esperá la próxima corrida del vigía.")
    else:
        filas, n_ocultos = [], 0
        for t in temas:
            titulo = t.get("titulo", "") if isinstance(t, dict) else str(t)
            medios = t.get("cant_medios", "") if isinstance(t, dict) else ""
            if not titulo:
                continue
            # ¿Olé ya lo tiene? dos vías: la marca del snapshot y el cruce con Cobertura
            ya_ole = bool(t.get("tiene_ole")) if isinstance(t, dict) else False
            if not ya_ole and keys_pub:
                k = normalizar_titulo(titulo)
                ya_ole = any(solapamiento(k, kp) >= 0.4 for kp in keys_pub if kp)
            if solo_faltantes and ya_ole:
                n_ocultos += 1
                continue
            r = predecir_semaforo(pack, titulo, "", True)
            p_verde = dict(r["probas"]).get("verde", 0)
            filas.append((p_verde, r["clase"], titulo, medios, r["empuja"][:3], ya_ole))
        filas.sort(reverse=True)  # por probabilidad, de mayor a menor
        if top_n != "todos":
            filas = filas[:int(top_n)]
        iconos = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
        extra_cap = f" · {n_ocultos} ocultos (Olé ya los tiene)" if n_ocultos else ""
        st.caption(f"Mostrando {len(filas)} temas ordenados por probabilidad{extra_cap}")
        if not filas:
            st.success("Olé ya tiene todo lo que hay en el panorama 👏")
        for pv, clase, titulo, medios, empuja, ya_ole in filas:
            extra = f" · {medios} medios" if medios else ""
            marca = " ✓" if ya_ole else ""
            razones = f"  _({', '.join(empuja)})_" if clase == "verde" and empuja else ""
            st.markdown(f"{iconos[clase]} **{pv:.0%}** · {titulo[:120]}{extra}{marca}{razones}")

st.markdown("---")

# ─── 3b) DETECTOR DE INCENDIOS ───────────────────────────────────────────────
st.header("🔥 Detector de incendios")
st.caption("¿Qué tema chico va a explotar? Aprende del Historial: temas que nacieron con 2-5 medios y llegaron (o no) a 8+ en las siguientes 12 horas.")
if st.button("Entrenar detector con el Historial"):
    with st.spinner("Rastreando nacimientos y explosiones en el Historial..."):
        try:
            hist = sheets_memoria.leer_historial(45)
            dpack = entrenar_detector(hist)
            if "error" in dpack:
                st.warning(dpack["error"])
            else:
                st.session_state.dpack = dpack
        except Exception as e:
            st.error(f"Error: {e}")

dpack = st.session_state.get("dpack")
if dpack:
    d1, d2, d3 = st.columns(3)
    d1.metric("Temas chicos rastreados", dpack["n_train"] + dpack["n_test"])
    d2.metric("🔥 Aciertos al marcar fuego", f"{dpack['precision_fuego']:.0%}",
              help="De los temas que el detector marcó como 'va a explotar', cuántos explotaron de verdad")
    d3.metric("Incendios detectados", f"{dpack['cobertura_fuego']:.0%}",
              help="De todas las explosiones reales, cuántas el detector vio venir")
    st.caption("⬆️ Empuja al fuego: " + " · ".join(n for n, _ in dpack["factores_fuego"][:6]))

    # aplicar al panorama actual: los temas chicos de hoy, ordenados por riesgo de explosión
    try:
        temas_hoy = sheets_memoria.leer_snapshot_anterior()
    except Exception:
        temas_hoy = []
    chicos = []
    from datetime import datetime as _dt
    hora_ahora = _dt.now().strftime("%H:%M")
    for t in temas_hoy:
        titulo = t.get("titulo", "") if isinstance(t, dict) else str(t)
        try:
            medios = int(t.get("cant_medios", 0)) if isinstance(t, dict) else 0
        except Exception:
            medios = 0
        if titulo and 2 <= medios <= 5:
            r = predecir_incendio(dpack, titulo, medios, hora_ahora)
            chicos.append((r["prob"], titulo, medios, r["empuja"][:3]))
    if chicos:
        chicos.sort(reverse=True)
        st.markdown("**Los temas chicos de AHORA, por riesgo de explosión:**")
        for prob, titulo, medios, empuja in chicos[:15]:
            icono = "🔥" if prob >= 0.6 else ("🟠" if prob >= 0.35 else "▫️")
            razones = f"  _({', '.join(empuja)})_" if prob >= 0.6 and empuja else ""
            st.markdown(f"{icono} **{prob:.0%}** · {titulo[:110]} · {medios} medios{razones}")
    else:
        st.info("No hay temas chicos (2-5 medios) en el Snapshot actual — esperá la próxima corrida del vigía.")

st.markdown("---")

# ─── 4) PROBADOR ─────────────────────────────────────────────────────────────
st.header("🧪 Probar un tema")
if not pack:
    st.info("Primero entrená el modelo.")
else:
    ct1, ct2, ct3, ct4 = st.columns([3, 1.3, 1.1, 0.9])
    with ct1:
        titulo_test = st.text_input("Título o tema", placeholder="ej: Mastantuono se lesiona en la práctica de River")
    with ct4:
        franja = st.selectbox("Horario", ["(s/d)", "mañana", "mediodía", "tarde", "noche"])
    with ct2:
        sec = st.selectbox("Sección", ["(sin sección)", "Mundial | Mundial 2026", "River Plate",
                                       "Boca Juniors", "Selección Argentina", "Fútbol de Primera",
                                       "Racing Club", "Tenis"])
    with ct3:
        caliente = st.toggle("Tema caliente", help="¿Está creciendo en el panorama ahora?")
    if titulo_test.strip():
        _hmap = {"mañana": "09:00", "mediodía": "12:00", "tarde": "17:00", "noche": "21:00"}
        r = predecir_semaforo(pack, titulo_test, "" if sec == "(sin sección)" else sec, caliente,
                              _hmap.get(franja, ""))
        iconos = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
        probas_txt = " · ".join(f"{iconos[c]} {p:.0%}" for c, p in r["probas"])
        st.markdown(f"## {iconos[r['clase']]} {r['clase'].upper()}  ·  {probas_txt}")
        st.caption(f"⬆️ Empuja: {', '.join(r['empuja']) or '—'}   ·   ⬇️ Frena: {', '.join(r['frena']) or '—'}")
        st.caption("El semáforo informa tu decisión, no la reemplaza.")
