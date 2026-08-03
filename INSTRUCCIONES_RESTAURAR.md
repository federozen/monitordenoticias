# Restaurar V11.6 en main y conservar V13 para pruebas

## 1. Crear la rama de respaldo

Desde la raiz del repositorio en GitHub:

1. Abrir el selector de rama que dice `main`.
2. Escribir `v13-pruebas`.
3. Elegir `Create branch: v13-pruebas from main`.
4. Volver a seleccionar la rama `main` antes de subir los archivos de este paquete.

## 2. Reemplazar archivos en main

### En la raiz

Subir y reemplazar:

- `app.py`
- `monitor_core.py`
- `online_storage.py`
- `vigia.py`

### Dentro de editorial_agents

Subir y reemplazar:

- `briefing.py`
- `desk.py`
- `discovery.py`
- `executive.py`
- `ole_today.py`
- `opportunities.py`
- `orchestrator.py`

### Dentro de tests

Subir y reemplazar:

- `test_agents.py`

### Workflows

Editar directamente desde GitHub:

- `.github/workflows/tests.yml`
- `.github/workflows/vigia.yml`

Copiar y pegar el contenido de los archivos incluidos en este paquete. No arrastrar la carpeta `.github`.

## 3. No borrar por ahora

Puede quedar `editorial_agents/freshness.py`. V11.6 no lo utiliza y no molesta. Se puede eliminar despues de validar la restauracion.

## 4. Validar

1. Esperar que `Tests V11` termine en verde.
2. Ejecutar manualmente `Monitor V11 - mesa editorial`.
3. Confirmar que no aparezca `asistente editorial fallo`.
4. En Streamlit: `Manage app` > `Reboot app` y luego recargar.
5. Mantener `AUTOMATION_ENABLED=false`, `TELEGRAM_MODE=off` y `AGENT_TELEGRAM_MODE=off`.
