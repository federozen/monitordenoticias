"""vigia.py — Piloto automático del Monitor Deportivo.

Corre solo (GitHub Actions, cada hora). En cada corrida:
  1. Scrapea las mismas fuentes que la app (monitor_core).
  2. Calcula tendencias y las compara con el Snapshot anterior del Sheet
     (momentum real entre corridas, aunque nadie haya abierto la app).
  3. Arma la agenda de acciones y descarta lo que el editor ya marcó
     como hecho/descartado en la planilla, y lo ya avisado hace poco.
  4. Escribe las acciones nuevas en la pestaña Agenda del Sheet.
  5. Si hay algo urgente (SUBIR YA) y hay bot configurado, avisa por Telegram.

Sin credenciales de Sheets corre en modo simulacro: imprime lo que haría.
"""
import os
import sys
import time
import requests as _rq
from concurrent.futures import ThreadPoolExecutor, as_completed

import monitor_core
from monitor_core import (
    TODAS_FUENTES, fetch_fuente, calcular_tendencias,
    analizar_ole_vs_compecencia_safe, construir_agenda, normalizar_titulo,
    fetch_cobertura_ole_gnews, fetch_ultimas_ole, coincide_cobertura,
    calcular_momentum, es_tema_de_pases, ranking_entidades, dic_entidades,
)
import sheets_memoria as mem
import online_storage as online
from editorial_agents import orchestrator as agent_orchestrator


def clave_tema(titulo: str) -> str:
    return " ".join(sorted(normalizar_titulo(titulo)))[:180]


def _fetch_timed(fuente: dict) -> tuple:
    inicio = time.perf_counter()
    try:
        resultado = fetch_fuente(fuente)
    except Exception as exc:
        resultado = {"id": fuente.get("id"), "noticias": [], "error": str(exc)}
    return resultado, round(time.perf_counter() - inicio, 2)


def scrapear_todo() -> tuple[dict, list]:
    """Devuelve resultados y salud de cada fuente para el tablero online."""
    resultados, estados = {}, []
    nac_ids = set(getattr(monitor_core, "FUENTES_NAC_IDS", set()))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_timed, f): f for f in TODAS_FUENTES}
        for fut in as_completed(futs):
            f = futs[fut]
            try:
                r, duracion = fut.result()
                noticias = r.get("noticias") or []
                error = r.get("error")
                via = r.get("via")
            except Exception as e:
                noticias, error, via, duracion = [], str(e), "", 0
            resultados[f["id"]] = noticias
            ultimo = max((n.get("fecha_publicacion", "") for n in noticias), default="")
            canal = ("Google News" if "news.google.com" in f.get("url", "") or via == "gnews"
                     else "RSS" if f.get("es_rss") else "Web directa")
            estados.append({
                "id": f["id"], "nombre": f.get("nombre", f["id"]),
                "zona": "Nacional" if f["id"] in nac_ids else "Internacional",
                "canal": canal, "estado": "ok" if noticias and not error else "error",
                "noticias": len(noticias), "duracion": duracion,
                "error": str(error or "")[:500], "ultimo_contenido": ultimo,
            })
            estado = f"{len(noticias):3d} notas" if not error else f"ERROR: {str(error)[:60]}"
            print(f"  [{f['id']:<12}] {estado} · {duracion:.1f}s")
    estados.sort(key=lambda x: (x["estado"] != "error", x["nombre"].lower()))
    return resultados, estados


def matches_watchlist(titulo: str, watchlist: list) -> str:
    t = titulo.lower()
    for w in watchlist:
        if w and w in t:
            return w
    return ""


def enviar_telegram(texto: str, html: bool = True, silencioso: bool = False) -> bool:
    modo = os.environ.get("TELEGRAM_MODE", "full").strip().lower()
    if modo in {"off", "no", "false", "0", "apagado"}:
        return False
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False

    # Telegram corta a los 4096 caracteres: partir en trozos por líneas enteras
    LIMITE = 3900
    if len(texto) <= LIMITE:
        trozos = [texto]
    else:
        trozos, actual = [], ""
        for linea in texto.split("\n"):
            # una sola línea gigante: cortarla a lo bruto como último recurso
            while len(linea) > LIMITE:
                if actual:
                    trozos.append(actual); actual = ""
                trozos.append(linea[:LIMITE]); linea = linea[LIMITE:]
            if actual and len(actual) + len(linea) + 1 > LIMITE:
                trozos.append(actual); actual = linea
            else:
                actual = f"{actual}\n{linea}" if actual else linea
        if actual:
            trozos.append(actual)

    ok_todos = True
    for i, trozo in enumerate(trozos):
        try:
            payload = {"chat_id": chat, "text": trozo, "disable_web_page_preview": True}
            if html:
                payload["parse_mode"] = "HTML"
            if silencioso:
                payload["disable_notification"] = True
            r = _rq.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json=payload, timeout=15)
            if r.status_code != 200:
                print(f"  Telegram rechazó el mensaje: {r.status_code} {r.text[:120]}")
                ok_todos = False
        except Exception as e:
            print(f"  Telegram falló: {e}")
            ok_todos = False
    return ok_todos


def main():
    simulacro = not mem.disponible()
    legacy_memory = os.environ.get("LEGACY_MEMORY_WRITES_ENABLED", "false").strip().lower() in {"1", "true", "yes", "si"}
    print("=== MONITOR V10 - resumen, cambios y hallazgos ===", "(modo simulacro: sin Sheet configurado)" if simulacro else "")
    print(f"modo de convivencia: escrituras heredadas={'si' if legacy_memory else 'no'}")

    # El workflow puede disparar esta corrida cada 20 min (como respaldo por si
    # GitHub Actions saltea algún cron), pero el trabajo pesado solo se hace
    # una vez por hora real. El freno aplica SOLO a las corridas automáticas
    # (schedule); si la disparás a mano (Run workflow), corre siempre.
    forzado = os.environ.get("GITHUB_EVENT_NAME", "") in ("workflow_dispatch", "push", "")
    min_minutos = int(os.environ.get("FRECUENCIA_MINUTOS", "55") or 55)
    if legacy_memory and not forzado and not mem.debe_correr(min_minutos=min_minutos):
        print(f"Corrida automática pero todavía no pasaron {min_minutos} minutos. Salgo sin hacer nada.")
        return
    if forzado:
        print("Corrida manual (Run workflow): ignoro el freno de 1 hora y actualizo ya.")

    cfg = mem.leer_config() if not simulacro else {
        "umbral_medios": 4, "watchlist": [], "horas_silencio": 48}
    print(f"config: umbral={cfg['umbral_medios']} medios · "
          f"watchlist={cfg['watchlist']} · silencio={cfg['horas_silencio']}h")

    inicio_corrida = time.perf_counter()
    print("\n1) Scrapeando fuentes...")
    resultados, estados_fuentes = scrapear_todo()
    total = sum(len(v) for v in resultados.values())
    fuentes_ok = sum(1 for v in resultados.values() if v)
    print(f"   {total} noticias de {fuentes_ok}/{len(TODAS_FUENTES)} fuentes")
    if fuentes_ok < 5:
        print("   Muy pocas fuentes respondieron; aborto para no ensuciar la memoria.")
        sys.exit(1)

    print("\n2) Tendencias y momentum...")
    tendencias = calcular_tendencias(resultados)
    if cfg.get("ignorar"):
        antes = len(tendencias)
        tendencias = [c for c in tendencias
                      if not matches_watchlist(c["titulo"], cfg["ignorar"])]
        if antes - len(tendencias):
            print(f"   {antes - len(tendencias)} temas descartados por lista 'ignorar'")
    ole = analizar_ole_vs_compecencia_safe(resultados)
    prev = []
    if not simulacro and online.disponible():
        try:
            prev = [
                {"titulo": row.get("Titulo", ""), "cant_medios": int(float(row.get("Medios", 0) or 0))}
                for row in online.leer_temas() if row.get("Titulo")
            ]
        except Exception:
            prev = []
    if not prev and not simulacro:
        try:
            prev = mem.leer_snapshot_anterior()
        except Exception:
            prev = []
    monitor_core.CRITERIOS_EDITOR = cfg.get("criterios", "")
    cubiertos, nuevas_ole, ole_coverage = [], [], []
    if not simulacro:
        # persistir lo publicado por Olé en su pestaña, por tres vías:
        # portada (lo destacado) + /ultimas-noticias (TODO, al minuto) + Google News (respaldo)
        portada = list(resultados.get("ole", []))
        ultimas = fetch_ultimas_ole()
        gnews_ole = fetch_cobertura_ole_gnews()
        print(f"   cobertura Olé: portada {len(portada)} · últimas {len(ultimas)} · gnews {len(gnews_ole)}")
        if legacy_memory:
            nuevas_ole = mem.registrar_cobertura_ole(portada + ultimas + gnews_ole)
        # La memoria se lee para aprovechar el proyecto actual, pero durante la
        # prueba V9 no se escriben las pestanas heredadas.
        try:
            cubiertos = mem.cobertura_propia(dias=5) + mem.titulos_cobertura_ole(dias=5)
        except Exception:
            cubiertos = []
        ole_coverage = portada + ultimas + gnews_ole + cubiertos
    print(f"   {len(tendencias)} clusters · snapshot anterior: {len(prev)} temas · "
          f"memoria de cobertura propia: {len(cubiertos)} temas")

    agenda = construir_agenda(tendencias, ole, prev, max_items=20, cubiertos=cubiertos)
    for it in agenda:
        it["clave"] = clave_tema(it["titulo"])

    # Watchlist: temas vigilados entran aunque Olé ya los tenga
    for c in tendencias:
        w = matches_watchlist(c["titulo"], cfg["watchlist"])
        if w and not any(a["clave"] == clave_tema(c["titulo"]) for a in agenda):
            agenda.append({
                "accion": "SEGUIR", "motivo": f"watchlist: '{w}'",
                "titulo": c["titulo"], "url": c.get("url"),
                "cant_medios": c["cant_medios"], "delta": 0, "nuevo": False,
                "clave": clave_tema(c["titulo"]),
            })

    # Tracker de pases: toda operación de mercado va a su pestaña con línea de tiempo
    if not simulacro and legacy_memory:
        temas_pases = [{"titulo": c["titulo"], "cant_medios": c["cant_medios"],
                        "tiene_ole": c.get("tiene_ole"), "url": c.get("url"),
                        "clave": clave_tema(c["titulo"])}
                       for c in tendencias if es_tema_de_pases(c["titulo"])]
        n_new, n_upd = mem.registrar_pases(temas_pases)
        print(f"   pases: {len(temas_pases)} operaciones en el panorama → "
              f"{n_new} nuevas · {n_upd} actualizadas en la pestaña")

        # Ranking de entidades (sin IA): quién manda hoy en la conversación
        dic = dic_entidades(cfg.get("entidades_extra", ""))
        ranking = ranking_entidades(resultados, dic)
        n_ent = mem.guardar_ranking_entidades(ranking)
        if ranking:
            top3 = " · ".join(f"{e['entidad']} ({e['menciones']})" for e in ranking[:3])
            print(f"   quién manda: {n_ent} entidades · top: {top3}")
        # Termómetro: qué sube y qué baja (usa la historia de entidades)
        termo = mem.calcular_termometro()
        n_termo = mem.guardar_termometro(termo)
        if termo:
            suben = [t for t in termo if "sube" in t["tendencia"] or "nuevo" in t["tendencia"]][:2]
            if suben:
                print("   termómetro: " + " · ".join(f"🔥{t['entidad']} {t['var']:+}%" for t in suben))

    # EXPLOTA: saltos de velocidad, incluso en temas que Olé ya tiene
    if cfg.get("avisos_explosion", True) and prev:
        mom = calcular_momentum(tendencias, prev)
        for i, c in enumerate(tendencias):
            m = mom.get(i, {})
            if (not m.get("nuevo") and m.get("delta", 0) >= cfg.get("umbral_explosion", 4)
                    and c.get("tiene_ole")
                    and not any(a["clave"] == clave_tema(c["titulo"]) for a in agenda)):
                agenda.append({
                    "accion": "EXPLOTA",
                    "motivo": (f"pasó de {c['cant_medios'] - m['delta']} a "
                               f"{c['cant_medios']} medios en una hora — "
                               f"si ya lo dimos, la nota puede quedar vieja"),
                    "titulo": c["titulo"], "url": c.get("url"),
                    "cant_medios": c["cant_medios"], "delta": m["delta"],
                    "nuevo": False, "clave": clave_tema(c["titulo"]),
                })

    # Filtro de urgencia: solo pasa lo que supera el umbral o es watchlist/exclusivo
    accionables = [
        it for it in agenda
        if (it["accion"] == "SUBIR YA" and it["cant_medios"] >= cfg["umbral_medios"])
        or it["accion"] in ("SEGUIR", "EMPUJAR", "RETOMAR", "EXPLOTA")
        or (it["accion"] == "REDACTAR" and it["cant_medios"] >= cfg["umbral_medios"])
    ]

    # Se conserva el corte anterior antes de reemplazar las pestanas operativas.
    # El resumen editorial se basa en diferencias reales, no en el inventario completo.
    previous_themes = []
    if not simulacro and online.disponible():
        try:
            previous_themes = online.leer_temas()
        except Exception:
            previous_themes = []

    # Snapshot para la app liviana. Usa pestanas nuevas (V9_ por defecto),
    # por lo que puede convivir con la planilla y el vigia anteriores.
    if not simulacro and online.disponible():
        try:
            counts = online.guardar_snapshot_online(
                resultados, tendencias, agenda, estados_fuentes,
                run_info={
                    "estado": "ok",
                    "duracion_seg": round(time.perf_counter() - inicio_corrida, 2),
                    "version_nucleo": getattr(monitor_core, "CORE_VERSION", ""),
                    "telegram_mode": os.environ.get("TELEGRAM_MODE", "full"),
                },
            )
            print(f"   snapshot online: {counts['noticias']} noticias · "
                  f"{counts['temas']} temas · {counts['fuentes']} fuentes")
        except Exception as exc:
            print(f"   snapshot online fallo: {exc}")

    # Capa V10: resumen comparado, cambios accionables y hallazgos.
    # e informe ejecutivo. No publica: recomienda, alerta y registra feedback.
    agent_result = {"enabled": False}
    if not simulacro and online.disponible():
        try:
            agent_result = agent_orchestrator.run(
                tendencias, agenda, estados_fuentes, online,
                send_telegram=enviar_telegram, config=cfg,
                raw_results=resultados, ole_coverage=ole_coverage,
                previous_themes=previous_themes,
            )
            if agent_result.get("enabled"):
                print("   asistente: "
                      f"{len(agent_result.get('changes', []))} cambios · "
                      f"{len(agent_result.get('discoveries', []))} hallazgos/candidatos · "
                      f"{len(agent_result.get('opportunities', []))} oportunidades · "
                      f"{agent_result.get('alerts_sent', 0)} alertas")
        except Exception as exc:
            print(f"   asistente editorial fallo: {exc}")
            try:
                online.registrar_agent_log({
                    "agent": "orchestrator", "status": "error", "detail": str(exc)[:500]
                })
            except Exception:
                pass

    print("\n3) Filtrando lo ya tratado/avisado...")
    if not simulacro and legacy_memory:
        nuevos = mem.filtrar_ya_tratados(accionables, cfg["horas_silencio"])
    else:
        nuevos = accionables
    print(f"   {len(accionables)} accionables → {len(nuevos)} nuevos")

    # Memoria y limpieza: SIEMPRE, haya o no avisos nuevos
    if not simulacro and legacy_memory:
        mem.guardar_snapshot(tendencias, origen="vigia")
        n_hist = mem.registrar_historial(tendencias)
        n_arch = mem.archivar_agenda_vieja(cfg.get("dias_archivo", 3))
        # Auto-resolución: pendientes que Olé ya cubrió pasan a "cubierto"
        cobertura_sets = [normalizar_titulo(c["titulo"]) for c in cubiertos]
        cobertura_sets += [normalizar_titulo(n["titulo"]) for n in resultados.get("ole", [])]
        cambios = {}
        for nro_fila, clave in mem.filas_pendientes_agenda():
            k = set(clave.split())
            for kc in cobertura_sets:
                if coincide_cobertura(k, kc):
                    cambios[nro_fila] = "cubierto"
                    break
        if cambios:
            n_res = mem.marcar_estados(cambios)
            print(f"   auto-resueltas: {n_res} filas que Olé ya cubrió → 'cubierto'")
        if cfg.get("_formato_v") != mem.FORMATO_VERSION:
            print("   aplicando formato al tablero:", "ok" if mem.formatear_tablero() else "falló")
        n_limp = mem.limpiar_historial()
        if n_limp:
            print(f"   historial recortado: {n_limp} filas viejas")
        print(f"   memoria: snapshot ok · {n_hist} temas al Historial"
              + (f" · {n_arch} filas archivadas" if n_arch else ""))
        mem.marcar_corrida_ok()

    if not nuevos:
        print("\nNada nuevo que avisar. Silencio = todo bajo control.")
        return

    print("\n4) Escribiendo en la Agenda del Sheet...")
    if not simulacro and legacy_memory:
        n = mem.agregar_a_agenda(nuevos, origen="vigia")
        print(f"   {n} filas agregadas -> {mem.url_planilla()}")
    else:
        for it in nuevos:
            print(f"   [{it['accion']:8}] {it['titulo'][:70]}")

    urgentes = [it for it in nuevos if it["accion"] in ("SUBIR YA", "EXPLOTA")]
    legacy_alerts = os.environ.get("LEGACY_ALERTS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "si"}
    if urgentes and legacy_alerts:
        lineas = "\n".join(
            f"{'⚡' if it['accion'] == 'EXPLOTA' else '🔴'} <b>{it['titulo'][:120]}</b>\n   {it['motivo'][:90]}"
            + (f" · <a href=\"{it['url']}\">ver</a>" if it.get("url") else "")
            for it in urgentes[:5]
        )
        extra = f"\n\n(+{len(nuevos) - len(urgentes)} acciones más en la planilla)" \
            if len(nuevos) > len(urgentes) else ""
        link = f"\n📋 {mem.url_planilla()}" if not simulacro else ""
        ok = enviar_telegram(f"<b>ALERTAS</b>\n\n{lineas}{extra}{link}")
        print(f"\n5) Telegram: {'enviado' if ok else 'no configurado / falló'}")

    legacy_digest = os.environ.get("LEGACY_OLE_DIGEST_ENABLED", "false").strip().lower() in {"1", "true", "yes", "si"}
    if legacy_digest and cfg.get("digest_ole", True) and nuevas_ole:
        cuerpo = "\n".join(f"• {t[:200]}" for t in nuevas_ole[:25])
        extra_d = f"\n…y {len(nuevas_ole) - 25} más" if len(nuevas_ole) > 25 else ""
        ok_d = enviar_telegram(f"📰 Lo último de Olé ({len(nuevas_ole)} nuevas):\n{cuerpo}{extra_d}",
                               html=False, silencioso=True)
        print(f"6) Digest Olé: {len(nuevas_ole)} notas nuevas · "
              f"telegram {'ok (silencioso)' if ok_d else 'no configurado'}")

    # ── PARTE INTELIGENTE (IA, modelo económico, una vez al día tras las 10am) ──
    legacy_parts = os.environ.get("LEGACY_AI_PARTS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "si"}
    if not simulacro and legacy_memory and legacy_parts:
        _parte_inteligente(resultados)


def _parte_inteligente(resultados: dict):
    """Genera y envía por Telegram el parte nacional y el internacional, una vez
    por día cada uno, después de las 10am. Usa el modelo económico para bajar el
    costo. La API key va en el secreto ANTHROPIC_API_KEY de GitHub."""
    from datetime import datetime
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return  # sin key configurada, no hace nada (silencioso)

    ahora = datetime.now(mem._TZ_AR)
    hoy = ahora.strftime("%Y-%m-%d")
    if ahora.hour < 10:
        return  # esperar a que el vigía haya corrido varias veces en la mañana

    import monitor_core as mc
    # cada parte se manda una sola vez por día (marca en Config vía Snapshot no;
    # usamos una pestaña simple de control)
    ya = mem.partes_enviados_hoy(hoy)

    if "nac" not in ya:
        try:
            texto = mc.call_claude(mc.prompt_parte_nacional(resultados), api_key,
                                   max_tokens=1600, modelo=mc.MODELO_ECONOMICO)
            enviar_telegram(f"🇦🇷 <b>PARTE NACIONAL</b> · {ahora.strftime('%d/%m %H:%M')}\n\n{texto}")
            mem.marcar_parte_enviado(hoy, "nac")
            print(f"   parte nacional: enviado (modelo económico)")
        except Exception as e:
            print(f"   parte nacional falló: {e}")

    if "int" not in ya:
        try:
            texto = mc.call_claude(mc.prompt_parte_internacional(resultados), api_key,
                                   max_tokens=1600, modelo=mc.MODELO_ECONOMICO)
            enviar_telegram(f"🌍 <b>PARTE INTERNACIONAL</b> · {ahora.strftime('%d/%m %H:%M')}\n\n{texto}")
            mem.marcar_parte_enviado(hoy, "int")
            print(f"   parte internacional: enviado (modelo económico)")
        except Exception as e:
            print(f"   parte internacional falló: {e}")


if __name__ == "__main__":
    main()
