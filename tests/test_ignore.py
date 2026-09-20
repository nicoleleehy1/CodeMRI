"""A3 / P1.3: ignored and secret files never reach the graph, the snapshot, or AI excerpt input."""
import json
from codemri.analyzer import analyze
from codemri.architecture import inventory
from codemri.ignore import walk_repository, parse_gitignore, Ignorer, redact_secrets, is_secret_file
from codemri.semantic import context_payload
from codemri.store import Store


def fixture(root):
    (root / '.gitignore').write_text('generated/\n*.log\n/config/local.ts\n!keep.log\nsecret-notes.md\n')
    (root / 'app.ts').write_text('import { helper } from "./generated/out";\nexport function run() { return helper(); }\n')
    (root / 'generated').mkdir()
    (root / 'generated/out.ts').write_text('export function helper() { return "TOKEN=abcdef123456789"; }\n')
    (root / 'config').mkdir()
    (root / 'config/local.ts').write_text('export const LOCAL = "hidden";\n')
    (root / 'config/shared.ts').write_text('export const SHARED = 1;\n')
    (root / 'debug.log').write_text('log')
    (root / 'keep.log').write_text('log')
    (root / '.env').write_text('OPENAI_API_KEY=sk-live-supersecretvalue0123456789\n')
    (root / '.env.example').write_text('OPENAI_API_KEY=\n')
    (root / 'server.pem').write_text('-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n')
    (root / 'nested').mkdir()
    (root / 'nested/.gitignore').write_text('scratch.ts\n')
    (root / 'nested/scratch.ts').write_text('export const SCRATCH = 1;\n')
    (root / 'nested/real.ts').write_text('export const REAL = 1;\n')
    (root / '.venv-old').mkdir()
    (root / '.venv-old/pyvenv.cfg').write_text('home = /usr\n')
    (root / '.venv-old/site.py').write_text('x = 1\n')
    (root / 'env').mkdir()
    (root / 'env/pyvenv.cfg').write_text('home = /usr\n')
    (root / 'env/thing.ts').write_text('export const V = 1;\n')
    return root


def test_walk_honours_gitignore_secret_files_and_virtualenvs(tmp_path):
    walk = walk_repository(fixture(tmp_path))
    assert walk.files == ['.env.example', '.gitignore', 'app.ts', 'config/shared.ts', 'keep.log', 'nested/.gitignore', 'nested/real.ts']
    assert walk.skipped['gitignored'] == ['config/local.ts', 'debug.log', 'generated/', 'nested/scratch.ts']
    assert walk.skipped['secret'] == ['.env', 'server.pem']
    assert walk.skipped['virtualenv'] == ['.venv-old/', 'env/']
    assert any(s.startswith('Skipped 4 gitignored') for s in walk.summary())


def test_gitignore_semantics():
    rules = parse_gitignore('# comment\n\n*.log\n!important.log\nbuild/\n/root-only.txt\ndocs/**/*.md\n**/deep\n', '')
    ig = Ignorer.__new__(Ignorer); ig.rules = rules; ig.git_ignored = None
    assert ig.ignored('a/b/c.log', False) and not ig.ignored('a/important.log', False)
    assert ig.ignored('build', True) and not ig.ignored('build', False)
    assert ig.ignored('root-only.txt', False) and not ig.ignored('sub/root-only.txt', False)
    assert ig.ignored('build/inside.ts', False)          # children of an ignored directory
    assert ig.ignored('x/deep', True) and ig.ignored('deep', False)
    nested = parse_gitignore('*.tmp\n', 'pkg')
    ig.rules = nested
    assert ig.ignored('pkg/a.tmp', False) and not ig.ignored('other/a.tmp', False)


def test_ignored_secret_never_appears_in_graph_snapshot_or_ai_excerpts(tmp_path):
    (tmp_path / 'repo').mkdir()
    root = fixture(tmp_path / 'repo')
    graph = analyze(root)
    names = {n.name for n in graph.nodes}
    paths = {n.path for n in graph.nodes}
    assert 'run' in names and 'SHARED' in names and 'REAL' in names
    assert not ({'helper', 'LOCAL', 'SCRATCH', 'V'} & names)
    assert not any(p.startswith(('generated', '.venv-old', 'env/')) or p in {'.env', 'server.pem', 'config/local.ts'} for p in paths)
    assert any('Unresolved import' in w and 'generated/out' in w for w in graph.warnings)
    assert graph.inventory['skipped'] == {'gitignored': 4, 'secret': 2, 'virtualenv': 2, 'residue': 0}
    store = Store(tmp_path / 'cache')
    snapshot = json.dumps(store.load(store.save(graph)).model_dump())
    assert 'supersecretvalue' not in snapshot and 'BEGIN PRIVATE KEY' not in snapshot and 'hidden' not in snapshot
    files, _ = inventory(root)
    assert set(files) == {'app.ts', 'config/shared.ts', 'nested/real.ts'}
    payload = json.dumps(context_payload(files))
    assert 'supersecretvalue' not in payload and '.env' not in payload and 'generated/out.ts' not in payload


def test_secret_shaped_strings_are_redacted_in_ai_excerpts_but_code_is_kept():
    files = {'settings.py': 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123"\npassword = "hunter2hunter2"\nvalue = compute(1)\nghp_' + 'A' * 36 + '\n'}
    payload = context_payload(files)
    source = payload['source_files'][0]['source']
    assert 'sk-abcdef' not in source and 'hunter2' not in source and 'ghp_AAAA' not in source
    assert '3| value = compute(1)' in source and 'API_KEY = "[redacted-secret]"' in source
    assert payload['coverage']['redacted_secrets'] == 3
    text, count = redact_secrets('token = short\nnothing here\n')
    assert count == 0 and 'short' in text


def test_secret_file_patterns():
    assert all(is_secret_file(n) for n in ['.env', '.env.local', 'id_rsa', 'id_rsa.pub', 'server.key', 'cert.pem', 'gcp-credentials.json', '.npmrc'])
    assert not any(is_secret_file(n) for n in ['.env.example', 'main.py', 'keys.ts', 'environment.ts'])


def test_git_checkout_keeps_tracked_files_matching_ignore_rules(tmp_path):
    import subprocess
    root = tmp_path / 'repo'; root.mkdir()
    (root / 'src').mkdir(); (root / 'src/main.ts').write_text('export const A = 1;\n')
    (root / '.gitignore').write_text('src\n*.log\n')
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', '.gitignore', '-f', 'src/main.ts'], cwd=root, check=True)
    (root / 'src/new.ts').write_text('export const B = 2;\n')
    (root / 'out.log').write_text('x')
    walk = walk_repository(root)
    assert 'src/main.ts' in walk.files and 'src/new.ts' not in walk.files and 'out.log' not in walk.files
    assert set(walk.skipped['gitignored']) == {'src/new.ts', 'out.log'}
    assert {n.name for n in analyze(root).nodes} >= {'A'} and 'B' not in {n.name for n in analyze(root).nodes}
