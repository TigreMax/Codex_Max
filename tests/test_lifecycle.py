import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codexmax.__main__ import main
from codexmax.lifecycle import process_alive, read_meta, recover, write_meta
from codexmax.orchestrator import Orchestrator
from codexmax.status import formatear, listar_corridas
from codexmax.store import Store
from codexmax.workspace import Workspace


class Lifecycle(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.run_dir = self.root / "run-1"
        self.run_dir.mkdir()
        self.store = Store(self.run_dir / "state.db")
        self.addCleanup(self.store.db.close)
        self.meta = dict(repo=str(self.root), goal="Objetivo de prueba", apply=True,
                         workers=2, aceptar=["ejemplo.txt"], started="fecha inicial", pid=2147483647)
        for i, state in enumerate(("en_curso", "pendiente", "bloqueada", "omitida", "hecha", "cerrada")):
            tid = str(i)
            self.store.add(dict(id=tid, title=tid, prompt="prueba"))
            self.store.set(tid, status=state, attempts=2, note="nota previa")
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def save_meta(self):
        write_meta(self.run_dir, self.meta)

    def test_process_detection(self):
        self.assertTrue(process_alive(os.getpid()))
        self.assertFalse(process_alive(2147483647))
        for pid in (None, -1, 0):
            self.assertFalse(process_alive(pid))

    def test_close_legacy_preserves_files_and_terminal_tasks(self):
        artifact = self.run_dir / "wt" / "t1" / "resultado.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("conservar", encoding="utf-8")
        with patch.object(Workspace, "apply_to_repo") as apply:
            recover("run-1", self.root, close=True)
        apply.assert_not_called()
        rows = self.store.all()
        self.assertEqual([r["status"] for r in rows],
                         ["cerrada", "cerrada", "bloqueada", "omitida", "hecha", "cerrada"])
        for row in rows[:2]:
            self.assertEqual(row["note"], "cerrada por el jefe")
            self.assertEqual(row["attempts"], 2)
        self.assertEqual(rows[2]["note"], "nota previa")
        self.assertEqual(artifact.read_text(encoding="utf-8"), "conservar")
        self.assertIn("cerrada por el jefe", (self.run_dir / "REPORTE.md").read_text(encoding="utf-8"))
        self.assertIsNone(read_meta(self.run_dir))

    def test_close_with_meta_never_applies(self):
        self.save_meta()
        with patch.object(Workspace, "apply_to_repo") as apply:
            recover("run-1", self.root, close=True)
        apply.assert_not_called()
        self.assertIn("finished", read_meta(self.run_dir))

    def test_reject_live_process_without_changes(self):
        self.meta["pid"] = os.getpid()
        self.save_meta()
        before = self.store.all()
        for close in (True, False):
            with self.subTest(close=close), self.assertRaisesRegex(SystemExit, "sigue vivo"):
                recover("run-1", self.root, close=close)
        self.assertEqual(before, self.store.all())
        self.assertEqual(self.meta, read_meta(self.run_dir))
        self.assertFalse((self.run_dir / "REPORTE.md").exists())

    def test_resume_without_meta_suggests_close(self):
        before = self.store.all()
        with self.assertRaisesRegex(SystemExit, "meta.json.*close"):
            recover("run-1", self.root)
        self.assertEqual(before, self.store.all())

    def check_resume(self, retry):
        self.save_meta()
        seen = []

        def process(orchestrator, task):
            seen.append(task["id"])
            self.assertEqual(task["attempts"], 2)
            self.assertEqual(orchestrator.goal, self.meta["goal"])
            self.assertEqual(orchestrator.repo, self.root)
            self.assertTrue(orchestrator.apply)
            self.assertEqual(orchestrator.workers, 2)
            self.assertEqual(orchestrator.aceptar, {"ejemplo.txt"})
            active = read_meta(self.run_dir)
            self.assertEqual(active["pid"], os.getpid())
            self.assertNotIn("finished", active)
            orchestrator.store.set(task["id"], status="hecha")

        with patch.object(Orchestrator, "plan", side_effect=AssertionError("no planificar")), \
                patch.object(Orchestrator, "call", side_effect=AssertionError("no agentes")), \
                patch.object(Orchestrator, "process", process):
            recover("run-1", self.root, reintentar=retry)
        self.assertEqual(set(seen), {"0", "1", "2", "3"} if retry else {"0", "1"})
        rows = self.store.all()
        self.assertTrue(all(r["status"] == "hecha" for r in rows if r["id"] in seen))
        self.assertTrue(all(r["attempts"] == 2 for r in rows))
        self.assertEqual(rows[5]["status"], "cerrada")
        if not retry:
            self.assertEqual([r["status"] for r in rows[2:4]], ["bloqueada", "omitida"])
        self.assertTrue((self.run_dir / "REPORTE.md").is_file())
        meta = read_meta(self.run_dir)
        self.assertEqual(meta["started"], self.meta["started"])
        self.assertIn("finished", meta)

    def test_resume(self):
        self.check_resume(False)

    def test_resume_retry(self):
        self.check_resume(True)

    def test_status_interrupted_legacy_dead_and_live(self):
        self.assertIn("INTERRUMPIDA", formatear(listar_corridas(self.root)))
        self.save_meta()
        self.assertIn("INTERRUMPIDA", formatear(listar_corridas(self.root)))
        self.meta["pid"] = os.getpid()
        self.save_meta()
        self.assertNotIn("INTERRUMPIDA", formatear(listar_corridas(self.root)))
        for row in self.store.all():
            self.store.set(row["id"], status="cerrada")
        self.meta["pid"] = 2147483647
        self.save_meta()
        self.assertNotIn("INTERRUMPIDA", formatear(listar_corridas(self.root)))

    def test_run_metadata_normal_and_interrupted(self):
        orchestrator = Orchestrator(self.root, "objetivo", self.run_dir, "run-1",
                                    workers=2, aceptar=["ejemplo.txt"])
        self.addCleanup(orchestrator.store.db.close)
        with patch.object(Workspace, "is_dirty", return_value=False), \
                patch("codexmax.orchestrator.guard.escanear_repo", return_value=[]), \
                patch.object(Workspace, "prepare"), \
                patch.object(Workspace, "current_branch", return_value="main"), \
                patch.object(Orchestrator, "plan", return_value=[]), \
                patch.object(Orchestrator, "execute") as execute:
            orchestrator.run()
            meta = read_meta(self.run_dir)
            self.assertEqual(meta["pid"], os.getpid())
            self.assertEqual(meta["repo"], str(self.root.resolve()))
            self.assertEqual(meta["goal"], "objetivo")
            self.assertEqual(meta["workers"], 2)
            self.assertEqual(meta["aceptar"], ["ejemplo.txt"])
            self.assertFalse(meta["apply"])
            self.assertIn("started", meta)
            self.assertIn("finished", meta)
            execute.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                orchestrator.run()
            self.assertNotIn("finished", read_meta(self.run_dir))

    def test_cli_dispatch(self):
        for args, retry, close in ((["resume", "run-1"], False, False),
                                   (["resume", "run-1", "--reintentar"], True, False),
                                   (["close", "run-1"], False, True)):
            with patch("sys.argv", ["codexmax", *args]), \
                    patch("codexmax.__main__.ROOT", self.root), \
                    patch("codexmax.lifecycle.recover") as recovery:
                main()
                recovery.assert_called_once_with("run-1", self.root / "runs", retry, close)


if __name__ == "__main__":
    unittest.main()
