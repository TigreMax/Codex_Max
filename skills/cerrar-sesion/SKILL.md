---
name: cerrar-sesion
description: Úsala al terminar una sesión de trabajo con una empresa, o cuando el jefe diga "cerramos", "hasta aquí", "guarda dónde nos quedamos". Escribe el historial de la sesión y deja el siguiente paso en la carpeta de la empresa.
---
# cerrar-sesion

## Antes de empezar
- Ten claro con qué empresa y proyecto trabajaste hoy.

## Pasos
1. Crea `<Empresa>\historial\AAAA-MM-DD_tema.md` con: qué se hizo, qué se decidió y por qué, qué archivos cambiaron y qué quedó a medias. Sin claves.
2. Reescribe `<Empresa>\_arranque.md`: actualiza proyectos activos, **siguiente paso** y **le toca al jefe**. Quita lo resuelto. Una página.
3. Si quedaron cosas por aprobar sin hacer, revisa que estén en `<Empresa>\por_aprobar.md` y menciónalas al jefe.
4. Si hubo corridas de Codex Max, anota en el historial el id de cada una y el resultado de `python -m codexmax status` (sin datos delicados).
5. Si descubriste algo que mejora el método (un error, una habilidad que falta), dilo al jefe; para crear la habilidad usa `nueva-habilidad`.
6. Dile al jefe en 3 renglones qué quedó guardado y dónde. Después de escribir, **relee los archivos** para comprobar que quedaron; no digas "quedó" sin verlo.

## Cómo saber que quedó bien
- Existe el archivo de historial de hoy y `_arranque.md` tiene la fecha de hoy.
- Otra sesión nueva podría arrancar leyendo solo `_arranque.md`.

## Qué nunca se hace
- Pegar el historial completo en `_arranque.md`.
- Guardar claves, contraseñas o datos bancarios.
