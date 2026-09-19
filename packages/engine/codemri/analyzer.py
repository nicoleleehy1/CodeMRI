"""Small conservative TypeScript AST graph builder. No repository code is executed."""
from pathlib import Path
import hashlib
import os
from tree_sitter import Language, Parser
import tree_sitter_typescript as ts
from .models import Graph, Symbol, Edge
from .architecture import build_layers

SKIP = {"node_modules", ".git", ".venv", "dist", "build", "coverage", ".next", ".codemri"}
EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"}

def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)

def text(node):
    return node.text.decode("utf-8", errors="replace") if node else ""

def analyze(root: Path) -> Graph:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Repository directory does not exist")
    nodes, edges, warnings, records = [], [], [], {}
    digest = hashlib.sha256()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not Path(directory, d).is_symlink())
        for filename in sorted(names):
            file = Path(directory, filename)
            if file.suffix not in EXTENSIONS or file.is_symlink():
                continue
            if file.stat().st_size > 1_000_000:
                warnings.append(f"Skipped large file: {file.relative_to(root)}")
                continue
            data = file.read_bytes()
            path = file.relative_to(root).as_posix()
            digest.update(path.encode() + b"\0" + data)
            parser = Parser(Language(ts.language_tsx() if file.suffix in {".tsx", ".jsx"} else ts.language_typescript()))
            tree = parser.parse(data)
            if tree.root_node.has_error:
                warnings.append(f"Parse errors: {path}; graph may be incomplete")
            module = Symbol(id=path, name=path, kind="module", path=path, start_line=1,
                            end_line=tree.root_node.end_point.row + 1, source=data.decode("utf-8", errors="replace"))
            nodes.append(module)
            symbols = []
            for ast in walk(tree.root_node):
                kind = ast.type
                name = ast.child_by_field_name("name")
                if kind == "variable_declarator":
                    value = ast.child_by_field_name("value")
                    if not value or value.type not in {"arrow_function", "function_expression"}:
                        continue
                    kind = "function"
                elif kind not in {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "type_alias_declaration"}:
                    continue
                if not name:
                    continue
                symbol = Symbol(id=f"{path}::{text(name)}@{ast.start_byte}", name=text(name), kind=kind,
                    path=path, start_line=ast.start_point.row+1, end_line=ast.end_point.row+1,
                    start_column=len(data[data.rfind(b"\n",0,ast.start_byte)+1:ast.start_byte].decode("utf-8").encode("utf-16-le"))//2,
                    end_column=len(data[data.rfind(b"\n",0,ast.end_byte)+1:ast.end_byte].decode("utf-8").encode("utf-16-le"))//2,
                    source=text(ast))
                symbols.append((ast, symbol))
                nodes.append(symbol)
                edges.append(Edge(source=path, target=symbol.id, kind="contains"))
            records[path] = (tree, symbols)
    for path, (tree, symbols) in records.items():
        imports = {}
        for ast in walk(tree.root_node):
            if ast.type != "import_statement":
                continue
            source = text(ast.child_by_field_name("source")).strip("\"'")
            if not source.startswith("."):
                continue
            base = (root / path).parent / source
            candidates = [base] + [Path(str(base)+ext) for ext in sorted(EXTENSIONS)] + [base / ("index"+ext) for ext in sorted(EXTENSIONS)]
            if base.suffix == ".js":
                candidates.insert(0, base.with_suffix(".ts"))
            target = next((p.resolve().relative_to(root).as_posix() for p in candidates if p.resolve().is_relative_to(root) and p.resolve().relative_to(root).as_posix() in records), None)
            if not target:
                warnings.append(f"Unresolved import: {path}: {source}")
                continue
            edges.append(Edge(source=path, target=target, kind="imports"))
            for spec in walk(ast):
                if spec.type == "import_specifier":
                    original = text(spec.child_by_field_name("name"))
                    local = text(spec.child_by_field_name("alias")) or original
                    matches = [s for _, s in records[target][1] if s.name == original]
                    if len(matches) == 1:
                        imports[local] = matches[0]
        for call in walk(tree.root_node):
            if call.type != "call_expression":
                continue
            fn = call.child_by_field_name("function")
            owners = [(a, s) for a, s in symbols if a.start_byte <= call.start_byte and a.end_byte >= call.end_byte]
            owner = min(owners, key=lambda pair: pair[0].end_byte-pair[0].start_byte)[1] if owners else None
            target = None
            if fn and fn.type == "identifier":
                matches = [s for _, s in symbols if s.name == text(fn)]
                target = matches[0] if len(matches) == 1 else imports.get(text(fn)) if not matches else None
            if target:
                edges.append(Edge(source=owner.id if owner else path, target=target.id, kind="calls"))
            else:
                warnings.append(f"Unresolved call: {path}:{call.start_point.row+1}: {text(fn)}")
    unique = {(e.source,e.target,e.kind):e for e in edges}
    from .java import extend_java
    graph = Graph(root=str(root), revision=digest.hexdigest()[:16], nodes=nodes, edges=list(unique.values()), warnings=warnings)
    return build_layers(root, extend_java(root, graph))
