"""El cerebro: planifica, reparte, hace revisar, reintenta e integra."""
import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from .adapters import ADAPTERS, GOOGLE_READ_ONLY, configured_mcp
from .core import Health, Router, Bitacora, pedir_humano, CuotaAgotada
from .store import Store
from .lifecycle import timestamp, write_meta, read_meta
from . import guard
from .workspace import Workspace
from .uso import limpiar_uso, reporte_consumo
from .avisos import avisar
from . import modelos
from .registro import registrar_uso
from .core import ROOT

MAX_INTENTOS = 4          # 2 con el mismo agente, 3.o con otro, 4.o ultimo
MODELO_NO_DISPONIBLE = re.compile(r"not found|unknown|invalid|not supported|no existe", re.I)
REGLAS = (
    "REGLAS: trabaja SOLO dentro de esta carpeta. No hagas git push ni publiques nada. "
    "No escribas claves ni contrasenas en archivos (usa variables de entorno). "
    "No leas ni abras archivos .env, claves (.pem, .key), ~/.ssh, ~/.aws ni las carpetas de otras "
    "herramientas (~/.codex, ~/.gemini, ~/.claude); si la tarea lo necesita, detente y dilo. "
    "No borres fuera de esta carpeta. "
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
    def __init__(self, repo, goal, run_dir, run_id, apply=False, workers=3, aceptar=(), espera_max_horas=6,
                 data_dir=None):
        self.repo, self.goal, self.run_id, self.apply = Path(repo), goal, run_id, apply
        self.aceptar = set(a.replace("\\", "/") for a in aceptar)
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log = Bitacora(self.run_dir / "bitacora.md")
        self.store = Store(self.run_dir / "state.db")
        self.health = Health()
        self.espera_max_horas = espera_max_horas
        self.router = Router(self.health, self.log, espera_max_horas * 3600)
        self.pause_lock = threading.Lock()
        self.uso_lock = threading.Lock()
        self.data_dir = Path(data_dir) if data_dir is not None else ROOT / "data"
        self.pausada_hasta = None
        self.ws = Workspace(repo, run_dir, run_id)
        self.workers = workers

    # ---------- llamadas a agentes ----------
    def call(self, agent, prompt, cwd, write, timeout, rol="code"):
        a = ADAPTERS[agent]
        modelo, esfuerzo = modelos.elegir(agent, rol)
        with self.health.sem[agent]:
            r = a.run(prompt, cwd, write=write, timeout=timeout, modelo=modelo, esfuerzo=esfuerzo)
            intentos = [(r, modelo, esfuerzo)]
            if (not r.ok and modelo and "model" in (r.error + "\n" + r.text).lower()
                    and MODELO_NO_DISPONIBLE.search(r.error + "\n" + r.text)):
                self.log(f"[{agent}] modelo {modelo} no disponible; reintento con modelo por defecto de la CLI")
                r = a.run(prompt, cwd, write=write, timeout=timeout)
                intentos.append((r, None, None))
        for result, used_model, used_effort in intentos:
            entry = dict(ts=time.time(), agente=agent, modelo=used_model, esfuerzo=used_effort,
                         escribe=bool(write), kind=result.kind, segundos=result.seconds)
            entry.update(limpiar_uso(getattr(result, "uso", {})))
            with self.uso_lock:
                with (self.run_dir / "uso.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                registrar_uso(entry, self.data_dir)
            self.log(f"[{agent}] {'escribe' if write else 'lee'} -> {result.kind} en {result.seconds:.0f}s"
                     + ("" if result.ok else f" | {result.error[-300:]!r}"))
            calls = self.run_dir / "llamadas"
            calls.mkdir(exist_ok=True)
            n = len(list(calls.iterdir())) + 1
            (calls / f"{n:03d}_{agent}_{'w' if write else 'r'}.txt").write_text(
                "PROMPT:\n" + prompt + f"\n\n--- RESULTADO ({result.kind}) ---\n" + result.text + "\n" + result.error,
                encoding="utf-8")
        if not write and Path(cwd).name != "_integracion":
            self.ws.reset(cwd)                 # el revisor/lector nunca deja cambios
        if r.kind == "limit":
            self.health.cooldown(agent, r.error + "\n" + r.text)
        elif r.kind == "auth":
            self.health.kill(agent, r.error)
            pedir_humano(f"Iniciar sesion en {agent}",
                         f"La CLI de {agent} no tiene sesion valida. Solo el jefe puede iniciarla.\n"
                         f"Detalle: {r.error[:300]}",
                         {"claude": "claude   (abrirlo una vez e iniciar sesion)", "codex": "codex login",
                          "agy": "agy  (abrirlo una vez e iniciar sesion)"}.get(agent),
                         self.run_id, path=self.run_dir / "por_aprobar.md")
        if r.ok:
            self.health.ok(agent)
        return r

    # ---------- planificacion ----------
    def plan(self):
        google = [s for s in configured_mcp() if s in GOOGLE_READ_ONLY]
        extra = (f"\nNota: el agente de investigacion (agy) puede ademas LEER (solo leer) estos servicios de "
                 f"Google del jefe: {', '.join(google)}. Usalo en tareas kind=research cuando haga falta.\n"
                 if google else "")
        prompt = (
            "Eres el planificador de un orquestador de agentes de programacion. "
            "Lee el proyecto (solo lectura) y divide el OBJETIVO en tareas pequenas y verificables.\n"
            f"OBJETIVO:\n{self.goal}\n{extra}\n"
            "Responde SOLO con JSON valido, sin texto extra, con esta forma:\n"
            '{"tasks":[{"id":"t1","title":"...","kind":"code|research|text",'
            '"prompt":"instrucciones completas y autocontenidas","done_when":"criterio comprobable",'
            '"deps":[]}]}\n'
            "Reglas: ids unicos; no incluyas tareas de publicar, enviar o hacer push. "
            "USA EL MENOR NUMERO DE TAREAS POSIBLE: cada tarea cuesta un ciclo completo de autor + revisor. "
            "Si el objetivo es chico o toca pocos archivos relacionados, devuelve UNA sola tarea. "
            "Solo separa en varias (maximo 5) cuando sean partes realmente independientes o de naturaleza distinta "
            "(por ejemplo investigar vs programar). NUNCA crees tareas aparte para 'documentar', 'escribir pruebas' "
            "o 'verificacion final': eso va dentro de la tarea que cambia el codigo. "
            "Si dos tareas tocan los mismos archivos, la segunda debe depender de la primera. "
            "Copia en el prompt de cada tarea las restricciones EXPLICITAS del objetivo (limites de longitud, "
            "archivos permitidos, formato) tal cual."
        )
        exclude = set()
        for _ in range(3):
            ag = self.router.pick("plan", exclude)
            if not ag:
                break
            r = self.call(ag, prompt, self.ws.integ, False, 600, "plan")
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
        while len(skip - {author}) < 3:
            rev = self.router.pick("review", exclude=skip)
            if not rev:
                return None, "", why
            prompt = (
                "Eres REVISOR (solo lectura: no modifiques archivos). Otro agente hizo esta tarea; tu no."
                "\n" + f"TAREA: {t['title']}\n{t['prompt']}\nCRITERIO: {t['done_when']}\n\n"
                f"CAMBIOS (git diff):\n{self.ws.diff(tree)}\n\n"
                "Verifica que el criterio se cumple de verdad (lee archivos, corre pruebas si existen). "
                "Ademas compara punto por punto el diff contra las RESTRICCIONES EXPLICITAS de la tarea "
                "(limites de longitud como 'una linea', archivos permitidos, formato pedido, cosas que no debia "
                "tocar). Si algo agrego de mas (informes, secciones, archivos no pedidos) o se paso de un limite, "
                "es FALTA aunque funcione. "
                "Se estricto con errores reales; no pidas mejoras esteticas. Termina con UNA linea final exacta:\n"
                "VEREDICTO: APROBADO\n  o\nVEREDICTO: FALTA - <que falta, concreto>")
            r = self.call(rev, prompt, tree, False, 900, "review")
            if r.kind == "limit":
                continue
            skip.add(rev)
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

    def pause(self, exc):
        with self.pause_lock:
            self.pausada_hasta = max(self.pausada_hasta or 0, exc.hasta)

    def process(self, t):
        try:
            self._process(t)
        except CuotaAgotada as exc:
            self.pause(exc)
            self.store.set(t["id"], status="pendiente")
            self.log(f"[{t['id']}] PAUSADA POR CUOTA")

    def _process(self, t):
        tid, critique, tried = t["id"], "", []
        tree = self.ws.task_tree(tid)
        intento = 0
        while intento < MAX_INTENTOS:
            ag = self.router.pick(t["kind"], prefer_not=tried[-1:] if intento >= 2 else ())
            if not ag:
                break
            r = self.call(ag, self.author_prompt(t, critique), tree, True, 1800, t["kind"])
            if r.kind == "limit" or r.kind == "auth":
                continue                       # no cuenta como intento: se reintenta con otro agente
            intento += 1
            tried.append(ag)
            self.store.set(tid, agent=ag, attempts=t["attempts"] + intento)
            if not r.ok:
                critique = f"El intento anterior fallo ({r.kind}): {r.error[:300]}"
                continue
            changed = self.ws.commit(tree, f"{tid}: {t['title']}")
            if not changed:
                critique = "No se produjo ningun cambio en los archivos. Deja el resultado en archivos de esta carpeta."
                continue
            fugas = guard.escanear_diff(self.ws.diff(tree, limit=10**7))
            if fugas:
                self.ws.restart(tree)       # borra el commit con el secreto: no debe llegar a la integracion
                detalle = "; ".join(f"{a}: {m}" for a, m in fugas[:5])
                critique = (f"FILTRO DE SECRETOS: tu cambio incluia lo que parece un secreto ({detalle}). Se descarto. "
                            "Rehaz la tarea sin escribir claves ni contrasenas en archivos: usa variables de entorno.")
                self.log(f"[{tid}] FILTRO: secreto detectado en el cambio de {ag} ({detalle}); cambio descartado")
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
                     f"Ultimo problema: {critique[:600]}\nCarpeta: {tree}", None, self.run_id,
                     path=self.run_dir / "por_aprobar.md")

    # ---------- ciclo principal ----------
    def run(self):
        meta = dict(repo=str(self.repo.resolve()), goal=self.goal, apply=self.apply,
                    workers=self.workers, aceptar=sorted(self.aceptar),
                    espera_max_horas=self.espera_max_horas,
                    started=timestamp(), pid=os.getpid())
        write_meta(self.run_dir, meta)
        if self.ws.is_dirty():
            raise SystemExit("El repositorio tiene cambios sin guardar. Haz commit (o usa otra copia) antes de correr.")
        # Filtro de secretos: el objetivo y los archivos que git rastrea van a 3 proveedores externos.
        tipos = guard.buscar_en_texto(self.goal)
        if tipos:
            raise SystemExit(f"FILTRO: el objetivo parece contener un secreto ({', '.join(tipos)}). No se envia a ningun agente.")
        hallazgos = guard.escanear_repo(self.repo, self.aceptar)
        if hallazgos:
            lista = "\n".join(f"  - {r}: {m}" for r, m in hallazgos[:20])
            pedir_humano("Archivos sensibles en el repositorio",
                         f"Run {self.run_id} NO inicio. Git rastrea archivos que parecen secretos y se enviarian a "
                         f"Codex, Claude y agy:\n{lista}\nSaquelos de git (git rm --cached) o, si estan bien, "
                         f"corra con --aceptar <ruta> para cada uno.", None, self.run_id,
                         path=self.run_dir / "por_aprobar.md")
            raise SystemExit("FILTRO: archivos sensibles en el repositorio:\n" + lista +
                             "\nQuitelos de git o use --aceptar <ruta> (detalle en por_aprobar.md).")
        self.ws.prepare()
        self.log(f"=== run {self.run_id} | repo {self.repo} | rama base {self.ws.current_branch()}")
        try:
            tasks = self.plan()
        except CuotaAgotada as exc:
            self.pause(exc)
            tasks = [dict(id="t1", title="Objetivo completo", kind="code",
                          prompt=self.goal, done_when="El objetivo se cumple.", deps=[])]
        for t in tasks:
            self.store.add(t)
        self.execute()
        self.save_outcome()

    def execute(self):
        """Ejecuta las tareas guardadas sin volver a planificar."""
        running = {}
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            while True:
                if self.pausada_hasta is None:
                    for r in self.store.ready():
                        with self.pause_lock:
                            if self.pausada_hasta is not None or len(running) >= self.workers:
                                break
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
        self.save_outcome()
        self.report()
        if self.pausada_hasta is not None:
            hora = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.pausada_hasta))
            avisar(f"PAUSADA POR CUOTA: {self.run_id}",
                   f"Reinicio: {hora}. Retomar: python -m codexmax resume {self.run_id}",
                   log_path=self.run_dir / "avisos.log")
        else:
            rows = self.store.all()
            hechas = sum(r["status"] == "hecha" for r in rows)
            bloqueadas = sum(r["status"] == "bloqueada" for r in rows)
            avisar(f"Corrida terminada: {self.run_id}",
                   f"{hechas}/{len(rows)} tareas hechas; {bloqueadas} bloqueadas.",
                   log_path=self.run_dir / "avisos.log")

    def save_outcome(self):
        meta = read_meta(self.run_dir)
        if meta is not None:
            if self.pausada_hasta is not None:
                meta["pausada_hasta"] = self.pausada_hasta
                meta.pop("finished", None)
            else:
                meta.pop("pausada_hasta", None)
                meta["finished"] = timestamp()
            write_meta(self.run_dir, meta)

    def report(self):
        rows = self.store.all()
        hechas = sum(r["status"] == "hecha" for r in rows)
        lines = [f"# Reporte run {self.run_id}", f"Objetivo: {self.goal}", "",
                 f"Rama de integracion: `{self.ws.integ_branch}` ({hechas}/{len(rows)} tareas hechas)", ""]
        if self.pausada_hasta is not None:
            hora = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.pausada_hasta))
            lines.extend([f"PAUSADA POR CUOTA hasta ~{hora}",
                          f"Retomar: python -m codexmax resume {self.run_id}", ""])
        for r in rows:
            lines.append(f"- [{r['status']}] {r['id']} {r['title']} ({r['agent']}, {r['attempts']} intentos) {r['note']}")
        if self.apply and hechas == len(rows):
            ok, msg = self.ws.apply_to_repo()
            lines.append(f"\nApply a la rama actual: {'OK' if ok else 'NO ('+msg+')'}")
        elif hechas:
            lines.append(f"\nPara aplicar lo hecho a tu rama actual:\n"
                         f"`git -C \"{self.repo}\" merge --ff-only {self.ws.integ_branch}`")
        lines.extend(reporte_consumo(self.run_dir / "uso.jsonl"))
        (self.run_dir / "REPORTE.md").write_text("\n".join(lines), encoding="utf-8")
        self.log("\n".join(lines))
