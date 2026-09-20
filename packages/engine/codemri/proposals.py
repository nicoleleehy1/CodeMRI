"""Read-only graph previews and line diffs for unapproved agent edits."""
import difflib
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from .analyzer import analyze
from .changes import changes

EXCLUDED = {'.git', '.codemri', '.codemri-preview', 'node_modules', '.venv', '__pycache__'}


def line_diff(before, after):
    result = []
    old_line = new_line = 0
    for line in difflib.unified_diff((before or '').splitlines(), (after or '').splitlines(), n=3, lineterm=''):
        if line.startswith(('---', '+++')) and not result:
            continue
        if line.startswith('@@'):
            spans = line.split(' ')
            old_line, new_line = int(spans[1][1:].split(',')[0]), int(spans[2][1:].split(',')[0])
            result.append({'kind': 'hunk', 'text': line})
        else:
            sign, text = line[:1], line[1:]
            result.append({'kind': 'added' if sign == '+' else 'removed' if sign == '-' else 'context',
                           'text': text, 'old': None if sign == '+' else old_line,
                           'new': None if sign == '-' else new_line})
            if sign != '+': old_line += 1
            if sign != '-': new_line += 1
    if before != after and not result:
        result.append({'kind': 'hunk', 'text': 'File existence or line endings changed (including the final newline).'})
    return result


def preview(root, files):
    root = Path(root).resolve()
    baseline = analyze(root)
    diffs = []
    with TemporaryDirectory(prefix='codemri-review-') as temporary:
        staging = Path(temporary) / root.name
        def ignored(directory, names):
            return [name for name in names if name in EXCLUDED or (Path(directory) / name).is_symlink()]
        shutil.copytree(root, staging, ignore=ignored)
        for item in files:
            name = Path(item.path)
            if name.is_absolute() or any(part in {'..', *EXCLUDED} for part in name.parts) or not name.parts:
                raise ValueError('Invalid proposal path')
            target = staging / name
            if item.after is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(item.after, encoding='utf-8')
            diffs.append({'path': item.path, 'status': 'added' if item.before is None else 'removed' if item.after is None else 'modified',
                          'lines': line_diff(item.before, item.after)})
        graph = analyze(staging)
        graph.root = str(root)
    return {'graph': graph, 'baseline': baseline, 'changes': changes(baseline, graph), 'files': diffs}
