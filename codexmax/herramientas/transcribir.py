"""Transcribe un audio o video a texto con Whisper local (faster-whisper).

Se corre con el Python del entorno whisper_env (ahi esta faster-whisper):
  D:\\Cortex_externas\\whisper_env\\Scripts\\python.exe transcribir.py "<archivo>" [--modelo large-v3] [--idioma es] [--cpu]
Nada sale de la computadora. Guarda <nombre>.txt junto al original, con [hh:mm:ss] por frase.
"""
import argparse
import os
import sys
import time
from pathlib import Path


def _agregar_dlls_nvidia():
    """Las librerias de CUDA vienen en paquetes nvidia-* del entorno; hay que dar su carpeta bin a Windows."""
    for base in sys.path:
        nvidia = Path(base) / "nvidia"
        if nvidia.is_dir():
            for sub in nvidia.glob("*/bin"):
                try:
                    os.add_dll_directory(str(sub))
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = str(sub) + os.pathsep + os.environ.get("PATH", "")


def _decodificar_audio(ruta, rate=16000):
    """Audio mono a 16 kHz (float32) con PyAV. faster-whisper trae su propio decodificador, pero con
    PyAV 19 falla (`metadata_errors`); este funciona con cualquier version y acepta audio o video."""
    import av
    import numpy as np

    contenedor = av.open(str(ruta), mode="r")
    try:
        if not contenedor.streams.audio:
            raise ValueError("el archivo no tiene pista de audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        partes = []
        for frame in contenedor.decode(contenedor.streams.audio[0]):
            for nuevo in resampler.resample(frame):
                partes.append(nuevo.to_ndarray().reshape(-1))
        for nuevo in resampler.resample(None):
            partes.append(nuevo.to_ndarray().reshape(-1))
    finally:
        contenedor.close()
    if not partes:
        raise ValueError("no se pudo leer audio")
    return np.concatenate(partes).astype(np.float32) / 32768.0


def _hora(segundos):
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _cargar(modelo, forzar_cpu):
    from faster_whisper import WhisperModel
    if not forzar_cpu:
        try:
            return WhisperModel(modelo, device="cuda", compute_type="float16"), "tarjeta de video"
        except Exception as e:  # sin CUDA, falta una DLL, etc.
            print(f"NO SE PUDO USAR LA TARJETA DE VIDEO: {e}", flush=True)
    return WhisperModel(modelo, device="cpu", compute_type="int8"), "procesador"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--modelo", default="large-v3", choices=["large-v3", "medium", "tiny"])
    ap.add_argument("--idioma", default=None)
    ap.add_argument("--cpu", action="store_true")
    a = ap.parse_args(argv)
    origen = Path(a.archivo)
    if not origen.is_file():
        print(f"NO EXISTE el archivo: {origen}", flush=True)
        return 2
    _agregar_dlls_nvidia()
    inicio = time.time()
    modelo, con = _cargar(a.modelo, a.cpu)
    print("Leyendo el audio...", flush=True)
    audio = _decodificar_audio(origen)
    print(f"Audio listo: {len(audio) / 16000 / 60:.1f} minutos. Transcribiendo...", flush=True)
    segmentos, info = modelo.transcribe(audio, language=a.idioma, vad_filter=True)
    salida = origen.with_suffix(".txt")
    lineas = []
    with salida.open("w", encoding="utf-8") as f:
        f.write(f"# Transcripcion de {origen.name} | modelo {a.modelo} | hecho con {con} | idioma {info.language}\n")
        for seg in segmentos:
            linea = f"[{_hora(seg.start)}] {seg.text.strip()}"
            lineas.append(linea)
            f.write(linea + "\n")
            print(linea, flush=True)
    print(f"\nLISTO: {salida} | {len(lineas)} frases | con {con} | {time.time() - inicio:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
