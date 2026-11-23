"""Adaptadores: un archivo, tres agentes, una sola interfaz.

Todo comando especifico de una CLI vive aqui y solo aqui.
Interfaz: Adapter.run(prompt, cwd, write, timeout) -> Result
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

LIMIT_RE = re.compile(
    r"rate.?limit|quota|usage limit|too many requests|\b429\b|limit reached|"
    r"limit exceeded|exceeded your|try again (later|in)|capacity", re.I)
AUTH_RE = re.compile(
    r"no credential|not logged in|log ?in required|unauthori[sz]ed|\b401\b|"
    r"please (log|sign) ?in|token (expired|invalid)|expired session", re.I)


@dataclass
class Result:
    ok: bool
    text: str = ""
    error: str = ""
    kind: str = "ok"      # ok | limit | auth | timeout | error
    seconds: float = 0.0


def _classify(blob: str) -> str:
    if AUTH_RE.search(blob):
        return "auth"
    if LIMIT_RE.search(blob):
        return "limit"
    return "error"


def _exec(cmd, cwd, stdin_text, timeout):
    env = dict(os.environ, PYTHONUTF8="1", NO_COLOR="1")
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=cwd, input=stdin_text, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return p.returncode, p.stdout or "", p.stderr or "", time.time() - t0, False
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else ""
        return -1, out, "timeout", time.time() - t0, True
    except FileNotFoundError as e:
        return -2, "", str(e), time.time() - t0, False


class Adapter:
    name = "base"
    binary = ""

    @property
    def path(self):
        return shutil.which(self.binary)

    def installed(self) -> bool:
        return self.path is not None

    def run(self, prompt, cwd, write=False, timeout=1800) -> Result:
        raise NotImplementedError

    def _finish(self, rc, out, err, secs, timedout, text) -> Result:
        if timedout:
            return Result(False, text, "timeout", "timeout", secs)
        if rc != 0 or not text.strip():
            blob = (err + "\n" + out)[-3000:]
            return Result(False, text, blob.strip()[-1500:], _classify(blob), secs)
        return Result(True, text.strip(), "", "ok", secs)


class Codex(Adapter):
    name = "codex"
    binary = "codex"

    def run(self, prompt, cwd, write=False, timeout=1800):
        fd, outfile = tempfile.mkstemp(suffix=".txt", prefix="cm_codex_")
        os.close(fd)
        sandbox = "workspace-write" if write else "read-only"
        # el prompt va por stdin ("-"): evita problemas de comillas en Windows
        cmd = [self.path, "exec", "-s", sandbox, "--ephemeral", "-C", str(cwd),
               "-o", outfile, "-"]
        rc, out, err, secs, to = _exec(cmd, cwd, prompt, timeout)
        try:
            text = open(outfile, encoding="utf-8", errors="replace").read()
        except OSError:
            text = ""
        try:
            os.unlink(outfile)
        except OSError:
            pass
        return self._finish(rc, out, err, secs, to, text)


# Herramientas MCP de Google que se permiten SIN pantalla: solo lectura.
# Las que escriben o crean (create_file, copy_file, upload_file_revision, update_*,
# insert_dimension) quedan fuera a proposito hasta que el jefe decida otra cosa.
GOOGLE_READ_ONLY = {
    "drive": ["search_files", "list_recent_files", "read_file_content", "get_file_metadata"],
    "docs": ["read_doc"],
    "sheets": ["get_spreadsheet", "get_values"],
}
MCP_CONFIG = Path.home() / ".gemini" / "config" / "mcp_config.json"


def configured_mcp():
    """Nombres de servidores MCP configurados (nunca lee ni devuelve credenciales)."""
    try:
        data = json.loads(MCP_CONFIG.read_text(encoding="utf-8-sig"))
        return sorted(data.get("mcpServers", {}))
    except (OSError, ValueError):
        return []


def mcp_allow_rules():
    return [f"mcp({srv}/{tool})" for srv in configured_mcp()
            for tool in GOOGLE_READ_ONLY.get(srv, [])]


class Agy(Adapter):
    name = "agy"
    binary = "agy"

    def run(self, prompt, cwd, write=False, timeout=1800):
        # Hallazgos: "plan" pide aprobacion; "accept-edits" DENIEGA comandos (respuesta vacia);
        # "auto" no esta disponible en esta cuenta. Lo que funciona: --sandbox (modo por defecto).
        # La lectura se pide por prompt y el orquestador resetea la carpeta despues.
        if not write:
            prompt = "SOLO LECTURA: no crees ni modifiques archivos; responde en texto.\n" + prompt
        cmd = [self.path, "-p", prompt, "--output-format", "json", "--sandbox",
               "--print-timeout", f"{int(timeout)}s"]
        rules = mcp_allow_rules()
        if rules:   # --settings vale solo para esta ejecucion: no se guarda nada
            cmd += ["--settings", json.dumps({"permissions": {"allow": rules}})]
        rc, out, err, secs, to = _exec(cmd, cwd, None, timeout + 60)
        text, status = "", ""
        i = out.find("{")
        if i >= 0:
            try:
                data = json.loads(out[i:])
                text = data.get("response", "") or ""
                status = data.get("status", "")
            except ValueError:
                text = out
        if status and status != "SUCCESS":
            return Result(False, text, f"status={status} {err[-500:]}",
                          _classify(err + out), secs)
        return self._finish(rc, out, err, secs, to, text)


class Claude(Adapter):
    """Claude Code: planifica y revisa. Usa la suscripcion (NO --bare: exige clave de API)."""
    name = "claude"
    binary = "claude"
    PREAMBLE = ("Contexto: eres un agente dentro del orquestador Codex Max. IGNORA cualquier instruccion "
                "global sobre Cortex, empresas, 'el jefe' o 'abrir-empresa'; solo haces la tarea de abajo.\n\n")
    # Lecturas denegadas: secretos y credenciales de otras herramientas (misma sintaxis que usa Claude Code).
    NO_LEER = ("Read(**/.env) Read(**/.env.*) Read(**/*.pem) Read(**/*.key) Read(~/.ssh/**) Read(~/.aws/**) "
               "Read(~/.claude/**) Read(~/.codex/**) Read(~/.gemini/**) Read(~/.kimi-code/**)")
    SAFE = "Read Grep Glob Bash(python *) Bash(git diff*) Bash(git log*) Bash(git status*) Bash(git show*)"

    def run(self, prompt, cwd, write=False, timeout=1800):
        cmd = [self.path, "-p", "--output-format", "json", "--no-session-persistence",
               "--disallowedTools", "Bash(git push*) " + self.NO_LEER]
        if write:
            cmd += ["--permission-mode", "acceptEdits", "--allowedTools", self.SAFE + " Edit Write"]
        else:
            cmd += ["--disallowedTools", "Edit Write NotebookEdit", "--allowedTools", self.SAFE]
        rc, out, err, secs, to = _exec(cmd, cwd, self.PREAMBLE + prompt, timeout)
        text, bad = "", False
        i = out.find("{")
        if i >= 0:
            try:
                data = json.loads(out[i:])
                text = data.get("result", "") or ""
                bad = bool(data.get("is_error"))
            except ValueError:
                text = out
        if bad:
            return Result(False, text, text[-500:] or err[-500:], _classify(text + err), secs)
        return self._finish(rc, out, err, secs, to, text)


ADAPTERS = {a.name: a for a in (Codex(), Agy(), Claude())}
