"""Consulta de corridas guardadas sin modificar sus bases de datos."""
import sqlite3
import time
from pathlib import Path

from .core import ROOT
from .lifecycle import process_alive, read_meta
from .registro import carpetas


def listar_corridas(runs_dir):
    """Lista corridas por id y tareas por orden de insercion, en solo lectura."""
    corridas = []
    for run_id, carpeta in carpetas(runs_dir):
        corrida = {"id": run_id, "ruta": str(carpeta), "hechas": 0, "total": 0, "tareas": []}
        if not carpeta.exists():
            corrida["error"] = "carpeta no encontrada"
            corridas.append(corrida)
            continue
        db_path = carpeta / "state.db"
        if not carpeta.is_dir() or not db_path.exists():
            corrida["error"] = "state.db no encontrada"
            corridas.append(corrida)
            continue
        conexion = None
        try:
            conexion = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
            tareas = conexion.execute("SELECT id, status FROM tasks ORDER BY rowid").fetchall()
            corrida["tareas"] = tareas
            corrida["total"] = len(tareas)
            corrida["hechas"] = sum(status == "hecha" for _, status in tareas)
            meta = read_meta(carpeta)
            corrida["pausada_hasta"] = (meta or {}).get("pausada_hasta")
            corrida["interrumpida"] = (any(status in ("en_curso", "pendiente") for _, status in tareas)
                                       and (meta is None or not process_alive(meta.get("pid"))))
        except (sqlite3.Error, OSError, ValueError) as exc:
            corrida["error"] = str(exc)
        finally:
            if conexion is not None:
                conexion.close()
        corridas.append(corrida)
    return corridas


def formatear(corridas):
    """Devuelve una linea de resumen por corrida."""
    if not corridas:
        return "No hay corridas guardadas."
    lineas = []
    for corrida in corridas:
        if "error" in corrida:
            error = " ".join(corrida["error"].splitlines())
            lineas.append(f"{corrida['id']}  ERROR: {error}" +
                          (f"  {corrida['ruta']}" if corrida.get("ruta") else ""))
            continue
        tareas = " ".join(f"{tid}:{status}" for tid, status in corrida["tareas"])
        linea = f"{corrida['id']}  {corrida['hechas']}/{corrida['total']} hechas"
        if tareas:
            linea += "  " + tareas
        if corrida.get("pausada_hasta") is not None:
            hora = time.strftime("%H:%M", time.localtime(corrida["pausada_hasta"]))
            linea += f"  PAUSADA POR CUOTA (hasta {hora})"
        elif corrida.get("interrumpida"):
            linea += "  INTERRUMPIDA"
        if corrida.get("ruta"):
            linea += f"  {corrida['ruta']}"
        lineas.append(linea)
    return "\n".join(lineas)


def main_status(runs_dir=None):
    """Imprime el estado de las corridas del repositorio o de otra carpeta."""
    if runs_dir is None:
        runs_dir = ROOT / "runs"
    print(formatear(listar_corridas(runs_dir)))
