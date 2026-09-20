"""Semantic changes relative to the last explicitly reviewed snapshot."""
from collections import defaultdict


def changes(before, after):
    # Parser IDs contain offsets. Pair declarations by qualified scope, then source,
    # then occurrence order, so insertions do not turn every later node into an add.
    def groups(graph):
        result = defaultdict(list)
        for n in graph.nodes:
            parents = sorted((p for p in graph.nodes if p.path == n.path and p.id != n.id
                              and p.kind != 'module' and p.start_line <= n.start_line
                              and p.end_line >= n.end_line
                              and (p.start_line, p.start_column) < (n.start_line, n.start_column)),
                             key=lambda p: (p.start_line, p.start_column))
            result[(n.path, n.kind, tuple(p.name for p in parents), n.name)].append(n)
        return result
    old, new = groups(before), groups(after)
    pairs, mapped = [], {}
    for key in sorted(old.keys() | new.keys()):
        left, right = list(old[key]), list(new[key])
        for a in left[:]:
            b = next((b for b in right if b.source == a.source), None)
            if b:
                pairs.append((a,b)); left.remove(a); right.remove(b)
        while left or right:
            pairs.append((left.pop(0) if left else None, right.pop(0) if right else None))
    nodes = []
    for a, b in pairs:
        if a and b:
            mapped[a.id] = b.id
        status = 'added' if a is None else 'removed' if b is None else 'modified'
        if a and b and (a.source, a.name, a.kind, a.details) == (b.source, b.name, b.kind, b.details):
            continue
        n = b or a
        nodes.append(dict(id=n.id, old_id=a.id if a else None, name=n.name, path=n.path, line=n.start_line, status=status))
    def indexed(graph, remap):
        return {(remap.get(e.source,e.source), remap.get(e.target,e.target), e.kind): e for e in graph.edges}
    left, right = indexed(before, mapped), indexed(after, {})
    edges = []
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key), right.get(key)
        # Moving a call down a few lines does not create a new connection.
        signature = lambda e: sorted((s.path, s.expression) for s in e.call_sites)
        if a and b and signature(a) == signature(b):
            continue
        e = b or a
        edges.append(dict(source=e.source, target=e.target, kind=e.kind, status='added' if a is None else 'removed' if b is None else 'modified'))
    return dict(nodes=nodes, edges=edges, baseline_revision=before.revision, revision=after.revision)
