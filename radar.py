# -*- coding: utf-8 -*-
"""RADAR IA v1 — curador semanal para el embajador de IA.
Lee las fuentes clave de IA + periodismo (RSS y Google News), junta lo de la
última semana y manda un digest a Telegram. Si hay ANTHROPIC_API_KEY, la IA
(modelo económico) resume y prioriza; si no, va la lista cruda igual.
Independiente del vigía: si esto falla, el monitor no se entera.
"""
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

TZ_AR = timezone(timedelta(hours=-3))
DIAS_VENTANA = 8
MAX_POR_FUENTE = 5
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RadarIA/1.0"}

G_AR = "&hl=es-419&gl=AR&ceid=AR:es-419"
G_EN = "&hl=en-US&gl=US&ceid=US:en"

FUENTES = [
    # Periodismo + IA (el corazón del rol)
    {"nombre": "Nieman Lab",        "grupo": "📰 Periodismo + IA", "url": "https://www.niemanlab.org/feed/"},
    {"nombre": "Reuters Institute", "grupo": "📰 Periodismo + IA", "url": f"https://news.google.com/rss/search?q=site:reutersinstitute.politics.ox.ac.uk{G_EN}"},
    {"nombre": "LatAm Journalism",  "grupo": "📰 Periodismo + IA", "url": f"https://news.google.com/rss/search?q=site:latamjournalismreview.org{G_AR}"},
    {"nombre": "IA y periodismo (ES)", "grupo": "📰 Periodismo + IA", "url": f"https://news.google.com/rss/search?q=%22inteligencia%20artificial%22%20(periodismo%20OR%20redacciones%20OR%20medios){G_AR}"},
    # Conceptual (criterio de embajador)
    {"nombre": "One Useful Thing (Mollick)", "grupo": "🧠 Conceptual", "url": "https://www.oneusefulthing.org/feed"},
    # Herramientas y anuncios
    {"nombre": "Anthropic", "grupo": "🔧 Herramientas", "url": f"https://news.google.com/rss/search?q=site:anthropic.com{G_EN}"},
    {"nombre": "OpenAI",    "grupo": "🔧 Herramientas", "url": f"https://news.google.com/rss/search?q=site:openai.com{G_EN}"},
    {"nombre": "Google IA", "grupo": "🔧 Herramientas", "url": f"https://news.google.com/rss/search?q=(Gemini%20OR%20%22Google%20AI%22)%20(launch%20OR%20release%20OR%20announces){G_EN}"},
]


def extraer_items(xml: str) -> list:
    items = []
    for m in re.finditer(r"<item>([\s\S]*?)</item>|<entry>([\s\S]*?)</entry>", xml):
        blk = m.group(1) or m.group(2)
        tm = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</title>", blk)
        if not tm:
            continue
        titulo = re.sub(r"<[^>]+>", "", tm.group(1)).strip()
        lm = re.search(r"<link>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</link>", blk)
        href = re.search(r'<link[^>]*href="([^"]+)"', blk)
        url = (lm.group(1).strip() if lm and lm.group(1).strip() else
               (href.group(1) if href else ""))
        dm = re.search(r"<pubDate>([\s\S]*?)</pubDate>|<published>([\s\S]*?)</published>|<updated>([\s\S]*?)</updated>", blk)
        fecha = None
        if dm:
            crudo = (dm.group(1) or dm.group(2) or dm.group(3) or "").strip()
            try:
                fecha = parsedate_to_datetime(crudo)
            except Exception:
                try:
                    fecha = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
                except Exception:
                    fecha = None
        # limpiar sufijo de medio de Google News
        d = titulo.rfind(" - ")
        if d > 25:
            titulo = titulo[:d].strip()
        items.append({"titulo": titulo, "url": url, "fecha": fecha})
    return items


def recolectar() -> list:
    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_VENTANA)
    out, vistos = [], set()
    for f in FUENTES:
        try:
            r = requests.get(f["url"], headers=HEADERS, timeout=15)
            r.raise_for_status()
            frescos = []
            for it in extraer_items(r.text):
                if it["fecha"] is not None and it["fecha"] < limite:
                    continue
                clave = re.sub(r"\W+", "", it["titulo"].lower())[:60]
                if not clave or clave in vistos:
                    continue
                vistos.add(clave)
                frescos.append(it)
                if len(frescos) >= MAX_POR_FUENTE:
                    break
            for it in frescos:
                out.append({**it, "fuente": f["nombre"], "grupo": f["grupo"]})
            print(f"  [{f['nombre']:<26}] {len(frescos)} items")
        except Exception as e:
            print(f"  [{f['nombre']:<26}] ERROR: {str(e)[:60]}")
    return out


def resumen_ia(items: list) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not items:
        return ""
    try:
        import anthropic
        listado = "\n".join(f"[{i['grupo']}] ({i['fuente']}) {i['titulo']}"
                            for i in items)
        prompt = f"""Sos el asistente de un editor deportivo argentino que acaba de ser
nombrado EMBAJADOR DE IA de su empresa periodística. Abajo están los títulos de
lo publicado esta semana por sus fuentes de referencia (IA + periodismo).

Escribí su briefing semanal en español rioplatense, corto y útil:

LO QUE NO TE PODÉS PERDER — los 3 a 5 ítems más relevantes para su rol, cada uno
en una línea: qué es y POR QUÉ le importa a un embajador de IA en un diario.

RADAR RÁPIDO — el resto agrupado por tema en una línea cada uno, solo si aportan.
Lo irrelevante, saltealo sin mencionar.

PARA LA REDACCIÓN — si hay algo directamente usable para evangelizar (un caso de
un medio, una herramienta nueva, un dato citable), marcalo con 💬.

TÍTULOS DE LA SEMANA:
{listado}"""
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(b.text for b in msg.content
                         if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        print(f"  resumen IA falló ({str(e)[:60]}) — va la lista cruda")
        return ""


def enviar_telegram(texto: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("  telegram no configurado")
        return False
    LIMITE = 3900
    trozos, actual = [], ""
    for linea in texto.split("\n"):
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
    ok = True
    for t in trozos:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": t,
                                    "disable_web_page_preview": True}, timeout=15)
            ok = ok and r.status_code == 200
        except Exception:
            ok = False
    return ok


def main():
    print("=== RADAR IA v1 · digest del embajador ===")
    ahora = datetime.now(TZ_AR)
    print(f"{ahora.strftime('%Y-%m-%d %H:%M')} AR")
    print("1) Recolectando fuentes...")
    items = recolectar()
    print(f"   {len(items)} items frescos de la semana")
    if not items:
        print("   nada nuevo — no se envía digest")
        return

    print("2) Armando digest...")
    cuerpo = resumen_ia(items)
    if not cuerpo:
        # sin IA: lista cruda agrupada
        grupos = {}
        for i in items:
            grupos.setdefault(i["grupo"], []).append(i)
        partes = []
        for g, lst in grupos.items():
            partes.append(f"\n{g}")
            for i in lst:
                partes.append(f"• ({i['fuente']}) {i['titulo'][:120]}")
        cuerpo = "\n".join(partes)

    encabezado = f"🎖️ RADAR IA · semana al {ahora.strftime('%d/%m')}\n"
    links = "\n\n🔗 Fuentes: niemanlab.org · oneusefulthing.org · reutersinstitute.politics.ox.ac.uk"
    ok = enviar_telegram(encabezado + cuerpo + links)
    print(f"3) Telegram: {'enviado' if ok else 'falló / no configurado'}")


if __name__ == "__main__":
    main()
