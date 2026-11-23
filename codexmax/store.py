"""Estado reanudable en SQLite (biblioteca estandar)."""
import json
import sqlite3
import threading


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, title TEXT, prompt TEXT, kind TEXT,
            done_when TEXT, deps TEXT, status TEXT DEFAULT 'pendiente',
            agent TEXT, attempts INTEGER DEFAULT 0, note TEXT DEFAULT '')""")
        self.db.commit()

    def add(self, t):
        with self.lock:
            self.db.execute(
                "INSERT OR IGNORE INTO tasks(id,title,prompt,kind,done_when,deps) VALUES(?,?,?,?,?,?)",
                (t["id"], t["title"], t["prompt"], t.get("kind", "code"),
                 t.get("done_when", ""), json.dumps(t.get("deps", []))))
            self.db.commit()

    def set(self, tid, **kw):
        with self.lock:
            sets = ",".join(f"{k}=?" for k in kw)
            self.db.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*kw.values(), tid))
            self.db.commit()

    def all(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM tasks ORDER BY rowid")]

    def ready(self):
        rows = self.all()
        st = {r["id"]: r["status"] for r in rows}
        out = []
        for r in rows:
            if r["status"] != "pendiente":
                continue
            deps = json.loads(r["deps"])
            if any(st.get(d) in ("bloqueada", "omitida") for d in deps):
                self.set(r["id"], status="omitida", note="dependencia bloqueada")
            elif all(st.get(d) == "hecha" for d in deps):
                out.append(r)
        return out
