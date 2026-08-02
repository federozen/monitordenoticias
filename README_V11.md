# Monitor Deportivo V11

## Qué resuelve

La aplicación reúne en una sola mesa:

- qué pasó en las últimas cuatro horas;
- qué cambió desde el corte anterior;
- qué publicó Olé y con qué enfoques;
- qué notas podrían actualizarse;
- qué falta verificar;
- qué hallazgos internacionales vale la pena explorar;
- qué fuentes requieren atención;
- qué enlaces de redes enviaron manualmente los editores.

## Flujo

1. GitHub Actions recolecta y procesa las fuentes cada 30 minutos.
2. El sistema mantiene un resumen gratuito del corte de cuatro horas en curso.
3. Al comenzar un nuevo corte, archiva el resumen anterior.
4. Streamlit lee las hojas editoriales y permite gestionar acciones.
5. El informe con IA nunca se ejecuta automáticamente.

## Uso diario

Abrir **Mesa editorial**:

- `Resumen 4H`: diez imprescindibles o panorama completo.
- `Acciones`: actualizar estados y dejar notas.
- `Olé hoy`: recordar lo publicado y detectar sobrecobertura.
- `Hallazgos`: historias internacionales, raras o sociales.
- `Fuentes`: problemas traducidos a lenguaje operativo.
- `Parte ampliado`: IA bajo demanda y con confirmación.

Abrir **Buzón social** para pegar enlaces encontrados en redes. El siguiente corte los incorpora a la mesa.
