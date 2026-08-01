# Monitor Deportivo V9 - asistente editorial proactivo

Esta version transforma el monitor en un asistente que trabaja sin esperar consultas. En cada ejecucion:

1. Recolecta y normaliza las fuentes.
2. Agrupa publicaciones sobre el mismo hecho.
3. Cuenta medios originales, no feeds de descubrimiento.
4. Compara el panorama con la cobertura de Ole.
5. Genera recomendaciones explicables.
6. Sugiere temas y formatos editoriales.
7. Construye un informe ejecutivo.
8. Envia alertas o resumentes por el bot de Telegram actual, si se habilita.
9. Guarda decisiones del editor para mejorar el sistema.

La IA generativa no se usa para cada titular. La curacion, el puntaje, las alertas y las oportunidades funcionan con reglas sin costo de API. La IA queda reservada para la produccion bajo demanda desde Streamlit y para experimentos opcionales.

## Arquitectura barata y online

```text
GitHub Actions
  -> recoleccion, agrupamiento y agentes
Google Sheets
  -> snapshot, recomendaciones, informes y feedback
Streamlit Community Cloud
  -> interfaz del editor
Telegram
  -> alertas e informes proactivos
Google Colab
  -> entrenamiento predictivo ocasional
```

## Un coordinador, varios modulos

No son bots separados. `editorial_agents/orchestrator.py` coordina cuatro modulos:

- `curator.py`: asigna accion, prioridad, confianza y evidencia.
- `opportunities.py`: deriva notas posibles, enfoques, esfuerzo y vigencia.
- `executive.py`: arma alertas e informes de apertura, horarios y cierre.
- `orchestrator.py`: evita repeticiones, guarda resultados y decide que enviar.

El sistema no publica ni modifica notas. Solo observa, ordena, recomienda y registra la decision humana.

## Reutilizar la planilla y Telegram actuales

Es la configuracion recomendada. La V9 usa el mismo `SHEET_ID`, la misma cuenta de servicio y el mismo bot, pero crea pestanas nuevas con el prefijo `V9_`:

- `V9_Noticias`
- `V9_Temas`
- `V9_Fuentes`
- `V9_Control`
- `V9_Feedback`
- `V9_Recomendaciones`
- `V9_Oportunidades`
- `V9_Informes`
- `V9_Avisos`
- `V9_AgentLog`

No borra las pestanas anteriores. Para usar otra planilla, se cambia solamente `SHEET_ID` y se comparte la nueva hoja con la misma cuenta de servicio.

## Archivos principales

| Archivo | Funcion |
|---|---|
| `vigia.py` | Motor programado que recolecta, crea snapshots y ejecuta el coordinador |
| `app.py` | Interfaz Streamlit liviana |
| `online_storage.py` | Persistencia en las pestanas `V9_` |
| `editorial_agents/curator.py` | Curacion y confianza |
| `editorial_agents/opportunities.py` | Temas para hacer |
| `editorial_agents/executive.py` | Alertas e informes |
| `editorial_agents/orchestrator.py` | Coordinacion, silencios y entregas |
| `monitor_core.py` | Fuentes, scraping, clustering y funciones heredadas |
| `colab/entrenar_modelo.ipynb` | Entrenamiento predictivo separado |

## Secrets de GitHub

Copiar desde el repositorio actual:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `SHEET_ID`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY` solo si se usara produccion con IA

## Variables de GitHub

Crear inicialmente:

| Variable | Valor inicial | Funcion |
|---|---|---|
| `AUTOMATION_ENABLED` | `false` | Evita ejecuciones automaticas durante la prueba |
| `SHEET_PREFIX` | `V9_` | Separa la nueva version |
| `TELEGRAM_MODE` | `full` | Habilita el transporte del bot; el contenido lo controla `AGENT_TELEGRAM_MODE` |
| `AGENT_ENABLED` | `true` | Genera recomendaciones en ejecuciones manuales |
| `AGENT_TELEGRAM_MODE` | `off` | Evita mensajes durante la prueba |
| `AGENT_HOURLY_DIGEST` | `true` | Habilita el informe horario al activar Telegram |
| `AGENT_OPENING_HOUR` | `8` | Hora argentina del informe de apertura |
| `AGENT_CLOSING_HOUR` | `23` | Hora argentina del cierre |
| `AGENT_MAX_ALERTS` | `4` | Maximo por mensaje |
| `AGENT_MAX_OPPORTUNITIES` | `6` | Maximo de ideas por corte |
| `AGENT_ALERT_SILENCE_HOURS` | `6` | Evita repetir la misma alerta |
| `LEGACY_MEMORY_WRITES_ENABLED` | `false` | Durante la prueba no toca Agenda, Snapshot ni Historial anteriores |

Valores de `AGENT_TELEGRAM_MODE`:

- `off`: no envia mensajes.
- `alerts`: solo alertas prioritarias.
- `digest`: solo informe ejecutivo.
- `full`: alertas e informes.

## Prueba segura

1. Subir el proyecto a un repositorio nuevo y privado.
2. Copiar Secrets y crear las variables con `AUTOMATION_ENABLED=false`, `TELEGRAM_MODE=full`, `AGENT_TELEGRAM_MODE=off` y `LEGACY_MEMORY_WRITES_ENABLED=false`.
3. Ejecutar manualmente `Monitor V9 - asistente editorial` desde GitHub Actions.
4. Revisar las nuevas pestanas `V9_`.
5. Desplegar `app.py` en una nueva aplicacion de Streamlit.
6. Verificar las paginas Ahora, Asistente, Explorar, Producir y Configuracion.
7. Cambiar `AGENT_TELEGRAM_MODE=digest` y ejecutar manualmente para probar un solo resumen.
8. Probar `alerts` y luego `full`.
9. Desactivar los workflows del repositorio viejo.
10. Cambiar `AUTOMATION_ENABLED=true` en el nuevo.
11. Mantener `LEGACY_MEMORY_WRITES_ENABLED=false` al principio; activarlo solo si se quiere que V9 continue escribiendo las pestanas historicas anteriores.

No activar simultaneamente los mensajes del repositorio anterior y de la V9, porque el mismo bot enviaria duplicados.

## Secrets de Streamlit

Usar el contenido de `.streamlit/secrets.example.toml` y completar:

```toml
GOOGLE_SERVICE_ACCOUNT_JSON = "{...}"
SHEET_ID = "ID_DE_LA_PLANILLA"
SHEET_PREFIX = "V9_"
ANTHROPIC_API_KEY = "opcional"
GITHUB_TOKEN = "token_para_disparar_actions"
GITHUB_REPO = "usuario/repositorio-v9"
GITHUB_WORKFLOW = "vigia.yml"
GITHUB_REF = "main"
```

`GITHUB_TOKEN` se usa solo para el boton Buscar noticias ahora. La app puede funcionar sin ese boton si no se configura.

## Telegram

El bot actual se conserva. La V9 puede enviar:

- alerta de publicar o actualizar;
- aviso de verificacion necesaria;
- resumen editorial horario;
- informe de apertura;
- informe de cierre;
- oportunidades de notas.

La hoja `V9_Avisos` evita repetir el mismo tema durante el periodo configurado.

## Parte predictiva

Streamlit solo carga un modelo ya entrenado. El entrenamiento se realiza en Colab y genera:

- `models/modelo_semaforo.joblib`
- `models/metricas.json`

Esto evita gastar recursos de Streamlit y permite revisar el modelo antes de publicarlo.

## Pruebas

Ejecutar:

```bash
python -m unittest discover -s tests -v
```

Tambien se ejecutan automaticamente con `.github/workflows/tests.yml`.

## Limitaciones importantes

- GitHub Actions no garantiza ejecucion al minuto exacto; siempre se conserva el ultimo snapshot valido.
- Las recomendaciones son ayudas editoriales, no confirmaciones periodisticas.
- Una fuente oficial mejora la confianza, pero el editor debe abrir y revisar la evidencia.
- La V9 no publica automaticamente ni envia push.
