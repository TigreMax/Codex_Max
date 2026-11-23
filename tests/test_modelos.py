import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codexmax import modelos
from codexmax.adapters import Agy, Claude, Codex, Result
from codexmax.orchestrator import Orchestrator


class Eleccion(unittest.TestCase):
    def test_tabla_completa(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp, patch.object(modelos, "ROOT", Path(tmp)):
            for agent, roles in modelos.DEFAULTS.items():
                for role, pair in roles.items():
                    with self.subTest(agent=agent, role=role):
                        self.assertEqual(modelos.elegir(agent, role), pair)

    def test_anulacion_y_archivo_corrupto(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp, patch.object(modelos, "ROOT", Path(tmp)):
            config = Path(tmp) / "modelos.json"
            config.write_text(json.dumps({"codex": {"code": ["gpt-6.2-astra", "high"]}}), encoding="utf-8")
            self.assertEqual(modelos.elegir("codex", "code"), ("gpt-6.2-astra", "high"))
            self.assertEqual(modelos.elegir("codex", "text"), ("gpt-6-sol", "low"))
            for data in ("{roto", "[]", '{"codex":{"code":["bad model","high"]}}'):
                config.write_text(data, encoding="utf-8")
                self.assertEqual(modelos.elegir("codex", "code"), ("gpt-6-sol", "medium"))


class Comandos(unittest.TestCase):
    def command(self, adapter, **kwargs):
        commands = []

        def execute(cmd, *args):
            commands.append(cmd[:])
            if isinstance(adapter, Codex):
                Path(cmd[cmd.index("-o") + 1]).write_text("OK", encoding="utf-8")
                return 0, "", "", 1, False
            key = "response" if isinstance(adapter, Agy) else "result"
            return 0, json.dumps({key: "OK"}), "", 1, False

        with patch("codexmax.adapters._exec", side_effect=execute), \
                patch("codexmax.adapters.mcp_allow_rules", return_value=[]), \
                patch("codexmax.adapters.shutil.which", return_value="cli"):
            adapter.run("prompt", ".", **kwargs)
        cmd = commands[0]
        if isinstance(adapter, Codex):
            cmd[cmd.index("-o") + 1] = "<salida>"
        return cmd

    def test_comandos_sin_opciones_y_con_modelo(self):
        cases = (
            (Codex(), ["cli", "exec", "-s", "read-only", "--ephemeral", "-C", ".",
                       "-o", "<salida>", "-"], ["-m", "gpt-6-sol", "-c", 'model_reasoning_effort="medium"']),
            (Agy(), ["cli", "-p", "SOLO LECTURA: no crees ni modifiques archivos; responde en texto.\nprompt",
                     "--output-format", "json", "--sandbox", "--print-timeout", "1800s"],
             ["--model", "gemini-4-hydrogen-medium"]),
            (Claude(), ["cli", "-p", "--output-format", "json", "--no-session-persistence",
                        "--disallowedTools", "Bash(git push*) " + Claude.NO_LEER,
                        "--disallowedTools", "Edit Write NotebookEdit", "--allowedTools", Claude.SAFE],
             ["--model", "sonnet", "--effort", "medium"]),
        )
        for adapter, base, added in cases:
            with self.subTest(agent=adapter.name):
                self.assertEqual(self.command(adapter), base)
                model = {"codex": "gpt-6-sol", "agy": "gemini-4-hydrogen", "claude": "sonnet"}[adapter.name]
                expected = base[:-1] + added + base[-1:] if isinstance(adapter, Codex) else base + added
                self.assertEqual(self.command(adapter, modelo=model, esfuerzo="medium"), expected)

    def test_caracteres_invalidos_se_ignoran(self):
        for adapter in (Codex(), Agy(), Claude()):
            with self.subTest(agent=adapter.name):
                base = self.command(adapter)
                self.assertEqual(self.command(adapter, modelo="bad;model", esfuerzo="high space"), base)
                self.assertEqual(self.command(adapter, modelo=123, esfuerzo=["high"]), base)


class Reintento(unittest.TestCase):
    def test_modelo_no_encontrado_reintenta_una_vez(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp, \
                patch("codexmax.orchestrator.Workspace"), patch("codexmax.orchestrator.Store"):
            o = Orchestrator(tmp, "objetivo", Path(tmp) / "run", "run")
            o.log = Mock()
            agent = Mock()
            agent.run.side_effect = [Result(False, error="Model not found", kind="error"),
                                     Result(True, text="OK")]
            with patch.dict("codexmax.orchestrator.ADAPTERS", codex=agent):
                result = o.call("codex", "prompt", tmp, True, 10, "text")
            self.assertTrue(result.ok)
            self.assertEqual(agent.run.call_count, 2)
            self.assertEqual(agent.run.call_args_list[0].kwargs["modelo"], "gpt-6-sol")
            self.assertEqual(agent.run.call_args_list[0].kwargs["esfuerzo"], "low")
            self.assertNotIn("modelo", agent.run.call_args_list[1].kwargs)
            self.assertNotIn("esfuerzo", agent.run.call_args_list[1].kwargs)
            rows = [json.loads(line) for line in (o.run_dir / "uso.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(r["modelo"], r["esfuerzo"]) for r in rows],
                             [("gpt-6-sol", "low"), (None, None)])
            self.assertIn("reintento con modelo por defecto", " ".join(c.args[0] for c in o.log.call_args_list))


if __name__ == "__main__":
    unittest.main()
