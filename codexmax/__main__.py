import argparse
import os
import sys
import time
from pathlib import Path

from .adapters import ADAPTERS
from .core import ROOT


def excluir_codexmax(repo, run_dir):
    """Excluye los artefactos locales sin tocar archivos versionados."""
    import subprocess

    repo = Path(repo).resolve()
    codexmax = repo / "_codexmax"
    if not (run_dir == codexmax or codexmax in run_dir.parents):
        return
    result = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"],
                            cwd=repo, capture_output=True, text=True, check=True)
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = repo / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    old = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if "_codexmax/" not in old.splitlines():
        with exclude.open("a", encoding="utf-8") as stream:
            stream.write(("\n" if old and not old.endswith("\n") else "") + "_codexmax/\n")


def doctor():
    print("Estado de agentes (prueba real con un prompt trivial):")
    for n, a in ADAPTERS.items():
        if not a.installed():
            print(f"  {n:6} NO INSTALADO")
            continue
        r = a.run("Responde solo con la palabra OK", ROOT, write=False, timeout=180)
        print(f"  {n:6} {'OK' if r.ok else 'FALLA ('+r.kind+')'}  {r.seconds:.0f}s  {r.error[:120]}")


def main():
    ap = argparse.ArgumentParser(prog="codexmax")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("status", help="consulta las corridas guardadas en runs/ en solo lectura")
    sub.add_parser("uso", help="muestra consumo local por agente en 5h, 7d y total")
    sk = sub.add_parser("skills", help="instala o revisa las habilidades de skills/ para todos los agentes")
    sk.add_argument("accion", choices=["instalar", "estado"])
    resume = sub.add_parser("resume", help="continua una corrida interrumpida")
    resume.add_argument("id")
    resume.add_argument("--reintentar", action="store_true")
    close = sub.add_parser("close", help="cierra tareas pendientes sin borrar archivos")
    close.add_argument("id")
    r = sub.add_parser("run")
    r.add_argument("--repo", required=True)
    r.add_argument("--salida", help="carpeta donde se guardara runs/<id>")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--goal")
    g.add_argument("--goal-file")
    r.add_argument("--apply", action="store_true", help="avanza la rama actual si todo salio bien (ff-only)")
    r.add_argument("--espera-max-horas", type=float, default=6)
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--sin-avisos", action="store_true", help="desactiva toasts; conserva avisos.log")
    r.add_argument("--aceptar", action="append", default=[], metavar="RUTA",
                   help="acepta enviar este archivo sensible que git rastrea (repetible)")
    a = ap.parse_args()
    if a.cmd == "skills":
        from .skills_cmd import main_skills
        return main_skills(a.accion)
    if a.cmd == "uso":
        from .uso import main_uso
        return main_uso(ROOT / "runs")
    if a.cmd == "status":
        from .status import main_status
        return main_status()
    if a.cmd == "doctor":
        return doctor()
    if a.cmd in ("resume", "close"):
        from .lifecycle import recover
        return recover(a.id, ROOT / "runs", getattr(a, "reintentar", False), a.cmd == "close")
    from .orchestrator import Orchestrator
    goal = a.goal or open(a.goal_file, encoding="utf-8").read()
    run_id = time.strftime("%Y%m%d-%H%M%S")
    repo = Path(a.repo).resolve()
    salida = Path(a.salida).resolve() if a.salida else repo / "_codexmax"
    base_id = run_id
    n = 1
    while (salida / "runs" / run_id).exists():
        run_id = f"{base_id}-{n}"
        n += 1
    run_dir = (salida / "runs" / run_id).resolve()
    excluir_codexmax(repo, run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    from .registro import registrar
    registrar(run_id, run_dir, repo, ROOT / "data")
    anterior = os.environ.get("CODEXMAX_SIN_AVISOS")
    try:
        if a.sin_avisos:
            os.environ["CODEXMAX_SIN_AVISOS"] = "1"
        Orchestrator(repo, goal, run_dir, run_id, a.apply, a.workers, a.aceptar,
                     espera_max_horas=a.espera_max_horas, data_dir=ROOT / "data").run()
    finally:
        if a.sin_avisos:
            if anterior is None:
                os.environ.pop("CODEXMAX_SIN_AVISOS", None)
            else:
                os.environ["CODEXMAX_SIN_AVISOS"] = anterior


if __name__ == "__main__":
    sys.exit(main())
