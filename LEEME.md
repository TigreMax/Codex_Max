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
python -m codexmax run --repo "D:\ruta\al\repo" --goal "lo que quieres lograr"
python -m codexmax run --repo ... --goal-file objetivo.md --apply
```
- El repo debe ser git y estar limpio. Todo ocurre en ramas `cm/<run>/...` y worktrees en `runs/<run>/wt/`.
- FALTA del revisor -> reintento con la critica; 3.er intento cambia de agente; 4.o fallido -> pide al jefe.
- Nunca hace `git push`. Lo hecho queda en `cm/<run>/_integracion`; `--apply` avanza tu rama (solo fast-forward).
- Lo unico que requiere al jefe se escribe en `por_aprobar.md`.
- Resultado: `runs/<run>/REPORTE.md`, `bitacora.md` y `llamadas/` (prompt y respuesta de cada agente).

## Archivos
`codexmax/adapters.py` (comandos de cada CLI) · `core.py` (roles, salud/cuotas, canal humano) · `workspace.py` (git) · `orchestrator.py` (planificar, repartir, revisar, integrar) · `store.py` (SQLite).
Hallazgos de las CLIs: `docs/hallazgos_cli.md`. Plan original: `PLAN.md` (anterior a los roles actuales).
