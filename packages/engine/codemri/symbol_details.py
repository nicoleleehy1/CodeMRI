"""Source-syntax labels for function cards; no inferred runtime values."""
FUNCTIONS = {'method_declaration', 'constructor_declaration', 'method_definition',
             'function_declaration', 'function_expression', 'arrow_function'}
CLASSES = {'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration'}


def function_details(root, owner=None):
    result = {key: [] for key in ('parameters', 'variables', 'attributes', 'strings', 'types', 'nested', 'calls', 'returns')}

    def text(node):
        return node.text.decode('utf-8', errors='replace') if node else ''

    def add(key, node):
        value = text(node)
        if value and value not in result[key]:
            result[key].append(value)

    fields = set()
    if owner:
        result['types'].append(text(owner.child_by_field_name('name')))
        body = owner.child_by_field_name('body')
        for field in body.named_children if body else []:
            if field.type == 'field_declaration':
                fields.update(text(c.child_by_field_name('name')) for c in field.named_children if c.type == 'variable_declarator')
            elif field.type in {'public_field_definition', 'property_signature'}:
                fields.add(text(field.child_by_field_name('name')))

    # Arrow functions are represented by their enclosing variable declarator.
    scope = root.child_by_field_name('value') if root.type == 'variable_declarator' else root
    parameters = scope.child_by_field_name('parameters') or scope.child_by_field_name('parameter')
    if parameters:
        for p in parameters.named_children if parameters.type == 'formal_parameters' else [parameters]:
            add('parameters', p)

    def visit(node):
        if node != scope and node.type in FUNCTIONS | CLASSES:
            if node.type in CLASSES:
                add('types', node.child_by_field_name('name'))
            else:
                name = node.child_by_field_name('name')
                if not name and node.parent and node.parent.type == 'variable_declarator':
                    name = node.parent.child_by_field_name('name')
                add('nested', name)
            return
        kind = node.type
        if kind in {'string', 'string_literal', 'template_string'}:
            add('strings', node)
        elif kind in {'call_expression', 'method_invocation'}:
            if kind == 'call_expression':
                add('calls', node.child_by_field_name('function'))
            else:
                receiver = text(node.child_by_field_name('object'))
                name = text(node.child_by_field_name('name'))
                value = (receiver + '.' if receiver else '') + name
                if value not in result['calls']:
                    result['calls'].append(value)
        elif kind == 'return_statement':
            value = text(node).removeprefix('return').strip().removesuffix(';').strip() or 'void'
            if value not in result['returns']:
                result['returns'].append(value)
        elif kind == 'variable_declarator':
            add('variables', node.child_by_field_name('name'))
        elif kind in {'enhanced_for_statement', 'catch_formal_parameter'}:
            add('variables', node.child_by_field_name('name'))
        elif kind in {'new_expression', 'object_creation_expression'}:
            add('types', node.child_by_field_name('constructor') or node.child_by_field_name('type'))
        elif kind in {'member_expression', 'field_access'}:
            # A method being invoked is a call label, not a data attribute.
            if not (node.parent and node.parent.type == 'call_expression' and node.parent.child_by_field_name('function') == node):
                add('attributes', node.child_by_field_name('property') or node.child_by_field_name('field'))
        elif kind in {'type_identifier', 'predefined_type', 'integral_type', 'floating_point_type', 'boolean_type', 'void_type'}:
            add('types', node)
        elif kind == 'identifier' and text(node) in fields:
            add('attributes', node)
        for child in node.named_children:
            visit(child)

    visit(scope)
    returns = scope.child_by_field_name('return_type') or scope.child_by_field_name('type')
    if returns:
        result['returns'].insert(0, 'Type: ' + text(returns).lstrip(': '))
    body = scope.child_by_field_name('body')
    if scope.type == 'arrow_function' and body and body.type != 'statement_block':
        add('returns', body)
    return result


def declaration_details(root):
    """Immediate members only: child method internals live in their own cards."""
    def text(node):
        return node.text.decode('utf-8', errors='replace') if node else ''

    result = {key: [] for key in ('constructors', 'attributes', 'methods', 'extends', 'members')}
    body = root.child_by_field_name('body')
    for member in body.named_children if body else []:
        name = member.child_by_field_name('name')
        parameters = member.child_by_field_name('parameters')
        if member.type in {'method_declaration', 'constructor_declaration', 'method_definition', 'method_signature', 'abstract_method_signature', 'construct_signature', 'call_signature'}:
            label = (text(name) or 'call') + text(parameters)
            returns = member.child_by_field_name('return_type') or member.child_by_field_name('type')
            if returns:
                label += ': ' + text(returns).lstrip(': ')
            key = 'constructors' if member.type in {'constructor_declaration', 'construct_signature'} or text(name) == 'constructor' else 'methods'
            result[key].append(label)
        elif member.type == 'field_declaration':
            field_type = text(member.child_by_field_name('type'))
            for child in member.named_children:
                if child.type == 'variable_declarator':
                    result['attributes'].append(f'{text(child.child_by_field_name("name"))}: {field_type}')
        elif member.type in {'public_field_definition', 'property_signature'}:
            result['attributes'].append(text(member).rstrip(';'))
        elif member.type in {'enum_constant', 'enum_assignment', 'property_identifier'}:
            result['members'].append(text(member))
    for child in root.named_children:
        if child.type in {'superclass', 'super_interfaces', 'extends_type_clause', 'class_heritage'}:
            result['extends'].append(text(child))
    if root.type == 'type_alias_declaration':
        result['members'].append(text(root.child_by_field_name('value')))
    return result


def function_calls(root, path, data):
    """All direct syntactic invocations, including unresolved library calls."""
    from .models import CallOccurrence
    result = []
    scope = root.child_by_field_name('value') if root.type == 'variable_declarator' else root

    def text(node):
        return node.text.decode('utf-8', errors='replace') if node else ''

    def visit(node):
        if node != scope and node.type in FUNCTIONS | CLASSES:
            return
        label = ''
        if node.type == 'call_expression':
            label = text(node.child_by_field_name('function'))
        elif node.type == 'method_invocation':
            receiver = text(node.child_by_field_name('object'))
            label = (receiver + '.' if receiver else '') + text(node.child_by_field_name('name'))
        elif node.type in {'new_expression', 'object_creation_expression'}:
            label = 'new ' + text(node.child_by_field_name('constructor') or node.child_by_field_name('type'))
        if label:
            result.append(CallOccurrence(label=label, path=path, line=node.start_point.row+1,
                column=len(data[node.start_byte-node.start_point.column:node.start_byte].decode('utf-8').encode('utf-16-le'))//2,
                expression=text(node)))
        for child in node.named_children:
            visit(child)

    visit(scope)
    return result


def attach_call_targets(graph):
    targets = {}
    for edge in graph.edges:
        if edge.kind == 'calls':
            for site in edge.call_sites:
                targets[(edge.source, site.path, site.line, site.column)] = edge.target
    for symbol in graph.nodes:
        for call in symbol.call_occurrences or []:
            call.target_id = targets.get((symbol.id, call.path, call.line, call.column))
    return graph
