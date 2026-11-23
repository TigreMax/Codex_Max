import unittest

from codexmax import guard

# Los "secretos" se arman en tiempo de ejecucion para no dejar cadenas reales en el repo.
FAKE_GOOGLE = "GOC" + "SPX-" + "a" * 28
FAKE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"


class Nombres(unittest.TestCase):
    def test_sensibles(self):
        for r in (".env", "app/.env.production", "certs/server.pem", "id_rsa",
                  "config/credentials.json", "client_secret_123.json", "x/mcp_config.json"):
            self.assertIsNotNone(guard.nombre_sensible(r), r)

    def test_ejemplos_permitidos(self):
        for r in (".env.example", "config/.env.sample", "secrets.yml.template"):
            self.assertIsNone(guard.nombre_sensible(r), r)

    def test_normales(self):
        for r in ("calc.py", "README.md", "src/environment.py"):
            self.assertIsNone(guard.nombre_sensible(r), r)


class Contenido(unittest.TestCase):
    def test_detecta_tipos_sin_devolver_valor(self):
        for txt in (FAKE_GOOGLE, FAKE_KEY, 'password = "Zx81hqLpq92mm"'):
            tipos = guard.buscar_en_texto(txt)
            self.assertTrue(tipos, txt[:10])
            self.assertNotIn(FAKE_GOOGLE, "".join(tipos))

    def test_placeholders_no_alertan(self):
        for txt in ('client_secret = "TU_SECRETO_AQUI_12345"', 'api_key = os.environ["API_KEY"]',
                    'password = "<tu-contrasena-aqui>"', "x = 1"):
            self.assertEqual(guard.buscar_en_texto(txt), [], txt)


class Diff(unittest.TestCase):
    def test_solo_lineas_agregadas(self):
        diff = ("--- a/a.py\n+++ b/a.py\n@@\n-token = '%s'\n+x = 1\n" % FAKE_GOOGLE)
        self.assertEqual(guard.escanear_diff(diff), [])          # estaba en lo quitado

    def test_detecta_agregado(self):
        diff = "--- /dev/null\n+++ b/cfg.py\n@@\n+KEY = '%s'\n" % FAKE_GOOGLE
        self.assertEqual(guard.escanear_diff(diff)[0][0], "cfg.py")

    def test_detecta_archivo_env_nuevo(self):
        diff = "--- /dev/null\n+++ b/.env\n@@\n+A=1\n"
        self.assertEqual(guard.escanear_diff(diff)[0][1], "archivo .env")


if __name__ == "__main__":
    unittest.main()
