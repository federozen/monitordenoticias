"""monitor_core.py — Cerebro compartido del Monitor Deportivo.
Scraping, clustering, tendencias y agenda. Sin Streamlit: lo importan
app.py (interfaz) y vigia.py (corridas automáticas en GitHub Actions)."""
import re
import json
import random
import unicodedata
import requests
import anthropic
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from datetime import datetime

MAX_ITEMS = 50
SIMILITUD_UMBRAL = 0.22

# ─── FUENTES ──────────────────────────────────────────────────────────────────
FUENTES_NAC = [
    {"id": "ole",           "nombre": "Olé",           "url": "https://www.ole.com.ar/",                             "color": "#00a846", "es_ole": True},
    {"id": "espn",          "nombre": "ESPN AR",        "url": "https://www.espn.com.ar/",                            "color": "#cc0000", "es_espn": True},
    {"id": "tyc",           "nombre": "TyC Sports",     "url": "https://www.tycsports.com/",                          "color": "#1565c0", "gnews_extra": True},
    {"id": "infobae",       "nombre": "Infobae",        "url": "https://www.infobae.com/deportes/",                   "color": "#b00020", "gnews_extra": True},
    {"id": "lanacion",      "nombre": "La Nación",      "url": "https://www.lanacion.com.ar/deportes/",               "color": "#1565c0"},
    {"id": "tn",            "nombre": "TN Deportes",    "url": "https://tn.com.ar/deportes/",                         "color": "#cc2200"},
    {"id": "clarin",        "nombre": "Clarín Dep.",    "url": "https://www.clarin.com/deportes/",                    "color": "#c00000"},
    {"id": "elgrafico",   "nombre": "El Gráfico",     "url": "https://news.google.com/rss/search?q=%22El%20Gr%C3%A1fico%22%20(futbol%20OR%20river%20OR%20boca%20OR%20seleccion)&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#b07800", "es_rss": True},
    {"id": "dobleamarilla","nombre": "Doble Amarilla", "url": "https://news.google.com/rss/search?q=%22Doble%20Amarilla%22&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#a07800", "es_rss": True},
    {"id": "bolavip",       "nombre": "Bolavip",        "url": "https://bolavip.com/ar",                              "color": "#c04a00"},
    {"id": "lavoz",         "nombre": "La Voz",         "url": "https://www.lavoz.com.ar/deportes/",                  "color": "#8b0000"},
    {"id": "capital",    "nombre": "La Capital (Ovación)", "url": "https://news.google.com/rss/search?q=site:lacapital.com.ar%20futbol&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#8e44ad", "es_rss": True},
    {"id": "na",         "nombre": "NA Deportes",      "url": "https://news.google.com/rss/search?q=site:noticiasargentinas.com%20(futbol%20OR%20deportes)&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#2c3e50", "es_rss": True},

    # ── Nuevas nacionales (vía Google News) ──
    {"id": "cuatro42",   "nombre": "442",              "url": "https://news.google.com/rss/search?q=site:442.perfil.com&hl=es-419&gl=AR&ceid=AR:es-419",                       "color": "#7b2d8b", "es_rss": True},
    {"id": "cielosports","nombre": "Cielosports",      "url": "https://news.google.com/rss/search?q=site:infocielo.com%20futbol&hl=es-419&gl=AR&ceid=AR:es-419",                      "color": "#0090d0", "es_rss": True},
    {"id": "popular",    "nombre": "Diario Popular",   "url": "https://news.google.com/rss/search?q=site:diariopopular.com.ar%20futbol&hl=es-419&gl=AR&ceid=AR:es-419",        "color": "#d32f2f", "es_rss": True},
    {"id": "ambito",     "nombre": "Ámbito Deportes",  "url": "https://news.google.com/rss/search?q=site:ambito.com%20futbol&hl=es-419&gl=AR&ceid=AR:es-419",                  "color": "#00594e", "es_rss": True},
    {"id": "afa",        "nombre": "AFA (oficial)",    "url": "https://news.google.com/rss/search?q=site:afa.com.ar&hl=es-419&gl=AR&ceid=AR:es-419",                           "color": "#6cace4", "es_rss": True},
    {"id": "radar_ar",   "nombre": "Radar AR",         "url": "https://news.google.com/rss/search?q=%22f%C3%BAtbol%20argentino%22&hl=es-419&gl=AR&ceid=AR:es-419",             "color": "#444444", "es_rss": True},
]

FUENTES_INT = [
    {"id": "as",        "nombre": "AS",              "url": "https://as.com/futbol/",                          "color": "#b00020", "es_as": True},
    {"id": "marca",     "nombre": "Marca",            "url": "https://www.marca.com/",                          "color": "#267326"},
    {"id": "mundodep",  "nombre": "Mundo Deportivo",  "url": "https://www.mundodeportivo.com/",                 "color": "#1565c0"},
    {"id": "sport",     "nombre": "Sport",            "url": "https://www.sport.es/es/",                        "color": "#cc0020"},
    {"id": "globo",     "nombre": "Globoesporte",     "url": "https://ge.globo.com/",                           "color": "#007a2f", "gnews_extra": True},
    {"id": "gazzetta",  "nombre": "Gazzetta Sport",   "url": "https://www.gazzetta.it/Calcio/",                 "color": "#e8000a"},
    {"id": "corriere",  "nombre": "Corriere Sport",   "url": "https://www.corrieredellosport.it/calcio",        "color": "#e06000"},
    {"id": "record",    "nombre": "Record PT",        "url": "https://www.record.pt/futebol/",                  "color": "#c8000a"},

    {"id": "bbc",       "nombre": "BBC Sport",        "url": "https://feeds.bbci.co.uk/sport/football/rss.xml",      "color": "#bb1919", "es_rss": True},
    {"id": "goal",      "nombre": "Goal",             "url": "https://www.goal.com/es",                         "color": "#00a878"},
    {"id": "espnint",   "nombre": "ESPN INT",         "url": "https://www.espn.com/soccer/",                    "color": "#d00000"},
    {"id": "cbssport",  "nombre": "CBS Sports",       "url": "https://www.cbssports.com/rss/headlines/soccer/", "color": "#004b87", "es_rss": True},
    {"id": "sportnews", "nombre": "Sporting News",    "url": "https://www.sportingnews.com/us/soccer",          "color": "#cc3300"},
    {"id": "lequipe",   "nombre": "L'Equipe",         "url": "https://www.lequipe.fr/Football/",                "color": "#f5c400"},
    {"id": "fifa",      "nombre": "FIFA (RSS)",       "url": "https://www.fifa.com/rss-feeds/index.html",       "color": "#326295"},

    # ── Nuevos: inglés + especialistas de mercado (todos por RSS) ──
    {"id": "guardian",   "nombre": "Guardian Fútbol",  "url": "https://www.theguardian.com/football/rss",        "color": "#052962", "es_rss": True},
    {"id": "skysports",  "nombre": "Sky Sports",       "url": "https://www.skysports.com/rss/12040",             "color": "#0072c9", "es_rss": True},
    {"id": "dimarzio",   "nombre": "Di Marzio",        "url": "https://www.gianlucadimarzio.com/it/rss",         "color": "#0a3d62", "es_rss": True},
    {"id": "calciomer",  "nombre": "Calciomercato",    "url": "https://www.calciomercato.com/rss",               "color": "#c8102e", "es_rss": True},

    # ── Vía Google News directo (para medios sin RSS propio confiable) ──
    {"id": "tntsports",  "nombre": "TNT Sports AR",    "url": "https://news.google.com/rss/search?q=%22TNT%20Sports%22%20(river%20OR%20boca%20OR%20futbol%20OR%20seleccion)&hl=es-419&gl=AR&ceid=AR:es-419",  "color": "#e4002b", "es_rss": True},
    {"id": "footmercato","nombre": "Foot Mercato",     "url": "https://news.google.com/rss/search?q=site:footmercato.net%20OR%20%22Foot%20Mercato%22&hl=fr&gl=FR&ceid=FR:fr",    "color": "#0a5c36", "es_rss": True},
    {"id": "fabrizio",   "nombre": "Fabrizio Romano",  "url": "https://news.google.com/rss/search?q=%22Fabrizio%20Romano%22%20fichaje%20OR%20transfer&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#1a1a2e", "es_rss": True},

    # ── Nuevas internacionales: medios + instituciones ──
    {"id": "kicker",     "nombre": "Kicker (DE)",      "url": "https://news.google.com/rss/search?q=site:kicker.de&hl=de&gl=DE&ceid=DE:de",                                    "color": "#c00d0d", "es_rss": True},
    {"id": "athletic",   "nombre": "The Athletic",     "url": "https://news.google.com/rss/search?q=site:nytimes.com/athletic%20football&hl=en-US&gl=US&ceid=US:en",           "color": "#00292f", "es_rss": True},
    {"id": "ovacion",    "nombre": "Ovación (UY)",     "url": "https://news.google.com/rss/search?q=site:elpais.com.uy%20futbol&hl=es-419&gl=AR&ceid=AR:es-419",               "color": "#75aadb", "es_rss": True},
    {"id": "conmebol",   "nombre": "CONMEBOL",         "url": "https://news.google.com/rss/search?q=site:conmebol.com&hl=es-419&gl=AR&ceid=AR:es-419",                         "color": "#002b5c", "es_rss": True},
    {"id": "uefa",       "nombre": "UEFA / Champions", "url": "https://news.google.com/rss/search?q=(UEFA%20OR%20%22Champions%20League%22%20OR%20Europa%20League)&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#00004b", "es_rss": True},

    # ── Nuevas internacionales (vía Google News, con su edición de idioma) ──
    {"id": "geglobo",   "nombre": "GE Globo (BR)",   "url": "https://news.google.com/rss/search?q=site:ge.globo.com&hl=pt-BR&gl=BR&ceid=BR:pt-419",        "color": "#c4170c", "es_rss": True},
    {"id": "latercera", "nombre": "La Tercera (CL)", "url": "https://news.google.com/rss/search?q=site:latercera.com%20futbol&hl=es-419&gl=CL&ceid=CL:es-419", "color": "#e2231a", "es_rss": True},
    {"id": "abola",     "nombre": "A Bola (PT)",     "url": "https://news.google.com/rss/search?q=site:abola.pt&hl=pt-PT&gl=PT&ceid=PT:pt-150",             "color": "#e30613", "es_rss": True},
    {"id": "bild",      "nombre": "Bild Sport (DE)", "url": "https://news.google.com/rss/search?q=site:bild.de%20fussball&hl=de&gl=DE&ceid=DE:de",           "color": "#d00000", "es_rss": True},
    {"id": "skyit",     "nombre": "Sky Sport (IT)",  "url": "https://news.google.com/rss/search?q=site:sport.sky.it&hl=it&gl=IT&ceid=IT:it",                "color": "#0a1a3f", "es_rss": True},
    # Agencias de noticias (material curado y verificado, vía web abierta)
    {"id": "efe",       "nombre": "EFE (agencia)",   "url": "https://news.google.com/rss/search?q=site:efe.com/deportes&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#0055a5", "es_rss": True},
    {"id": "afp_f24",   "nombre": "AFP (France 24)", "url": "https://news.google.com/rss/search?q=site:france24.com/es%20(futbol%20OR%20deportes%20OR%20Argentina)&hl=es-419&gl=AR&ceid=AR:es-419", "color": "#0f3b8c", "es_rss": True},
    {"id": "reuters_dep","nombre": "Reuters Sports", "url": "https://news.google.com/rss/search?q=site:reuters.com%20(soccer%20OR%20football%20OR%20Argentina)&hl=en-US&gl=US&ceid=US:en", "color": "#ff8000", "es_rss": True},
]

# ─── GRUPO 3: PRIMICIAS E INSTITUCIONES ──────────────────────────────────────
# No son diarios genéricos: traen lo que otros tardan o no tienen — primicias de
# mercado, comunicados oficiales, designaciones, agregadores temáticos. Todo por
# Google News (búsqueda por marca/nombre), que es la vía confiable.
G_AR = "&hl=es-419&gl=AR&ceid=AR:es-419"
FUENTES_ESP = [
    # Primicias de mercado (periodistas especializados)
    {"id": "merlo",     "nombre": "César Merlo",      "url": f"https://news.google.com/rss/search?q=%22C%C3%A9sar%20Luis%20Merlo%22%20OR%20%22Cesar%20Merlo%22{G_AR}", "color": "#0b7a3b", "es_rss": True, "sin_fallback": True},
    {"id": "grova",     "nombre": "García Grova",     "url": f"https://news.google.com/rss/search?q=%22Germ%C3%A1n%20Garc%C3%ADa%20Grova%22%20OR%20%22Garcia%20Grova%22{G_AR}", "color": "#0b7a3b", "es_rss": True, "sin_fallback": True},
    # Institucional argentino
    {"id": "ligapro",   "nombre": "Liga Profesional", "url": f"https://news.google.com/rss/search?q=%22Liga%20Profesional%22%20(fixture%20OR%20fecha%20OR%20programacion%20OR%20oficial){G_AR}", "color": "#1a3c8f", "es_rss": True},
    {"id": "arbitros",  "nombre": "Designaciones/Arbitraje", "url": f"https://news.google.com/rss/search?q=(designaciones%20arbitrales%20OR%20%22arbitros%20para%20la%20fecha%22%20OR%20%22dirigir%C3%A1%22){G_AR}", "color": "#111111", "es_rss": True},
    # Agregadores temáticos (red de pesca ancha: todos los medios que Google indexa)
    {"id": "gn_river",  "nombre": "GNews · River",    "url": f"https://news.google.com/rss/search?q=River%20Plate%20futbol{G_AR}", "color": "#c8102e", "es_rss": True, "sin_fallback": True},
    {"id": "gn_boca",   "nombre": "GNews · Boca",     "url": f"https://news.google.com/rss/search?q=Boca%20Juniors%20futbol{G_AR}", "color": "#005baa", "es_rss": True, "sin_fallback": True},
    {"id": "gn_selec",  "nombre": "GNews · Selección","url": f"https://news.google.com/rss/search?q=%22selecci%C3%B3n%20argentina%22{G_AR}", "color": "#6cace4", "es_rss": True, "sin_fallback": True},
    {"id": "gn_pases",  "nombre": "GNews · Mercado AR","url": f"https://news.google.com/rss/search?q=(fichaje%20OR%20refuerzo%20OR%20%22mercado%20de%20pases%22)%20futbol%20argentino{G_AR}", "color": "#d68910", "es_rss": True, "sin_fallback": True},
    # Verticales flojas hoy
    {"id": "juveniles", "nombre": "Juveniles/Sub",    "url": f"https://news.google.com/rss/search?q=(sub%2020%20OR%20sub%2017%20OR%20juveniles)%20seleccion%20argentina{G_AR}", "color": "#0891b2", "es_rss": True},
    {"id": "gn_racing", "nombre": "GNews · Racing",   "url": f"https://news.google.com/rss/search?q=Racing%20Club%20futbol{G_AR}", "color": "#6cb4e4", "es_rss": True, "sin_fallback": True},
    {"id": "gn_inde",   "nombre": "GNews · Independiente", "url": f"https://news.google.com/rss/search?q=%22Independiente%22%20futbol%20argentina{G_AR}", "color": "#e30613", "es_rss": True, "sin_fallback": True},
    {"id": "gn_sanlo",  "nombre": "GNews · San Lorenzo", "url": f"https://news.google.com/rss/search?q=%22San%20Lorenzo%22%20futbol%20argentina{G_AR}", "color": "#1a2a6c", "es_rss": True, "sin_fallback": True},
    {"id": "gn_messi",  "nombre": "GNews · Messi",    "url": f"https://news.google.com/rss/search?q=Messi{G_AR}", "color": "#6cace4", "es_rss": True, "sin_fallback": True},
    {"id": "gn_colap",  "nombre": "GNews · Colapinto", "url": f"https://news.google.com/rss/search?q=Colapinto{G_AR}", "color": "#0090d0", "es_rss": True, "sin_fallback": True},
]

TODAS_FUENTES = FUENTES_NAC + FUENTES_INT + FUENTES_ESP
FUENTES_NAC_IDS = {f["id"] for f in FUENTES_NAC}
FUENTES_ESP_IDS = {f["id"] for f in FUENTES_ESP}

# ─── STOPWORDS ────────────────────────────────────────────────────────────────
STOPWORDS = set([
    "de","la","el","en","y","a","los","del","se","las","por","un","para","con","una","su","al","lo",
    "como","más","pero","sus","le","ya","o","fue","este","ha","si","porque","esta","son","entre",
    "cuando","muy","sin","sobre","también","me","hasta","hay","donde","quien","desde","todo","nos",
    "durante","e","esto","mi","antes","yo","otro","otras","otra","él","bien","así","cada","ser",
    "tiene","había","era","no","es","que","the","a","an","and","or","but","in","on","at","to","for",
    "of","with","by","from","is","was","are","were","be","been","have","has","had","will","would",
    "could","should","may","might","can","da","do","em","para","com","por","que","um","uma",
    "os","as","ao","na","no","nas","nos","se","seu","sua","seus","suas","não","após","tras",
    "vs","vs.","after","over","into","than","then","their","they","this","that",
])

# ─── SIMILITUD SEMÁNTICA ──────────────────────────────────────────────────────
@lru_cache(maxsize=8192)
def normalizar_titulo(titulo: str) -> set:
    t = titulo.lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if len(w) >= 3 and w not in STOPWORDS}

def similitud_jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    interseccion = len(set_a & set_b)
    union = len(set_a | set_b)
    return interseccion / union if union > 0 else 0.0


def similitud_ponderada(set_a: set, set_b: set, pesos: dict) -> float:
    """Como Jaccard pero cada palabra vale según su rareza (idf): los nombres
    propios (raros) pesan más que 'partido' o 'gol' (comunes). Mejora el
    agrupamiento sin IA — es TF-IDF simplificado sobre conjuntos."""
    if not set_a or not set_b:
        return 0.0
    inter = set_a & set_b
    union = set_a | set_b
    peso_inter = sum(pesos.get(w, 1.0) for w in inter)
    peso_union = sum(pesos.get(w, 1.0) for w in union)
    return peso_inter / peso_union if peso_union > 0 else 0.0


def _calcular_idf(listas_keys: list) -> dict:
    """Peso idf por palabra: log(N / docs_que_la_contienen). Palabra en muchos
    títulos → peso bajo; palabra rara → peso alto."""
    import math
    from collections import Counter
    N = len(listas_keys) or 1
    df = Counter()
    for keys in listas_keys:
        for w in keys:
            df[w] += 1
    return {w: math.log((N + 1) / (c + 1)) + 1.0 for w, c in df.items()}

def es_exclusivo(titulo: str, propio_id: str, resultados: dict) -> bool:
    keys = normalizar_titulo(titulo)
    if len(keys) < 2:
        return False
    for f in TODAS_FUENTES:
        if f["id"] == propio_id:
            continue
        for n in resultados.get(f["id"], []):
            if similitud_jaccard(keys, normalizar_titulo(n["titulo"])) >= SIMILITUD_UMBRAL:
                return False
    return True

def analizar_ole_vs_competencia(resultados: dict) -> dict:
    # Pre-calcular keysets
    keysets = {}
    for f in TODAS_FUENTES:
        keysets[f["id"]] = [
            {"noticia": n, "keys": normalizar_titulo(n["titulo"])}
            for n in resultados.get(f["id"], [])
        ]

    ole_items = keysets.get("ole", [])
    competencia = [f for f in TODAS_FUENTES if not f.get("es_ole")]

    # 1. Exclusivos Olé
    exclusivos_ole = []
    for item in ole_items:
        encontrado = any(
            similitud_jaccard(item["keys"], ci["keys"]) >= SIMILITUD_UMBRAL
            for fid, citems in keysets.items()
            if fid != "ole"
            for ci in citems
        )
        if not encontrado:
            exclusivos_ole.append(item["noticia"])

    # 2. Faltantes en Olé
    faltantes_en_ole = []
    ya_agregados_keys = []
    for fuente in competencia:
        for item in keysets.get(fuente["id"], []):
            # ¿Lo tiene Olé?
            tiene_ole = any(
                similitud_jaccard(item["keys"], oi["keys"]) >= SIMILITUD_UMBRAL
                for oi in ole_items
            )
            if not tiene_ole:
                # Deduplicar entre faltantes
                es_dup = any(
                    similitud_jaccard(item["keys"], k) >= SIMILITUD_UMBRAL
                    for k in ya_agregados_keys
                )
                if not es_dup:
                    ya_agregados_keys.append(item["keys"])
                    faltantes_en_ole.append({
                        "titulo": item["noticia"]["titulo"],
                        "url": item["noticia"].get("url"),
                        "fuente_id": fuente["id"],
                        "fuente_nombre": fuente["nombre"],
                        "fuente_color": fuente["color"],
                    })

    # 3. Cubiertos por ambos
    cubiertos_por_ambos = []
    for item in ole_items:
        competidores = []
        for fid, citems in keysets.items():
            if fid == "ole":
                continue
            for ci in citems:
                sim = similitud_jaccard(item["keys"], ci["keys"])
                if sim >= SIMILITUD_UMBRAL:
                    competidores.append({"fuente_id": fid, "noticia": ci["noticia"], "sim": sim})
                    break
        if competidores:
            cubiertos_por_ambos.append({
                "noticia_ole": item["noticia"],
                "competencia": competidores[:4],
            })

    return {
        "exclusivos_ole": exclusivos_ole,
        "faltantes_en_ole": faltantes_en_ole,
        "cubiertos_por_ambos": cubiertos_por_ambos,
    }

def _normalizar_publisher(nombre: str) -> str:
    """Clave estable para contar publishers, no canales de descubrimiento."""
    t = unicodedata.normalize("NFD", (nombre or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()[:100]


def _publisher_de(noticia: dict, fuente: dict) -> tuple:
    """Devuelve (clave, nombre). En Google News usa el medio original del RSS.
    Si no está disponible, cae al nombre de la fuente configurada."""
    nombre = (noticia.get("publisher_original") or fuente.get("nombre")
              or fuente.get("id") or "desconocido").strip()
    clave = _normalizar_publisher(nombre) or fuente.get("id", "desconocido")
    return clave, nombre


def calcular_tendencias(resultados: dict) -> list:
    todas = []
    for f in TODAS_FUENTES:
        for n in resultados.get(f["id"], []):
            pkey, pname = _publisher_de(n, f)
            todas.append({
                "noticia": n,
                "fuente": f,
                "keys": normalizar_titulo(n["titulo"]),
                "publisher_key": pkey,
                "publisher_name": pname,
            })

    # Pesos idf: las palabras raras (nombres propios) pesan más que las comunes.
    pesos = _calcular_idf([t["keys"] for t in todas])

    UMBRAL_CLUSTER = 0.22
    clusters = []
    asignado = [False] * len(todas)

    for i in range(len(todas)):
        if asignado[i]:
            continue
        base = todas[i]
        cluster = {
            "titulo": base["noticia"]["titulo"],
            "url": base["noticia"].get("url"),
            "fuente_ids": {base["fuente"]["id"]},
            "publisher_keys": {base["publisher_key"]},
            "publisher_names": {base["publisher_name"]},
            "publisher_zonas": {
                base["publisher_key"]: "nac" if base["fuente"]["id"] in FUENTES_NAC_IDS else "intl"
            },
            "noticias": [{"noticia": base["noticia"], "fuente": base["fuente"]}],
            "keys": base["keys"],
        }
        asignado[i] = True
        for j in range(i + 1, len(todas)):
            if asignado[j]:
                continue
            item = todas[j]
            if similitud_ponderada(cluster["keys"], item["keys"], pesos) >= UMBRAL_CLUSTER:
                cluster["fuente_ids"].add(item["fuente"]["id"])
                cluster["publisher_keys"].add(item["publisher_key"])
                cluster["publisher_names"].add(item["publisher_name"])
                cluster["publisher_zonas"].setdefault(
                    item["publisher_key"],
                    "nac" if item["fuente"]["id"] in FUENTES_NAC_IDS else "intl",
                )
                cluster["noticias"].append({"noticia": item["noticia"], "fuente": item["fuente"]})
                asignado[j] = True

        # Un tema es tendencia cuando aparece en al menos dos publishers reales.
        # Los feeds temáticos de Google News ya no cuentan como medios distintos.
        if len(cluster["publisher_keys"]) >= 2:
            clusters.append(cluster)

    clusters.sort(key=lambda c: (-len(c["publisher_keys"]), -len(c["noticias"])))
    salida = []
    for c in clusters:
        medios = sorted(c["publisher_names"], key=str.lower)
        tiene_ole = ("ole" in c["fuente_ids"] or
                     any(_normalizar_publisher(m) in {"ole", "ole com ar"} for m in medios))
        salida.append({
            "titulo": c["titulo"],
            "url": c["url"],
            "cant_medios": len(c["publisher_keys"]),
            "medios_originales": medios,
            "fuente_ids": sorted(c["fuente_ids"]),
            "noticias": c["noticias"],
            "tiene_ole": tiene_ole,
            "nac": sum(1 for z in c["publisher_zonas"].values() if z == "nac"),
            "intl": sum(1 for z in c["publisher_zonas"].values() if z == "intl"),
        })
    return salida


# ─── FRAMEWORK EDITORIAL: LOS 10 ÁNGULOS ─────────────────────────────────────
# Condensado del framework del editor: competir por el significado, no por la
# información. Se inyecta en el parte matutino y en los briefs.
FRAMEWORK_ANGULOS = """Antes de proponer nada, identificá: qué pasó, qué cambió, a quién afecta, qué emoción genera, qué patrón revela y qué consecuencia deja. No digas qué pasó: decí por qué importa para el hincha. Competí por el significado antes que por la información.

Los 10 ángulos que más rinden (elegí los 2-3 que mejor apliquen a cada tema):
1. CAMBIO DE ESTATUS — ¿alguien dejó de ser lo que era? ("ya no es revelación: es campeón")
2. PATRÓN — ¿esto ya pasó antes? ("la historia que Boca vuelve a repetir")
3. CONSECUENCIA — ¿qué cambia desde mañana? ("lo que cambia para River después de la final")
4. HÉROE INESPERADO — ¿quién apareció donde nadie lo esperaba?
5. CONFLICTO — ¿quién piensa distinto? ("la grieta que dejó la final")
6. PARADOJA — ¿qué contradicción hay? ("jugó mejor y perdió")
7. IDENTIDAD — ¿qué dice esto sobre el club y su gente?
8. TENDENCIA — ¿qué se está viendo venir?
9. QUÉ SIGNIFICA — ¿qué representa realmente? ("mucho más que un campeonato")
10. EL DÍA DESPUÉS — ¿qué queda cuando termina el ruido? ("la pregunta que River debe responder ahora")"""

# Criterios personales del editor (se cargan desde la celda criterios_editor
# de la pestaña Config; vacío si no está configurado)
CRITERIOS_EDITOR = ""


def bloque_criterios() -> str:
    if CRITERIOS_EDITOR.strip():
        return f"\n\nCRITERIOS DEL EDITOR (respetalos siempre):\n{CRITERIOS_EDITOR.strip()}"
    return ""


PASES_KEYWORDS = [
    "fichaje", "fichajes", "ficha a", "el pase de", "pase a", "refuerzo", "refuerzos",
    "transfer", "mercado de pases", "libro de pases", "oferta por", "ofertas por",
    "prestamo", "préstamo", "a prestamo", "cedido", "cesion", "cesión",
    "clausula", "cláusula", "acuerdo por el pase", "cerro la llegada", "cerró la llegada",
    "incorpora a", "incorporacion de", "incorporación de", "sumo a", "sumó a",
    "negocia por", "negociacion por", "negociación por", "here we go",
    "se va a", "deja el club", "rescision", "rescisión", "renovacion de contrato",
    "renovación de contrato", "renueva con", "firma con", "firmó con", "firmo con",
    "nuevo refuerzo", "vendido a", "venta de", "traspaso", "quiere contratar a",
    "oferta millonaria", "pretendido por", "seria nuevo", "sería nuevo",
    "es nuevo jugador", "llega a", "desembarca en",
]


def es_tema_de_pases(titulo: str) -> bool:
    t = titulo.lower()
    return any(k in t for k in PASES_KEYWORDS)


def solapamiento(a: set, b: set) -> float:
    """Coeficiente de solapamiento: intersección / el más chico de los dos.
    Mejor que Jaccard cuando un título es corto y creativo y el otro largo
    y descriptivo (el caso típico de Olé vs el resto)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# Palabras del léxico futbolero que no distinguen un tema de otro: dos títulos
# que solo comparten estas NO son el mismo tema.
GENERICOS_FUTBOL = {
    "acuerdo", "acordo", "pase", "pases", "fichaje", "fichajes", "refuerzo",
    "refuerzos", "vuelve", "vuelta", "regreso", "regresa", "llegada", "llega",
    "club", "equipo", "partido", "partidos", "gol", "goles", "final", "torneo",
    "futbol", "mercado", "oficial", "confirmado", "confirmada", "negociacion",
    "negociaciones", "jugador", "jugadores", "tecnico", "entrenador", "bombazo",
    "ultimo", "ultima", "primera", "primer", "hora", "horas", "video", "fotos",
}


def coincide_cobertura(a: set, b: set) -> bool:
    """¿Dos títulos hablan del mismo tema ya cubierto? Exige que compartan
    al menos 2 palabras DISTINTIVAS (nombres propios, no léxico genérico)."""
    if similitud_jaccard(a, b) >= 0.35:
        return True
    sa, sb = a - GENERICOS_FUTBOL, b - GENERICOS_FUTBOL
    return len(sa & sb) >= 2 and solapamiento(sa, sb) >= 0.5


def fetch_ultimas_ole() -> list:
    """Scrapea https://www.ole.com.ar/ultimas-noticias — el listado completo de
    lo publicado, incluidas las notas que nunca pisan la portada. Devuelve
    [{titulo, url}, ...]. Basado en el patrón data-noteid del sitio (estable),
    con la clase del listado como respaldo (parcial, sin el hash)."""
    try:
        resp = requests.get("https://www.ole.com.ar/ultimas-noticias",
                            headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        contenedores = soup.select("div[data-noteid]")
        if not contenedores:
            contenedores = soup.select("li[class*='listado']")
        out, vistos = [], set()
        for cont in contenedores:
            a = cont.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.ole.com.ar" + href
            if not href.startswith("http") or href in vistos:
                continue
            t_el = cont.find(["h1", "h2", "h3", "h4"])
            titulo = " ".join((t_el.get_text(strip=True) if t_el
                               else a.get_text(strip=True)).split())
            if len(titulo) < 16:
                # último recurso: armar el título desde el slug de la URL
                slug = href.rstrip("/").split("/")[-1].replace(".html", "")
                titulo = slug.replace("-", " ").capitalize()
                if len(titulo) < 16:
                    continue
            vistos.add(href)
            out.append({"titulo": titulo[:250], "url": href, "imagen": ""})
        return out[:MAX_ITEMS]
    except Exception:
        return []


def fetch_cobertura_ole_gnews() -> list:
    """Trae por Google News lo último publicado por Olé (más allá de su
    portada). Devuelve [{titulo, url}, ...]."""
    try:
        resp = requests.get(_gnews_url("ole.com.ar", "ole"), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return [{"titulo": _limpiar_titulo_gnews(n["titulo"]), "url": n.get("url") or ""}
                for n in extraer_rss(resp.text)]
    except Exception:
        return []


# ─── ENTIDADES (detección sin IA) ────────────────────────────────────────────
# Cada entidad: nombre canónico → lista de variantes/alias que buscar en los
# titulares (en minúscula, sin acentos, como los normaliza _norm_texto).
ENTIDADES_BASE = {
    # Grandes
    "River": ["river", "millonario", "nunez"], "Boca": ["boca", "xeneize", "bombonera"],
    "Racing": ["racing", "academia"], "Independiente": ["independiente", "rojo"],
    "San Lorenzo": ["san lorenzo", "ciclon", "cuervo"], "Huracan": ["huracan", "globo"],
    "Velez": ["velez", "fortin"], "Estudiantes": ["estudiantes", "pincha"],
    "Gimnasia": ["gimnasia", "lobo"], "Newells": ["newells", "newell", "leproso"],
    "Rosario Central": ["rosario central", "central", "canalla"],
    "Lanus": ["lanus", "granate"], "Banfield": ["banfield", "taladro"],
    "Talleres": ["talleres cordoba", "talleres", "matador"], "Belgrano": ["belgrano", "pirata"],
    "Defensa": ["defensa y justicia", "halcon"], "Argentinos": ["argentinos juniors", "argentinos", "bicho"],
    "Tigre": ["tigre matador", "tigre"], "Platense": ["platense", "calamar"],
    "Instituto": ["instituto cordoba", "instituto"], "Barracas": ["barracas central", "barracas"],
    "Sarmiento": ["sarmiento junin", "sarmiento"], "Union": ["union santa fe", "union"],
    "Colon": ["colon santa fe", "colon"], "Godoy Cruz": ["godoy cruz", "tomba"],
    "Central Cordoba": ["central cordoba"], "Riestra": ["deportivo riestra", "riestra"],
    # Selección
    "Seleccion": ["seleccion argentina", "seleccion", "albiceleste", "scaloneta"],
    "Sub-20": ["sub 20", "sub-20", "seleccion sub"], "Sub-23": ["sub 23", "sub-23"],
    # Figuras / DTs
    "Messi": ["messi", "leo messi"], "Scaloni": ["scaloni"], "Di Maria": ["di maria", "fideo"],
    "Julian Alvarez": ["julian alvarez", "julian"], "Dibu Martinez": ["dibu", "emiliano martinez"],
    "Gallardo": ["gallardo"], "Costas": ["costas"], "Enzo Fernandez": ["enzo fernandez"],
    "Mastantuono": ["mastantuono"], "Colapinto": ["colapinto"],
    # Torneos
    "Libertadores": ["libertadores"], "Sudamericana": ["sudamericana"],
    "Mundial": ["mundial", "copa del mundo", "world cup"],
    "Champions": ["champions", "champions league"],
    "Liga Profesional": ["liga profesional", "torneo local", "copa de la liga"],
    "Eliminatorias": ["eliminatorias"],
    # Grandes de Europa (para el mercado)
    "Real Madrid": ["real madrid"], "Barcelona": ["barcelona", "barca", "culé"],
    "PSG": ["psg", "paris saint"], "City": ["manchester city"], "United": ["manchester united"],
    "Inter": ["inter de milan", "inter milan"], "Milan": ["ac milan"], "Juventus": ["juventus", "juve"],
}


def _norm_texto(t: str) -> str:
    t = t.lower()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def detectar_entidades(titulo: str, dic: dict = None) -> list:
    """Devuelve la lista de entidades canónicas mencionadas en el titular.
    Sin IA: busca los alias como palabras/frases dentro del texto normalizado."""
    dic = dic or ENTIDADES_BASE
    t = " " + _norm_texto(titulo) + " "
    encontradas = []
    for canonico, alias in dic.items():
        for a in alias:
            # límite de palabra a ambos lados para no matchear "central" dentro de otra palabra
            if f" {a} " in t or t.startswith(f"{a} ") or t.endswith(f" {a}"):
                encontradas.append(canonico)
                break
    return encontradas


def parsear_entidades_extra(texto: str) -> dict:
    """Convierte 'River B=riverito | Pumas=pumas,rugby' en dict de entidades."""
    extra = {}
    if not texto or not texto.strip():
        return extra
    for bloque in texto.split("|"):
        if "=" not in bloque:
            continue
        nombre, alias = bloque.split("=", 1)
        nombre = nombre.strip()
        lista = [_norm_texto(a.strip()) for a in alias.split(",") if a.strip()]
        if nombre and lista:
            extra[nombre] = lista
    return extra


def dic_entidades(entidades_extra: str = "") -> dict:
    """Diccionario base + las entidades propias del editor (Config)."""
    d = dict(ENTIDADES_BASE)
    d.update(parsear_entidades_extra(entidades_extra))
    return d


def ranking_entidades(resultados: dict, dic: dict = None) -> list:
    """Cuenta menciones de cada entidad en todos los titulares de la corrida.
    Devuelve [{entidad, menciones, medios, tiene_ole}, ...] ordenado."""
    from collections import defaultdict
    conteo = defaultdict(lambda: {"menciones": 0, "medios": set(), "ole": False})
    for f in TODAS_FUENTES:
        for n in resultados.get(f["id"], []):
            for ent in detectar_entidades(n.get("titulo", ""), dic):
                c = conteo[ent]
                c["menciones"] += 1
                c["medios"].add(f["id"])
                if f["id"] == "ole":
                    c["ole"] = True
    out = [{"entidad": e, "menciones": v["menciones"], "medios": len(v["medios"]),
            "tiene_ole": v["ole"]} for e, v in conteo.items()]
    out.sort(key=lambda x: (-x["menciones"], -x["medios"]))
    return out



# ─── RELEVANCIA ARGENTINA (para notas del exterior) ──────────────────────────
# Señales de que una nota internacional puede impactar en Argentina.
RELEVANCIA_AR_KEYWORDS = [
    # país y selección
    "argentin", "albiceleste", "seleccion argentina", "scaloneta",
    "afa", "eliminatorias sudamericana",
    # figuras de la Selección
    "messi", "di maria", "julian alvarez", "lautaro", "mac allister",
    "enzo fernandez", "cuti romero", "dibu", "emiliano martinez", "garnacho",
    "mastantuono", "nico paz", "nico gonzalez", "otamendi", "paredes",
    "de paul", "lo celso", "tagliafico", "lisandro martinez", "licha martinez",
    "foyth", "molina", "montiel", "acuna", "palacios", "almada",
    "gonzalo montiel", "thiago almada", "valentin carboni", "carboni",
    "soule", "matias soule", "buonanotte", "simeone hijo", "giuliano simeone",
    # DTs argentinos en el mundo
    "colapinto", "river", "boca", "gallardo", "scaloni", "simeone",
    "cholo", "pochettino", "martino", "bielsa", "batistuta",
    "mascherano", "sebastian beccacece", "gustavo alfaro",
    # ex / que suenan para clubes argentinos
    "borre", "santos borre", "driussi", "beltran", "lucas beltran",
    # temas que impactan de rebote en Argentina
    "libertadores", "copa sudamericana", "mundial de clubes",
    "rival de argentina", "grupo de argentina",
    # mercado europeo que moviliza al hincha argentino
    "here we go", "fabrizio romano",
]


def relevancia_argentina(titulo: str) -> bool:
    """True si una nota internacional tiene gancho argentino: un jugador/DT
    argentino, un grande local, o alguien que suena para el fútbol argentino."""
    t = _norm_texto(titulo)
    return any(k in t for k in RELEVANCIA_AR_KEYWORDS)


def notas_exterior_relevantes(resultados: dict, max_items: int = 40) -> list:
    """Del panorama internacional, las notas con impacto argentino.
    Devuelve [{fuente, titulo, url, entidades}, ...] dedupeado."""
    out, vistos = [], set()
    for f in TODAS_FUENTES:
        # solo medios internacionales de verdad: afuera los nacionales Y el
        # grupo Primicias (GNews de River/Boca/Messi etc., que traen prensa argentina)
        if f["id"] in FUENTES_NAC_IDS or f["id"] in FUENTES_ESP_IDS:
            continue
        for n in resultados.get(f["id"], []):
            t = n.get("titulo", "")
            if not relevancia_argentina(t):
                continue
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append({"fuente": f, "titulo": t, "url": n.get("url"),
                        "entidades": detectar_entidades(t)})
    # ordenar: los que mencionan más entidades conocidas, primero
    out.sort(key=lambda x: -len(x["entidades"]))
    return out[:max_items]



# ─── FILTROS TEMÁTICOS (rebanadas del panorama, sin IA) ──────────────────────
FILTROS_TEMATICOS = {
    "mercado": {
        "titulo": "💸 Mercado de pases",
        "desc": "Fichajes, ofertas, negociaciones y movimientos del libro de pases.",
        "keywords": PASES_KEYWORDS,   # reusa el vocabulario de pases que ya existe
    },
    "polemica": {
        "titulo": "🔥 Polémicas y conflictos",
        "desc": "Escándalos, cruces, denuncias, sanciones y líos que generan debate.",
        "keywords": [
            "polemica", "escandalo", "denuncia", "sancion", "sancionado", "multa",
            "expulsado", "expulsion", "roja", "insulto", "agresion", "pelea",
            "cruce", "picante", "fuerte contra", "apunto contra", "estallo",
            "renuncia", "renuncio", "echado", "despido", "crisis", "conflicto",
            "arbitro", "arbitraje", "var polemico", "penal inexistente",
            "amenaza", "investigacion", "acusacion", "acuso", "repudio", "furia",
        ],
    },
    "viral": {
        "titulo": "😮 Virales y color",
        "desc": "Lo insólito, emotivo, curioso y con potencial de tráfico.",
        "keywords": [
            "insolito", "insólito", "insolita", "viral", "se hizo viral", "furor",
            "increible", "increíble", "emotivo", "emocionante", "conmovedor",
            "el gesto de", "insolita imagen", "nunca visto", "las redes",
            "estallaron las redes", "el video que", "el video de", "video viral",
            "las fotos de", "memes", "los memes", "se emociono", "se emocionó",
            "hasta las lagrimas", "hasta las lágrimas", "revoluciono", "revolucionó",
            "curioso", "curiosa", "bizarro", "papelon", "papelón", "blooper",
            "la reaccion de", "la reacción de", "lo que hizo", "no vas a creer",
            "insolita situacion", "camara capto", "cámara captó",
        ],
    },
    "confirmado": {
        "titulo": "✅ Confirmado / Oficial",
        "desc": "Noticia dura confirmada: anuncios, comunicados, oficializaciones.",
        "keywords": [
            "confirmado", "confirmada", "confirmo", "confirmó", "oficial",
            "oficializo", "oficializó", "es oficial", "anuncio", "anunció",
            "anuncia", "comunicado", "parte oficial", "hizo oficial",
            "acuerdo cerrado", "cerrado", "firmado", "sellado", "hecho oficial",
            "ya es", "de forma oficial", "presento", "presentó", "presentacion oficial",
        ],
    },
    "lesiones": {
        "titulo": "🏥 Lesiones / Bajas",
        "desc": "Parte médico: lesiones, molestias, bajas y recuperaciones.",
        "keywords": [
            "lesion", "lesión", "lesionado", "lesionada", "desgarro", "distension",
            "distensión", "molestia", "operado", "operacion", "operación",
            "sera operado", "será operado", "baja", "se rompio", "se rompió",
            "rotura", "resonancia", "estudios medicos", "estudios médicos",
            "parte medico", "parte médico", "tiempo de recuperacion",
            "vuelve a las canchas", "recuperacion", "recuperación", "esguince",
            "sobrecarga", "tocado", "en duda por", "se resiente",
        ],
    },
    "previa": {
        "titulo": "📅 Previa / Formaciones",
        "desc": "Todo lo pre-partido: formaciones, convocados, cómo llegan.",
        "keywords": [
            "formacion", "formación", "probable formacion", "el once", "onces",
            "la probable", "cómo llegan", "como llegan", "la previa", "previa del",
            "concentrados", "convocados", "convocatoria", "lista de convocados",
            "el equipo para", "sale con", "saldria con", "saldría con",
            "los citados", "hora y tv", "horario y tv", "donde ver", "dónde ver",
            "arbitro del partido", "árbitro del partido", "posibles titulares",
        ],
    },
    "declaraciones": {
        "titulo": "🎙️ Declaraciones",
        "desc": "Lo que dijo alguien: frases, conferencias, cruces verbales.",
        "keywords": [
            "aseguro", "aseguró", "declaro", "declaró", "hablo", "habló",
            "palabras de", "en conferencia", "conferencia de prensa", "dijo",
            "afirmo", "afirmó", "sentencio", "sentenció", "disparo contra",
            "disparó contra", "picante contra", "apunto contra", "apuntó contra",
            "se sincero", "se sinceró", "revelo", "reveló", "confeso", "confesó",
            "explico", "explicó", "reconocio", "reconoció", "banco a", "bancó a",
            "respondio", "respondió", "cruce", "fuerte contra",
        ],
    },
    "arbitraje": {
        "titulo": "⚖️ Reglamento / Arbitraje",
        "desc": "VAR, penales, expulsiones, designaciones y jugadas polémicas.",
        "keywords": [
            "var", "penal", "penales", "offside", "orsai", "fuera de juego",
            "expulsion", "expulsión", "expulsado", "roja", "tarjeta roja",
            "doble amarilla", "designacion", "designación", "designado",
            "dirigira", "dirigirá", "arbitro", "árbitro", "arbitraje",
            "polemica arbitral", "polémica arbitral", "mano en el area",
            "mano en el área", "gol anulado", "anulado", "revision del var",
            "revisión del var", "cobro", "no cobro", "reglamento",
        ],
    },
}


def filtrar_custom(resultados: dict, keywords: list, solo_ar: bool = False,
                   max_items: int = 60) -> list:
    """Filtro personalizado del Streamlit: rebana el panorama por una lista de
    palabras libres que escribe el editor. Sin IA."""
    if not keywords:
        return []
    kws = [_norm_texto(k) for k in keywords if k.strip()]
    out, vistos = [], set()
    for f in TODAS_FUENTES:
        for n in resultados.get(f["id"], []):
            t = n.get("titulo", "")
            tn = _norm_texto(t)
            if not any(k in tn for k in kws):
                continue
            if solo_ar and not relevancia_argentina(t):
                continue
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append({"fuente": f, "titulo": t, "url": n.get("url"),
                        "entidades": detectar_entidades(t)})
    out.sort(key=lambda x: -len(x["entidades"]))
    return out[:max_items]


def filtrar_por_tema(resultados: dict, filtro_id: str, solo_ar: bool = False,
                     max_items: int = 50) -> list:
    """Rebana el panorama por un filtro temático. Si solo_ar=True, además exige
    gancho argentino. Devuelve [{fuente, titulo, url, entidades}, ...]."""
    conf = FILTROS_TEMATICOS.get(filtro_id)
    if not conf:
        return []
    kws = conf["keywords"]
    out, vistos = [], set()
    for f in TODAS_FUENTES:
        for n in resultados.get(f["id"], []):
            t = n.get("titulo", "")
            tn = _norm_texto(t)
            if not any(k in tn for k in kws):
                continue
            if solo_ar and not relevancia_argentina(t):
                continue
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append({"fuente": f, "titulo": t, "url": n.get("url"),
                        "entidades": detectar_entidades(t)})
    out.sort(key=lambda x: -len(x["entidades"]))
    return out[:max_items]



# ─── MÉTRICAS: parser del Reporte Diario de Olé (BigData AGEA) ───────────────
def _filas_por_columnas_pdf(page, cortes):
    from collections import defaultdict
    lineas = defaultdict(list)
    for w in page.extract_words():
        lineas[round(w["top"])].append(w)
    filas = []
    for t in sorted(lineas):
        ws = sorted(lineas[t], key=lambda w: w["x0"])
        cols = [""] * (len(cortes) + 1)
        for w in ws:
            i = 0
            while i < len(cortes) and w["x0"] >= cortes[i]:
                i += 1
            cols[i] = (cols[i] + " " + w["text"]).strip()
        filas.append(cols)
    return filas


def parsear_reporte_ole(ruta_o_bytes) -> dict:
    """Extrae del Reporte Diario de Olé (PDF de BigData): fecha, notas más
    vistas (acumulado), publicadas ese día y menos vistas, con sus páginas
    vistas. Requiere pdfplumber (import interno para no romper al vigía)."""
    import pdfplumber
    pdf = pdfplumber.open(ruta_o_bytes)
    out = {"fecha": None, "mas_vistas": [], "publicadas_hoy": [], "menos_vistas": []}
    for page in pdf.pages:
        texto = page.extract_text() or ""
        primera = texto.split("\n")[0] if texto else ""
        if out["fecha"] is None:
            m = re.search(r"\b(\d{2}/\d{2})\b", primera)
            if m:
                out["fecha"] = m.group(1)
        if "Más Vistas" in primera and "Publicadas" in primera:
            destino = "publicadas_hoy"
        elif "Más Vistas" in primera and "Top de Notas" in primera:
            destino = "mas_vistas"
        elif "Menos Vistas" in primera:
            destino = "menos_vistas"
        else:
            continue
        for cols in _filas_por_columnas_pdf(page, [500, 615, 720]):
            titulo, seccion, pub, vistas = cols[0], cols[1], cols[2], cols[3]
            v = vistas.replace(".", "").replace(",", "")
            if not titulo or not v.isdigit():
                continue
            if titulo.startswith(("Nota", "NNoott", "Olé |")):
                continue
            out[destino].append({"titulo": titulo, "seccion": seccion,
                                 "publicacion": pub, "vistas": int(v)})
    return out


def cruzar_metricas(notas: list, historial: list = None,
                    entidades_extra: str = "") -> list:
    """Enriquece cada nota leída con lo que el sistema sabe: entidades que
    menciona y si el tema estaba en el panorama (Historial de temas calientes).
    Sin IA: matching de títulos."""
    dic = dic_entidades(entidades_extra)
    hist_keys = [normalizar_titulo(h.get("titulo", h) if isinstance(h, dict) else h)
                 for h in (historial or [])]
    out = []
    for n in notas:
        keys = normalizar_titulo(n["titulo"])
        en_panorama = any(solapamiento(keys, hk) >= 0.35 for hk in hist_keys if hk)
        out.append({**n,
                    "entidades": detectar_entidades(n["titulo"], dic),
                    "en_panorama": en_panorama})
    return out



# ─── SEMÁFORO PREDICTIVO (se entrena con la pestaña Métricas) ────────────────
def _franja_horaria(hora: str) -> str:
    """'15:50' → 'tarde'. Devuelve '' si no hay hora parseable."""
    m = re.match(r"(\d{1,2}):\d{2}", (hora or "").strip())
    if not m:
        return ""
    h = int(m.group(1))
    if 5 <= h < 11: return "manana"
    if 11 <= h < 15: return "mediodia"
    if 15 <= h < 20: return "tarde"
    return "noche"


def _dia_semana(fecha: str) -> str:
    """'2026-07-17' o '17/07' → 'vie'. '' si no parsea."""
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            d = datetime.strptime(fecha.strip(), fmt)
            if fmt == "%d/%m":
                d = d.replace(year=datetime.now().year)
            return ["lun","mar","mie","jue","vie","sab","dom"][d.weekday()]
        except Exception:
            continue
    return ""


def _features_nota(titulo: str, seccion: str = "", entidades: list = None,
                   en_panorama: bool = False, hora: str = "",
                   momentum: str = "", nov_entidad: str = "", fecha: str = "") -> dict:
    """Convierte una nota en el vector de características del modelo.
    Mismo constructor para entrenar y para predecir (clave de consistencia)."""
    t = titulo or ""
    tn = _norm_texto(t)
    ents = entidades if entidades is not None else detectar_entidades(t)
    f = {
        "len_titulo": min(len(t), 200) / 100.0,
        "tiene_dospuntos": 1 if ":" in t else 0,
        "tiene_cifra": 1 if re.search(r"\d", t) else 0,
        "tiene_pregunta": 1 if "?" in t or "¿" in t else 0,
        "tiene_comillas": 1 if '"' in t or "\u201c" in t else 0,
        "n_entidades": len(ents),
        "en_panorama": 1 if en_panorama else 0,
    }
    for e in ents[:5]:
        f[f"ent_{e}"] = 1
    if seccion:
        f[f"sec_{seccion.strip()[:30]}"] = 1
    for fid, conf in FILTROS_TEMATICOS.items():
        if any(k in tn for k in conf["keywords"]):
            f[f"tipo_{fid}"] = 1
    fr = _franja_horaria(hora)
    if fr:
        f[f"franja_{fr}"] = 1
    cl = clasificar_titulo_liviano(t)
    f[f"func_{cl['funcion']}"] = 1
    for e in cl["estructuras"]:
        f[f"estruct_{e}"] = 1
    f["calidad_titulo"] = cl["calidad"] / 10.0
    if momentum:
        f[f"mom_{momentum}"] = 1        # subiendo / bajando / estable
    if nov_entidad:
        f[f"nov_{nov_entidad}"] = 1     # emergente / habitual
    ds = _dia_semana(fecha)
    if ds:
        f[f"dow_{ds}"] = 1
    return f


_HIST_PARA_MOMENTUM = []  # lo setea la app antes de entrenar (opcional)


def _campo(h: dict, *nombres, default=""):
    """Lee un campo del historial sin importar si viene 'Titulo' o 'titulo'."""
    for n in nombres:
        if n in h and h[n] not in (None, ""):
            return h[n]
        for k in h:
            if k.lower().replace("_", "") == n.lower().replace("_", "") and h[k] not in (None, ""):
                return h[k]
    return default


def _indice_momentum(historial: list) -> dict:
    """Precalcula, por tema del historial, su trayectoria de medios: devuelve
    dict {(fecha, frozenset_keys): 'subiendo'|'bajando'|'estable'} comparando
    la primera vs la última aparición del tema ese día."""
    from collections import defaultdict
    series = defaultdict(list)
    for h in historial:
        titulo = str(_campo(h, "Titulo", "titulo"))
        if not titulo:
            continue
        try:
            medios = int(_campo(h, "CantMedios", "cant_medios", default=0) or 0)
        except Exception:
            continue
        keys = frozenset(normalizar_titulo(titulo))
        if keys:
            series[(str(_campo(h, "Fecha", "fecha")), keys)].append(
                (str(_campo(h, "Hora", "hora")), medios))
    out = {}
    for clave, obs in series.items():
        obs.sort()
        if len(obs) < 2:
            out[clave] = "estable"
        else:
            delta = obs[-1][1] - obs[0][1]
            out[clave] = "subiendo" if delta >= 2 else ("bajando" if delta <= -2 else "estable")
    return out


def _momentum_de(titulo: str, idx: dict, fecha: str = "") -> str:
    """Busca el momentum de un título contra el índice precalculado."""
    keys = frozenset(normalizar_titulo(titulo))
    if not keys:
        return ""
    # match exacto por fecha si está, o el mejor solapamiento
    if (fecha, keys) in idx:
        return idx[(fecha, keys)]
    mejor, mejor_sol = "", 0.0
    for (f, k), mom in idx.items():
        s = solapamiento(set(keys), set(k))
        if s > mejor_sol and s >= 0.5:
            mejor_sol, mejor = s, mom
    return mejor


def entrenar_semaforo(metricas: list) -> dict:
    """Entrena el clasificador 🟢🟡🔴 con las filas de la pestaña Métricas.
    Devuelve el paquete (modelos + métricas de evaluación) o un dict con error.
    Import de sklearn adentro: el vigía no lo necesita ni lo carga."""
    import math
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier

    filas = [m for m in metricas if m.get("Titulo") and str(m.get("Vistas", "")).isdigit()]
    if len(filas) < 150:
        return {"error": f"Datos insuficientes: {len(filas)} notas (mínimo 150). Seguí cargando reportes."}

    # etiquetas por terciles de log-vistas (verde/amarillo/rojo)
    logs = sorted(math.log10(int(m["Vistas"]) + 1) for m in filas)
    c1 = logs[len(logs) // 3]
    c2 = logs[2 * len(logs) // 3]

    def etiqueta(v):
        lv = math.log10(int(v) + 1)
        return "verde" if lv >= c2 else ("amarillo" if lv >= c1 else "rojo")

    # orden temporal para el split honesto (entrenar pasado, testear futuro).
    # Las filas sin fecha real (histórico "hist90") se MEZCLAN entre sí antes:
    # suelen venir ordenadas por vistas, y ese orden rompería la evaluación.
    import random as _rnd
    def clave_fecha(m):
        p = (m.get("Fecha") or "").split("/")
        if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
            return (int(p[1]), int(p[0]))
        return None
    sin_fecha = [m for m in filas if clave_fecha(m) is None]
    con_fecha = sorted((m for m in filas if clave_fecha(m) is not None), key=clave_fecha)
    _rnd.Random(7).shuffle(sin_fecha)
    filas = sin_fecha + con_fecha

    idx_mom = _indice_momentum(_HIST_PARA_MOMENTUM) if _HIST_PARA_MOMENTUM else {}
    X_raw, y = [], []
    for m in filas:
        ents = [e.strip() for e in (m.get("Entidades") or "").split("·") if e.strip()]
        mom = _momentum_de(m["Titulo"], idx_mom, m.get("Fecha", "")) if idx_mom else ""
        X_raw.append(_features_nota(m["Titulo"], m.get("Seccion", ""), ents,
                                    m.get("EnPanorama") == "sí", m.get("Hora", ""),
                                    momentum=mom, fecha=m.get("Fecha", "")))
        y.append(etiqueta(m["Vistas"]))

    corte = max(int(len(X_raw) * 0.8), len(X_raw) - 400)
    vec = DictVectorizer(sparse=False)
    Xtr = vec.fit_transform(X_raw[:corte]); ytr = y[:corte]
    Xte = vec.transform(X_raw[corte:]);     yte = y[corte:]

    base = max(set(ytr), key=ytr.count)
    acc_mayoritaria = sum(1 for v in yte if v == base) / max(len(yte), 1)
    # base honesta: la mejor apuesta ciega nunca rinde menos que el azar (1/3);
    # sin este piso, un test sin la clase mayoritaria muestra "0%" engañoso
    acc_base = max(acc_mayoritaria, 1.0 / 3.0)

    logit = LogisticRegression(max_iter=1000)
    logit.fit(Xtr, ytr)
    acc_logit = logit.score(Xte, yte) if len(yte) else 0.0

    rf = RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=7)
    rf.fit(Xtr, ytr)
    acc_rf = rf.score(Xte, yte) if len(yte) else 0.0

    ganador = ("rf", rf, acc_rf) if acc_rf >= acc_logit else ("logit", logit, acc_logit)
    # factores globales interpretables (de la logística, que es la legible)
    nombres = vec.get_feature_names_out()
    idx_verde = list(logit.classes_).index("verde")
    pesos = sorted(zip(nombres, logit.coef_[idx_verde]), key=lambda x: -x[1])
    return {"vec": vec, "modelo": ganador[1], "tipo": ganador[0],
            "acc": ganador[2], "acc_base": acc_base, "acc_logit": acc_logit,
            "acc_rf": acc_rf, "n_train": len(ytr), "n_test": len(yte),
            "clases": list(ganador[1].classes_),
            "factores_verde": pesos[:8], "frena_verde": pesos[-5:],
            "logit": logit, "preliminar": len(filas) < 500}


def predecir_semaforo(pack: dict, titulo: str, seccion: str = "",
                      en_panorama: bool = False, hora: str = "") -> dict:
    """Devuelve clase, probabilidades y razones para un título nuevo."""
    f = _features_nota(titulo, seccion, None, en_panorama, hora)
    X = pack["vec"].transform([f])
    probas = pack["modelo"].predict_proba(X)[0]
    clases = list(pack["modelo"].classes_)
    orden = sorted(zip(clases, probas), key=lambda x: -x[1])
    pred = orden[0][0]
    # razones: features activas ordenadas por su peso hacia la clase predicha (logística)
    nombres = list(pack["vec"].get_feature_names_out())
    idx = list(pack["logit"].classes_).index(pred)
    coefs = pack["logit"].coef_[idx]
    activos = [(n, coefs[i]) for i, n in enumerate(nombres) if X[0][i] != 0]
    activos.sort(key=lambda x: -abs(x[1]))
    return {"clase": pred, "probas": orden,
            "empuja": [n for n, c in activos if c > 0][:4],
            "frena": [n for n, c in activos if c < 0][:3]}



# ─── DETECTOR DE INCENDIOS (¿este tema chico va a explotar?) ─────────────────
def _dataset_incendios(historial: list, umbral_explota: int = 8,
                       ventana_horas: int = 12) -> tuple:
    """Construye ejemplos desde el Historial: cada tema visto CHICO (2-5 medios)
    por primera vez en el día, etiquetado según si llegó a umbral_explota medios
    dentro de la ventana. Devuelve (X_raw, y, timestamps)."""
    from datetime import datetime, timedelta
    filas = []
    for h in historial:
        f_txt = str(_campo(h, "Fecha", "fecha"))
        h_txt = str(_campo(h, "Hora", "hora"))
        ts = None
        for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M"):
            try:
                ts = datetime.strptime(f"{f_txt} {h_txt}".strip(), fmt)
                if fmt == "%d/%m %H:%M":
                    ts = ts.replace(year=datetime.now().year)
                break
            except Exception:
                continue
        if ts is None:
            continue
        try:
            medios = int(_campo(h, "CantMedios", "cant_medios", default=0) or 0)
        except Exception:
            continue
        titulo = str(_campo(h, "Titulo", "titulo"))
        if not titulo:
            continue
        ole_val = _campo(h, "TieneOle", "tiene_ole", default=False)
        filas.append({"ts": ts, "titulo": titulo, "medios": medios,
                      "keys": normalizar_titulo(titulo),
                      "ole": ole_val in (True, "1", 1, "sí", "si")})
    filas.sort(key=lambda f: f["ts"])

    X_raw, y, tss = [], [], []
    vistos_dia = set()  # (fecha, frozenset_keys) para tomar solo el primer avistaje
    for i, f in enumerate(filas):
        if not (2 <= f["medios"] <= 5) or not f["keys"]:
            continue
        marca = (f["ts"].date(), frozenset(f["keys"]))
        if marca in vistos_dia:
            continue
        vistos_dia.add(marca)
        limite = f["ts"] + timedelta(hours=ventana_horas)
        max_futuro = f["medios"]
        for g in filas[i+1:]:
            if g["ts"] > limite:
                break
            if solapamiento(f["keys"], g["keys"]) >= 0.4:
                max_futuro = max(max_futuro, g["medios"])
        feats = _features_nota(f["titulo"], "", None, False,
                               f["ts"].strftime("%H:%M"))
        feats["medios_ahora"] = f["medios"] / 10.0
        feats["ya_en_ole"] = 1 if f["ole"] else 0
        X_raw.append(feats)
        y.append("explota" if max_futuro >= umbral_explota else "no")
        tss.append(f["ts"])
    return X_raw, y, tss


def entrenar_detector(historial: list) -> dict:
    """Entrena el detector de incendios con el Historial. Devuelve pack con
    métricas honestas (incluye precisión y cobertura de la clase 'explota')."""
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier

    X_raw, y, tss = _dataset_incendios(historial)
    n_exp = y.count("explota")
    if len(y) < 120 or n_exp < 15:
        return {"error": f"Datos insuficientes: {len(y)} temas chicos rastreados, "
                         f"{n_exp} explosiones. El Historial necesita más días acumulados."}
    corte = int(len(y) * 0.8)
    vec = DictVectorizer(sparse=False)
    Xtr = vec.fit_transform(X_raw[:corte]); ytr = y[:corte]
    Xte = vec.transform(X_raw[corte:]);     yte = y[corte:]

    base = max(set(ytr), key=ytr.count)
    acc_base = max(sum(1 for v in yte if v == base) / max(len(yte), 1), 0.5)

    logit = LogisticRegression(max_iter=1000, class_weight="balanced")
    logit.fit(Xtr, ytr)
    rf = RandomForestClassifier(n_estimators=200, min_samples_leaf=3,
                                class_weight="balanced", random_state=7)
    rf.fit(Xtr, ytr)
    acc_l, acc_r = logit.score(Xte, yte), rf.score(Xte, yte)
    tipo, modelo, acc = ("rf", rf, acc_r) if acc_r >= acc_l else ("logit", logit, acc_l)

    # métricas de la clase que importa: 🔥 explota
    pred = modelo.predict(Xte)
    tp = sum(1 for p, v in zip(pred, yte) if p == "explota" and v == "explota")
    fp = sum(1 for p, v in zip(pred, yte) if p == "explota" and v == "no")
    fn = sum(1 for p, v in zip(pred, yte) if p == "no" and v == "explota")
    precision_fuego = tp / max(tp + fp, 1)
    cobertura_fuego = tp / max(tp + fn, 1)

    nombres = vec.get_feature_names_out()
    idx = list(logit.classes_).index("explota")
    pesos = sorted(zip(nombres, logit.coef_[idx]), key=lambda x: -x[1])
    return {"vec": vec, "modelo": modelo, "logit": logit, "tipo": tipo,
            "acc": acc, "acc_base": acc_base, "n_train": len(ytr),
            "n_test": len(yte), "n_explosiones": n_exp,
            "precision_fuego": precision_fuego, "cobertura_fuego": cobertura_fuego,
            "factores_fuego": pesos[:8]}


def predecir_incendio(pack: dict, titulo: str, medios_ahora: int,
                      hora: str = "") -> dict:
    """Probabilidad de que un tema chico explote en las próximas horas."""
    f = _features_nota(titulo, "", None, False, hora)
    f["medios_ahora"] = medios_ahora / 10.0
    X = pack["vec"].transform([f])
    probas = dict(zip(pack["modelo"].classes_, pack["modelo"].predict_proba(X)[0]))
    p = probas.get("explota", 0.0)
    nombres = list(pack["vec"].get_feature_names_out())
    idx = list(pack["logit"].classes_).index("explota")
    coefs = pack["logit"].coef_[idx]
    activos = sorted(((n, coefs[i]) for i, n in enumerate(nombres) if X[0][i] != 0),
                     key=lambda x: -abs(x[1]))
    return {"prob": p, "empuja": [n for n, c in activos if c > 0][:4],
            "frena": [n for n, c in activos if c < 0][:3]}


# ─── AGENDA ACCIONABLE + MOMENTUM ─────────────────────────────────────────────
def calcular_momentum(tendencias: list, prev_tendencias: list) -> dict:
    """Compara cada cluster actual con el más parecido del snapshot anterior.
    Devuelve {indice_actual: {'delta': int, 'nuevo': bool}}.
    'delta' = variación en cantidad de medios; 'nuevo' si no matchea ninguno previo."""
    prev = prev_tendencias or []
    prev_keys = [normalizar_titulo(c["titulo"]) for c in prev]
    out = {}
    for i, c in enumerate(tendencias):
        k = normalizar_titulo(c["titulo"])
        best_j, best_sim = -1, 0.0
        for j, pk in enumerate(prev_keys):
            s = similitud_jaccard(k, pk)
            if s > best_sim:
                best_sim, best_j = s, j
        if best_j >= 0 and best_sim >= 0.30:
            out[i] = {"delta": c["cant_medios"] - prev[best_j]["cant_medios"], "nuevo": False}
        else:
            out[i] = {"delta": c["cant_medios"], "nuevo": True}
    return out

def construir_agenda(tendencias: list, ole_analisis: dict, prev_tendencias: list,
                     max_items: int = 14, cubiertos: list = None) -> list:
    """Convierte tendencias + análisis Olé en una lista priorizada de ACCIONES.
    Cada ítem trae un verbo (SUBIR YA / REDACTAR / SEGUIR / EMPUJAR), el motivo,
    el momentum y las noticias del cluster."""
    momentum = calcular_momentum(tendencias, prev_tendencias)
    items = []
    for i, c in enumerate(tendencias):
        mom = momentum.get(i, {"delta": 0, "nuevo": False})
        delta, nuevo = mom["delta"], mom["nuevo"]
        base = c["cant_medios"]
        tiene_ole = c.get("tiene_ole")
        score = base + max(delta, 0) * 2.5 + (3 if nuevo else 0) + (4 if not tiene_ole else 0)

        # ¿Es un hueco de verdad, o ya lo dimos en días anteriores?
        ya_dado = None
        if not tiene_ole and cubiertos:
            k_actual = normalizar_titulo(c["titulo"])
            for cub in cubiertos:
                if coincide_cobertura(k_actual, normalizar_titulo(cub["titulo"])):
                    ya_dado = cub
                    break
        if ya_dado is not None:
            cuando = ya_dado.get("fecha") or "estos días"
            accion = "RETOMAR"
            motivo = f"lo diste el {cuando} y hoy {base} medios lo mueven — ¿actualización o segunda vuelta?"
            score += 1
        elif not tiene_ole and base >= 3:
            accion, motivo = "SUBIR YA", f"{base} medios lo tienen y Olé no"
        elif not tiene_ole:
            accion, motivo = "REDACTAR", f"{base} medio(s) lo cubren y Olé no"
        elif nuevo or delta >= 2:
            accion = "SEGUIR"
            motivo = ("tema nuevo creciendo" if nuevo else f"creciendo (+{delta} medios)") + " — reforzá tu ángulo"
            score += 1
        else:
            continue  # ya cubierto por Olé y estable: no es una acción

        items.append({
            "accion": accion, "motivo": motivo, "titulo": c["titulo"], "url": c.get("url"),
            "cant_medios": base, "delta": delta, "nuevo": nuevo,
            "nac": c.get("nac", 0), "intl": c.get("intl", 0),
            "noticias": c.get("noticias", []), "score": score,
        })

    for n in (ole_analisis or {}).get("exclusivos_ole", [])[:5]:
        items.append({
            "accion": "EMPUJAR", "motivo": "exclusivo de Olé — promocionalo o hacé segunda vuelta",
            "titulo": n["titulo"], "url": n.get("url"),
            "cant_medios": 1, "delta": 0, "nuevo": False, "nac": 1, "intl": 0,
            "noticias": [], "score": 2.0,
        })

    items.sort(key=lambda x: -x["score"])
    return items[:max_items]

def prompt_parte_editorial(agenda: list) -> str:
    lineas = "\n".join(
        f"  {i+1}. [{it['accion']}] {it['titulo']} ({it['cant_medios']} medios; {it['motivo']})"
        for i, it in enumerate(agenda[:10])
    )
    return f"""Sos editor jefe de Olé. Esta es la agenda priorizada de forma automática.
Por cada ítem, en UNA sola línea, decime por qué le importa a un lector argentino y un ángulo concreto para la nota. Telegráfico, español rioplatense, sin relleno.

{lineas}"""

def prompt_brief_item(item: dict) -> str:
    fuentes_ctx = ""
    if item.get("noticias"):
        fuentes_ctx = "\nCómo lo titularon otros medios:\n" + "\n".join(
            f'  • [{n["fuente"]["nombre"]}] {n["noticia"]["titulo"]}'
            for n in item["noticias"][:6]
        )
    return f"""Sos editor jefe de Olé.

{FRAMEWORK_ANGULOS}{bloque_criterios()}

Para este tema, dame un mini-brief telegráfico en español rioplatense:
VALOR: por qué importa para el hincha (qué está en juego, no cuántos medios lo tienen).
ÁNGULOS: los 2 mejores ángulos del framework aplicados a ESTE tema — que ningún otro medio haya usado (mirá cómo titularon ellos).
TÍTULO: un título filoso para el mejor ángulo.

TEMA: {item["titulo"]}{fuentes_ctx}"""

AGENDA_COLORES = {
    "SUBIR YA": "#c0392b", "REDACTAR": "#d68910", "RETOMAR": "#7d3c98", "EXPLOTA": "#e67e22",
    "SEGUIR": "#2471a3", "EMPUJAR": "#1e8449",
}

def analizar_ole_vs_compecencia_safe(resultados: dict) -> dict:
    """Wrapper seguro para el análisis semántico."""
    try:
        return analizar_ole_vs_competencia(resultados)
    except Exception as e:
        return {"exclusivos_ole": [], "faltantes_en_ole": [], "cubiertos_por_ambos": []}

# ─── EXTRACCIÓN HTML ──────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
}

# Patrones para detectar imágenes genéricas/logos (definidos aquí para uso en extraer_generico)
_GENERIC_IMAGE_PATTERNS_EARLY = [
    "logo", "brand", "favicon", "default", "placeholder",
    "og-default", "og_default", "share-default",
    "ole-logo", "ole_logo", "icon",
]

def _es_imagen_generica(img_url: str) -> bool:
    """Retorna True si la URL parece ser un logo o imagen genérica del sitio."""
    if not img_url:
        return True
    lower = img_url.lower()
    return any(pat in lower for pat in _GENERIC_IMAGE_PATTERNS_EARLY)

def _extraer_imagen_rss_item(item_raw: str) -> str:
    """Extrae la imagen de un item RSS crudo (string XML). Más robusto que BS4 con namespaces."""
    # 1. media:content url="..."
    m = re.search(r'<media:content[^>]+url=["\']([^"\']+)["\']', item_raw)
    if m:
        src = m.group(1)
        if src.startswith("http") and not src.endswith(".gif") and not _es_imagen_generica(src):
            return src

    # 2. media:thumbnail url="..."
    m = re.search(r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']', item_raw)
    if m:
        src = m.group(1)
        if src.startswith("http") and not src.endswith(".gif") and not _es_imagen_generica(src):
            return src

    # 3. enclosure type="image/..." url="..."
    m = re.search(r'<enclosure[^>]+type=["\']image/[^"\']*["\'][^>]+url=["\']([^"\']+)["\']', item_raw)
    if not m:
        m = re.search(r'<enclosure[^>]+url=["\']([^"\']+)["\'][^>]+type=["\']image/[^"\']*["\']', item_raw)
    if m:
        src = m.group(1)
        if src.startswith("http") and not _es_imagen_generica(src):
            return src

    # 4. content:encoded o description — buscar primer <img src="...">
    for tag in ["content:encoded", "description"]:
        m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', item_raw, re.DOTALL)
        if m:
            content = m.group(1)
            # Decodificar CDATA si aplica
            cdata = re.search(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
            if cdata:
                content = cdata.group(1)
            # Buscar src= en img tags
            img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if img_m:
                src = img_m.group(1)
                if src.startswith("http") and not src.endswith(".gif") and not _es_imagen_generica(src):
                    return src
            # También wp:featuredmedia o similares con URL
            wp_m = re.search(r'https?://[^\s"\'<>]+(?:jpg|jpeg|png|webp)', content, re.IGNORECASE)
            if wp_m:
                src = wp_m.group(0)
                if not _es_imagen_generica(src):
                    return src

    return ""

CORE_VERSION = "núcleo v26 · publishers reales + snapshots online"
MAX_ANTIGUEDAD_HORAS = 48  # notas de RSS/Google News más viejas que esto se descartan


def _fecha_item_rss(item) -> "datetime | None":
    """Lee la fecha de publicación de un item RSS (pubDate) o Atom (published/updated)."""
    for tag in ("pubDate", "published", "updated", "dc:date"):
        t = item.find(tag)
        if t and t.get_text(strip=True):
            texto = t.get_text(strip=True)
            try:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(texto)          # RFC-822 (RSS)
            except Exception:
                pass
            try:
                return datetime.fromisoformat(texto.replace("Z", "+00:00"))  # ISO (Atom)
            except Exception:
                pass
    return None


def extraer_rss(xml_text: str) -> list:
    noticias, vistos = [], set()
    try:
        soup = BeautifulSoup(xml_text, "xml")
        # Dividir el XML en items crudos para extraer imágenes con regex
        items_raw = re.findall(r'<item[^>]*>(.*?)</item>', xml_text, re.DOTALL | re.IGNORECASE)
        if not items_raw:
            items_raw = re.findall(r'<entry[^>]*>(.*?)</entry>', xml_text, re.DOTALL | re.IGNORECASE)

        for i, item in enumerate(soup.find_all(["item", "entry"])[:MAX_ITEMS]):
            titulo_tag = item.find("title")
            if not titulo_tag:
                continue
            # descartar notas viejas (los feeds de Google News traen de días atrás)
            fecha_pub = _fecha_item_rss(item)
            if fecha_pub is not None:
                try:
                    from datetime import timezone as _tz
                    ahora = datetime.now(_tz.utc)
                    fp = fecha_pub if fecha_pub.tzinfo else fecha_pub.replace(tzinfo=_tz.utc)
                    if (ahora - fp).total_seconds() > MAX_ANTIGUEDAD_HORAS * 3600:
                        continue
                except Exception:
                    pass
            titulo = titulo_tag.get_text(strip=True)
            titulo = re.sub(r"<[^>]+>", "", titulo)
            titulo = titulo.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"').replace("&#39;","'")
            publisher_original = ""
            if " - " in titulo:
                posible = titulo.rsplit(" - ", 1)[-1].strip()
                if 2 <= len(posible) <= 100:
                    publisher_original = posible
            fecha_iso = ""
            if fecha_pub is not None:
                try:
                    fecha_iso = fecha_pub.isoformat()
                except Exception:
                    fecha_iso = str(fecha_pub)
            if not titulo or len(titulo) < 15 or len(titulo) > 300 or titulo in vistos:
                continue
            vistos.add(titulo)
            url = None
            link_tag = item.find("link")
            if link_tag:
                url = link_tag.get_text(strip=True) or link_tag.get("href")
            if not url or not url.startswith("http"):
                guid = item.find("guid", isPermaLink="true")
                url = guid.get_text(strip=True) if guid else None
            # Extraer imagen del item crudo correspondiente
            imagen = ""
            if i < len(items_raw):
                imagen = _extraer_imagen_rss_item(items_raw[i])
            noticias.append({
                "titulo": titulo,
                "url": url,
                "imagen": imagen,
                "fecha_publicacion": fecha_iso,
                "publisher_original": publisher_original,
            })
    except Exception:
        pass
    return noticias[:MAX_ITEMS]

def _extraer_ole(html: str, fuente: dict) -> list:
    """
    Scraper específico para Olé.
    - Prioriza links que terminan en .html (formato estándar de notas de Olé)
    - Escala el DOM hacia los padres para encontrar el link envolvente
    - Filtra autores/tags tanto en URLs como en imágenes (evita fotos de firma)
    """
    soup = BeautifulSoup(html, "html.parser")
    BASE = "https://www.ole.com.ar"
    noticias, vistos = [], set()

    _OLE_URL_SKIP = [
        "/autor/", "/autores/", "/firma/", "/columnistas/", "/tag/", "/tags/",
        "/categoria/", "/seccion/", "/author/", "tag=", "/tema/",
        "mailto:", "javascript:", "#",
    ]
    _FIRMA_CLASES = [
        "author", "autor", "firma", "byline", "avatar", "perfil", "profile",
        "journalist", "periodista", "columnist", "writer", "reporter",
        "signature", "bio", "headshot",
    ]

    def resolve_ole(href):
        if not href:
            return None
        if any(s in href for s in _OLE_URL_SKIP):
            return None
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return BASE + href
        if href.startswith("http"):
            return href
        return None

    def _es_img_firma(tag):
        for parent in tag.parents:
            cls = " ".join(parent.get("class", [])).lower()
            pid = (parent.get("id") or "").lower()
            if any(p in cls or p in pid for p in _FIRMA_CLASES):
                return True
            if parent.name in ("article", "section", "main"):
                break
        return False

    def get_best_link(titulo_el, card):
        """Prioriza .html, escala DOM hasta 4 niveles hacia arriba."""
        candidatos = []

        # 1. Padre directo <a>
        p = titulo_el.find_parent("a")
        if p:
            u = resolve_ole(p.get("href", ""))
            if u:
                candidatos.append(u)

        # 2. <a> hijo del título
        ic = titulo_el.find("a")
        if ic:
            u = resolve_ole(ic.get("href", ""))
            if u and u not in candidatos:
                candidatos.append(u)

        # 3. Todos los <a> del card
        for a in card.find_all("a", href=True):
            u = resolve_ole(a.get("href", ""))
            if u and u not in candidatos:
                candidatos.append(u)

        # 4. Escalar DOM del card hacia arriba (4 niveles)
        parent = card.parent
        for _ in range(4):
            if not parent or parent.name in ("body", "html", "[document]"):
                break
            if parent.name == "a":
                u = resolve_ole(parent.get("href", ""))
                if u and u not in candidatos:
                    candidatos.append(u)
            for a in (parent.find_all("a", href=True, recursive=False) or []):
                u = resolve_ole(a.get("href", ""))
                if u and u not in candidatos:
                    candidatos.append(u)
            parent = parent.parent

        if not candidatos:
            return None
        # Priorizar .html
        html_links = [u for u in candidatos if u.endswith(".html")]
        return html_links[0] if html_links else candidatos[0]

    def get_mejor_imagen(card):
        """Imagen principal del card, ignorando fotos de firma/autor."""
        IMG_ATTRS = ["src", "data-src", "data-lazy-src", "data-original", "data-url"]
        candidatos = []

        for tag in card.find_all("img"):
            if _es_img_firma(tag):
                continue
            best_src = ""
            srcset = tag.get("srcset", "") or tag.get("data-srcset", "")
            if srcset:
                parts = [s.strip().split(" ") for s in srcset.split(",") if s.strip()]
                sized = []
                for p in parts:
                    url_s = p[0]
                    try:
                        w = int(p[1].rstrip("w")) if len(p) > 1 and p[1].endswith("w") else 0
                    except ValueError:
                        w = 0
                    sized.append((w, url_s))
                sized.sort(key=lambda x: x[0], reverse=True)
                for _, url_s in sized:
                    if url_s.startswith("http") and not _es_imagen_generica(url_s) and "1x1" not in url_s:
                        best_src = url_s
                        break
            if not best_src:
                for attr in IMG_ATTRS:
                    src = tag.get(attr, "")
                    if (src and src.startswith("http")
                            and not src.endswith(".gif")
                            and not _es_imagen_generica(src)
                            and "1x1" not in src
                            and "pixel" not in src.lower()):
                        best_src = src
                        break
            if best_src:
                score = 0
                cls = " ".join(tag.get("class", [])).lower()
                for good in ["featured", "hero", "portada", "principal", "cover",
                             "thumb", "thumbnail", "wp-post-image", "article-image"]:
                    if good in cls:
                        score += 300
                m = re.search(r'[-/](\d{3,4})x(\d{3,4})[-/.]', best_src)
                if m:
                    score += int(m.group(1)) + int(m.group(2))
                if tag.get("srcset") or tag.get("data-srcset"):
                    score += 100
                candidatos.append((score, best_src))

        if not candidatos:
            return ""
        candidatos.sort(key=lambda x: x[0], reverse=True)
        return candidatos[0][1]

    CARD_SELS_OLE = [
        "article", "[class*=card]", "[class*=nota]", "[class*=story]",
        "[class*=article]", "[class*=item]",
    ]
    TITLE_SELS_OLE = ["h1", "h2", "h3", "h4", "[class*=title]", "[class*=titular]", "[class*=headline]"]

    for sel in CARD_SELS_OLE:
        for card in soup.select(sel)[:MAX_ITEMS * 2]:
            if len(noticias) >= MAX_ITEMS:
                break
            titulo_el = None
            for tsel in TITLE_SELS_OLE:
                titulo_el = card.select_one(tsel)
                if titulo_el:
                    break
            if not titulo_el:
                continue
            titulo = titulo_el.get_text(strip=True)
            if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                continue
            vistos.add(titulo)
            url = get_best_link(titulo_el, card)
            img = get_mejor_imagen(card)
            noticias.append({"titulo": titulo, "url": url, "imagen": img})

    # Fallback: h2/h3 con links directos
    if len(noticias) < 8:
        for el in soup.select("h2 a[href], h3 a[href]"):
            if len(noticias) >= MAX_ITEMS:
                break
            titulo = el.get_text(strip=True)
            if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                continue
            url = resolve_ole(el.get("href", ""))
            if url:
                vistos.add(titulo)
                noticias.append({"titulo": titulo, "url": url, "imagen": ""})

    return noticias[:MAX_ITEMS]

def _extraer_as(html: str, fuente: dict) -> list:
    """Scraper específico para AS (as.com/futbol/). Filtra links de autores/tags."""
    soup = BeautifulSoup(html, "html.parser")
    BASE = "https://as.com"
    noticias, vistos = [], set()

    _AS_URL_SKIP = ["/autor/", "/autores/", "/tag/", "/tags/", "/tema/",
                    "/categoria/", "mailto:", "javascript", "/redaccion/"]

    def resolve_as(href):
        if not href:
            return None
        if any(s in href for s in _AS_URL_SKIP):
            return None
        if href.startswith("javascript") or href == "#":
            return None
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return BASE + href
        if href.startswith("http"):
            return href
        return None

    def get_nota_url_as(titulo_el, card):
        parent_a = titulo_el.find_parent("a")
        if parent_a:
            u = resolve_as(parent_a.get("href", ""))
            if u:
                return u
        inner_a = titulo_el.find("a")
        if inner_a:
            u = resolve_as(inner_a.get("href", ""))
            if u:
                return u
        for a in card.find_all("a", href=True):
            u = resolve_as(a.get("href", ""))
            if u:
                return u
        return None

    CARD_SELS_AS = [
        "article", "[class*=card]", "[class*=article]",
        "[class*=noticia]", "[class*=story]", "[class*=item]",
        "li[class*=list]",
    ]
    TITLE_SELS_AS = ["h1", "h2", "h3", "[class*=title]", "[class*=headline]", "[class*=titular]"]

    for sel in CARD_SELS_AS:
        for card in soup.select(sel)[:MAX_ITEMS * 2]:
            if len(noticias) >= MAX_ITEMS:
                break
            titulo_el = None
            for tsel in TITLE_SELS_AS:
                titulo_el = card.select_one(tsel)
                if titulo_el:
                    break
            if not titulo_el:
                continue
            titulo = titulo_el.get_text(strip=True)
            if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                continue
            vistos.add(titulo)
            url = get_nota_url_as(titulo_el, card)
            img = ""
            for tag in card.find_all("img"):
                src = (tag.get("src") or tag.get("data-src") or
                       tag.get("data-lazy-src") or tag.get("data-original") or "")
                if src and src.startswith("http") and not _es_imagen_generica(src):
                    img = src
                    break
            noticias.append({"titulo": titulo, "url": url, "imagen": img})

    if len(noticias) < 8:
        for el in soup.select("h2 a[href], h3 a[href]"):
            if len(noticias) >= MAX_ITEMS:
                break
            titulo = el.get_text(strip=True)
            if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                continue
            vistos.add(titulo)
            url = resolve_as(el.get("href", ""))
            if url:
                noticias.append({"titulo": titulo, "url": url, "imagen": ""})

    return noticias[:MAX_ITEMS]


def _extraer_espn(html: str, fuente: dict) -> list:
    """Scraper dedicado para ESPN AR (SPA React). El HTML estático trae JSON-LD
    con las URLs reales; las notas siguen el patrón /_/id/NNNNNN/."""
    noticias, seen = [], set()
    soup = BeautifulSoup(html, "html.parser")
    BASE = "https://www.espn.com.ar"
    ESPN_SKIP = ["/autor/", "/author/", "/tag/", "/tags/", "/equipo/", "/liga/",
                 "/atletismo/", "javascript:", "mailto:", "#", "/video/"]

    def resolve_espn(href):
        if not href:
            return None
        if any(s in href for s in ESPN_SKIP):
            return None
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return BASE + href
        if href.startswith("http"):
            return href
        return None

    def es_url_nota(url):
        if not url:
            return False
        return "/_/id/" in url or "/nota/" in url or "/historia/" in url or "/story/" in url

    urls_json = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")

            def _walk(obj):
                if isinstance(obj, dict):
                    if obj.get("@type") in ("NewsArticle", "Article", "WebPage"):
                        u = obj.get("url") or obj.get("mainEntityOfPage", {}).get("@id", "")
                        if u and es_url_nota(u) and u not in urls_json:
                            urls_json.append(u)
                    if obj.get("@type") == "ItemList":
                        for item in obj.get("itemListElement", []):
                            u = item.get("url") or item.get("item", {}).get("url", "")
                            if u and es_url_nota(u) and u not in urls_json:
                                urls_json.append(u)
                    for v in obj.values():
                        _walk(v)
                elif isinstance(obj, list):
                    for v in obj:
                        _walk(v)
            _walk(data)
        except Exception:
            pass

    urls_html = []
    for a in soup.find_all("a", href=True):
        url = resolve_espn(a.get("href", ""))
        if url and es_url_nota(url) and url not in urls_html:
            urls_html.append(url)

    todas_urls = list(dict.fromkeys(urls_json + urls_html))

    url_to_titulo = {}
    TITLE_SELS_ESPN = ["h1", "h2", "h3", "h4",
                       "[class*=title]", "[class*=Title]",
                       "[class*=headline]", "[class*=Headline]",
                       "[class*=contentItem__title]"]
    for a in soup.find_all("a", href=True):
        url = resolve_espn(a.get("href", ""))
        if not url or not es_url_nota(url):
            continue
        titulo = None
        for sel in TITLE_SELS_ESPN:
            t_el = a.select_one(sel)
            if t_el:
                titulo = t_el.get_text(strip=True)
                break
        if not titulo:
            titulo = a.get_text(strip=True)
        titulo = " ".join(titulo.split())
        if 20 <= len(titulo) <= 300 and url not in url_to_titulo:
            url_to_titulo[url] = titulo

    for url in todas_urls:
        if len(noticias) >= MAX_ITEMS:
            break
        titulo = url_to_titulo.get(url)
        if not titulo:
            slug = url.rstrip("/").split("/")[-1]
            slug = re.sub(r"^\d+-", "", slug)
            titulo = slug.replace("-", " ").title()
            if len(titulo) < 15:
                continue
        if titulo in seen:
            continue
        seen.add(titulo)
        noticias.append({"titulo": titulo, "url": url, "imagen": ""})

    return noticias[:MAX_ITEMS]


def extraer_generico(html: str, fuente: dict) -> list:
    # Scrapers específicos
    if fuente.get("es_ole"):
        return _extraer_ole(html, fuente)
    if fuente.get("es_as"):
        return _extraer_as(html, fuente)
    if fuente.get("es_espn"):
        return _extraer_espn(html, fuente)

    if fuente.get("es_rss"):
        return extraer_rss(html)

    # Doble Amarilla es WordPress — usar su feed RSS que incluye imágenes
    if fuente.get("es_wp"):
        feed_url = fuente["url"].rstrip("/") + "/feed/"
        try:
            resp = requests.get(feed_url, headers=_FETCH_HEADERS, timeout=15)
            if resp.status_code == 200 and "<rss" in resp.text[:500]:
                return extraer_rss(resp.text)
        except Exception:
            pass  # Fallback al scraping normal si el feed falla

    soup = BeautifulSoup(html, "html.parser")
    base_url = re.match(r"https?://[^/]+", fuente["url"])
    base = base_url.group(0) if base_url else ""
    noticias, vistos = [], set()

    CARD_SELS = ["article", "[class*=card]", "[class*=story]", "[class*=nota]", "[class*=item]", "[class*=news]"]
    TITLE_SELS = ["h1","h2","h3","h4","[class*=title]","[class*=headline]","[class*=titular]"]

    def resolve_url(href):
        if not href or href.startswith("javascript") or href == "#":
            return None
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return base + href
        if href.startswith("http"):
            return href
        return None

    def get_titulo(el):
        for sel in TITLE_SELS:
            t = el.select_one(sel)
            if t:
                return t.get_text(strip=True)
        return None

    def get_url(el, titulo_el):
        link = titulo_el.find_parent("a") or titulo_el.find("a") or el.find("a")
        if link:
            return resolve_url(link.get("href", ""))
        return None

    # Patrones de clases/padres que indican imagen de firma/autor (NO foto de nota)
    AUTOR_PATTERNS = [
        "author", "autor", "firma", "byline", "avatar", "perfil", "profile",
        "journalist", "periodista", "columnist", "writer", "reporter",
        "signature", "bio", "headshot",
    ]

    def _es_img_autor(tag):
        """Retorna True si la imagen está dentro de un contenedor de firma/autor."""
        for parent in tag.parents:
            cls = " ".join(parent.get("class", [])).lower()
            pid = (parent.get("id") or "").lower()
            combined = cls + " " + pid
            if any(p in combined for p in AUTOR_PATTERNS):
                return True
            # No escalar más allá del card
            if parent == tag.parent.parent.parent:
                break
        return False

    def _img_score(tag, src):
        """Puntúa una imagen: más grande y más prominente = mayor score."""
        score = 0
        # Dimensiones explícitas
        try:
            w = int(tag.get("width") or tag.get("data-width") or 0)
            h = int(tag.get("height") or tag.get("data-height") or 0)
            score += w + h
        except (ValueError, TypeError):
            pass
        # Clases que sugieren imagen principal (incluyendo WordPress)
        cls = " ".join(tag.get("class", [])).lower()
        for good in [
            "featured", "hero", "portada", "principal", "cover",
            "thumb", "thumbnail", "featured-image", "post-image",
            "article-image", "nota-img", "card-img",
            # WordPress específico
            "wp-post-image", "attachment-", "size-large", "size-full",
            "size-medium_large", "wp-block-image", "entry-thumb",
        ]:
            if good in cls:
                score += 500
        # Clases de autor = penalizar mucho
        for bad in AUTOR_PATTERNS:
            if bad in cls:
                score -= 9999
        # Si es autor por contexto = penalizar
        if _es_img_autor(tag):
            score -= 9999
        # srcset presente = suele ser imagen de contenido
        if tag.get("srcset") or tag.get("data-srcset"):
            score += 200
        # Dimensiones implícitas de URL (Olé usa /fit-in/NxN/, WP usa -NNNxNNN.)
        m = re.search(r'[-/](\d{3,4})x(\d{3,4})[-/.]', src)
        if m:
            score += int(m.group(1)) + int(m.group(2))
        # alt descriptivo (no vacío, no "logo") también suma
        alt = (tag.get("alt") or "").lower()
        if alt and len(alt) > 5 and "logo" not in alt:
            score += 50
        return score

    def get_imagen(el):
        """Extrae la imagen principal de una card, ignorando fotos de autores."""
        IMG_ATTRS = ["src", "data-src", "data-lazy-src", "data-original", "data-url", "data-image"]
        candidatos = []  # (score, src)

        for tag in el.find_all("img"):
            best_src = ""
            # srcset primero — generalmente tiene la versión más grande
            srcset = tag.get("srcset", "") or tag.get("data-srcset", "")
            if srcset:
                parts = [s.strip().split(" ") for s in srcset.split(",") if s.strip()]
                # Ordenar por ancho declarado (ej "800w") descendente
                sized = []
                for p in parts:
                    url = p[0]
                    try:
                        w = int(p[1].rstrip("w")) if len(p) > 1 and p[1].endswith("w") else 0
                    except ValueError:
                        w = 0
                    sized.append((w, url))
                sized.sort(key=lambda x: x[0], reverse=True)
                for _, url in sized:
                    if url.startswith("http") and not _es_imagen_generica(url) and "1x1" not in url:
                        best_src = url
                        break

            if not best_src:
                for attr in IMG_ATTRS:
                    src = tag.get(attr, "")
                    if (src and src.startswith("http")
                            and not src.endswith(".gif")
                            and not _es_imagen_generica(src)
                            and "1x1" not in src
                            and "pixel" not in src.lower()):
                        best_src = src
                        break

            if best_src:
                score = _img_score(tag, best_src)
                candidatos.append((score, best_src))

        # background-image en estilos
        for tag in el.find_all(style=True):
            m = re.search(r'background(?:-image)?:\s*url\(["\']?(https?://[^"\')\s]+)["\']?\)', tag["style"])
            if m:
                src = m.group(1)
                if not _es_imagen_generica(src) and "1x1" not in src:
                    cls = " ".join(tag.get("class", [])).lower()
                    score = 100
                    for bad in AUTOR_PATTERNS:
                        if bad in cls:
                            score = -9999
                    candidatos.append((score, src))

        if not candidatos:
            return ""
        # Tomar la de mayor score, descartar si score muy negativo (= autor)
        candidatos.sort(key=lambda x: x[0], reverse=True)
        best_score, best_src = candidatos[0]
        return best_src if best_score > -100 else ""

    # Intentar cards
    for sel in CARD_SELS:
        for card in soup.select(sel)[:MAX_ITEMS * 2]:
            if len(noticias) >= MAX_ITEMS:
                break
            titulo_el = None
            for tsel in TITLE_SELS:
                titulo_el = card.select_one(tsel)
                if titulo_el:
                    break
            if not titulo_el:
                continue
            titulo = titulo_el.get_text(strip=True)
            if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                continue
            vistos.add(titulo)
            url = get_url(card, titulo_el)
            imagen = get_imagen(card)
            noticias.append({"titulo": titulo, "url": url, "imagen": imagen})

    # Fallback: sólo headings
    if len(noticias) < 8:
        for sel in ["h2","h3"]:
            for el in soup.select(sel)[:MAX_ITEMS * 2]:
                if len(noticias) >= MAX_ITEMS:
                    break
                titulo = el.get_text(strip=True)
                if len(titulo) < 20 or len(titulo) > 300 or titulo in vistos:
                    continue
                vistos.add(titulo)
                link = el.find_parent("a") or el.find("a")
                url = resolve_url(link.get("href", "")) if link else None
                noticias.append({"titulo": titulo, "url": url})

    return noticias[:MAX_ITEMS]

# ─── FALLBACK UNIVERSAL: GOOGLE NEWS RSS ─────────────────────────────────────
# Si el scraping directo de una fuente falla o trae 0 notas, se le pide a
# Google News el feed de ese dominio (site:medio.com). Google ya indexa todos
# los medios, así que esto autocura fuentes rotas (SPAs, bloqueos, rediseños).

# Edición de Google News según el idioma de cada medio: pedirle un sitio
# italiano a la edición argentina puede devolver 0 resultados.
GNEWS_LOC = {
    # italiano
    "dimarzio": ("it", "IT", "IT:it"), "calciomer": ("it", "IT", "IT:it"),
    "gazzetta": ("it", "IT", "IT:it"), "corriere": ("it", "IT", "IT:it"),
    # inglés
    "guardian": ("en-US", "US", "US:en"), "skysports": ("en-US", "US", "US:en"),
    "bbc": ("en-US", "US", "US:en"), "cbssport": ("en-US", "US", "US:en"),
    "goal": ("en-US", "US", "US:en"), "espnint": ("en-US", "US", "US:en"),
    "sportnews": ("en-US", "US", "US:en"), "fifa": ("en-US", "US", "US:en"),
    # francés
    "lequipe": ("fr", "FR", "FR:fr"), "footmercato": ("fr", "FR", "FR:fr"),
    # portugués
    "globo": ("pt-BR", "BR", "BR:pt-419"),
    "record": ("pt-PT", "PT", "PT:pt-150"),
    # español de España
    "marca": ("es", "ES", "ES:es"), "as": ("es", "ES", "ES:es"),
    "sport": ("es", "ES", "ES:es"), "mundodep": ("es", "ES", "ES:es"),
    "geglobo": ("pt-BR", "BR", "BR:pt-419"),
    "latercera": ("es-419", "CL", "CL:es-419"), "abola": ("pt-PT", "PT", "PT:pt-150"),
    "bild": ("de", "DE", "DE:de"), "skyit": ("it", "IT", "IT:it"),
}


def _gnews_url(dominio: str, fuente_id: str = "") -> str:
    hl, gl, ceid = GNEWS_LOC.get(fuente_id, ("es-419", "AR", "AR:es-419"))
    return (f"https://news.google.com/rss/search?q=site:{dominio}"
            f"&hl={hl}&gl={gl}&ceid={ceid}")


def _limpiar_titulo_gnews(titulo: str) -> str:
    """Google News agrega ' - Nombre del Medio' al final de cada título."""
    if " - " in titulo:
        base = titulo.rsplit(" - ", 1)[0].strip()
        if len(base) >= 15:
            return base
    return titulo


def _dominio_de(fuente: dict) -> str:
    if fuente.get("gnews"):
        return fuente["gnews"]
    url = fuente.get("url", "")
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""


def _fallback_gnews(fuente: dict, motivo_original: str) -> dict:
    if fuente.get("sin_fallback"):
        return {"id": fuente["id"], "noticias": [], "error": motivo_original}
    dominio = _dominio_de(fuente)
    if not dominio or "news.google.com" in fuente.get("url", ""):
        return {"id": fuente["id"], "noticias": [], "error": motivo_original}
    try:
        resp = requests.get(_gnews_url(dominio, fuente.get("id", "")), headers=HEADERS, timeout=15)
        resp.raise_for_status()
        noticias = extraer_rss(resp.text)
        for n in noticias:
            n["titulo"] = _limpiar_titulo_gnews(n["titulo"])
        if noticias:
            return {"id": fuente["id"], "noticias": noticias[:MAX_ITEMS],
                    "error": None, "via": "gnews"}
    except Exception:
        pass
    return {"id": fuente["id"], "noticias": [], "error": motivo_original}


def fetch_fuente(fuente: dict) -> dict:
    try:
        resp = requests.get(fuente["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()

        # Fuentes RSS (feeds de Google News y similares): parser dedicado
        if fuente.get("es_rss"):
            resp.encoding = resp.encoding or "utf-8"
            noticias = extraer_rss(resp.text)
            for n in noticias:
                n["titulo"] = _limpiar_titulo_gnews(n["titulo"])
            noticias = noticias[:MAX_ITEMS]
            if noticias:
                return {"id": fuente["id"], "noticias": noticias, "error": None}
            # si el feed vino vacío y permite fallback, intentarlo
            if not fuente.get("sin_fallback"):
                return _fallback_gnews(fuente, "feed rss vacío")
            return {"id": fuente["id"], "noticias": [], "error": "feed rss vacío"}

        # Detectar encoding real desde el header o el HTML antes de usar resp.text
        # requests a veces asume ISO-8859-1 para text/html sin charset declarado
        content_type = resp.headers.get("content-type", "").lower()
        if "charset=" in content_type:
            # Respetar el charset del servidor
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        else:
            # Intentar detectar desde el meta charset del HTML
            raw = resp.content
            sniff = raw[:4096].decode("ascii", errors="ignore").lower()
            if 'charset="utf-8"' in sniff or "charset=utf-8" in sniff:
                encoding = "utf-8"
            elif 'charset="iso-8859-1"' in sniff or 'charset=iso-8859-1' in sniff:
                encoding = "iso-8859-1"
            elif 'charset="windows-1252"' in sniff or 'charset=windows-1252' in sniff:
                encoding = "windows-1252"
            else:
                # Si apparent_encoding detecta latin, usarlo; si no, utf-8
                detected = (resp.apparent_encoding or "utf-8").lower()
                # Confiar en la detección (incluye windows-1252/latin para páginas
                # ES/PT/IT/FR sin charset declarado); sólo caer a utf-8 si es ascii/vacío.
                encoding = "utf-8" if detected in ("ascii", "") else detected
        resp.encoding = encoding
        noticias = extraer_generico(resp.text, fuente)
        if noticias:
            # fuentes flacas marcadas: complementar el directo con Google News (dedup)
            if fuente.get("gnews_extra") and len(noticias) < 25:
                extra = _fallback_gnews(fuente, "")
                vistos = {frozenset(normalizar_titulo(n["titulo"])) for n in noticias}
                for n in extra.get("noticias", []):
                    k = frozenset(normalizar_titulo(n["titulo"]))
                    if k and k not in vistos:
                        vistos.add(k)
                        noticias.append(n)
                noticias = noticias[:MAX_ITEMS]
            return {"id": fuente["id"], "noticias": noticias, "error": None}
        return _fallback_gnews(fuente, "scraping directo: 0 notas")
    except Exception as e:
        return _fallback_gnews(fuente, str(e))

# ─── IA — CLAUDE ──────────────────────────────────────────────────────────────
MODELO_ANALISIS = "claude-sonnet-5"       # para notas y análisis profundos
MODELO_ECONOMICO = "claude-haiku-4-5-20251001"  # para partes/resúmenes: mucho más barato


def call_claude(prompt: str, api_key: str, max_tokens: int = 2000,
                modelo: str = None) -> str:
    if not api_key:
        raise RuntimeError("Falta la API key de Anthropic.")
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=modelo or MODELO_ANALISIS,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        raise RuntimeError(f"Error al llamar a Claude: {e}") from e
    # Concatenar todos los bloques de texto (no asumir que content[0] es texto)
    partes = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    return "\n".join(partes).strip()

PERLITA_KEYWORDS = [
    "insolito", "insólito", "viral", "furor", "locura", "increible", "increíble",
    "inedito", "inédito", "record", "récord", "historico", "histórico", "blooper",
    "papelon", "papelón", "escandalo", "escándalo", "polemica", "polémica",
    "sorpresa", "sorprend", "curios", "emotivo", "conmovedor", "gesto de",
    "no lo vio nadie", "nunca visto", "por primera vez", "el más", "la más",
    "wtf", "video:", "el video", "la foto", "se volvio", "se volvió",
    "estallo", "estalló", "explotaron", "memes", "reaccion", "reacción",
]


def candidatas_perlitas(resultados: dict, max_items: int = 30) -> list:
    """Barre todos los titulares buscando señales de perlita (viral, insólito,
    récord, blooper...). Devuelve [(nombre_fuente, titulo), ...] dedupeado."""
    out, vistos = [], set()
    for f in TODAS_FUENTES:
        for n in resultados.get(f["id"], []):
            t = n.get("titulo", "")
            tl = t.lower()
            if not any(k in tl for k in PERLITA_KEYWORDS):
                continue
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            out.append((f["nombre"], t[:150]))
            if len(out) >= max_items:
                return out
    return out


def prompt_analisis_general(resultados: dict) -> str:
    tendencias = calcular_tendencias(resultados)[:30]
    perlitas = candidatas_perlitas(resultados)
    bloque_perlitas = "\n".join(f"  • [{f}] {t}" for f, t in perlitas) or "  (ninguna detectada en esta pasada)"
    lineas = "\n".join(
        f"{i+1}. {c['titulo'][:130]} — {c['cant_medios']} medios "
        f"({c.get('nac', 0)} nac / {c.get('intl', 0)} int) · Olé: {'sí' if c.get('tiene_ole') else 'NO'}"
        for i, c in enumerate(tendencias)
    )
    return f"""Sos editor jefe de un portal deportivo argentino. Abajo están los 30 temas
que más medios están cubriendo AHORA (de {len(TODAS_FUENTES)} medios monitoreados),
ya agrupados y ordenados por volumen.{bloque_criterios()}

Escribí un RESUMEN EJECUTIVO en español rioplatense, directo:

LECTURA GENERAL — 3 líneas: qué domina la conversación y qué tono tiene el día.

LOS 30 TEMAS, agrupados por eje (Selección / mercado de pases / torneo local /
fútbol internacional / otros). Por cada tema, UNA sola línea: qué pasó y por qué
importa para el hincha argentino. No repitas el título textual: interpretalo.
Marcá con ⚠️ los temas donde Olé no tiene cobertura.

DATO SALIENTE — 1 línea: la asimetría o el patrón más llamativo del panorama.

PERLITAS — 3 a 5 joyitas con potencial de tráfico: lo viral, lo insólito, la
sorpresa, el gesto, el récord raro. Elegilas de la canasta de candidatas (y del
top 30 si alguna califica). Por cada una: por qué puede rendir en una línea +
un título con gancho. Si una candidata es puro clickbait sin sustancia, salteala.

TEMAS:
{lineas}

CANDIDATAS A PERLITA (detectadas por señales de viralidad/rareza):
{bloque_perlitas}"""

def _temas_por_origen(resultados: dict, origen: str, top: int = 25) -> list:
    tendencias = calcular_tendencias(resultados)
    out = []
    for c in tendencias:
        if origen == "nac" and c.get("nac", 0) >= 1:
            out.append(c)
        elif origen == "int" and c.get("intl", 0) >= 1:
            out.append(c)
    return out[:top]


def prompt_parte_nacional(resultados: dict) -> str:
    """Análisis general enfocado en el fútbol argentino (mismo nivel que el
    Análisis General, pero solo temas que cubren los medios nacionales)."""
    tendencias = _temas_por_origen(resultados, "nac", 30)
    perlitas = candidatas_perlitas(resultados)
    bloque_perlitas = "\n".join(f"  • [{f}] {t}" for f, t in perlitas) or "  (ninguna detectada en esta pasada)"
    lineas = "\n".join(
        f"{i+1}. {c['titulo'][:130]} — {c['cant_medios']} medios "
        f"({c.get('nac', 0)} nac / {c.get('intl', 0)} int) · Olé: {'sí' if c.get('tiene_ole') else 'NO'}"
        for i, c in enumerate(tendencias)
    )
    return f"""Sos editor jefe de un diario deportivo argentino. Abajo están los temas
del FÚTBOL ARGENTINO que más medios están cubriendo AHORA, ya agrupados y
ordenados por volumen.{bloque_criterios()}

Escribí un RESUMEN EJECUTIVO en español rioplatense, directo:

LECTURA GENERAL — 3 líneas: qué domina la conversación del fútbol argentino y qué tono tiene el día.

LOS TEMAS, agrupados por eje (River / Boca / otros clubes / Selección / mercado local / otros).
Por cada tema, UNA sola línea: qué pasó y por qué importa para el hincha argentino.
No repitas el título textual: interpretalo. Marcá con ⚠️ los temas donde Olé no tiene cobertura.

DATO SALIENTE — 1 línea: la asimetría o el patrón más llamativo del panorama local.

PERLITAS — 3 a 5 joyitas con potencial de tráfico: lo viral, lo insólito, la
sorpresa, el gesto, el récord raro. Elegilas de la canasta de candidatas (y del
top si alguna califica). Por cada una: por qué puede rendir en una línea +
un título con gancho. Si una candidata es puro clickbait sin sustancia, salteala.

TEMAS:
{lineas}

CANDIDATAS A PERLITA (detectadas por señales de viralidad/rareza):
{bloque_perlitas}"""


def prompt_parte_internacional(resultados: dict) -> str:
    """Análisis general del fútbol internacional (mismo nivel que el Análisis
    General) más una sección enfocada en impacto argentino."""
    tendencias = _temas_por_origen(resultados, "int", 30)
    relevantes = notas_exterior_relevantes(resultados, 15)
    lineas = "\n".join(
        f"{i+1}. {c['titulo'][:130]} — {c['cant_medios']} medios"
        for i, c in enumerate(tendencias)
    )
    bloque_ar = "\n".join(f"  • [{r['fuente']['nombre']}] {r['titulo'][:120]}"
                           + (f" ({' · '.join(r['entidades'][:3])})" if r['entidades'] else "")
                           for r in relevantes) or "  (nada con gancho argentino ahora)"
    return f"""Sos editor de la sección internacional de un diario deportivo argentino.
Abajo están los temas del FÚTBOL MUNDIAL que más medios están cubriendo AHORA,
ya agrupados y ordenados por volumen.{bloque_criterios()}

Escribí un RESUMEN EJECUTIVO en español rioplatense, directo:

PANORAMA INTERNACIONAL — 3 líneas: qué domina el fútbol mundial hoy (ligas,
Champions, mercado europeo, figuras) y qué tono tiene.

LOS TEMAS DEL MUNDO, agrupados por eje (España / Italia / Inglaterra / mercado
europeo / Champions y copas / Brasil y Sudamérica / otros). Por cada tema, UNA
sola línea: qué pasó y por qué importa. No repitas el título: interpretalo.

DATO SALIENTE — 1 línea: el patrón o la historia más llamativa del fútbol mundial hoy.

🧉 IMPACTO ARGENTINO — la sección clave: de todo lo internacional, qué le toca
directamente a un hincha argentino (jugadores argentinos en el exterior, rivales
de la Selección, nombres que suenan para el fútbol local). Por cada uno, una
línea con el ángulo para trabajarlo desde acá.

TEMAS INTERNACIONALES:
{lineas}

NOTAS DEL EXTERIOR CON GANCHO ARGENTINO:
{bloque_ar}"""


def _fuentes_int_reales():
    return [f for f in TODAS_FUENTES
            if f["id"] not in FUENTES_NAC_IDS and f["id"] not in FUENTES_ESP_IDS]


def exportar_recorte_argentina(resultados: dict) -> str:
    """Recorte de titulares internacionales que mencionan a la Argentina.
    Dedup POR MEDIO (no global): si tres medios titulan la misma historia,
    entran las tres versiones — clave para el sentimiento por país."""
    from datetime import datetime
    lineas_notas = []
    for f in _fuentes_int_reales():
        vistos = set()
        for n in resultados.get(f["id"], []):
            t = n.get("titulo", "")
            if not relevancia_argentina(t):
                continue
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            lineas_notas.append(f"[{f['nombre']}] {t}")
    hoy = datetime.now().strftime("%d/%m/%Y")
    return "\n".join(
        ["TITULARES DE MEDIOS INTERNACIONALES QUE MENCIONAN A ARGENTINA",
         f"Recorte del panorama (~últimas 24-48h) · {hoy} · {len(lineas_notas)} titulares "
         "(cada medio conserva su propia versión de cada historia)", ""]
        + lineas_notas)


def exportar_panorama_internacional(resultados: dict) -> str:
    """TODOS los titulares del panorama internacional, sin filtro ni tope,
    agrupados por medio. Para que la IA del editor haga el recorte con
    contexto completo (nada queda afuera)."""
    from datetime import datetime
    partes, total = [], 0
    for f in _fuentes_int_reales():
        notas = resultados.get(f["id"], [])
        if not notas:
            continue
        partes.append(f"\n=== {f['nombre']} ({len(notas)} titulares) ===")
        vistos = set()
        for n in notas:
            t = n.get("titulo", "")
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            partes.append(t)
            total += 1
    hoy = datetime.now().strftime("%d/%m/%Y")
    encabezado = ["PANORAMA INTERNACIONAL COMPLETO — TODOS LOS TITULARES",
                  f"~últimas 24-48h · {hoy} · {total} titulares de "
                  f"{len([f for f in _fuentes_int_reales() if resultados.get(f['id'])])} medios", ""]
    return "\n".join(encabezado + partes)


TRENDS_DEPORTE_KW = [
    "futbol", "river", "boca", "racing", "independiente", "san lorenzo",
    "seleccion", "mundial", "gol", "copa", "liga", "partido", "dt", "tecnico",
    "messi", "scaloni", "afa", "libertadores", "champions", "penal", "vs",
    "colapinto", "f1", "formula", "tenis", "basquet", "nba", "rugby", "pumas",
    "boxeo", "ufc", "hincha", "estadio", "arquero", "delantero", "refuerzo",
]


def fetch_trends_ar(max_items: int = 20) -> list:
    """Tendencias de búsqueda de Google en Argentina (RSS oficial de Trends).
    Marca cuáles parecen deportivas. Devuelve [{busqueda, trafico, nota, url,
    deportivo}] o lista vacía si Google no responde."""
    urls = [
        "https://trends.google.com/trending/rss?geo=AR",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AR",
    ]
    xml = ""
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=12)
            if r.status_code == 200 and "<item>" in r.text:
                xml = r.text
                break
        except Exception:
            continue
    if not xml:
        return []
    out = []
    for m in re.finditer(r"<item>([\s\S]*?)</item>", xml):
        blk = m.group(1)
        tm = re.search(r"<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</title>", blk)
        if not tm:
            continue
        busqueda = tm.group(1).strip()
        tr = re.search(r"<ht:approx_traffic>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</ht:approx_traffic>", blk)
        nt = re.search(r"<ht:news_item_title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</ht:news_item_title>", blk)
        nu = re.search(r"<ht:news_item_url>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?</ht:news_item_url>", blk)
        nota = re.sub(r"<[^>]+>", "", nt.group(1)).strip() if nt else ""
        texto = _norm_texto(f"{busqueda} {nota}")
        deportivo = bool(detectar_entidades(f"{busqueda} {nota}")) or \
                    any(k in texto for k in TRENDS_DEPORTE_KW)
        out.append({"busqueda": busqueda,
                    "trafico": tr.group(1).strip() if tr else "",
                    "nota": nota, "url": nu.group(1).strip() if nu else "",
                    "deportivo": deportivo})
        if len(out) >= max_items:
            break
    out.sort(key=lambda x: not x["deportivo"])  # deportivas primero
    return out


def exportar_titulos_ole(resultados: dict) -> str:
    """Solo los títulos de Olé del panorama del día, en texto limpio —
    para auditar la calidad editorial propia."""
    from datetime import datetime
    notas = resultados.get("ole", [])
    vistos, lineas = set(), []
    for n in notas:
        t = n.get("titulo", "")
        k = frozenset(normalizar_titulo(t))
        if not k or k in vistos:
            continue
        vistos.add(k)
        lineas.append(t)
    hoy = datetime.now().strftime("%d/%m/%Y")
    return "\n".join([f"TÍTULOS DE OLÉ — {hoy} — {len(lineas)} títulos", ""] + lineas)


def exportar_panorama_total(resultados: dict) -> str:
    """TODOS los titulares scrapeados (nacionales + primicias + internacionales),
    con Olé primero, agrupados por medio, sin tope. Para adjuntar a cualquier IA
    y consultar sobre el panorama completo del día."""
    from datetime import datetime
    ole = [f for f in FUENTES_NAC if f["id"] == "ole"]
    resto_nac = [f for f in FUENTES_NAC if f["id"] != "ole"]
    orden = ole + resto_nac + FUENTES_ESP + _fuentes_int_reales()
    partes, total, n_medios = [], 0, 0
    seccion_actual = None
    secciones = {id(ole[0]) if ole else None: None}
    def _grupo(f):
        if f["id"] == "ole": return "═══ OLÉ ═══"
        if f["id"] in FUENTES_NAC_IDS: return "═══ MEDIOS NACIONALES ═══"
        if f["id"] in FUENTES_ESP_IDS: return "═══ PRIMICIAS E INSTITUCIONES ═══"
        return "═══ MEDIOS INTERNACIONALES ═══"
    for f in orden:
        notas = resultados.get(f["id"], [])
        if not notas:
            continue
        g = _grupo(f)
        if g != seccion_actual:
            partes.append(f"\n\n{g}")
            seccion_actual = g
        partes.append(f"\n=== {f['nombre']} ({len(notas)} titulares) ===")
        n_medios += 1
        vistos = set()
        for n in notas:
            t = n.get("titulo", "")
            k = frozenset(normalizar_titulo(t))
            if not k or k in vistos:
                continue
            vistos.add(k)
            partes.append(t)
            total += 1
    hoy = datetime.now().strftime("%d/%m/%Y")
    encabezado = ["PANORAMA TOTAL — TODOS LOS TITULARES SCRAPEADOS (NACIONALES + INTERNACIONALES)",
                  f"~últimas 24-48h · {hoy} · {total} titulares de {n_medios} medios · Olé primero", ""]
    return "\n".join(encabezado + partes)


# Clasificación editorial liviana (función · estructura · calidad) ─────────────
FUNCIONES_VALIDAS = ["NOT","SER","VIV","DEC","ANA","OPI","RUM","EXP","HUM","VIR","COM","INS"]
FUNCIONES_DESC = {"NOT":"noticia confirmada","SER":"servicio","VIV":"en vivo",
    "DEC":"declaración","ANA":"análisis","OPI":"opinión","RUM":"rumor/mercado",
    "EXP":"explicador","HUM":"historia humana","VIR":"viral/color","COM":"comercial","INS":"institucional"}


def prompt_termometro_editorial(titulos: list) -> str:
    """Una sola llamada: clasifica el mix editorial del día y su calidad.
    titulos: lista de strings (los títulos de Olé del día)."""
    listado = "\n".join(f"{i+1}. {t[:160]}" for i, t in enumerate(titulos[:130]))
    return f"""Sos analista editorial de un diario deportivo argentino. Abajo están los
{len(titulos[:130])} titulares que Olé publicó hoy. Clasificá el PANORAMA del día
(no título por título: el agregado) y escribí un termómetro breve en español rioplatense.

FUNCIONES (para el mix): NOT=noticia confirmada, SER=servicio, VIV=en vivo,
DEC=declaración, ANA=análisis, OPI=opinión, RUM=rumor/mercado, EXP=explicador,
HUM=historia humana, VIR=viral/color, COM=comercial, INS=institucional.

Escribí:

MIX DEL DÍA — el reparto aproximado por función (ej: "45% NOT, 20% RUM, 15% VIR...").
Qué tipo de periodismo dominó hoy.

CALIDAD GENERAL — una nota del 0 al 10 al conjunto de titulares, considerando
información, atribución de fuentes, proporcionalidad (¿exageran?) y pertinencia.
Una línea justificando.

SEÑALES DE ALERTA — si hay títulos que parecen clickbait, rumores sin fuente
clara, o exageraciones, citá 2-3 como ejemplo (textual). Si el día fue limpio, decilo.

RECOMENDACIÓN — 1 línea: qué debería cuidar la redacción mañana según lo que viste.

TITULARES DE HOY:
{listado}"""


def clasificar_titulo_liviano(titulo: str) -> dict:
    """Clasificación SIN IA (por palabras) de función y estructura — para features
    del modelo, gratis. No reemplaza el análisis fino de la IA, pero da señal útil
    y consistente a costo cero."""
    t = titulo or ""
    tn = _norm_texto(t)
    # función principal (heurística por señales léxicas)
    func = "NOT"
    if any(k in tn for k in ["en vivo","minuto a minuto","seguilo","en directo"]):
        func = "VIV"
    elif '"' in t or "\u201c" in t or any(k in tn for k in ["aseguro","declaro","hablo","palabras de","apunto contra"]):
        func = "DEC"
    elif any(k in tn for k in PASES_KEYWORDS):
        func = "RUM"
    elif any(k in tn for k in ["por que","las claves","el analisis","que significa"]):
        func = "ANA"
    elif any(k in tn for k in ["como ver","horario","donde ver","a que hora","formaciones","posibles"]):
        func = "SER"
    elif any(k in tn for k in FILTROS_TEMATICOS.get("viral",{}).get("keywords",[])):
        func = "VIR"
    # estructuras visibles
    estructuras = []
    if "?" in t or "¿" in t: estructuras.append("PREG")
    if '"' in t or "\u201c" in t: estructuras.append("CITA")
    if ":" in t: estructuras.append("DECL")
    if re.match(r"^\d+", t.strip()) or re.search(r"\b\d+\s+(cosas|claves|razones|motivos)\b", tn): estructuras.append("LIST")
    if any(k in tn for k in ["esto","asi","lo que","el motivo","la razon"]) and "?" not in t: estructuras.append("TEAS")
    # calidad aproximada (heurística conservadora 0-10)
    q = 7
    if "?" in t: q -= 1
    if any(k in tn for k in ["escandalo","brutal","increible","tremendo","fuerte"]): q -= 1
    if any(k in tn for k in PASES_KEYWORDS) and not any(k in tn for k in ["oficial","confirmado","firmo"]): q -= 1
    if len(t) < 30: q -= 1
    q = max(2, min(9, q))
    banda = "SOLIDO" if q>=8 else ("CORRECTO" if q>=6 else ("DEBIL" if q>=4 else "CLICKBAIT"))
    return {"funcion": func, "estructuras": estructuras, "calidad": q, "banda": banda}


def prompt_sentimiento_argentina(resultados: dict) -> str:
    """Análisis de sentimiento: cómo tratan HOY los medios internacionales a la
    Argentina (Selección, jugadores, clubes). Sobre el recorte de notas del
    exterior con gancho argentino del panorama actual (~últimas 24-48h)."""
    notas = notas_exterior_relevantes(resultados, 60)
    listado = "\n".join(
        f"  • [{n['fuente']['nombre']}] {n['titulo'][:130]}"
        + (f"  ({' · '.join(n['entidades'][:3])})" if n['entidades'] else "")
        for n in notas
    ) or "  (sin notas del exterior con gancho argentino en el panorama)"
    return f"""Sos analista de medios de un diario deportivo argentino. Abajo están los
titulares que los medios INTERNACIONALES publicaron en las últimas 24-48 horas
mencionando a la Argentina: su Selección, sus jugadores en el mundo, sus clubes,
sus DTs. El nombre de cada medio indica su origen (Marca/AS España, Gazzetta/
Corriere/Sky Italia, L'Équipe Francia, BBC/Guardian/Sky Inglaterra, Globo/GE
Brasil, Record Portugal, Bild Alemania, etc.).

Hacé un ANÁLISIS DE SENTIMIENTO en español rioplatense:

TERMÓMETRO GENERAL — ¿cómo nos está viendo el mundo hoy? Un veredicto en 2-3
líneas con temperatura: admiración / respeto / neutralidad / crítica / burla.

POR TEMA — el sentimiento desglosado (Selección / Messi / jugadores en Europa /
clubes y mercado / otros). Por cada uno: el tono dominante y UN titular que lo
pruebe (citalo entre comillas con su medio).

POR PAÍS — ¿quién nos elogia y quién nos pega? Diferencias entre la prensa
española, italiana, inglesa, brasileña, francesa. Una línea por país con datos.

LO MÁS ELOGIOSO y LO MÁS CRÍTICO — el titular más admirativo y el más hostil
del recorte, citados textuales con su medio.

💡 IDEAS DE NOTA — 2-3 títulos estilo Olé que salgan de este análisis (del tipo
"Los europeos te ningunean, Argentina" o "El mundo se rinde a..."), cada uno con
una línea de por qué rendiría.

Basate SOLO en los titulares listados. Si el recorte es chico, aclaralo y no
sobreinterpretes.

TITULARES DEL EXTERIOR SOBRE ARGENTINA:
{listado}"""


def prompt_informe_ole(resultados: dict, analisis: dict, temas_editor: str = "") -> str:
    tendencias = calcular_tendencias(resultados)
    top = tendencias[:10]
    faltantes = analisis.get("faltantes_en_ole", [])[:15]
    bloque_top = "\n\n".join(
        f"TEMA {i+1}: {c['titulo'][:130]} ({c['cant_medios']} medios · Olé: {'sí' if c.get('tiene_ole') else 'NO'})\n"
        + "\n".join(f"   · [{n['fuente']['nombre']}] {n['noticia']['titulo'][:110]}"
                     for n in c.get("noticias", [])[:5])
        for i, c in enumerate(top)
    )
    bloque_falt = "\n".join(f"  • [{f['fuente_nombre']}] {f['titulo'][:120]}"
                             for f in faltantes) or "  (ninguno)"

    if temas_editor.strip():
        # contexto: cómo tituló la competencia los temas que pidió el editor
        pedidos = [t.strip() for t in re.split(r"[\n,;]+", temas_editor) if t.strip()]
        ctx = []
        for pedido in pedidos[:6]:
            kp = normalizar_titulo(pedido)
            relacionadas = []
            for c in tendencias:
                if solapamiento(kp, normalizar_titulo(c["titulo"])) >= 0.3 or \
                   any(w in c["titulo"].lower() for w in pedido.lower().split() if len(w) > 3):
                    for n in c.get("noticias", [])[:4]:
                        relacionadas.append(f"     · [{n['fuente']['nombre']}] {n['noticia']['titulo'][:110]}")
                    if len(relacionadas) >= 6:
                        break
            ctx.append(f"TEMA PEDIDO: {pedido}\n"
                       + ("\n".join(relacionadas[:6]) if relacionadas
                          else "     (sin cobertura detectada en el panorama actual)"))
        bloque_ctx = "\n\n".join(ctx)
        return f"""Sos editor de Olé. No generes noticias descriptivas: competí por el
significado antes que por la información.

{FRAMEWORK_ANGULOS}{bloque_criterios()}

El editor quiere trabajar ESTOS temas hoy. Para cada uno, dale munición:

POR CADA TEMA PEDIDO:
  • Los niveles de lectura que manda (qué cambió / a quién afecta / qué emoción /
    qué patrón / qué consecuencia).
  • CINCO ÁNGULOS del framework, cada uno con su título sugerido y el tipo de
    ángulo nombrado. Si la competencia ya cubrió el tema (tenés sus títulos),
    priorizá los ángulos que NADIE usó.
  • Tu recomendación: cuál es EL ángulo ganador y por qué.
  • Un dato o pregunta que le falta a la nota para ser imbatible.

Español rioplatense, directo, sin relleno.

TEMAS PEDIDOS (con cómo los tituló la competencia):
{bloque_ctx}"""

    return f"""Sos editor de Olé. No generes noticias descriptivas: para cada hecho
detectá patrones, conflictos, consecuencias, cambios de estatus, héroes
inesperados, paradojas e impacto emocional en el hincha. Competí por el
significado antes que por la información.

{FRAMEWORK_ANGULOS}{bloque_criterios()}

Abajo tenés los 10 temas más calientes (con cómo tituló cada medio) y los
huecos donde Olé no entró. Escribí en español rioplatense:

FOCOS SUGERIDOS — Elegí los 6 temas con más potencial. Por cada uno:
  • El tema en una línea y qué nivel de lectura manda (qué cambió / a quién
    afecta / qué emoción genera / qué patrón revela / qué consecuencia deja).
  • AL MENOS CINCO ÁNGULOS DISTINTOS del framework, cada uno con su título
    sugerido. Nombrá el tipo de ángulo. Evitá los que ya usó la competencia
    (sus títulos están a la vista).
  • Tu recomendación: cuál de los cinco es EL ángulo, y por qué.

HUECOS RÁPIDOS — De la lista de faltantes, marcá los 3 que valen la pena y el
ángulo de entrada en una línea; ignorá el resto.

TOP 10 TEMAS:
{bloque_top}

FALTANTES EN OLÉ:
{bloque_falt}"""

def _extraer_cuerpo_nota(url: str, max_chars: int = 900) -> str:
    """Intenta extraer los primeros párrafos del cuerpo de una nota. Retorna '' si falla.
    Limitado a 900 chars por nota para controlar el gasto de tokens de entrada."""
    if not url or not url.startswith("http"):
        return ""
    try:
        resp = requests.get(url, headers=_FETCH_HEADERS, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        # Eliminar scripts, estilos, menús, publicidades
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form", "figure", "noscript", "iframe"]):
            tag.decompose()
        # Selectores de cuerpo de nota, del más específico al más genérico
        BODY_SELS = [
            "article .article-body", "article .nota-cuerpo", "article .entry-content",
            "article .article-content", "article .post-content", "article .content-body",
            ".article__body", ".nota__cuerpo", ".article-text", ".news-body",
            "[class*=article-body]", "[class*=nota-cuerpo]", "[class*=entry-content]",
            "[class*=article-content]", "[class*=post-body]",
            "article", "[role=main]",
        ]
        texto = ""
        for sel in BODY_SELS:
            el = soup.select_one(sel)
            if el:
                parrafos = [p.get_text(" ", strip=True) for p in el.find_all("p") if len(p.get_text(strip=True)) > 40]
                texto = "\n".join(parrafos[:5])  # máx 5 párrafos por nota
                if len(texto) > 200:
                    break
        if not texto:
            # Último recurso: todos los <p> largos de la página
            parrafos = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 60]
            texto = "\n".join(parrafos[:4])
        return texto[:max_chars].strip()
    except Exception:
        return ""

def scrape_cuerpos_notas(titulares: list, max_notas: int = 6) -> list:
    """
    Enriquece los titulares con el cuerpo scrapeado de cada URL.
    Retorna lista de dicts con keys: fuente, noticia, cuerpo, ok.
    Solo scrappea las primeras max_notas con URL válida.
    """
    enriquecidos = []
    con_url = [item for item in titulares if item["noticia"].get("url")][:max_notas]
    sin_url  = [item for item in titulares if not item["noticia"].get("url")]

    if con_url:
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(_extraer_cuerpo_nota, item["noticia"]["url"]): item for item in con_url}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    cuerpo = future.result()
                except Exception:
                    cuerpo = ""
                enriquecidos.append({**item, "cuerpo": cuerpo, "ok": bool(cuerpo)})

    for item in sin_url:
        enriquecidos.append({**item, "cuerpo": "", "ok": False})

    # Agregar el resto de titulares (más allá de max_notas) sin cuerpo
    ids_procesados = {id(item) for item in con_url + sin_url}
    for item in titulares:
        if id(item) not in ids_procesados:
            enriquecidos.append({**item, "cuerpo": "", "ok": False})

    return enriquecidos

def prompt_nota_rapida(tema: str, titulares_enriquecidos: list, estilo: str, tipo_nota: str, contexto_extra: str = "") -> str:
    con_cuerpo  = [t for t in titulares_enriquecidos if t.get("ok")]
    solo_titulo = [t for t in titulares_enriquecidos if not t.get("ok")]
    tiene_info_real = len(con_cuerpo) > 0

    # Bloque de fuentes con cuerpo completo
    bloque_completo = ""
    if con_cuerpo:
        partes = []
        for t in con_cuerpo:
            f, n = t["fuente"], t["noticia"]
            partes.append(
                f"── [{f['nombre']}] {n['titulo']}\n"
                f"URL: {n.get('url','')}\n"
                f"TEXTO:\n{t['cuerpo']}"
            )
        bloque_completo = "\n\n".join(partes)

    # Bloque de fuentes solo con titular
    bloque_titulares = ""
    if solo_titulo:
        bloque_titulares = "\n".join(
            f"  • [{t['fuente']['nombre']}] {t['noticia']['titulo']}"
            for t in solo_titulo
        )

    estilos = {
        "Informativa": (
            "Estilo agencia de noticias argentina (Télam/NA). "
            "Tono directo, neutro, sin opinión ni adjetivos innecesarios. "
            "Verbos en pasado o presente simple. Oraciones cortas. "
            "Los datos concretos van primero, el contexto después."
        ),
        "Analítica": (
            "Estilo agencia argentina con profundidad. "
            "Tono directo y neutro pero con contexto, antecedentes y proyección. "
            "Cada afirmación tiene respaldo en las fuentes. "
            "Párrafos más largos, estructura de causa-efecto."
        ),
        "Urgente/Flash": (
            "Estilo despacho urgente de agencia argentina. "
            "Máximo 3 párrafos muy cortos. Verbo en presente. "
            "Solo el dato central, sin contexto. "
            "Primera oración = toda la noticia en una línea."
        ),
    }
    tipos = {
        "Nota completa": (
            "Nota con subtítulos (SIN lead/cierre clásico de manual). Estructura:\n"
            "- Primer párrafo suelto: el hecho central en 2-3 oraciones directas, sin subtítulo.\n"
            "- Luego 3 o 4 secciones, cada una con subtítulo informativo en negrita (## Subtítulo), "
            "seguido de 2-3 párrafos de 60-80 palabras.\n"
            "- La nota entera: entre 400 y 550 palabras.\n"
            "- Los subtítulos deben ser concretos y periodísticos, no genéricos "
            "(ej: '## La lesión y los plazos de recuperación' en vez de '## Contexto')."
        ),
        "Solo titulares alternativos": (
            "Generá 8 titulares alternativos: 2 impactantes, 2 SEO, "
            "2 para redes sociales (con gancho), 2 estilo agencia neutro. "
            "Para cada uno agregá una línea corta explicando el enfoque."
        ),
        "Esqueleto + ángulos": (
            "Esqueleto con subtítulos numerados (## 1. ..., ## 2. ...) "
            "y una línea describiendo qué información va en cada sección. "
            "Al final, 3 ángulos posibles con título sugerido para cada uno."
        ),
    }

    instruccion_angulo = f"""ANTES DE ESCRIBIR — el método (obligatorio, no lo saltees):
Identificá en silencio los 6 niveles de lectura del hecho: qué pasó, qué cambió,
a quién afecta, qué emoción genera, qué tendencia o patrón revela y qué
consecuencia deja. Después elegí UN ángulo del framework de Olé (cambio de
estatus, patrón, consecuencia, héroe inesperado, conflicto, paradoja, identidad,
tendencia, qué significa, el día después) y construí TODA la nota alrededor de
ese ángulo: el título compite por el significado, no por la información; el
primer párrafo instala el ángulo, no la crónica.{bloque_criterios()}

"""

    if tiene_info_real:
        instruccion_alucinacion = instruccion_angulo + """⚠️ REGLAS ANTI-ALUCINACIÓN (CRÍTICAS — leelas antes de escribir una sola palabra):
- Usá ÚNICAMENTE datos, cifras, citas y hechos que aparezcan textualmente en las FUENTES de abajo.
- Prohibido agregar contexto histórico, estadísticas o antecedentes que no estén en los textos.
- Las citas entre comillas SOLO pueden ser frases que aparezcan literalmente en los textos fuente.
- Si un dato no está en los textos, escribí [DATO A CONFIRMAR] en su lugar. Sin excepciones.
- Si dos fuentes se contradicen, mencioná la contradicción explícitamente."""

        instruccion_formato = """
FORMATO DE RESPUESTA OBLIGATORIO — respetá este orden exacto:

════════════════════════════════════
NOTA
════════════════════════════════════
[Aquí va la nota redactada según el estilo y entregable solicitado]


════════════════════════════════════
TABLA DE VERIFICACIÓN
════════════════════════════════════
Lista TODOS los datos concretos que usaste en la nota (cifras, nombres, citas, hechos).
Para cada uno indicá:
• DATO: el dato exacto como aparece en la nota
• FUENTE: nombre del medio de donde lo tomaste
• VERIFICADO: ✅ si está textualmente en el cuerpo scrapeado | ⚠️ si solo aparece en el titular | ❌ si no encontrás respaldo

Ejemplo de fila:
• DATO: "sufrió un desgarro en el isquiotibial derecho" | FUENTE: TyC Sports | VERIFICADO: ✅

════════════════════════════════════
ÁNGULOS ALTERNATIVOS
════════════════════════════════════
3 enfoques distintos del framework (nombrá el tipo de ángulo), con título sugerido para cada uno.
"""

        bloque_fuentes = f"""=== FUENTES CON TEXTO COMPLETO ({len(con_cuerpo)}) — de estas podés extraer datos ===
{bloque_completo}"""
        if bloque_titulares:
            bloque_fuentes += f"""

=== FUENTES SOLO CON TITULAR ({len(solo_titulo)}) — NO inferir datos, solo confirmar que el tema existe ===
{bloque_titulares}"""
    else:
        instruccion_alucinacion = instruccion_angulo + """⚠️ MODO ESQUELETO SEGURO — no se pudo leer el cuerpo de ninguna nota.
No redactes la nota. En cambio, seguí el formato de respuesta obligatorio de abajo."""

        instruccion_formato = """
FORMATO DE RESPUESTA OBLIGATORIO:

════════════════════════════════════
ESQUELETO DE NOTA
════════════════════════════════════
Estructura con secciones numeradas y vacías, listas para que el redactor complete.
Indicá qué tipo de información va en cada sección.

════════════════════════════════════
DATOS CONFIRMADOS (solo desde titulares)
════════════════════════════════════
Lista con bullet points. Solo lo que los titulares permiten afirmar con certeza.
Formato: • [dato] — confirmado por: [medio]

════════════════════════════════════
DATOS A CONFIRMAR ANTES DE PUBLICAR
════════════════════════════════════
Lista de preguntas concretas que el redactor debe responder antes de publicar.

════════════════════════════════════
ÁNGULOS ALTERNATIVOS
════════════════════════════════════
3 enfoques distintos según qué datos aparezcan, con título sugerido para cada uno.
"""
        bloque_fuentes = f"""=== SOLO TITULARES DISPONIBLES ({len(solo_titulo)}) ===
{bloque_titulares}"""

    return f"""Sos un redactor deportivo de un portal argentino. Tu tarea es trabajar sobre este tema:

TEMA: {tema}
ESTILO: {estilos.get(estilo, estilos["Informativa"])}
ENTREGABLE: {tipos.get(tipo_nota, tipos["Nota completa"])}

{instruccion_alucinacion}
{instruccion_formato}

{bloque_fuentes}

Escribí en español rioplatense con voseo. Tono de agencia de noticias argentina (estilo Télam, NA, DyN).
Reglas de estilo periodístico argentino:
- Los clubes se nombran como los nombra la prensa argentina: "River" (no "River Plate"), "Boca" (no "Boca Juniors"), "Racing" (no "Racing Club"), "San Lorenzo" (no "San Lorenzo de Almagro"), "Independiente", "Huracán", "Vélez", "Lanús", "Defensa", etc.
- Los seleccionados: "la Selección" o "el equipo nacional" (no "la Albiceleste" salvo que sea en un contexto festivo), "la Sub-20", "la Sub-23".
- Los jugadores se mencionan por apellido a partir de la segunda referencia: "Messi" (no "La Pulga"), "Di María" (no "el Fideo"). Sin apodos en texto de agencia.
- Cargos y funciones en minúscula: "el entrenador Scaloni", "el presidente Laporta", "el director técnico".
- Evitá frases como "en este contexto", "cabe destacar", "vale la pena mencionar", "a su vez", "en tanto".
- No uses adjetivos valorativos ("increíble", "impresionante", "histórico", "brillante") salvo que estén textualmente en la fuente.
- Nunca uses "lead", "bajada" ni ningún término de manual de redacción en el cuerpo de la nota.
{("\n=== CONTEXTO ADICIONAL DEL REDACTOR ===\n" + contexto_extra + "\n(Podés usar este contexto libremente en la nota — es información aportada por el redactor, no requiere verificación de fuente.)") if contexto_extra else ""}
"""


def prompt_tono_editorial(query: str, titulares_filtrados: list) -> str:
    bloque = "\n".join(
        f'[{item["fuente"]["nombre"]}] {item["noticia"]["titulo"]}'
        for item in titulares_filtrados
    )
    return f"""Analizá el tono editorial de estos titulares sobre "{query}".

TITULARES ({len(titulares_filtrados)} en total):
{bloque}

Respondé ÚNICAMENTE con un objeto JSON válido, sin texto antes ni después, sin backticks.
El JSON debe tener exactamente esta estructura:

{{
  "resumen": "una oración que describe el tono general de la cobertura",
  "distribucion": {{
    "positivo": 0,
    "negativo": 0,
    "neutro": 0,
    "alarmista": 0,
    "expectante": 0
  }},
  "por_medio": [
    {{
      "medio": "nombre del medio",
      "tono": "positivo|negativo|neutro|alarmista|expectante",
      "titular": "el titular analizado",
      "razon": "una línea explicando por qué ese tono"
    }}
  ],
  "patrones": [
    "patrón editorial detectado 1",
    "patrón editorial detectado 2"
  ]
}}

Tonos posibles:
- positivo: elogio, logro, buena noticia
- negativo: crítica, fracaso, escándalo, mala noticia
- neutro: informativo puro, sin carga valorativa
- alarmista: urgencia, crisis, peligro, dramatismo
- expectante: incertidumbre, espera, "podría", "se espera"
"""



_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
}

def fetch_og_image(url: str) -> str:
    """Busca la imagen principal de una nota. Retorna la URL de la imagen o ''."""
    if not url or not url.startswith("http") or "google.com/search" in url:
        return ""
    if url in _IMAGE_CACHE:
        return _IMAGE_CACHE[url]
    try:
        resp = requests.get(url, headers=_FETCH_HEADERS, timeout=10, allow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Intentar og:image / twitter:image
        for meta in [
            soup.find("meta", property="og:image"),
            soup.find("meta", property="og:image:url"),
            soup.find("meta", attrs={"name": "twitter:image"}),
            soup.find("meta", attrs={"name": "twitter:image:src"}),
        ]:
            if not meta:
                continue
            candidate = meta.get("content", "") or meta.get("value", "") or ""
            if candidate and not _es_imagen_generica(candidate):
                _IMAGE_CACHE[url] = candidate
                return candidate

        # 2. Fallback: primera imagen grande dentro del artículo
        #    Selectores ordenados de más específico a más genérico
        img_selectors = [
            "article figure img",
            "article .image img",
            "article img[src]",
            ".nota-cuerpo img",
            ".article-body img",
            ".entry-content img",
            "figure img",
            "[class*=hero] img",
            "[class*=featured] img",
            "[class*=portada] img",
            "[class*=cover] img",
        ]
        for sel in img_selectors:
            for tag in soup.select(sel):
                src = (
                    tag.get("src") or tag.get("data-src") or
                    tag.get("data-lazy-src") or tag.get("data-original") or ""
                )
                if (src and src.startswith("http")
                        and not src.endswith(".gif")
                        and not _es_imagen_generica(src)
                        and "1x1" not in src and "pixel" not in src.lower()):
                    _IMAGE_CACHE[url] = src
                    return src

        _IMAGE_CACHE[url] = ""
        return ""
    except Exception:
        _IMAGE_CACHE[url] = ""
        return ""

_IMAGE_CACHE = {}  # cache de og:images por URL (vive lo que dure el proceso)


def fetch_og_images_batch(noticias: list) -> None:
    """Fetch og:images en paralelo para una lista de noticias. Guarda en _IMAGE_CACHE."""
    urls_sin_cache = [
        n["url"] for n in noticias
        if n.get("url") and n["url"] not in _IMAGE_CACHE
        and "news.google.com" not in n["url"]  # redirects de Google News: no tienen imagen
    ]
    if not urls_sin_cache:
        return
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(fetch_og_image, u) for u in urls_sin_cache]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

