"""Small conservative TypeScript AST graph builder. No repository code is executed."""
from pathlib import Path
import hashlib
from tree_sitter import Language, Parser
import tree_sitter_typescript as ts
from .models import Graph, Symbol, Edge, CallSite, merge_edges
from .architecture import build_layers
from .ignore import walk_repository
from .symbol_details import function_details, declaration_details, function_calls, attach_call_targets, FUNCTIONS, CLASSES

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
    listing = walk_repository(root)
    for path in listing.files:
        file = root / path
        if file.suffix not in EXTENSIONS:
            continue
        if file.stat().st_size > 1_000_000:
            warnings.append(f"Skipped large file: {path}")
            continue
        data = file.read_bytes()
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
                if value and value.type in {"arrow_function", "function_expression"}:
                    kind = "function"
                else:
                    parent = ast.parent
                    local = False
                    while parent:
                        if parent.type in FUNCTIONS | CLASSES:
                            local = True
                            break
                        parent = parent.parent
                    if local:
                        continue
                    kind = "constant" if text(ast.parent).lstrip().startswith("const ") else "global_variable"
            elif kind not in {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "type_alias_declaration", "enum_declaration"}:
                continue
            if not name:
                continue
            symbol = Symbol(id=f"{path}::{text(name)}@{ast.start_byte}", name=text(name), kind=kind,
                path=path, start_line=ast.start_point.row+1, end_line=ast.end_point.row+1,
                start_column=len(data[data.rfind(b"\n",0,ast.start_byte)+1:ast.start_byte].decode("utf-8").encode("utf-16-le"))//2,
                end_column=len(data[data.rfind(b"\n",0,ast.end_byte)+1:ast.end_byte].decode("utf-8").encode("utf-16-le"))//2,
                source=text(ast))
            if kind in FUNCTIONS or kind == "function":
                owner = ast.parent
                while owner and owner.type not in CLASSES:
                    owner = owner.parent
                symbol.details = function_details(ast, owner)
                symbol.call_occurrences = function_calls(ast, path, data)
                symbol.details["calls"] = list(dict.fromkeys(c.label for c in symbol.call_occurrences))
            elif kind in CLASSES or kind in {"type_alias_declaration", "enum_declaration"}:
                symbol.details = declaration_details(ast)
            elif kind in {"constant", "global_variable"}:
                symbol.details = {"values": [text(ast.child_by_field_name("value"))]}
            symbols.append((ast, symbol))
            nodes.append(symbol)
        for ast, symbol in symbols:
            owners = [(a, s) for a, s in symbols if a.start_byte <= ast.start_byte and a.end_byte >= ast.end_byte and s.id != symbol.id]
            parent = min(owners, key=lambda pair: pair[0].end_byte-pair[0].start_byte)[1].id if owners else path
            edges.append(Edge(source=parent, target=symbol.id, kind="contains"))
        records[path] = (tree, symbols, data)
    for path, (tree, symbols, source_bytes) in records.items():
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
                edges.append(Edge(source=owner.id if owner else path, target=target.id, kind="calls", call_sites=[CallSite(
                    path=path, line=call.start_point.row+1,
                    column=len(source_bytes[call.start_byte-call.start_point.column:call.start_byte].decode("utf-8").encode("utf-16-le"))//2,
                    expression=text(call))]))
            else:
                warnings.append(f"Unresolved call: {path}:{call.start_point.row+1}: {text(fn)}")
    unique = merge_edges(edges)
    from .java import extend_java
    graph = Graph(root=str(root), revision=digest.hexdigest()[:16], nodes=nodes, edges=unique, warnings=warnings)
    return build_layers(root, attach_call_targets(extend_java(root, graph, listing)), listing)
