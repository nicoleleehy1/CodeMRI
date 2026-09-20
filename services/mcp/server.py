"""Run from monorepo root: python -m services.mcp.server."""
from mcp.server.fastmcp import FastMCP
from codemri.analyzer import analyze
from codemri.roots import resolve_allowed
from codemri.store import Store
from codemri.context import impact, compile_context

mcp = FastMCP("CodeMRI")
store = Store()

@mcp.tool()
def analyze_repository(root: str) -> dict:
    """Analyze a local repository under CODEMRI_ALLOWED_ROOT and persist its graph.

    Symbols and call edges are extracted for TypeScript/JavaScript and Java; other languages are
    inventoried into the architecture layer only. Returns the repo_id used by the other tools.
    """
    graph = analyze(resolve_allowed(root))
    return {"repo_id": store.save(graph), "revision": graph.revision, "nodes": len(graph.nodes), "warnings": graph.warnings}

@mcp.tool()
def get_architecture(repo_id: str, compact: bool = True) -> dict:
    """Return the persisted static graph. Reanalyze after edits.

    With compact=True (default) symbol source bodies and per-call-site details are omitted so the
    response stays small; fetch a symbol's source with get_symbol. compact=False returns everything.
    """
    graph = store.load(repo_id)
    if not compact:
        return graph.model_dump()
    return graph.model_dump(exclude={'nodes': {'__all__': {'source', 'call_occurrences'}}, 'edges': {'__all__': {'call_sites'}}})

@mcp.tool()
def get_symbol(repo_id: str, symbol_id: str) -> dict:
    """Return source and location for a graph symbol."""
    node = next((n for n in store.load(repo_id).nodes if n.id == symbol_id), None)
    if node is None:
        raise ValueError(f'Unknown symbol ID {symbol_id!r}; list IDs with get_architecture')
    return node.model_dump()

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
def find_tests(repo_id: str, change: str, seed_ids: list[str] | None = None) -> dict:
    """Tests heuristically associated with a change, each with the link (call, import, naming) that justifies it.

    Symbols listed under no_identified_tests have no discovered link; that does not mean they are untested.
    Returns run selectors but never executes anything.
    """
    return impact(store.load(repo_id), change, seed_ids)["tests"]

@mcp.tool()
def compile_agent_context(repo_id: str, task: str, budget: int = 4000, seed_ids: list[str] | None = None) -> dict:
    """Compile graph-selected source within a cl100k_base token budget."""
    return compile_context(store.load(repo_id), task, budget, seed_ids)

if __name__ == "__main__":
    mcp.run(transport="stdio")
