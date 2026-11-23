import io
import tempfile
import time
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codexmax import core
from codexmax.core import CuotaAgotada, Health, Router, parse_reset
from codexmax.lifecycle import read_meta, recover
from codexmax.orchestrator import Orchestrator
from codexmax.status import formatear, listar_corridas
from codexmax.workspace import git


class Cuotas(unittest.TestCase):
    def test_parse_reset(self):
        now = datetime(2026, 11, 23, 10, 0).timestamp()
        for text, seconds in (("in 2 hours 30 minutes", 9000),
                              ("in 45 minutes", 2700), ("en 3 horas", 10800),
                              ("in 7 days", 604800)):
            with self.subTest(text=text):
                self.assertEqual(parse_reset(text, now), now + seconds)
        for text in ("resets at 5:10 pm", "reset at 17:10", "a las 17:10"):
            with self.subTest(text=text):
                self.assertEqual(parse_reset(text, now),
                                 datetime(2026, 11, 23, 17, 10).timestamp())
                self.assertEqual(parse_reset(text, now + 10 * 3600),
                                 datetime(2026, 11, 24, 17, 10).timestamp())
        for text in ("quota exhausted", "", "reset at 25:00", "a las 17:99"):
            self.assertIsNone(parse_reset(text, now))

    def test_cli_wait_option(self):
        from codexmax.__main__ import main
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.argv", ["codexmax", "run", "--repo", ".", "--goal", "prueba",
                                    "--espera-max-horas", "2.5", "--salida", tmp]), \
                    patch("codexmax.__main__.ROOT", Path(tmp)), \
                    patch("codexmax.orchestrator.Orchestrator") as orchestrator:
                main()
        self.assertEqual(orchestrator.call_args.kwargs["espera_max_horas"], 2.5)
        orchestrator.return_value.run.assert_called_once_with()

    def test_health_backoff_reset_and_margin(self):
        with patch.object(core.time, "time", return_value=1000):
            h = Health()
            for seconds in (600, 1200, 1800, 1800):
                h.cooldown("codex", "mensaje desconocido")
                self.assertEqual(h.cool["codex"], 1000 + seconds)
            h.cooldown("agy", "")
            self.assertEqual(h.cool["agy"], 1600)
            h.ok("codex")
            self.assertTrue(h.available("codex"))
            h.cooldown("codex")
            self.assertEqual(h.cool["codex"], 1600)
            h.cooldown("codex", "in 45 minutes")
            self.assertEqual(h.cool["codex"], 3760)

    def test_router_pause_short_wait_and_unavailable(self):
        now = [1000]
        def sleep(seconds):
            now[0] += seconds
        fake = SimpleNamespace(installed=lambda: True)
        with patch.object(core, "ADAPTERS", {"codex": fake}), \
                patch.object(core.time, "time", side_effect=lambda: now[0]), \
                patch.object(core.time, "sleep", side_effect=sleep) as sleeping:
            h = Health()
            router = Router(h, lambda msg: None)
            h.cooldown("codex", "in 7 days")
            with self.assertRaises(CuotaAgotada) as caught:
                router.pick("code")
            self.assertEqual(caught.exception.agentes, ["codex"])
            self.assertEqual(caught.exception.hasta, h.cool["codex"])
            sleeping.assert_not_called()
            h.ok("codex")
            h.cooldown("codex")
            self.assertEqual(router.pick("code"), "codex")
            self.assertEqual(now[0], 1600)
            h.kill("codex", "sin sesion")
            self.assertIsNone(router.pick("code"))
            self.assertIsNone(router.pick("review"))


class CorridaCuota(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("codexmax.orchestrator.avisar"))
        self.enterContext(patch("codexmax.core.avisar"))

    def test_pause_resume(self):
        # Todo queda dentro del workspace, incluso los worktrees temporales.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp, ExitStack() as stack:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            git(repo, "init")
            (repo / "base.txt").write_text("base", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "base")
            run_dir = root / "runs" / "prueba"
            pending = root / "por_aprobar.md"
            limited = [True]
            writes = []

            def result(kind="ok", text="", error=""):
                return SimpleNamespace(ok=kind == "ok", kind=kind, text=text,
                                       error=error, seconds=0)

            def author(prompt, cwd, write, timeout, modelo=None, esfuerzo=None):
                self.assertTrue(write)
                writes.append(Path(cwd).name)
                if limited[0]:
                    return result("limit", error="in 7 days")
                (Path(cwd) / (Path(cwd).name + ".txt")).write_text("hecho", encoding="utf-8")
                return result(text="terminado")

            def reviewer(prompt, cwd, write, timeout, modelo=None, esfuerzo=None):
                self.assertFalse(write)
                return result(text="VEREDICTO: APROBADO")

            adapters = {
                "codex": SimpleNamespace(installed=lambda: True, run=author),
                "claude": SimpleNamespace(installed=lambda: True, run=reviewer),
            }
            stack.enter_context(patch("codexmax.core.ADAPTERS", adapters))
            stack.enter_context(patch("codexmax.orchestrator.ADAPTERS", adapters))
            stack.enter_context(patch("codexmax.core.POR_APROBAR", pending))
            stack.enter_context(patch("codexmax.core.time.time", return_value=1800000000))
            sleeping = stack.enter_context(patch("codexmax.core.time.sleep"))
            stack.enter_context(redirect_stdout(io.StringIO()))
            tasks = [dict(id=f"t{i}", title=f"Tarea {i}", prompt="crear resultado",
                          kind="code", done_when="archivo creado", deps=[]) for i in (1, 2)]
            o = Orchestrator(repo, "crear resultado", run_dir, "prueba", workers=1)
            try:
                with patch.object(o, "plan", return_value=tasks):
                    o.run()
                self.assertEqual(writes, ["t1"])
                self.assertEqual([r["status"] for r in o.store.all()], ["pendiente"] * 2)
                self.assertEqual([r["attempts"] for r in o.store.all()], [0, 0])
                meta = read_meta(run_dir)
                self.assertEqual(meta["pausada_hasta"], 1800000000 + 7 * 86400 + 60)
                self.assertNotIn("finished", meta)
                self.assertFalse(pending.exists())
                report = (run_dir / "REPORTE.md").read_text(encoding="utf-8")
                self.assertIn("PAUSADA POR CUOTA hasta ~", report)
                self.assertIn("python -m codexmax resume prueba", report)
                status = formatear(listar_corridas(root / "runs"))
                hora = time.strftime("%H:%M", time.localtime(meta["pausada_hasta"]))
                self.assertIn(f"PAUSADA POR CUOTA (hasta {hora})", status)
                self.assertNotIn("INTERRUMPIDA", status)
                with patch("codexmax.lifecycle.process_alive", return_value=False):
                    recover("prueba", root / "runs")
                self.assertIn("pausada_hasta", read_meta(run_dir))
                self.assertNotIn("finished", read_meta(run_dir))
                self.assertEqual([r["attempts"] for r in o.store.all()], [0, 0])
                limited[0] = False
                with patch("codexmax.lifecycle.process_alive", return_value=False):
                    recover("prueba", root / "runs")
                self.assertEqual([r["status"] for r in o.store.all()], ["hecha"] * 2)
                self.assertNotIn("pausada_hasta", read_meta(run_dir))
                self.assertIn("finished", read_meta(run_dir))
                self.assertFalse(pending.exists())
                sleeping.assert_not_called()
            finally:
                o.store.db.close()

    def test_execute_drains_running_tasks(self):
        import threading
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            o = Orchestrator(tmp, "prueba", Path(tmp) / "run", "prueba", workers=2)
            started = threading.Event()
            paused = threading.Event()
            seen = []
            def process(task):
                seen.append(task["id"])
                if task["id"] == "t1":
                    self.assertTrue(started.wait(5))
                    o.pause(CuotaAgotada(["codex"], 2000000000))
                    o.store.set("t1", status="pendiente")
                    paused.set()
                else:
                    started.set()
                    self.assertTrue(paused.wait(5))
                    o.store.set(task["id"], status="hecha")
            try:
                for i in range(1, 4):
                    o.store.add(dict(id=f"t{i}", title="tarea", prompt="prueba"))
                with patch.object(o, "process", side_effect=process), redirect_stdout(io.StringIO()):
                    o.execute()
                self.assertEqual(set(seen), {"t1", "t2"})
                self.assertEqual([r["status"] for r in o.store.all()],
                                 ["pendiente", "hecha", "pendiente"])
            finally:
                o.store.db.close()

    def test_review_quota_propagates_without_blocking(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            o = Orchestrator(tmp, "prueba", Path(tmp) / "run", "prueba")
            try:
                o.store.add(dict(id="t1", title="tarea", prompt="prueba"))
                task = o.store.all()[0]
                success = SimpleNamespace(ok=True, kind="ok")
                with patch.object(o.ws, "task_tree", return_value=Path(tmp)),                         patch.object(o.router, "pick", return_value="codex"),                         patch.object(o, "call", return_value=success),                         patch.object(o.ws, "commit", return_value=True),                         patch.object(o.ws, "diff", return_value=""),                         patch.object(o, "review", side_effect=CuotaAgotada(["claude"], 2000000000)),                         patch("codexmax.orchestrator.pedir_humano") as ask,                         redirect_stdout(io.StringIO()):
                    o.process(task)
                self.assertEqual(o.store.all()[0]["status"], "pendiente")
                self.assertEqual(o.store.all()[0]["attempts"], 1)
                self.assertEqual(o.pausada_hasta, 2000000000)
                ask.assert_not_called()
            finally:
                o.store.db.close()

    def test_call_success_resets_health(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            o = Orchestrator(tmp, "prueba", Path(tmp) / "run", "prueba")
            try:
                fake = SimpleNamespace(run=lambda *a, **kw: SimpleNamespace(
                    ok=True, kind="ok", text="", error="", seconds=0))
                o.health.cooldown("codex")
                with patch("codexmax.orchestrator.ADAPTERS", {"codex": fake}), \
                        redirect_stdout(io.StringIO()):
                    o.call("codex", "prueba", tmp, True, 1)
                self.assertNotIn("codex", o.health.limits)
            finally:
                o.store.db.close()


if __name__ == "__main__":
    unittest.main()
