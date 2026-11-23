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
python -m codexmax run --repo "D:\ruta\al\repo" --goal "lo que quieres lograr"
python -m codexmax run --repo ... --goal-file objetivo.md --apply
```
status: lista las corridas guardadas en runs/ (id, tareas hechas/total y estado de cada tarea) leyendo su state.db
- El repo debe ser git y estar limpio. Todo ocurre en ramas `cm/<run>/...` y worktrees en `runs/<run>/wt/`.
- FALTA del revisor -> reintento con la critica; 3.er intento cambia de agente; 4.o fallido -> pide al jefe.
- Nunca hace `git push`. Lo hecho queda en `cm/<run>/_integracion`; `--apply` avanza tu rama (solo fast-forward).
- Lo unico que requiere al jefe se escribe en `por_aprobar.md`.
- Resultado: `runs/<run>/REPORTE.md`, `bitacora.md` y `llamadas/` (prompt y respuesta de cada agente).

## Filtro de secretos (`codexmax/guard.py`)
1. Las copias de trabajo solo tienen lo que git rastrea: un `.env` ignorado por git nunca llega a un agente.
2. Antes de correr se escanean los archivos rastreados (nombres y contenido). Si hay algo sensible, **no inicia** y lo deja en `por_aprobar.md`. Para aceptar un archivo concreto: `--aceptar <ruta>`.
3. Antes de integrar se escanea lo que el agente agrego; si hay un secreto, se descarta ese cambio y se le pide rehacerlo.
4. El objetivo tambien se revisa. Claude lleva lecturas denegadas (`.env`, `~/.ssh`, `~/.aws`, carpetas de otras CLIs). Todos los agentes reciben la regla en el prompt (capa blanda).
Limite conocido: no se verifico que Codex o agy no puedan leer archivos fuera de su copia de trabajo. Nunca se imprime el valor de un secreto.

## Archivos
`codexmax/adapters.py` (comandos de cada CLI) · `core.py` (roles, salud/cuotas, canal humano) · `workspace.py` (git) · `orchestrator.py` (planificar, repartir, revisar, integrar) · `store.py` (SQLite).
Hallazgos de las CLIs: `docs/hallazgos_cli.md`. Plan original: `PLAN.md` (anterior a los roles actuales).
