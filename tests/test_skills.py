"""Instalador de habilidades: usa carpetas temporales, nunca las reales del usuario."""
import tempfile
import unittest
from pathlib import Path

from codexmax import skills_cmd


def crear_skill(base, nombre, extra="", encabezado=None):
    carpeta = Path(base) / nombre
    carpeta.mkdir(parents=True)
    head = encabezado or f"---\nname: {nombre}\ndescription: Úsala para probar\n---\n"
    (carpeta / "SKILL.md").write_text(head + "cuerpo " + extra, encoding="utf-8")
    return carpeta


class InstaladorSkills(unittest.TestCase):
    def preparar(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        src = tmp / "src"
        dests = {"agents": (tmp / "a" / "skills", tmp / "a" / "resp"),
                 "claude": (tmp / "c" / "skills", tmp / "c" / "resp")}
        return tmp, src, dests

    def test_instala_en_ambos_destinos_y_marca(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "uno")
        skills_cmd.instalar(src, {}, dests, retirar=[])
        for raiz, _ in dests.values():
            self.assertTrue((raiz / "uno" / "SKILL.md").is_file())
            self.assertTrue((raiz / "uno" / skills_cmd.MARCA).exists())

    def test_lo_ajeno_con_mismo_nombre_se_respalda_no_se_borra(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "uno", extra="nuevo")
        ajeno = crear_skill(dests["agents"][0], "uno", extra="viejo-ajeno")
        skills_cmd.instalar(src, {}, dests, retirar=[])
        respaldos = list(dests["agents"][1].glob("uno-*"))
        self.assertEqual(len(respaldos), 1)
        self.assertIn("viejo-ajeno", (respaldos[0] / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("nuevo", (ajeno / "SKILL.md").read_text(encoding="utf-8"))

    def test_reinstalar_actualiza_lo_propio_sin_respaldo(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "uno", extra="v1")
        skills_cmd.instalar(src, {}, dests, retirar=[])
        (src / "uno" / "SKILL.md").write_text("---\nname: uno\ndescription: x\n---\nv2", encoding="utf-8")
        skills_cmd.instalar(src, {}, dests, retirar=[])
        self.assertIn("v2", (dests["agents"][0] / "uno" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse(dests["agents"][1].exists() and any(dests["agents"][1].iterdir()))

    def test_retira_las_viejas_al_respaldo(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "uno")
        crear_skill(dests["agents"][0], "vieja")
        skills_cmd.instalar(src, {}, dests, retirar=["vieja"])
        self.assertFalse((dests["agents"][0] / "vieja").exists())
        self.assertEqual(len(list(dests["agents"][1].glob("vieja-*"))), 1)

    def test_no_instala_invalidas(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "mala", encabezado="---\nname: otra\ndescription: x\n---\n")
        crear_skill(src, "oculta", extra="texto​escondido")
        crear_skill(src, "buena")
        out = skills_cmd.instalar(src, {}, dests, retirar=[])
        self.assertTrue((dests["agents"][0] / "buena").exists())
        self.assertFalse((dests["agents"][0] / "mala").exists())
        self.assertFalse((dests["agents"][0] / "oculta").exists())
        self.assertEqual(sum(l.startswith("OMITIDA") for l in out), 2)

    def test_externas_solo_si_existen(self):
        tmp, src, dests = self.preparar()
        ext = crear_skill(tmp / "ext", "grande")
        out = skills_cmd.fuentes(src, {"grande": ext, "falta": tmp / "no_existe"})
        self.assertEqual(list(out), ["grande"])

    def test_estado_dice_falta_distinta_ok(self):
        tmp, src, dests = self.preparar()
        crear_skill(src, "uno")
        crear_skill(dests["claude"][0], "uno")                      # ajena -> distinta
        texto = "\n".join(skills_cmd.estado(src, {}, dests, retirar=[]))
        self.assertIn("agents=falta", texto)
        self.assertIn("claude=distinta", texto)
        skills_cmd.instalar(src, {}, dests, retirar=[])
        self.assertIn("agents=OK claude=OK", "\n".join(skills_cmd.estado(src, {}, dests, retirar=[])))

    def test_las_habilidades_del_repo_son_validas(self):
        for nombre, carpeta in skills_cmd.fuentes(externas={}).items():
            self.assertEqual(skills_cmd.validar(nombre, carpeta), [], nombre)


if __name__ == "__main__":
    unittest.main()
