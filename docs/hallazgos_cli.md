# Hallazgos de las CLIs (2026-11-23)

Todo lo de esta tabla se comprobo ejecutando de verdad, no leyendo ayudas.

| Agente | Como se usa sin pantalla | Hallazgos |
|---|---|---|
| codex 0.160.0 | `codex exec -s read-only\|workspace-write --ephemeral -C <dir> -o <archivo> -` (prompt por stdin) | ~30-60 s por tarea. El texto final queda en el archivo de `-o`. Imprime errores de `rmcp` en stderr aunque todo vaya bien: no usar stderr para decidir exito. Una vez reporto "limit" en 4 s sin que lo pudiera reproducir; ahora cada error se guarda en `runs/<run>/llamadas/`. |
| agy 1.5.9 | `agy -p "<prompt>" --output-format json --sandbox` | Devuelve `{"status","response",...}`. **`--mode plan`** genera un plan y pide aprobacion (inutil). **`--mode accept-edits`** DENIEGA comandos (`denied_actions`) y responde vacio. **`--mode auto`** no esta disponible en esta cuenta. Lo que funciona: `--sandbox` con modo por defecto (edita archivos, corre comandos, busca en la web). Sin servidores MCP configurados; plugins: android-cli, chrome-devtools, modern-web-guidance. |
| claude 2.1.x | `claude -p --output-format json --no-session-persistence ...` (prompt por stdin) | `--bare` NO sirve: exige clave de API (no lee la suscripcion). Corre con la configuracion normal, asi que carga CLAUDE.md global y hooks: el prompt le dice que los ignore. Lectura: `--disallowedTools "Edit Write NotebookEdit"`; siempre `--disallowedTools "Bash(git push*)"`. |
| kimi 2.1.1 | DESCARTADO por el jefe | Sin credencial (`kimi login`). `-p` no se puede combinar con ningun flag de modo de permisos. |

## Sin verificar
- Mensajes exactos de limite de cuota de cada CLI (`adapters.py` usa expresiones regulares amplias).
- "Entorno de Google" de agy: hoy no tiene ningun conector de Google (Drive, Docs, Gmail, etc.) configurado. No se sabe cuales soporta; hay que decidir cuales conectar.
- Cuotas/limites de las suscripciones y si sus terminos permiten automatizar con la CLI de forma continua.

## Pruebas de punta a punta (repo de juguete `_smoke/demo`)
- Run 7: Claude planifico 2 tareas, Codex las hizo, Claude las reviso, 0 intervenciones humanas. Se verifico aparte: 3 pruebas unittest pasan.
- Run 8 (investigacion): agy busco en la web, escribio `docs/mock.md` con fuente, Claude aprobo.
- Fallos corregidos en el camino: nombres de rama anidados, modos de agy, regex del veredicto (caracter de control), revisor fallido ya no gasta intentos del autor.
