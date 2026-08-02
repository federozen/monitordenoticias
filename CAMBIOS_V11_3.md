# V11.3 - cortes confiables y Google News estabilizado

## Problema resuelto

Una corrida con 22 de 73 fuentes podía reemplazar un panorama completo por otro parcial y producir falsos cambios. Además, decenas de solicitudes simultáneas a Google News generaban respuestas 503 masivas.

## Cambios

- Evalúa la calidad de cada corte.
- Considera completo un corte cuando responde al menos el 60% de las fuentes y un mínimo de 35 fuentes.
- Si el corte es parcial:
  - conserva `V9_Noticias` y `V9_Temas` del último corte completo;
  - actualiza el estado de fuentes y el control;
  - combina las novedades recuperadas con el panorama anterior para el resumen editorial;
  - no interpreta la desaparición de fuentes como una novedad;
  - marca qué temas fueron conservados del panorama anterior.
- Streamlit muestra una advertencia visible cuando el corte es degradado.
- Google News se consulta de forma regulada, con intervalo mínimo y un reintento para errores 429/503.
- El número de hilos de scraping pasa a ser configurable.
- El log informa calidad, porcentaje, fuentes directas y Google News.

## Variables disponibles

- `MIN_HEALTHY_SOURCE_RATIO`, por defecto `0.60`.
- `MIN_HEALTHY_SOURCES`, por defecto `35`.
- `SCRAPE_MAX_WORKERS`, por defecto `5`.
- `GNEWS_MIN_INTERVAL_SECONDS`, por defecto `0.45`.
- `GNEWS_RETRY_ATTEMPTS`, por defecto `2`.

No es necesario crearlas: el workflow incluye valores predeterminados.
