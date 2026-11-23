import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from codexmax.status import formatear, listar_corridas, main_status


class Status(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.runs_dir = Path(temporal.name)

    def crear_corrida(self, corrida_id, tareas):
        carpeta = self.runs_dir / corrida_id
        carpeta.mkdir()
        with closing(sqlite3.connect(carpeta / "state.db")) as conexion:
            conexion.execute("""CREATE TABLE tasks(
                id TEXT PRIMARY KEY, title TEXT, prompt TEXT, kind TEXT,
                done_when TEXT, deps TEXT, status TEXT DEFAULT 'pendiente',
                agent TEXT, attempts INTEGER DEFAULT 0, note TEXT DEFAULT '')""")
            conexion.executemany(
                "INSERT INTO tasks(id, status) VALUES (?, ?)", tareas
            )
            conexion.commit()

    def test_directorio_inexistente_o_vacio(self):
        for ruta in (self.runs_dir / "inexistente", self.runs_dir):
            with self.subTest(ruta=ruta):
                corridas = listar_corridas(ruta)
                self.assertEqual(corridas, [])
                self.assertEqual(formatear(corridas), "No hay corridas guardadas.")

    def test_resumen_y_estados_de_tareas(self):
        tareas = [("t1", "hecha"), ("t2", "hecha"), ("t3", "pendiente")]
        self.crear_corrida("corrida-01", tareas)

        corridas = listar_corridas(self.runs_dir)

        self.assertEqual(len(corridas), 1)
        self.assertEqual(corridas[0]["hechas"], 2)
        self.assertEqual(corridas[0]["total"], 3)
        self.assertEqual(corridas[0]["tareas"], tareas)
        linea = formatear(corridas)
        self.assertEqual(len(linea.splitlines()), 1)
        self.assertIn("corrida-01", linea)
        self.assertIn("2/3", linea)
        for tarea_id, estado in tareas:
            self.assertIn(f"{tarea_id}:{estado}", linea)

    def test_corridas_ordenadas_con_una_linea_por_corrida(self):
        self.crear_corrida("corrida-02", [("t2", "pendiente")])
        self.crear_corrida("corrida-01", [("t1", "hecha")])

        corridas = listar_corridas(self.runs_dir)

        self.assertEqual([corrida["id"] for corrida in corridas],
                         ["corrida-01", "corrida-02"])
        self.assertEqual(formatear(corridas).splitlines(), [
            "corrida-01  1/1 hechas  t1:hecha",
            "corrida-02  0/1 hechas  t2:pendiente",
        ])

    def test_carpeta_sin_base_se_ignora(self):
        (self.runs_dir / "sin-base").mkdir()
        self.assertEqual(listar_corridas(self.runs_dir), [])

    def test_base_corrupta_no_lanza_excepcion(self):
        carpeta = self.runs_dir / "corrupta"
        carpeta.mkdir()
        (carpeta / "state.db").write_bytes(b"esto no es una base SQLite")
        self.crear_corrida("valida", [("t1", "hecha")])

        corridas = listar_corridas(self.runs_dir)

        self.assertEqual([corrida["id"] for corrida in corridas],
                         ["corrupta", "valida"])
        self.assertTrue(corridas[0]["error"])
        self.assertEqual(corridas[1]["hechas"], 1)

    def test_main_status_imprime_directorio_vacio(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            main_status(self.runs_dir)
        self.assertEqual(salida.getvalue(), "No hay corridas guardadas.\n")

    def test_main_status_imprime_resumen(self):
        self.crear_corrida("corrida-01", [
            ("t1", "hecha"), ("t2", "hecha"), ("t3", "pendiente"),
        ])
        salida = io.StringIO()
        with redirect_stdout(salida):
            main_status(self.runs_dir)
        self.assertEqual(salida.getvalue(),
                         "corrida-01  2/3 hechas  t1:hecha t2:hecha t3:pendiente\n")


if __name__ == "__main__":
    unittest.main()
