---
name: comprobar-codexmax
description: Úsala cuando el jefe pida comprobar que Codex Max quedó bien instalado en esta computadora (después de actualizar, reinstalar programas o cambiar de equipo). Solo comprueba y reporta; no instala nada.
---
# comprobar-codexmax

Esta habilidad **no instala programas**: comprueba y reporta. Instalar es decisión del jefe.

## Pasos
1. **Programas:** `python -m codexmax doctor` (muestra qué CLIs están: codex, agy, claude). Anota versiones con `git --version`, `python --version`, `codex --version`, `agy --version`, `claude --version`. Si falta algo, dile al jefe cuál; no lo instales.
2. **Pruebas:** `python -m unittest discover -s tests` desde `D:\Codex_Max`. Esperado: todas OK.
3. **Habilidades:** `python -m codexmax skills estado`. Esperado: cada habilidad instalada en las tres ubicaciones (Codex, Antigravity y Claude). Si falta alguna: `python -m codexmax skills instalar`.
4. **Corridas:** `python -m codexmax status` (¿hay alguna interrumpida o pausada por cuota?) y `python -m codexmax uso` (consumo local por agente y modelo).
5. **Modelos:** si existe `D:\Codex_Max\modelos.json`, dilo (anula la tabla por defecto).
6. **Reporte al jefe:** tabla corta: programas (versiones), pruebas, habilidades, corridas → OK / FALLA, y qué hace falta. Si algo falla, el mensaje de error **exacto**.

## Cómo saber que quedó bien
- Cada renglón de la tabla dice OK, o dice FALLA con el motivo exacto.

## Qué nunca se hace
- Instalar programas, paquetes o entornos.
- Dar un OK sin haber corrido la comprobación y visto su resultado.
- Hacer `git push`: lo corre el jefe.
