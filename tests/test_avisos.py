import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from codexmax import avisos, core
from codexmax.__main__ import main
from codexmax.orchestrator import Orchestrator


class Avisos(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / "avisos.log"
        for target, value in (("LOG", self.log), ("_ultimos", {})):
            self.enterContext(patch.object(avisos, target, value))
        self.enterContext(patch.object(avisos.sys, "platform", "win32"))
        self.enterContext(patch.dict(os.environ, {"CODEXMAX_SIN_AVISOS": "0"}))
        self.run = self.enterContext(patch.object(avisos.subprocess, "run"))

    def entries(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_environment_only_and_hidden_timeout(self):
        title = "Titulo <&> ' \" $(malicioso)"
        body = "Texto `codigo`; & <xml>\nsegunda linea"
        avisos.avisar(title, body)
        args, kwargs = self.run.call_args
        for value in (title, body):
            self.assertNotIn(value, str(args))
            self.assertNotIn(value, avisos._SCRIPT)
        self.assertEqual(kwargs["env"]["CODEXMAX_AVISO_TITULO"], title)
        self.assertEqual(kwargs["env"]["CODEXMAX_AVISO_TEXTO"], body)
        self.assertEqual(kwargs["timeout"], 10)
        self.assertIn("Hidden", args[0])
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertIn("::Escape($env:CODEXMAX_AVISO_TITULO)", avisos._SCRIPT)
        self.assertIn("::Escape($env:CODEXMAX_AVISO_TEXTO)", avisos._SCRIPT)
        self.assertIn(r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe", avisos._SCRIPT)
        self.assertEqual(self.entries()[0]["texto"], body)

    def test_dedup_title_ten_minutes_logs_every_call(self):
        with patch.object(avisos.time, "monotonic", side_effect=[0, 599, 599, 600]):
            avisos.avisar("uno", "primero")
            avisos.avisar("uno", "otro texto")
            avisos.avisar("dos", "distinto titulo")
            avisos.avisar("uno", "diez minutos")
        self.assertEqual(self.run.call_count, 3)
        self.assertEqual(len(self.entries()), 4)

    def test_failures_never_escape(self):
        for i, error in enumerate((OSError("fallo"), subprocess.TimeoutExpired("powershell", 10))):
            self.run.side_effect = error
            avisos.avisar(str(i), "mensaje")
        self.assertEqual(len(self.entries()), 2)
        with patch.object(avisos, "LOG", self.root):  # directorio, no escribible como archivo
            avisos.avisar("log falla", "mensaje")
        self.assertEqual(self.run.call_count, 3)

    def test_non_windows_logs_only(self):
        with patch.object(avisos.sys, "platform", "linux"):
            avisos.avisar("titulo", "texto")
        self.run.assert_not_called()
        self.assertEqual(len(self.entries()), 1)

    def test_env_disables_only_toast(self):
        with patch.dict(os.environ, {"CODEXMAX_SIN_AVISOS": "1"}):
            avisos.avisar("titulo", "texto")
        self.run.assert_not_called()
        self.assertEqual(len(self.entries()), 1)

    def test_cli_disables_only_toast_and_restores_environment(self):
        with patch("sys.argv", ["codexmax", "run", "--repo", ".", "--goal", "prueba", "--sin-avisos"]), \
                patch("codexmax.orchestrator.Orchestrator") as orchestrator:
            orchestrator.return_value.run.side_effect = lambda: avisos.avisar("fin", "prueba")
            main()
        self.run.assert_not_called()
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(os.environ["CODEXMAX_SIN_AVISOS"], "0")

    def test_new_human_request_only(self):
        pending = self.root / "por_aprobar.md"
        with patch.object(core, "POR_APROBAR", pending), patch.object(core, "avisar") as notify:
            core.pedir_humano("Ayuda", "Detalle")
            core.pedir_humano("Ayuda", "Detalle")
            notify.assert_called_once()
            self.assertIn("Ayuda", pending.read_text(encoding="utf-8"))
            pending.write_text(pending.read_text(encoding="utf-8").replace("[PENDIENTE]", "[HECHO]"), encoding="utf-8")
            core.pedir_humano("Ayuda", "Otra solicitud")
            self.assertEqual(notify.call_count, 2)

    def test_pause_and_finish_triggers(self):
        o = Orchestrator(self.root, "prueba", self.root / "run", "run-1")
        self.addCleanup(o.store.db.close)
        for i, status in enumerate(("hecha", "bloqueada")):
            o.store.add(dict(id=str(i), title="tarea", prompt="prueba"))
            o.store.set(str(i), status=status)
        with patch.object(o, "report"), patch("codexmax.orchestrator.avisar") as notify:
            o.pause(core.CuotaAgotada(["codex"], 2000000000))
            o.execute()
            title, body = notify.call_args.args
            self.assertIn("PAUSADA POR CUOTA", title)
            self.assertIn(time.strftime("%Y-%m-%d %H:%M", time.localtime(2000000000)), body)
            self.assertIn("python -m codexmax resume run-1", body)
            o.pausada_hasta = None
            o.execute()
            self.assertEqual(notify.call_count, 2)
            self.assertIn("1/2 tareas hechas; 1 bloqueadas", notify.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
