"""Metadatos y recuperacion de corridas locales."""
import ctypes
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def process_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        if pid > 0xFFFFFFFF:
            return False
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            # Acceso denegado no demuestra que el proceso haya terminado.
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    return True


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def read_meta(run_dir):
    path = Path(run_dir) / "meta.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(run_dir, meta):
    path = Path(run_dir) / "meta.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def recover(run_id, runs_dir, reintentar=False, close=False):
    from .orchestrator import Orchestrator

    root = Path(runs_dir).resolve()
    run_dir = (root / run_id).resolve()
    if run_dir.parent != root or not (run_dir / "state.db").is_file():
        raise SystemExit(f"Corrida inexistente o id invalido: {run_id}")
    try:
        meta = read_meta(run_dir)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"No se puede leer meta.json: {exc}") from exc
    if meta is not None and process_alive(meta.get("pid")):
        raise SystemExit(f"El proceso {meta['pid']} sigue vivo; no se puede modificar la corrida.")
    if meta is None and not close:
        raise SystemExit(f"La corrida no tiene meta.json; use python -m codexmax close {run_id}.")
    config = meta or {}
    orchestrator = Orchestrator(
        config.get("repo", run_dir), config.get("goal", "Corrida antigua sin meta.json"),
        run_dir, run_id, apply=config.get("apply", False) if not close else False,
        workers=config.get("workers", 3), aceptar=config.get("aceptar", []),
        espera_max_horas=config.get("espera_max_horas", 6))
    try:
        if not close:
            meta["pid"] = os.getpid()
            meta.pop("finished", None)
            meta.pop("pausada_hasta", None)
            write_meta(run_dir, meta)
        states = ("en_curso", "pendiente") if close else ("en_curso",)
        if reintentar and not close:
            states += ("bloqueada", "omitida")
        for task in orchestrator.store.all():
            if task["status"] in states:
                changes = {"status": "cerrada" if close else "pendiente"}
                if close:
                    changes["note"] = "cerrada por el jefe"
                orchestrator.store.set(task["id"], **changes)
        if close:
            orchestrator.report()
        else:
            orchestrator.execute()
        if meta is not None:
            orchestrator.save_outcome()
    finally:
        orchestrator.store.db.close()
