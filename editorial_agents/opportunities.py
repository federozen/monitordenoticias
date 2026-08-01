from __future__ import annotations

from collections import Counter

from .utils import normalize_text, stable_id

CATEGORY_RULES = [
    ({"lesion", "lesionado", "baja", "parte medico", "recuperacion"},
     "SERVICIO", "Estado, reemplazos y consecuencias deportivas"),
    ({"mercado", "pase", "fichaje", "refuerzo", "oferta", "negocia", "prestamo"},
     "EXPLICADOR", "Que se sabe, que falta y quienes intervienen"),
    ({"clasifica", "clasificacion", "tabla", "libertadores", "sudamericana", "descenso", "promedio"},
     "CUENTAS", "Escenarios, rivales directos y que necesita cada equipo"),
    ({"formacion", "equipo", "practica", "entrenamiento", "titulares", "cambio"},
     "PREVIA", "La decision del entrenador y como cambia el partido"),
    ({"record", "historia", "primera vez", "racha"},
     "DATOS", "El antecedente, la comparacion y por que importa ahora"),
    ({"sancion", "fallo", "tribunal", "reglamento"},
     "EXPLICADOR", "Que dice la norma y cual es el impacto concreto"),
]

STOP = {
    "para", "como", "sobre", "desde", "hasta", "ante", "entre", "tras", "esta", "este",
    "estos", "estas", "del", "los", "las", "una", "uno", "que", "con", "sin", "por",
    "mas", "muy", "sus", "fue", "ser", "son", "nuevo", "nueva",
}


def _category(title: str) -> tuple[str, str]:
    normalized = normalize_text(title)
    for words, fmt, angle in CATEGORY_RULES:
        if any(word in normalized for word in words):
            return fmt, angle
    return "ANALISIS", "Que cambio, a quien afecta y que puede pasar ahora"


def _main_entity(title: str) -> str:
    tokens = [token for token in normalize_text(title).split() if len(token) > 3 and token not in STOP]
    return tokens[0].title() if tokens else "El tema"


def generate(recommendations: list[dict], max_items: int = 6) -> list[dict]:
    opportunities: list[dict] = []
    used_clusters: set[str] = set()

    for rec in recommendations:
        if rec.get("priority", 0) < 45:
            continue
        fmt, angle = _category(rec.get("title", ""))
        entity = _main_entity(rec.get("title", ""))
        effort = "BAJO" if fmt in {"SERVICIO", "CUENTAS", "PREVIA"} else "MEDIO"
        expiry = "HOY" if rec.get("priority", 0) >= 75 else "PROXIMAS HORAS"
        idea = f"{fmt.title()}: {angle}"
        opportunities.append({
            "opportunity_id": stable_id(f"{rec.get('cluster_id')}|{fmt}|{angle}", "o"),
            "title": idea,
            "source_title": rec.get("title", ""),
            "cluster_ids": [rec.get("cluster_id", "")],
            "format": fmt,
            "angle": angle,
            "why_now": rec.get("reason", ""),
            "suggested_headline": f"{entity}: {angle.lower()}",
            "effort": effort,
            "expiry": expiry,
            "score": min(100, int(rec.get("priority", 0)) + (10 if not rec.get("has_ole") else 0)),
        })
        used_clusters.add(rec.get("cluster_id", ""))
        if len(opportunities) >= max_items - 1:
            break

    # One cross-topic opportunity when the same meaningful token appears repeatedly.
    token_counter: Counter[str] = Counter()
    rec_by_token: dict[str, list[dict]] = {}
    for rec in recommendations[:20]:
        tokens = {t for t in normalize_text(rec.get("title", "")).split() if len(t) > 4 and t not in STOP}
        for token in tokens:
            token_counter[token] += 1
            rec_by_token.setdefault(token, []).append(rec)
    common = next(((token, count) for token, count in token_counter.most_common() if count >= 3), None)
    if common and len(opportunities) < max_items:
        token, count = common
        related = rec_by_token[token][:5]
        opportunities.append({
            "opportunity_id": stable_id(f"panorama|{token}", "o"),
            "title": f"PANORAMA: las {count} novedades que explican el momento de {token.title()}",
            "source_title": " | ".join(r.get("title", "") for r in related),
            "cluster_ids": [r.get("cluster_id", "") for r in related],
            "format": "PANORAMA",
            "angle": "Unir novedades dispersas en una lectura editorial unica",
            "why_now": f"El mismo protagonista aparece en {count} temas relevantes del corte actual",
            "suggested_headline": f"{token.title()}, bajo la lupa: que cambio y que viene",
            "effort": "MEDIO",
            "expiry": "HOY",
            "score": 80,
        })

    opportunities.sort(key=lambda item: -item["score"])
    return opportunities[:max_items]
