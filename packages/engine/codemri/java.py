"""Java AST symbols and conservative, arity-aware direct call resolution."""
from pathlib import Path
from collections import defaultdict
from tree_sitter import Language, Parser
import tree_sitter_java
from .models import Symbol, Edge, CallSite, merge_edges
from .symbol_details import function_details, declaration_details, function_calls


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node):
    return node.text.decode('utf-8',errors='replace') if node else ''


def ancestor(node, types):
    parent=node.parent
    while parent:
        if parent.type in types:
            return parent
        parent=parent.parent


CLASSES={'class_declaration','interface_declaration','enum_declaration','record_declaration'}
METHODS={'method_declaration','constructor_declaration'}


def extend_java(root, graph, listing=None):
    from .architecture import inventory
    files,_=inventory(root, listing)
    classes=[]; methods=[]; trees=[]
    by_class=defaultdict(list); by_name=defaultdict(list)
    for path,source in files.items():
        if not path.endswith('.java'):
            continue
        data=source.encode();tree=Parser(Language(tree_sitter_java.language())).parse(data)
        trees.append((path,tree))
        if tree.root_node.has_error:
            graph.warnings.append(f'Java parse errors: {path}; graph may be incomplete')
        module=Symbol(id=path,name=Path(path).name,kind='module',path=path,start_line=1,end_line=tree.root_node.end_point.row+1,source=source)
        graph.nodes.append(module)
        for node in walk(tree.root_node):
            if node.type not in CLASSES|METHODS:
                continue
            name=node.child_by_field_name('name')
            if not name:
                continue
            owner=ancestor(node,CLASSES)
            owner_id=f'{path}::java@{owner.start_byte}' if owner else None
            def column(offset):
                return len(data[data.rfind(b'\n',0,offset)+1:offset].decode('utf-8').encode('utf-16-le'))//2
            symbol=Symbol(id=f'{path}::java@{node.start_byte}',name=text(name),kind=node.type,path=path,start_line=node.start_point.row+1,end_line=node.end_point.row+1,start_column=column(node.start_byte),end_column=column(node.end_byte),source=text(node))
            if node.type in METHODS:
                symbol.details=function_details(node, owner)
                symbol.call_occurrences=function_calls(node, path, data)
                symbol.details["calls"]=list(dict.fromkeys(c.label for c in symbol.call_occurrences))
                symbol.signature=symbol.name+text(node.child_by_field_name('parameters'))
            else:
                symbol.details=declaration_details(node)
            graph.nodes.append(symbol)
            container=ancestor(node,CLASSES|METHODS)
            parent_id=f'{path}::java@{container.start_byte}' if container else path
            graph.edges.append(Edge(source=parent_id,target=symbol.id,kind='contains'))
            record={'ast':node,'symbol':symbol,'owner':owner_id,'path':path,'data':data}
            if node.type in CLASSES:
                classes.append(record);by_name[symbol.name].append(record)
            else:
                parameters=node.child_by_field_name('parameters')
                record['arity']=len(parameters.named_children) if parameters else 0
                methods.append(record);by_class[owner_id].append(record)
    class_by_id={c['symbol'].id:c for c in classes}

    def resolve_type(type_name, path):
        simple=type_name.split('<')[0].replace('[]','').split('.')[-1].strip()
        candidates=by_name.get(simple,[])
        same=[c for c in candidates if c['path']==path]
        if len(same)==1:return same[0]['symbol'].id
        if len(candidates)==1:return candidates[0]['symbol'].id
        # Duplicate simple class names are deliberately left unresolved.
        return None

    def class_chain(owner):
        seen=set()
        while owner and owner not in seen:
            seen.add(owner);yield owner
            cls=class_by_id.get(owner)
            if not cls:break
            superclass=cls['ast'].child_by_field_name('superclass')
            owner=resolve_type(text(superclass).removeprefix('extends ').strip(),cls['path']) if superclass else None

    def binding(receiver, method):
        owner=method['owner'];pos=method['ast'].start_byte
        # Parameters and in-scope locals shadow fields; keep ambiguous bindings unresolved.
        local=[]
        for n in walk(method['ast']):
            if n.type=='formal_parameter' and text(n.child_by_field_name('name'))==receiver:
                local.append(text(n.child_by_field_name('type')))
            elif n.type=='local_variable_declaration':
                for child in n.named_children:
                    if child.type=='variable_declarator' and text(child.child_by_field_name('name'))==receiver:
                        local.append(text(n.child_by_field_name('type')))
            elif n.type=='enhanced_for_statement' and text(n.child_by_field_name('name'))==receiver:
                local.append(text(n.child_by_field_name('type')))
        if local:
            return resolve_type(local[0],method['path']) if len(set(local))==1 else None
        for clsid in class_chain(owner):
            cls=class_by_id[clsid]
            body=cls['ast'].child_by_field_name('body')
            for field in body.named_children if body else []:
                if field.type!='field_declaration':continue
                if any(c.type=='variable_declarator' and text(c.child_by_field_name('name'))==receiver for c in field.named_children):
                    return resolve_type(text(field.child_by_field_name('type')),method['path'])
        return resolve_type(receiver,method['path'])

    for method in methods:
        for call in walk(method['ast']):
            if call.type not in {'method_invocation','object_creation_expression'}:
                continue
            # Calls in nested methods belong to those methods, not the outer one.
            containing=ancestor(call,METHODS)
            if containing!=method['ast']:continue
            arguments=call.child_by_field_name('arguments');arity=len(arguments.named_children) if arguments else 0
            if call.type=='object_creation_expression':
                target_class=resolve_type(text(call.child_by_field_name('type')),method['path'])
                name=None
            else:
                name=text(call.child_by_field_name('name'))
                receiver=text(call.child_by_field_name('object'))
                target_class=method['owner'] if receiver in {'','this'} else binding(receiver.removeprefix('this.'),method)
            candidates=[]
            for clsid in class_chain(target_class):
                matches=[m for m in by_class[clsid] if m['arity']==arity and (m['ast'].type=='constructor_declaration' if name is None else m['symbol'].name==name and m['ast'].type=='method_declaration')]
                if matches:
                    candidates=matches;break
            if len(candidates)==1:
                graph.edges.append(Edge(source=method['symbol'].id,target=candidates[0]['symbol'].id,kind='calls',call_sites=[CallSite(
                    path=method['path'], line=call.start_point.row+1,
                    column=len(method['data'][call.start_byte-call.start_point.column:call.start_byte].decode('utf-8').encode('utf-16-le'))//2,
                    expression=text(call))]))
            elif target_class:
                graph.warnings.append(f'Unresolved Java call: {method["path"]}:{call.start_point.row+1}: {text(call.child_by_field_name("name")) or "constructor"} (overload or unsupported dispatch)')
    graph.edges=merge_edges(graph.edges)
    return graph
