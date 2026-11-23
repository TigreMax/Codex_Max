"""La espera maxima por cuota es ACUMULADA, no por cada espera suelta."""
import unittest
from unittest import mock

from codexmax import core


class RelojFalso:
    def __init__(self):
        self.now = 1_000_000.0

    def time(self):
        return self.now

    def sleep(self, segundos):
        self.now += segundos


class FalsoAgente:
    def installed(self):
        return True


class EsperaAcumulada(unittest.TestCase):
    def preparar(self):
        reloj = RelojFalso()
        parches = [mock.patch.object(core, "time", reloj),
                   mock.patch.dict(core.ADAPTERS, {"claude": FalsoAgente(), "codex": FalsoAgente(),
                                                   "agy": FalsoAgente()}, clear=True)]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        salud = core.Health()
        return reloj, salud, core.Router(salud, lambda m: None, 6 * 3600)

    def test_limite_repetido_sin_hora_termina_en_pausa(self):
        reloj, salud, router = self.preparar()
        inicio = reloj.now
        with self.assertRaises(core.CuotaAgotada):
            for _ in range(200):                 # cada intento vuelve a toparse con el limite
                router.pick("review")
                salud.cooldown("claude", "limit reached")
        espera = reloj.now - inicio
        self.assertGreater(espera, 4 * 3600)     # espero de verdad antes de rendirse...
        self.assertLessEqual(espera, 6 * 3600 + 1800)   # ...pero no para siempre

    def test_un_exito_reinicia_el_conteo(self):
        reloj, salud, router = self.preparar()
        salud.cooldown("claude", "limit reached")
        salud.ok("claude")
        self.assertEqual(salud.limited_for(["claude"]), 0)
        self.assertEqual(router.pick("review"), "claude")

    def test_cuota_corta_con_hora_conocida_no_pausa(self):
        reloj, salud, router = self.preparar()
        salud.cooldown("claude", "try again in 45 minutes")
        self.assertEqual(router.pick("review"), "claude")    # espera ~46 min y sigue
        self.assertGreater(reloj.now - 1_000_000.0, 45 * 60)

    def test_cuota_semanal_con_hora_conocida_pausa(self):
        reloj, salud, router = self.preparar()
        salud.cooldown("claude", "try again in 3 days")
        with self.assertRaises(core.CuotaAgotada):
            router.pick("review")


if __name__ == "__main__":
    unittest.main()
