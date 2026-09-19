from pydantic import BaseModel, Field

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
    signature: str | None = None
    component_id: str | None = None
    module_id: str | None = None

class Edge(BaseModel):
    source: str
    target: str
    kind: str

class Graph(BaseModel):
    schema_version: int = 2
    root: str
    revision: str
    nodes: list[Symbol] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    layers: dict = Field(default_factory=dict)
    inventory: dict = Field(default_factory=dict)
