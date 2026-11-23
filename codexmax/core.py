"""Piezas pequenas: salud/cuotas de agentes, enrutador, canal humano, bitacora."""
import re
from datetime import datetime, timedelta
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


def parse_reset(texto, ahora):
    """Interpreta duraciones y horas locales de reinicio, sin depender de una CLI."""
    relative = re.search(r"\b(?:in|en)\s+((?:\d+\s*(?:hours?|horas?|minutes?|minutos?|days?|dias?|días?)\s*(?:and|y)?\s*)+)", texto, re.I)
    if relative:
        units = re.findall(r"(\d+)\s*(hours?|horas?|minutes?|minutos?|days?|dias?|días?)", relative[1], re.I)
        return ahora + sum(int(n) * (3600 if u.lower().startswith('h') else
                                    60 if u.lower().startswith('m') else 86400)
                           for n, u in units)
    clock = re.search(r"\b(?:resets?\s+at|a\s+las)\s+(\d{1,2}):(\d{2})\s*(am|pm)?\b", texto, re.I)
    if clock:
        hour, minute, period = int(clock[1]), int(clock[2]), clock[3]
        if minute > 59 or hour > (12 if period else 23) or (period and hour == 0):
            return None
        if period:
            hour = hour % 12 + (12 if period.lower() == 'pm' else 0)
        now = datetime.fromtimestamp(ahora)
        reset = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reset <= now:
            reset += timedelta(days=1)
        return reset.timestamp()
    return None


class CuotaAgotada(Exception):
    def __init__(self, agentes, hasta):
        self.agentes, self.hasta = list(agentes), hasta
        super().__init__(f"Cuota agotada: {', '.join(self.agentes)} hasta {hasta}")


class Health:
    """Enfriamiento por cuota y agentes 'muertos' (sesion caducada)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cool = {}
        self.limits = {}
        self.dead = {}
        self.sem = {n: threading.Semaphore(SIMULT.get(n, 1)) for n in ADAPTERS}

    def available(self, n):
        with self.lock:
            return n not in self.dead and self.cool.get(n, 0) <= time.time()

    def cooldown(self, n, texto=""):
        with self.lock:
            now = time.time()
            self.limits[n] = self.limits.get(n, 0) + 1
            reset = parse_reset(texto, now)
            self.cool[n] = (reset + 60 if reset is not None else
                            now + min(self.limits[n] * 10, 30) * 60)

    def ok(self, n):
        with self.lock:
            self.limits.pop(n, None)
            self.cool.pop(n, None)

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
    def __init__(self, health, log, timeout=6 * 3600):
        self.h, self.log, self.timeout = health, log, timeout

    def candidates(self, kind, exclude=()):
        return [n for n in PREF.get(kind, PREF["code"])
                if n not in exclude and n in ADAPTERS and ADAPTERS[n].installed()]

    def pick(self, kind, exclude=(), prefer_not=(), timeout=None):
        """Devuelve un agente disponible; espera enfriamientos; None si no hay ninguno."""
        end = time.time() + (self.timeout if timeout is None else timeout)
        while True:
            cands = self.candidates(kind, exclude)
            ok = [n for n in cands if self.h.available(n)]
            if ok:
                fresh = [n for n in ok if n not in prefer_not]
                return (fresh or ok)[0]
            w = self.h.wait_secs(cands)
            if w is None:
                return None
            if time.time() + w > end:
                raise CuotaAgotada([n for n in cands if n not in self.h.dead], time.time() + w)
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
