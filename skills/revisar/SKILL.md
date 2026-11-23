---
name: revisar
description: Úsala cuando otro agente entregue trabajo, cuando una corrida de Codex Max termine, o antes de dar por bueno cualquier trabajo importante. Decide quién revisa, obtiene el veredicto APROBADO o FALTA. Quien hace no aprueba.
---
# revisar

Codex Max ya revisa cada tarea con un agente distinto al autor. Esta habilidad sirve para revisar **a mano** (trabajo que llegó de fuera, o una segunda revisión de algo delicado).

## Antes de empezar
- Sabe qué se pidió y cómo se sabe que quedó bien (el objetivo original).
- Sabe quién lo hizo. **Nunca lo revisa el mismo.**

## ¿Quién revisa?
| Lo hizo | Revisa |
|---|---|
| Codex | Claude |
| Antigravity | Claude, verificando las fuentes |
| Claude | Codex, en solo lectura (`python -m codexmax run` con un objetivo de solo revisar) |
Algo delicado (dinero, seguridad, datos de clientes, algo que se publicará): **dos** revisiones.

## Pasos
1. Lee el objetivo completo, sobre todo "cómo saber que quedó bien".
2. **Abre los archivos** que cambiaron (`git diff`). No basta con el reporte del agente.
3. Código: corre sus pruebas si se puede sin instalar nada. Lo que no puedas comprobar, dilo.
4. Recalcula todo número o total que entregó el agente.
5. Investigación: abre las fuentes de los datos más importantes y confirma que dicen lo que el agente dice. Un dato que no está en la fuente es **FALTA**, aunque suene bien.
6. Termina con UNA línea: `VEREDICTO: APROBADO` o `VEREDICTO: FALTA - <qué falta, concreto>`.
7. Comprueba cada hallazgo antes de anotarlo como FALTA (pueden ser falsos positivos).

## Cómo saber que quedó bien
- El veredicto está escrito, lo dio alguien distinto al autor y cada FALTA dice archivo y qué se espera.

## Qué nunca se hace
- Aprobar tu propio trabajo, o el de un agente sin abrir los archivos.
- Aprobar algo que no pudiste comprobar "por si acaso".
- Corregir tú el trabajo que estás revisando: señalas, y lo corrige quien lo hizo.
- Tratar un APROBADO como permiso para publicar, enviar o pagar: eso lo autoriza el jefe.
- Rechazar por algo que Codex Max hace a propósito (por ejemplo, que el orquestador haga los commits de las tareas en sus ramas aisladas).
