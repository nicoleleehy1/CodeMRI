import os
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from codemri.analyzer import analyze
from codemri.roots import resolve_allowed
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

def allowed_or_403(root: str) -> Path:
    try:
        return resolve_allowed(root)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

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
    root = allowed_or_403(request.root)
    try:
        graph = analyze(root)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    repo_id = store.save(graph)
    return {"repo_id": repo_id, "graph": graph, **store.review(repo_id)}

@app.get("/graphs/{repo_id}")
def get_graph(repo_id: str):
    return load(repo_id)

@app.get("/graphs/{repo_id}/freshness")
def get_freshness(repo_id: str):
    """Check source revision without replacing a saved AI architecture or review baseline."""
    graph = load(repo_id)
    try:
        current = analyze(Path(graph.root))
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    return {"revision": current.revision, "matches": current.revision == graph.revision}


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


class ReviewRequest(BaseModel):
    revision: str

@app.post("/graphs/{repo_id}/review")
def accept_review(repo_id: str, request: ReviewRequest):
    load(repo_id)
    try:
        store.accept(repo_id, request.revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return store.review(repo_id)


class ProposedFile(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    before: str | None = Field(max_length=2_000_000)
    after: str | None = Field(max_length=2_000_000)


class PreviewRequest(BaseModel):
    root: str
    files: list[ProposedFile] = Field(max_length=1000)


@app.post('/preview')
def preview_proposal(request: PreviewRequest):
    from codemri.proposals import preview
    root = allowed_or_403(request.root)
    if sum(len(f.before or '') + len(f.after or '') for f in request.files) > 20_000_000:
        raise HTTPException(413, 'Proposal is too large to preview')
    try:
        return preview(root, request.files)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


class TestRunRequest(BaseModel):
    """Explicit, user-initiated test execution. Either a change description (tests are selected by impact) or
    explicit selectors; optional proposed file contents are applied to the isolated copy first."""
    query: str | None = Field(default=None, max_length=10000)
    seed_ids: list[str] = Field(default_factory=list)
    selection: list[dict] | None = Field(default=None, max_length=500)
    files: list[ProposedFile] = Field(default_factory=list, max_length=1000)
    timeout: int = Field(default=300, ge=5, le=3600)


@app.post('/graphs/{repo_id}/tests/run')
def run_selected_tests(repo_id: str, request: TestRunRequest):
    from codemri.runner import run_tests
    graph = load(repo_id)
    root = allowed_or_403(graph.root)
    if request.selection is None:
        if not request.query and not request.seed_ids:
            raise HTTPException(400, 'Provide a change description, seed_ids, or an explicit selection')
        selection = impact(graph, request.query or '', request.seed_ids)['tests']['tests']
    else:
        selection = request.selection
    try:
        result = run_tests(root, selection, [f.model_dump() for f in request.files], request.timeout)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    result['selection'] = [{'name': t.get('name'), 'path': t.get('path'), 'selector': t.get('selector', t)} for t in selection]
    result['id'] = store.save_run(repo_id, graph.revision, result)
    result['revision'] = graph.revision
    return result


@app.get('/graphs/{repo_id}/tests/runs')
def list_test_runs(repo_id: str):
    load(repo_id)
    return store.runs(repo_id)
