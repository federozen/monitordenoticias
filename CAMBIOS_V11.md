# Monitor Deportivo V11 — Mesa editorial

La V11 deja de presentar el monitor como una sucesión de tableros técnicos y agrega una mesa de edición única.

## Funciones nuevas

- Resumen gratuito de 30 a 40 temas, organizado en cortes de cuatro horas.
- Vista rápida con los diez imprescindibles y vista completa.
- Cola de acciones con estados: pendiente, en curso, hecho, descartado o seguir.
- Módulo **Olé Hoy** con línea de tiempo, agrupación por tema, enfoques cubiertos y aviso de posible sobrecobertura.
- Hoja de cobertura propia que vincula notas de Olé con novedades externas.
- Hallazgos internacionales y enlaces sociales en una vista editorial legible.
- Estado de fuentes traducido a categorías comprensibles y sugerencias de respaldo.
- Buzón social manual: permite pegar enlaces sin contratar APIs de redes.
- Parte editorial ampliado con Anthropic exclusivamente bajo demanda y con confirmación previa.
- El parte generado queda guardado; volver a abrirlo no consume IA.
- Historial automático: cuando cambia el corte de cuatro horas, el resumen anterior pasa a `HISTORIAL_4H`.

## Hojas editoriales nuevas

Con el prefijo actual (`V9_` salvo que se cambie):

- `V9_RESUMEN_4H`
- `V9_HISTORIAL_4H`
- `V9_ACCIONES`
- `V9_OLE_HOY`
- `V9_COBERTURA_OLE`
- `V9_HALLAZGOS`
- `V9_FUENTES_EDITOR`
- `V9_BUZON_SOCIAL`
- `V9_PARTES_IA`

Las hojas se formatean automáticamente con texto ajustado, filtros, encabezado congelado y columnas más anchas.

## Costos

La recolección, el resumen de cuatro horas, la memoria de Olé, las acciones, los hallazgos y el buzón social no usan Anthropic.

La IA se utiliza solamente cuando el editor abre **Mesa editorial → Parte ampliado**, confirma el gasto y pulsa el botón. Si no se pulsa, el costo de IA es cero.
