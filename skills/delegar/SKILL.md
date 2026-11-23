---
name: delegar
description: Úsala cuando un trabajo de código o de archivos conviene repartirlo entre agentes (Codex hace, Claude planifica y revisa, Antigravity investiga). Escribe el objetivo en un archivo y lo manda con Codex Max, que planifica, ejecuta en copias aisladas, revisa con otro agente y deja un reporte.
---
# delegar (con Codex Max)

Codex Max ya reparte el trabajo y lo revisa solo. Esta habilidad es para **mandarle** un objetivo bien escrito.

## Antes de empezar
- Sabe qué carpeta es el proyecto. **Debe ser un repositorio git con todo guardado** (`git status` limpio): de ahí salen las copias aisladas y es lo que permite deshacer.
- Si el trabajo toca dinero, publicar, enviar o instalar algo, pide permiso al jefe antes.
- Los comandos se corren desde `D:\Codex_Max`.

## Pasos
1. Escribe el objetivo en un archivo de texto dentro de `<proyecto>\_codexmax\tareas\AAAA-MM-DD_nombre.md` (todo lo que generan los agentes va en `_codexmax\`; lo que sube el jefe va en `entrada\`) con: qué se quiere, hechos comprobados que ya se saben, restricciones (archivos que NO se tocan) y cómo saber que quedó bien. Sé concreto: el planificador copia tus restricciones.
2. Muestra el comando al jefe antes de correrlo:
   `python -m codexmax run --repo "<carpeta del proyecto>" --goal-file "<archivo del objetivo>"`
   Cada corrida se guarda en `<repo>\_codexmax\runs\<id>\` (no en el taller). Si el repo está dentro de una carpeta de proyecto más grande, agrega `--salida "<carpeta del proyecto>\_codexmax"` para que quede junto al proyecto.
   Opciones: `--apply` (avanza la rama actual si todo sale bien, solo ff), `--workers N`, `--espera-max-horas H`, `--sin-avisos`, `--aceptar <ruta>` (acepta enviar a los agentes un archivo sensible que git rastrea).
3. Córrelo. Si lo dejas largo, avisa al jefe cuánto puede tardar. Los avisos de Windows le llegan solos.
4. Revisa el resultado: `<proyecto>\_codexmax\runs\<id>\REPORTE.md` (tareas, ramas, consumo). `status` muestra la ruta de cada corrida. Para ver todas las corridas: `python -m codexmax status`.
5. Nada se aplica solo salvo con `--apply`. Si no, el reporte trae el comando exacto: `git -C "<proyecto>" merge --ff-only <rama de integración>`. **Nunca hay git push automático.**
6. Si la corrida quedó interrumpida o pausada por cuota: `python -m codexmax resume <id>` (con `--reintentar` para tareas bloqueadas) o `python -m codexmax close <id>`.

## Cómo saber que quedó bien
- El reporte dice "hechas" para todas las tareas, o dice exactamente cuáles quedaron bloqueadas y por qué.
- Un agente distinto al autor las revisó (Codex Max lo hace solo).

## Qué nunca se hace
- Mandar datos delicados de una empresa a un agente sin permiso del jefe.
- Usar modos que se saltan permisos (`--yolo`, `--dangerously-skip-permissions`, `danger-full-access`).
- Dar por bueno un resultado sin leer el reporte y revisar los cambios.
- Hacer `git push` sin que el jefe lo pida.
