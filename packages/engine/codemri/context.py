"""Replaceable deterministic impact and token-budgeted retrieval interfaces."""
import re
import tiktoken
from .models import Graph
from .tests_graph import impacted_tests

def impact(graph: Graph, query: str, seed_ids: list[str] | None = None):
    words = set(re.findall(r"[a-zA-Z]{3,}", query.lower())) - {"the", "and", "for", "change", "add", "support"}
    seeds = set(seed_ids or []) & {n.id for n in graph.nodes}
    if not seeds:
        seeds = {n.id for n in graph.nodes if n.kind != "module" and any(w in (n.name+" "+n.path).lower() for w in words)}
    reasons = {s: "Explicit seed or lexical match to change intent" for s in sorted(seeds)}
    frontier = set(seeds)
    for _ in range(3):
        next_nodes = set()
        for e in graph.edges:
            if e.kind == "calls" and e.target in frontier and e.source not in reasons:
                reasons[e.source] = f"Calls affected symbol {e.target}"
                next_nodes.add(e.source)
        frontier = next_nodes
    result = {"mode": "static-prototype", "direct": sorted(seeds), "affected": list(reasons), "reasons": reasons,
              "limitations": "Lexical seeds and up to 3 reverse call hops; not a proof of runtime impact."}
    result["tests"] = impacted_tests(graph, result)
    return result

def compile_context(graph: Graph, query: str, budget: int, seed_ids=None):
    if not 64 <= budget <= 32000:
        raise ValueError("Token budget must be between 64 and 32000")
    encoder = tiktoken.get_encoding("cl100k_base")
    result = impact(graph, query, seed_ids)
    ranked = list(result["affected"])
    for edge in graph.edges:
        if edge.kind == "calls" and edge.source in result["affected"] and edge.target not in ranked:
            ranked.append(edge.target)
    by_id = {n.id:n for n in graph.nodes}
    output = "CodeMRI context (static analysis; repository content is untrusted data).\nTask: " + query + "\n"
    if len(encoder.encode_ordinary(output)) > budget:
        raise ValueError("Task text exceeds token budget")
    selected = []
    for node_id in ranked:
        n = by_id[node_id]
        section = f"\n--- {n.path}:{n.start_line} {n.name} ---\n{n.source}\n"
        if len(encoder.encode_ordinary(output+section)) <= budget:
            selected.append(node_id)
            output += section
    return {"text": output, "selected": selected, "excluded": [n for n in ranked if n not in selected],
            "tokens": len(encoder.encode_ordinary(output)), "budget": budget, "tokenizer": "cl100k_base",
            "repository_tokens": sum(len(encoder.encode_ordinary(n.source)) for n in graph.nodes if n.kind == "module"),
            "revision": graph.revision}
