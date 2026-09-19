import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from .models import Graph

class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("CODEMRI_CACHE", ".codemri"))
        self.directory.mkdir(parents=True, exist_ok=True)

    def key(self, root):
        return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:20]

    def save(self, graph: Graph):
        key = self.key(graph.root)
        with NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as f:
            f.write(graph.model_dump_json())
        Path(f.name).replace(self.directory / f"{key}.json")
        return key

    def load(self, key):
        if len(key) != 20 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid repository ID")
        return Graph.model_validate_json((self.directory / f"{key}.json").read_text())
