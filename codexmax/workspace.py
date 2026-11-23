"""Git: rama de integracion + un worktree aislado por tarea. Nunca hace push."""
import subprocess
import threading
from pathlib import Path

ID = ["-c", "user.name=CodexMax", "-c", "user.email=codexmax@local"]


def git(cwd, *args, check=True):
    p = subprocess.run(["git", *ID, *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()}")
    return p


class Workspace:
    def __init__(self, repo, run_dir, run_id):
        self.repo, self.wt_dir = Path(repo), Path(run_dir) / "wt"
        self.wt_dir.mkdir(parents=True, exist_ok=True)
        self.integ_branch = f"cm/{run_id}/_integracion"
        self.task_prefix = f"cm/{run_id}"
        self.integ = self.wt_dir / "_integracion"
        self.lock = threading.Lock()
        self.run_id = run_id

    def is_dirty(self):
        return bool(git(self.repo, "status", "--porcelain").stdout.strip())

    def current_branch(self):
        return git(self.repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def prepare(self):
        if not self.integ.exists():
            git(self.repo, "worktree", "add", "-b", self.integ_branch, str(self.integ), "HEAD")

    def task_tree(self, tid):
        path = self.wt_dir / tid
        if not path.exists():
            git(self.repo, "worktree", "add", "-b", f"{self.task_prefix}/{tid}",
                str(path), self.integ_branch)
        return path

    def reset(self, path):
        git(path, "reset", "-q", "--hard", "HEAD", check=False)
        git(path, "clean", "-fdq", check=False)

    def restart(self, path):
        """Descarta todo lo hecho en la rama de la tarea y vuelve a la rama de integracion."""
        git(path, "reset", "-q", "--hard", self.integ_branch)
        git(path, "clean", "-fdq", check=False)

    def base_of(self, path):
        return git(path, "merge-base", "HEAD", self.integ_branch).stdout.strip()

    def commit(self, path, msg):
        """Guarda lo que hizo el agente. True si la rama tiene cambios sobre la integracion."""
        git(path, "add", "-A")
        if git(path, "diff", "--cached", "--quiet", check=False).returncode != 0:
            git(path, "commit", "-q", "-m", msg)
        return bool(git(path, "rev-list", f"{self.integ_branch}..HEAD").stdout.strip())

    def diff(self, path, limit=60000):
        stat = git(path, "diff", "--stat", f"{self.integ_branch}...HEAD").stdout
        full = git(path, "diff", f"{self.integ_branch}...HEAD").stdout
        if len(full) > limit:
            full = full[:limit] + "\n...[diff recortado]"
        return stat + "\n" + full

    def merge(self, tid):
        """Integra la rama de la tarea. Devuelve (ok, mensaje)."""
        with self.lock:
            p = git(self.integ, "merge", "--no-ff", "-m", f"tarea {tid}",
                    f"{self.task_prefix}/{tid}", check=False)
            if p.returncode != 0:
                git(self.integ, "merge", "--abort", check=False)
                return False, (p.stdout + p.stderr).strip()[-800:]
            return True, ""

    def apply_to_repo(self):
        """--apply: avanza la rama actual solo si es fast-forward y el arbol esta limpio."""
        if self.is_dirty():
            return False, "el repositorio tiene cambios sin guardar"
        p = git(self.repo, "merge", "--ff-only", self.integ_branch, check=False)
        return p.returncode == 0, (p.stdout + p.stderr).strip()[-400:]
