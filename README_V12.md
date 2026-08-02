# Monitor Deportivo V12

La V12 es una mesa editorial online para un editor. Recolecta noticias con GitHub Actions, guarda el panorama en Google Sheets y lo muestra en Streamlit.

Su objetivo no es acumular titulares, sino responder:

- qué ocurrió en las últimas cuatro horas;
- qué cambió;
- qué publicó Olé hoy;
- qué falta o podría actualizarse;
- qué hallazgos internacionales tienen valor editorial real;
- qué evidencia sostiene cada recomendación.

## Principios

1. **Frescura verificable.** Google News descubre, pero no certifica la fecha de una nota.
2. **Olé Hoy no es el histórico.** Publicaciones y actualizaciones del día se separan de la memoria usada para comparar.
3. **Confianza no equivale a interés.** Una fuente prestigiosa puede sostener un dato, pero no convierte una noticia rutinaria en hallazgo.
4. **Menos es mejor que rellenar.** El resumen puede tener pocos temas si son los únicos verificables.
5. **IA paga solo bajo demanda.** El informe ampliado no se ejecuta automáticamente.

## Arquitectura

```text
Fuentes web
  -> GitHub Actions
  -> normalización, fechas, clusters y auditoría
  -> Google Sheets
  -> Streamlit
```

## Uso recomendado

- Abrir `Mesa editorial` para el corte gratuito.
- Revisar `Olé hoy` para recordar publicaciones y enfoques.
- Revisar `Hallazgos` separando firmes de candidatos.
- Marcar acciones como hecho, descartado o seguir.
- Generar el parte ampliado solo cuando haga falta.

## Puesta en marcha

Ver `ACTUALIZAR_A_V12.md` y `CAMBIOS_V12.md`.
