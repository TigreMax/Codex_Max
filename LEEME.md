# Codex Max

Orquestador local que reparte trabajo entre tres agentes usando sus CLIs y las suscripciones del jefe.
Independiente de Cortex. Solo Python estandar (3.10+), sin dependencias.

## Roles (definidos por el jefe, 2026-11-23)
| Agente | Rol |
|---|---|
| **Claude Code** (`claude`) | Orquestador: planifica el objetivo y **revisa** todo lo que otros hacen |
| **Codex** (`codex`) | Hace el trabajo (codigo, textos) |
| **Antigravity** (`agy`) | Investiga (web) y, a futuro, el entorno de Google |
Kimi quedo fuera. Quien hace un trabajo nunca lo aprueba: el revisor siempre es Claude.

## Uso
```
python -m codexmax doctor
python -m codexmax status
python -m codexmax uso
python -m codexmax run --repo "D:\ruta\al\repo" --goal "lo que quieres lograr"
python -m codexmax run --repo ... --goal-file objetivo.md --apply
python -m codexmax run --repo ... --salida "D:\proyecto\_codexmax" --goal "objetivo"
```
`status` lista corridas nuevas y antiguas con sus rutas (hechas/total y estado de cada tarea), en solo lectura.
Avisos Windows y registro en `avisos.log`: `run --sin-avisos` o `CODEXMAX_SIN_AVISOS=1` desactiva solo los toasts.
`uso` muestra llamadas y tokens locales por agente y modelo (5h, 7d y total); no incluye uso fuera de Codex Max ni conoce los limites del plan.
Cada llamada registra metricas en `uso.jsonl` y el reporte resume Consumo; `costo_usd` es equivalente API informativo, no un cobro de la suscripcion.
Para cambiar modelos, crea `modelos.json` en la raiz: `{"codex": {"code": ["gpt-6.2-astra", "high"]}}`.
Puedes indicar roles `plan`, `review`, `code`, `text` y `research` para `codex`, `claude` o `agy`.
`run` guarda configuracion y PID en `meta.json`; `status` indica INTERRUMPIDA cuando quedan tareas sin proceso vivo.
`python -m codexmax resume <id> [--reintentar]` continua sin planificar; la opcion incluye bloqueadas y omitidas.
`python -m codexmax close <id>` cierra pendientes y genera REPORTE.md sin borrar ramas ni carpetas; admite corridas antiguas. Ambos comandos rechazan procesos vivos.

- El repo debe ser git y estar limpio. Todo ocurre en ramas `cm/<run>/...` y worktrees en `runs/<run>/wt/`.
- FALTA del revisor -> reintento con la critica; 3.er intento cambia de agente; 4.o fallido -> pide al jefe.
- Nunca hace `git push`. Lo hecho queda en `cm/<run>/_integracion`; `--apply` avanza tu rama (solo fast-forward).
- Lo unico que requiere al jefe se escribe en el `por_aprobar.md` de la corrida.
- Resultado: `<repo>/_codexmax/runs/<run>/REPORTE.md`, `bitacora.md` y `llamadas/` (prompt y respuesta de cada agente); el taller solo registra `data/registro.jsonl` y `data/uso.jsonl`.

## Filtro de secretos (`codexmax/guard.py`)
1. Las copias de trabajo solo tienen lo que git rastrea: un `.env` ignorado por git nunca llega a un agente.
2. Antes de correr se escanean los archivos rastreados (nombres y contenido). Si hay algo sensible, **no inicia** y lo deja en `por_aprobar.md`. Para aceptar un archivo concreto: `--aceptar <ruta>`.
3. Antes de integrar se escanea lo que el agente agrego; si hay un secreto, se descarta ese cambio y se le pide rehacerlo.
4. El objetivo tambien se revisa. Claude lleva lecturas denegadas (`.env`, `~/.ssh`, `~/.aws`, carpetas de otras CLIs). Todos los agentes reciben la regla en el prompt (capa blanda).
Limite conocido: no se verifico que Codex o agy no puedan leer archivos fuera de su copia de trabajo. Nunca se imprime el valor de un secreto.

## Archivos
`codexmax/adapters.py` (comandos de cada CLI) · `core.py` (roles, salud/cuotas, canal humano) · `workspace.py` (git) · `orchestrator.py` (planificar, repartir, revisar, integrar) · `store.py` (SQLite).
Hallazgos de las CLIs: `docs/hallazgos_cli.md`. Plan original: `PLAN.md` (anterior a los roles actuales).

La cuota agotada pausa la corrida sin bloquear tareas ni pedir al jefe; status muestra PAUSADA POR CUOTA.
run --espera-max-horas 6 limita la espera dentro del proceso; para retomar: python -m codexmax resume <id>.

## Habilidades (skills)
Viven en `skills/` y las leen los 3 agentes: `python -m codexmax skills instalar` (copia a Codex `~/.agents/skills`, Antigravity `~/.gemini/antigravity-cli/skills` y Claude `~/.claude/skills`; lo ajeno se respalda, no se borra) y `skills estado`.
Las bibliotecas grandes (ciberseguridad, cientifica, diagram-design) siguen en `D:\Cortex_externas`; las habilidades solo las apuntan. Para crear una nueva: habilidad `nueva-habilidad`.
