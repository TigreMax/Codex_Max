"""El cerebro: planifica, reparte, hace revisar, reintenta e integra."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from .adapters import ADAPTERS
from .core import Health, Router, Bitacora, pedir_humano
from .store import Store
from .workspace import Workspace

MAX_INTENTOS = 4          # 2 con el mismo agente, 3.o con otro, 4.o ultimo
COOLDOWN_LIMITE = 15 * 60
REGLAS = (
    "REGLAS: trabaja SOLO dentro de esta carpeta. No hagas git push ni publiques nada. "
    "No escribas claves ni contrasenas en archivos. No borres fuera de esta carpeta. "
    "Si hay pruebas, corrélas. Termina con un resumen corto de lo que hiciste."
)


def _json_obj(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("sin JSON")
    return json.loads(text[i:j + 1])


def _acyclic(tasks):
    ids = {t["id"] for t in tasks}
    seen, stack = {}, set()

    def visit(n, deps):
        if n in stack:
            return False
        if seen.get(n):
            return True
        stack.add(n)
        ok = all(visit(d, deps) for d in deps[n])
        stack.discard(n)
        seen[n] = True
        return ok
    deps = {t["id"]: [d for d in t["deps"] if d in ids] for t in tasks}
    return all(visit(n, deps) for n in deps)


class Orchestrator:
    def __init__(self, repo, goal, run_dir, run_id, apply=False, workers=3):
        self.repo, self.goal, self.run_id, self.apply = Path(repo), goal, run_id, apply
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log = Bitacora(self.run_dir / "bitacora.md")
        self.store = Store(self.run_dir / "state.db")
        self.health = Health()
        self.router = Router(self.health, self.log)
        self.ws = Workspace(repo, run_dir, run_id)
        self.workers = workers

    # ---------- llamadas a agentes ----------
    def call(self, agent, prompt, cwd, write, timeout):
        a = ADAPTERS[agent]
        with self.health.sem[agent]:
            r = a.run(prompt, cwd, write=write, timeout=timeout)
        self.log(f"[{agent}] {'escribe' if write else 'lee'} -> {r.kind} en {r.seconds:.0f}s"
                 + ("" if r.ok else f" | {r.error[-300:]!r}"))
        calls = self.run_dir / "llamadas"
        calls.mkdir(exist_ok=True)
        n = len(list(calls.iterdir())) + 1
        (calls / f"{n:03d}_{agent}_{'w' if write else 'r'}.txt").write_text(
            "PROMPT:\n" + prompt + f"\n\n--- RESULTADO ({r.kind}) ---\n" + r.text + "\n" + r.error,
            encoding="utf-8")
        if not write and Path(cwd).name != "_integracion":
            self.ws.reset(cwd)                 # el revisor/lector nunca deja cambios
        if r.kind == "limit":
            self.health.cooldown(agent, COOLDOWN_LIMITE)
        elif r.kind == "auth":
            self.health.kill(agent, r.error)
            pedir_humano(f"Iniciar sesion en {agent}",
                         f"La CLI de {agent} no tiene sesion valida. Solo el jefe puede iniciarla.\n"
                         f"Detalle: {r.error[:300]}",
                         {"claude": "claude   (abrirlo una vez e iniciar sesion)", "codex": "codex login",
                          "agy": "agy  (abrirlo una vez e iniciar sesion)"}.get(agent),
                         self.run_id)
        return r

    # ---------- planificacion ----------
    def plan(self):
        prompt = (
            "Eres el planificador de un orquestador de agentes de programacion. "
            "Lee el proyecto (solo lectura) y divide el OBJETIVO en tareas pequenas y verificables.\n"
            f"OBJETIVO:\n{self.goal}\n\n"
            "Responde SOLO con JSON valido, sin texto extra, con esta forma:\n"
            '{"tasks":[{"id":"t1","title":"...","kind":"code|research|text",'
            '"prompt":"instrucciones completas y autocontenidas","done_when":"criterio comprobable",'
            '"deps":[]}]}\n'
            "Reglas: maximo 8 tareas; ids unicos; si dos tareas tocan los mismos archivos, la segunda "
            "debe depender de la primera; no incluyas tareas de publicar, enviar o hacer push."
        )
        exclude = set()
        for _ in range(3):
            ag = self.router.pick("plan", exclude)
            if not ag:
                break
            r = self.call(ag, prompt, self.ws.integ, False, 600)
            if not r.ok:
                exclude.add(ag) if r.kind != "limit" else None
                continue
            try:
                tasks = _json_obj(r.text)["tasks"][:8]
                ids = [t["id"] for t in tasks]
                for t in tasks:
                    t["deps"] = [d for d in t.get("deps", []) if d in ids and d != t["id"]]
                    t["id"] = re.sub(r"[^A-Za-z0-9_-]", "_", str(t["id"]))
                    assert t["prompt"] and t["title"]
                if len({t["id"] for t in tasks}) != len(tasks) or not _acyclic(tasks):
                    raise ValueError("ids repetidos o ciclo")
                self.log(f"[plan] {len(tasks)} tareas (planificó {ag})")
                return tasks
            except Exception as e:
                self.log(f"[plan] respuesta no valida de {ag}: {e}")
        self.log("[plan] sin plan valido: se usa una sola tarea con el objetivo completo")
        return [{"id": "t1", "title": "Objetivo completo", "kind": "code",
                 "prompt": self.goal, "done_when": "El objetivo se cumple y las pruebas existentes pasan.",
                 "deps": []}]

    # ---------- una tarea de punta a punta ----------
    def author_prompt(self, t, critique):
        p = (f"TAREA: {t['title']}\n\n{t['prompt']}\n\n"
             f"CRITERIO DE TERMINADO: {t['done_when']}\n\n{REGLAS}")
        if critique:
            p += f"\n\nUN REVISOR RECHAZO TU INTENTO ANTERIOR. Corrige esto:\n{critique}"
        return p

    def review(self, t, tree, author):
        """Pide veredicto a un agente distinto del autor; si el revisor falla, prueba otro."""
        skip = {author}
        why = "no hay otro agente disponible para revisar"
        for _ in range(3):
            rev = self.router.pick("review", exclude=skip, timeout=1800)
            if not rev:
                return None, "", why
            skip.add(rev)
            prompt = (
                "Eres REVISOR (solo lectura: no modifiques archivos). Otro agente hizo esta tarea; tu no."
                "\n" + f"TAREA: {t['title']}\n{t['prompt']}\nCRITERIO: {t['done_when']}\n\n"
                f"CAMBIOS (git diff):\n{self.ws.diff(tree)}\n\n"
                "Verifica que el criterio se cumple de verdad (lee archivos, corre pruebas si existen). "
                "Se estricto con errores reales; no pidas mejoras esteticas. Termina con UNA linea final exacta:\n"
                "VEREDICTO: APROBADO\n  o\nVEREDICTO: FALTA - <que falta, concreto>")
            r = self.call(rev, prompt, tree, False, 900)
            if not r.ok:
                why = f"revisor {rev} fallo: {r.kind}"
                continue
            m = re.findall(r"VEREDICTO:\s*(APROBADO|FALTA)(.*)", r.text)
            if not m:
                why = f"el revisor {rev} no dio veredicto claro"
                continue
            v, _rest = m[-1]
            return v == "APROBADO", rev, (r.text[-1500:] if v == "FALTA" else "")
        return None, "", why

    def process(self, t):
        tid, critique, tried = t["id"], "", []
        tree = self.ws.task_tree(tid)
        intento = 0
        while intento < MAX_INTENTOS:
            ag = self.router.pick(t["kind"], prefer_not=tried[-1:] if intento >= 2 else ())
            if not ag:
                break
            r = self.call(ag, self.author_prompt(t, critique), tree, True, 1800)
            if r.kind == "limit" or r.kind == "auth":
                continue                       # no cuenta como intento: se reintenta con otro agente
            intento += 1
            tried.append(ag)
            self.store.set(tid, agent=ag, attempts=intento)
            if not r.ok:
                critique = f"El intento anterior fallo ({r.kind}): {r.error[:300]}"
                continue
            changed = self.ws.commit(tree, f"{tid}: {t['title']}")
            if not changed:
                critique = "No se produjo ningun cambio en los archivos. Deja el resultado en archivos de esta carpeta."
                continue
            ok, rev, why = self.review(t, tree, ag)
            if ok is None:
                critique = why
                self.log(f"[{tid}] revision no concluyente: {why}")
                break
            if not ok:
                critique = why
                self.log(f"[{tid}] FALTA (intento {intento}, autor {ag}, revisor {rev})")
                continue
            merged, msg = self.ws.merge(tid)
            if merged:
                self.store.set(tid, status="hecha", note=f"autor {ag}, revisor {rev}")
                self.log(f"[{tid}] HECHA (autor {ag}, revisor {rev})")
                return
            critique = ("Tu rama tiene conflicto con la rama de integracion. En esta carpeta corre "
                        f"`git merge {self.ws.integ_branch}`, resuelve conservando ambos cambios y haz commit.\n{msg}")
            self.log(f"[{tid}] conflicto al integrar")
        self.store.set(tid, status="bloqueada", note=critique[:500])
        self.log(f"[{tid}] BLOQUEADA tras {intento} intentos")
        pedir_humano(f"Tarea atascada: {t['title']}",
                     f"Run {self.run_id}, tarea {tid}. {intento} intentos con {', '.join(tried) or 'ningun agente'}.\n"
                     f"Ultimo problema: {critique[:600]}\nCarpeta: {tree}", None, self.run_id)

    # ---------- ciclo principal ----------
    def run(self):
        if self.ws.is_dirty():
            raise SystemExit("El repositorio tiene cambios sin guardar. Haz commit (o usa otra copia) antes de correr.")
        self.ws.prepare()
        self.log(f"=== run {self.run_id} | repo {self.repo} | rama base {self.ws.current_branch()}")
        tasks = self.plan()
        for t in tasks:
            self.store.add(t)
        running = {}
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            while True:
                for r in self.store.ready():
                    self.store.set(r["id"], status="en_curso")
                    running[ex.submit(self.process, r)] = r
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for f in done:
                    r = running.pop(f)
                    if f.exception():
                        self.log(f"[{r['id']}] ERROR interno: {f.exception()}")
                        self.store.set(r["id"], status="bloqueada", note=str(f.exception())[:300])
        self.report()

    def report(self):
        rows = self.store.all()
        hechas = sum(r["status"] == "hecha" for r in rows)
        lines = [f"# Reporte run {self.run_id}", f"Objetivo: {self.goal}", "",
                 f"Rama de integracion: `{self.ws.integ_branch}` ({hechas}/{len(rows)} tareas hechas)", ""]
        for r in rows:
            lines.append(f"- [{r['status']}] {r['id']} {r['title']} ({r['agent']}, {r['attempts']} intentos) {r['note']}")
        if self.apply and hechas == len(rows):
            ok, msg = self.ws.apply_to_repo()
            lines.append(f"\nApply a la rama actual: {'OK' if ok else 'NO ('+msg+')'}")
        elif hechas:
            lines.append(f"\nPara aplicar lo hecho a tu rama actual:\n"
                         f"`git -C \"{self.repo}\" merge --ff-only {self.ws.integ_branch}`")
        (self.run_dir / "REPORTE.md").write_text("\n".join(lines), encoding="utf-8")
        self.log("\n".join(lines))
