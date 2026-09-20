import hashlib
import os
import sqlite3
from pathlib import Path
from .models import Graph
from .changes import changes


class Store:
    """Local, transactional snapshots. Baselines survive scans and server restarts."""
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("CODEMRI_CACHE", ".codemri"))
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS repositories (id TEXT PRIMARY KEY, current TEXT NOT NULL, baseline TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.directory / 'graphs.sqlite3', timeout=30)

    def key(self, root):
        return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:20]

    def save(self, graph: Graph):
        key = self.key(graph.root)
        data = graph.model_dump_json()
        # Migrate the previous JSON cache without losing its review baseline.
        legacy = self.directory / f'{key}.json'
        baseline = Graph.model_validate_json(legacy.read_text()).model_dump_json() if legacy.exists() else data
        with self.connect() as db:
            db.execute('INSERT INTO repositories VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET current=excluded.current', (key, data, baseline))
        return key

    def load(self, key, baseline=False):
        if len(key) != 20 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid repository ID')
        with self.connect() as db:
            row = db.execute('SELECT current, baseline FROM repositories WHERE id=?', (key,)).fetchone()
        if row:
            return Graph.model_validate_json(row[1 if baseline else 0])
        return Graph.model_validate_json((self.directory / f'{key}.json').read_text())

    def review(self, key):
        current, baseline = self.load(key), self.load(key, baseline=True)
        return {'changes': changes(baseline, current), 'baseline': baseline}

    def accept(self, key, revision):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT current FROM repositories WHERE id=?', (key,)).fetchone()
            if not row or Graph.model_validate_json(row[0]).revision != revision:
                raise ValueError('Graph changed. Refresh before marking reviewed.')
            db.execute('UPDATE repositories SET baseline=current WHERE id=?', (key,))
