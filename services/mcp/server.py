"""Run from monorepo root: python -m services.mcp.server."""
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from codemri.analyzer import analyze
from codemri.store import Store
from codemri.context import impact, compile_context

mcp = FastMCP("CodeMRI")
store = Store()

@mcp.tool()
def analyze_repository(root: str) -> dict:
    """Build and persist a graph of a local TS/JS repository under the allowed root."""
    path = Path(root).resolve()
    allowed = Path(os.environ.get("CODEMRI_ALLOWED_ROOT", os.getcwd())).resolve()
    if not path.is_relative_to(allowed):
        raise ValueError("Repository is outside CODEMRI_ALLOWED_ROOT")
    graph = analyze(path)
    return {"repo_id": store.save(graph), "revision": graph.revision, "nodes": len(graph.nodes), "warnings": graph.warnings}

@mcp.tool()
def get_architecture(repo_id: str) -> dict:
    """Return the persisted static graph. Reanalyze after edits."""
    return store.load(repo_id).model_dump()

@mcp.tool()
def get_symbol(repo_id: str, symbol_id: str) -> dict:
    """Return source and location for a graph symbol."""
    return next(n.model_dump() for n in store.load(repo_id).nodes if n.id == symbol_id)

@mcp.tool()
def find_callers(repo_id: str, symbol_id: str) -> list[str]:
    """Return statically resolved direct callers."""
    return [e.source for e in store.load(repo_id).edges if e.kind == "calls" and e.target == symbol_id]

@mcp.tool()
def find_callees(repo_id: str, symbol_id: str) -> list[str]:
    """Return statically resolved direct callees."""
    return [e.target for e in store.load(repo_id).edges if e.kind == "calls" and e.source == symbol_id]

@mcp.tool()
def impact_analysis(repo_id: str, change: str, seed_ids: list[str] | None = None) -> dict:
    """Prototype: lexical matching followed by reverse call traversal."""
    return impact(store.load(repo_id), change, seed_ids)

@mcp.tool()
def compile_agent_context(repo_id: str, task: str, budget: int = 4000, seed_ids: list[str] | None = None) -> dict:
    """Compile graph-selected source within a cl100k_base token budget."""
    return compile_context(store.load(repo_id), task, budget, seed_ids)

if __name__ == "__main__":
    mcp.run(transport="stdio")
