"""Piezas pequenas: salud/cuotas de agentes, enrutador, canal humano, bitacora."""
import threading
import time
from pathlib import Path

from .adapters import ADAPTERS

ROOT = Path(__file__).resolve().parent.parent
POR_APROBAR = ROOT / "por_aprobar.md"

# Preferencias iniciales por tipo de tarea. Son HIPOTESIS: se calibran con uso real.
# Roles definidos por el jefe (2026-11-23): Claude Code planifica y revisa, Codex hace el
# trabajo, Antigravity investiga. El revisor nunca es el autor: Claude no esta en las listas
# de autores, asi que siempre es otro agente.
PREF = {
    "code":     ["codex", "agy"],
    "text":     ["codex", "agy"],
    "research": ["agy", "codex"],
    "review":   ["claude"],
    "plan":     ["claude", "codex"],
}
SIMULT = {"codex": 2, "agy": 2, "claude": 2}


class Health:
    """Enfriamiento por cuota y agentes 'muertos' (sesion caducada)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cool = {}
        self.dead = {}
        self.sem = {n: threading.Semaphore(SIMULT.get(n, 1)) for n in ADAPTERS}

    def available(self, n):
        with self.lock:
            return n not in self.dead and self.cool.get(n, 0) <= time.time()

    def cooldown(self, n, secs):
        with self.lock:
            self.cool[n] = time.time() + secs

    def kill(self, n, why):
        with self.lock:
            self.dead[n] = why

    def wait_secs(self, names):
        with self.lock:
            live = [n for n in names if n not in self.dead]
            if not live:
                return None
            return max(0, min(self.cool.get(n, 0) for n in live) - time.time())


class Router:
    def __init__(self, health, log):
        self.h, self.log = health, log

    def candidates(self, kind, exclude=()):
        return [n for n in PREF.get(kind, PREF["code"])
                if n not in exclude and ADAPTERS[n].installed()]

    def pick(self, kind, exclude=(), prefer_not=(), timeout=3 * 3600):
        """Devuelve un agente disponible; espera enfriamientos; None si no hay ninguno."""
        end = time.time() + timeout
        while True:
            cands = self.candidates(kind, exclude)
            ok = [n for n in cands if self.h.available(n)]
            if ok:
                fresh = [n for n in ok if n not in prefer_not]
                return (fresh or ok)[0]
            w = self.h.wait_secs(cands)
            if w is None or time.time() + w > end:
                return None
            self.log(f"[router] todos en enfriamiento; espero {int(w)}s")
            time.sleep(min(max(w, 5), 60))


_ask_lock = threading.Lock()


def pedir_humano(titulo, detalle, comando=None, run_id=""):
    """UNICO canal hacia el jefe. Escribe en por_aprobar.md (sin duplicar)."""
    with _ask_lock:
        old = POR_APROBAR.read_text(encoding="utf-8") if POR_APROBAR.exists() else \
            "# Por aprobar / requiere al jefe\n\n"
        if f"## {titulo}" in old and "[PENDIENTE]" in old.split(f"## {titulo}")[1].split("## ")[0]:
            return
        bloque = f"\n## {titulo}\n[PENDIENTE] run {run_id} - {time.strftime('%Y-%m-%d %H:%M')}\n\n{detalle}\n"
        if comando:
            bloque += f"\nComando exacto:\n```\n{comando}\n```\n"
        POR_APROBAR.write_text(old + bloque, encoding="utf-8")


class Bitacora:
    def __init__(self, path):
        self.path, self.lock = Path(path), threading.Lock()

    def __call__(self, msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with self.lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
