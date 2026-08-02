from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .coverage import best_ole_match, normalize_ole_items
from .utils import clamp, normalize_text, stable_id, unique_strings

RARE_HINTS = {
    "insolito", "insolita", "bizarre", "weird", "strange", "unusual", "curious",
    "record", "historico", "historic", "historia", "primera vez", "youngest", "oldest",
    "viral", "video", "imagen", "foto", "fan", "hincha", "supporter", "crowd",
    "estadio", "stadium", "tecnologia", "technology", "robot", "inteligencia artificial",
    "millones", "million", "billion", "fortuna", "salario", "premio", "money",
    "rescato", "saved", "rescue", "milagro", "miracle", "emocion", "tears",
    "escandalo", "scandal", "denuncia", "court", "tribunal", "ban", "sancion",
    "muerte", "murio", "fallecio", "death", "accident", "accidente",
    "mascota", "animal", "wedding", "casamiento", "tattoo", "tatuaje",
    "gol de arquero", "goalkeeper score", "goalkeeper scored", "own goal", "autogol",
}

VISUAL_HINTS = {
    "video", "imagen", "foto", "viral", "camara", "camera", "celebracion",
    "celebration", "hinchas", "fans", "estadio", "stadium", "golazo", "blooper",
}

DATA_HINTS = {
    "record", "historico", "primera vez", "youngest", "oldest", "racha",
    "estadistica", "stat", "million", "millones", "ranking", "marca",
}

ROUTINE_HINTS = {
    "probable formacion", "probable lineup", "training", "entrenamiento", "practica",
    "preview", "previa", "where to watch", "donde ver", "hora y tv", "convocados",
    "said", "dijo", "hablo", "declaracion", "press conference", "conferencia",
    "rumor", "could sign", "interested in", "sondeo", "interesa", "negocia",
}

ARGENTINA_HINTS = {
    "argentin", "messi", "scaloni", "dibu", "emiliano martinez", "julian alvarez",
    "lautaro", "enzo fernandez", "mac allister", "cuti romero", "garnacho",
    "mastantuono", "nico paz", "di maria", "de paul", "otamendi", "simeone",
    "bielsa", "pochettino", "gallardo", "river", "boca", "racing", "independiente",
    "san lorenzo", "libertadores", "sudamericana", "rival de argentina",
}

GLOBAL_HINTS = {
    "real madrid", "barcelona", "manchester", "liverpool", "arsenal", "chelsea",
    "psg", "bayern", "juventus", "milan", "inter", "champions", "world cup",
    "mundial", "premier league", "la liga", "serie a", "formula 1", "nba",
    "mbappe", "haaland", "cristiano", "neymar", "vinicius", "lamine yamal",
}

QUALITY_SOURCE_IDS = {
    "bbc", "guardian", "reuters_dep", "efe", "afp_f24", "fifa", "uefa",
    "conmebol", "athletic", "lequipe", "gazzetta", "globo", "geglobo",
}

EXCLUDED_SOURCE_IDS = {
    "ole", "espn", "tyc", "infobae", "lanacion", "tn", "clarin", "elgrafico",
    "dobleamarilla", "bolavip", "lavoz", "capital", "na", "cuatro42", "cielosports",
    "popular", "ambito", "afa", "radar_ar", "tntsports",
    "merlo", "grova", "ligapro", "arbitros", "gn_river", "gn_boca",
    "gn_selec", "gn_pases", "juveniles", "gn_racing", "gn_inde",
    "gn_sanlo", "gn_messi", "gn_colap",
}


def _parse_date(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _jaccard(a: str, b: str) -> float:
    ta = {x for x in normalize_text(a).split() if len(x) >= 3}
    tb = {x for x in normalize_text(b).split() if len(x) >= 3}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _category(text: str, arg_hook: bool) -> str:
    if arg_hook:
        return "CONEXION ARGENTINA"
    if any(h in text for h in VISUAL_HINTS):
        return "OPORTUNIDAD VISUAL"
    if any(h in text for h in DATA_HINTS):
        return "DATO O RECORD"
    return "HISTORIA RARA"


def _story_score(title: str, source_id: str, publisher: str, media_count: int,
                 age_hours: float | None, ole_score: float) -> tuple[int, int, list[str], str]:
    text = normalize_text(title)
    arg_hook = any(h in text for h in ARGENTINA_HINTS)
    rare_hits = [h for h in RARE_HINTS if h in text]
    visual_hits = [h for h in VISUAL_HINTS if h in text]
    global_hook = any(h in text for h in GLOBAL_HINTS)
    routine = any(h in text for h in ROUTINE_HINTS)

    value_ar = 12
    if arg_hook:
        value_ar += 42
    if global_hook:
        value_ar += 20
    if rare_hits:
        value_ar += min(24, len(rare_hits) * 8)
    if visual_hits:
        value_ar += 8
    value_ar = clamp(value_ar)

    score = 18
    score += 28 if arg_hook else 0
    score += 16 if global_hook else 0
    score += min(30, len(rare_hits) * 10)
    score += min(12, max(0, media_count - 1) * 5)
    score += 10 if source_id in QUALITY_SOURCE_IDS else 0
    score += 5 if publisher and publisher.lower() not in {"google news", "gnews"} else 0
    score -= 24 if routine and not rare_hits else 0
    score -= 30 if ole_score >= 0.60 else (15 if ole_score >= 0.40 else 0)
    if age_hours is None:
        score -= 18
    elif age_hours > 8:
        score -= 18
    elif age_hours <= 2:
        score += 8
    score = clamp(score)

    reasons: list[str] = []
    if arg_hook:
        reasons.append("tiene una conexion directa con el lector argentino")
    if global_hook:
        reasons.append("involucra una figura, club o competencia de alcance masivo")
    if rare_hits:
        reasons.append("contiene una rareza, record o giro narrativo")
    if visual_hits:
        reasons.append("tiene potencial visual o de redes")
    if source_id in QUALITY_SOURCE_IDS:
        reasons.append("proviene de una fuente internacional de alta confianza")
    if media_count > 1:
        reasons.append(f"aparece en {media_count} publishers originales")
    if ole_score < 0.38:
        reasons.append("no se encontro una nota equivalente en Ole")
    elif ole_score < 0.60:
        reasons.append("la coincidencia con Ole es parcial y requiere revision")
    if age_hours is not None:
        reasons.append(f"fue publicada hace {age_hours:.1f} horas")

    return score, value_ar, reasons, _category(text, arg_hook)


def _collect(results: dict, source_map: dict, max_age_hours: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for source_id, news_items in (results or {}).items():
        if source_id in EXCLUDED_SOURCE_IDS:
            continue
        source = source_map.get(source_id, {"id": source_id, "nombre": source_id})
        for news in news_items or []:
            title = str(news.get("titulo") or "").strip()
            if len(title) < 18:
                continue
            published = _parse_date(news.get("fecha_publicacion", ""))
            age = (now - published).total_seconds() / 3600 if published else None
            if age is not None and age > max_age_hours:
                continue
            items.append({
                "source_id": source_id,
                "source_name": source.get("nombre", source_id),
                "publisher": news.get("publisher_original") or source.get("nombre", source_id),
                "title": title,
                "url": news.get("url", ""),
                "published_at": news.get("fecha_publicacion", ""),
                "age_hours": age,
            })
    return items


def _cluster(items: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            if _jaccard(item["title"], cluster[0]["title"]) >= 0.34:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def generate(results: dict, ole_items: list[dict] | None, previous: list[dict] | None = None,
             max_items: int = 10, config: dict | None = None) -> list[dict]:
    config = config or {}
    max_age_hours = int(
        config.get("discovery_max_age_hours")
        or os.environ.get("DISCOVERY_MAX_AGE_HOURS", "8")
        or 8
    )
    min_score = int(os.environ.get("DISCOVERY_MIN_SCORE", "58") or 58)
    try:
        from monitor_core import TODAS_FUENTES
        source_map = {source["id"]: source for source in TODAS_FUENTES}
    except Exception:
        source_map = {}

    normalized_ole = normalize_ole_items(ole_items)
    prev_by_id = {
        str(row.get("DiscoveryID") or row.get("discovery_id") or ""): row
        for row in previous or []
        if str(row.get("DiscoveryID") or row.get("discovery_id") or "")
    }
    clusters = _cluster(_collect(results, source_map, max_age_hours))
    discoveries: list[dict] = []

    for cluster in clusters:
        representative = min(cluster, key=lambda x: x.get("age_hours") if x.get("age_hours") is not None else 999)
        publishers = unique_strings([item.get("publisher", "") for item in cluster])
        match = best_ole_match(representative["title"], normalized_ole)
        score, value_ar, reasons, category = _story_score(
            representative["title"], representative["source_id"], representative["publisher"],
            len(publishers), representative.get("age_hours"), float(match.get("score", 0) or 0),
        )
        if score < min_score:
            continue
        discovery_id = stable_id(normalize_text(representative["title"]), "d")
        previous_item = prev_by_id.get(discovery_id)
        is_new = previous_item is None
        try:
            previous_media = int(float(previous_item.get("Medios", 0))) if previous_item else 0
        except Exception:
            previous_media = 0
        grew = bool(previous_item) and len(publishers) > previous_media
        if previous_item and not grew:
            score = max(0, score - 22)
            reasons.append("ya aparecio en el corte anterior y no sumo nuevos publishers")
        elif grew:
            reasons.append(f"sumo {len(publishers) - previous_media} publishers desde el corte anterior")
        discoveries.append({
            "discovery_id": discovery_id,
            "title": representative["title"],
            "url": representative.get("url", ""),
            "category": category,
            "score": score,
            "value_argentina": value_ar,
            "publishers": publishers,
            "media_count": len(publishers),
            "published_at": representative.get("published_at", ""),
            "age_hours": representative.get("age_hours"),
            "is_new": is_new,
            "grew": grew,
            "ole_status": "NO_CUBIERTO" if float(match.get("score", 0) or 0) < 0.38 else "REVISAR_COINCIDENCIA",
            "ole_match_title": match.get("title", ""),
            "ole_match_url": match.get("url", ""),
            "reason": ". ".join(unique_strings(reasons)),
            "suggested_angle": _suggest_angle(category, representative["title"]),
            "suggested_format": _suggest_format(category),
            "evidence": cluster[:8],
            "notify": (is_new or grew) and score >= 76,
        })

    discoveries.sort(key=lambda item: (-item["score"], -item["value_argentina"], item.get("age_hours") or 999))
    return discoveries[:max_items]


def _suggest_angle(category: str, title: str) -> str:
    if category == "CONEXION ARGENTINA":
        return "Explicar por que esta historia del exterior importa en Argentina y que protagonista local conecta ambos mundos."
    if category == "OPORTUNIDAD VISUAL":
        return "Contar el hecho desde la escena, el video o la imagen y sumar el contexto que la vuelve significativa."
    if category == "DATO O RECORD":
        return "Poner el dato en perspectiva: antecedente, comparacion y por que es excepcional."
    return "Convertir la rareza en una historia con personaje, conflicto, giro y consecuencia."


def _suggest_format(category: str) -> str:
    return {
        "CONEXION ARGENTINA": "PERFIL / EXPLICADOR",
        "OPORTUNIDAD VISUAL": "NOTA BREVE + VIDEO",
        "DATO O RECORD": "DATOS / COMPARATIVA",
        "HISTORIA RARA": "HISTORIA / COLOR",
    }.get(category, "HISTORIA")
