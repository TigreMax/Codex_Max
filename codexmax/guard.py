"""Filtro de secretos. Nunca imprime ni guarda el VALOR de un secreto: solo tipo y archivo.

Capas (de la mas fuerte a la mas debil):
 1. Las copias de trabajo (git worktree) solo contienen archivos que git rastrea:
    un .env ignorado por git NUNCA llega al agente.
 2. Antes de correr: escanea los archivos rastreados por git (nombres y contenido).
 3. Antes de integrar: escanea lo que el agente agrego en su diff.
 4. Claude Code (revisor/planificador) lleva reglas de lectura denegada (ver adapters.py).
 5. Aviso en el prompt de cada agente (capa blanda: no se puede garantizar).
Lo que este filtro NO puede hacer: impedir que Codex o agy lean archivos fuera de su
copia de trabajo (no se verifico que su sandbox lo impida).
"""
import re
import subprocess

NOMBRES = [
    (r"(^|/)\.env(\..+)?$", "archivo .env"),
    (r"\.(pem|key|pfx|p12|jks|keystore)$", "archivo de clave/certificado"),
    (r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$", "clave SSH privada"),
    (r"(^|/)(credentials|secrets?)(\.[A-Za-z0-9]+)?$", "archivo de credenciales"),
    (r"(^|/)\.(npmrc|pypirc|netrc)$", "archivo de credenciales de herramienta"),
    (r"service[-_]?account.*\.json$", "cuenta de servicio de Google"),
    (r"client_secret.*\.json$", "secreto de cliente OAuth"),
    (r"(^|/)mcp_config\.json$", "configuracion MCP (puede traer secretos OAuth)"),
]
EJEMPLOS = re.compile(r"\.(example|sample|template|dist)$", re.I)

PATRONES = [
    ("clave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secreto OAuth de Google", re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}")),
    ("clave de API de Google", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("clave de AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token de GitHub", re.compile(r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{30,}")),
    ("clave de API (sk-)", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{24,}")),
    ("token de Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
]
GENERICO = re.compile(
    r"""(?ix)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b
        \s*[:=]\s*["']([^"'\s]{12,})["']""")
PLACEHOLDER = re.compile(r"(?i)(tu_|your|example|ejemplo|xxxx|changeme|placeholder|<|\{\{|\$\{|environ|getenv|env\.)")


def nombre_sensible(ruta: str):
    r = ruta.replace("\\", "/")
    if EJEMPLOS.search(r):
        return None
    for rx, motivo in NOMBRES:
        if re.search(rx, r):
            return motivo
    return None


def buscar_en_texto(texto: str):
    """Devuelve la lista de TIPOS de secreto encontrados (nunca el valor)."""
    tipos = []
    for tipo, rx in PATRONES:
        if rx.search(texto):
            tipos.append(tipo)
    for m in GENERICO.finditer(texto):
        if not PLACEHOLDER.search(m.group(2)):
            tipos.append("asignacion de clave/contrasena")
            break
    return tipos


def escanear_repo(repo, aceptados=()):
    """Archivos rastreados por git con nombre o contenido sensible. [(ruta, motivo)]"""
    p = subprocess.run(["git", "ls-files", "-z"], cwd=str(repo), capture_output=True)
    hallazgos = []
    for ruta in p.stdout.decode("utf-8", "replace").split("\0"):
        if not ruta or ruta in aceptados:
            continue
        motivo = nombre_sensible(ruta)
        if motivo:
            hallazgos.append((ruta, motivo))
            continue
        try:
            f = (__import__("pathlib").Path(repo) / ruta)
            if not f.is_file() or f.stat().st_size > 1_000_000:
                continue
            data = f.read_bytes()
            if b"\0" in data[:2048]:
                continue
            tipos = buscar_en_texto(data.decode("utf-8", "replace"))
            if tipos:
                hallazgos.append((ruta, "contiene " + ", ".join(tipos)))
        except OSError:
            pass
    return hallazgos


def escanear_diff(diff_texto: str):
    """Revisa solo las lineas AGREGADAS de un diff. [(archivo, motivo)]"""
    hallazgos, actual, agregado = [], None, []

    def cerrar():
        if actual is None:
            return
        motivo = nombre_sensible(actual)
        if motivo:
            hallazgos.append((actual, motivo))
        tipos = buscar_en_texto("\n".join(agregado))
        if tipos:
            hallazgos.append((actual, "contiene " + ", ".join(tipos)))

    for linea in diff_texto.splitlines():
        if linea.startswith("+++ "):
            cerrar()
            actual = linea[4:].removeprefix("b/") if linea[4:] != "/dev/null" else None
            agregado = []
        elif linea.startswith("+") and actual is not None:
            agregado.append(linea[1:])
    cerrar()
    return hallazgos
