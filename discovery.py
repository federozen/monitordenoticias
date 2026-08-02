from __future__ import annotations

import os
from datetime import datetime, timezone

from .coverage import best_ole_match, normalize_ole_items
from .freshness import confidence_from_evidence, is_stale_risk_title
from .utils import clamp, normalize_text, stable_id, unique_strings

RARE_HINTS = {
    "insolito", "bizarre", "weird", "strange", "unusual", "curious", "inusitado",
    "curioso", "insolite", "kurios", "milagro", "miracle", "wunder", "mascota",
    "animal", "tattoo", "boda", "wedding", "gol de arquero", "goalkeeper scored",
    "goleiro marcou", "portiere segna", "gardien buteur", "goalkeeper score", "98th minute",
    "tiny club", "blooper", "own goal",
}
VISUAL_HINTS = {
    "video", "imagen", "foto", "viral", "camara", "camera", "celebracion",
    "celebration", "hinchas", "fans", "torcida", "tifosi", "supporters", "golazo",
}
DATA_HINTS = {
    "record", "recorde", "rekord", "historico", "historic", "historique", "storico",
    "primera vez", "youngest", "oldest", "racha", "estadistica", "ranking", "million",
    "millones", "billion",
}
CONFLICT_HINTS = {
    "escandalo", "scandal", "skandal", "polemica", "controversy", "denuncia",
    "court", "ban", "sancion", "suspend", "investig", "pelea", "crisis", "conflict",
}
HUMAN_HINTS = {
    "historia", "story", "emocion", "tears", "lagrimas", "muerte", "death",
    "accident", "familia", "superacion", "survivor", "dream", "sueno", "refugee",
}
TECH_BUSINESS_HINTS = {
    "tecnologia", "technology", "inteligencia artificial", "artificial intelligence",
    "estadio", "stadium", "derechos", "broadcast", "patrocin", "sponsor", "inversion",
    "investment", "negocio", "business", "ticket", "salario", "money", "fortuna",
}
CONSEQUENCE_HINTS = {
    "clasifico", "elimino", "ascenso", "descenso", "campeon", "promotion", "relegation",
    "qualified", "banned", "suspended", "cambio la regla", "new rule", "afecta", "impact",
}
ROUTINE_HINTS = {
    "probable formacion", "probable lineup", "training", "entrenamiento", "preview", "previa",
    "where to watch", "donde ver", "hora y tv", "convocados", "said", "dijo", "hablo",
    "press conference", "conferencia", "rumor", "could sign", "interested in", "sondeo",
    "interesa", "negocia", "mercato", "calciomercato", "resultado en vivo", "live score",
}
ARGENTINA_HINTS = {
    "argentin", "messi", "scaloni", "dibu", "emiliano martinez", "julian alvarez", "lautaro",
    "enzo fernandez", "mac allister", "cuti romero", "garnacho", "mastantuono", "nico paz",
    "di maria", "de paul", "otamendi", "simeone", "bielsa", "pochettino", "gallardo",
    "river", "boca", "racing", "independiente", "san lorenzo", "libertadores", "sudamericana",
}
GLOBAL_HINTS = {
    "real madrid", "barcelona", "manchester", "liverpool", "arsenal", "chelsea", "psg",
    "bayern", "juventus", "milan", "inter", "champions", "world cup", "mundial",
    "premier league", "la liga", "serie a", "formula 1", "nba", "mbappe", "haaland",
    "cristiano", "neymar", "vinicius", "lamine yamal",
}
OFFICIAL_SOURCE_HINTS = {
    "fifa", "uefa", "conmebol", "olympics", "club", "federation", "federacion", "liga",
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
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _hits(text: str, hints: set[str]) -> list[str]:
    return [hint for hint in hints if hint in text]


def _category(signals: dict[str, bool]) -> str:
    if signals["argentina"]:
        return "CONEXION ARGENTINA"
    if signals["rare"]:
        return "HISTORIA RARA"
    if signals["visual"]:
        return "OPORTUNIDAD VISUAL"
    if signals["data"]:
        return "DATO O RECORD"
    if signals["tech_business"]:
        return "NEGOCIO / TECNOLOGIA"
    if signals["human"]:
        return "HISTORIA HUMANA"
    if signals["conflict"]:
        return "POLEMICA / CONFLICTO"
    return "CANDIDATO INTERNACIONAL"


def _editorial_assessment(title: str, media_count: int, age_hours: float,
                          ole_score: float) -> tuple[int, int, list[str], str, int]:
    text = normalize_text(title)
    signals = {
        "argentina": any(h in text for h in ARGENTINA_HINTS),
        "rare": bool(_hits(text, RARE_HINTS)),
        "visual": bool(_hits(text, VISUAL_HINTS)),
        "data": bool(_hits(text, DATA_HINTS)),
        "conflict": bool(_hits(text, CONFLICT_HINTS)),
        "human": bool(_hits(text, HUMAN_HINTS)),
        "tech_business": bool(_hits(text, TECH_BUSINESS_HINTS)),
        "consequence": bool(_hits(text, CONSEQUENCE_HINTS)),
        "global": any(h in text for h in GLOBAL_HINTS),
    }
    routine = any(h in text for h in ROUTINE_HINTS)
    signal_count = sum(1 for key, value in signals.items() if value and key not in {"global"})

    # La reputacion de la fuente no entra en este puntaje. Solo mide valor
    # periodistico potencial para el lector argentino.
    score = 8
    score += 24 if signals["argentina"] else 0
    score += 22 if signals["rare"] else 0
    score += 13 if signals["visual"] else 0
    score += 13 if signals["data"] else 0
    score += 13 if signals["conflict"] else 0
    score += 13 if signals["human"] else 0
    score += 14 if signals["tech_business"] else 0
    score += 15 if signals["consequence"] else 0
    score += 7 if signals["global"] else 0
    score += min(8, max(0, media_count - 1) * 3)
    score += 6 if age_hours <= 2 else (3 if age_hours <= 6 else 0)
    score -= 22 if routine and signal_count < 2 else 0
    score -= 30 if ole_score >= 0.62 else (12 if ole_score >= 0.42 else 0)
    score = clamp(score)

    value_ar = 10
    value_ar += 45 if signals["argentina"] else 0
    value_ar += 12 if signals["global"] else 0
    value_ar += 12 if signals["rare"] or signals["human"] else 0
    value_ar += 10 if signals["visual"] or signals["data"] else 0
    value_ar += 10 if signals["consequence"] or signals["conflict"] else 0
    value_ar = clamp(value_ar)

    reasons: list[str] = []
    if signals["argentina"]:
        reasons.append("tiene una conexion concreta con protagonistas o intereses argentinos")
    if signals["rare"]:
        reasons.append("contiene una rareza o giro fuera de lo habitual")
    if signals["human"]:
        reasons.append("tiene una historia humana reconocible")
    if signals["consequence"]:
        reasons.append("produce una consecuencia deportiva clara")
    if signals["data"]:
        reasons.append("aporta un record o dato que puede ponerse en perspectiva")
    if signals["visual"]:
        reasons.append("tiene una escena, imagen o video con valor narrativo")
    if signals["conflict"]:
        reasons.append("plantea un conflicto o polemica con consecuencias")
    if signals["tech_business"]:
        reasons.append("abre un angulo de negocio, tecnologia o industria deportiva")
    if signals["global"] and signal_count:
        reasons.append("involucra una figura o competencia conocida por el lector argentino")
    if ole_score < 0.38:
        reasons.append("no se encontro una cobertura equivalente en Ole")
    elif ole_score < 0.62:
        reasons.append("la coincidencia con Ole es parcial")

    return score, value_ar, reasons, _category(signals), signal_count


def _international_source_ids(source_map: dict) -> set[str]:
    try:
        from monitor_core import FUENTES_NAC_IDS, FUENTES_ESP_IDS
        return set(source_map) - set(FUENTES_NAC_IDS) - set(FUENTES_ESP_IDS)
    except Exception:
        return set(source_map)


def _collect(results: dict, source_map: dict, max_age_hours: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    allowed = _international_source_ids(source_map)
    items: list[dict] = []
    for source_id, news_items in (results or {}).items():
        if allowed and source_id not in allowed:
            continue
        source = source_map.get(source_id, {"id": source_id, "nombre": source_id})
        for news in news_items or []:
            title = str(news.get("titulo") or "").strip()
            if len(title) < 18:
                continue
            published = _parse_date(news.get("article_published_at") or news.get("fecha_publicacion", ""))
            channel = str(news.get("discovery_channel") or "")
            source_url = str(source.get("url") or "")
            trust = str(news.get("date_trust") or "").lower()
            is_gnews = channel.lower() == "google news" or "news.google.com" in source_url or source_id.startswith("gn_")
            if not trust:
                trust = "discovery_timestamp" if is_gnews else "rss_publisher_timestamp"
            if published is None or trust in {"discovery_timestamp", "missing", "unverified", "unverified_stale_risk"}:
                continue
            if is_stale_risk_title(title) and trust not in {"article_metadata", "publisher_metadata", "official_timestamp"}:
                continue
            age = (now - published).total_seconds() / 3600
            if age < -0.25 or age > max_age_hours:
                continue
            items.append({
                "source_id": source_id,
                "source_name": source.get("nombre", source_id),
                "publisher": news.get("publisher_original") or source.get("nombre", source_id),
                "title": title,
                "url": news.get("url", ""),
                "published_at": published.isoformat(),
                "article_published_at": news.get("article_published_at", ""),
                "age_hours": age,
                "date_trust": trust,
            })
    return items


def _cluster(items: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for item in items:
        best_index = None
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            score = _jaccard(item["title"], cluster[0]["title"])
            if score > best_score:
                best_score, best_index = score, index
        if best_index is not None and best_score >= 0.30:
            clusters[best_index].append(item)
        else:
            clusters.append([item])
    return clusters


def _status(score: int, signal_count: int, confidence: int, strong_threshold: int) -> str:
    if signal_count >= 2 and score >= strong_threshold and confidence >= 55:
        return "HALLAZGO FUERTE"
    if signal_count >= 2 and score >= max(48, strong_threshold - 12):
        return "HALLAZGO"
    return "CANDIDATO"


def generate(results: dict, ole_items: list[dict] | None, previous: list[dict] | None = None,
             max_items: int = 12, config: dict | None = None) -> list[dict]:
    config = config or {}
    max_age_hours = int(config.get("discovery_max_age_hours") or os.environ.get("DISCOVERY_MAX_AGE_HOURS", "12") or 12)
    strong_threshold = int(os.environ.get("DISCOVERY_MIN_SCORE", "62") or 62)
    try:
        from monitor_core import TODAS_FUENTES
        source_map = {source["id"]: source for source in TODAS_FUENTES}
    except Exception:
        source_map = {}

    normalized_ole = normalize_ole_items(ole_items)
    prev_by_id = {
        str(row.get("DiscoveryID") or row.get("discovery_id") or ""): row
        for row in previous or [] if str(row.get("DiscoveryID") or row.get("discovery_id") or "")
    }
    discoveries: list[dict] = []
    for cluster in _cluster(_collect(results, source_map, max_age_hours)):
        representative = min(cluster, key=lambda x: x.get("age_hours", 999))
        publishers = unique_strings([item.get("publisher", "") for item in cluster])
        match = best_ole_match(representative["title"], normalized_ole)
        score, value_ar, reasons, category, signal_count = _editorial_assessment(
            representative["title"], len(publishers), representative["age_hours"], float(match.get("score", 0) or 0)
        )
        # Una fuente excelente no convierte una noticia rutinaria en hallazgo.
        if signal_count == 0 or score < 38:
            continue

        confidence, confidence_reason = confidence_from_evidence(cluster)
        discovery_id = stable_id(normalize_text(representative["title"]), "d")
        previous_item = prev_by_id.get(discovery_id)
        is_new = previous_item is None
        try:
            previous_media = int(float(previous_item.get("Medios", 0))) if previous_item else 0
        except Exception:
            previous_media = 0
        grew = bool(previous_item) and len(publishers) > previous_media
        if previous_item and not grew:
            score = max(0, score - 8)
        elif grew:
            reasons.append(f"sumo {len(publishers) - previous_media} publisher(s) desde el corte anterior")

        status = _status(score, signal_count, confidence, strong_threshold)
        if status == "CANDIDATO" and score < 45:
            continue
        why = reasons[0] if reasons else "combina al menos dos señales de noticiabilidad"
        discoveries.append({
            "discovery_id": discovery_id,
            "title": representative["title"],
            "url": representative.get("url", ""),
            "category": category,
            "status": status,
            "score": score,
            "value_argentina": value_ar,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "editorial_signal_count": signal_count,
            "publishers": publishers,
            "media_count": len(publishers),
            "published_at": representative.get("published_at", ""),
            "article_published_at": representative.get("article_published_at", ""),
            "age_hours": representative.get("age_hours"),
            "date_trust": representative.get("date_trust", "publisher_timestamp"),
            "is_new": is_new,
            "grew": grew,
            "ole_status": "NO_CUBIERTO" if float(match.get("score", 0) or 0) < 0.38 else "REVISAR_COINCIDENCIA",
            "ole_match_title": match.get("title", ""),
            "ole_match_url": match.get("url", ""),
            "reason": ". ".join(unique_strings(reasons)),
            "why_it_matters": why,
            "suggested_angle": _suggest_angle(category),
            "suggested_format": _suggest_format(category),
            "evidence": cluster[:8],
            "notify": (is_new or grew) and status == "HALLAZGO FUERTE",
        })

    order = {"HALLAZGO FUERTE": 0, "HALLAZGO": 1, "CANDIDATO": 2}
    discoveries.sort(key=lambda item: (
        order.get(item["status"], 9), -item["score"], -item["value_argentina"],
        -item["confidence"], item.get("age_hours", 999),
    ))
    return discoveries[:max_items]


def _suggest_angle(category: str) -> str:
    return {
        "CONEXION ARGENTINA": "Explicar la conexion argentina y la consecuencia concreta, no traducir la noticia.",
        "OPORTUNIDAD VISUAL": "Partir de la escena o el video y agregar contexto verificable.",
        "DATO O RECORD": "Poner el dato en perspectiva con antecedentes y comparacion.",
        "HISTORIA RARA": "Construir personaje, conflicto, giro y consecuencia.",
        "HISTORIA HUMANA": "Contar la trayectoria y por que el desenlace excede el resultado.",
        "NEGOCIO / TECNOLOGIA": "Explicar el impacto deportivo y economico para el lector general.",
        "POLEMICA / CONFLICTO": "Separar hechos, posiciones y consecuencias verificadas.",
    }.get(category, "Verificar si existe un angulo concreto para el lector argentino.")


def _suggest_format(category: str) -> str:
    return {
        "CONEXION ARGENTINA": "PERFIL / EXPLICADOR",
        "OPORTUNIDAD VISUAL": "NOTA BREVE + VIDEO",
        "DATO O RECORD": "DATOS / COMPARATIVA",
        "HISTORIA RARA": "HISTORIA / COLOR",
        "HISTORIA HUMANA": "PERFIL / HISTORIA",
        "NEGOCIO / TECNOLOGIA": "EXPLICADOR",
        "POLEMICA / CONFLICTO": "CONTEXTO / CRONOLOGIA",
    }.get(category, "EXPLORACION")
