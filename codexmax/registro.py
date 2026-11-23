"""Indice minimo de corridas y conteos locales del taller."""
import json
import threading
from pathlib import Path

from .core import ROOT
from .lifecycle import timestamp


_registro_lock = threading.Lock()
_uso_lock = threading.Lock()


def append_line(path, row, lock):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with lock, path.open("a", encoding="utf-8") as stream:
        stream.write(line)


def registrar(run_id, run_dir, repo, data_dir=None):
    data_dir = Path(data_dir) if data_dir is not None else ROOT / "data"
    append_line(data_dir / "registro.jsonl",
                dict(id=run_id, ruta=str(Path(run_dir).resolve()),
                     repo=str(Path(repo).resolve()), ts=timestamp()), _registro_lock)


def registrar_uso(row, data_dir=None):
    data_dir = Path(data_dir) if data_dir is not None else ROOT / "data"
    append_line(data_dir / "uso.jsonl", row, _uso_lock)


def leer_registro(data_dir=None):
    data_dir = Path(data_dir) if data_dir is not None else ROOT / "data"
    try:
        with (data_dir / "registro.jsonl").open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if (isinstance(row, dict) and isinstance(row.get("id"), str)
                            and row["id"] and isinstance(row.get("ruta"), str)
                            and Path(row["ruta"]).is_absolute()):
                        yield row
                except (ValueError, TypeError, RecursionError):
                    continue
    except OSError:
        return


def carpetas(runs_dir, data_dir=None):
    """Une el indice nuevo con las corridas antiguas, sin repetir ids."""
    runs_dir = Path(runs_dir)
    data_dir = Path(data_dir) if data_dir is not None else runs_dir.parent / "data"
    found = {}
    if runs_dir.is_dir():
        for path in runs_dir.iterdir():
            if path.is_dir() and (path / "state.db").is_file():
                found[path.name] = path.resolve()
    for row in leer_registro(data_dir):
        found[row["id"]] = Path(row["ruta"])
    return sorted(found.items())
