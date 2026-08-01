# Migracion rapida a V9

## Etapa 1 - prueba sin riesgo

1. Crear un repositorio privado nuevo.
2. Subir todos los archivos de este proyecto.
3. Copiar los Secrets del repositorio actual.
4. Crear estas variables:
   - `AUTOMATION_ENABLED=false`
   - `SHEET_PREFIX=V9_`
   - `TELEGRAM_MODE=full`
   - `AGENT_ENABLED=true`
   - `AGENT_TELEGRAM_MODE=off`
   - `LEGACY_MEMORY_WRITES_ENABLED=false`
5. Ejecutar manualmente el workflow `Monitor V9 - asistente editorial`.
6. Confirmar que se crearon las pestanas `V9_` y que contienen datos.
7. Desplegar una app nueva en Streamlit usando `app.py`.

## Etapa 2 - prueba de Telegram

1. Poner `AGENT_TELEGRAM_MODE=digest`.
2. Ejecutar manualmente una vez.
3. Confirmar que llega un solo informe.
4. Probar `alerts`.
5. Finalmente usar `full`.

## Etapa 3 - reemplazo

1. Desactivar los workflows programados del repositorio anterior.
2. Cambiar `AUTOMATION_ENABLED=true` en la V9.
3. Mantener la V8 algunos dias como respaldo, sin automatizacion ni Telegram.

## Volver atras

Poner `AUTOMATION_ENABLED=false` en la V9 y reactivar el workflow anterior. Las pestanas `V9_` pueden conservarse; no interfieren con las anteriores.
