import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codexmax.__main__ import main
from codexmax.lifecycle import read_meta, recover, write_meta
from codexmax.orchestrator import Orchestrator
from codexmax.registro import registrar
from codexmax.status import formatear, listar_corridas
from codexmax.store import Store
from codexmax.uso import main_uso
from codexmax.workspace import Workspace


class Ubicacion(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.taller = self.root / "taller"
        self.taller.mkdir()
        self.repo = self.root / "proyecto" / "repo"
        self.repo.mkdir(parents=True)
        self.git("init", "-q")
        (self.repo / "README.txt").write_text("prueba", encoding="utf-8")
        self.git("add", "README.txt")
        self.git("-c", "user.name=Prueba", "-c", "user.email=prueba@local",
                 "commit", "-qm", "inicio")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def cli(self, salida=None):
        args = ["codexmax", "run", "--repo", str(self.repo), "--goal", "prueba"]
        if salida is not None:
            args.extend(["--salida", str(salida)])
        with patch("sys.argv", args), patch("codexmax.__main__.ROOT", self.taller), \
                patch("codexmax.orchestrator.Orchestrator"):
            main()
        rows = [json.loads(line) for line in (self.taller / "data" / "registro.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        return rows[-1]

    def test_run_exclusion_registro_y_worktrees(self):
        row = self.cli()
        run_dir = Path(row["ruta"])
        self.assertEqual(run_dir.parent, self.repo / "_codexmax" / "runs")
        self.assertEqual(set(row), {"id", "ruta", "repo", "ts"})
        self.assertEqual(row["repo"], str(self.repo.resolve()))
        self.assertTrue(run_dir.is_dir())
        self.cli()
        exclude = self.repo / self.git("rev-parse", "--git-path", "info/exclude")
        self.assertEqual(exclude.read_text(encoding="utf-8").splitlines().count("_codexmax/"), 1)
        self.assertEqual(self.git("status", "--porcelain"), "")
        ws = Workspace(self.repo, run_dir, "prueba-worktree")
        ws.prepare()
        tree = ws.task_tree("t1")
        self.assertEqual(subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                         cwd=tree, check=True, capture_output=True, text=True).stdout.strip(), "true")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_salida_y_busqueda_nueva_vieja_corrupta(self):
        salida = self.root / "proyecto" / "_codexmax"
        row = self.cli(salida)
        new = Path(row["ruta"])
        self.assertEqual(new.parent, salida / "runs")
        old = self.taller / "runs" / "antigua"
        for path in (new, old):
            path.mkdir(parents=True, exist_ok=True)
            store = Store(path / "state.db")
            store.add(dict(id="t1", title="prueba", prompt="prueba"))
            store.db.close()
        write_meta(new, dict(repo=str(self.repo), goal="prueba", pid=2147483647))
        with (self.taller / "data" / "registro.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("{roto\n")
        registrar("perdida", self.root / "no_existe", self.repo, self.taller / "data")
        corridas = listar_corridas(self.taller / "runs")
        self.assertEqual({r["id"] for r in corridas}, {row["id"], "antigua", "perdida"})
        output = formatear(corridas)
        self.assertIn("carpeta no encontrada", output)
        self.assertIn(str(new), output)
        self.assertIn(str(old), output)
        with patch("codexmax.orchestrator.avisar"), \
                patch.object(Orchestrator, "process", lambda o, t: o.store.set(t["id"], status="hecha")):
            recover(row["id"], self.taller / "runs")
            meta = read_meta(new)
            meta["pid"] = 2147483647
            write_meta(new, meta)
            recover(row["id"], self.taller / "runs", close=True)
            recover("antigua", self.taller / "runs", close=True)
        self.assertTrue((new / "REPORTE.md").is_file())
        self.assertTrue((old / "REPORTE.md").is_file())

    def test_exclude_en_repo_worktree(self):
        worktree = self.root / "copia"
        self.git("worktree", "add", "-qb", "copia", str(worktree))
        self.repo = worktree
        row = self.cli()
        self.assertEqual(Path(row["ruta"]).parent, worktree / "_codexmax" / "runs")
        git_path = self.git("rev-parse", "--git-path", "info/exclude")
        exclude = Path(git_path)
        if not exclude.is_absolute():
            exclude = worktree / exclude
        self.assertIn("_codexmax/", exclude.read_text(encoding="utf-8").splitlines())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_uso_central_y_legacy(self):
        new = self.root / "nueva"
        new.mkdir()
        old = self.taller / "runs" / "antigua"
        old.mkdir(parents=True)
        row = json.dumps(dict(ts=100, agente="codex", tokens_total=7)) + "\n"
        (new / "uso.jsonl").write_text(row, encoding="utf-8")
        data = self.taller / "data"
        data.mkdir()
        (data / "uso.jsonl").write_text(row + "{roto\n", encoding="utf-8")
        (old / "uso.jsonl").write_text(row, encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            main_uso(self.taller / "runs", ahora=100)
        self.assertIn("codex | (por defecto) | 2 / 14 | 2 / 14 | 2 / 14", output.getvalue())


if __name__ == "__main__":
    unittest.main()
