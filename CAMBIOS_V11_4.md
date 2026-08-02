# V11.4 - Ventanas temporales estrictas

## Problema corregido

`RESUMEN_4H` usaba la ventana solo como etiqueta y completaba hasta 40 filas con temas que seguian visibles en portadas, aunque fueran anteriores. `OLE_HOY` recibia tambien la memoria de cobertura de cinco dias, por lo que mezclaba notas actuales con publicaciones viejas.

## Cambios

- `RESUMEN_4H` exige actividad real dentro del corte vigente.
- Se toman fechas de las evidencias del cluster y de la propia noticia.
- Los titulos con una fecha explicita anterior, por ejemplo "miercoles 29 de julio", quedan excluidos.
- Si hubo menos de 30 temas en cuatro horas, se muestran menos: ya no se rellena con noticias viejas.
- Los temas sin fecha solo entran si son genuinamente nuevos respecto del corte anterior.
- `OLE_HOY` usa `/ultimas-noticias` y Google News fechado, no la memoria acumulada.
- `OLE_HOY` conserva solo publicaciones o detecciones del dia argentino actual.
- La portada de Ole y la memoria de cinco dias siguen utilizandose para comparar cobertura, pero no para la vista `Ole hoy`.
- `fetch_ultimas_ole` intenta recuperar el atributo `datetime` de las etiquetas `time`.
- La metrica de Streamlit pasa a llamarse `Notas de Ole hoy`.

## Validacion

La version supera 19 pruebas automaticas, incluidas pruebas que verifican:

- exclusion de noticias de mas de cuatro horas;
- exclusion de fechas viejas escritas en el titulo;
- exclusion de notas de Ole publicadas ayer;
- mantenimiento de notas publicadas hoy.
