"""P3.4: isolated test runner with structured, stored results."""
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from codemri.analyzer import analyze
from codemri.context import impact
from codemri.runner import run_tests, merge_junit, parse_commands, summarize, aggregate_status, Command
from codemri.store import Store
from services.api import main

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / 'examples/shop'
HAS_TSX = (SHOP / 'node_modules/.bin/tsx').exists()


def test_refuses_unknown_tools_and_dedupes():
    with pytest.raises(ValueError):
        parse_commands([{'tool': 'bash', 'args': ['-c', 'echo hi']}])
    cmds = parse_commands([{'selector': {'tool': 'node', 'args': ['--test', 'a.js']}}, {'tool': 'node', 'args': ['--test', 'a.js']}])
    assert len(cmds) == 1


def test_junit_selectors_fold_into_one_maven_run():
    cmds = merge_junit([Command('mvn', ['-q', '-Dtest=T#a', 'test']), Command('mvn', ['-q', '-Dtest=T#b', 'test']), Command('node', ['--test', 'x.js'])])
    assert [c.tool for c in cmds] == ['mvn', 'node'] and '-Dtest=T#a,T#b' in cmds[0].args


def test_output_summaries():
    assert summarize('mvn', 'Tests run: 5, Failures: 1, Errors: 0, Skipped: 1', '')['failed'] == 1
    assert summarize('node', '# pass 3\n# fail 0\n# skipped 0\n', '') == {'passed': 3, 'failed': 0, 'skipped': 0, 'no_tests_ran': False}
    assert summarize('pytest', '2 failed, 7 passed in 0.3s', '')['failed'] == 2
    assert summarize('node', '# tests 0\n# pass 0\n', '')['no_tests_ran']


def test_runner_reports_failure_faithfully_and_leaves_checkout_untouched(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'math.js').write_text('module.exports = { add: (a, b) => a + b };\n')
    (repo / 'math.test.js').write_text("const test = require('node:test'); const assert = require('node:assert');\nconst { add } = require('./math');\ntest('adds', () => assert.strictEqual(add(1, 2), 3));\n")
    before = {p: p.read_text() for p in repo.rglob('*') if p.is_file()}
    selection = [{'name': 'math.test.js', 'path': 'math.test.js', 'selector': {'tool': 'node', 'args': ['--test', 'math.test.js']}}]
    ok = run_tests(repo, selection, timeout=60)
    assert ok['status'] == 'passed' and ok['totals'] == {'passed': 1, 'failed': 0, 'skipped': 0}
    assert ok['runs'][0]['cwd'] != str(repo) and not Path(ok['runs'][0]['cwd']).exists()
    broken = run_tests(repo, selection, files=[{'path': 'math.js', 'after': 'module.exports = { add: (a, b) => a - b };\n'}], timeout=60)
    assert broken['status'] == 'failed' and broken['applied_files'] == ['math.js']
    assert broken['runs'][0]['exit_code'] != 0 and 'adds' in broken['runs'][0]['stdout']
    assert {p: p.read_text() for p in repo.rglob('*') if p.is_file()} == before
    assert run_tests(repo, [], timeout=60)['status'] == 'no_tests'


def test_timeout_is_reported(tmp_path):
    (tmp_path / 'slow.js').write_text('setTimeout(() => {}, 60000);\n')
    result = run_tests(tmp_path, [{'tool': 'node', 'args': ['slow.js']}], timeout=5)
    assert result['status'] == 'timeout' and result['runs'][0]['status'] == 'timeout' and 'Timed out' in result['runs'][0]['stderr']


@pytest.mark.skipif(not HAS_TSX, reason='run npm install in examples/shop first')
def test_api_runs_impacted_shop_tests_and_stores_results(tmp_path, monkeypatch):
    work = tmp_path / 'shop'
    shutil.copytree(SHOP, work, symlinks=True)
    store = Store(tmp_path / 'cache')
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    client = TestClient(main.app)
    repo_id = client.post('/analyze', json={'root': str(work)}).json()['repo_id']
    run = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change applyCoupon', 'timeout': 120}).json()
    assert run['status'] == 'passed', run
    assert sorted(s['path'] for s in run['selection']) == ['tests/checkout.test.ts', 'tests/pricing.test.ts']
    assert run['totals']['passed'] == 4
    broken = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change applyCoupon', 'timeout': 120,
        'files': [{'path': 'src/coupons.ts', 'before': (SHOP / 'src/coupons.ts').read_text(), 'after': 'export function applyCoupon(total: number, discount: number): number {\n  return total - discount;\n}\n'}]}).json()
    assert broken['status'] == 'failed' and broken['totals']['failed'] >= 1
    assert (work / 'src/coupons.ts').read_text().startswith('export function applyCoupon(total: number, discount: number): number {\n  return Math.max')
    assert broken['freshness']['matches'] is True
    (work / 'src/analytics.ts').write_text((work / 'src/analytics.ts').read_text() + '\n// edited after analysis\n')
    stale = client.post(f'/graphs/{repo_id}/tests/run', json={'query': 'change trackPage', 'timeout': 120}).json()
    assert stale['freshness']['matches'] is False and 'stale' in stale['note']
    runs = client.get(f'/graphs/{repo_id}/tests/runs').json()
    assert [r['status'] for r in runs] == ['passed', 'failed', 'passed'] and runs[0]['revision'] == run['revision']
    assert client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'sh', 'args': ['-c', 'true']}]}).status_code == 400


def test_aggregate_status_precedence():
    assert aggregate_status(['passed', 'no_tests']) == 'passed'
    assert aggregate_status(['no_tests', 'no_tests']) == 'no_tests'
    assert aggregate_status(['passed', 'error']) == 'error'
    assert aggregate_status(['failed', 'timeout', 'passed']) == 'timeout'
    assert aggregate_status(['failed', 'passed']) == 'failed'
    assert aggregate_status([]) == 'no_tests'


def test_api_only_runs_selectors_codemri_derived(tmp_path, monkeypatch):
    (tmp_path / 'repo').mkdir()
    (tmp_path / 'repo/math.js').write_text('module.exports = { add: (a, b) => a + b };\n')
    (tmp_path / 'repo/math.test.js').write_text("const test = require('node:test'); const assert = require('node:assert');\nconst { add } = require('./math');\ntest('add', () => assert.equal(add(1, 2), 3));\n")
    monkeypatch.setattr(main, 'store', Store(tmp_path / 'cache'))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    client = TestClient(main.app)
    repo_id = client.post('/analyze', json={'root': str(tmp_path / 'repo')}).json()['repo_id']
    evil = client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'node', 'args': ['-e', 'process.exit(0)']}]})
    assert evil.status_code == 400 and 'Unknown test selector' in evil.text
    ok = client.post(f'/graphs/{repo_id}/tests/run', json={'selection': [{'tool': 'node', 'args': ['--test', 'math.test.js']}], 'timeout': 60}).json()
    assert ok['status'] == 'passed' and ok['selection'][0]['path'] == 'math.test.js'


def test_timeout_kills_the_whole_process_tree(tmp_path):
    (tmp_path / 'repo').mkdir()
    marker = tmp_path / 'child-alive'
    # A launcher (python) that spawns a grandchild which would keep running after the launcher dies.
    (tmp_path / 'repo/child.py').write_text(f"import time, pathlib\nwhile True:\n    pathlib.Path({str(marker)!r}).write_text(str(time.time()))\n    time.sleep(0.1)\n")
    (tmp_path / 'repo/launch.py').write_text("import subprocess, sys, time\nsubprocess.Popen([sys.executable, 'child.py'])\ntime.sleep(60)\n")
    result = run_tests(tmp_path / 'repo', [{'tool': 'python3', 'args': ['launch.py']}], timeout=2)
    assert result['status'] == 'timeout'
    import time
    time.sleep(0.5)
    first = marker.read_text() if marker.exists() else None
    time.sleep(0.5)
    assert (marker.read_text() if marker.exists() else None) == first, 'grandchild kept running after timeout'


def test_apply_files_rejects_symlinked_parents_and_stale_proposals(tmp_path):
    from codemri.runner import apply_files
    work = tmp_path / 'work'
    (work / 'src').mkdir(parents=True)
    (work / 'src/a.ts').write_text('old\n')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (work / 'linked').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic link'):
        apply_files(work, [{'path': 'linked/evil.txt', 'after': 'x'}])
    assert not (outside / 'evil.txt').exists()
    with pytest.raises(ValueError, match='stale'):
        apply_files(work, [{'path': 'src/a.ts', 'before': 'something else\n', 'after': 'new\n'}])
    assert (work / 'src/a.ts').read_text() == 'old\n'
    apply_files(work, [{'path': 'src/a.ts', 'before': 'old\n', 'after': 'new\n'}, {'path': 'src/b.ts', 'before': None, 'after': 'b\n'}])
    assert (work / 'src/a.ts').read_text() == 'new\n' and (work / 'src/b.ts').read_text() == 'b\n'


def test_scrubbed_env_strips_credentials_but_honours_keep_list(monkeypatch):
    from codemri.runner import scrubbed_env
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'x'); monkeypatch.setenv('SSH_AUTH_SOCK', '/tmp/s'); monkeypatch.setenv('GITHUB_TOKEN', 'x')
    monkeypatch.setenv('OPENAI_API_KEY', 'x'); monkeypatch.setenv('PATH', '/usr/bin')
    monkeypatch.setenv('CODEMRI_SUBPROCESS_ENV_KEEP', 'OPENAI_API_KEY')
    env = scrubbed_env()
    assert 'AWS_SECRET_ACCESS_KEY' not in env and 'SSH_AUTH_SOCK' not in env and 'GITHUB_TOKEN' not in env
    assert env['OPENAI_API_KEY'] == 'x' and env['PATH'] == '/usr/bin'


def test_output_capture_is_bounded_and_repo_cannot_shadow_tools(tmp_path):
    from codemri.runner import OUTPUT_LIMIT, run_process, scrubbed_env
    repo = tmp_path / 'repo'
    (repo / 'node_modules/.bin').mkdir(parents=True)
    (repo / 'spam.py').write_text("import sys\nfor _ in range(20000): sys.stdout.write('x' * 100 + '\\n')\nprint('END')\n")
    env = scrubbed_env()
    env['PATH'] = str(repo / 'node_modules/.bin') + ':' + env.get('PATH', '')
    proc = run_process(['python3', 'spam.py'], repo, env, timeout=60)
    assert proc.returncode == 0 and proc.stdout.endswith('END\n') and len(proc.stdout) <= OUTPUT_LIMIT
    assert str(repo) not in proc.args[0]
    fake = repo / 'node_modules/.bin/python3'
    fake.write_text('#!/bin/sh\necho hijacked\n'); fake.chmod(0o755)
    proc = run_process(['python3', '-c', 'print("real")'], repo, env, timeout=30)
    assert proc.stdout.strip() == 'real'
    with pytest.raises(ValueError):
        run_process([str(fake)], repo, env, timeout=30)


def test_surefire_aggregate_is_not_double_counted():
    from codemri.runner import summarize
    out = ('[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.1 s - in a.ATest\n'
           '[INFO] Tests run: 2, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.1 s - in a.BTest\n'
           '[INFO] Results:\n[ERROR] Tests run: 5, Failures: 1, Errors: 0, Skipped: 0\n')
    assert summarize('mvn', out, '') == {'passed': 4, 'failed': 1, 'skipped': 0, 'no_tests_ran': False}


def test_run_process_times_out_when_child_never_reads_large_stdin(tmp_path):
    import subprocess, time
    from codemri.runner import run_process, scrubbed_env
    (tmp_path / 'sleepy.py').write_text('import time\ntime.sleep(30)\n')
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(['python3', 'sleepy.py'], tmp_path, scrubbed_env(), timeout=2, stdin_text='x' * 2_000_000)
    assert time.monotonic() - started < 15


def test_copy_leaves_out_secret_files(tmp_path):
    from codemri.runner import copy_repository
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/a.js').write_text('1')
    (tmp_path / '.env').write_text('TOKEN=abc')
    (tmp_path / 'id_rsa').write_text('key')
    work = copy_repository(tmp_path)
    assert (work / 'src/a.js').is_file() and not (work / '.env').exists() and not (work / 'id_rsa').exists()


def test_all_skipped_suite_is_not_no_tests():
    from codemri.runner import summarize
    counts = summarize('pytest', '3 skipped in 0.10s', '')
    assert counts['skipped'] == 3 and counts['no_tests_ran'] is False


def test_stale_addition_is_rejected_when_path_already_exists(tmp_path):
    from codemri.runner import apply_files
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/cache.ts').write_text('user wrote this\n')
    with pytest.raises(ValueError, match='stale'):
        apply_files(tmp_path, [{'path': 'src/cache.ts', 'before': None, 'after': 'proposed\n'}])
    assert (tmp_path / 'src/cache.ts').read_text() == 'user wrote this\n'
    apply_files(tmp_path, [{'path': 'src/new.ts', 'before': None, 'after': 'ok\n'}])
    assert (tmp_path / 'src/new.ts').read_text() == 'ok\n'


def test_proxy_credentials_are_scrubbed(monkeypatch):
    from codemri.runner import scrubbed_env
    monkeypatch.setenv('HTTPS_PROXY', 'http://user:pw@proxy.example:3128')
    monkeypatch.setenv('HTTP_PROXY', 'http://proxy.example:3128')
    env = scrubbed_env()
    assert 'HTTPS_PROXY' not in env and env['HTTP_PROXY'] == 'http://proxy.example:3128'


def test_failed_copy_removes_its_temporary_directory(tmp_path, monkeypatch):
    import tempfile
    from codemri import runner
    (tmp_path / 'src').mkdir()
    monkeypatch.setattr(runner, 'write_copy_marker', lambda root, work: (_ for _ in ()).throw(OSError('disk full')))
    before = set(Path(tempfile.gettempdir()).glob('codemri-run-*'))
    with pytest.raises(OSError):
        runner.copy_repository(tmp_path)
    assert set(Path(tempfile.gettempdir()).glob('codemri-run-*')) == before


def test_tool_paths_are_rejected_even_with_an_allowed_basename():
    with pytest.raises(ValueError):
        parse_commands([{'tool': '/opt/evil/node', 'args': ['--test', 'a.js']}])


def test_empty_suite_before_positive_aggregate_is_not_no_tests():
    out = 'Tests run: 0, Failures: 0, Errors: 0, Skipped: 0\nResults:\nTests run: 5, Failures: 0, Errors: 0, Skipped: 0\n'
    assert summarize('mvn', out, '') == {'passed': 5, 'failed': 0, 'skipped': 0, 'no_tests_ran': False}
