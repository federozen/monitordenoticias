"""Carga e inferencia del semaforo predictivo sin entrenar dentro de Streamlit."""
from __future__ import annotations

import json
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "modelo_semaforo.joblib"
METRICS_PATH = Path(__file__).parent / "models" / "metricas_modelo.json"


def disponible() -> bool:
    return MODEL_PATH.exists()


def cargar_modelo():
    if not disponible():
        return None
    import joblib
    return joblib.load(MODEL_PATH)


def cargar_metricas() -> dict:
    if not METRICS_PATH.exists():
        return {}
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def predecir(pack: dict, titulo: str, seccion: str = "",
             en_panorama: bool = False, hora: str = "") -> dict:
    if pack.get("format") == "v8_pipeline":
        import pandas as pd
        hora_num = 0
        try:
            hora_num = int((hora or "0").split(":", 1)[0])
        except Exception:
            pass
        if 5 <= hora_num < 11:
            franja = "manana"
        elif 11 <= hora_num < 15:
            franja = "mediodia"
        elif 15 <= hora_num < 20:
            franja = "tarde"
        else:
            franja = "noche"
        frame = pd.DataFrame([{
            "titulo": titulo,
            "seccion": seccion or "sin_seccion",
            "franja": franja,
            "panorama": "si" if en_panorama else "no",
        }])
        pipeline = pack["pipeline"]
        probas = pipeline.predict_proba(frame)[0]
        clases = list(pipeline.classes_)
        orden = sorted(zip(clases, probas), key=lambda x: -x[1])
        empuja, frena = [], []
        if len(titulo) >= 45:
            empuja.append("titulo descriptivo")
        elif len(titulo) < 25:
            frena.append("titulo muy corto")
        if any(ch.isdigit() for ch in titulo):
            empuja.append("dato concreto")
        if en_panorama:
            empuja.append("tema presente en el panorama")
        if not seccion:
            frena.append("sin sección informada")
        return {"clase": orden[0][0], "probas": orden,
                "empuja": empuja[:4], "frena": frena[:3]}

    from monitor_core import predecir_semaforo
    return predecir_semaforo(pack, titulo, seccion, en_panorama, hora)
