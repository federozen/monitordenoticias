# Cambios V12 — frescura verificable, Olé completo y hallazgos editoriales

La V12 consolida las correcciones de las versiones anteriores. No busca mostrar más contenido a cualquier costo: prioriza que cada tema pueda auditarse y que una noticia antigua o reindexada no aparezca como novedad.

## 1. Resumen de cuatro horas con fecha verificable

Un tema entra al resumen solo cuando tiene una fecha confiable dentro de la ventana. La hora de Google News o el momento en que el monitor descubrió un enlace no prueban que el artículo sea nuevo.

Se excluyen especialmente:

- notas históricas o de archivo sin un dato nuevo;
- aniversarios reindexados;
- recuerdos de la final del Mundial sin información nueva;
- notas sobre hitos anteriores, como los 100 partidos de un entrenador, sin publicación directa reciente;
- contenidos con fecha ausente o dudosa.

La cantidad de temas puede ser inferior a 30 o 40. No se completa el informe con material antiguo.

## 2. Olé Hoy separado de la memoria histórica

El recolector de Olé:

- recorre páginas sucesivas de Últimas Noticias;
- extrae artículos desde HTML, datos estructurados y sitemap cuando están disponibles;
- verifica fechas en las notas individuales de forma concurrente;
- separa `PUBLICADA_HOY` de `ACTUALIZADA_HOY`;
- conserva el histórico solo para comparar cobertura, sin contarlo como actividad del día;
- marca la cobertura como completa, estimada o parcial según la evidencia real.

La pantalla muestra páginas revisadas, notas agregadas por sitemap y el rango fechado recuperado.

## 3. Hallazgos basados en noticiabilidad

La reputación de una fuente ya no suma puntos de interés. Se usa solamente para calcular confianza.

Para ser hallazgo firme, una historia debe combinar al menos dos señales editoriales, por ejemplo:

- rareza o sorpresa;
- conexión argentina;
- consecuencia deportiva;
- historia humana;
- dato o récord;
- componente visual;
- conflicto o polémica;
- negocio o tecnología deportiva.

Los resultados se separan en:

- `HALLAZGO FUERTE`;
- `HALLAZGO`;
- `CANDIDATO`.

Los candidatos pueden verse para explorar, pero no se incorporan automáticamente al resumen de cuatro horas ni generan oportunidades editoriales firmes.

## 4. Auditoría visible

Cada hallazgo conserva por separado:

- puntaje de noticiabilidad;
- valor para Argentina;
- confianza de la evidencia;
- motivo de confianza;
- cantidad de señales editoriales;
- estado del hallazgo.

Olé Hoy conserva el tipo de registro, la confianza de la fecha, la página y el origen de recuperación.

## 5. Compatibilidad

- Se mantiene el prefijo de hojas existente, por ejemplo `V9_`.
- No se requieren nuevos Secrets.
- Telegram y automatización permanecen apagados durante la prueba.
- El parte con Anthropic continúa siendo exclusivamente bajo demanda.

## Validación técnica

- Compilación de Python correcta.
- 32 pruebas automáticas superadas.
- Incluye pruebas contra historias históricas, timestamps de agregadores y hallazgos creados solo por prestigio de fuente.

La prueba definitiva del recorrido de Olé requiere una ejecución manual en GitHub, porque depende del HTML real que entregue el sitio en ese momento.
