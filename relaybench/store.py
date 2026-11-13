import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT UNIQUE NOT NULL, trace TEXT NOT NULL)")

    def save(self, trace):
        run_id = uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO runs VALUES (?, ?)", (run_id, json.dumps(trace)))
        return run_id

    def read(self, run_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT trace FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("""SELECT id, json_extract(trace,'$.policy'), json_extract(trace,'$.fault'),
                json_extract(trace,'$.seed'), json_extract(trace,'$.metrics.passed')
                FROM runs ORDER BY rowid DESC LIMIT 50""")
            return [dict(id=i, policy=p, fault=f, seed=s, passed=bool(ok)) for i, p, f, s, ok in rows]
