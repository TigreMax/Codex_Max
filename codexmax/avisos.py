"""Avisos locales de mejor esfuerzo; ningun fallo interrumpe una corrida."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

LOG = Path(__file__).resolve().parent.parent / "avisos.log"
_lock = threading.Lock()
_ultimos = {}

# El contenido del aviso solo entra por el entorno, nunca como codigo.
_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$titulo = [System.Security.SecurityElement]::Escape($env:CODEXMAX_AVISO_TITULO)
$texto = [System.Security.SecurityElement]::Escape($env:CODEXMAX_AVISO_TEXTO)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$titulo</text><text>$texto</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
'''


def avisar(titulo, texto, log_path=None):
    """Registra siempre; intenta un toast por titulo cada 600 s por proceso."""
    try:
        titulo, texto = str(titulo), str(texto)
        # JSON mantiene una sola linea aunque el mensaje incluya saltos de linea.
        try:
            with (Path(log_path) if log_path is not None else LOG).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(fecha=time.time(), titulo=titulo, texto=texto),
                                        ensure_ascii=False) + "\n")
        except Exception:
            pass
        if sys.platform != "win32" or os.environ.get("CODEXMAX_SIN_AVISOS") == "1":
            return
        with _lock:
            ahora = time.monotonic()
            if ahora - _ultimos.get(titulo, float("-inf")) < 600:
                return
            _ultimos[titulo] = ahora
        env = os.environ.copy()
        env.update(CODEXMAX_AVISO_TITULO=titulo, CODEXMAX_AVISO_TEXTO=texto)
        subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", _SCRIPT],
            env=env, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False)
    except Exception:
        pass
