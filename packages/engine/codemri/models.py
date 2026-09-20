from pydantic import BaseModel, Field

class CallOccurrence(BaseModel):
    label: str
    path: str
    line: int
    column: int = 0
    expression: str = ""
    target_id: str | None = None


class Symbol(BaseModel):
    id: str
    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    source: str = ""
    details: dict[str, list[str]] = Field(default_factory=dict)
    call_occurrences: list[CallOccurrence] | None = None
    signature: str | None = None
    component_id: str | None = None
    module_id: str | None = None

class CallSite(BaseModel):
    path: str
    line: int
    column: int = 0
    expression: str = ""


class Edge(BaseModel):
    source: str
    target: str
    kind: str
    call_sites: list[CallSite] = Field(default_factory=list)


def merge_edges(edges):
    """Keep one graph edge per relationship, preserving every source occurrence."""
    unique = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.kind)
        if key not in unique:
            unique[key] = edge
        else:
            existing = unique[key]
            positions = {(s.path, s.line, s.column) for s in existing.call_sites}
            existing.call_sites.extend(s for s in edge.call_sites if (s.path, s.line, s.column) not in positions)
    return list(unique.values())


class Graph(BaseModel):
    schema_version: int = 2
    root: str
    revision: str
    nodes: list[Symbol] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    layers: dict = Field(default_factory=dict)
    inventory: dict = Field(default_factory=dict)
