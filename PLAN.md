# Codex Max — Plan del orquestador (paso 1)

Fecha: 2026-11-23 · Estado: BORRADOR para aprobación del jefe

## 1. Qué es
Un programa local (Python, sin dependencias externas) que recibe un objetivo, lo parte en tareas, se las reparte a **Codex, Kimi y Antigravity (agy)** usando las CLIs ya instaladas con las suscripciones del jefe, hace que **otro agente revise** cada resultado, y solo molesta al jefe cuando es indispensable.

## 2. Lo que SÍ comprobé en esta máquina (2026-11-23)
| Pieza | Estado |
|---|---|
| Codex | `codex-cli 0.160.0`; sesión iniciada con ChatGPT (`codex login status`). Modo sin pantalla: `codex exec` con `--json`, `-o <archivo>` (guarda el último mensaje), `--output-schema`, `-s read-only/workspace-write`, `-C <carpeta>`, `--ephemeral`, `--worktree`. |
| Kimi | `kimi 2.1.1`; configuración válida (`kimi doctor`). Modo sin pantalla: `kimi -p "<prompt>" --output-format stream-json`; también `--plan`, `--add-dir`, `--agent-file`, y servidor `acp`. |
| Antigravity | Comando real: `agy 1.5.9` (no `antigravity`). Modo sin pantalla: `agy -p "<prompt>" --output-format json/stream-json`, `--json-schema`, `--mode accept-edits/auto/plan`, `--sandbox`, `--print-timeout`, `--model`, `--effort`. Modelos listados con `agy models` (Gemini, y también Claude Opus/Sonnet 5.5 y GPT-OSS). |
| Base | Python 3.14, Node 24, git 2.55. `D:\Codex_Max` está vacía. |

## 3. Lo que NO sé (no lo invento)
1. **Cuotas y límites de cada suscripción** (mensajes/hora, tope semanal). Ninguna CLI que vi los expone; hay que medirlos en pruebas. El precio/cupo de Kimi ya figuraba como pendiente del jefe.
2. **Si Kimi y agy funcionan realmente sin pantalla** con la sesión actual (solo vi su ayuda; no he corrido un prompt real). Es la Fase 0.
3. **Si los términos de cada suscripción permiten automatizar con la CLI** de forma continua. No lo sé; el jefe o yo debemos leerlos antes de usarlo a escala.
4. **Dónde está Córtex ahora.** `D:\Cortex` y `D:\Cortex_Maestro` no existen, y no encontré `delegar.ps1`. Su habilidad `delegar` dice cómo se mandaban tareas, pero no puedo reutilizar el código. Si el jefe sabe dónde quedó, lo reviso; si no, Codex Max parte de cero.
5. Qué modo de permisos usa Kimi en `-p` sin preguntar (ver decisión B).

## 4. Diseño

```
objetivo (archivo .md)
   │
   ▼
PLANIFICADOR ──► lista de tareas (JSON, con dependencias)
   │
   ▼
COLA (SQLite) ──► ENRUTADOR ──► ADAPTADOR codex | kimi | agy
                      │              │  corre en worktree git aislado
                      │              ▼
                      │         RESULTADO + diff
                      ▼
                 REVISOR (agente distinto al autor) ──► APROBADO / FALTA
                      │
        FALTA ≤2 veces: reintento con la crítica; 3ª: cambia de agente; 4ª: consulta humana
                      │
                      ▼
              integrar a la rama (git local) ──► BITÁCORA
```

**Piezas**
- `adapters/` — un archivo por agente con la misma interfaz: `run(tarea, carpeta, modo) → {ok, texto, archivos, costo/tiempo, error}`. Solo ahí viven los comandos específicos.
- `router.py` — elige agente por tipo de tarea y por **cuota restante** (se sustituye por otro si uno se agota o falla). Reglas iniciales (a calibrar con la Fase 0, hoy son hipótesis): Codex = código y refactor; agy = lectura/resumen de volumen e investigación; Kimi = textos y datos en cantidad.
- `reviewer.py` — regla heredada de Córtex: **quien hace no aprueba**. El revisor corre en solo lectura con una lista de verificación y devuelve veredicto estructurado (`--output-schema` / `--json-schema`).
- `workspace.py` — cada tarea en un `git worktree` propio; nada toca la rama principal hasta que el revisor aprueba. Deshacer = descartar la rama.
- `quota.py` — cuenta usos por agente y detecta mensajes de límite; pone al agente en "enfriamiento" y reencola.
- `state.db` + `bitacora.md` — todo reanudable: si se apaga la PC, retoma donde quedó.
- `humano.py` — **único** canal hacia el jefe (ver §5).

## 5. Autonomía: cuándo SÍ se molesta al jefe
Por defecto todo corre solo. Solo se pausa y se escribe una solicitud en `por_aprobar.md` (con el comando exacto y una pregunta de sí/no) cuando:
1. **Sale, cuesta o no se puede deshacer:** `git push`, publicar, enviar correos/mensajes, pagar, tocar servidores reales, borrar fuera del worktree. (Regla nivel 3 de Córtex; `git push` nunca lo hace el sistema.)
2. **Secretos:** una tarea necesita una clave que no está en el `.env`.
3. **Ambigüedad real** del objetivo que no se resuelve leyendo los archivos (una sola pregunta, agrupada).
4. **Atasco:** 4 intentos fallidos con dos agentes distintos.
5. **Inicio de sesión caducado** de una CLI (solo el jefe puede iniciar sesión).

Todo lo demás (elegir agente, reintentar, esperar cuota, revisar, rehacer, integrar localmente) lo decide el sistema. Mientras algo espera al jefe, **el trabajo independiente sigue**.

## 6. Fases
**Fase 0 — Verificación (primero, ~1 sesión).** Correr un prompt trivial real en cada CLI desde Python y registrar: ¿funciona sin pantalla?, formato de salida, códigos de error, texto del mensaje de límite, tiempo. Resultado: `docs/hallazgos_cli.md`. Sin esto no se construye nada.
**Fase 1 — Núcleo.** Adaptadores + workspace + cola + bitácora. Meta: `codexmax run tarea.md --agente kimi` hace una tarea y deja el resultado en un worktree.
**Fase 2 — Revisión y reintentos.** Revisor cruzado, veredictos estructurados, política de reintentos.
**Fase 3 — Planificador y enrutador.** Objetivo → tareas con dependencias en paralelo; enrutado por tipo y cuota.
**Fase 4 — Autonomía total.** Modo desatendido (tarea programada de Windows), `por_aprobar.md`, notificación al jefe, reanudación tras reinicio.
**Fase 5 (los "demás pasos" que mencionó el jefe).** Conexión con Córtex/empresas, memoria compartida, panel de estado.

Prueba de aceptación del paso 1: un objetivo real y pequeño (p. ej. "agrega una función + sus pruebas") se resuelve de punta a punta, con un agente que lo hace, otro que lo revisa, y cero intervenciones humanas.

## 7. Estructura de carpetas propuesta
```
D:\Codex_Max\
  PLAN.md  LEEME.md  AGENTS.md
  codexmax\ (adapters, router, reviewer, workspace, quota, humano)
  docs\hallazgos_cli.md
  data\state.db   (fuera de git)
  runs\<fecha>_<id>\  (tareas, resultados, diffs)
  por_aprobar.md  bitacora.md
  .env (fuera de git)
```
Será su propio repositorio git.

## 8. Riesgos
- **Seguridad vs. autonomía:** para no preguntar, las CLIs piden modos permisivos. Mitigación: worktree aislado + sandbox `workspace-write` + `--add-dir` solo de la carpeta de la tarea; nunca `danger-full-access`.
- **Cuotas agotadas** a media tarea → reencolar y rotar agente.
- **Cambios de formato de las CLIs** (versiones nuevas): por eso los comandos viven solo en `adapters/` y la Fase 0 deja pruebas de humo repetibles.
- **Datos de empresas:** una tarea no manda datos de una empresa a un agente sin que su `permisos` lo autorice.

## 9. Decisiones que necesito del jefe
A. ¿El "cerebro" que planifica y reparte es un **programa Python** (barato, predecible, corre solo) apoyado en Codex para planear, o quiere que **Claude Code siga de Director** y Codex Max sea solo la herramienta? (Recomiendo Python autónomo.)
B. Para trabajar desatendido, Kimi/agy necesitan un modo sin preguntas (`--yolo`/`--auto`, `--mode auto`). Córtex los prohibía. ¿Se permiten **solo dentro del worktree aislado**? (Recomiendo sí.)
C. ¿Dónde quedó Córtex (`D:\Cortex_Maestro`)? ¿Lo integramos en la Fase 5 o va aparte?
