"""Instala las habilidades de Codex Max (skills/) donde las leen los agentes.

Codex lee ~/.agents/skills; Antigravity lee ~/.gemini/antigravity-cli/skills; Claude lee ~/.claude/skills.
Nunca borra nada que no sea suyo: lo que ya exista con el mismo nombre y no lo haya puesto Codex Max
se MUEVE a una carpeta de respaldo.
"""
import re
import shutil
import time
import unicodedata
from pathlib import Path

from .core import ROOT

SRC = ROOT / "skills"
MARCA = ".codexmax"
# Habilidades grandes que se quedan fuera del repositorio y se copian desde su carpeta.
EXTERNAS = {"diagram-design": Path("D:/Cortex_externas/diagram-design/skills/diagram-design")}
# Habilidades viejas de Cortex que ya no aplican: se mueven al respaldo si estan instaladas.
RETIRAR = ["instalar-cortex"]


def destinos():
    home = Path.home()
    return {"agents": (home / ".agents" / "skills", home / ".agents" / "skills_respaldo"),
            "antigravity": (home / ".gemini" / "antigravity-cli" / "skills",
                            home / ".gemini" / "antigravity-cli" / "skills_respaldo"),
            "claude": (home / ".claude" / "skills", home / ".claude" / "skills_respaldo")}


def fuentes(src=None, externas=None):
    """{nombre: carpeta} de las habilidades a instalar (propias + externas que existan)."""
    src = SRC if src is None else Path(src)
    externas = EXTERNAS if externas is None else externas
    found = {p.parent.name: p.parent for p in sorted(src.glob("*/SKILL.md"))}
    for name, path in externas.items():
        if (Path(path) / "SKILL.md").is_file():
            found.setdefault(name, Path(path))
    return found


def validar(nombre, carpeta):
    """Devuelve una lista de problemas ([] si esta bien)."""
    texto = (Path(carpeta) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    problemas = []
    m = re.match(r"---\r?\nname:\s*(.+?)\r?\ndescription:\s*(.+?)\r?\n---", texto, re.S)
    if not m:
        problemas.append("falta el encabezado name/description")
    elif m.group(1).strip() != nombre:
        problemas.append(f"name '{m.group(1).strip()}' no coincide con la carpeta '{nombre}'")
    if any(unicodedata.category(c) in ("Cf", "Co") for c in texto):
        problemas.append("tiene caracteres invisibles")
    return problemas


def _copiar(origen, destino):
    shutil.copytree(origen, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", MARCA))
    (destino / MARCA).write_text("instalada por Codex Max\n", encoding="utf-8")


def _respaldar(ruta, respaldo):
    respaldo.mkdir(parents=True, exist_ok=True)
    destino = respaldo / f"{ruta.name}-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.move(str(ruta), str(destino))
    return destino


def instalar(src=None, externas=None, dests=None, retirar=None):
    """Instala/actualiza todo. Devuelve lineas de reporte."""
    dests = destinos() if dests is None else dests
    retirar = RETIRAR if retirar is None else retirar
    lines = []
    lista = fuentes(src, externas)
    buenas = {}
    for nombre, carpeta in lista.items():
        problemas = validar(nombre, carpeta)
        if problemas:
            lines.append(f"OMITIDA {nombre}: {'; '.join(problemas)}")
        else:
            buenas[nombre] = carpeta
    for etiqueta, (raiz, respaldo) in dests.items():
        raiz = Path(raiz)
        raiz.mkdir(parents=True, exist_ok=True)
        for nombre in retirar:
            viejo = raiz / nombre
            if viejo.exists():
                lines.append(f"[{etiqueta}] retirada {nombre} -> {_respaldar(viejo, Path(respaldo))}")
        for nombre, carpeta in buenas.items():
            destino = raiz / nombre
            if destino.exists():
                if (destino / MARCA).exists():
                    shutil.rmtree(destino)
                    accion = "actualizada"
                else:
                    lines.append(f"[{etiqueta}] respaldo de {nombre} -> {_respaldar(destino, Path(respaldo))}")
                    accion = "instalada"
            else:
                accion = "instalada"
            _copiar(carpeta, destino)
            lines.append(f"[{etiqueta}] {accion} {nombre}")
    return lines


def estado(src=None, externas=None, dests=None, retirar=None):
    dests = destinos() if dests is None else dests
    retirar = RETIRAR if retirar is None else retirar
    lines = []
    for nombre, carpeta in fuentes(src, externas).items():
        problemas = validar(nombre, carpeta)
        celdas = []
        for etiqueta, (raiz, _) in dests.items():
            ruta = Path(raiz) / nombre
            celdas.append(f"{etiqueta}={'OK' if (ruta / MARCA).exists() else 'distinta' if ruta.exists() else 'falta'}")
        lines.append(f"{nombre:28} {' '.join(celdas)}" + (f"  PROBLEMA: {'; '.join(problemas)}" if problemas else ""))
    for nombre in retirar:
        for etiqueta, (raiz, _) in dests.items():
            if (Path(raiz) / nombre).exists():
                lines.append(f"{nombre:28} [{etiqueta}] sigue instalada y esta retirada: corre 'skills instalar'")
    return lines


def main_skills(accion):
    for line in (instalar() if accion == "instalar" else estado()):
        print(line)
    if accion == "instalar":
        print("Listo. Los agentes leen las habilidades al abrir una sesion nueva.")
