import argparse
import sys
import time

from .adapters import ADAPTERS
from .core import ROOT


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
    r = sub.add_parser("run")
    r.add_argument("--repo", required=True)
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--goal")
    g.add_argument("--goal-file")
    r.add_argument("--apply", action="store_true", help="avanza la rama actual si todo salio bien (ff-only)")
    r.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "doctor":
        return doctor()
    from .orchestrator import Orchestrator
    goal = a.goal or open(a.goal_file, encoding="utf-8").read()
    run_id = time.strftime("%Y%m%d-%H%M%S")
    Orchestrator(a.repo, goal, ROOT / "runs" / run_id, run_id, a.apply, a.workers).run()


if __name__ == "__main__":
    sys.exit(main())
