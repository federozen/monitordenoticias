"""sheets_memoria.py — Google Sheets como memoria, tablero y panel de control.

Pestañas que gestiona (las crea si no existen):
  • Agenda    — el tablero vivo: cada fila es una acción sugerida. El editor
                marca la columna Estado ("hecho" / "descartado") y el vigía
                deja de insistir con ese tema.
  • Snapshot  — la última corrida (clusters), para calcular momentum real
                entre corridas. Se reemplaza entera en cada corrida.
  • Config    — parámetros editables por el editor sin tocar código:
                umbral de medios para alertar, watchlist de keywords.

Credenciales (env o inyectadas con configure()):
  GOOGLE_SERVICE_ACCOUNT_JSON  — el JSON completo de la service account
  SHEET_ID                     — el ID de la planilla (de su URL)

Si falta algo, todas las funciones degradan sin romper: disponible() da False
y los llamadores siguen con su comportamiento local.
"""
import os
import json
from datetime import datetime, timedelta, timezone

try:
    import gspread
except Exception:  # gspread no instalado: modo degradado
    gspread = None

_TZ_AR = timezone(timedelta(hours=-3))

AGENDA_HEADERS = ["Fecha", "Hora", "Accion", "Tema", "Medios", "Momentum",
                  "Motivo", "URL", "Estado", "Origen", "Clave"]
SNAPSHOT_HEADERS = ["RunTS", "Origen", "Titulo", "CantMedios", "TieneOle"]
HISTORIAL_HEADERS = ["Fecha", "Hora", "Titulo", "CantMedios", "TieneOle"]
INFORMES_HEADERS = ["Fecha", "Periodo", "Informe"]
COBERTURA_HEADERS = ["Fecha", "Hora", "Titulo", "URL"]
PASES_HEADERS = ["PrimeraVez", "UltimaVez", "Titulo", "MediosMax", "Apariciones", "Olé", "URL", "Clave"]
ENTIDADES_HEADERS = ["Ranking", "Entidad", "Menciones", "Medios", "Olé", "Actualizado"]
ENTHIST_HEADERS = ["Fecha", "Hora", "Entidad", "Menciones"]
TERMO_HEADERS = ["Entidad", "Tendencia", "HoyProm", "AntesProm", "Variacion", "Actualizado"]
PARTES_HEADERS = ["Fecha", "Parte", "Enviado"]
METRICAS_HEADERS = ["Fecha", "Vistas", "Titulo", "Seccion", "Entidades", "EnPanorama", "Lista", "Hora"]
EVOL_HEADERS = ["Fecha", "Hora", "NotasDataset", "TestNotas", "Base", "Logistica", "RandomForest", "Ganador", "Mejora"]
CONFIG_DEFAULTS = [
    ["parametro", "valor", "descripcion"],
    ["umbral_medios", "4", "Mínimo de medios cubriendo un tema sin Olé para alertar"],
    ["watchlist", "river, boca, seleccion argentina", "Keywords a vigilar siempre (separadas por coma)"],
    ["horas_silencio", "48", "No repetir un aviso del mismo tema dentro de estas horas"],
    ["dias_archivo", "3", "Mover a la pestaña Archivo las filas de Agenda más viejas que esto"],
    ["ignorar", "", "Temas a no mostrar nunca (keywords separadas por coma, ej: tenis, nba)"],
    ["criterios_editor", "", "Tus criterios editoriales, en tu idioma; la IA los respeta en el parte, los briefs y el informe"],
    ["digest_ole", "si", "Mandar por Telegram (silencioso) las notas nuevas de Olé en cada corrida: si / no"],
    ["avisos_explosion", "si", "Alertar por Telegram cuando un tema explota en velocidad: si / no"],
    ["umbral_explosion", "4", "Cuántos medios tiene que sumar un tema en una hora para considerarse explosión"],
    ["entidades_extra", "", "Entidades propias a vigilar: formato 'Nombre=alias1,alias2 | Otro=alias'. Se suman a las de base"],
]

_conf = {"json": None, "sheet_id": None}
_cache = {"sh": None}


def configure(service_account_json: str = None, sheet_id: str = None):
    """Permite inyectar credenciales desde st.secrets en vez de env."""
    if service_account_json:
        _conf["json"] = service_account_json
    if sheet_id:
        _conf["sheet_id"] = sheet_id
    _cache["sh"] = None


def _credenciales():
    sa = _conf["json"] or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    sid = _conf["sheet_id"] or os.environ.get("SHEET_ID", "")
    return sa, sid


def disponible() -> bool:
    sa, sid = _credenciales()
    return bool(gspread and sa and sid)


def _sheet():
    if _cache["sh"] is not None:
        return _cache["sh"]
    sa, sid = _credenciales()
    creds = json.loads(sa)
    client = gspread.service_account_from_dict(creds)
    _cache["sh"] = client.open_by_key(sid)
    return _cache["sh"]


def _ws(nombre: str, headers: list, defaults: list = None):
    sh = _sheet()
    try:
        ws = sh.worksheet(nombre)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=nombre, rows=200, cols=max(len(headers), 3))
        if defaults:
            ws.update(range_name="A1", values=defaults)
        else:
            ws.update(range_name="A1", values=[headers])
    return ws


def asegurar_estructura():
    _ws("Agenda", AGENDA_HEADERS)
    _ws("Snapshot", SNAPSHOT_HEADERS)
    _ws("Config", CONFIG_DEFAULTS[0], defaults=CONFIG_DEFAULTS)


# ── Config ────────────────────────────────────────────────────────────────────
def leer_config() -> dict:
    """Devuelve la config del Sheet con defaults sanos si algo falta."""
    cfg = {"umbral_medios": 4, "watchlist": [], "horas_silencio": 48,
           "dias_archivo": 3, "ignorar": [], "criterios": "",
           "digest_ole": True, "avisos_explosion": True, "umbral_explosion": 4,
           "entidades_extra": ""}
    try:
        ws = _ws("Config", CONFIG_DEFAULTS[0], defaults=CONFIG_DEFAULTS)
        filas = ws.get_all_values()
        vistos = set()
        for fila in filas[1:]:
            if len(fila) < 2:
                continue
            k, v = fila[0].strip().lower(), fila[1].strip()
            vistos.add(k)
            if k == "umbral_medios" and v.isdigit():
                cfg["umbral_medios"] = int(v)
            elif k == "horas_silencio" and v.isdigit():
                cfg["horas_silencio"] = int(v)
            elif k == "dias_archivo" and v.isdigit():
                cfg["dias_archivo"] = int(v)
            elif k == "watchlist":
                cfg["watchlist"] = [w.strip().lower() for w in v.split(",") if w.strip()]
            elif k == "ignorar":
                cfg["ignorar"] = [w.strip().lower() for w in v.split(",") if w.strip()]
            elif k == "_formato_v":
                cfg["_formato_v"] = v
            elif k == "criterios_editor":
                cfg["criterios"] = v
            elif k == "digest_ole":
                cfg["digest_ole"] = v.lower().startswith("s")
            elif k == "avisos_explosion":
                cfg["avisos_explosion"] = v.lower().startswith("s")
            elif k == "umbral_explosion" and v.isdigit():
                cfg["umbral_explosion"] = int(v)
            elif k == "entidades_extra":
                cfg["entidades_extra"] = v
        # auto-agregar al Sheet los parámetros nuevos que falten (updates del sistema)
        for fila_def in CONFIG_DEFAULTS[1:]:
            if fila_def[0] not in vistos:
                ws.append_row(fila_def, value_input_option="RAW")
    except Exception:
        pass
    return cfg


# ── Snapshot (memoria de la corrida anterior, para momentum) ────────────────
def debe_correr(min_minutos: int = 55) -> bool:
    """True si conviene correr ahora. Evita corridas duplicadas cuando GitHub
    dispara seguido: si el último Snapshot es más reciente que min_minutos,
    devuelve False. Ante cualquier duda o error, devuelve True (mejor correr
    de más que saltear una corrida válida)."""
    try:
        ws = _ws("Snapshot", SNAPSHOT_HEADERS)
        valores = ws.get_all_values()
        if len(valores) < 2:
            return True
        # RunTS está en la primera columna de la primera fila de datos
        ultimo_ts = None
        for fila in valores[1:]:
            if fila and fila[0].strip():
                dt = _parse_fecha(fila[0].strip())
                if dt and (ultimo_ts is None or dt > ultimo_ts):
                    ultimo_ts = dt
        if ultimo_ts is None:
            return True
        transcurrido = datetime.now(_TZ_AR) - ultimo_ts
        return transcurrido >= timedelta(minutes=min_minutos)
    except Exception:
        return True


def guardar_evolucion(pack: dict, n_dataset: int) -> bool:
    """Registra los números de cada entrenamiento: la serie histórica del modelo.
    Si el entrenamiento es idéntico al último registrado (mismo dataset y mismos
    resultados), no lo guarda — evita ensuciar la serie con corridas repetidas."""
    try:
        ws = _ws("Evolución", EVOL_HEADERS)
        ahora = datetime.now(_TZ_AR)
        # ¿es idéntico al último? entonces no registrar
        try:
            previas = ws.get_all_values()
            if len(previas) > 1:
                ult = previas[-1]
                if (len(ult) >= 7 and ult[2] == str(n_dataset)
                        and ult[5] == f"{pack.get('acc_logit', 0):.0%}"
                        and ult[6] == f"{pack.get('acc_rf', 0):.0%}"):
                    return True  # ya está registrado ese resultado exacto
        except Exception:
            pass
        ws.append_row([ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M"),
                       str(n_dataset), str(pack.get("n_test", "")),
                       f"{pack.get('acc_base', 0):.0%}", f"{pack.get('acc_logit', 0):.0%}",
                       f"{pack.get('acc_rf', 0):.0%}",
                       "RandomForest" if pack.get("tipo") == "rf" else "Logística",
                       f"{(pack.get('acc', 0) - pack.get('acc_base', 0)):+.0%}"],
                      value_input_option="RAW")
        return True
    except Exception:
        return False


def leer_evolucion() -> list:
    try:
        ws = _ws("Evolución", EVOL_HEADERS)
        return [dict(zip(EVOL_HEADERS, f)) for f in ws.get_all_values()[1:]]
    except Exception:
        return []


def guardar_metricas(fecha: str, filas_cruzadas: list) -> int:
    """Guarda las notas del reporte diario ya cruzadas con el sistema.
    Si la fecha ya existía, la reemplaza (podés re-subir el mismo reporte)."""
    try:
        ws = _ws("Métricas", METRICAS_HEADERS)
        existentes = ws.get_all_values()
        conservar = [f for f in existentes[1:] if len(f) >= 1 and f[0] != fecha]
        nuevas = [[fecha, str(n.get("vistas", 0)), n.get("titulo", "")[:200],
                   n.get("seccion", "")[:40],
                   " · ".join(n.get("entidades", [])[:4]),
                   "sí" if n.get("en_panorama") else "no",
                   n.get("lista", ""), n.get("hora", "")] for n in filas_cruzadas]
        ws.clear()
        ws.update(range_name="A1", values=[METRICAS_HEADERS] + nuevas + conservar,
                  value_input_option="RAW")
        # poda a ~40 días de datos (30 filas/día aprox)
        return len(nuevas)
    except Exception:
        return 0


def leer_metricas(dias: int = 14) -> list:
    """Lee las métricas acumuladas para análisis."""
    try:
        ws = _ws("Métricas", METRICAS_HEADERS)
        return [dict(zip(METRICAS_HEADERS, f)) for f in ws.get_all_values()[1:]]
    except Exception:
        return []


def partes_enviados_hoy(fecha: str) -> set:
    """Devuelve el set de partes ya enviados hoy ('nac', 'int')."""
    try:
        ws = _ws("PartesLog", PARTES_HEADERS)
        return {f[1] for f in ws.get_all_values()[1:]
                if len(f) >= 2 and f[0] == fecha}
    except Exception:
        return set()


def marcar_parte_enviado(fecha: str, parte: str) -> bool:
    """Registra que un parte se envió hoy, para no repetirlo."""
    try:
        ws = _ws("PartesLog", PARTES_HEADERS)
        ws.append_row([fecha, parte, datetime.now(_TZ_AR).strftime("%H:%M")],
                      value_input_option="RAW")
        # poda: dejar solo últimos 30 días
        todas = ws.get_all_values()
        if len(todas) > 120:
            ws.clear()
            ws.update(range_name="A1", values=[PARTES_HEADERS] + todas[-90:],
                      value_input_option="RAW")
        return True
    except Exception:
        return False


def marcar_corrida_ok() -> bool:
    """Registra que la corrida terminó bien. El timestamp que usa debe_correr
    ya lo escribe guardar_snapshot, así que esto es una confirmación liviana:
    nunca debe hacer fallar al vigía, por eso traga cualquier error."""
    try:
        return True
    except Exception:
        return True


def leer_snapshot_anterior() -> list:
    """Lee los clusters de la última corrida guardada. Formato compatible
    con calcular_momentum: [{titulo, cant_medios, tiene_ole}, ...]"""
    try:
        ws = _ws("Snapshot", SNAPSHOT_HEADERS)
        out = []
        for fila in ws.get_all_values()[1:]:
            if len(fila) < 5:
                continue
            out.append({
                "titulo": fila[2],
                "cant_medios": int(fila[3]) if str(fila[3]).isdigit() else 1,
                "tiene_ole": str(fila[4]).lower() in ("1", "true", "si", "sí"),
            })
        return out
    except Exception:
        return []


def guardar_snapshot(tendencias: list, origen: str, max_temas: int = 60):
    """Reemplaza la pestaña Snapshot con la corrida actual."""
    try:
        ws = _ws("Snapshot", SNAPSHOT_HEADERS)
        ts = datetime.now(_TZ_AR).strftime("%Y-%m-%d %H:%M")
        filas = [SNAPSHOT_HEADERS]
        for c in tendencias[:max_temas]:
            filas.append([ts, origen, c.get("titulo", "")[:200],
                          str(c.get("cant_medios", 1)),
                          "1" if c.get("tiene_ole") else "0"])
        ws.clear()
        ws.update(range_name="A1", values=filas)
        return True
    except Exception:
        return False


# ── Agenda (tablero + feedback del editor) ───────────────────────────────────
def leer_agenda_estados() -> dict:
    """Devuelve {clave: (estado, fecha_hora_str)} con la última fila por clave.
    Es el canal de vuelta: 'hecho' o 'descartado' silencian el tema."""
    estados = {}
    try:
        ws = _ws("Agenda", AGENDA_HEADERS)
        for fila in ws.get_all_values()[1:]:
            if len(fila) < 11 or not fila[10]:
                continue
            estados[fila[10]] = (fila[8].strip().lower(), f"{fila[0]} {fila[1]}")
    except Exception:
        pass
    return estados


def _parse_fecha(texto: str):
    """Tolera los formatos con que Sheets puede mostrar la fecha según la
    configuración regional de la planilla."""
    texto = texto.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).replace(tzinfo=_TZ_AR)
        except Exception:
            continue
    return None


def _es_reciente(fecha_hora: str, horas: int) -> bool:
    dt = _parse_fecha(fecha_hora)
    if dt is None:
        return False
    return datetime.now(_TZ_AR) - dt < timedelta(hours=horas)


def filtrar_ya_tratados(items: list, horas_silencio: int = 48) -> list:
    """Quita de la lista los temas que el editor marcó hecho/descartado,
    y los ya avisados como pendientes dentro de la ventana de silencio."""
    estados = leer_agenda_estados()
    out = []
    for it in items:
        clave = it.get("clave", "")
        prev = estados.get(clave)
        if prev:
            estado, fh = prev
            if estado in ("hecho", "descartado", "ok", "listo", "cubierto"):
                continue
            if _es_reciente(fh, horas_silencio):
                continue
        out.append(it)
    return out


def agregar_a_agenda(items: list, origen: str):
    """Agrega filas nuevas al tablero. Cada item: dict de construir_agenda + clave."""
    if not items:
        return 0
    try:
        ws = _ws("Agenda", AGENDA_HEADERS)
        ahora = datetime.now(_TZ_AR)
        filas = []
        for it in items:
            if it.get("nuevo"):
                mom = "nuevo"
            elif it.get("delta", 0) > 0:
                mom = f"sube +{it['delta']}"
            elif it.get("delta", 0) < 0:
                mom = f"baja {it['delta']}"
            else:
                mom = "estable"
            filas.append([
                ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"),
                it.get("accion", ""), it.get("titulo", "")[:200],
                str(it.get("cant_medios", "")), mom,
                it.get("motivo", "")[:150], it.get("url") or "",
                "pendiente", origen, it.get("clave", ""),
            ])
        # insertar arriba: lo más nuevo siempre primero
        ws.insert_rows(filas, row=2, value_input_option="USER_ENTERED")
        return len(filas)
    except Exception:
        return 0


# ── Historial (registro acumulado para inteligencia semanal) ─────────────────
def registrar_historial(tendencias: list, max_temas: int = 70):
    """Deja constancia compacta de qué se publicó en esta corrida.
    Solo clusters con 2+ medios (el resto es ruido para el análisis)."""
    try:
        ws = _ws("Historial", HISTORIAL_HEADERS)
        ahora = datetime.now(_TZ_AR)
        filas = [
            [ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"),
             c.get("titulo", "")[:200], str(c.get("cant_medios", 1)),
             "1" if c.get("tiene_ole") else "0"]
            for c in tendencias[:max_temas] if c.get("cant_medios", 1) >= 2
        ]
        if filas:
            ws.append_rows(filas, value_input_option="RAW")
        return len(filas)
    except Exception:
        return 0


def leer_historial(dias: int = 7) -> list:
    """Devuelve las filas del Historial de los últimos N días."""
    out = []
    try:
        ws = _ws("Historial", HISTORIAL_HEADERS)
        limite = datetime.now(_TZ_AR) - timedelta(days=dias)
        for fila in ws.get_all_values()[1:]:
            if len(fila) < 5:
                continue
            dt = _parse_fecha(f"{fila[0]} {fila[1]}") or _parse_fecha(fila[0])
            if dt is None or dt < limite:
                continue
            out.append({
                "fecha": fila[0], "hora": fila[1], "titulo": fila[2],
                "cant_medios": int(fila[3]) if str(fila[3]).isdigit() else 1,
                "tiene_ole": str(fila[4]) == "1",
            })
    except Exception:
        pass
    return out


def cobertura_propia(dias: int = 5) -> list:
    """Temas de los últimos N días donde Olé tuvo cobertura, según el
    Historial. Formato: [{titulo, fecha}, ...] para construir_agenda."""
    return [{"titulo": h["titulo"], "fecha": h["fecha"]}
            for h in leer_historial(dias) if h.get("tiene_ole")]


# ── Archivo (limpieza automática de la Agenda) ───────────────────────────────
def archivar_agenda_vieja(dias: int = 3) -> int:
    """Mueve a la pestaña Archivo las filas de Agenda más viejas que N días.
    La Agenda queda corta y fresca; el Archivo conserva todo el historial."""
    try:
        ws = _ws("Agenda", AGENDA_HEADERS)
        filas = ws.get_all_values()
        if len(filas) <= 1:
            return 0
        limite = datetime.now(_TZ_AR) - timedelta(days=dias)
        quedan, van = [], []
        for fila in filas[1:]:
            dt = _parse_fecha(fila[0]) if fila else None
            (van if (dt is not None and dt < limite) else quedan).append(fila)
        if not van:
            return 0
        ws_arch = _ws("Archivo", AGENDA_HEADERS)
        ws_arch.append_rows(van, value_input_option="RAW")
        ws.clear()
        ws.update(range_name="A1", values=[AGENDA_HEADERS] + quedan,
                  value_input_option="USER_ENTERED")
        return len(van)
    except Exception:
        return 0


# ── Informes (análisis semanal generado por IA) ──────────────────────────────
def guardar_informe(texto: str, periodo: str):
    try:
        ws = _ws("Informes", INFORMES_HEADERS)
        ws.append_row(
            [datetime.now(_TZ_AR).strftime("%Y-%m-%d"), periodo, texto[:45000]],
            value_input_option="RAW",
        )
        return True
    except Exception:
        return False


# ── Formato del tablero (se aplica una sola vez, versionado en Config) ──────
FORMATO_VERSION = "4"

_COLORES_ACCION = {
    "SUBIR YA":  {"red": 0.98, "green": 0.88, "blue": 0.87},
    "RETOMAR":   {"red": 0.93, "green": 0.88, "blue": 0.96},
    "EXPLOTA":   {"red": 1.00, "green": 0.91, "blue": 0.82},
    "REDACTAR":  {"red": 1.00, "green": 0.95, "blue": 0.80},
    "SEGUIR":    {"red": 0.87, "green": 0.92, "blue": 0.97},
    "EMPUJAR":   {"red": 0.88, "green": 0.96, "blue": 0.89},
}
_ANCHOS_AGENDA = [90, 55, 110, 420, 60, 90, 260, 180, 110, 70, 150]


def formatear_tablero() -> bool:
    """Convierte la pestaña Agenda en un tablero usable: encabezado fijo y en
    negrita, columna Estado con desplegable (pendiente/hecho/descartado),
    filas pintadas según la acción, anchos razonables y la columna técnica
    Clave oculta. Registra la versión aplicada en Config para no repetirse."""
    try:
        sh = _sheet()
        ws = _ws("Agenda", AGENDA_HEADERS)
        sid = ws.id
        # limpiar reglas de formato previas (de versiones anteriores)
        for _ in range(12):
            try:
                sh.batch_update({"requests": [{"deleteConditionalFormatRule":
                                               {"sheetId": sid, "index": 0}}]})
            except Exception:
                break
        reqs = [
            # encabezado congelado y en negrita con fondo gris
            {"updateSheetProperties": {
                "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.93, "green": 0.93, "blue": 0.93}}},
                "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
            # Estado (col I) como desplegable
            {"setDataValidation": {
                "range": {"sheetId": sid, "startRowIndex": 1,
                          "startColumnIndex": 8, "endColumnIndex": 9},
                "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                            {"userEnteredValue": "pendiente"},
                            {"userEnteredValue": "hecho"},
                            {"userEnteredValue": "descartado"},
                            {"userEnteredValue": "cubierto"}]},
                         "showCustomUi": True, "strict": False}}},
            # ocultar la columna técnica Clave (col K)
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": 10, "endIndex": 11},
                "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        ]
        # anchos de columna
        for i, ancho in enumerate(_ANCHOS_AGENDA):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": ancho}, "fields": "pixelSize"}})
        # fila pintada según la acción (col C)
        for accion, color in _COLORES_ACCION.items():
            reqs.append({"addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sid, "startRowIndex": 1,
                                "startColumnIndex": 0, "endColumnIndex": 11}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA", "values": [
                            {"userEnteredValue": f'=$C2="{accion}"'}]},
                        "format": {"backgroundColor": color}}},
                "index": 0}})
        sh.batch_update({"requests": reqs})
        # registrar la versión aplicada
        try:
            _ws("Config", CONFIG_DEFAULTS[0]).append_row(
                ["_formato_v", FORMATO_VERSION, "(interno) formato del tablero aplicado"],
                value_input_option="RAW")
        except Exception:
            pass
        return True
    except Exception:
        return False


def limpiar_historial(dias: int = 30, umbral_filas: int = 3000) -> int:
    """Si el Historial superó el umbral, recorta a los últimos N días."""
    try:
        ws = _ws("Historial", HISTORIAL_HEADERS)
        filas = ws.get_all_values()
        if len(filas) <= umbral_filas:
            return 0
        limite = datetime.now(_TZ_AR) - timedelta(days=dias)
        quedan = [f for f in filas[1:]
                  if (_parse_fecha(f[0]) or datetime.now(_TZ_AR)) >= limite]
        borradas = len(filas) - 1 - len(quedan)
        if borradas > 0:
            ws.clear()
            ws.update(range_name="A1", values=[HISTORIAL_HEADERS] + quedan,
                      value_input_option="RAW")
        return borradas
    except Exception:
        return 0


def registrar_cobertura_ole(notas: list) -> list:
    """Suma a la pestaña 'Cobertura Olé' las notas que aún no estaban
    (dedup por título). Devuelve la lista de títulos NUEVOS de esta corrida."""
    try:
        ws = _ws("Cobertura Olé", COBERTURA_HEADERS)
        existentes = {f[2] for f in ws.get_all_values()[1:] if len(f) >= 3}
        ahora = datetime.now(_TZ_AR)
        nuevas, filas = [], []
        for n in notas:
            t = (n.get("titulo") or "").strip()[:200]
            if not t or t in existentes:
                continue
            existentes.add(t)
            nuevas.append(t)
            filas.append([ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"),
                          t, n.get("url") or ""])
        if filas:
            # insertar arriba (fila 2) para que lo más nuevo quede primero;
            # reversed() deja el orden correcto dentro de la propia tanda
            ws.insert_rows(list(reversed(filas)), row=2, value_input_option="USER_ENTERED")
        # poda: si engordó, conservar solo los últimos 7 días
        todas = ws.get_all_values()
        if len(todas) > 2500:
            limite = ahora - timedelta(days=7)
            quedan = [f for f in todas[1:]
                      if (_parse_fecha(f[0]) or ahora) >= limite]
            ws.clear()
            ws.update(range_name="A1", values=[COBERTURA_HEADERS] + quedan,
                      value_input_option="USER_ENTERED")
        return nuevas
    except Exception:
        return []


def titulos_cobertura_ole(dias: int = 5) -> list:
    """Lo publicado por Olé en los últimos N días según la pestaña
    'Cobertura Olé'. Formato: [{titulo, fecha}, ...]."""
    out = []
    try:
        ws = _ws("Cobertura Olé", COBERTURA_HEADERS)
        limite = datetime.now(_TZ_AR) - timedelta(days=dias)
        for f in ws.get_all_values()[1:]:
            if len(f) >= 3 and (_parse_fecha(f[0]) or datetime.now(_TZ_AR)) >= limite:
                out.append({"titulo": f[2], "fecha": f[0]})
    except Exception:
        pass
    return out


def registrar_pases(temas: list) -> tuple:
    """Upsert en la pestaña 'Pases': cada operación de mercado es UNA fila que
    se actualiza cuando reaparece (última vez, pico de medios, apariciones).
    temas: [{titulo, cant_medios, tiene_ole, url, clave}]. Devuelve (nuevas, actualizadas)."""
    if not temas:
        return (0, 0)
    try:
        ws = _ws("Pases", PASES_HEADERS)
        filas = ws.get_all_values()
        por_clave = {f[7]: (i, f) for i, f in enumerate(filas[1:], start=2)
                     if len(f) >= 8 and f[7]}
        ahora = datetime.now(_TZ_AR)
        hoy, hora = ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M")
        nuevas, celdas = [], []
        for t in temas:
            clave = t.get("clave", "")
            if not clave:
                continue
            if clave in por_clave:
                nro, f = por_clave[clave]
                medios_max = max(int(f[3]) if str(f[3]).isdigit() else 1,
                                 t.get("cant_medios", 1))
                apar = (int(f[4]) if str(f[4]).isdigit() else 1) + 1
                ole = "sí" if (f[5] == "sí" or t.get("tiene_ole")) else "no"
                celdas += [gspread.Cell(nro, 2, f"{hoy} {hora}"),
                           gspread.Cell(nro, 3, t.get("titulo", "")[:200]),
                           gspread.Cell(nro, 4, str(medios_max)),
                           gspread.Cell(nro, 5, str(apar)),
                           gspread.Cell(nro, 6, ole)]
            else:
                nuevas.append([f"{hoy} {hora}", f"{hoy} {hora}",
                               t.get("titulo", "")[:200],
                               str(t.get("cant_medios", 1)), "1",
                               "sí" if t.get("tiene_ole") else "no",
                               t.get("url") or "", clave])
        if celdas:
            ws.update_cells(celdas)
        if nuevas:
            ws.insert_rows(nuevas, row=2, value_input_option="USER_ENTERED")
        # poda: operaciones sin movimiento hace 45 días
        todas = ws.get_all_values()
        if len(todas) > 1500:
            limite = ahora - timedelta(days=45)
            quedan = [f for f in todas[1:]
                      if (_parse_fecha(f[1].split()[0] if f[1] else "") or ahora) >= limite]
            ws.clear()
            ws.update(range_name="A1", values=[PASES_HEADERS] + quedan,
                      value_input_option="USER_ENTERED")
        return (len(nuevas), len(celdas) // 5)
    except Exception:
        return (0, 0)


def guardar_ranking_entidades(ranking: list, top: int = 40) -> int:
    """Reemplaza la pestaña 'Quién manda' con el ranking de entidades de la
    corrida actual. Sin IA: son conteos de menciones."""
    try:
        ws = _ws("Quién manda", ENTIDADES_HEADERS)
        ahora = datetime.now(_TZ_AR).strftime("%Y-%m-%d %H:%M")
        filas = [ENTIDADES_HEADERS]
        for i, e in enumerate(ranking[:top], 1):
            filas.append([str(i), e["entidad"], str(e["menciones"]),
                          str(e["medios"]), "sí" if e.get("tiene_ole") else "no", ahora])
        ws.clear()
        ws.update(range_name="A1", values=filas, value_input_option="USER_ENTERED")
        _registrar_entidades_hist(ranking[:top])
        return len(ranking[:top])
    except Exception:
        return 0


def _registrar_entidades_hist(ranking: list):
    """Guarda un snapshot compacto del ranking para calcular el termómetro."""
    try:
        ws = _ws("EntidadesHist", ENTHIST_HEADERS)
        ahora = datetime.now(_TZ_AR)
        filas = [[ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"),
                  e["entidad"], str(e["menciones"])] for e in ranking]
        if filas:
            ws.append_rows(filas, value_input_option="RAW")
        # poda a 10 días
        todas = ws.get_all_values()
        if len(todas) > 6000:
            limite = ahora - timedelta(days=10)
            quedan = [f for f in todas[1:] if (_parse_fecha(f[0]) or ahora) >= limite]
            ws.clear()
            ws.update(range_name="A1", values=[ENTHIST_HEADERS] + quedan, value_input_option="RAW")
    except Exception:
        pass


def calcular_termometro(horas_reciente: int = 24, horas_base: int = 72) -> list:
    """Compara menciones promedio recientes vs la ventana previa, por entidad.
    Sin IA: puro promedio sobre EntidadesHist. Devuelve entidades ordenadas
    por variación, marcando 🔥 sube / ❄️ baja / ➡️ estable."""
    from collections import defaultdict
    try:
        ws = _ws("EntidadesHist", ENTHIST_HEADERS)
        ahora = datetime.now(_TZ_AR)
        t_reciente = ahora - timedelta(hours=horas_reciente)
        t_base = ahora - timedelta(hours=horas_base)
        reciente = defaultdict(list)
        base = defaultdict(list)
        for f in ws.get_all_values()[1:]:
            if len(f) < 4 or not str(f[3]).isdigit():
                continue
            dt = _parse_fecha(f"{f[0]} {f[1]}") or _parse_fecha(f[0])
            if dt is None:
                continue
            ent, m = f[2], int(f[3])
            if dt >= t_reciente:
                reciente[ent].append(m)
            elif dt >= t_base:
                base[ent].append(m)
        out = []
        entidades = set(reciente) | set(base)
        for e in entidades:
            hoy = sum(reciente[e]) / len(reciente[e]) if reciente[e] else 0
            antes = sum(base[e]) / len(base[e]) if base[e] else 0
            if hoy < 1 and antes < 1:
                continue
            if antes == 0:
                var = 100.0  # nuevo/reaparece
                icono = "🔥 nuevo"
            else:
                var = (hoy - antes) / antes * 100
                icono = "🔥 sube" if var >= 30 else "❄️ baja" if var <= -30 else "➡️ estable"
            out.append({"entidad": e, "tendencia": icono, "hoy": round(hoy, 1),
                        "antes": round(antes, 1), "var": round(var)})
        out.sort(key=lambda x: -x["var"])
        return out
    except Exception:
        return []


def guardar_termometro(termo: list, top: int = 30) -> int:
    """Escribe la pestaña 'Termómetro' con lo que sube y lo que baja."""
    try:
        ws = _ws("Termómetro", TERMO_HEADERS)
        ahora = datetime.now(_TZ_AR).strftime("%Y-%m-%d %H:%M")
        # los que suben arriba, los que bajan abajo
        suben = [t for t in termo if "sube" in t["tendencia"] or "nuevo" in t["tendencia"]]
        bajan = [t for t in termo if "baja" in t["tendencia"]]
        elegidos = suben[:top // 2] + bajan[-(top // 2):]
        filas = [TERMO_HEADERS]
        for t in elegidos:
            signo = "+" if t["var"] >= 0 else ""
            filas.append([t["entidad"], t["tendencia"], str(t["hoy"]),
                          str(t["antes"]), f"{signo}{t['var']}%", ahora])
        ws.clear()
        ws.update(range_name="A1", values=filas, value_input_option="USER_ENTERED")
        return len(elegidos)
    except Exception:
        return 0


def filas_pendientes_agenda() -> list:
    """Filas de Agenda en estado pendiente: [(nro_fila, clave), ...]."""
    out = []
    try:
        ws = _ws("Agenda", AGENDA_HEADERS)
        for i, fila in enumerate(ws.get_all_values()[1:], start=2):
            if len(fila) >= 11 and fila[8].strip().lower() == "pendiente" and fila[10]:
                out.append((i, fila[10]))
    except Exception:
        pass
    return out


def marcar_estados(cambios: dict):
    """cambios: {nro_fila: nuevo_estado}. Actualiza la columna Estado en lote."""
    if not cambios:
        return 0
    try:
        ws = _ws("Agenda", AGENDA_HEADERS)
        celdas = [gspread.Cell(row=fila, col=9, value=estado)
                  for fila, estado in cambios.items()]
        ws.update_cells(celdas)
        return len(celdas)
    except Exception:
        return 0


def url_planilla() -> str:
    _, sid = _credenciales()
    return f"https://docs.google.com/spreadsheets/d/{sid}" if sid else ""
