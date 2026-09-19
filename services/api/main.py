import os
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from codemri.analyzer import analyze
from codemri.store import Store
from codemri.context import impact, compile_context

app = FastAPI(title="CodeMRI", version="0.1.0")
store = Store()
STARTED = time.strftime("%Y-%m-%d %H:%M:%S")

class AnalyzeRequest(BaseModel):
    root: str

class ContextRequest(BaseModel):
    query: str = Field(max_length=10000)
    seed_ids: list[str] = Field(default_factory=list)
    budget: int = Field(default=4000, ge=64, le=32000)

def load(repo_id):
    try:
        return store.load(repo_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Analyze this repository first")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ai/status")
def ai_status():
    """What this server process sees for AI setup. Never returns the key, only whether it is set."""
    return {"api_key_set": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
            "model": (os.environ.get("CODEMRI_ARCHITECTURE_MODEL") or "").strip() or None,
            "pid": os.getpid(), "parent_pid": os.getppid(), "started": STARTED, "cwd": os.getcwd()}

@app.post("/analyze")
def scan(request: AnalyzeRequest):
    root = Path(request.root).resolve()
    allowed = Path(os.environ.get("CODEMRI_ALLOWED_ROOT", os.getcwd())).resolve()
    if not root.is_relative_to(allowed):
        raise HTTPException(403, "Repository must be under CODEMRI_ALLOWED_ROOT")
    try:
        graph = analyze(root)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    return {"repo_id": store.save(graph), "graph": graph}

@app.get("/graphs/{repo_id}")
def get_graph(repo_id: str):
    return load(repo_id)

@app.post("/graphs/{repo_id}/impact")
def get_impact(repo_id: str, request: ContextRequest):
    return impact(load(repo_id), request.query, request.seed_ids)

@app.post("/graphs/{repo_id}/context")
def get_context(repo_id: str, request: ContextRequest):
    try:
        return compile_context(load(repo_id), request.query, request.budget, request.seed_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/graphs/{repo_id}/architecture-ai")
def generate_architecture(repo_id: str):
    from codemri.semantic import synthesize
    try:
        graph = synthesize(load(repo_id))
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    store.save(graph)
    return {"repo_id": repo_id, "graph": graph}
