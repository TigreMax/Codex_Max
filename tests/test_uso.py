import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from codexmax.adapters import Agy, Claude, Codex, Result
from codexmax.orchestrator import Orchestrator
from codexmax.uso import main_uso, reporte_consumo
from codexmax.__main__ import main


class Extraccion(unittest.TestCase):
    def run_adapter(self, adapter, out, rc=0, timedout=False, err=""):
        def execute(cmd, *args):
            if isinstance(adapter, Codex):
                Path(cmd[cmd.index("-o") + 1]).write_text("respuesta", encoding="utf-8")
            return rc, out, err, 1.25, timedout
        with patch("codexmax.adapters._exec", side_effect=execute), \
                patch("codexmax.adapters.mcp_allow_rules", return_value=[]), \
                patch("codexmax.adapters.shutil.which", return_value="cli"):
            return adapter.run("prompt", ".")

    def test_claude(self):
        out = json.dumps(dict(result="OK", usage=dict(input_tokens=100, output_tokens=20,
                              cache_creation_input_tokens=30, cache_read_input_tokens=40),
                              total_cost_usd=0.02, duration_ms=1250))
        self.assertEqual(self.run_adapter(Claude(), out).uso,
                         dict(tokens_in=100, tokens_out=20, tokens_total=190, costo_usd=0.02))

    def test_agy(self):
        out = json.dumps(dict(response="OK", status="SUCCESS", usage=dict(input_tokens=100,
                              output_tokens=20, thinking_tokens=30, cache_read_tokens=40, total_tokens=190)))
        self.assertEqual(self.run_adapter(Agy(), out).uso,
                         dict(tokens_in=100, tokens_out=20, tokens_total=190))

    def test_codex(self):
        self.assertEqual(self.run_adapter(Codex(), "texto\ntokens used\n4,635\n").uso,
                         dict(tokens_total=4635))
        self.assertEqual(self.run_adapter(Codex(), "tokens used\n123\n").uso, dict(tokens_total=123))
        self.assertEqual(self.run_adapter(Codex(), "sin datos").uso, {})
        # la CLI real imprime los tokens por stderr
        self.assertEqual(self.run_adapter(Codex(), "OK", err="codex\nOK\ntokens used\n9,436\n").uso,
                         dict(tokens_total=9436))

    def test_raros_y_ausentes(self):
        for adapter in (Claude(), Agy()):
            for out in ("", "{mal", "[]", '{"usage": null}', '{"usage": []}',
                        '{"result": {}, "response": [], "usage": {"input_tokens": "secreto", '
                        '"output_tokens": -1, "total_tokens": true}, "total_cost_usd": NaN}'):
                with self.subTest(agent=adapter.name, out=out):
                    self.assertEqual(self.run_adapter(adapter, out).uso, {})

    def test_conserva_uso_en_fallos(self):
        for adapter, data in ((Claude(), dict(result="quota", is_error=True)),
                              (Agy(), dict(response="quota", status="ERROR"))):
            data["usage"] = dict(input_tokens=2, output_tokens=0)
            result = self.run_adapter(adapter, json.dumps(data), rc=1)
            self.assertFalse(result.ok)
            self.assertEqual(result.uso["tokens_total"], 2)
        self.assertEqual(self.run_adapter(Codex(), "tokens used\n4,635\n", timedout=True).uso,
                         dict(tokens_total=4635))

    def test_default_independiente(self):
        a, b = Result(True), Result(True)
        a.uso["tokens_total"] = 1
        self.assertEqual(b.uso, {})


class RegistroYConsulta(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_call_y_reporte(self):
        with patch("codexmax.orchestrator.Workspace"), patch("codexmax.orchestrator.Store"):
            o = Orchestrator(self.root, "objetivo", self.root / "run", "run")
        o.store.all.return_value = []
        o.log = Mock()
        agent = Mock()
        agent.run.side_effect = [Result(True, "RESPUESTA_PRIVADA", seconds=1.5,
                                        uso=dict(tokens_in=3, tokens_out=4, tokens_total=7,
                                                 costo_usd=0.01, prompt="NO_GUARDAR")),
                                 Result(False, "RESPUESTA_PRIVADA", "quota", "limit", 2)]
        with patch.dict("codexmax.orchestrator.ADAPTERS", codex=agent), \
                patch("codexmax.orchestrator.time.time", return_value=1234):
            o.call("codex", "PROMPT_PRIVADO", self.root, True, 10)
            o.call("codex", "PROMPT_PRIVADO", self.root, False, 10)
        raw = (o.run_dir / "uso.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("PRIVADO", raw)
        self.assertNotIn("PRIVADA", raw)
        self.assertNotIn("NO_GUARDAR", raw)
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(rows[0], dict(ts=1234, agente="codex", modelo="gpt-6-sol", esfuerzo="medium", escribe=True, kind="ok",
                                      segundos=1.5, tokens_in=3, tokens_out=4, tokens_total=7, costo_usd=0.01))
        self.assertEqual(rows[1], dict(ts=1234, agente="codex", modelo="gpt-6-sol", esfuerzo="medium", escribe=False, kind="limit", segundos=2))
        o.report()
        report = (o.run_dir / "REPORTE.md").read_text(encoding="utf-8")
        self.assertIn("## Consumo", report)
        self.assertIn("| codex | gpt-6-sol | 2 | 7 | 3.50 | 1 |", report)

    def test_ventanas_corrupcion_y_cli(self):
        now = 2_000_000
        run = self.root / "run"
        run.mkdir()
        (self.root / "antigua_sin_uso").mkdir()
        rows = [dict(ts=now-age, agente="codex", tokens_total=tokens)
                for age, tokens in ((0, 1), (5*3600, 2), (5*3600+1, 4),
                                    (7*86400, 8), (7*86400+1, 16))]
        rows.append(dict(ts=now, agente="claude"))
        rows.append(dict(ts=now, agente="codex", modelo="gpt-6-sol", tokens_total=9))
        (run / "uso.jsonl").write_text(
            "roto\n[]\nnull\n{\"ts\": \"raro\"}\n" +
            "\n".join(json.dumps(row) for row in rows) + "\n{truncado", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            main_uso(self.root, now)
        text = output.getvalue()
        self.assertIn("codex | (por defecto) | 2 / 3 | 4 / 15 | 5 / 31", text)
        self.assertIn("codex | gpt-6-sol | 1 / 9 | 1 / 9 | 1 / 9", text)
        self.assertIn("claude | (por defecto) | 1 / 0 | 1 / 0 | 1 / 0", text)
        report = "\n".join(reporte_consumo(run / "uso.jsonl"))
        self.assertIn("| codex | (por defecto) | 5 | 31 |", report)
        self.assertIn("| codex | gpt-6-sol | 1 | 9 |", report)
        self.assertIn("conteos locales", text)
        self.assertIn("no incluyen el uso fuera de Codex Max", text)
        with patch("sys.argv", ["codexmax", "uso"]), \
                patch("codexmax.__main__.ROOT", self.root.parent), \
                patch("codexmax.uso.main_uso") as command:
            main()
        command.assert_called_once_with(self.root.parent / "runs")

    def test_sin_corridas(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main_uso(self.root / "no_existe", 1234)
        self.assertIn("Sin consumo registrado", output.getvalue())
        self.assertIn("conteos locales", output.getvalue())


if __name__ == "__main__":
    unittest.main()
